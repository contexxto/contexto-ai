"""BuyerContextV0 — lo que sabemos de quien decide (E1.2 de FASE 1, Contracts).

QUÉ ES: el estado de conocimiento sobre una persona que está decidiendo dónde vivir.
Conocimiento PARCIAL por definición: casi todo puede ser `None`, y lo que falta se
nombra en `unresolved_questions` en vez de rellenarse con un supuesto.

Contrato puro. No hay updater, ni persistencia, ni resolución de conflictos, ni
herramientas: eso es Buyer Harness y es otra fase.

──────────────────────────────────────────────────────────────────────────────────
LAS CUATRO REGLAS CONGELADAS
──────────────────────────────────────────────────────────────────────────────────

1. `household` NO EXISTE AQUÍ, y no es un olvido: es estructural.

   No basta con excluirlo del scoring — si el campo existe, alguien lo llena, y lo que
   se llena termina puntuando. El Plan 1.0 sustituyó esa dimensión por NECESIDADES
   EXPLÍCITAS: dormitorios, área, mascotas, movilidad, accesibilidad y presupuesto.

   La diferencia importa y no es cosmética. "Familia de cuatro" es una descripción de
   quién es la persona —y *familial status* es categoría protegida—. "Necesita tres
   dormitorios" es una descripción de lo que el inmueble tiene que tener. La segunda es
   verificable contra el inmueble; la primera solo sirve para inferir un perfil.

   Lo mismo con accesibilidad: se modela lo que el INMUEBLE debe cumplir ("sin
   escaleras", "ascensor"), nunca una condición de la persona. La discapacidad es
   categoría protegida; un requisito de acceso sin escalones es un requisito del
   inmueble.

   `extra="forbid"` hace que colar `household` falle al construir, no en revisión.

2. LOS CUATRO REGISTROS SE MANTIENEN SEPARADOS. `hard_constraints`,
   `soft_preferences`, `tradeoffs` y `unresolved_questions` no se funden en una lista
   de preferencias ponderadas.

   Cada uno se usa distinto y colapsarlos pierde justo lo que hace útil el objeto: una
   restricción dura DESCALIFICA, una preferencia blanda ORDENA, un tradeoff dice qué
   está dispuesta a cambiar por qué, y una pregunta abierta dice qué NO sabemos. Meter
   todo en `{dimensión: peso}` convierte "no puede tener escaleras" y "prefiere que haya
   un parque cerca" en la misma clase de cosa, que es como un motor acaba ofreciendo un
   tercer piso sin ascensor porque el parque compensaba.

   Las restricciones y preferencias no son prosa: son `DecisionCriterionV0`, con
   dimensión, operador, valor y procedencia. Guardarlas como texto obligaría a
   reparsear con un LLM cada vez que alguien quiera comprobarlas contra un inmueble, y
   ahí es donde se cuelan las alucinaciones que FASE 0 se pasó cerrando.

3. `stage` ES EL RECORRIDO DE LA DECISIÓN, NO EL CALOR COMERCIAL.

   `app/intencion.py` ya modela el otro eje: cuán cerca está de transaccionar
   (`anonimo → identificado → … → confirmado`, con frío/tibio/caliente), inferido de
   señales de conversación. Es un eje de VENTA.

   `stage` aquí es un eje de DECISIÓN: cuánto ha convergido sobre lo que quiere. Son
   ortogonales — alguien puede tener criterios clarísimos y cero intención de comprar
   este año, o estar caliente comercialmente sin saber aún qué busca. Confundirlos
   haría que el sistema apurara a quien todavía está orientándose.

   **El vocabulario queda abierto en V0** (`str | None`), porque no hay todavía
   evidencia de producto que respalde una lista concreta de etapas. Ver el campo.

4. LA PROCEDENCIA ES UNA SOLA. `EvidenceRefV0` (E1.1), por dos caminos según el sitio:
   los criterios la llevan DENTRO (`DecisionCriterionV0.evidence`) y se referencian por
   `criterion_id`, que es estable; el resto de campos la lleva en `field_evidence` con
   la ruta del campo. No hay un segundo sistema de procedencia.

──────────────────────────────────────────────────────────────────────────────────
LO QUE ESTE CONTRATO **NO** GARANTIZA
──────────────────────────────────────────────────────────────────────────────────

Que las categorías protegidas no sean ESTRUCTURA está garantizado y probado. Que no
aparezcan en el TEXTO libre de una restricción o una preferencia, no: un contrato no
puede vigilar prosa. Eso es trabajo de `app/fair_housing.py` y de la fase que conecte
ambos. Decirlo aquí evita que alguien lea este módulo como una garantía que no da.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.contracts.evidence_v0 import EvidenceRefV0

CONTRACT_VERSION = "buyer-context-v0"


class _Base(BaseModel):
    """Config común: inmutable y sin campos extra. Ver E1.1 para el porqué del frozen."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Objective(StrEnum):
    """Para qué busca."""

    BUY = "buy"
    RENT = "rent"
    INVEST = "invest"
    UNKNOWN = "unknown"
    """Todavía no lo sabemos. Es el valor honesto al empezar una conversación."""


