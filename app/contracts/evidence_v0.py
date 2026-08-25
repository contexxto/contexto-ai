"""EvidenceRefV0 — la primitiva compartida de evidencia (E1.1 de FASE 1, Contracts).

QUÉ ES: la procedencia de un dato, no el dato. Un `EvidenceRefV0` responde "¿de dónde
salió esto, cuándo, cómo, y qué NO puede decirme?" y se adjunta al valor, que vive en
otro sitio. Separarlos es deliberado: el mismo valor puede llegar por dos caminos con
credibilidad distinta, y el ranking tiene que poder distinguirlos.

POR QUÉ EXISTE, con nombres y fechas. La FASE 0 cerró dos defectos que son el mismo
defecto:

  · E0.3 — la caminabilidad afirmaba "OpenStreetMap" cuando el número era una
    estimación por zona. El motor y la ficha leían la misma columna y decían cosas
    distintas.
  · E0.4 — ruido y vegetación movían el score ±50 y ±80 puntos sin ninguna fuente
    medida detrás. Se sacaron del ranking y se les dio un estado explícito,
    `insufficient_evidence`.

En los dos casos la causa fue que **la procedencia no era un objeto**: viajaba como
convención, como nombre de columna, como comentario. Este contrato la convierte en algo
que se valida o revienta.

LAS TRES REGLAS QUE ESTE MÓDULO HACE CUMPLIR, y no son decorativas:

  1. NO SE INVENTA PROCEDENCIA. `observed_at` no cae por defecto a `retrieved_at`, ni
     `confidence` a un número inventado. Si no se sabe, hay una forma de decirlo.
  2. UNA ESTIMACIÓN DECLARA SUS LÍMITES. `heuristic_estimate` exige `limitations` no
     vacía. Es E0.4 escrito como invariante en vez de como disciplina.
  3. NINGÚN PROVEEDOR ES ESTRUCTURA. No hay `google_place_id` ni `overture_id`. El
     proveedor es un VALOR en `provider`, no una forma del esquema. Ver §"Proveedores".

ESTE OBJETO REPRESENTA EVIDENCIA QUE EXISTE. No hay `source_type="unknown"` y no debe
haberlo: fabricar una `EvidenceRefV0` para decir "no tengo evidencia" es inventarse una
procedencia para representar su ausencia, que es el mismo error de E0.3 con otra ropa.
La ausencia vive en el contrato consumidor, que la declara con sus propios campos:

    status = "insufficient_evidence"      # el estado que E0.4 dejó visible
    evidence = []                          # vacío, porque no hay
    limitations = ["no hay medición de ruido en este punto"]

Una heurística REAL sí produce evidencia —a veces es lo único que hay—, siempre que
declare `methodology` y `limitations` y no se presente como medición. Eso es distinto
de no tener nada.

Uso mínimo:

    EvidenceRefV0(
        source_type=SourceType.PROVIDER_API,
        provider="google_places",
        source_id="ChIJ...",
        retrieved_at=datetime.now(timezone.utc),
        observed_at=None,                      # el proveedor no dice de cuándo es
        confidence=None,                       # no hay correspondencia numérica defendible
        methodology="Places Details, campo rating; sin fecha de observación",
        persistence_policy=PersistencePolicy.CACHEABLE_TEMPORARILY,
        cache_ttl_seconds=30 * 24 * 3600,
        limitations=("el rating agrega reseñas de fechas desconocidas",),
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# El contrato se versiona en el propio objeto, igual que `score_version = "encaje-v0"`
# hizo en E0.4. Un dato serializado hace seis meses tiene que poder decir bajo qué
# reglas nació; sin esto, comparar dos evidencias es comparar dos cosas que se llaman
# igual. NUNCA se reescribe: una regla nueva que rompa compatibilidad es v1, no v0.
CONTRACT_VERSION = "evidence-ref/v0"


class SourceType(StrEnum):
    """De qué CLASE de origen viene el dato. Clases, no proveedores — ver §"Proveedores".

    El eje que separa estos valores es uno solo: **cuánto se midió y cuánto se supuso.**
    """

    PROVIDER_API = "provider_api"
    """API de un tercero. Cuál, en `provider`."""

    PUBLIC_DATASET = "public_dataset"
    """Dato abierto descargado (Overture, OSM, censo…). Cuál, en `provider`."""

    OWN_MEASUREMENT = "own_measurement"
    """Calculado por Contexto sobre dato primario. La metodología es nuestra y se
    describe en `methodology`; sin eso no es reproducible."""

    USER_DECLARED = "user_declared"
    """Lo dijo la persona. Es evidencia real y a menudo la mejor que hay sobre su
    propia intención — pero es declarada, no verificada, y eso no se maquilla."""

    OPERATOR_DECLARED = "operator_declared"
    """Lo dijo un corredor, un promotor o un partner. Se distingue de USER_DECLARED
    porque quien lo declara tiene interés comercial en el resultado."""

    HEURISTIC_ESTIMATE = "heuristic_estimate"
    """Inferido, no medido. Exige `limitations` no vacía. Este es exactamente el caso
    que en E0.4 movía el ranking sin fuente; el contrato ya no deja que pase callado.

    Ojo: una heurística real ES evidencia. Lo que no es evidencia es no tener nada —
    eso no se representa aquí, ver la cabecera del módulo."""

    # NO existe un valor "unknown", y su ausencia es la decisión. Una evidencia sin
    # procedencia conocida no es una evidencia con procedencia "desconocida": es la
    # AUSENCIA de evidencia, y eso lo declara el contrato consumidor con
    # status=insufficient_evidence y evidence=[]. Si algún día alguien lo echa de menos
    # al migrar datos viejos, la respuesta correcta es no crear la referencia.


class PersistencePolicy(StrEnum):
    """Qué se puede hacer con este dato en el tiempo.

    No es una preferencia de ingeniería: algunos proveedores restringen por contrato
    cuánto se guarda su dato. Como el proveedor no puede ser estructura (§"Proveedores"),
    la restricción viaja aquí, declarada por quien crea la evidencia.
    """

    PERSISTABLE = "persistable"
    """Se puede guardar sin caducidad."""

    CACHEABLE_TEMPORARILY = "cacheable_temporarily"
    """Se puede guardar por un tiempo acotado. **Exige `cache_ttl_seconds`** — una
    política que dice "temporalmente" sin decir cuánto no se puede hacer cumplir, y una
    política que no se puede hacer cumplir es un comentario."""

    RUNTIME_ONLY = "runtime_only"
    """Se usa y se tira. No toca disco."""


class EvidenceRefV0(BaseModel):
    """Procedencia de un dato. Inmutable y serializable.

    §Proveedores — por qué no hay un campo por proveedor
    ────────────────────────────────────────────────────
    No existe `google_place_id`, ni `overture_id`, ni `osm_id`. Si existieran, cada
    proveedor nuevo obligaría a cambiar el contrato, y el contrato pasaría a tener la
    forma del mercado de proveedores en vez de la del problema. Peor: los consumidores
    empezarían a ramificar por `if ev.google_place_id`, que es acoplamiento disfrazado
    de tipado.

    El proveedor es un VALOR: `source_type` dice de qué clase de origen viene y
    `provider` lo nombra. `provider` es texto libre a propósito — restringirlo a un Enum
    de proveedores conocidos volvería a meter el catálogo de proveedores dentro del
    contrato por la puerta de atrás.

    §Qué NO es
    ──────────
    No lleva el valor. No lleva geometría. No lleva nada específico de dominio. Es la
    primitiva que `BuyerContextV0`, `PropertyContextV0` y `PlaceContextV0` incrustan;
    si empieza a crecer con campos de uno de ellos, el que tiene que crecer es ese otro.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        use_enum_values=False,
    )

    contract_version: Literal["evidence-ref/v0"] = CONTRACT_VERSION
    """Fijo por diseño. Que sea `Literal` hace que deserializar un `v1` falle en vez de
    colarse como si fuera esto."""

    evidence_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    """Identidad de esta referencia. Es un asa nuestra, no una afirmación sobre el
    mundo, así que autogenerarla no viola la regla de no inventar procedencia."""

    source_type: SourceType
    provider: str | None = Field(default=None, min_length=1)
    """Quién es el origen concreto, cuando aplica: `"google_places"`, `"overture"`,
    `"overpass"`, `"valhalla"`… Texto libre por diseño."""

    source_id: str | None = Field(default=None, min_length=1)
    """Identificador del dato DENTRO del origen. Opaco: no se parsea ni se interpreta."""

    observed_at: datetime | None
    """Cuándo el mundo estaba así. **Sin valor por defecto**: hay que decidirlo y
    escribirlo. `None` significa "el origen no lo dice", que es una respuesta legítima
    y distinta de "es de ahora".

    Confundir esto con `retrieved_at` es precisamente la mentira de E0.3."""

    retrieved_at: datetime
    """Cuándo lo trajimos nosotros. Esto siempre se sabe."""

    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    """Cuánta confianza merece el dato, en `[0.0, 1.0]`.

        None → desconocida o no proporcionada
        0.0  → confianza explícitamente nula
        1.0  → máxima confianza

    `None` y `0.0` NO son lo mismo, y confundirlos es el error que este campo tiene que
    evitar: `0.0` afirma "esto no merece confianza", que es una medición; `None` dice
    "no lo sé", que es una abstención.

    **No se convierten categorías de un proveedor a números arbitrarios.** Si un origen
    entrega "alta/media/baja" y no hay una correspondencia numérica defendible, esto va
    a `None` y la explicación vive en `methodology` y `limitations`. Inventar el 0.7 que
    hace falta para que el ranking salga bonito es exactamente cómo E0.4 acabó con
    heurísticas puntuando.

    Por qué tiene default `None` y `observed_at` no: omitir `confidence` cae en "no sé",
    que es la afirmación humilde; omitir `observed_at` habría caído en "es de ahora",
    que es una afirmación fuerte y falsa. Los defaults seguros se permiten; los que
    mienten, no."""

    methodology: str = Field(min_length=1)
    """Cómo se obtuvo, en prosa corta y concreta. Obligatorio: una evidencia sin
    metodología no es evidencia, es un número con buena presentación."""

    persistence_policy: PersistencePolicy
    cache_ttl_seconds: int | None = Field(default=None, gt=0)
    """Solo con `CACHEABLE_TEMPORARILY`, y obligatorio con ella."""

    limitations: tuple[str, ...] = Field(default_factory=tuple)
    """Qué NO puede sostener este dato. Obligatorio y no vacío para
    `HEURISTIC_ESTIMATE`.

    Tupla y no lista: `frozen=True` impide reasignar el campo, pero no impide un
    `.append()` sobre una lista. Afirmar inmutabilidad y dejar una colección mutable
    dentro es afirmar algo que no se cumple."""

    # ── invariantes ──────────────────────────────────────────────────────────────

    @field_validator("observed_at", "retrieved_at")
    @classmethod
    def _exigir_zona_horaria(cls, v: datetime | None) -> datetime | None:
        """Un datetime sin zona no dice nada: en esta máquina es Quito, en el runner es
        UTC, y comparar los dos da diferencias de cinco horas que parecen datos. El
        repo ya pagó un bug de fechas por esto."""
        if v is not None and v.tzinfo is None:
            raise ValueError(
                "los instantes deben traer zona horaria (usa datetime.now(timezone.utc)); "
                "un datetime naive cambia de significado según dónde corra"
            )
        return v

    @field_validator("limitations")
    @classmethod
    def _limitaciones_con_texto(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if any(not l.strip() for l in v):
            raise ValueError("una limitación vacía no limita nada")
        return v

    @model_validator(mode="after")
    def _no_observar_despues_de_traer(self) -> EvidenceRefV0:
        """No se puede haber observado el mundo después de haberlo consultado."""
        if self.observed_at is not None and self.observed_at > self.retrieved_at:
            raise ValueError(
                f"observed_at ({self.observed_at.isoformat()}) es posterior a "
                f"retrieved_at ({self.retrieved_at.isoformat()}): el dato no puede "
                "describir un momento que aún no había ocurrido cuando se trajo"
            )
        return self

    @model_validator(mode="after")
    def _ttl_solo_y_siempre_con_cache_temporal(self) -> EvidenceRefV0:
        """`cacheable_temporarily` sin plazo es inaplicable; con plazo en las otras dos
        es una instrucción contradictoria. Se exige en un sentido y se prohíbe en el
        otro para que la política signifique siempre lo mismo."""
        temporal = self.persistence_policy is PersistencePolicy.CACHEABLE_TEMPORARILY
        if temporal and self.cache_ttl_seconds is None:
            raise ValueError(
                "persistence_policy=cacheable_temporarily exige cache_ttl_seconds: "
                "'temporalmente' sin plazo no se puede hacer cumplir"
            )
        if not temporal and self.cache_ttl_seconds is not None:
            raise ValueError(
                f"cache_ttl_seconds no aplica a persistence_policy="
                f"{self.persistence_policy.value}; solo a cacheable_temporarily"
            )
        return self

    @model_validator(mode="after")
    def _lo_no_medido_declara_sus_limites(self) -> EvidenceRefV0:
        """E0.4, convertido en invariante.

        Una heurística puede entrar al sistema —a veces es lo único que hay— pero no
        puede entrar callada.
        """
        if self.source_type is SourceType.HEURISTIC_ESTIMATE and not self.limitations:
            raise ValueError(
                "source_type=heuristic_estimate exige al menos una entrada en "
                "limitations: un dato no medido que no declara qué no puede sostener "
                "acaba puntuando como si estuviera medido"
            )
        return self

    # ── ayudas de lectura, sin lógica de negocio ─────────────────────────────────

    @property
    def es_medicion(self) -> bool:
        """¿Esto se midió, o se supuso? La pregunta que E0.3 y E0.4 no podían responder.

        Deliberadamente NO devuelve un score ni un peso: quién puntúa y cuánto es
        decisión del motor, no del contrato.
        """
        return self.source_type is not SourceType.HEURISTIC_ESTIMATE

    @property
    def puede_guardarse(self) -> bool:
        return self.persistence_policy is not PersistencePolicy.RUNTIME_ONLY


def json_schema() -> dict[str, Any]:
    """JSON Schema del contrato, para consumidores que no son Python.

    Se expone como función y no como constante para que no se congele en el import y
    quede desincronizado del modelo si alguien lo edita.
    """
    return EvidenceRefV0.model_json_schema()


def ahora() -> datetime:
    """UTC con zona. Existe para que nadie escriba `datetime.now()` a secas y se cuele
    un naive que el validador rechazará más tarde y más lejos."""
    return datetime.now(timezone.utc)
