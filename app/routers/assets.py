import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from geoalchemy2.elements import WKTElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ActivoInmutable
from app.schemas import ActivoCreateRequest, ActivoResponse

router = APIRouter(prefix="/api/v1/assets", tags=["Assets — Catastro Inmutable"])


@router.post(
    "/",
    response_model=ActivoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar nuevo activo inmutable",
    description="Inscribe una coordenada física permanente en el Catastro Vivo.",
)
async def create_asset(
    payload: ActivoCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> ActivoResponse:
    point_wkt = WKTElement(
        f"POINT({payload.longitude} {payload.latitude})",
        srid=4326,
    )

    asset = ActivoInmutable(
        id=uuid.uuid4(),
        geom=point_wkt,
        direccion_estandarizada=payload.direccion_estandarizada,
        piso_altura=payload.piso_altura,
        walk_score=payload.walk_score,
        score_ruido_predictivo=payload.score_ruido_predictivo,
        porcentaje_cobertura_vegetal=payload.porcentaje_cobertura_vegetal,
        tipo_activo=payload.tipo_activo,
    )

    db.add(asset)
    await db.flush()
    await db.refresh(asset)

    return ActivoResponse(
        id=asset.id,
        direccion_estandarizada=asset.direccion_estandarizada,
        piso_altura=asset.piso_altura,
        walk_score=asset.walk_score,
        score_ruido_predictivo=asset.score_ruido_predictivo,
        porcentaje_cobertura_vegetal=float(asset.porcentaje_cobertura_vegetal) if asset.porcentaje_cobertura_vegetal else None,
        tipo_activo=asset.tipo_activo,
        created_at=asset.created_at,
    )
