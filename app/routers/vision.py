"""
Router de visión (Fase B2) — endpoint de prueba.

POST /api/v1/vision/extract
Corre SOLO la extracción visual y devuelve la ficha observable.
No crea activos ni embeddings (eso es B3). Sirve para validar con fotos
reales de Quito apenas se despliega, sin necesidad de Voyage.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, HttpUrl

from app.limiter import limiter
from app.routers.chat import verify_api_key
from app.vision import (
    ExtractionInvalidError,
    FichaVision,
    ImageFetchError,
    extract_ficha_from_image,
)

router = APIRouter(prefix="/api/v1/vision", tags=["Vision — Extracción visual"])


class VisionRequest(BaseModel):
    image_url: HttpUrl


class VisionResponse(BaseModel):
    ficha: FichaVision
    requiere_revision: bool
    umbral_confianza: float = 0.6


@router.post(
    "/extract",
    response_model=VisionResponse,
    summary="Extraer ficha observable de una foto (prueba)",
    description=(
        "Analiza una foto de inmueble y devuelve la ficha técnica observable. "
        "Marca requiere_revision=true si la confianza < 0.6. No persiste nada."
    ),
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("20/minute")
async def extract(request: Request, payload: VisionRequest) -> VisionResponse:
    try:
        ficha = await extract_ficha_from_image(str(payload.image_url))
    except ImageFetchError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ExtractionInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return VisionResponse(
        ficha=ficha,
        requiere_revision=ficha.confianza_global < 0.6,
    )