class Direction(StrEnum):
    """Hacia dónde quiere moverse en una dimensión del lugar."""

    MORE = "more"
    LESS = "less"
    UNSPECIFIED = "unspecified"
    """Le importa la dimensión pero no sabemos en qué sentido. Sin esto, "me importa el
    ruido" habría que adivinarlo, y adivinar es lo que E0.4 nos costó.

    Ojo con el límite: si ni siquiera sabemos si la dimensión le importa, **no se crea
    la preferencia**. `UNSPECIFIED` afirma que le importa; no es un relleno para cuando
    no sabemos nada."""


class Operator(StrEnum):
    """Comparadores genéricos. A propósito NO hay nada inmobiliario aquí.

    Un `Operator` con valores tipo `MIN_BEDROOMS` metería el dominio dentro de la
    primitiva y obligaría a tocarla cada vez que aparezca una dimensión nueva. La
    dimensión viaja en `dimension`, que es texto.
    """

    GTE = "gte"
    LTE = "lte"
    GT = "gt"
    LT = "lt"
    EQ = "eq"
    NEQ = "neq"
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"


class CriterionStatus(StrEnum):
    """De dónde salió el criterio y si sigue vigente.

    Esto SÍ es un enum cerrado, a diferencia de `stage`, y la diferencia tiene razón:
    `stage` es una hipótesis sobre cómo decide la gente —necesita evidencia de uso para
    cerrarse—, mientras que esto es un hecho sobre nuestros propios datos. Que un
    criterio lo dijera la persona o lo dedujéramos nosotros no depende de aprender nada
    del mercado: ya lo sabemos al escribirlo.
    """

    STATED = "stated"
    """Lo dijo la persona."""

    INFERRED = "inferred"
    """Lo dedujimos de otra cosa. Mismo espíritu que `heuristic_estimate` en E1.1: puede
    entrar, pero no disfrazado de declaración."""

    RETRACTED = "retracted"
    """Estuvo vigente y ya no. Se conserva en vez de borrarse porque saber que alguien
    descartó un criterio es información, y borrarlo hace que el sistema vuelva a
    proponer lo que ya rechazó."""


CriterionValue = bool | int | float | str | tuple[str | int | float, ...] | None
"""Lo que se compara. Sin `Any`: un valor que puede ser cualquier cosa no se puede
validar, y un criterio que no se puede validar no es evaluable más adelante."""


