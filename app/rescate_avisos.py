"""
Correo de RESCATE — el único correo que genera una conversación.

Decisión de producto (Carlos, 2026-08-12): el correo no es una copia de cada mensaje. La
conversación vive en la campana (dentro de la app, no depende de nada) y en el push
(inmediato, si concedió permiso). El correo queda para novedades, promociones y
reenganche… con una excepción: si el aviso lleva horas SIN LEER, hay que rescatar al
interesado. Es el modelo de Slack o LinkedIn — no te escriben por cada mensaje, te
escriben si te lo perdiste.

Sin esto, un interesado que no dio permiso de push y no vuelve a abrir la app nunca se
entera de que el corredor le respondió: el lead se pierde en silencio, que es justo el
fallo que hemos estado persiguiendo todo el día.

Un solo correo por dirección y barrido, aunque tenga cinco avisos pendientes: se rescata
a la persona, no se le reenvía la conversación.

SEC-X2-B5 · el correo de un interesado sin cuenta es el de SU hilo exacto: el del handoff
`(sesión, inmueble del aviso)` y solo si ese hilo está autorizado (`principal_requested_at`).
Nunca «cualquier `lead_email` de la sesión»: otra fila puede ser histórica (contacto escrito
antes de cualquier acto) o de otro inmueble. Sin correo autorizado exacto, no hay correo de
rescate (falla cerrado; la campana sigue ahí).
"""
from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy import text

log = logging.getLogger(__name__)

_tarea: asyncio.Task | None = None


def _horas_espera() -> float:
    """Horas que un aviso puede estar sin leer antes de rescatar por correo."""
    try:
        return max(0.1, float(os.getenv("RESCATE_HORAS", "2")))
    except ValueError:
        return 2.0


def _intervalo() -> int:
    """Segundos entre barridos."""
    try:
        return max(60, int(os.getenv("RESCATE_INTERVALO_SEG", "900")))
    except ValueError:
        return 900


def habilitado() -> bool:
    return os.getenv("RESCATE_ENABLED", "1") not in ("0", "false", "False")


async def escanear_rescates(db) -> dict:
    """Busca avisos sin leer y vencidos, y manda UN correo por destinatario.

    `rescate_en` marca lo ya rescatado: sin esa marca, cada barrido reenviaría el mismo
    aviso cada 15 minutos — exactamente el spam que veníamos a quitar.
    """
    from app.notifications import send_notification, APP_URL

    horas = _horas_espera()
    filas = (await db.execute(text(
        "SELECT n.id, n.destinatario_user_id::text AS uid, n.destinatario_session AS sid, "
        "       n.activo_id::text AS aid, n.titulo, n.cuerpo, n.url "
        "FROM notificacion n "
        "WHERE n.leida_en IS NULL AND n.rescate_en IS NULL "
        "  AND n.creada_en < now() - make_interval(hours => :h) "
        "ORDER BY n.creada_en ASC LIMIT 200"), {"h": horas})).mappings().all()
    if not filas:
        return {"rescatados": 0, "avisos": 0}

    # Agrupa por destinatario: una persona, un correo, aunque tenga cinco avisos.
    por_destinatario: dict[str, list] = {}
    for f in filas:
        clave = f["uid"] or f["sid"]
        if clave:
            por_destinatario.setdefault(clave, []).append(f)

    enviados = 0
    for clave, avisos in por_destinatario.items():
        ids = [a["id"] for a in avisos]
        # Se marcan SIEMPRE, haya correo o no: sin dirección no hay nada que reintentar,
        # y dejarlos sin marcar los haría reaparecer en cada barrido para siempre.
        await db.execute(text(
            "UPDATE notificacion SET rescate_en = now() WHERE id = ANY(:ids)"), {"ids": ids})
        # SEC-X2-B5 · el destino se resuelve POR AVISO (su hilo exacto), no por sesión: dos
        # avisos de la misma persona pueden ser de hilos distintos, cada uno con su correo
        # autorizado o sin ninguno. Un correo por DIRECCIÓN.
        por_correo: dict[str, list] = {}
        for a in avisos:
            correo = await _correo_de(db, a["uid"], a["sid"], a["aid"])
            if correo:
                por_correo.setdefault(correo, []).append(a)
        for correo, grupo in por_correo.items():
            ultimo = grupo[-1]
            cuantos = len(grupo)
            titulo = (ultimo["titulo"] if cuantos == 1
                      else f"Tienes {cuantos} mensajes sin leer en Contexto")
            cuerpo = (ultimo["cuerpo"] or "Abre Contexto para continuar la conversación.")
            try:
                await send_notification(
                    email=correo, push_subscription=None,
                    title=titulo, body=cuerpo, url=ultimo["url"] or "/",
                    email_subject=titulo,
                )
                enviados += 1
            except Exception as exc:  # noqa: BLE001 — un envío fallido no aborta el barrido
                log.warning("Rescate: no se pudo avisar a %s: %s", clave, exc)
    await db.commit()
    log.info("Rescate: %d correos por %d avisos sin leer (>%sh)", enviados, len(filas), horas)
    return {"rescatados": enviados, "avisos": len(filas)}


async def _correo_de(db, user_id: str | None, session_id: str | None,
                     activo_id: str | None) -> str | None:
    """Dirección del destinatario: de su cuenta si la tiene, o del handoff si es un
    interesado sin registrar — SOLO el de su hilo exacto `(session_id, activo_id)` y solo si
    ese hilo está autorizado (SEC-X2-B5). Un aviso sin inmueble (los históricos quedan en
    NULL) no tiene hilo exacto: sin correo."""
    if user_id:
        correo = (await db.execute(text(
            "SELECT email FROM push_usuario WHERE user_id = CAST(:u AS uuid)"),
            {"u": user_id})).scalar()
        if correo:
            return correo
    if session_id and activo_id:
        return (await db.execute(text(
            "SELECT lead_email FROM handoff_sesion "
            "WHERE session_id = :s AND activo_id = CAST(:a AS uuid) "
            "  AND principal_requested_at IS NOT NULL AND lead_email IS NOT NULL"),
            {"s": session_id, "a": activo_id})).scalar()
    return None


async def _bucle() -> None:
    from app.database import AsyncSessionLocal
    intervalo = _intervalo()
    log.info("Rescate de avisos activo (barrido cada %ds, espera %sh).", intervalo, _horas_espera())
    while True:
        try:
            await asyncio.sleep(intervalo)
            async with AsyncSessionLocal() as db:
                await escanear_rescates(db)
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001 — jamás morir por un barrido fallido
            log.error("Rescate: barrido falló: %s", exc)


def iniciar_rescate() -> None:
    """Arranca el bucle de fondo (desde el lifespan de la app). Idempotente."""
    global _tarea
    if not habilitado():
        log.info("Rescate de avisos deshabilitado (RESCATE_ENABLED=0).")
        return
    if _tarea is None or _tarea.done():
        _tarea = asyncio.create_task(_bucle())


async def detener_rescate() -> None:
    global _tarea
    if _tarea and not _tarea.done():
        _tarea.cancel()
        try:
            await _tarea
        except asyncio.CancelledError:
            pass
    _tarea = None
