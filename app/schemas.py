import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ActivoCreateRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90, description="Latitud WGS84")
    longitude: float = Field(..., ge=-180, le=180, description="Longitud WGS84")
    direccion_estandarizada: str = Field(..., min_length=5, max_length=255)
    piso_altura: int = Field(default=1, ge=1, le=200)
    walk_score: int | None = Field(default=None, ge=0, le=100)
    score_ruido_predictivo: str | None = Field(default=None)
    porcentaje_cobertura_vegetal: float | None = Field(default=None, ge=0, le=100)

    @field_validator("score_ruido_predictivo")
    @classmethod
    def validate_ruido(cls, v: str | None) -> str | None:
        if v is not None and v not in ("BAJO", "MEDIO", "ALTO"):
            raise ValueError("score_ruido_predictivo debe ser BAJO, MEDIO o ALTO")
        return v

    model_config = {"json_schema_extra": {"example": {
        "latitude": -0.1807,
        "longitude": -78.4678,
        "direccion_estandarizada": "Av. República del Salvador N34-183, La Carolina, Quito",
        "piso_altura": 3,
        "walk_score": 88,
        "score_ruido_predictivo": "MEDIO",
        "porcentaje_cobertura_vegetal": 34.5,
    }}}


class ActivoResponse(BaseModel):
    id: uuid.UUID
    direccion_estandarizada: str
    piso_altura: int
    walk_score: int | None
    score_ruido_predictivo: str | None
    porcentaje_cobertura_vegetal: float | None
    created_at: datetime

    model_config = {"from_attributes": True}
