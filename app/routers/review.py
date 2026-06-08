"""
Router de Revisión Asistida (Human-in-the-loop).

Infraestructura para la "Estación de Revisión" del administrador:
  GET   /api/v1/assets/review-queue            → cola de pendientes (confianza asc)
  PATCH /api/v1/assets/review-queue/{id}       → corrige la extracción IA (registra bitácora)
  POST  /api/v1/assets/review-queue/{id}/approve → publica
  POST  /api/v1/assets/review-queue/{id}/reject  → descarta (no es inmueble / inservible)

Cada corrección humana se registra en `correcciones_ficha` (par valor_ia/valor_humano):
es la "fábrica de ground-truth" que mide la precisión real del modelo y alimenta
un eventual fine-tuning.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.limiter import limiter
from app.models import ActivoInmutable, CorreccionFicha, FichaTecnicaMantenimiento
from app.routers.chat import verify_api_key
from app.vision import FichaVision

router = APIRouter(prefix="/api/v1/assets", tags=["Revisión asistida"])

_VALID_TIPOS = {"Departamento", "Casa", "Local Comercial", "Oficina", "Quinta"}
_CAMPOS_FICHA = set(FichaVision.model_fields)  # campos válidos para corregir


# ─────────────────────────── Schemas ───────────────────────────
class ReviewItem(BaseModel):
    activo_id: uuid.UUID
    direccion: str
    tipo_activo: str
    imagen_url: str | None
    confianza_extraccion: float | None
    estado_revision: str
    ficha_vision_raw: dict | None


class ReviewQueueResponse(BaseModel):
    pendientes: int
    items: list[ReviewItem]


class CorreccionRequest(BaseModel):
    correcciones: dict[str, object] = Field(
        ..., description="Mapa campo→valor_corregido. Las claves deben ser campos de la ficha de visión."
    )
    revisor: str | None = Field(default=None, description="Identificador del revisor (opcional).")

    model_config = {"json_schema_extra": {"example": {
        "correcciones": {
            "tipo_estructura_aparente": "Hormigon Armado",
            "presencia_medidores": "Varios",
            "es_inmueble_exterior": True,
        },
        "revisor": "carlos",
    }}}


class CorreccionResponse(BaseModel):
    activo_id: uuid.UUID
    campos_corregidos: list[str]
    ficha_vision_raw: dict
    estado_revision: str


class EstadoResponse(BaseModel):
    activo_id: uuid.UUID
    estado_revision: str


# ─────────────────────────── Helpers ───────────────────────────
async def _load_ficha(db: AsyncSession, activo_id: uuid.UUID) -> FichaTecnicaMantenimiento:
    ficha = (
        await db.execute(
            select(FichaTecnicaMantenimiento).where(
                FichaTecnicaMantenimiento.activo_id == activo_id
            )
        )
    ).scalar_one_or_none()
    if ficha is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ficha para el activo {activo_id}.",
        )
    return ficha


# ─────────────────────────── Endpoints ───────────────────────────
@router.get(
    "/review-queue",
    response_model=ReviewQueueResponse,
    summary="Cola de activos pendientes de revisión (confianza ascendente)",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("60/minute")
async def review_queue(
    request: Request, limit: int = 50, db: AsyncSession = Depends(get_db)
) -> ReviewQueueResponse:
    limit = max(1, min(limit, 200))
    rows = (
        await db.execute(
            select(ActivoInmutable, FichaTecnicaMantenimiento)
            .join(FichaTecnicaMantenimiento, FichaTecnicaMantenimiento.activo_id == ActivoInmutable.id)
            .where(FichaTecnicaMantenimiento.estado_revision == "pendiente_revision")
            .order_by(FichaTecnicaMantenimiento.confianza_extraccion.asc().nulls_first())
            .limit(limit)
        )
    ).all()

    items = [
        ReviewItem(
            activo_id=a.id,
            direccion=a.direccion_estandarizada,
            tipo_activo=a.tipo_activo,
            imagen_url=a.imagen_url,
            confianza_extraccion=float(f.confianza_extraccion) if f.confianza_extraccion is not None else None,
            estado_revision=f.estado_revision,
            ficha_vision_raw=f.ficha_vision_raw,
        )
        for a, f in rows
    ]
    return ReviewQueueResponse(pendientes=len(items), items=items)


@router.patch(
    "/review-queue/{activo_id}",
    response_model=CorreccionResponse,
    summary="Corregir la extracción de la IA (registra bitácora de ground-truth)",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("60/minute")
async def corregir(
    request: Request,
    activo_id: uuid.UUID,
    payload: CorreccionRequest,
    db: AsyncSession = Depends(get_db),
) -> CorreccionResponse:
    # Validar nombres de campo
    invalidos = set(payload.correcciones) - _CAMPOS_FICHA
    if invalidos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Campos no válidos: {sorted(invalidos)}. Válidos: {sorted(_CAMPOS_FICHA)}",
        )

    activo = (
        await db.execute(select(ActivoInmutable).where(ActivoInmutable.id == activo_id))
    ).scalar_one_or_none()
    if activo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Activo {activo_id} no existe.")
    ficha = await _load_ficha(db, activo_id)

    raw = dict(ficha.ficha_vision_raw or {})
    corregidos: list[str] = []

    for campo, nuevo in payload.correcciones.items():
        viejo = raw.get(campo)
        if str(viejo) == str(nuevo):
            continue  # sin cambio real → no se registra
        db.add(CorreccionFicha(
            activo_id=activo_id,
            campo=campo,
            valor_ia=None if viejo is None else str(viejo),
            valor_humano=None if nuevo is None else str(nuevo),
            revisor=payload.revisor,
        ))
        raw[campo] = nuevo
        corregidos.append(campo)

        # Reflejar en columnas estructuradas (las que el catastro consulta)
        if campo == "tipo_activo" and nuevo in _VALID_TIPOS:
            activo.tipo_activo = nuevo  # type: ignore[assignment]
        elif campo == "tipo_estructura_aparente":
            ficha.tipo_estructura = None if nuevo in (None, "Indeterminado") else str(nuevo)
        elif campo == "calidad_acabados_aparente":
            ficha.calidad_acabados = None if nuevo in (None, "Indeterminado") else str(nuevo)
        elif campo == "cobertura_vegetal_visible_pct" and isinstance(nuevo, (int, float)):
            activo.porcentaje_cobertura_vegetal = float(nuevo)

    # Reasignar un dict NUEVO para que SQLAlchemy detecte el cambio del JSONB.
    ficha.ficha_vision_raw = raw

    return CorreccionResponse(
        activo_id=activo_id,
        campos_corregidos=corregidos,
        ficha_vision_raw=raw,
        estado_revision=ficha.estado_revision,
    )


@router.post(
    "/review-queue/{activo_id}/approve",
    response_model=EstadoResponse,
    summary="Aprobar y publicar el activo",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("60/minute")
async def aprobar(
    request: Request, activo_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> EstadoResponse:
    ficha = await _load_ficha(db, activo_id)
    ficha.estado_revision = "publicado"
    return EstadoResponse(activo_id=activo_id, estado_revision="publicado")


@router.post(
    "/review-queue/{activo_id}/reject",
    response_model=EstadoResponse,
    summary="Rechazar el activo (no es inmueble / inservible)",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("60/minute")
async def rechazar(
    request: Request, activo_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> EstadoResponse:
    ficha = await _load_ficha(db, activo_id)
    ficha.estado_revision = "rechazado"
    return EstadoResponse(activo_id=activo_id, estado_revision="rechazado")
