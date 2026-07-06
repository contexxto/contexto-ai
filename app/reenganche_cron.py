"""
Cron de Reenganche (Fase 2) — vive DENTRO de la app (tarea de fondo), no en un
servicio aparte ni en WhatsApp. Cada cierto tiempo barre los leads dormidos y,
cuando el motor (app/reenganche) dispara por VALOR, avisa al CORREDOR por los
canales que la app YA tiene (Web Push + email/Resend) para que retome la
conversación — humano en el lazo.

NO mensajea al comprador directo: los leads dormidos-no-calientes no dejaron un
canal propio (no pidieron corredor → sin email ni push del comprador). Alcanzar
al comprador directo exige capturar su contacto o WhatsApp — es un paso aparte.

Config por entorno (todas opcionales, con defaults sensatos):
  REENGANCHE_CRON_ENABLED   "1"/"0"     habilita el barrido de fondo (default "1")
  REENGANCHE_CRON_INTERVAL  segundos entre barridos (default 21600 = 6 h, mínimo 300)
  REENGANCHE_CRON_LIMITE    máx leads por barrido (default 200)

Asume una sola instancia web (plan starter de Render, no duerme). El anti-repetición
(reenganche_enviado_en) hace inocuo un doble-barrido si algún día se escala.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import text

log = logging.getLogger(__name__)


def _intervalo() -> int:
    try:
        return max(300, int(os.getenv("REENGANCHE_CRON_INTERVAL", "21600")))
    except ValueError:
        return 21600


def _limite() -> int:
    try:
        return max(1, int(os.getenv("REENGANCHE_CRON_LIMITE", "200")))
    except ValueError:
        return 200


def habilitado() -> bool:
    return os.getenv("REENGANCHE_CRON_ENABLED", "1").strip().lower() not in ("0", "false", "no", "")


def _horas_inactividad(ua: datetime | None) -> float | None:
    if ua is None:
        return None
    if ua.tzinfo is None:
        ua = ua.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - ua).total_seconds() / 3600.0)


_scan_lock = asyncio.Lock()


async def escanear_reenganches(db) -> dict:
    """Serializa el barrido en esta instancia: si el endpoint manual y el bucle de
    fondo coinciden, el segundo espera y re-lee (ya marcado) → sin doble aviso.
    Ver _escanear_reenganches para la lógica."""
    async with _scan_lock:
        return await _escanear_reenganches(db)


async def _escanear_reenganches(db) -> dict:
    """Un barrido: detecta leads dormidos con disparo por valor y avisa al corredor.
    Idempotente vía reenganche_enviado_en (anti-repetición). Devuelve un resumen
    {escaneados, disparados, corredores}."""
    from app.reenganche import evaluar_reenganche, HORAS_DORMIDO, HORAS_ANTI_REPETICION
    from app.routers.chat import intencion_de_sesion, _corredor_de_activo, ensure_lead_actividad
    from app.notifications import send_notification

    await ensure_lead_actividad(db)
    try:
        filas = (await db.execute(
            text(
                "SELECT session_id, activo_id::text AS activo_id, ultima_actividad "
                "FROM lead_actividad "
                "WHERE ultima_actividad < now() - make_interval(hours => :dorm) "
                "  AND (reenganche_enviado_en IS NULL "
                "       OR reenganche_enviado_en < now() - make_interval(hours => :rep)) "
                "ORDER BY ultima_actividad ASC LIMIT :lim"
            ),
            {"dorm": HORAS_DORMIDO, "rep": HORAS_ANTI_REPETICION, "lim": _limite()},
        )).mappings().all()
    except Exception:  # noqa: BLE001 — tabla aún no creada / fallo transitorio
        await db.rollback()
        return {"escaneados": 0, "disparados": 0, "corredores": 0}

    if not filas:
        return {"escaneados": 0, "disparados": 0, "corredores": 0}

    # Cache por-activo: direccion, novedad verificada, corredor (email/push).
    cache: dict[str, dict] = {}

    async def _info_activo(activo_id: str) -> dict:
        if activo_id in cache:
            return cache[activo_id]
        info = {"direccion": None, "novedades": [], "email": None, "sub": None, "corredor_id": None}
        try:
            row = (await db.execute(
                text("SELECT a.direccion_estandarizada AS dir, a.walk_score_fuente AS f, "
                     "COALESCE(a.owner_user_id, ag.owner_user)::text AS corredor_id "
                     "FROM activos_inmutables a "
                     "LEFT JOIN agencies ag ON ag.id = a.owner_agency_id "
                     "WHERE a.id = :id"),
                {"id": activo_id},
            )).mappings().first()
            if row:
                info["direccion"] = row["dir"]
                info["corredor_id"] = row["corredor_id"]
                if row["f"] == "osm":
                    info["novedades"] = [{
                        "tipo": "entorno",
                        "etiqueta": "la caminabilidad del entorno medida con comercios reales (no una estimación)",
                    }]
        except Exception:  # noqa: BLE001
            await db.rollback()
        try:
            info["email"], info["sub"] = await _corredor_de_activo(db, activo_id)
        except Exception:  # noqa: BLE001
            await db.rollback()
        cache[activo_id] = info
        return info

    disparados: list[str] = []
    por_corredor: dict[str, dict] = {}
    for f in filas:
        sid = f["session_id"]
        activo_id = f["activo_id"]
        horas = _horas_inactividad(f["ultima_actividad"])
        try:
            intenc = await intencion_de_sesion(sid, horas_inactividad=horas)
        except Exception:  # noqa: BLE001
            continue
        if not intenc.get("turnos"):
            continue  # solo escaneó / sin mensajes → no es un lead real
        info = await _info_activo(activo_id)
        decision = evaluar_reenganche(
            intencion=intenc, horas_inactividad=horas,
            direccion=info["direccion"], novedades=info["novedades"],
        )
        if not decision:
            continue
        disparados.append(sid)
        # Agrupa por corredor (id del dueño; email/activo solo como respaldo) para
        # un único aviso — así un corredor con push y sin email no recibe doble push.
        clave = info["corredor_id"] or info["email"] or f"activo:{activo_id}"
        grupo = por_corredor.setdefault(clave, {"email": info["email"], "sub": info["sub"], "n": 0})
        grupo["n"] += 1

    if not disparados:
        return {"escaneados": len(filas), "disparados": 0, "corredores": 0}

    # Marcar anti-repetición ANTES de notificar: si un envío falla, no se reintenta
    # en bucle (mejor perder un aviso que spammear al corredor).
    try:
        await db.execute(
            text("UPDATE lead_actividad SET reenganche_enviado_en = now() WHERE session_id = ANY(:ids)"),
            {"ids": disparados},
        )
        await db.commit()
    except Exception:  # noqa: BLE001
        await db.rollback()
        return {"escaneados": len(filas), "disparados": len(disparados), "corredores": 0}

    notificados = 0
    for grupo in por_corredor.values():
        if not grupo["email"] and not grupo["sub"]:
            continue  # sin canal al corredor → no hay a quién avisar
        n = grupo["n"]
        plural = "s" if n != 1 else ""
        try:
            await send_notification(
                email=grupo["email"], push_subscription=grupo["sub"],
                title="Interesados para reenganchar",
                body=(f"Tienes {n} interesado{plural} dormido{plural} con dato verificado "
                      "para retomar por valor. Míralos en tu CRM."),
                url="/?crm=1",
                email_subject="Contexto AI · interesados para reenganchar",
            )
            notificados += 1
        except Exception as exc:  # noqa: BLE001
            log.error("Reenganche cron: fallo notificando corredor: %s", exc)

    log.info("Reenganche cron: %d escaneados, %d disparados, %d corredores notificados",
             len(filas), len(disparados), notificados)
    return {"escaneados": len(filas), "disparados": len(disparados), "corredores": notificados}


# ── Bucle de fondo (el "cron" dentro de la app) ─────────────────────────────
_tarea: asyncio.Task | None = None


async def _bucle() -> None:
    from app.database import AsyncSessionLocal
    intervalo = _intervalo()
    log.info("Reenganche cron activo (barrido cada %ds).", intervalo)
    while True:
        try:
            await asyncio.sleep(intervalo)
            async with AsyncSessionLocal() as db:
                await escanear_reenganches(db)
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001 — jamás morir por un barrido fallido
            log.error("Reenganche cron: barrido falló: %s", exc)


def iniciar_cron() -> None:
    """Arranca el bucle de fondo (desde el lifespan de la app). Idempotente."""
    global _tarea
    if not habilitado():
        log.info("Reenganche cron deshabilitado (REENGANCHE_CRON_ENABLED=0).")
        return
    if _tarea is None or _tarea.done():
        _tarea = asyncio.create_task(_bucle())


async def detener_cron() -> None:
    """Detiene el bucle de fondo (desde el shutdown del lifespan)."""
    global _tarea
    if _tarea and not _tarea.done():
        _tarea.cancel()
        try:
            await _tarea
        except asyncio.CancelledError:
            pass
    _tarea = None
