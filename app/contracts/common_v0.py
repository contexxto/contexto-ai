"""Piezas compartidas por varios contratos de FASE 1.

Existe por una razón concreta: `Money` nació en `buyer_v0.py` (presupuesto) y hace falta
otra vez en `property_v0.py` (precio de la transacción). Importarlo de `buyer_v0`
acoplaría el contrato del inmueble al del comprador, que es la dirección equivocada —
un inmueble existe sin que haya nadie buscándolo.

Aquí solo entra lo que **ya** usan dos contratos. No es un cajón para lo que podría
compartirse algún día.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ContractBase(BaseModel):
    """Config común de los contratos: inmutable y sin campos extra.

    `frozen` porque un contrato que se puede editar después de creado deja de ser una
    afirmación sobre un momento. `extra="forbid"` porque colar un campo no declarado es
    exactamente como `household` volvería a entrar por la puerta de atrás.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class Money(ContractBase):
    """Importe con moneda. La moneda no es opcional: Contexto opera en Quito y mira
    plazas en México, y un número suelto no dice si son 200 000 dólares o pesos."""

    amount: Decimal = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    """ISO 4217 en mayúsculas: `USD`, `MXN`."""


class TravelMode(StrEnum):
    """Cómo se recorre una distancia. Aquí porque lo usan el comprador (sus anclas de
    trayecto) y el lugar (los trayectos y las isócronas)."""

    WALK = "walk"
    TRANSIT = "transit"
    DRIVE = "drive"
    BIKE = "bike"
    UNKNOWN = "unknown"
