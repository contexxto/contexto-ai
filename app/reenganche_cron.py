"""
Cron de Reenganche (Fase 2) — vive DENTRO de la app (tarea de fondo), no en un
servicio aparte ni en WhatsApp. Cada cierto tiempo barre los leads dormidos y,
cuando el motor (app/reenganche) dispara por VALOR, avisa por los canales que la
app YA tiene (Web Push + email/Resend) a UNA audiencia AUTORIZADA, o a ninguna:

  · al COMPRADOR, si dejó canal y un grant vivo para ese canal (Fase 3, TR-5);
  · al CORREDOR del inmueble exacto, solo si la persona le PIDIÓ contacto para ese
    inmueble (SEC-X2-EGRESS-R0) — humano en el lazo.

Sin ninguna de las dos autoridades, silencio: que el comprador no tenga grant no
autoriza a avisar al corredor, y llegar por un QR tampoco.

Config por entorno (todas opcionales, con defaults sensatos):
  REENGANCHE_CRON_ENABLED   "1"/"0"     habilita el barrido (default "1"). Se consulta al arrancar
                                        el bucle Y en cada barrido: apagarla detiene todo efecto.
  REENGANCHE_CRON_INTERVAL  segundos entre barridos (default 21600 = 6 h, mínimo 300)
  REENGANCHE_CRON_LIMITE    máx leads por barrido (default 200)
  REENGANCHE_BAJA_SECRET    secreto DEDICADO del enlace de baja (≥ 32 caracteres; ver
                            app/baja_aviso.py). Sin él no sale NINGÚN aviso al comprador
                            (Plan 1.1 · TR-2, fail-closed); el aviso al corredor no depende de él.

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


def _holdout_pct() -> int:
    """% de dormidos elegibles que se RETIENE como control (no se les manda el touch automático),
    el contrafactual de la métrica de lift. Default 20 (aprobado para el piloto). 0 = desactivado.
    Desde SEC-X2-EGRESS-R0 se aplica SOLO a la población que el corredor está autorizado a recibir
    (el comprador no entra al experimento). Ver docs/DISENO_Metrica_Lift_Intencion.md §3."""
    try:
        return min(100, max(0, int(os.getenv("REENGANCHE_HOLDOUT_PCT", "20"))))
    except ValueError:
        return 20


def habilitado() -> bool:
    return os.getenv("REENGANCHE_CRON_ENABLED", "1").strip().lower() not in ("0", "false", "no", "")


def auto_lead() -> bool:
    """Fase 3: si True, cuando el comprador dejó canal + consentimiento el reenganche le
    llega a ÉL directo (email/push). Si no, el comprador no recibe nada y el corredor solo
    recibe con su propia autoridad (SEC-X2-EGRESS-R0). Default True."""
    return os.getenv("REENGANCHE_AUTO_LEAD", "1").strip().lower() not in ("0", "false", "no", "")


def _horas_inactividad(ua: datetime | None) -> float | None:
    if ua is None:
        return None
    if ua.tzinfo is None:
        ua = ua.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - ua).total_seconds() / 3600.0)


_scan_lock = asyncio.Lock()


_APAGADO = {"escaneados": 0, "disparados": 0, "corredores": 0, "deshabilitado": True}


async def escanear_reenganches(db) -> dict:
    """ÚNICA entrada al barrido. Con REENGANCHE_CRON_ENABLED apagada no hace NADA: ni lee
    leads, ni escribe lead_actividad, ni calcula destinatarios, ni manda correo o push.

    La bandera se comprueba aquí y no solo en iniciar_cron (Plan 1.1 · TR-4): el control del
    arranque evita crear el bucle, pero no protege a un caller que ya existe ni a una bandera
    que cambió después del arranque. Se vuelve a mirar tras el candado porque quien esperaba
    turno pudo entrar con la bandera ya apagada.

    El candado serializa el barrido en esta instancia: dos barridos simultáneos no avisan dos
    veces (el segundo re-lee lo ya marcado). Ver _escanear_reenganches para la lógica."""
    if not habilitado():
        log.info("Reenganche: barrido omitido (REENGANCHE_CRON_ENABLED=0).")
        return dict(_APAGADO)
    async with _scan_lock:
        if not habilitado():
            return dict(_APAGADO)
        return await _escanear_reenganches(db)


async def _escanear_reenganches(db) -> dict:
    """Un barrido: detecta leads dormidos con disparo por valor y produce, como mucho, UN efecto
    por lead y solo hacia una audiencia AUTORIZADA (SEC-X2-EGRESS-R0):

      A · el COMPRADOR (PRINCIPAL_SELF), con su grant por canal (TR-5: autorizar_efecto_reenganche);
      B · el CORREDOR del inmueble EXACTO del lead, con el hecho X2 (corredor_autorizado) y una
          elegibilidad calculada SOLO con lo que tiene alcance a ese inmueble
          (intencion_de_sesion(…, activo_id=X), la frontera R0c; sin respaldo de sesión entera).

    Sin audiencia autorizada → SILENCIO: ni aviso, ni grupo, ni elegible_en, ni enviado_en. El
    NO_GRANT del comprador ya no deriva al corredor (DR-15 retirado): no es autoridad para nadie.

    El experimento tocado-vs-holdout (`reenganche_grupo`, `reenganche_elegible_en`) alimenta una
    métrica y un comportamiento del CRM que ve el corredor, así que es SOLO de la rama B: un efecto
    al comprador deja únicamente la marca de envío (dosis única), nunca grupo ni elegibilidad.
    ASIGNAR AL EXPERIMENTO ES UN CAMBIO DE ESTADO CON CONSECUENCIAS: exige la misma población
    autorizada que el aviso.

    Idempotente vía la marca de envío y el grupo (anti-repetición). Devuelve un resumen
    {escaneados, disparados, holdout, comprador, corredores}.

    NO llamar directo: no mira la bandera. La única entrada es escanear_reenganches
    (tests/test_tr4_reenganche.py lo impone sobre todo el código de producción)."""
    from app.reenganche import evaluar_reenganche, HORAS_DORMIDO
    from app.routers.chat import intencion_de_sesion, _corredor_de_activo, ensure_lead_actividad
    from app.notifications import send_notification
    from app.lift import grupo_holdout
    from app import baja_aviso
    from app.autoridad_reenganche import (
        EstadoAutorizacion, autorizar_efecto_reenganche, corredor_autorizado)

    pct = _holdout_pct()
    await ensure_lead_actividad(db)
    try:
        # UNA dosis automática por lead de por vida: se escanea hasta que produce un efecto; luego queda
        # con la marca de envío (comprador o corredor tocado) o en 'holdout' (control del corredor) y no
        # vuelve a entrar. Alinea con "aportar valor sin presionar": el cron no pinguea en bucle.
        filas = (await db.execute(
            text(
                "SELECT session_id, activo_id::text AS activo_id, ultima_actividad, "
                "       lead_email, lead_push "
                "FROM lead_actividad "
                "WHERE ultima_actividad < now() - make_interval(hours => :dorm) "
                "  AND reenganche_enviado_en IS NULL "   # nunca tocado
                "  AND reenganche_grupo IS NULL "        # ni asignado a un grupo (tocado/holdout)
                # Plan 1.1 · TR-2: un CIERRE explícito saca la fila del barrido COMPLETO, antes del
                # holdout, del scoring, de la marca de grupo y de cualquier aviso (comprador o corredor).
                "  AND reenganche_cerrado_en IS NULL "
                "ORDER BY ultima_actividad ASC LIMIT :lim"
            ),
            {"dorm": HORAS_DORMIDO, "lim": _limite()},
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

    # 1 · LECTURAS, todas ANTES de reservar ningún grant: un rollback aquí (ficha, corredor, hecho X2)
    # no puede deshacer un permiso ya consumido.
    leads: list[dict] = []
    for f in filas:
        sid = f["session_id"]
        activo_id = f["activo_id"]
        horas = _horas_inactividad(f["ultima_actividad"])
        info = await _info_activo(activo_id)
        canales = (["EMAIL"] if f["lead_email"] else []) + (["PUSH"] if f["lead_push"] else [])
        # A · comprador: misma semántica que antes (sesión entera). Este barrido NO adjudica si la
        # personalización al PROPIO comprador debe acotarse al inmueble: no es divulgación a terceros.
        decision = None
        if auto_lead() and canales:
            try:
                intenc = await intencion_de_sesion(sid, horas_inactividad=horas)
            except Exception:  # noqa: BLE001
                intenc = {}
            if intenc.get("turnos"):  # solo escaneó / sin mensajes → no es un lead real
                decision = evaluar_reenganche(
                    intencion=intenc, horas_inactividad=horas,
                    direccion=info["direccion"], novedades=info["novedades"],
                )
        leads.append({"sid": sid, "activo_id": activo_id, "f": f, "info": info, "horas": horas,
                      "canales": canales, "decision": decision,
                      # B · el hecho X2 para el inmueble EXACTO del lead, nada más.
                      "corredor_autorizado": await corredor_autorizado(db, session_id=sid, activo_id=activo_id)})

    # 2 · DECISIÓN por lead: una audiencia autorizada o ninguna. Con reserva, la frontera TR-5 marca
    # `used_at` en la MISMA transacción que la marca de envío de abajo: un solo COMMIT para permiso
    # consumido + lead marcado, y sólo después el envío.
    a_comprador: list[dict] = []
    ids_comprador: list[str] = []
    tocados: list[str] = []
    holdouts: list[str] = []
    por_corredor: dict[str, dict] = {}
    for c in leads:
        sid, f, info, activo_id = c["sid"], c["f"], c["info"], c["activo_id"]
        if c["decision"]:
            # Plan 1.1 · TR-2: cada aviso al comprador lleva su enlace de baja. Sin
            # REENGANCHE_BAJA_SECRET no se puede emitir: entonces se consulta la frontera SIN
            # reservar (no se gasta el permiso) y, si lo había, el lead queda intacto — ni
            # comprador, ni corredor, ni marca — hasta que el secreto exista.
            try:
                baja = baja_aviso.emitir(sid)
            except baja_aviso.SinSecretoDeBaja:
                baja = None
            veredicto = await autorizar_efecto_reenganche(
                db, session_id=sid, canales_candidatos=c["canales"], reservar=baja is not None)
            if veredicto.estado is EstadoAutorizacion.ERROR:
                # Sin decisión no hay efecto ni marca, para NINGUNA audiencia: un fallo de autoridad
                # no se esconde detrás del camino del corredor. Sin marca, vuelve al próximo barrido.
                log.error("Reenganche cron: autoridad en ERROR — lead omitido.")
                continue
            if veredicto.estado is EstadoAutorizacion.AUTHORIZED:
                if baja is None:
                    log.error("Reenganche cron: sin secreto de baja — aviso al comprador omitido.")
                    continue
                ids_comprador.append(sid)
                a_comprador.append({
                    "email": f["lead_email"] if "EMAIL" in veredicto.canales else None,
                    "push": f["lead_push"] if "PUSH" in veredicto.canales else None,
                    "mensaje": c["decision"]["mensaje"],
                    "activo_id": activo_id, "baja": baja,
                })
                # UNA audiencia por lead: el comprador tiene prioridad. Su efecto no avisa al corredor
                # (un grant del comprador no lo autoriza) ni entra a su experimento.
                continue
            # NO_GRANT → ningún efecto al comprador. Y NO es autoridad para el corredor: la rama B se
            # evalúa abajo por su cuenta, exactamente igual que para un lead sin canal propio.

        # B · corredor del inmueble EXACTO. Orden: autoridad → canal → elegibilidad acotada → grupo.
        # Nada de lo que sigue (ni el holdout) ocurre para un lead sin el hecho X2.
        if not c["corredor_autorizado"]:
            continue  # ni el QR, ni la atribución, ni el NO_GRANT del comprador: silencio
        if not info["email"] and not info["sub"]:
            continue  # sin canal no hay tratamiento posible → tampoco un control válido
        try:
            intenc_x = await intencion_de_sesion(sid, horas_inactividad=c["horas"], activo_id=activo_id)
        except Exception:  # noqa: BLE001
            continue
        if not intenc_x.get("turnos"):
            continue
        if not evaluar_reenganche(
            intencion=intenc_x, horas_inactividad=c["horas"],
            direccion=info["direccion"], novedades=info["novedades"],
        ):
            # Lo hablado de otro inmueble, o el AgentState sin procedencia, no vuelve elegible a X.
            # Sin respaldo a la sesión entera: silencio.
            continue
        # Holdout (contrafactual de la métrica de lift): un % de la población AUTORIZADA y elegible del
        # corredor no recibe el touch automático y queda como control desde su momento de elegibilidad.
        # Control y tratamiento son la MISMA audiencia y la misma clase de tratamiento. El corredor
        # humano igual puede retomarlos a mano desde el CRM. Ver docs/DISENO_Metrica_Lift_Intencion.md §3.
        if grupo_holdout(sid, pct) == "holdout":
            holdouts.append(sid)
            continue
        tocados.append(sid)
        # Agrupa por corredor (id del dueño; email/activo solo como respaldo) para un único aviso. N
        # cuenta SOLO leads que pasaron uno a uno la autoridad, la elegibilidad acotada y el grupo tocado.
        clave = info["corredor_id"] or info["email"] or f"activo:{activo_id}"
        grupo = por_corredor.setdefault(clave, {"email": info["email"], "sub": info["sub"], "n": 0})
        grupo["n"] += 1

    disparados = len(ids_comprador) + len(tocados)
    if not disparados and not holdouts:
        return {"escaneados": len(filas), "disparados": 0, "holdout": 0, "comprador": 0, "corredores": 0}

    # 3 · MARCAS, todas en UN commit y ANTES de notificar: si un envío falla, no se reintenta en bucle
    # (mejor perder un aviso que spammear). El COMMIT confirma a la vez los permisos consumidos (TR-5);
    # si falla, se deshace todo y no sale nada.
    try:
        if ids_comprador:
            # Comprador: SOLO la marca de envío (anti-repetición). Sin grupo ni elegible_en: un efecto
            # PRINCIPAL_SELF no es una observación del experimento del corredor.
            await db.execute(
                text("UPDATE lead_actividad SET reenganche_enviado_en = now() "
                     "WHERE session_id = ANY(:ids)"),
                {"ids": ids_comprador},
            )
        if holdouts:
            # Control del corredor: grupo + momento de elegibilidad, SIN envío. elegible_en se fija una
            # sola vez (COALESCE) para anclar la primera elegibilidad. No re-entra (el SELECT lo excluye).
            await db.execute(
                text("UPDATE lead_actividad SET reenganche_grupo = 'holdout', "
                     "reenganche_elegible_en = COALESCE(reenganche_elegible_en, now()) "
                     "WHERE session_id = ANY(:ids)"),
                {"ids": holdouts},
            )
        if tocados:
            await db.execute(
                text("UPDATE lead_actividad SET reenganche_enviado_en = now(), reenganche_grupo = 'tocado', "
                     "reenganche_elegible_en = COALESCE(reenganche_elegible_en, now()) "
                     "WHERE session_id = ANY(:ids)"),
                {"ids": tocados},
            )
        await db.commit()
    except Exception:  # noqa: BLE001
        await db.rollback()
        return {"escaneados": len(filas), "disparados": disparados, "holdout": len(holdouts),
                "comprador": 0, "corredores": 0}

    # Fase 3: al COMPRADOR directo, SÓLO por los canales que la frontera autorizó (un grant de
    # EMAIL no abre el PUSH ni al revés) → el mensaje de valor con deep-link al inmueble.
    enviados_comprador = 0
    for c in a_comprador:
        if not c["email"] and not c["push"]:
            continue
        try:
            await send_notification(
                email=c["email"], push_subscription=c["push"],
                title="Novedad sobre el inmueble que viste",
                body=c["mensaje"],
                # El toque (push) y el botón (correo) abren el inmueble con la confirmación de
                # baja a mano; el correo lleva además el enlace explícito al pie.
                url=f"/a/{c['activo_id']}?baja={c['baja']}",
                baja_url=f"/?baja={c['baja']}",
                email_subject="Contexto · una novedad verificada para ti",
            )
            enviados_comprador += 1
        except Exception as exc:  # noqa: BLE001
            log.error("Reenganche cron: fallo avisando al comprador: %s", exc)

    notificados = 0
    for grupo in por_corredor.values():
        n = grupo["n"]
        plural = "s" if n != 1 else ""
        try:
            await send_notification(
                email=grupo["email"], push_subscription=grupo["sub"],
                title="Interesados para reenganchar",
                body=(f"Tienes {n} interesado{plural} dormido{plural} con dato verificado "
                      "para retomar por valor. Míralos en tu CRM."),
                url="/?crm=1",
                email_subject="Contexto · interesados para reenganchar",
            )
            notificados += 1
        except Exception as exc:  # noqa: BLE001
            log.error("Reenganche cron: fallo notificando corredor: %s", exc)

    log.info("Reenganche cron: %d escaneados, %d disparados, %d holdout, %d a comprador, %d a corredor",
             len(filas), disparados, len(holdouts), enviados_comprador, notificados)
    return {"escaneados": len(filas), "disparados": disparados, "holdout": len(holdouts),
            "comprador": enviados_comprador, "corredores": notificados}


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
