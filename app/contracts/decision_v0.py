"""DecisionContextV0 — qué se decidió sobre qué, y bajo qué reglas (E1.5).

Contrato puro. No hay resolver, ni store, ni fetch, ni assembler, ni persistencia de
snapshots, ni hashes, ni validación cruzada, ni scoring. Todo eso es F2/F6.

──────────────────────────────────────────────────────────────────────────────────
REFERENCIA, NO CONTENIDO
──────────────────────────────────────────────────────────────────────────────────

Este objeto **apunta** a los tres contextos; no los lleva dentro. La diferencia no es
de tamaño, es de responsabilidad: un `DecisionContextV0` que arrastrara copias completas
de comprador, inmueble y lugar sería un snapshot, y la reproducibilidad profunda es
trabajo de `DecisionTraceV0` (E1.6). Aquí basta con poder decir, sin ambigüedad, sobre
qué se decidió.

Las referencias son pequeñas y neutrales respecto al proveedor, y usan la identidad más
precisa que cada contrato ya tiene — nada de referencias débiles:

    BuyerContextRefV0     buyer_id + context_revision
    PropertyContextRefV0  provider_id + property_id   ← el par de identidad de E1.3
    PlaceContextRefV0     place_id

`context_revision` va en la referencia del comprador a propósito: un comprador cambia de
opinión, y una decisión tomada sobre la revisión 2 no se explica con la revisión 5.
Apuntar solo a `buyer_id` haría que la decisión pareciera coherente con un estado que
no existía cuando se tomó.

──────────────────────────────────────────────────────────────────────────────────
LO QUE ESTE CONTRATO **NO** VALIDA, Y ES DELIBERADO
──────────────────────────────────────────────────────────────────────────────────

No comprueba que los `anchor_ids` existan en el `BuyerContextV0` referenciado. **No
puede**: no tiene el contexto delante, solo una referencia a él. Ese invariante —

    todo anchor_id usado por Place/Decision existe en BuyerContextV0.commute_anchors

— pertenece al assembler de F2, que es donde los tres contextos están disponibles a la
vez. Fingir aquí una validación que no se puede hacer sería peor que no tenerla: daría
una garantía falsa.

Lo que sí se hace cumplir es que las referencias a anclas sean **por `anchor_id` y solo
por `anchor_id`**. Nunca por `anchor_label`, que es presentación y puede cambiar sin que
cambie el ancla.

──────────────────────────────────────────────────────────────────────────────────
POR QUÉ NO HAY UN `evidence[]` AQUÍ
──────────────────────────────────────────────────────────────────────────────────

La evidencia vive en los contextos referenciados: cada medida del lugar lleva la suya,
cada criterio del comprador la suya, y el registro del inmueble la suya. Copiarla aquí
la duplicaría y convertiría este objeto en el snapshot que se decidió que no fuera.

`score_version` sí está, porque no vive en ningún otro sitio: es la regla bajo la que se
decidió. Es el mismo campo que E0.4 introdujo en `calcular_encaje()` como `"encaje-v0"`,
y existe por la misma razón — dos números producidos por reglas distintas no son
comparables, y sin registrar la regla nadie puede saberlo después.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.contracts.buyer_v0 import CONTRACT_VERSION as BUYER_V0
from app.contracts.common_v0 import ContractBase as _Base
from app.contracts.place_v0 import CONTRACT_VERSION as PLACE_V0
from app.contracts.property_v0 import CONTRACT_VERSION as PROPERTY_V0

CONTRACT_VERSION = "decision-context-v0"


class BuyerContextRefV0(_Base):
    """A qué comprador, y en qué revisión de su estado."""

    buyer_id: str = Field(min_length=1)

    context_revision: int | None = Field(default=None, ge=0)
    """La revisión del ESTADO del comprador (no la del contrato — ver E1.2). `None` = el
    contexto referenciado no estaba versionado.

    Que pueda ser `None` es una concesión al presente, no un diseño: mientras F3 no
    construya el store con historial, no hay revisiones que citar. Lo que no se hace es
    inventar un número para taparlo."""

    contract_version: Literal["buyer-context-v0"] = BUYER_V0


class PropertyContextRefV0(_Base):
    """A qué inmueble. Usa el par de identidad externa de E1.3, que es lo más preciso
    que hay: `property_id` solo es único dentro de su proveedor."""

    provider_id: str = Field(min_length=1)
    property_id: str = Field(min_length=1)
    contract_version: Literal["property-context-v0"] = PROPERTY_V0

    @property
    def identidad_externa(self) -> tuple[str, str]:
        return (self.provider_id, self.property_id)


class PlaceContextRefV0(_Base):
    """A qué lugar.

    `place_id` es OBLIGATORIO aquí aunque en `PlaceContextV0` sea opcional, y la
    diferencia es intencionada: un contexto de lugar sin identificador es un cálculo de
    paso, perfectamente válido para mirar un punto. Para PARTICIPAR EN UNA DECISIÓN hay
    que poder volver a nombrarlo — una decisión que no se puede rastrear hasta su lugar
    no se puede explicar.
    """

    place_id: str = Field(min_length=1)
    contract_version: Literal["place-context-v0"] = PLACE_V0


class DecisionContextV0(_Base):
    """Los insumos de una decisión, por referencia."""

    contract_version: Literal["decision-context-v0"] = CONTRACT_VERSION

    decision_id: str = Field(min_length=1)
    created_at: datetime

    buyer: BuyerContextRefV0
    property: PropertyContextRefV0
    place: PlaceContextRefV0

    score_version: str = Field(min_length=1)
    """Bajo qué reglas se decidió. Ver la cabecera: dos números producidos por reglas
    distintas no son comparables."""

    anchor_ids: tuple[str, ...] = ()
    """Las anclas de trayecto que participaron, **por id**. Vacío es válido: hay
    decisiones que no miran trayectos.

    Nunca por `anchor_label`. Que este campo sea de ids y no de etiquetas es lo que
    impide que una decisión quede correlacionada con un texto que alguien puede
    reescribir."""

    @field_validator("created_at")
    @classmethod
    def _exigir_zona_horaria(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("created_at debe traer zona horaria")
        return v

    @field_validator("anchor_ids")
    @classmethod
    def _ids_con_contenido(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if any(not i.strip() for i in v):
            raise ValueError("un anchor_id vacío no referencia nada")
        return v

    @model_validator(mode="after")
    def _sin_anclas_repetidas(self) -> DecisionContextV0:
        repetidos = {i for i in self.anchor_ids if self.anchor_ids.count(i) > 1}
        if repetidos:
            raise ValueError(f"anchor_id repetido: {sorted(repetidos)}")
        return self


def json_schema() -> dict[str, Any]:
    """JSON Schema del contrato. Función y no constante, para que no se congele en el
    import y quede desincronizado del modelo."""
    return DecisionContextV0.model_json_schema()
