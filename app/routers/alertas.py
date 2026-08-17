"""
La ALERTA — la primera puerta suave de identidad de Contexto.

*"¿Te aviso cuando aparezca algo así?"*. Captura un correo SIN transferir a nadie: no
toca el consentimiento del handoff ni la frontera con el corredor. La persona sigue
siendo dueña de su conversación.

CUÁNDO se ofrece lo decide `app/puerta.py` (el motor, no el modelo). Este router solo
persiste lo que la persona aceptó, y de paso guarda **la demanda**: qué pidió y si había
algo que se lo diera. Las filas con `hubo_match = false` son la demanda no cubierta de
Quito, que es el activo real de esta fase (ver migrations/025_contacto_demanda.sql).

Best-effort en la escritura de la demanda, estricto en el correo: si el contacto no se
guarda, la persona tiene que enterarse (le prometimos avisarle); si la demanda falla, la
alerta igual vale y no vamos a perder el correo por eso.
"""

# Sin `from __future__ import annotations` a propósito: convierte las anotaciones en
# cadenas y FastAPI degrada el modelo del cuerpo a parámetro de QUERY (422 en toda
# llamada). Ver la nota equivalente en visitas.py.
import json
import logging
import re
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.limiter import limiter
from app.routers.chat import verify_api_key

log = logging.getLogger("alertas")

router = APIRouter(prefix="/api/v1/alertas", tags=["Alertas — la puerta suave"])

# Validación sobria y sin dependencia nueva: descarta lo que claramente no es un correo,
# sin pretender decidir si existe. Lo definitivo es que el aviso llegue; un correo con
# error tipográfico se descubre entonces, no aquí.
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s.]+(\.[^@\s.]+)+$")

_DDL = [
    "CREATE TABLE IF NOT EXISTS contacto ("
    "id bigserial PRIMARY KEY, email text NOT NULL, session_id text NOT NULL, "
    "device_key text, canal text, origen text NOT NULL DEFAULT 'alerta', "
    "activo_id uuid, creado_en timestamptz NOT NULL DEFAULT now(), "
    "CONSTRAINT contacto_email_sesion_unico UNIQUE (email, session_id))",
    "CREATE TABLE IF NOT EXISTS demanda ("
    "id bigserial PRIMARY KEY, contacto_id bigint REFERENCES contacto(id) ON DELETE CASCADE, "
    "session_id text NOT NULL, criterio jsonb NOT NULL, criterio_texto text, "
    "hubo_match boolean NOT NULL, motivo text, activo_id uuid, "
    "creado_en timestamptz NOT NULL DEFAULT now())",
    # Un reintento NO cuenta dos veces: la demanda no cubierta es un reporte que se
    # enseña, y un doble envío la inflaba (verificado en vivo: 3 POST → 1 contacto y
    # 3 demandas). Un criterio distinto en la misma sesión SÍ crea otra fila.
    "CREATE UNIQUE INDEX IF NOT EXISTS demanda_unica_por_criterio "
    "ON demanda (contacto_id, criterio)",
    "CREATE INDEX IF NOT EXISTS contacto_creado_en_idx ON contacto (creado_en DESC)",
    "CREATE INDEX IF NOT EXISTS contacto_session_idx ON contacto (session_id)",
    "CREATE INDEX IF NOT EXISTS demanda_sin_match_idx ON demanda (creado_en DESC) "
    "WHERE hubo_match = false",
    "CREATE INDEX IF NOT EXISTS demanda_contacto_idx ON demanda (contacto_id)",
]
_listo = False


async def ensure_alertas(db) -> None:
    """Crea las tablas si faltan (idempotente, una vez por proceso). Mismo patrón que
    `ensure_visita` / `ensure_lead_actividad`."""
    global _listo
    if _listo:
        return
    for ddl in _DDL:
        await db.execute(text(ddl))
    await db.commit()
    _listo = True


def _uuid_o_none(v) -> str | None:
    try:
        return str(_uuid.UUID(str(v)))
    except (ValueError, AttributeError, TypeError):
        return None