class DecisionCriterionV0(_Base):
    """Un criterio evaluable. Estructura, no prosa.

    POR QUÉ NO ES TEXTO. Una restricción guardada como `"sin escalones"` obliga a
    reparsear prosa cada vez que alguien quiera comprobarla contra un inmueble — y
    reparsear prosa con un LLM es exactamente donde se cuelan las alucinaciones que
    FASE 0 se pasó cerrando. Con `dimension="stairs"`, `operator=EXISTS` negado y su
    evidencia al lado, la comprobación es una comparación.

    LO QUE **NO** HAY AQUÍ, y es deliberado: no hay motor de evaluación, ni parser, ni
    updater. El contrato solo tiene que poder REPRESENTAR el criterio de forma que
    alguien lo evalúe después. Quién evalúa y cómo es Decision Core, otra fase.

    La evidencia viaja DENTRO del criterio, no por una ruta tipo
    `"hard_constraints[0]"`: esas rutas se rompen en cuanto cambia el orden del array.
    `criterion_id` es el identificador estable, y es único dentro del contexto.
    """

    criterion_id: str = Field(min_length=1)
    dimension: str = Field(min_length=1)
    """Qué se compara: `"bedrooms"`, `"area_m2"`, `"stairs"`, `"pets_allowed"`. Texto
    libre por la misma razón que `provider` en E1.1 — un enum de dimensiones metería el
    catálogo del dominio dentro de la primitiva."""

    operator: Operator
    value: CriterionValue = None
    unit: str | None = Field(default=None, min_length=1)
    """Unidad del valor: `"m2"`, `"minutes"`, `"USD"`. `None` cuando no aplica."""

    status: CriterionStatus
    evidence: tuple[EvidenceRefV0, ...] = ()
    """Procedencia, con la primitiva de E1.1. Regla 4: no hay un segundo sistema."""

    @model_validator(mode="after")
    def _el_valor_encaja_con_el_operador(self) -> DecisionCriterionV0:
        """Sin esto, `operator=GTE` con `value="tres"` se guarda tan tranquilo y revienta
        meses después, en el evaluador, lejos de donde se creó."""
        op, v = self.operator, self.value

        if op in (Operator.EXISTS, Operator.NOT_EXISTS):
            if v is not None:
                raise ValueError(f"operator={op.value} no lleva value; recibió {v!r}")
            if self.unit is not None:
                raise ValueError(f"operator={op.value} no lleva unit")
            return self

        if v is None:
            raise ValueError(
                f"operator={op.value} necesita un value; para expresar presencia o "
                "ausencia usa exists / not_exists"
            )

        if op in (Operator.IN, Operator.NOT_IN):
            if not isinstance(v, tuple):
                raise ValueError(f"operator={op.value} necesita una colección de valores")
            if not v:
                raise ValueError(f"operator={op.value} con colección vacía no compara nada")
            return self

        if isinstance(v, tuple):
            raise ValueError(
                f"operator={op.value} compara contra un valor único, no una colección"
            )

        if op in (Operator.GTE, Operator.LTE, Operator.GT, Operator.LT):
            # bool es subclase de int en Python; un orden sobre True/False no significa nada.
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(
                    f"operator={op.value} ordena, así que necesita un número; "
                    f"recibió {type(v).__name__}"
                )
        return self


class TravelMode(StrEnum):
    WALK = "walk"
    TRANSIT = "transit"
    DRIVE = "drive"
    BIKE = "bike"
    UNKNOWN = "unknown"


class Money(_Base):
    """Importe con moneda. La moneda no es opcional: Contexto opera en Quito y mira
    plazas en México, y un número suelto no dice si son 200 000 dólares o pesos."""

    amount: Decimal = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    """ISO 4217 en mayúsculas: `USD`, `MXN`."""


class Financial(_Base):
    budget_max: Money | None = None
    """Techo declarado. `None` = no lo sabemos; que aparezca en `unresolved_questions`
    es lo que convierte ese hueco en algo accionable."""


class PropertyRequirements(_Base):
    """Lo que el INMUEBLE debe cumplir. Nunca una descripción de la persona — regla 1."""

    bedrooms_min: int | None = Field(default=None, ge=0)
    area_m2_min: float | None = Field(default=None, gt=0)
    pets_allowed_required: bool | None = None
    """Que el inmueble admita mascotas. Es un requisito del inmueble, no un dato del
    hogar."""

    accessibility_requirements: tuple[str, ...] = ()
    """Requisitos de acceso DEL INMUEBLE: "sin escalones", "ascensor", "puerta ancha".

    Deliberadamente NO hay un campo para una condición de la persona. La discapacidad
    es categoría protegida; lo que el inmueble tiene que cumplir es una especificación
    verificable contra el inmueble."""


