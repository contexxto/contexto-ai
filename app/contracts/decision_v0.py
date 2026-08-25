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
LA EVIDENCIA SE CITA, NO SE COPIA
──────────────────────────────────────────────────────────────────────────────────

Cada afirmación material de la decisión —una violación, una dimensión de encaje, una
fortaleza, un tradeoff— lleva `evidence_refs`: una lista de `evidence_id`, no de
`EvidenceRefV0` completos. El reparto es:

    DecisionContext            dice QUÉ evidencia sustenta cada afirmación
    Buyer/Property/Place       CONTIENEN la evidencia
    DecisionTrace (E1.6)       registra qué evidencia se usó al ejecutar

Copiar los objetos enteros aquí los duplicaría, y un duplicado se desincroniza: en
cuanto alguien corrija una `EvidenceRefV0` en su contexto, la copia de la decisión
seguiría afirmando lo viejo. Citar por id no tiene ese problema.

Una referencia rota —un `evidence_id` que no existe— **no se detecta aquí**. Resolver
contra un store es F2/F6, igual que la validación de `anchor_id`.

Las afirmaciones materiales EXIGEN al menos una referencia. Una fortaleza sin evidencia
es "este barrio es tranquilo" sin nada detrás, que es el defecto que E0.4 cerró. La
excepción es `uncertainties`: una incertidumbre puede existir precisamente **porque
faltan datos**, así que ahí `evidence_refs` es opcional — y cuando la hay, sirve para
mostrar evidencia parcial o contradictoria.

`score_version` sí está, porque no vive en ningún otro sitio: es la regla bajo la que se
decidió. Es el mismo campo que E0.4 introdujo en `calcular_encaje()` como `"encaje-v0"`,
y existe por la misma razón — dos números producidos por reglas distintas no son
comparables, y sin registrar la regla nadie puede saberlo después.

──────────────────────────────────────────────────────────────────────────────────
AUSENTE NO ES VACÍO
──────────────────────────────────────────────────────────────────────────────────

`eligibility` y `match` son opcionales, y la distinción es la misma que E1.4 congeló
para las dimensiones del lugar:

    eligibility = None              no se evaluó la elegibilidad
    eligibility.violations = ()     se evaluó y no se encontró ninguna violación

Sin esa diferencia, "no lo miramos" y "lo miramos y está limpio" serían el mismo dato, y
el segundo es una afirmación mucho más fuerte que el primero.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.contracts.buyer_v0 import CONTRACT_VERSION as BUYER_V0
from app.contracts.common_v0 import ContractBase as _Base
from app.contracts.common_v0 import Objective, RankingEntryV0
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


def _refs_utilizables(v: tuple[str, ...]) -> tuple[str, ...]:
    """Un `evidence_id` en blanco no cita nada, y uno repetido no cita dos veces."""
    if any(not r.strip() for r in v):
        raise ValueError("un evidence_id vacío no referencia ninguna evidencia")
    repetidos = {r for r in v if v.count(r) > 1}
    if repetidos:
        raise ValueError(f"evidence_id repetido: {sorted(repetidos)}")
    return v


