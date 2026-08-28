"""E3.2b.1 · Extractor + routing situacional — la capa determinista.

Decide, para **un** `IdentifiedUserMessage`, qué de lo que se afirmó es estado durable del
comprador, qué es contexto del turno, qué es ambiguo y qué no debe crear estado — y lo
devuelve como un lote ordenado.

`[PENDIENTE · intérprete NOT STARTED]` **Este módulo no lee el texto para producir las
afirmaciones.** `construir_lote` las recibe ya construidas de su llamante y usa el texto sólo
para detectar autocorrección. El paso `text → Afirmacion` no existe todavía, así que decir
que el extractor "convierte un mensaje en decisiones" describiría una capa que nadie ha
escrito.

## Dos guardas, y protegen cosas distintas

```
E3.2b.0 boundary   protege DESTINOS   →  no hay dónde escribir household.children
E3.2b.1 aquí       protege TRADUCCIONES →  "tenemos dos niños" no puede volverse bedrooms_min=2
```

La segunda es la que importa en esta unidad, porque `SetBedroomsMin(2)` es una mutación
**perfectamente válida para el tipo**. La frontera no puede rechazarla: es exactamente lo que
está diseñada para aceptar. Lo único que puede impedir que nazca de una frase sobre personas
es exigir evidencia textual de lo que se va a escribir.

`autorizar_traduccion` es esa exigencia, y es determinista a propósito: un modelo no puede
tender el puente persona → requisito de propiedad porque el puente se comprueba fuera de él.

## Qué cuenta como evidencia

```
EVIDENCIA EXACTA   no es   "todos los tokens necesarios existen en el mensaje"
                   es      "los tokens sostienen LA MISMA afirmación"
```

Esa distinción no es retórica: cada vez que se relajó costó una autorización falsa, y las
tres formas de relajarla aparecieron por separado.

**LOCAL.** La evidencia vive en UNA cláusula. Repartida por el mensaje, dos hechos sin
relación suman un tercero que nadie declaró: `"tenemos 2 niños y al menos 3 dormitorios"`
autorizaba `SetBedroomsMin(2)` —el peor caso del §7—, y
`"ya no necesito mascotas; mi presupuesto máximo es 120000 USD"` autorizaba `ClearBudgetMax`,
borrando un campo vigente.

**POSITIVA.** La cláusula tiene que afirmar, no negar. `"no quiero comprar"` contiene
`comprar`, y sin ese filtro el patrón de `BUY` encontraba ahí su evidencia y autorizaba lo
contrario de lo que dijo el usuario. La matriz del §5 lo congela como AMBIGUOUS.

**DEL VALOR, no de la dimensión.** Los tres objetivos comparten vocabulario, así que
comprobar la dimensión dejaba pasar `SetObjective(BUY)` ante `"quiero alquilar"`. Y ningún
`Clear*` se autoriza por omisión: necesita retractación explícita de su propia dimensión, en
su propia cláusula.

## Routing POR AFIRMACIÓN, no por mensaje

Un mensaje mezcla cosas. *"Quiero comprar, máximo 120000 USD y algo tranquilo"* tiene dos
hechos persistibles y uno que no lo es; tratar el mensaje como una sola disposición
perdería los dos primeros por culpa del tercero.

## Por qué CUATRO clases de afirmación y no una con `disposicion` variable

Una sola clase obliga a un validador que diga *"si no eres DURABLE no lleves mutación"*, y
—lo que costó el defecto que abre E3.2b.1a— **deja la dimensión colgando de la mutación**:
una ambigüedad sin mutación no tenía campo, así que no competía con la durable que venía a
invalidar, y `"120000 USD… no, 100000"` conservaba los 120000.

Con la unión cerrada eso deja de ser un caso que haya que acordarse de cubrir:
`AfirmacionAmbiguous` **exige** su `BuyerFieldV0`, y `AfirmacionDurable` no tiene dónde
recibir uno —lo deriva de su propia mutación—. Es el mismo principio que `BuyerMutationV0`:
no se filtra lo inválido, se deja sin forma de expresarlo.

## Lo que NO hace

No aplica mutaciones, no construye el contexto del comprador, no toca el store, no crea
procedencia, no resuelve conflictos entre mensajes y no detecta novedad —*identificado
≠ nuevo*: eso lo resuelve el store por `(buyer_id, source_message_id)`.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from decimal import Decimal
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.buyer.boundary import (
    BuyerCurrencyV0,
    BuyerFieldV0,
    BuyerMutationV0,
    ClearAreaM2Min,
    ClearBedroomsMin,
    ClearBudgetMax,
    ClearObjective,
    ClearPetsRequired,
    Disposicion,
    SetAreaM2Min,
    SetBedroomsMin,
    SetBudgetMax,
    SetObjective,
    SetPetsRequired,
    campo_de_mutacion,
)
from app.contracts.buyer_v0 import Objective

_CERRADO = ConfigDict(frozen=True, extra="forbid")


def _norm(texto: str) -> str:
    """Minúsculas sin acentos. Comparar `"mínimo"` con `"minimo"` no es interpretar: es no
    fallar por una tilde."""
    plano = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in plano if unicodedata.category(c) != "Mn")


# ── La autorización semántica ──────────────────────────────────────────────────────
#
# Cada mutación exige que el texto evidencie **su dimensión Y su valor concreto**. No es un
# detector de intención —eso puede proponerlo un modelo— sino la condición sin la cual
# ninguna propuesta se acepta. Todo el vocabulario es cerrado y se amplía a mano, con la
# misma disciplina que `encaje.DIMENSIONES`.
#
# Comprobar solo la dimensión era el defecto 4 de §6b: `SetObjective` comparte vocabulario
# para comprar/alquilar/invertir, así que `BUY` pasaba ante un texto que solo dice "quiero
# alquilar". Una dimensión correcta con un valor inventado es indistinguible, para el store,
# de una preferencia que el usuario declaró.

_MINIMO = re.compile(
    r"(al menos|como minimo|minimo|minimum|at least|o mas|o más|en adelante|desde)")

_DIM_OBJECTIVE = re.compile(r"\b(comprar|compra|adquirir|buy|purchase|"
                            r"alquilar|arrendar|rentar|rent|"
                            r"invertir|inversion|invest)\b")
_DIM_BUDGET = re.compile(r"\b(presupuesto|budget|maximo|max|hasta|tope)\b")
# La dimensión Y el mínimo se piden por separado: "2 dormitorios" nombra la dimensión pero
# no declara un mínimo, y V0 solo modela mínimos.
_DIM_BEDROOMS = re.compile(r"\b(dormitorio|dormitorios|habitacion|habitaciones|"
                           r"cuarto|cuartos|recamara|recamaras|bedroom|bedrooms)\b")
_DIM_AREA = re.compile(r"(\bm2\b|\bm²|metros? cuadrados?|square meters?)")
_PETS_SUSTANTIVO = re.compile(r"\b(mascota|mascotas|perro|perros|gato|gatos|pet|pets)\b")

# Dos clases de verbo, y separarlas es lo que impide sumar dos hechos sin relación:
#
#   REQUISITO   genérico —"necesito", "deben"—. NO relaciona nada con la mascota por sí solo:
#               en "necesito 2 dormitorios" pide dormitorios. Exige el sustantivo EN SU
#               CLÁUSULA.
#   ANAFORICO   el clítico de objeto —"aceptarlo"— ya lleva dentro a qué se refiere. Es lo
#               que hace legítimo *"tengo un perro y deben aceptarlo"*, donde el sustantivo
#               vive en la cláusula anterior.
_PETS_REQUISITO = re.compile(
    r"\b(acepte|acepten|admita|admitan|permita|permitan|"
    r"necesito|necesitamos|debe|deben|tiene que|allowed|required)\b")
_PETS_ANAFORICO = re.compile(r"\b(aceptarlo|aceptarla|aceptarlos|aceptarlas|"
                             r"admitirlo|admitirla|admitirlos|admitirlas)\b")


# ── La evidencia del VALOR ─────────────────────────────────────────────────────────

_EVIDENCIA_OBJECTIVE: dict[Objective, re.Pattern] = {
    Objective.BUY: re.compile(r"\b(comprar|compra|compro|adquirir|adquiero|buy|purchase)\b"),
    Objective.RENT: re.compile(r"\b(alquilar|alquilo|arrendar|arriendo|rentar|rento|rent)\b"),
    Objective.INVEST: re.compile(r"\b(invertir|invierto|inversion|invest)\b"),
}
"""Un patrón POR VALOR, no por dimensión. Es la mitad que faltaba: sin esto, los tres
objetivos comparten el mismo vocabulario y cualquiera de ellos pasa por los otros dos."""

_MONEDA_ISO: dict[BuyerCurrencyV0, re.Pattern] = {
    BuyerCurrencyV0.USD: re.compile(r"\busd\b"),
    BuyerCurrencyV0.MXN: re.compile(r"\bmxn\b"),
}
"""**Solo el código ISO literal.** El símbolo `$` no resuelve USD y `pesos` no implica MXN:
las dos están congeladas como AMBIGUOUS en la matriz del §4. Aceptar `dolares` reabriría lo
mismo por otra puerta —hay ocho dólares en el mundo— así que el coste de que
`"máximo 120000 dólares"` no autorice es deliberado, no un olvido."""

# El lookbehind `(?<!\w)` es lo que impide que el "2" de `m2` cuente como un número que el
# usuario dijo. Sin él, "mínimo 80 m2" ofrecería {80, 2} y autorizaría un área mínima de 2.
_TOKEN_NUMERICO = re.compile(r"(?<!\w)\d[\d.,]*")
_SOLO_DIGITOS = re.compile(r"\d+")
_MILES = re.compile(r"\d{1,3}(?:[.,]\d{3})+")


def _numeros_del_texto(plano: str) -> set[Decimal]:
    """Los números que el mensaje declara de forma INEQUÍVOCA.

    Se aceptan dos formas y nada más: dígitos puros (`120000`) y grupos de exactamente tres
    (`120.000`, `1,200,000`). Cualquier otra —`120.5`, `120000.50`, `1.2.3`— **no aporta
    evidencia**, porque `120.000` puede ser ciento veinte mil o ciento veinte coma cero según
    la plaza y esta guarda no tiene forma de saber cuál.

    Ante duda → no autorizar. El coste conocido es que un presupuesto con centavos no es
    autorizable por esta gramática; se prefiere eso a inventar un valor persistente.
    """
    valores: set[Decimal] = set()
    for token in _TOKEN_NUMERICO.findall(plano):
        token = token.rstrip(".,")                    # "…120000." al cerrar una frase
        if _SOLO_DIGITOS.fullmatch(token):
            valores.add(Decimal(token))
        elif _MILES.fullmatch(token):
            valores.add(Decimal(token.replace(".", "").replace(",", "")))
    return valores


# Cláusulas. Acotan el alcance de una negación —"tengo un perro y deben aceptarlo" autoriza,
# "no necesito que acepten mascotas" no— y, sobre todo, ACOTAN EL ALCANCE DE UN NÚMERO.
#
# La puntuación NO corta entre dígitos: en "120.000" ese punto es un separador de miles, no
# un fin de cláusula. Sin esa excepción el número se parte en "120" y "000" y un presupuesto
# perfectamente declarado deja de autorizarse. Lo destapó el test de B3.
_CLAUSULA = re.compile(r"(?<!\d)[,;.:]|[,;.:](?!\d)|[!?¡¿]|\by\b|\bpero\b|\baunque\b")
_NEGACION = re.compile(r"\b(no|ni|tampoco|sin)\b")


def _afirmativas(plano: str):
    """Las cláusulas que AFIRMAN algo: las que no llevan negación.

    Una cláusula negada no evidencia lo que nombra — lo contradice. `"no quiero comprar"`
    contiene `comprar`, y sin este filtro el patrón de `BUY` encontraba ahí su evidencia y
    autorizaba lo contrario de lo que dijo el usuario. La matriz del §5 congela ese mensaje
    como AMBIGUOUS: *"¿alquila, o retira el objetivo?"*.

    **Por cláusula y no por mensaje**: una negación en otra cláusula no puede costar un hecho
    que el usuario sí declaró. *"No tengo mascotas, pero quiero comprar"* declara la compra.
    """
    return [c for c in _CLAUSULA.split(plano) if not _NEGACION.search(c)]


def _evidencia_objective(mutacion, plano: str) -> bool:
    patron = _EVIDENCIA_OBJECTIVE.get(mutacion.objective)
    return patron is not None and any(patron.search(c) for c in _afirmativas(plano))


def _numero_junto_a_su_dimension(plano: str, valor, *dimension: re.Pattern) -> bool:
    """¿Alguna cláusula AFIRMA esta dimensión **y** este número a la vez?

    **Por cláusula, y es una frontera de Fair Housing, no una preferencia de estilo.** Buscar
    el número en todo el mensaje convierte el conteo de personas en evidencia de un requisito
    de propiedad: `"tenemos 2 niños y al menos 3 dormitorios"` trae dimensión, mínimo y un
    `2`, y autorizaría `SetBedroomsMin(2)` — el peor caso del §7, y plausible.

    La guarda de dimensión no lo veía: el texto SÍ habla de dormitorios. Lo que hay que
    exigir es que el número salga de la misma cláusula que la dimensión que va a escribir, y
    que esa cláusula lo afirme en vez de negarlo.
    """
    return any(
        all(p.search(clausula) for p in dimension)
        and any(n == valor for n in _numeros_del_texto(clausula))
        for clausula in _afirmativas(plano)
    )


def _evidencia_budget(mutacion, plano: str) -> bool:
    moneda = _MONEDA_ISO.get(mutacion.currency)
    if moneda is None:
        return False
    return _numero_junto_a_su_dimension(plano, mutacion.amount, _DIM_BUDGET, moneda)


def _evidencia_bedrooms(mutacion, plano: str) -> bool:
    return _numero_junto_a_su_dimension(
        plano, mutacion.bedrooms_min, _DIM_BEDROOMS, _MINIMO)


def _evidencia_area(mutacion, plano: str) -> bool:
    return _numero_junto_a_su_dimension(
        plano, mutacion.area_m2_min, _DIM_AREA, _MINIMO)


def _evidencia_pets(_mutacion, plano: str) -> bool:
    """`SetPetsRequired` no lleva payload, así que "valor exacto" aquí significa que alguna
    cláusula afirmativa exija **que la propiedad admita mascotas** — no que el mensaje
    mencione una mascota y, por separado, pida algo.

    ```
    "necesito que acepten mascotas"        requisito + sustantivo en la MISMA cláusula
    "tengo un perro y deben aceptarlo"     el clítico -lo ya dice a qué se refiere
    "tengo un perro; necesito 2 dormitorios"   dos hechos sin relación → NO
    ```

    El tercero autorizaba: el sustantivo se buscaba en todo el mensaje y bastaba un
    `necesito` suelto en cualquier cláusula sin negación. Pero `necesito` y `deben` son
    genéricos —ahí piden dormitorios— y no vinculan nada con la mascota. Sumar los dos
    fabricaba un requisito que nadie declaró.

    **Límite conocido y no cerrado:** la vía anafórica no comprueba a QUÉ se refiere el
    clítico, así que *"tengo un perro; el banco debe aceptarlo"* pasaría. Resolver el
    referente es interpretación, no gramática cerrada, y no le toca a una guarda. Queda
    anotado en vez de disimulado.
    """
    hay_mascota = bool(_PETS_SUSTANTIVO.search(plano))
    return hay_mascota and any(
        _PETS_ANAFORICO.search(clausula)
        or (_PETS_REQUISITO.search(clausula) and _PETS_SUSTANTIVO.search(clausula))
        for clausula in _afirmativas(plano)
    )


# ── La retractación · lo que autoriza un `Clear*` ──────────────────────────────────

_RETRACCION = re.compile(
    r"\bya no\b|\bquita\b|\bquitar\b|\bquitame\b|\belimina\b|\beliminar\b|"
    r"\bborra\b|\bborrar\b|\bolvida\b|\bolvidar\b|\bdescarta\b|\bdescartar\b")
"""**Un `no` a secas NUNCA es retractación.** §5: *"La negación no es borrado. Es la confusión
que más fácilmente convierte un CLEAR en pérdida silenciosa de estado."* `"no quiero comprar"`
es AMBIGUOUS en esa matriz —¿alquila, o retira el objetivo?—, no un borrado."""

# Vocabulario de dimensión PROPIO de los `Clear*`, separado del de los `Set*` (N4). Motivo
# concreto: "ya no necesito un mínimo de área" no dice `m2` ni `metros cuadrados`, dice
# "área". Meter `area` en el vocabulario de los `Set*` debilitaría esa guarda sin necesidad.
_DIM_BUDGET_CLEAR = re.compile(r"\b(presupuesto|budget|limite|tope|maximo|max)\b")
_DIM_AREA_CLEAR = re.compile(r"(\bm2\b|\bm²|metros? cuadrados?|square meters?|"
                             r"\barea\b|\bsuperficie\b)")


def _retractacion_de(*dimension: re.Pattern):
    """Construye el verificador de un `Clear*`: retractación explícita **Y** su dimensión,
    **en la MISMA cláusula**.

    Es la misma vinculación que exigen los números, y por el mismo motivo. Pedir marcador en
    cualquier parte del mensaje y dimensión en cualquier parte deja que dos afirmaciones sin
    relación se sumen en un borrado:

    ```
    "ya no necesito mascotas; mi presupuesto máximo es 120000 USD"
         ^^^^^ retractación de mascotas      ^^^^^^^^^^^ dimensión budget
                          →  autorizaba ClearBudgetMax
    ```

    El usuario no retiró su presupuesto. Un `Clear` mal vinculado es pérdida silenciosa de un
    campo que sigue vigente, que es exactamente lo que §5 avisa que hay que evitar.

    Aquí NO se filtra por cláusula afirmativa: `"ya no"` **es** una negación, y es la que
    autoriza. Lo que distingue retractación de negación es el marcador, no la polaridad.

    Esta función no recibe estado, así que no demuestra que el campo existiera antes: sólo
    que el texto autoriza la INTENCIÓN de borrar esa dimensión. Que borrar algo vacío sea un
    no-op es del reducer y del store, no de aquí.
    """
    def verificar(_mutacion, plano: str) -> bool:
        return any(_RETRACCION.search(clausula) and all(p.search(clausula) for p in dimension)
                   for clausula in _CLAUSULA.split(plano))

    return verificar


_VERIFICADOR: dict[type, Callable[[object, str], bool]] = {
    SetObjective: _evidencia_objective,
    SetBudgetMax: _evidencia_budget,
    SetBedroomsMin: _evidencia_bedrooms,
    SetAreaM2Min: _evidencia_area,
    SetPetsRequired: _evidencia_pets,
    ClearObjective: _retractacion_de(_DIM_OBJECTIVE),
    ClearBudgetMax: _retractacion_de(_DIM_BUDGET_CLEAR),
    ClearBedroomsMin: _retractacion_de(_DIM_BEDROOMS, _MINIMO),
    ClearAreaM2Min: _retractacion_de(_DIM_AREA_CLEAR, _MINIMO),
    ClearPetsRequired: _retractacion_de(_PETS_SUSTANTIVO),
}
"""**Total sobre `BuyerMutationV0`, y comprobado por meta-test.** Los diez, incluidos los
cinco `Clear*` que antes no tenían entrada y quedaban autorizados por omisión."""


class TraduccionNoAutorizada(Exception):
    """El texto no habla de la dimensión que la mutación quiere escribir.

    No es un error del usuario ni del modelo: es la guarda haciendo su trabajo. El caso que
    la justifica es `"tenemos dos niños"` → `SetBedroomsMin(2)`, donde la mutación es válida
    para el tipo y la inferencia es exactamente la que Fair Housing prohíbe.
    """


def autorizar_traduccion(mutacion, texto: str) -> None:
    """Levanta si el texto no evidencia **exactamente** la mutación propuesta.

    Exactamente quiere decir **local, positiva y del valor**: la evidencia vive en una sola
    cláusula, esa cláusula afirma en vez de negar, y sostiene el valor concreto y no sólo la
    dimensión. `"quiero alquilar"` no autoriza `SetObjective(BUY)` aunque hable
    inequívocamente del objetivo; `"no quiero comprar"` tampoco autoriza `SetObjective(BUY)`
    aunque contenga la palabra. Y un `Clear*` exige retractación explícita de su propia
    dimensión, en su propia cláusula — la negación no basta y el marcador no se presta entre
    afirmaciones vecinas.

    **Fail closed.** Un tipo sin entrada en `_VERIFICADOR` no se autoriza. Antes hacía lo
    contrario —`return` cuando no había vocabulario—, que es como los cinco `Clear*` quedaban
    autorizados por omisión: nadie los había añadido a la tabla, así que pasaban todos.

    Sigue siendo una GUARDA, no un intérprete: recibe una mutación ya propuesta y responde
    sí/no. No decide qué mutación crear, y no resuelve conflictos — si el texto soporta
    `BUY` y `RENT`, autoriza las dos y C1-C3 deciden después. Duplicar aquí esa política
    daría dos copias que se desincronizarían.
    """
    verificador = _VERIFICADOR.get(type(mutacion))
    if verificador is None:
        raise TraduccionNoAutorizada(
            f"{type(mutacion).__name__} no tiene verificador de evidencia: no se autoriza"
        )
    if not verificador(mutacion, _norm(texto)):
        raise TraduccionNoAutorizada(
            f"{type(mutacion).__name__} sin evidencia textual de su valor exacto"
        )


# ── La unión cerrada de afirmaciones ───────────────────────────────────────────────
#
# Discriminada por `disposicion`, igual que `BuyerMutationV0` lo está por `tipo`. Cada
# variante congela qué puede llevar: sólo la durable tiene mutación, sólo la ambigua exige
# dimensión. Lo que no está en la variante no se rechaza — no se puede escribir.


class _Afirmacion(BaseModel):
    """Lo común a las cuatro. `motivo` es obligatorio y no vacío en todas: una decisión de
    routing sin razón registrada es una decisión que nadie puede revisar después."""

    model_config = _CERRADO

    motivo: str = Field(min_length=1)


class AfirmacionDurable(_Afirmacion):
    """Un hecho que SÍ debe volverse estado durable del comprador.

    `campo` es una **property, no un campo de entrada**: se deriva de la mutación por
    `campo_de_mutacion`. Dejarlo entrar como dato permitiría declarar una dimensión distinta
    de la de la mutación, y entonces la resolución intramensaje agruparía por algo que el
    llamante eligió — justo la superficie que `BuyerFieldV0` cierra.
    """

    disposicion: Literal[Disposicion.DURABLE] = Disposicion.DURABLE
    mutacion: BuyerMutationV0

    @property
    def campo(self) -> BuyerFieldV0:
        return campo_de_mutacion(self.mutacion)


class AfirmacionAmbiguous(_Afirmacion):
    """Podría ser durable, pero falta información o la semántica no es exacta.

    **`campo` es OBLIGATORIO, y ahí está la corrección de E3.2b.1a.** Una ambigüedad sin
    dimensión no puede competir con la declaración durable que viene a invalidar: es lo que
    hacía que `"máximo 120000 USD… no, 100000"` conservara los 120000.
    """

    disposicion: Literal[Disposicion.AMBIGUOUS] = Disposicion.AMBIGUOUS
    campo: BuyerFieldV0


class AfirmacionTurnOnly(_Afirmacion):
    """Útil en este turno; no es una preferencia. Preguntar, explorar, comparar.

    `campo` es opcional porque una pregunta puede nombrar una dimensión —*"¿hay de 2
    dormitorios?"*— o ninguna —*"¿qué tan caminable es el barrio?"*—. Nombrarla no la
    declara, y por eso un TURN_ONLY nunca compite (ver `_declara`).
    """

    disposicion: Literal[Disposicion.TURN_ONLY] = Disposicion.TURN_ONLY
    campo: BuyerFieldV0 | None = None


class AfirmacionRejected(_Afirmacion):
    """Intenta producir estado fuera de la frontera. **No significa "mensaje inválido"**: el
    producto responde igual, sólo que esto no se escribe.

    `campo` es opcional: *"algo tranquilo"* no toca ninguna de las cinco dimensiones, mientras
    que *"no quiero mascotas"* sí toca `PETS_REQUIRED` aunque V0 no pueda representarlo.
    """

    disposicion: Literal[Disposicion.REJECTED] = Disposicion.REJECTED
    campo: BuyerFieldV0 | None = None


AfirmacionV0 = Annotated[
    Union[AfirmacionDurable, AfirmacionAmbiguous, AfirmacionTurnOnly, AfirmacionRejected],
    Field(discriminator="disposicion"),
]
"""La unión CERRADA de afirmaciones. Sólo la durable lleva mutación; sólo la ambigua exige
campo. No hay una quinta forma, y ninguna acepta lo que no le corresponde."""


class LoteExtraccion(BaseModel):
    """Lo que un mensaje produce. **Ordenado y con una sola mutación durable por CAMPO.**

    El orden importa porque sin él no se puede describir *"dijo A y luego B"*. La unicidad por
    campo importa más: si llegaran dos mutaciones de la misma dimensión sin resolver, el
    reducer las aplicaría en orden y **ganaría la última** — que es un *last-write-wins*
    dentro del mensaje, exactamente la política que C1 prohíbe.

    **Por campo semántico y no por ruta contractual.** Las dos van hoy en paralelo sobre la
    misma unión, pero la invariante que se quiere es *"una declaración por dimensión del
    comprador"*; agrupar por el path del contrato la dejaría dependiendo de que dos
    dimensiones nunca compartan destino.

    Por eso el lote **no se puede construir** en ese estado. Es un fallo del extractor, no
    algo que el reducer deba arreglar.
    """

    model_config = _CERRADO

    source_message_id: str = Field(min_length=1)
    afirmaciones: tuple[AfirmacionV0, ...] = ()

    @model_validator(mode="after")
    def _una_durable_por_campo(self) -> LoteExtraccion:
        campos = [a.campo for a in self.afirmaciones if isinstance(a, AfirmacionDurable)]
        repetidos = {c for c in campos if campos.count(c) > 1}
        if repetidos:
            raise ValueError(
                f"dos mutaciones durables para {sorted(repetidos)}: el conflicto se resuelve "
                f"en el extractor (C4), no dejando que el orden decida"
            )
        return self

    @property
    def mutaciones(self) -> tuple:
        """Solo las durables, en orden. Es lo que consumirá el reducer de E3.2b.2."""
        return tuple(a.mutacion for a in self.afirmaciones
                     if isinstance(a, AfirmacionDurable))


# ── C1-C5 · la política intramensaje ───────────────────────────────────────────────

# OJO con el `\b` final: las alternativas que acaban en signo de puntuación —`no,`— nunca
# casarían, porque tras la coma viene un espacio y ahí no hay frontera de palabra. Van en su
# propia rama. Lo destapó el primer smoke test: "quiero comprar... no, alquilar" daba
# `corr=False` y la corrección se perdía en silencio.
_CORRECCION = re.compile(
    r"\bno[,.]|"
    r"\b(mejor|en realidad|realmente|perdon|perdona|disculpa|"
    r"me equivoque|corrijo|actually|rather)\b")


def hay_autocorreccion(texto: str) -> bool:
    """¿El mensaje marca EXPLÍCITAMENTE que se está corrigiendo?

    Sin marca explícita, dos declaraciones incompatibles son ambigüedad, no corrección (C3).
    Tratarlas como corrección sería adivinar cuál quiso decir — y adivinar en la dirección de
    "la última" es el *last-write-wins* que C1 prohíbe.

    **No hay guarda de disyunción, y no falta.** Delante de este `return` hubo un
    `if _DISYUNCION.search(p) and not _CORRECCION.search(p): return False`: era **redundante,
    sin comportamiento observable distinto** —ningún input separa las dos versiones— así que
    se eliminó en vez de fabricarle un test. Que *"comprar o alquilar"* dé `False` lo produce
    este `return` solo, porque la disyunción no lleva marca de corrección.
    """
    return bool(_CORRECCION.search(_norm(texto)))


def _declara(afirmacion) -> bool:
    """¿Esta afirmación DECLARA un valor para su dimensión, o sólo la menciona?

    Declaran la durable —lo consiguió— y la ambigua —lo intentó y no llegó—. Son las "dos
    declaraciones incompatibles sobre la misma dimensión" de C2/C3, y son las únicas que
    compiten.

    TURN_ONLY y REJECTED **no**, ni siquiera llevando campo. §4 define TURN_ONLY como
    pregunta o exploración, y una pregunta sobre el presupuesto no retira el presupuesto; C5
    dice que un REJECTED no elimina mutaciones durables. Dejarlos competir haría que
    *"máximo 120000 USD, ¿y cuánto suele costar aquí?"* borrara el presupuesto en silencio.

    **Es una decisión de esta unidad, no algo que C1-C5 dejara escrito**: las cinco reglas
    hablan de declaraciones y no dicen qué hacer con un TURN_ONLY o un REJECTED que llevan
    campo. Se resuelve en la dirección de no perder una declaración explícita del usuario.
    """
    return isinstance(afirmacion, (AfirmacionDurable, AfirmacionAmbiguous))


def _valor_declarado(afirmacion):
    """Qué se declaró, para saber si dos declaraciones son la misma o chocan.

    La ambigua devuelve `None` a propósito: *no llegó a haber valor*. Así una durable y una
    ambigua del mismo campo siempre cuentan como distintas —el caso de la corrección
    incompleta— y dos ambiguas del mismo campo se deduplican como cualquier repetición.
    """
    return afirmacion.mutacion if isinstance(afirmacion, AfirmacionDurable) else None


def _resolver_campo(campo, grupo, texto):
    """Colapsa las declaraciones que compiten por UNA dimensión. Devuelve `(índice, afirmación)`.

    ```
    A · misma dimensión, misma declaración      → deduplica, en la posición de la PRIMERA
    B · distintas + autocorrección explícita    → la declaración FINAL
    C · durable previa + ambigua + corrección   → sólo la ambigua (es B con final ambigua)
    D · distintas sin autocorrección            → AMBIGUOUS(campo), CERO durables
    ```

    B y C son la misma rama, y es deliberado: *"la corrección SELECCIONA una declaración"* no
    dice que la seleccionada tenga que ser válida. `"máximo 120000 USD… no, 100000"` selecciona
    una segunda declaración que nunca llegó a ser mutación, así que el resultado es la ambigua
    — **ni hereda la moneda de la primera ni deja sobrevivir a la primera.**

    Las que no declaran (TURN_ONLY, REJECTED) se devuelven intactas y en su sitio.
    """
    declaraciones = [par for par in grupo if _declara(par[1])]
    acompanantes = [par for par in grupo if not _declara(par[1])]

    if not declaraciones:
        return acompanantes
    if len(declaraciones) == 1:
        return acompanantes + declaraciones

    if len({_valor_declarado(a) for _, a in declaraciones}) == 1:      # A · repetición
        return acompanantes + [declaraciones[0]]
    if hay_autocorreccion(texto):                                     # B/C · la final
        return acompanantes + [declaraciones[-1]]

    indice_ultimo = declaraciones[-1][0]                              # D · conflicto
    return acompanantes + [(indice_ultimo, AfirmacionAmbiguous(
        campo=campo,
        motivo=f"dos declaraciones incompatibles para {campo} sin corrección explícita"))]


def resolver_intramensaje(afirmaciones, texto: str) -> tuple:
    """Colapsa las afirmaciones que compiten por la misma DIMENSIÓN. C1-C5.

    **Se agrupa por `BuyerFieldV0`, no por la presencia de mutación.** Ésa era la avería: la
    dimensión se derivaba de la mutación, así que una ambigüedad quedaba sin campo y no
    competía con nada.

    **El orden es el de aparición, y se conserva por construcción.** Se trabaja con
    `(índice_original, afirmación)` y se ordena por índice al final, así que las tres reglas
    congeladas salen solas y sin casos especiales:

    ```
    duplicado                 → índice del primero
    autocorrección            → índice del último
    conflicto → AMBIGUOUS     → índice del último
    ```

    C5: lo que no compite por esa dimensión **no se toca**. Un `REJECTED` no arrastra hechos
    independientes del mismo mensaje, y una afirmación sin campo no compite con nada.
    """
    por_campo: dict[BuyerFieldV0, list] = {}
    sin_campo: list = []
    for indice, afirmacion in enumerate(afirmaciones):
        if afirmacion.campo is None:
            sin_campo.append((indice, afirmacion))
        else:
            por_campo.setdefault(afirmacion.campo, []).append((indice, afirmacion))

    resueltas = list(sin_campo)
    for campo, grupo in por_campo.items():
        resueltas.extend(_resolver_campo(campo, grupo, texto))

    return tuple(a for _, a in sorted(resueltas, key=lambda par: par[0]))


def construir_lote(mensaje, afirmaciones) -> LoteExtraccion:
    """El lote final: se resuelve el conflicto intramensaje ANTES de construirlo.

    El `source_message_id` sale del mensaje tal cual. **No se fabrica ni se deriva**: es lo
    que la procedencia de E3.2b.2 podrá citar, y un id sintético dejaría de apuntar a un
    `HumanMessage` que existe.
    """
    return LoteExtraccion(
        source_message_id=mensaje.message_id,
        afirmaciones=resolver_intramensaje(afirmaciones, mensaje.text),
    )