class CommuteAnchor(_Base):
    """Un sitio al que necesita llegar con frecuencia.

    Queda ESTRUCTURADO y listo para resolución espacial futura, pero aquí no se resuelve
    nada: no hay `compute_travel_to_anchor` y no debe haberlo en F1. El contrato solo
    tiene que poder representar tanto lo que la persona dijo (`raw_location`) como lo
    ya geocodificado (`lat`/`lon`), y no confundirlos.
    """

    label: str = Field(min_length=1)
    """Cómo lo llama la persona: "la oficina", "el colegio de mi hija"."""

    raw_location: str | None = Field(default=None, min_length=1)
    """Tal como lo dijo, sin resolver. Se conserva aunque ya haya coordenadas: si la
    geocodificación fue mala, esto es lo único que permite darse cuenta."""

    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    mode: TravelMode = TravelMode.UNKNOWN
    max_minutes: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _las_coordenadas_van_de_a_dos(self) -> CommuteAnchor:
        if (self.lat is None) != (self.lon is None):
            raise ValueError(
                "lat y lon van juntas: media coordenada no ubica nada y se propaga "
                "como si ubicara"
            )
        return self

    @model_validator(mode="after")
    def _un_ancla_tiene_que_apuntar_a_algo(self) -> CommuteAnchor:
        if self.raw_location is None and self.lat is None:
            raise ValueError(
                "un ancla necesita raw_location o coordenadas: sin ninguna de las dos "
                "es una etiqueta sin destino"
            )
        return self

    @property
    def esta_resuelta(self) -> bool:
        """¿Ya tiene coordenadas? Lo pregunta quien vaya a resolverlas, en otra fase."""
        return self.lat is not None


class Mobility(_Base):
    commute_anchors: tuple[CommuteAnchor, ...] = ()


class PlacePreference(_Base):
    """Qué le importa del lugar y en qué sentido. Sin peso — regla 2."""

    dimension: str = Field(min_length=1)
    """"ruido", "áreas verdes", "caminabilidad"…"""

    direction: Direction = Direction.UNSPECIFIED


class Tradeoff(_Base):
    """Qué está dispuesta a ceder y a cambio de qué.

    Es el registro que más se pierde al colapsar todo en pesos, y el más caro de perder:
    un peso dice "esto importa 0,7", un tradeoff dice "acepto veinte minutos más de
    trayecto si hay un dormitorio más". Lo segundo se puede verificar contra una opción
    concreta; lo primero no.
    """

    gives_up: str = Field(min_length=1)
    gains: str = Field(min_length=1)


class UnresolvedQuestion(_Base):
    """Algo que sabemos que no sabemos.

    Es la contraparte de que casi todo pueda ser `None`: sin esto, un hueco y un dato
    ausente por descuido son indistinguibles.
    """

    question: str = Field(min_length=1)
    about_field: str | None = Field(default=None, min_length=1)
    """Ruta del campo que resolvería, p. ej. `"financial.budget_max"`. Opcional porque
    hay preguntas que no mapean a un campo, pero es lo que hace la pregunta accionable."""


class FieldEvidence(_Base):
    """De dónde salió un campo concreto de este contexto.

    `evidence` es un `EvidenceRefV0` (E1.1). Regla 4: no hay un segundo sistema de
    procedencia para el comprador.
    """

    field: str = Field(min_length=1)
    """Ruta del campo: `"financial.budget_max"`, `"property_requirements.bedrooms_min"`.

    **No se usa para criterios.** Un `DecisionCriterionV0` lleva su evidencia dentro y
    se identifica por `criterion_id`, que es estable; una ruta como
    `"hard_constraints[0]"` deja de apuntar a lo mismo en cuanto cambia el orden del
    array, y nadie se entera."""

    evidence: EvidenceRefV0


