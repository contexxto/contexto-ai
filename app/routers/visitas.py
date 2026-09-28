"""
Registro de LLEGADAS — el primer escalón del embudo, que hasta hoy no existía.

Una fila por llegada (log append-only, ver migrations/024_visita.sql). El escaneo de un
QR se cuenta AUNQUE la persona no escriba nada: es la señal más fuerte del sistema
—estaba parada frente al inmueble— y se estaba tirando.

Best-effort de punta a punta: registrar una visita JAMÁS puede romper la página que la
persona vino a ver. Cualquier fallo se traga y se devuelve `ok:false`; el frontend no
reacciona a eso. Es el mismo criterio que `marcar_actividad_lead`.

La clasificación del canal es determinista y vive en `app/llegada.py` (puro, testeable).
Aquí solo se persiste.
"""

# OJO: este módulo NO lleva `from __future__ import annotations`, y es a propósito.
# Con él, las anotaciones se vuelven cadenas y FastAPI recibe un ForwardRef en vez del
# modelo: degrada `cuerpo: LlegadaIn` a parámetro de QUERY y el endpoint responde 422 a
# todas las llamadas. Lo destapó la primera prueba real contra el backend; ningún test
# unitario lo veía porque ninguno llamaba al endpoint. Ningún router del repo lo usa.
import logging
import uuid as _uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.auth import CurrentUser, get_optional_user
from app.database import AsyncSessionLocal
from app.limiter import limiter
from app.llegada import normalizar_llegada
from app.routers.chat import _exigir_autoridad, verify_api_key

log = logging.getLogger("visitas")

router = APIRouter(prefix="/api/v1/visitas", tags=["Llegadas — parte alta del embudo"])

_DDL = [
    "CREATE TABLE IF NOT EXISTS visita ("
    "id bigserial PRIMARY KEY, session_id text NOT NULL, activo_id uuid, "
    "superficie text NOT NULL, canal text NOT NULL, "
    "utm_source text, utm_medium text, utm_campaign text, utm_content text, "
    "referrer text, device_key text, "
    "creado_en timestamptz NOT NULL DEFAULT now())",
    "CREATE INDEX IF NOT EXISTS visita_creado_en_idx ON visita (creado_en DESC)",
    "CREATE INDEX IF NOT EXISTS visita_activo_idx ON visita (activo_id, creado_en DESC) "
    "WHERE activo_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS visita_session_idx ON visita (session_id)",
]
_listo = False


async def ensure_visita(db) -> None:
    """Crea la tabla si falta (idempotente, una vez por proceso). Mismo patrón que
    `ensure_lead_actividad`: el despliegue no depende de correr la migración a mano."""
    global _listo
    if _listo:
        return
    for ddl in _DDL:
        await db.execute(text(ddl))
    await db.commit()
    _listo = True


class LlegadaIn(BaseModel):
    session_id: str = Field(min_length=4, max_length=200)
    activo_id: str | None = None
    superficie: str | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None
    referrer: str | None = None
    device_key: str | None = Field(default=None, max_length=200)


def _uuid_o_none(v) -> str | None:
    """Un uuid válido, o None. El `activo_id` llega del cliente: un valor basura no
    puede llegar a la consulta ni tumbar el registro."""
    try:
        return str(_uuid.UUID(str(v)))
    except (ValueError, AttributeError, TypeError):
        return None


async def registrar_visita(datos: dict, *, host_propio: str | None = None) -> bool:
    """Persiste UNA llegada ya normalizada. True si se guardó. Nunca lanza."""
    sid = (datos or {}).get("session_id")
    if not isinstance(sid, str) or not sid.strip():
        return False
    fila = normalizar_llegada(datos, host_propio=host_propio)
    try:
        async with AsyncSessionLocal() as db:
            await ensure_visita(db)
            await db.execute(
                text("INSERT INTO visita (session_id, activo_id, superficie, canal, "
                     "utm_source, utm_medium, utm_campaign, utm_content, referrer, device_key) "
                     "VALUES (:s, CAST(:a AS uuid), :sup, :can, :us, :um, :uc, :uo, :ref, :dev)"),
                {"s": sid.strip()[:200], "a": _uuid_o_none(datos.get("activo_id")),
                 "sup": fila["superficie"], "can": fila["canal"],
                 "us": fila["utm_source"], "um": fila["utm_medium"],
                 "uc": fila["utm_campaign"], "uo": fila["utm_content"],
                 "ref": fila["referrer"],
                 "dev": (datos.get("device_key") or None)},
            )
            await db.commit()
        return True
    except Exception as exc:  # noqa: BLE001 — una visita perdida no vale una página rota
        log.warning("visita no registrada (%s): %s", type(exc).__name__, exc)
        return False


@router.post(
    "",
    summary="Registrar una llegada de una conversación propia",
    description="Una fila por llegada. Se llama al cargar la página, ANTES de que la "
                "persona escriba nada — así el escaneo de un QR se cuenta aunque la "
                "conversación nunca empiece. Exige autoridad sobre la conversación que "
                "se dice estar visitando: 404 si no se puede demostrar.",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("60/minute")
async def crear_visita(
    request: Request,
    cuerpo: LlegadaIn,
    user: CurrentUser | None = Depends(get_optional_user),
) -> dict:
    """Registra la llegada — sólo para quien pueda demostrar autoridad sobre el hilo.

    EL AGUJERO QUE CIERRA. La única puerta era `verify_api_key`, y esa llave la PUBLICA el
    frontend (`VITE_API_KEY`), así que el `session_id`, el `activo_id` y el `device_key` los
    AFIRMABA el cliente sin nada que lo respaldara: cualquiera que abriese el bundle podía
    anclar un `device_key` —dato personal, con obligación de supresión declarada en
    `migrations/024_visita.sql:29-31`— al `session_id` de un tercero, y falsear la única
    medición que existe de los dos motores de adquisición declarados.

    POR QUÉ ESTO NO ROMPE AL VISITANTE ANÓNIMO, que es lo que parecía el problema: cuando el
    cliente llama aquí ya tiene una sesión y su capacidad viaja en la cabecera —el efecto sale
    con `if (!sessionId) return` y usa `apiHeadersSesion(sessionId)`—, y todo camino que produce
    un `session_id` nuevo pasa antes por el bootstrap, que emite y guarda esa capacidad. La
    llegada por QR ni siquiera llega aquí hasta que la persona pulsa el CTA, que hace bootstrap.

    LO QUE SÍ SE PIERDE, dicho aquí para que nadie lo descubra leyendo una gráfica: la llegada
    de la superficie `home` de un usuario CON CUENTA que vuelve. En ese instante el efecto corre
    con el `session_id` heredado de `localStorage`, el Bearer todavía no está puesto y la
    capacidad ya se borró al reclamar el hilo, así que no hay nada que demostrar y la llegada no
    se cuenta. Desde este cambio (27-sep-2026) esta tabla mide **llegadas con autoridad
    demostrable**, no «llegadas»: NO se pueden comparar series a través de esa fecha. Conservar
    también esa llegada exige alinear el frontend y es una unidad aparte, deliberadamente no
    mezclada con un arreglo de autoridad.
    """
    await _exigir_autoridad(request, cuerpo.session_id, user)
    ok = await registrar_visita(cuerpo.model_dump(), host_propio=request.url.hostname)
    return {"ok": ok}
