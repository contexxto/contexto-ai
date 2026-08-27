"""E3.2b.0 · Buyer State Boundary — qué estado durable puede crear el updater.

**Pura, determinista y offline.** No habla con un modelo, ni con la base, ni con el store.
No conoce el `buyer_id`, ni el transcript, ni la hora. Recibe una mutación ya estructurada y
dice si está autorizada; nada más.

## La distinción que justifica este módulo

`BuyerContextV0` define lo que puede **representarse**. Esta frontera define lo que este
updater puede **crear**. No son lo mismo, y confundirlas es el fallo que el módulo existe
para impedir: que un path exista en el contrato no autoriza a escribir en él cualquier valor
que Pydantic acepte.

## Por qué variantes concretas y no `(path, operation, value)`

Una firma genérica —`path: str`, `operation: str`, `value: Any`— deja que el candidato
**exprese** `household.children` y confía en que un saneador posterior lo descarte. Eso
convierte la barrera en un filtro, y un filtro se puede olvidar de un caso.

Aquí cada clase congela a la vez **path, operación, tipo y dominio**. `household.children`
no es que se rechace: es que no hay dónde escribirlo.

## La regla estructural, y cómo se comprueba

> Una mutación cerrada no debe aceptar parámetros que puedan representar estados inválidos
> para esa operación.

La prueba de revisión: si después de construir una mutación todavía hay que preguntar *"¿este
valor era válido para esta operación?"*, la discriminación quedó incompleta.

Por eso `SetPetsRequired()` **no lleva campo**. Con `value: bool` podría construirse con
`False`, que no significa "no necesito mascotas permitidas" sino un requisito distinto que
esta versión no modela — y haría falta validarlo después. La operación **es** la afirmación.
Dejar de necesitarlo es `ClearPetsRequired()`.

## Tipos: se sigue al contrato que se va a alimentar

`SetBudgetMax.amount` es `Decimal` porque `Money.amount` lo es. `SetAreaM2Min.area_m2_min`
es `float` porque `PropertyRequirements.area_m2_min` lo es. Que difieran no es incoherencia:
cada uno sigue a su destino. Unificarlos por simetría introduciría una conversión que nadie
pidió y un segundo sitio donde el valor puede cambiar de forma.

## Lo que NO hace, y pertenece a E3.2b.1+

Interpretar lenguaje natural. `"comprar"` → `BUY`, `"900 dólares"` → `Money`, `"sí"` → `True`
son trabajo del extractor. Esta frontera recibe estructura y valida forma y dominio.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, model_validator

from app.contracts.buyer_v0 import Objective

_CERRADO = ConfigDict(frozen=True, extra="forbid")


class BuyerCurrencyV0(StrEnum):
    """Las monedas que el updater V0 acepta. **No** las que el contrato permite.

    `Money.currency` valida `^[A-Z]{3}$`: eso restringe la FORMA y no el dominio, así que
    `ZZZ` y `EUR` pasan igual que `USD`. Para un contrato general está bien —no le toca
    decidir en qué plazas opera el producto—; para el updater no, porque persistiría una
    moneda que nadie puede convertir ni comparar.

    Dos valores porque son las dos plazas del producto. Ampliar esto es una decisión de
    producto, no un detalle de implementación: añadir una moneda sin saber quién la consume
    repite el error que dejó fuera a `accessibility_requirements`.
    """

    USD = "USD"
    MXN = "MXN"


# ── Las mutaciones ─────────────────────────────────────────────────────────────────
#
# Cada clase congela PATH + OPERACIÓN + TIPO + DOMINIO. Los `Clear*` no llevan payload:
# no hay nada que puedan expresar mal.


class _Mutacion(BaseModel):
    model_config = _CERRADO


class SetObjective(_Mutacion):
    """`UNKNOWN` no es un valor que se declare: es la ausencia de declaración. Admitirlo
    como `SET` permitiría "afirmar que no se sabe", que no es lo mismo que no saber —y que
    ya se expresa con `ClearObjective`."""

    tipo: Literal["set_objective"] = "set_objective"
    objective: Literal[Objective.BUY, Objective.RENT, Objective.INVEST]


class ClearObjective(_Mutacion):
    tipo: Literal["clear_objective"] = "clear_objective"


class SetBudgetMax(_Mutacion):
    """`Decimal` porque `Money.amount` lo es. La moneda es obligatoria y de dominio cerrado:
    sin ella no hay `Money` posible, y el §12 prohíbe inferirla del contexto."""

    tipo: Literal["set_budget_max"] = "set_budget_max"
    # `strict=True` porque sin él Pydantic acepta `"900"` y lo convierte. Eso es
    # INTERPRETAR una cadena, y D-B5 se lo reserva al extractor: la frontera recibe
    # estructura ya tipada. Un `amount` que llega como texto es un candidato mal formado,
    # no un presupuesto.
    amount: Annotated[Decimal, Field(gt=0, strict=True)]
    currency: BuyerCurrencyV0


class ClearBudgetMax(_Mutacion):
    tipo: Literal["clear_budget_max"] = "clear_budget_max"


class SetBedroomsMin(_Mutacion):
    """`StrictInt` para que `True` no entre como `1`: `bool` es subclase de `int` en Python
    y sin estricto un candidato mal formado se colaría como un dormitorio.

    **`ge=1` y no `ge=0`:** "cero dormitorios como mínimo" no restringe nada, así que no es
    un requisito — es ruido que ocuparía sitio de estado real.
    """

    tipo: Literal["set_bedrooms_min"] = "set_bedrooms_min"
    bedrooms_min: Annotated[StrictInt, Field(ge=1)]


class ClearBedroomsMin(_Mutacion):
    tipo: Literal["clear_bedrooms_min"] = "clear_bedrooms_min"


class SetAreaM2Min(_Mutacion):
    """`float` porque `PropertyRequirements.area_m2_min` lo es — no `Decimal`.

    `allow_inf_nan=False` deja la garantía en la definición del campo y visible en el schema,
    en vez de en un validador aparte que alguien pueda retirar sin notarlo: `NaN` y `±inf`
    quedan fuera por tipo.

    `StrictFloat` **admite `int`** como entrada compatible con `float` —`50` entra como
    `50.0`, sin pérdida— pero **excluye `bool`**, que en Python es subclase de `int`. Es
    justo la línea que interesa: un entero es un área legítima; un booleano es un candidato
    mal formado. Verificado en `test_un_area_entera_SI_se_acepta_y_bool_no`.
    """

    tipo: Literal["set_area_m2_min"] = "set_area_m2_min"
    area_m2_min: Annotated[StrictFloat, Field(gt=0, allow_inf_nan=False)]


class ClearAreaM2Min(_Mutacion):
    tipo: Literal["clear_area_m2_min"] = "clear_area_m2_min"


class SetPetsRequired(_Mutacion):
    """SIN CAMPO, y es la decisión más importante del módulo.

    Con `value: bool` esta clase podría construirse con `False`, que no significa "ya no lo
    necesito" —eso es `ClearPetsRequired`— sino un requisito distinto que V0 no modela. Y
    haría falta validarlo *después* de construirla, que es exactamente la señal de que la
    discriminación quedó incompleta. La operación **es** la afirmación.
    """

    tipo: Literal["set_pets_required"] = "set_pets_required"


class ClearPetsRequired(_Mutacion):
    tipo: Literal["clear_pets_required"] = "clear_pets_required"


BuyerMutationV0 = Annotated[
    Union[
        SetObjective, ClearObjective,
        SetBudgetMax, ClearBudgetMax,
        SetBedroomsMin, ClearBedroomsMin,
        SetAreaM2Min, ClearAreaM2Min,
        SetPetsRequired, ClearPetsRequired,
    ],
    Field(discriminator="tipo"),
]
"""La unión CERRADA. Lo que no esté aquí no es que se rechace — es que no se puede expresar."""


# ── El destino de cada mutación ────────────────────────────────────────────────────

_RUTA_CONTRACTUAL: dict[type[_Mutacion], str] = {
    SetObjective: "objective",
    ClearObjective: "objective",
    SetBudgetMax: "financial.budget_max",
    ClearBudgetMax: "financial.budget_max",
    SetBedroomsMin: "property_requirements.bedrooms_min",
    ClearBedroomsMin: "property_requirements.bedrooms_min",
    SetAreaM2Min: "property_requirements.area_m2_min",
    ClearAreaM2Min: "property_requirements.area_m2_min",
    SetPetsRequired: "property_requirements.pets_allowed_required",
    ClearPetsRequired: "property_requirements.pets_allowed_required",
}


def ruta_contractual(mutacion) -> str:
    """El path de `BuyerContextV0` que alimenta esta mutación.

    **Se DERIVA de la clase; nunca llega como dato.** `FieldEvidence.field` es un `str` libre
    en el contrato, así que aceptarlo del candidato reabriría por la puerta de atrás la
    superficie que la unión cierra: bastaría con pedir procedencia de `household.children`.

    Lo consumirá el provenance de E3.2b.2. Aquí no se crea ningún `EvidenceRefV0`.
    """
    try:
        return _RUTA_CONTRACTUAL[type(mutacion)]
    except KeyError:                                     # pragma: no cover — unión cerrada
        raise TypeError(f"mutación fuera de la unión V0: {type(mutacion).__name__}") from None


# ── El resultado ───────────────────────────────────────────────────────────────────


class Disposicion(StrEnum):
    """Qué se decidió sobre el intento. **Tres de los cuatro no son errores.**

    `TURN_ONLY` y `AMBIGUOUS` son decisiones de no persistencia: preguntar por lo caminable
    que es un barrio no declara una preferencia, y mencionar el ruido sin dirección no basta
    para inventarla. Tratarlos como fallos empujaría a "arreglarlos" persistiendo.
    """

    DURABLE = "durable"
    TURN_ONLY = "turn_only"
    AMBIGUOUS = "ambiguous"
    REJECTED = "rejected"


class ResultadoFrontera(BaseModel):
    """Lo que la frontera autoriza. **Solo `DURABLE` puede llevar mutación.**

    El emparejamiento se garantiza al construir, no por convención: un resultado inválido no
    se puede crear. Si dependiera de que el llamante lo respete, la garantía viviría en la
    disciplina de quien escriba E3.2b.1 en vez de en el tipo.
    """

    model_config = _CERRADO

    disposicion: Disposicion
    mutacion: BuyerMutationV0 | None = None
    motivo: str | None = None

    @model_validator(mode="after")
    def _solo_durable_muta(self) -> ResultadoFrontera:
        if self.disposicion is Disposicion.DURABLE and self.mutacion is None:
            raise ValueError("DURABLE exige una mutación: autorizar sin qué no significa nada")
        if self.disposicion is not Disposicion.DURABLE and self.mutacion is not None:
            raise ValueError(
                f"{self.disposicion} no puede llevar mutación — NO MATCH nunca persiste")
        return self

    @property
    def persiste(self) -> bool:
        return self.disposicion is Disposicion.DURABLE


def autorizar(mutacion) -> ResultadoFrontera:
    """La puerta. Recibe una mutación de la unión y devuelve el resultado autorizado.

    No interpreta: para cuando algo llega aquí, la forma y el dominio ya los garantizó el
    tipo. Esta función existe para que E3.2b.1 tenga **un solo sitio** al que llamar, y para
    que rechazar lo que no pertenece a la unión sea explícito y no un `TypeError` por
    accidente aguas abajo.
    """
    if not isinstance(mutacion, _Mutacion) or type(mutacion) not in _RUTA_CONTRACTUAL:
        return ResultadoFrontera(
            disposicion=Disposicion.REJECTED,
            motivo="no pertenece a la unión de mutaciones autorizadas de V0",
        )
    return ResultadoFrontera(disposicion=Disposicion.DURABLE, mutacion=mutacion)


def no_persistir(disposicion: Disposicion, motivo: str) -> ResultadoFrontera:
    """Atajo para los tres desenlaces sin escritura. Existe para que el llamante no tenga
    que acordarse de dejar `mutacion` en `None`."""
    if disposicion is Disposicion.DURABLE:
        raise ValueError("no_persistir no puede producir DURABLE")
    return ResultadoFrontera(disposicion=disposicion, motivo=motivo)