class BuyerContextV0(_Base):
    """Estado de conocimiento sobre quien decide. Inmutable, parcial y con procedencia."""

    version: Literal["buyer-context-v0"] = CONTRACT_VERSION
    """Versión DEL CONTRATO. **No** es el número de revisión del estado del comprador —
    ese es `context_revision`. Reutilizar este campo para las dos cosas haría imposible
    saber si un cambio viene de que la persona dijo algo nuevo o de que cambiaron las
    reglas del esquema."""

    context_revision: int | None = Field(default=None, ge=0)
    """Revisión del ESTADO, separada de la versión del contrato. Se declara aquí para
    que la distinción exista desde el principio, pero **no se implementa nada**: ni
    store, ni historial, ni diff. Eso es Buyer Harness (F3). `None` = sin versionar."""

    buyer_id: str = Field(min_length=1)
    objective: Objective = Objective.UNKNOWN
    financial: Financial = Field(default_factory=Financial)
    property_requirements: PropertyRequirements = Field(
        default_factory=PropertyRequirements
    )
    mobility: Mobility = Field(default_factory=Mobility)
    place_preferences: tuple[PlacePreference, ...] = ()

    hard_constraints: tuple[DecisionCriterionV0, ...] = ()
    """Descalifican. Si no se cumple, la opción no entra — no "puntúa menos"."""

    soft_preferences: tuple[DecisionCriterionV0, ...] = ()
    """Ordenan entre las que sí entran. Misma primitiva que las duras a propósito: lo
    que cambia es CÓMO se usan, no cómo se escriben, y esa diferencia la marca el campo
    en el que viven — regla 2."""

    tradeoffs: tuple[Tradeoff, ...] = ()

    stage: str | None = Field(default=None, min_length=1)
    """Estado de DECISIÓN del comprador: cuánto ha convergido sobre lo que quiere.

    **Vocabulario deliberadamente abierto en V0.** Valores como
    `"orienting" / "narrowing" / "validating" / "committing"` son razonables, pero hoy
    no están respaldados por evidencia de producto ni de uso — son una hipótesis sobre
    cómo decide la gente. Congelarlos en un enum sería fijar esa hipótesis con la misma
    fuerza que un hecho medido, que es justo el error que FASE 0 se pasó cerrando en
    otro terreno. **Se cerrará a enum cuando exista esa evidencia, no antes.**

    ORTOGONAL A `app/intencion.py`, que mide el otro eje: cuán cerca está de
    transaccionar (`anonimo → … → confirmado`, frío/tibio/caliente) a partir de señales
    de conversación. Ese es un eje de VENTA; este es de DECISIÓN. Se puede tener
    criterios clarísimos y cero intención de comprar este año, y al revés.

    Consecuencia honesta de dejarlo abierto: mientras sea `str`, la separación entre los
    dos ejes está DOCUMENTADA pero no puede hacerse cumplir por el tipo. Nada impide
    escribir aquí `"enganchado"`. Cuando se cierre el vocabulario, esa garantía vuelve.

    `None` = no hay señal suficiente."""

    field_evidence: tuple[FieldEvidence, ...] = ()
    unresolved_questions: tuple[UnresolvedQuestion, ...] = ()
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def _exigir_zona_horaria(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError(
                "updated_at debe traer zona horaria: un datetime naive vale cinco horas "
                "distintas según dónde corra"
            )
        return v

    @model_validator(mode="after")
    def _cada_criterio_tiene_identidad_propia(self) -> BuyerContextV0:
        """`criterion_id` solo sirve como referencia estable si es único. Si se repite,
        apuntar a él vuelve a ser tan ambiguo como apuntar a `hard_constraints[0]`."""
        ids = [c.criterion_id for c in (*self.hard_constraints, *self.soft_preferences)]
        repetidos = {i for i in ids if ids.count(i) > 1}
        if repetidos:
            raise ValueError(
                f"criterion_id repetido: {sorted(repetidos)}. Tiene que ser único en "
                "todo el contexto para poder referenciarlo sin ambigüedad"
            )
        return self


def json_schema() -> dict[str, Any]:
    """JSON Schema del contrato. Función y no constante, para que no se congele en el
    import y quede desincronizado del modelo."""
    return BuyerContextV0.model_json_schema()
