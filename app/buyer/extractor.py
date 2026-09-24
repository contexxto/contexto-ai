"""E3.2b.1 · Extractor + routing situacional — la capa determinista.

Decide, para **un** `IdentifiedUserMessage`, qué de lo que se afirmó es estado durable del
comprador, qué es contexto del turno, qué es ambiguo y qué no debe crear estado — y lo
devuelve como un lote ordenado.

**Este módulo no lee el texto para producir las afirmaciones**, y la distinción sigue
importando aunque el intérprete ya exista: `construir_lote` las recibe ya construidas de su
llamante y usa el texto sólo para detectar autocorrección. Quien convierte `text → Afirmacion`
es `app/buyer/interprete.py` (E3.2b.1b); aquí vive la GUARDA y la política intramensaje.

Mantener la frontera es lo que permite que la guarda se pruebe sin modelo y que el intérprete
no pueda saltársela.

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
cuatro formas de relajarla aparecieron por separado.

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

**DEL TIPO DE LA MUTACIÓN.** El predicado tiene que significar lo que la mutación afirma, no
sólo caer cerca de su vocabulario. `SetPetsRequired` admitía verbos genéricos de requisito, y
`"necesito un veterinario cerca para mi perro"` cumplía LOCAL, POSITIVA y VINCULADA sin
afirmar en ningún momento que la propiedad admita mascotas. *Predicado relacionado con una
mascota* no es *predicado de admisión de mascotas*.

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
    CampoConCriterioV0,
    ClearAreaM2Min,
    ClearBedroomsMin,
    ClearBudgetMax,
    ClearObjective,
    ClearPetsRequired,
    DeclaracionRigidezV0,
    Disposicion,
    RigidezV0,
    SetAreaM2Min,
    SetBedroomsMin,
    SetBudgetMax,
    SetObjective,
    SetPetsRequired,
    campo_de_mutacion,
)
from app.config import settings
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

# PREDICADO DE ADMISIÓN, y solo eso. Cada alternativa significa *admitir* por sí misma, en
# cualquier contexto. No hay verbos genéricos de requisito —`necesito`, `debe`, `tiene que`—
# y su ausencia es la propiedad, no un olvido: con ellos, cualquier cláusula que pidiera algo
# y nombrara un animal evidenciaba que la propiedad admite mascotas. "Necesito un veterinario
# cerca para mi perro" pide un veterinario.
#
#     predicado RELACIONADO con una mascota   ≠   predicado DE ADMISIÓN de mascotas
#
# `required` se retiró con ellos: "pets required" diría que la propiedad EXIGE mascotas, que
# no es lo que `SetPetsRequired` afirma. `allowed` sí se queda — "pets allowed" es admisión
# inequívoca — y tiene su caso en la sección K.
#
# Los infinitivos están porque hacen falta: `"el edificio debe permitir perros"` pasaba por
# `debe`, no por `permitir`, que ni siquiera figuraba. Era un test verde por la razón
# equivocada.
#
# Las formas con clítico —`aceptarlo`— NO casan: `\baceptar\b` exige frontera de palabra y en
# "aceptarlo" viene una letra. Es deliberado; ver `_evidencia_pets`.
_PETS_ADMISION = re.compile(
    r"\b(acepta|acepte|acepten|aceptan|aceptar|"
    r"admite|admita|admitan|admiten|admitir|"
    r"permite|permita|permitan|permiten|permitir|"
    r"allow|allows|allowed)\b")


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
"""**El código ISO literal, que acredita SIEMPRE y sin depender del mercado.** El símbolo `$`
no resuelve USD y `pesos` no implica MXN: las dos siguen congeladas como AMBIGUOUS en la
matriz del §4."""

_DENOMINACION_DE_MERCADO: dict[BuyerCurrencyV0, re.Pattern] = {
    BuyerCurrencyV0.USD: re.compile(r"\b(dolar|dolares)\b"),
}
"""G16 · cómo se nombra cada moneda en habla natural. **Sólo acredita si el mercado del
despliegue declara esa misma moneda.**