class _AfirmacionMaterial(_Base):
    """Base de las afirmaciones que sostienen una decisión.

    Todas exigen al menos una `evidence_refs`. Ver la cabecera: una afirmación material
    sin evidencia es exactamente el defecto que cerró E0.4.
    """

    evidence_refs: tuple[str, ...] = Field(min_length=1)
    """`evidence_id` de `EvidenceRefV0` que viven en los contextos referenciados."""

    @field_validator("evidence_refs")
    @classmethod
    def _validar_refs(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        return _refs_utilizables(v)


class ViolationV0(_AfirmacionMaterial):
    """Un criterio duro del comprador que esta opción no cumple."""

    criterion_id: str = Field(min_length=1)
    """El `criterion_id` de `DecisionCriterionV0` (E1.2). Referencia por id estable, no
    por el texto de la restricción."""


class MatchDimensionV0(_AfirmacionMaterial):
    """Una dimensión en la que se comparó la opción contra lo que la persona pidió.

    Sin `score` ni `weight`: cuánto pesa cada dimensión es del Decision Harness. Aquí
    solo se registra que la dimensión participó y con qué respaldo.
    """

    dimension: str = Field(min_length=1)


class StrengthV0(_AfirmacionMaterial):
    """Algo que juega a favor de esta opción."""

    dimension: str = Field(min_length=1)
    statement: str | None = Field(default=None, min_length=1)
    """Presentación. La afirmación estructural es `dimension` + su evidencia."""


class DecisionTradeoffV0(_AfirmacionMaterial):
    """Lo que esta opción concreta obliga a ceder, y a cambio de qué.

    Distinto del `Tradeoff` de E1.2: aquel es lo que la persona DIJO que aceptaría;
    este es lo que esta opción realmente exige. Por eso no se reutiliza el tipo — y por
    eso este módulo no importa el contrato del comprador.
    """

    gives_up: str = Field(min_length=1)
    gains: str = Field(min_length=1)
    severity: Severity
    """Vocabulario cerrado del Blueprint 0.1: `low | medium | high`. Obligatorio: un
    tradeoff que el sistema decide mostrar ya implica un juicio sobre cuánto cuesta, y
    dejarlo implícito lo devolvería a la prosa."""


class UncertaintyV0(_Base):
    """Algo que no se pudo resolver al decidir.

    **La única afirmación cuya evidencia es opcional**, y por una razón concreta: una
    incertidumbre suele existir precisamente porque FALTAN datos. Exigirle evidencia
    sería exigirle que demuestre lo que no tiene. Cuando sí hay algo —evidencia parcial
    o contradictoria— se cita, y ahí es donde más aporta.
    """

    statement: str = Field(min_length=1)
    impact: Impact
    """Vocabulario cerrado del Blueprint 0.1: `low | medium | high`. Obligatorio: sin
    esto, "no hay medición de ruido" y "no sabemos si el edificio tiene ascensor" pesarían
    igual, y no pesan igual."""

    evidence_refs: tuple[str, ...] = ()

    @field_validator("evidence_refs")
    @classmethod
    def _validar_refs(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        return _refs_utilizables(v)


class VerificationStatus(StrEnum):
    """Resultado de verificar la explicación. **Vocabulario del Blueprint 0.1.**

    Encaja con lo que `app/verificacion_prosa.py` ya produce: hallazgos con gravedad
    `alta`/`media`. Un hallazgo grave es `FAILED`, uno medio es `WARNING`, ninguno es
    `PASSED`. El mapeo concreto lo hará F2; el contrato solo fija el vocabulario.
    """

    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


class Severity(StrEnum):
    """Cuánto pesa un tradeoff. **Vocabulario del Blueprint 0.1.**"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Impact(StrEnum):
    """Cuánto afecta una incertidumbre a la decisión. **Vocabulario del Blueprint 0.1.**

    Distinto de `Severity` aunque compartan valores: uno califica un intercambio real y
    el otro un hueco de conocimiento. Fundirlos en un solo enum los habría hecho
    intercambiables, y no lo son.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class NextActionType(StrEnum):
    """Qué sugiere hacer el sistema. **Vocabulario del Blueprint 0.1**, cerrado.

    `NONE` significa "se evaluó y no se recomienda ninguna acción" — distinto de que
    `recommended_next_action` sea `None`, que significa que no se evaluó. Es la misma
    distinción entre ausente y vacío que gobierna `eligibility` y `match`.
    """

    INSPECT = "inspect"
    COMPARE = "compare"
    ASK_PROVIDER = "ask_provider"
    SCHEDULE_VISIT = "schedule_visit"
    CONTACT = "contact"
    REJECT = "reject"
    NONE = "none"


class RecommendedNextActionV0(_Base):
    """La acción sugerida. Tipada, no prosa."""

    type: NextActionType


class ExplanationV0(_Base):
    """El estado de la explicación que se le dio a la persona.

    **No guarda la prosa.** La explicación se DERIVA de las afirmaciones materiales de
    este mismo contrato —`strengths`, `tradeoffs`, `uncertainties`— y guardarla aquí la
    duplicaría y la dejaría desincronizarse. Lo que sí importa registrar es si esa prosa
    pasó por verificación, porque `app/verificacion_prosa.py` existe precisamente para
    cazar afirmaciones que el dato no sostiene.
    """

    verification_status: VerificationStatus
    """Vocabulario cerrado del Blueprint 0.1: `passed | warning | failed`.

    **Lo que este objeto NO lleva**, y es una reducción deliberada del V0 operativo:
    `summary` y `generated_by_model`. El Blueprint objetivo los contempla, pero el Plan
    1.0 solo exige `verification_status` para F1, y F2 construye el `DecisionContextV0`
    **antes** de que exista la prosa — guardar aquí un resumen que todavía no se ha
    generado no tendría qué guardar. Se añaden cuando la fase que genera la prosa los
    necesite."""


class EligibilityV0(_Base):
    """Si la opción supera los criterios duros.

    Que este objeto exista significa que la elegibilidad SE EVALUÓ. `violations` vacío
    significa que se evaluó y no se encontró nada — ver "ausente no es vacío" en la
    cabecera.
    """

    violations: tuple[ViolationV0, ...] = ()

    @property
    def sin_violaciones(self) -> bool:
        return not self.violations


class MatchV0(_Base):
    """Las dimensiones en las que se comparó la opción."""

    dimensions: tuple[MatchDimensionV0, ...] = ()


class DecisionContextV0(_Base):
    """Los insumos de una decisión, por referencia."""

    contract_version: Literal["decision-context-v0"] = CONTRACT_VERSION

    decision_id: str = Field(min_length=1)
    created_at: datetime

    buyer: BuyerContextRefV0
    property: PropertyContextRefV0
    place: PlaceContextRefV0

    objective: Objective = Objective.UNKNOWN
    """Para qué se decidió. Mismo eje que declara el comprador; se copia el VALOR, no se
    referencia el contexto, porque la decisión tiene que poder explicarse aunque el
    comprador cambie de objetivo después."""

    score_version: str = Field(min_length=1)
    """Bajo qué reglas se decidió. Ver la cabecera: dos números producidos por reglas
    distintas no son comparables."""

    ranking: tuple[RankingEntryV0, ...] = ()
    """El ranking que produjo esta decisión, con la identidad estable
    `(provider_id, property_id)`. Vacío es válido: hay decisiones sobre una sola opción.

    Comparte tipo con la traza (E1.6) a propósito: son el mismo hecho visto desde dos
    sitios, y duplicar el tipo habría permitido que divergieran."""

    recommended_next_action: RecommendedNextActionV0 | None = None
    """`None` = no se evaluó qué hacer. Distinto de `type=NONE`, que es "se evaluó y no
    se recomienda nada" — la misma distinción entre ausente y vacío que gobierna
    `eligibility` y `match`."""

    explanation: ExplanationV0 | None = None
    """`None` = no se generó explicación. Ver `ExplanationV0`."""

    trace_id: str | None = Field(default=None, min_length=1)
    """La ejecución que produjo esta decisión (`DecisionTraceV0.trace_id`).

    Es una referencia, no una evidencia: **no se confunde con `evidence_refs`**. Aquéllas
    dicen qué sustenta cada afirmación; esto dice qué ejecución la generó. `None` = la
    decisión no quedó trazada."""

    eligibility: EligibilityV0 | None = None
    """`None` = no se evaluó la elegibilidad. Ver "ausente no es vacío"."""

    match: MatchV0 | None = None
    """`None` = no se comparó por dimensiones."""

    strengths: tuple[StrengthV0, ...] = ()
    tradeoffs: tuple[DecisionTradeoffV0, ...] = ()
    uncertainties: tuple[UncertaintyV0, ...] = ()

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
