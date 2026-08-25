"""DecisionTraceV0 — la trayectoria auditable de una ejecución (E1.6).

Contrato puro. No se construye el sistema que captura la traza: no hay instrumentación,
ni persistencia, ni hooks de LangGraph, ni benchmark runner. F1 define la forma.

──────────────────────────────────────────────────────────────────────────────────
QUÉ RESPONDE
──────────────────────────────────────────────────────────────────────────────────

    ¿qué insumos y versiones participaron?      buyer_ref, inventory_snapshot_id
    ¿qué proveedores se consultaron?            provider_calls
    ¿qué hechos se usaron REALMENTE?            facts_used
    ¿qué se derivó, y cómo?                     derived_features
    ¿qué políticas se aplicaron?                policies_applied
    ¿qué quedó sin resolver?                    uncertainties
    ¿qué ranking salió?                         ranking
    ¿qué salida corresponde a esta ejecución?   final_output_hash

`facts_used` es el campo con más valor y el más fácil de malinterpretar: registra lo que
ENTRÓ en la decisión, no lo que estaba disponible. Un contexto puede traer veinte
dimensiones y la decisión haber mirado tres; anotar las veinte haría la traza inútil
para la pregunta que importa —¿qué movió el resultado?—.

──────────────────────────────────────────────────────────────────────────────────
QUÉ NO ES
──────────────────────────────────────────────────────────────────────────────────

No es un snapshot de los contextos, ni un volcado de respuestas de Google, Overture o un
partner, ni logging general, ni tracing distribuido, ni el transcript de LangGraph, ni el
prompt, ni el razonamiento interno del modelo. Todo eso o pertenece a observabilidad de
infraestructura o no debe guardarse.

**Nunca almacena credenciales, cabeceras, payloads, respuestas completas, URLs firmadas
ni tokens.** Si algún día hacen falta hashes de request/response, se añaden sin guardar
el contenido.

──────────────────────────────────────────────────────────────────────────────────
POR QUÉ AQUÍ LA EVIDENCIA PUEDE FALTAR Y EN LA DECISIÓN NO
──────────────────────────────────────────────────────────────────────────────────

En `DecisionContextV0` (E1.5) una afirmación material EXIGE al menos una referencia de
evidencia: una fortaleza sin respaldo es "este barrio es tranquilo" sin nada detrás.

Aquí no, y la asimetría es deliberada. La traza **registra lo que pasó, huecos
incluidos**: una llamada a un proveedor que falló no produce evidencia, y un hecho puede
venir de un registro cuya procedencia nadie anotó. Exigir `evidence_ids` obligaría a
inventarse ids para que el objeto validara, que es peor que la ausencia — la traza
dejaría de ser un registro fiel para volverse una redacción.

La regla se mantiene en lo que sí importa: solo IDs, nunca `EvidenceRefV0` embebidos. La
traza dice qué evidencia participó; no es su almacén.

──────────────────────────────────────────────────────────────────────────────────
V0 REPRESENTA EJECUCIONES COMPLETADAS
──────────────────────────────────────────────────────────────────────────────────

No hay `running`, `pending`, `failed`, `cancelled` ni `partial`: eso sería infraestructura
de ciclo de vida antes de necesitarla. Por eso `final_output_hash` es obligatorio y no
vacío — una ejecución sin salida no es una ejecución completada, y representarla es otra
decisión y otra versión.

`inventory_snapshot_id` y `model_config_hash` sí existen siempre como campos, y sin
default: quien crea la traza tiene que **declarar** que no los hay en vez de omitirlos.
Un campo que desaparece en silencio es indistinguible de uno que nadie rellenó.

La política más fuerte —una traza válida para benchmark exige snapshot, y exige
`model_config_hash` cuando intervino un modelo— pertenece a F6 y **no se congela aquí**.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.contracts.common_v0 import ContractBase as _Base
from app.contracts.decision_v0 import BuyerContextRefV0

CONTRACT_VERSION = "decision-trace-v0"


def _ids_utilizables(v: tuple[str, ...]) -> tuple[str, ...]:
    if any(not i.strip() for i in v):
        raise ValueError("un evidence_id vacío no referencia ninguna evidencia")
    repetidos = {i for i in v if v.count(i) > 1}
    if repetidos:
        raise ValueError(f"evidence_id repetido: {sorted(repetidos)}")
    return v


def _exigir_zona(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("los instantes deben traer zona horaria")
    return v


class CallStatus(StrEnum):
    """NUESTRO estado operativo de la llamada, no la semántica del proveedor.

    Enum cerrado y de tres valores porque describe algo que sabemos siempre al
    terminar: si obtuvimos respuesta, si falló, o si se nos acabó el tiempo. Lo que el
    proveedor devolvió —su código, su mensaje— no se guarda: ver "qué no es".
    """

    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    """Distinto de `ERROR` porque operativamente lo es: se reintenta y habla de latencia,
    no de que la petición fuera mala."""


class ProviderCallV0(_Base):
    """Una consulta a un proveedor. Pequeña a propósito."""

    call_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    """Vocabulario abierto: `"google_places"`, `"overpass"`, `"valhalla"`. Mismo criterio
    que `provider` en E1.1 — un enum metería el catálogo de proveedores en el contrato."""

    operation: str = Field(min_length=1)
    """Qué se le pidió, en términos nuestros: `"nearby_search"`, `"isochrone"`."""

    started_at: datetime
    status: CallStatus
    latency_ms: int | None = Field(default=None, ge=0)

    evidence_ids: tuple[str, ...] = ()
    """Puede estar vacío: una llamada que falló no produce evidencia."""

    _z = field_validator("started_at")(_exigir_zona)
    _e = field_validator("evidence_ids")(_ids_utilizables)


class FactUsedV0(_Base):
    """Un hecho que ENTRÓ en la decisión. No todo lo que estaba disponible."""

    fact_path: str = Field(min_length=1)
    """Ruta semántica al hecho: `"property.transaction.price"`,
    `"place.walkability.value"`, `"buyer.hard_constraints[criterion_id=budget-max]"`.

    Se prefiere el identificador estable al índice: `[criterion_id=budget-max]` sigue
    apuntando a lo mismo cuando el array se reordena, y `[0]` no. Es la misma lección
    que hizo nacer `criterion_id` y `anchor_id`."""

    evidence_ids: tuple[str, ...] = ()

    _e = field_validator("evidence_ids")(_ids_utilizables)


class DerivedFeatureV0(_Base):
    """Algo que el sistema calculó a partir de los hechos."""

    name: str = Field(min_length=1)

    value: bool | int | float | str | tuple[bool | int | float | str, ...] | None = None
    """Serializable a JSON e inmutable. En V0 no se admiten objetos anidados: una feature
    derivada que necesite una estructura profunda probablemente sea varias features, y
    esto no es un sistema universal de feature engineering."""

    methodology: str = Field(min_length=1)
    """OBLIGATORIO. Una feature derivada sin metodología recrea exactamente el problema
    que cerró FASE 0: un número que nadie puede reproducir ni discutir."""

    evidence_ids: tuple[str, ...] = ()

    _e = field_validator("evidence_ids")(_ids_utilizables)


class PolicyAppliedV0(_Base):
    """Una política que se aplicó durante la ejecución."""

    policy_id: str = Field(min_length=1)
    policy_version: str | None = Field(default=None, min_length=1)
    outcome: str = Field(min_length=1)
    """Vocabulario abierto en V0. Inventar ahora un enum de resultados congelaría una
    taxonomía de políticas que todavía no existe."""


class TraceUncertaintyV0(_Base):
    """Algo que quedó sin resolver AL EJECUTAR.

    No es lo mismo que una incertidumbre de `DecisionContextV0`: aquella forma parte de
    lo que se le explica a la persona sobre la opción; esta es operativa — un proveedor
    que no respondió, un dato que no se pudo resolver.
    """

    code: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()
    """Puede estar vacío: la incertidumbre existe a menudo por ausencia de evidencia."""

    _e = field_validator("evidence_ids")(_ids_utilizables)


class TraceRankingEntryV0(_Base):
    """Una posición del ranking que produjo el sistema."""

    provider_id: str = Field(min_length=1)
    property_id: str = Field(min_length=1)
    rank: int = Field(ge=1)

    score: float | None = None
    """`None` es válido: un ranking puede no ser numérico."""

    score_version: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _un_score_sin_su_version_no_es_comparable(self) -> TraceRankingEntryV0:
        if self.score is not None and self.score_version is None:
            raise ValueError(
                "hay score pero no score_version: dos números producidos por reglas "
                "distintas no son comparables, y sin la versión nadie puede saberlo"
            )
        return self

    @property
    def identidad_externa(self) -> tuple[str, str]:
        return (self.provider_id, self.property_id)


class DecisionTraceV0(_Base):
    """La trayectoria de una ejecución completada."""

    contract_version: Literal["decision-trace-v0"] = CONTRACT_VERSION

    trace_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    buyer_ref: BuyerContextRefV0

    inventory_snapshot_id: str | None = Field(min_length=1)
    """Sin default: hay que declararlo, aunque sea `None`. Ver la cabecera."""

    model_config_hash: str | None = Field(min_length=1)
    """Sin default, por la misma razón."""

    provider_calls: tuple[ProviderCallV0, ...] = ()
    """Vacío es válido: una ejecución puramente determinista no consulta a nadie."""

    facts_used: tuple[FactUsedV0, ...] = ()
    derived_features: tuple[DerivedFeatureV0, ...] = ()
    policies_applied: tuple[PolicyAppliedV0, ...] = ()
    uncertainties: tuple[TraceUncertaintyV0, ...] = ()
    ranking: tuple[TraceRankingEntryV0, ...] = ()

    final_output_hash: str = Field(min_length=1)
    """Obligatorio: V0 representa ejecuciones COMPLETADAS."""

    created_at: datetime
    """Cierre de la traza. **No** es el `observed_at` de los hechos: una traza creada hoy
    puede haber usado evidencia de hace meses, y sustituir una fecha por otra haría
    parecer fresco lo que no lo es."""

    _z = field_validator("created_at")(_exigir_zona)

    @model_validator(mode="after")
    def _sin_llamadas_repetidas(self) -> DecisionTraceV0:
        ids = [c.call_id for c in self.provider_calls]
        repetidos = {i for i in ids if ids.count(i) > 1}
        if repetidos:
            raise ValueError(f"call_id repetido: {sorted(repetidos)}")
        return self

    @model_validator(mode="after")
    def _un_inmueble_una_posicion(self) -> DecisionTraceV0:
        """Los empates de `rank` son legítimos; el mismo inmueble dos veces, no."""
        ids = [e.identidad_externa for e in self.ranking]
        repetidos = {i for i in ids if ids.count(i) > 1}
        if repetidos:
            raise ValueError(f"inmueble repetido en el ranking: {sorted(repetidos)}")
        return self


def json_schema() -> dict[str, Any]:
    """JSON Schema del contrato. Función y no constante, para que no se congele en el
    import y quede desincronizado del modelo."""
    return DecisionTraceV0.model_json_schema()