`dolares` sin contexto seguiría siendo ambiguo —hay ocho dólares en el mundo, y ése era el
argumento original de esta guarda—. Lo que cambió es que ahora existe un contexto
determinista que puede resolverlo: `BUYER_MARKET_CURRENCY`. En un despliegue que declara
USD, "900 dólares" no es ambiguo; en uno que no declara nada, lo sigue siendo.

MXN no está aquí a propósito: "pesos" nombra a más de una moneda de la región y no fue el
fallo observado. Añadirlo exige su propia evidencia, no una simetría estética."""


def _patron_de_moneda(currency: BuyerCurrencyV0) -> re.Pattern | None:
    """El patrón que acredita ESTA moneda, dado el mercado del despliegue.

    La correspondencia se exige entre las TRES: la moneda que propone la mutación, la
    denominación que aparece en el texto y la que declara el mercado. Por eso el mercado no
    puede acreditar una mutación en otra moneda —comparar `settings` con `currency` es lo que
    lo impide— ni convertir `"900 euros"` en dólares, porque `euros` no está en ningún patrón.

    **El mercado CONFIRMA, no ORIGINA.** Sin denominación en el texto no hay nada que
    confirmar: el número desnudo no se acredita por mucho mercado que haya declarado, y ésa es
    la propiedad que separa esto de fabricar un dato que la persona no dijo.
    """
    iso = _MONEDA_ISO.get(currency)
    if iso is None:
        return None
    if (getattr(settings, "buyer_market_currency", "") or "") != currency.value:
        return iso
    natural = _DENOMINACION_DE_MERCADO.get(currency)
    return iso if natural is None else re.compile(f"(?:{iso.pattern}|{natural.pattern})")

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


# Cláusulas. Son la unidad en la que tiene que caber TODA la evidencia de una mutación:
# acotan el alcance de una negación —"no tengo mascotas, pero quiero comprar" declara la
# compra—, el de un número y el de un marcador de retractación. Nada se presta entre
# cláusulas vecinas; ahí es donde se colaban las autorizaciones falsas.
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
    moneda = _patron_de_moneda(mutacion.currency)
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
    """`SetPetsRequired` no lleva payload, así que "valor exacto" aquí significa que **una
    misma cláusula afirmativa** exija que la propiedad admita mascotas.

    ```
    "necesito que acepten mascotas"             admisión + sustantivo juntos    →  SÍ
    "busco algo que admita gatos"               idem                            →  SÍ
    "el edificio debe permitir perros"          por `permitir`, no por `debe`   →  SÍ
    "necesito un veterinario para mi perro"     pide un veterinario             →  NO
    "tengo un perro; necesito 2 dormitorios"    dos hechos sin relación         →  NO
    "tengo un perro; el banco debe aceptarlo"   el clítico no dice a qué refiere→  NO
    "tengo un perro y deben aceptarlo"          tampoco, y es deliberado        →  NO
    ```

    El predicado tiene que ser **de admisión**, no un requisito cualquiera que caiga cerca de
    un animal. Es el cuarto término de "evidencia exacta", el que estaba implícito y no
    garantizado: la evidencia ha de ser LOCAL, POSITIVA, VINCULADA **y semánticamente del tipo
    de la mutación**.

    Una regla, sin excepciones — y la última línea es una decisión REVERTIDA. Hubo una vía
    anafórica que aceptaba el clítico de objeto (`aceptarlo`) con el sustantivo en otra
    cláusula, para no perder ese caso. Tendía un puente que la gramática no puede sostener:
    `-lo` no dice a qué refiere, así que *"el banco debe aceptarlo"* servía de evidencia de un
    requisito de mascotas porque en otra frase había un perro.

    **Fail closed, y ése es el punto.** Precisamente porque resolver el referente no le toca a
    la guarda, tampoco le toca darlo por supuesto:

    ```
    no puedo verificar la coreferencia   →   NO autorizo
    ```

    Una guarda de autorización tolera falsos negativos antes que falsos positivos. Que
    *"tengo un perro y deben aceptarlo"* no autorice no dice que el usuario no lo quisiera
    decir: dice que esto no puede probarlo. El intérprete podrá clasificarlo AMBIGUOUS, que
    es donde vive lo que se entiende pero no se puede acreditar.
    """
    return any(_PETS_ADMISION.search(clausula) and _PETS_SUSTANTIVO.search(clausula)
               for clausula in _afirmativas(plano))


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


# ── E3.3 · la guarda de RIGIDEZ — ASIMÉTRICA, y para ESTRICTA sobre el MENSAJE entero ──
#
# La misma exigencia que las mutaciones, aplicada a otra afirmación: que la persona dijo que
# ESE requisito es indispensable —o flexible— y no que el modelo lo dedujo.
#
# **Las dos direcciones no cuestan lo mismo, y la guarda ya no finge que sí.**
#
#     ESTRICTA  un falso positivo DESCALIFICA inmuebles que la persona aceptaba   → caro
#     FLEXIBLE  un falso positivo sólo deja de excluir: ordena en vez de filtrar  → barato
#               un falso NEGATIVO deja dura una restricción que ella relajó        → caro
#
# ESTRICTA — COBERTURA TOTAL. Tres revisiones adversariales seguidas mostraron que ninguna
# frontera local —cláusula, oración— aguanta: el desmentido llega en la cláusula de al lado,
# tras una «y», tras unos puntos suspensivos o en la línea siguiente («…o no?», «Es broma
# jaja», «Para mí no.»). Así que ESTRICTA se acredita sólo si **TODAS** las cláusulas del
# mensaje son algo que la guarda reconoce:
#
#     la declaración canónica      «el presupuesto es innegociable» (requisito como SUJETO)
#     un valor acreditado          «máximo 900 USD», «busco alquilar» — una durable del mensaje
#     el marcador pegado al valor  «al menos 2 dormitorios sí o sí», «máximo 900 USD, es
#                                  innegociable» — justo tras la unidad o el sustantivo
#     otra declaración canónica    «los dormitorios son flexibles»
#     cortesía                     «hola», «gracias»; y una partícula SÓLO al principio
#
# y no hay «?» ni «¿» en ninguna parte. Lo que no encaja en nada —«jaja», «para mí no», un
# emoji, «olvida eso»— deja el mensaje sin ESTRICTA. Es una lista BLANCA sobre el mensaje
# entero: no depende de haber previsto la palabra con la que alguien se desdice.
#
# FLEXIBLE — local y permisiva: la cláusula nombra la dimensión y trae el marcador sin una
# negación que lo invierta; o, si el mensaje sólo nombra ESA dimensión, una cláusula que es
# sólo el marcador («…no, perdón, es flexible.»).

_MARCADOR_ESTRICTO = (r"(?:indispensables?|imprescindibles?|innegociables?|no (?:es |son )?negociables?|"
                      r"obligatori[oa]s?|excluyentes?|si o si|sin excepcion(?:es)?)")
_MARCA_ESTRICTA = re.compile(rf"\b{_MARCADOR_ESTRICTO}\b")

_MARCADOR_FLEXIBLE_R = (
    r"(?:flexibles?|negociables?|idealmente|lo ideal|de preferencia|preferiblemente|"
    r"preferentemente|si se puede|si es posible|hay margen|con margen|me puedo estirar|"
    r"puedo estirarme|podemos estirarnos|"
    r"(?:ya )?no (?:es|son) (?:indispensables?|imprescindibles?|innegociables?|"
    r"obligatori[oa]s?|excluyentes?))")
_MARCADOR_FLEXIBLE = re.compile(rf"\b{_MARCADOR_FLEXIBLE_R}\b")
"""`ideal` suelto no está: *"mi casa ideal"* describe el inmueble. *"Ya no es innegociable"*
SÍ es flexibilidad declarada."""

_NIEGA_FLEXIBLE = re.compile(
    r"\b(?:no|ni|nunca|jamas|tampoco|nada|poco|cero|apenas|sin)\b|\bsi\b(?!\s+(?:es|son)\b)")
"""Lo que, en SU cláusula, invierte o suspende un marcador de flexibilidad: la negación («no
es flexible», «cero negociable», «poco flexible») y el «si» condicional («quería saber si es
negociable»). El «sí» enfático va pegado a la cópula y no bloquea; el subjuntivo sólo, tampoco:
«prefiero que el presupuesto sea flexible» es una corrección, y «no creo que sea…» ya cae por
el «no»."""

_LOCUCION_NEUTRA = re.compile(r"\bsin (?:duda|problema|problemas)\b")
_SUBJUNTIVO = re.compile(r"\b(?:sea|sean|fuera|fueran|fuese|fuesen)\b")
_VOLITIVO = re.compile(r"\b(?:prefiero|preferimos|quiero|queremos|mejor|ojala)\b")
"""El subjuntivo es la huella de una subordinada. Sin un verbo de preferencia en la cláusula
—«prefiero que sea flexible»—, lo más probable es que cuelgue de un «no creo» que quedó al otro
lado de la coma, y hacia flexible eso sería relajar lo que la persona dijo que no era
flexible."""

_DIM_RIGIDEZ: dict[BuyerFieldV0, re.Pattern] = {
    BuyerFieldV0.BUDGET_MAX: re.compile(r"\b(presupuesto|budget)\b"),
    BuyerFieldV0.BEDROOMS_MIN: re.compile(
        r"\b(dormitorios?|habitaciones|cuartos|recamaras|bedrooms?)\b"),
    BuyerFieldV0.AREA_M2_MIN: re.compile(
        r"(\bm2\b|\bm²|metros? cuadrados?|\bsuperficie\b|square meters?)"),
    BuyerFieldV0.PETS_REQUIRED: _PETS_SUSTANTIVO,
}
"""Qué NOMBRA una dimensión para FLEXIBLE. `máximo`, `tope`, `cuarto` y `área` sueltos
cuantifican cualquier cosa. `precio` tampoco: *"el precio es negociable"* habla del inmueble."""

_SUJETO_CANONICO: dict[BuyerFieldV0, str] = {
    BuyerFieldV0.BUDGET_MAX: r"(?:el |mi |nuestro |lo del )?(?:tope de presupuesto|presupuesto maximo|presupuesto)",
    BuyerFieldV0.BEDROOMS_MIN: r"(?:los |las |mis |el numero de |la cantidad de |lo de los |lo de las )?(?:dormitorios|habitaciones|recamaras|cuartos)",
    BuyerFieldV0.AREA_M2_MIN: r"(?:el |la |los |lo del |lo de la |lo de los )?(?:area minima|area total|superficie|metraje|metros cuadrados)",
    BuyerFieldV0.PETS_REQUIRED: r"(?:que (?:acepten|admitan|permitan) (?:mascotas|perros|gatos)|(?:lo de )?(?:las |los |mis )?(?:mascotas|perros|gatos))",
}
"""El SUJETO de la forma canónica. «El área» sola NO: en español es también la zona, el
sector. «El área mínima», «la superficie» o «los metros cuadrados» sí son el requisito."""

_ANCLA_DEL_VALOR: dict[BuyerFieldV0, str] = {
    BuyerFieldV0.BUDGET_MAX: r"(?:usd|dolares|mxn|pesos|presupuesto)",
    BuyerFieldV0.BEDROOMS_MIN: r"(?:dormitorios?|habitacion(?:es)?|cuartos?|recamaras?)",
    BuyerFieldV0.AREA_M2_MIN: r"(?:m2|m²|metros cuadrados?)",
    BuyerFieldV0.PETS_REQUIRED: r"(?:mascotas?|perros?|gatos?)",
}
"""Con qué tiene que terminar el valor para que un marcador pegado a él hable DE ÉL:
«al menos 2 dormitorios sí o sí» sí; «al menos 2 dormitorios con baño privado indispensable»
no —el marcador modifica al baño—."""

_COPULA = r"(?:es|son|tiene que ser|tienen que ser|debe ser|deben ser|va a ser|van a ser)"
_RELLENO_ESTRICTO = (r"(?:muy|totalmente|completamente|absolutamente|realmente|"
                     r"definitivamente|para mi|para nosotros|un requisito|requisito|algo|eso|esto)")


def _canonica(campo: BuyerFieldV0, marcador: str) -> re.Pattern:
    r = _RELLENO_ESTRICTO
    return re.compile(
        rf"^(?:{r}\s+)*{_SUJETO_CANONICO[campo]}(?:\s+{_COPULA})?"
        rf"(?:\s+{r})*\s+{marcador}(?:\s+{r})*$")


_CANONICA: dict[BuyerFieldV0, re.Pattern] = {
    c: _canonica(c, _MARCADOR_ESTRICTO) for c in _SUJETO_CANONICO}
_CANONICA_FLEXIBLE: dict[BuyerFieldV0, re.Pattern] = {
    c: _canonica(c, _MARCADOR_FLEXIBLE_R) for c in _SUJETO_CANONICO}

_CORTESIA = re.compile(r"^(?:hola|buenas|buenos dias|buenas tardes|buenas noches|gracias|"
                       r"muchas gracias|mil gracias|saludos)$")
_PARTICULA_INICIAL = re.compile(r"^(?:si|no|bueno|ok|claro|vale|mira|oye|ojo)$")

_CORTE_ESTRICTO = re.compile(
    r"(?<!\d)[.;:]|[.;:](?!\d)|[!\n…]|(?<!\d),|,(?!\d)|\by\b|\bpero\b|\baunque\b")
_RELLENO = frozenset({
    "es", "son", "sera", "eso", "esto", "muy", "totalmente", "completamente", "absolutamente",
    "para", "mi", "requisito", "un", "algo",
})


def _clausulas_estrictas(plano: str) -> list[str]:
    return [c.strip() for c in _CORTE_ESTRICTO.split(plano) if c.strip()]


def _solo_marcador(clausula: str) -> bool:
    return bool(_MARCA_ESTRICTA.search(clausula)) and set(
        _MARCA_ESTRICTA.sub(" ", clausula).split()) <= _RELLENO


_VOCABULARIO_DE_VALOR = frozenset("""
    mi mis el la los las un una unos unas de del al a en con para por que o es son
    busco buscamos quiero queremos necesito necesitamos tengo tenemos prefiero preferimos me nos
    ahora mejor entonces pues tambien ademas solo como minimo min maximo max hasta tope limite
    menos mas adelante desde presupuesto budget
    comprar compra compro adquirir adquiero alquilar alquilo arrendar arriendo rentar rento
    invertir invierto inversion buy purchase rent invest casa departamento depa inmueble
    propiedad vivienda
    usd dolar dolares mxn pesos
    dormitorio dormitorios habitacion habitaciones cuarto cuartos recamara recamaras
    m2 m² metros metro cuadrados cuadrado superficie area
    mascota mascotas perro perros gato gatos pet pets acepte acepten admita admitan permita
    permitan aceptan admiten permiten allow allows allowed
    ya no quita quitar quitame elimina eliminar borra borrar olvida olvidar descarta descartar