class AlertaIn(BaseModel):
    session_id: str = Field(min_length=4, max_length=200)
    email: str = Field(min_length=3, max_length=254)
    # El criterio DECLARADO tal cual lo leyó el motor. Se guarda entero para poder
    # agregar después por dimensión sin volver a preguntarle a nadie.
    criterio: dict = Field(default_factory=dict)
    criterio_texto: str | None = Field(default=None, max_length=300)
    # ¿Había algo que le sirviera cuando pidió el aviso? El campo que hace de `demanda`
    # un activo y no un registro más.
    hubo_match: bool = False
    motivo: str | None = Field(default=None, max_length=40)
    activo_id: str | None = None
    device_key: str | None = Field(default=None, max_length=200)


@router.post(
    "",
    summary="Crear una alerta (la puerta suave)",
    description="Guarda el correo con finalidad ACOTADA —avisar cuando aparezca algo que "
                "encaje— y registra la demanda declarada. No transfiere a ningún corredor: "
                "eso sigue siendo el handoff, con su propio consentimiento.",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("10/minute")
async def crear_alerta(request: Request, cuerpo: AlertaIn) -> dict:
    email = (cuerpo.email or "").strip().lower()
    if not _EMAIL.match(email):
        # Este SÍ falla hacia el cliente: le prometimos avisarle. Callarlo sería
        # exactamente la promesa incumplida que esta puerta existe para no hacer.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Ese correo no parece válido. ¿Lo revisas?")

    activo = _uuid_o_none(cuerpo.activo_id)
    try:
        async with AsyncSessionLocal() as db:
            await ensure_alertas(db)
            # El canal se hereda de la PRIMERA visita de la sesión (F0): así se puede
            # responder de qué canal vienen los correos que de verdad se capturan.
            canal = None
            try:
                canal = (await db.execute(
                    text("SELECT canal FROM visita WHERE session_id = :s "
                         "ORDER BY creado_en ASC LIMIT 1"),
                    {"s": cuerpo.session_id})).scalar()
            except Exception:  # noqa: BLE001 — sin F0 desplegado, la alerta igual vale
                await db.rollback()

            # ON CONFLICT: reintentar no duplica ni rompe. Devuelve el id en ambos casos.
            contacto_id = (await db.execute(
                text("INSERT INTO contacto (email, session_id, device_key, canal, origen, activo_id) "
                     "VALUES (:e, :s, :d, :c, 'alerta', CAST(:a AS uuid)) "
                     "ON CONFLICT ON CONSTRAINT contacto_email_sesion_unico "
                     "DO UPDATE SET canal = COALESCE(contacto.canal, EXCLUDED.canal) "
                     "RETURNING id"),
                {"e": email, "s": cuerpo.session_id, "d": cuerpo.device_key,
                 "c": canal, "a": activo})).scalar()

            try:
                await db.execute(
                    text("INSERT INTO demanda (contacto_id, session_id, criterio, "
                         "criterio_texto, hubo_match, motivo, activo_id) "
                         "VALUES (:cid, :s, CAST(:cr AS jsonb), :ct, :hm, :mo, CAST(:a AS uuid)) "
                         "ON CONFLICT (contacto_id, criterio) DO NOTHING"),
                    {"cid": contacto_id, "s": cuerpo.session_id,
                     "cr": json.dumps(cuerpo.criterio or {}, ensure_ascii=False),
                     "ct": cuerpo.criterio_texto, "hm": bool(cuerpo.hubo_match),
                     "mo": cuerpo.motivo, "a": activo})
            except Exception as exc:  # noqa: BLE001 — la demanda es nuestra, el correo es suyo
                log.warning("demanda no registrada (%s): %s", type(exc).__name__, exc)

            await db.commit()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("alerta no registrada (%s): %s", type(exc).__name__, exc)
        # Le prometimos avisarle y no pudimos guardarlo: se lo decimos.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="No pudimos guardar tu aviso ahora mismo. Reintenta en un momento.")