""".split())
"""Qué palabras puede traer una cláusula de VALOR para contar como parte reconocida del
mensaje. El verificador de cada mutación es permisivo con lo que rodea al valor —su trabajo es
otro—, así que «mi esposo dice que máximo 900 USD» lo acredita igual. Para la cobertura de
ESTRICTA no basta: la cláusula tiene que ser SÓLO valor. Otra lista blanca, no una negra."""


def _solo_vocabulario_de_valor(clausula: str) -> bool:
    return all(t in _VOCABULARIO_DE_VALOR or t.replace(".", "").replace(",", "").isdigit()
               for t in clausula.split())


def _es_valor(clausula: str, valores) -> list:
    """Las durables del mensaje que ESTA cláusula acredita por sí sola, y sin nada más."""
    if not _solo_vocabulario_de_valor(clausula):
        return []
    return [m for m in valores if _VERIFICADOR[type(m)](m, clausula)]


def _valor_de(clausula: str, campo: BuyerFieldV0, valores) -> bool:
    """¿La cláusula es un valor de ESE campo que termina en su ancla?"""
    return any(campo_de_mutacion(m) is campo for m in _es_valor(clausula, valores)) and bool(
        re.search(rf"\b{_ANCLA_DEL_VALOR[campo]}\s*$", clausula))


def _acredita_estricta(campo: BuyerFieldV0, plano: str, valores) -> bool:
    if "?" in plano or "¿" in plano:
        return False
    clausulas = _clausulas_estrictas(plano)
    declara = False
    for i, c in enumerate(clausulas):
        if _CANONICA[campo].match(c):
            declara = True
            continue
        final = re.search(rf"\s+{_MARCADOR_ESTRICTO}$", c)
        if final and _valor_de(c[:final.start()].strip(), campo, valores):
            declara = True                                   # «al menos 2 dormitorios sí o sí»
            continue
        if _solo_marcador(c) and i > 0 and _valor_de(clausulas[i - 1], campo, valores):
            declara = True                                   # «máximo 900 USD, es innegociable»
            continue
        if (_es_valor(c, valores) or _CORTESIA.match(c)
                or any(p.match(c) for p in _CANONICA.values())
                or any(p.match(c) for p in _CANONICA_FLEXIBLE.values())
                or (i == 0 and _PARTICULA_INICIAL.match(c))):
            continue
        return False                                         # algo que no se reconoce
    return declara


# ── FLEXIBLE ──

_CORTE_FLEXIBLE = re.compile(r"(?<!\d)[.;:]|[.;:](?!\d)|[!\n…]|(?<!\d),|,(?!\d)|\bpero\b|\baunque\b")
"""Sin «y»: «el presupuesto y los metros cuadrados son flexibles» relaja las dos."""

_RELLENO_FLEXIBLE = frozenset({
    "es", "son", "sera", "mas", "bien", "bastante", "muy", "algo", "totalmente", "realmente",
    "mejor", "entonces", "pues", "eso", "lo", "igual", "tambien", "que",
})


def _clausulas_declarativas(plano: str) -> list[str]:
    """Las cláusulas que no preguntan. Se descarta la CLÁUSULA con «?» o «¿», no la oración:
    «el presupuesto es flexible, ¿tienen algo en Cumbayá?» sigue relajando el presupuesto."""
    return [c.strip() for c in _CORTE_FLEXIBLE.split(plano)
            if c.strip() and "?" not in c and "¿" not in c]


def _flexible_en(clausula: str) -> bool:
    limpia = _LOCUCION_NEUTRA.sub(" ", clausula)
    if not _MARCADOR_FLEXIBLE.search(limpia):
        return False
    resto = _MARCADOR_FLEXIBLE.sub(" ", limpia)
    if _SUBJUNTIVO.search(resto) and not _VOLITIVO.search(resto):
        return False          # «que el presupuesto sea flexible» colgando de un «no creo»
    return not _MARCA_ESTRICTA.search(resto) and not _NIEGA_FLEXIBLE.search(resto)


_MENCIONA: dict[BuyerFieldV0, tuple[re.Pattern, ...]] = {
    BuyerFieldV0.BUDGET_MAX: (_DIM_RIGIDEZ[BuyerFieldV0.BUDGET_MAX], _DIM_BUDGET,
                              re.compile(r"\b(usd|mxn|dolares|pesos)\b")),
    BuyerFieldV0.BEDROOMS_MIN: (_DIM_RIGIDEZ[BuyerFieldV0.BEDROOMS_MIN], _DIM_BEDROOMS),
    BuyerFieldV0.AREA_M2_MIN: (_DIM_RIGIDEZ[BuyerFieldV0.AREA_M2_MIN], _DIM_AREA,
                               re.compile(r"\barea\b")),
    BuyerFieldV0.PETS_REQUIRED: (_PETS_SUSTANTIVO,),
}
"""Para la anáfora hacia flexible basta con que el mensaje MENCIONE la dimensión, también por
su valor: «mínimo 80 m2, idealmente» habla del área aunque no diga «superficie»."""


def _dimensiones_nombradas(plano: str) -> set[BuyerFieldV0]:
    return {c for c, ps in _MENCIONA.items() if any(p.search(plano) for p in ps)}


def _acredita_flexible(campo: BuyerFieldV0, plano: str) -> bool:
    clausulas = _clausulas_declarativas(plano)
    if any(_DIM_RIGIDEZ[campo].search(c) and _flexible_en(c) for c in clausulas):
        return True
    # Anáfora, sólo hacia flexible: el mensaje nombra ESTA dimensión y ninguna otra, y una
    # cláusula es sólo el marcador. Equivocarse aquí deja de excluir; no excluye.
    if _dimensiones_nombradas(plano) != {campo}:
        return False
    return any(_flexible_en(c) and set(_MARCADOR_FLEXIBLE.sub(" ", c).split()) <= _RELLENO_FLEXIBLE
               for c in clausulas)


def autorizar_rigidez(declaracion: DeclaracionRigidezV0, texto: str, valores=()) -> None:
    """Levanta si el texto no declara **exactamente** esa rigidez para esa dimensión.

    `valores` son las durables ACREDITADAS del mensaje (de cualquier dimensión): son lo que
    permite a ESTRICTA reconocer «máximo 900 USD» como parte de una declaración y no como
    algo desconocido. Sin ellas, sólo la forma canónica y la cortesía cubren el mensaje.

    **Fail closed.** Una dimensión fuera de la whitelist no se autoriza.
    """
    campo = declaracion.campo
    if campo not in _CANONICA:
        raise TraduccionNoAutorizada(f"rigidez sobre {campo}: no es una dimensión con criterio")
    plano = _norm(texto)
    acreditada = (_acredita_flexible(campo, plano)
                  if declaracion.rigidez is RigidezV0.FLEXIBLE
                  else _acredita_estricta(campo, plano, tuple(valores)))
    if not acreditada:
        raise TraduccionNoAutorizada(
            f"rigidez {declaracion.rigidez.value} de {campo.value} sin evidencia textual "
            f"explícita que cubra el mensaje")


def autorizar_rigidez_por_adyacencia(declaracion: DeclaracionRigidezV0, mutacion,
                                     texto: str) -> None:
    """ESTRICTA pegada a UN valor. Se conserva como atajo: es `autorizar_rigidez` con esa sola
    durable, así que cualquier otra cláusula del mensaje tiene que ser reconocible igual."""
    if declaracion.rigidez is not RigidezV0.ESTRICTA:
        raise TraduccionNoAutorizada("el puente sólo existe para ESTRICTA")
    if campo_de_mutacion(mutacion) is not declaracion.campo:
        raise TraduccionNoAutorizada("el valor y la rigidez son de dimensiones distintas")
    if not isinstance(mutacion, (SetBudgetMax, SetBedroomsMin, SetAreaM2Min, SetPetsRequired)):
        raise TraduccionNoAutorizada("el puente sólo se apoya en un valor declarado")
    autorizar_rigidez(declaracion, texto, valores=(mutacion,))


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

    rigideces: tuple[DeclaracionRigidezV0, ...] = ()
    """E3.3 · las rigideces ACREDITADAS del mensaje, como mucho una por dimensión.

    Van aparte de `afirmaciones` porque no compiten con ellas: *"máximo 900 USD, y es
    innegociable"* declara un valor Y su rigidez, y meter las dos en C1-C5 las haría pelear
    por la misma dimensión hasta anularse. La rigidez que no se pudo acreditar no llega aquí:
    queda en `afirmaciones` como `REJECTED` con su campo, que deja constancia sin crear estado
    y sin competir con el valor."""

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

    @model_validator(mode="after")
    def _una_rigidez_por_campo(self) -> LoteExtraccion:
        """La misma regla que las durables, por el mismo motivo: dos rigideces de una
        dimensión sin resolver dejarían que el orden eligiera — *last-write-wins* dentro del
        mensaje."""
        campos = [r.campo for r in self.rigideces]
        repetidos = {c for c in campos if campos.count(c) > 1}
        if repetidos:
            raise ValueError(
                f"dos rigideces para {sorted(repetidos)}: se resuelven en el extractor, "
                f"no dejando que el orden decida")
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


class RigidezNoAcreditada(BaseModel):
    """E3.3-R2 · una rigidez que el proponente LEYÓ y la guarda no pudo acreditar.

    No crea estado, pero **compite**: es la mitad que faltaba. *"El presupuesto es
    innegociable… no, perdón, es flexible"* trae dos lecturas, y la corrección no repite la
    dimensión, así que la guarda sólo acredita la primera. Si la no acreditada no contara, la
    polaridad RETIRADA ganaba sola — el mismo defecto que E3.2b.1a cerró para los valores.
    """

    model_config = _CERRADO

    campo: CampoConCriterioV0
    rigidez: RigidezV0
    motivo: str = Field(min_length=1)


def resolver_rigideces(intentos, texto: str) -> tuple[tuple, tuple]:
    """C1-C5 para las rigideces. Devuelve `(vigentes, rechazos)`.

    `intentos` llega EN ORDEN de aparición y mezcla las acreditadas (`DeclaracionRigidezV0`)
    con las que no se pudieron acreditar (`RigidezNoAcreditada`). Por dimensión:

    ```
    todas de la misma rigidez          → la acreditada, si hay alguna
    polaridades distintas              → NUNCA estricta: la flexible acreditada si la hay;
                                         si no, nada — y un REJECTED con su campo
    ```

    **Asimétrico, como la guarda.** Un mensaje que dice las dos cosas de una dimensión —se
    corrija o no, se acredite o no cada lectura— no la endurece: la marca de autocorrección
    es global y puede referirse a otra cosa, y equivocarse hacia estricta excluye. Si la
    persona quería corregir hacia estricta, lo dice en el mensaje siguiente. Hacia flexible,
    en cambio, basta: *"el presupuesto es innegociable… no, perdón, es flexible"* relaja.

    Cada intento no acreditado deja además su propio REJECTED: constancia sin estado.
    """
    por_campo: dict[BuyerFieldV0, list] = {}
    for intento in intentos:
        por_campo.setdefault(intento.campo, []).append(intento)

    vigentes, rechazos = [], []
    for campo, grupo in por_campo.items():
        acreditadas = [i for i in grupo if isinstance(i, DeclaracionRigidezV0)]
        rechazos.extend(AfirmacionRejected(campo=i.campo, motivo=i.motivo)
                        for i in grupo if isinstance(i, RigidezNoAcreditada))
        if not acreditadas:
            continue
        if len({i.rigidez for i in grupo}) == 1:
            vigentes.append(acreditadas[0])
            continue
        flexibles = [a for a in acreditadas if a.rigidez is RigidezV0.FLEXIBLE]
        if flexibles:
            vigentes.append(flexibles[-1])
        rechazos.append(AfirmacionRejected(
            campo=campo,
            motivo=f"rigideces en conflicto para {campo}: un mismo mensaje no endurece"))
    return tuple(vigentes), tuple(rechazos)


def construir_lote(mensaje, afirmaciones, rigideces=()) -> LoteExtraccion:
    """El lote final: se resuelve el conflicto intramensaje ANTES de construirlo.

    El `source_message_id` sale del mensaje tal cual. **No se fabrica ni se deriva**: es lo
    que la procedencia de E3.2b.2 podrá citar, y un id sintético dejaría de apuntar a un
    `HumanMessage` que existe.

    `rigideces` trae, en orden, las acreditadas y las que no (`RigidezNoAcreditada`); aquí se
    resuelven entre sí. Los rechazos se añaden al final de las afirmaciones: no compiten con
    nada —un `REJECTED` nunca lo hace—, así que su posición no cambia ninguna resolución.
    """
    vigentes, rechazos = resolver_rigideces(rigideces, mensaje.text)
    return LoteExtraccion(
        source_message_id=mensaje.message_id,
        afirmaciones=resolver_intramensaje(afirmaciones, mensaje.text) + rechazos,
        rigideces=vigentes,
    )
