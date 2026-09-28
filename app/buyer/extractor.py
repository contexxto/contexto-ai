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

import functools
import re
import unicodedata
from collections.abc import Callable
from decimal import Decimal
from typing import Annotated, Literal, NamedTuple, Union

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


# ── F3-E3.2-VALUE-GUARD · el número LIGADO a su dimensión, dentro de una GRAMÁTICA CERRADA ──
#
# La guarda de E3.2 pedía la dimensión y el número en la misma cláusula, así que podía elegir
# CUALQUIER número presente:
#
#     "al menos 2 dormitorios para mis 3 hijos"      acreditaba bedrooms_min = 3  ← los hijos
#     "mínimo 80 m2 para 4 personas"                  acreditaba area_m2_min = 4   ← las personas
#     "presupuesto desde 900 USD"                     acreditaba budget_max = 900  ← un PISO
#
# R1 ligó el número a SU operador y SU ancla. R1b y R1c le añadieron LISTAS NEGRAS de contexto y
# tres revisiones adversariales mostraron que no convergen (8, 6 y 18 hallazgos, 0 refutados): una
# lista de lo que NO es el valor nunca está completa. R2 invirtió la carga —GRAMÁTICA CERRADA— y
# la cuarta ronda (20 hallazgos, 0 refutados) mostró dos cosas:
#
#   · las reglas de MENSAJE fallaban ABIERTAS. Sólo actuaban si reconocían el peligro, así que un
#     dígito en la cláusula que reparte («cada uno de los 3»), una cláusula de relleno intermedia
#     («La alícuota, de preferencia, máximo 80 USD») o una corrección fuera del vocabulario
#     («máximo 900 USD, perdón, mil USD») desactivaban la defensa entera.
#   · las propias listas cerradas tenían ASIMETRÍAS DE FAIR HOUSING: «solo» era neutro y «sola»
#     no; «mudarme de Guayaquil» acreditaba y «de Esmeraldas» no; «por Dios» acreditaba y «por
#     Alá» anulaba el mensaje entero; «ascensor» estaba en la lista de amenidades y «rampa» no.
#
# R2b corrige las dos. La regla de mensaje se invierte igual que la de cláusula (toda cláusula con
# una SEÑAL de la dimensión tiene que estar reconocida entera), y el vocabulario deja de nombrar a
# la persona: **se eliminó la lista de lugares**. Un lugar ya no se reconoce por su nombre sino
# por su POSICIÓN —detrás de una preposición locativa— y lo que se enumera es lo que NO es un
# lugar: magnitudes (dinero, área, dirección, partes del inmueble). Así «en Cumbayá» y «en
# Chillogallo» pesan igual, y «mudarme de X» no acredita para ningún X.
#
# **ESTADO: HARDENED, no certificado** (adjudicación de Carlos, 2026-09-27). Una guarda léxica
# reduce el riesgo frente a un proponente hostil, pero no puede certificar que no exista otra
# composición: cada ronda encontró una. Lo que sí garantiza, por construcción, es la DIRECCIÓN del
# error en todo lo que no reconoce: cae a AMBIGUOUS y a una pregunta.
#
# LA CLÁUSULA DEL VALOR acredita sólo si TODO lo que contiene está reconocido:
#
#     la frase del valor           operador + número + ancla, en una forma cerrada
#     frases de otras dimensiones  «máximo 900 USD con al menos 2 dormitorios»
#     cantidades del inmueble      «2 baños», «2 parqueaderos»
#     vocabulario neutro           CERRADO: pronombres, verbos de búsqueda, el inmueble
#     huecos acotados              cortesía, rigidez, tiempo, fechas, distancia, LUGAR (por
#                                  posición), forma de pago, periodo, amenidad, beneficiarios,
#                                  accesibilidad
#
# y ninguna regla de POSICIÓN la contradice: candidatos, solape, dirección (con símbolos «+», «>»,
# «≥», «↑»), operador compartido con una frase sin el suyo, «<X> de» (X tiene que ser el inmueble;
# un pronombre no basta), amenidad pegada al operador (también a través de «que cueste»).
#
# EL MENSAJE, FAIL-CLOSED: toda OTRA cláusula que traiga una SEÑAL de la dimensión —un número en
# dígitos o en letras, la unidad, un operador, un marcador de dirección, un reparto— tiene que
# estar reconocida ENTERA; si no, no se sabe qué hace esa señal con el valor, y no se acredita.
# Eso cubre de una vez el valor rival, la corrección («perdón, quise decir 1000»), el eco («900
# para arriba»), el reparto («cada uno de los 3») y el piso a distancia («…, bueno, en adelante»).
# Una cláusula SIN señal habla de otra cosa y no cuenta —por eso «Gracias por su atención» o «Me
# mudo por trabajo» ya no anulan nada—, salvo como TEMA de un valor que no tiene sujeto propio
# («El parqueadero, por favor. Máximo 50 USD»).
#
# Ninguna lista de este bloque puede nombrar un atributo de la PERSONA ni un lugar: los tests K7 y
# K13 cruzan plantillas con sustantivos y adjetivos protegidos, orígenes, religiones, barrios y
# rasgos de accesibilidad, y exigen el mismo veredicto en todos.

_NUM_LIGABLE = r"(?<![\w.,])(?P<n>\d{1,3}(?:,\d{3})+|\d{1,3}(?:\.\d{3})+|\d+)(?!\d|[.,]\d)"
"""Un número que se declara entero: dígitos, o miles agrupados de tres con UN solo separador.
`120.5` no liga —el punto puede ser decimal o de miles según la plaza—, `1,234.567` tampoco —dos
separadores distintos—, y el `2` de `m2` tampoco, porque va pegado a una letra. Puede ir pegado a
la unidad de área («80m2») pero NO al código de moneda: «900usd» no liga porque `usd` exige
frontera de palabra, y se prefiere preguntar a ensanchar la moneda."""

_OP_MINIMO = (r"(?:al menos|por lo menos|como minim[oa]|minim[oa]|minimum|at least|desde|"
              r"a partir de)")
_OP_MINIMO_POST = (r"(?:o mas|como minim[oa]|minim[oa]|al menos|por lo menos|en adelante|"
                   r"para arriba|hacia arriba|or more)")
_VERBO_MINIMO = r"(?:necesito|necesitamos|quiero|queremos|busco|buscamos|requiero|requerimos)"
_OP_TOPE = (r"(?:como maxim[oa]|no mas de|maxim[oa]|max|hasta|tope(?: de presupuesto)?|"
            r"limite(?: de presupuesto)?|presupuesto(?: maxim[oa])?|budget)")
_OP_TOPE_POST = (r"(?:como maxim[oa]|maxim[oa]|max|como tope|tope|como limite|"
                 r"de presupuesto)")
_OP_TECHO_SIMPLE = r"(?:como maxim[oa]|no mas de|maxim[oa]|max|hasta|a lo sumo)"
_VERBO_TOPE = (r"(?:(?:que\s+)?(?:puedo|podemos|quiero|queremos)\s+(?:pagar|gastar|invertir)|"
               r"pagaria|pagariamos|tengo|tenemos)")
_CONECTOR = r"(?:\s+(?:es|son|seria|sera|esta en|llega a))?(?:\s+(?:de|los))?"
_APROX = r"(?:unos\s+)?"
_PERIODO = r"(?:\s+(?:mensuales|mensual|al mes|por mes))?"
_FIN_DE_VALOR = r"(?![\w.,]|\s*[a-z$])"
"""Detrás de «dormitorios mínimo 3» no puede venir otro sustantivo: «… mínimo 3 baños»."""

_ANCLA_DORMITORIOS = (
    r"(?:dormitorios?|habitacion(?:es)?|cuartos?|recamaras?|bedrooms?)(?!\w)"
    r"(?!\s+de\s+(?!(?:(?:al menos|por lo menos|como minimo|minimo|unos)?\s*\d|"
    r"(?:preferencia|buen|tamano|ser)\b)))")
"""«de» detrás del sustantivo sólo si lo que sigue es su TAMAÑO —«3 dormitorios de al menos 12
m2», «de buen tamaño»— o una cortesía —«de preferencia», «de ser posible»—. «2 cuartos de baño»,
«1 cuarto de servicio», «3 cuartos de hora» o «habitaciones de hotel» nombran otra cosa."""
_ANCLA_AREA = r"(?:m2|m²|mts2|metros cuadrados?|square meters?)(?!\w)"


def _formas_minimo(ancla: str) -> tuple[re.Pattern, ...]:
    return (
        re.compile(rf"\b{_OP_MINIMO}(?:\s+{_VERBO_MINIMO})?\s+(?:de\s+)?{_APROX}{_NUM_LIGABLE}"
                   rf"\s*{ancla}"),
        re.compile(rf"{_NUM_LIGABLE}\s*{ancla}\s+{_OP_MINIMO_POST}\b"),
        re.compile(rf"{_NUM_LIGABLE}\s+o\s+mas\s+{ancla}"),
        re.compile(rf"\b{ancla}\s+{_OP_MINIMO}\s+{_NUM_LIGABLE}{_FIN_DE_VALOR}"),
    )


def _candidatos_minimo(ancla: str) -> tuple[re.Pattern, ...]:
    return (
        re.compile(rf"{_NUM_LIGABLE}\s*(?:o\s+mas\s+)?{ancla}"),
        re.compile(rf"\b{ancla}\s+{_OP_MINIMO}\s+{_NUM_LIGABLE}{_FIN_DE_VALOR}"),
    )


def _techos_de_minimo(ancla: str) -> tuple[re.Pattern, ...]:
    """El TECHO de una dimensión de mínimo —«máximo 3 dormitorios»—. Sólo sirve para RECONOCERLO
    en otra cláusula: no es un rival del mínimo, es su otro extremo."""
    return (
        re.compile(rf"\b{_OP_TECHO_SIMPLE}\s+{_NUM_LIGABLE}\s*{ancla}"),
        re.compile(rf"{_NUM_LIGABLE}\s*{ancla}\s+(?:como maxim[oa]|maxim[oa]|o menos|"
                   rf"a lo sumo)\b"),
        re.compile(rf"\b{ancla}\s+(?:maxim[oa]|hasta)\s+{_NUM_LIGABLE}{_FIN_DE_VALOR}"),
    )


_LIGA_DORMITORIOS = _formas_minimo(_ANCLA_DORMITORIOS)
_LIGA_AREA = _formas_minimo(_ANCLA_AREA)
_CANDIDATOS_DORMITORIOS = _candidatos_minimo(_ANCLA_DORMITORIOS)
_CANDIDATOS_AREA = _candidatos_minimo(_ANCLA_AREA)
_TECHOS_DORMITORIOS = _techos_de_minimo(_ANCLA_DORMITORIOS)
_TECHOS_AREA = _techos_de_minimo(_ANCLA_AREA)


@functools.lru_cache(maxsize=8)
def _liga_presupuesto(cur: str) -> tuple[re.Pattern, ...]:
    """Las formas de tope para ESTA moneda. `(?:\\$\\s*)?` y no `\\$?\\s*`: dos cuantificadores
    de espacio seguidos hacían cuadrático el retroceso con miles de espacios (revisión R1c)."""
    return (
        re.compile(rf"\b{_OP_TOPE}(?:\s+{_VERBO_TOPE})?{_CONECTOR}\s+{_APROX}(?:\$\s*)?"
                   rf"{_NUM_LIGABLE}\s*{cur}"),
        re.compile(rf"\b{_OP_TOPE}(?:\s+{_VERBO_TOPE})?{_CONECTOR}\s+{cur}\s*{_NUM_LIGABLE}"),
        re.compile(rf"{_NUM_LIGABLE}\s*{cur}{_PERIODO}\s+{_OP_TOPE_POST}\b"),
        re.compile(rf"{cur}\s*{_NUM_LIGABLE}{_PERIODO}\s+{_OP_TOPE_POST}\b"),
        re.compile(rf"{_NUM_LIGABLE}\s*{cur}\s+(?:es|sera|seria)\s+(?:mi|el|lo)\s+"
                   rf"(?:tope|maximo|limite)\b"),
    )


@functools.lru_cache(maxsize=8)
def _candidatos_presupuesto(cur: str) -> tuple[re.Pattern, ...]:
    """Los números pegados a la moneda. «USD 900» cuenta; el «2» de «hasta 900 USD 2
    dormitorios» no: detrás lleva el sustantivo de OTRA dimensión."""
    return (re.compile(rf"(?:\$\s*)?{_NUM_LIGABLE}\s*{cur}"),
            re.compile(rf"{cur}\s*{_NUM_LIGABLE}(?!\s*[a-z])"))


@functools.lru_cache(maxsize=8)
def _pisos_de_presupuesto(cur: str) -> tuple[re.Pattern, ...]:
    """El PISO del presupuesto. Sólo sirve para RECONOCERLO en otra cláusula: «presupuesto 900 USD
    mínimo y 1200 USD máximo» no tiene dos topes rivales, tiene un rango."""
    return (
        re.compile(rf"\b{_OP_MINIMO}\s+(?:de\s+)?{_APROX}(?:\$\s*)?{_NUM_LIGABLE}\s*{cur}"),
        re.compile(rf"(?:\$\s*)?{_NUM_LIGABLE}\s*{cur}(?:\s+de\s+presupuesto)?{_PERIODO}\s+"
                   rf"{_OP_MINIMO_POST}\b"),
        re.compile(rf"\bpresupuesto\s+minim[oa]\s+(?:de\s+)?(?:\$\s*)?{_NUM_LIGABLE}\s*{cur}"),
        re.compile(rf"\b(?:mas de|arriba de|por encima de|superior a|no menos de)\s+(?:\$\s*)?"
                   rf"{_NUM_LIGABLE}\s*{cur}"),
    )


_MONEDA_GENERICA = r"(?:\busd\b|\bmxn\b|\bdolar(?:es)?\b)"
"""Para RECONOCER un tope cuando se examina otra dimensión: sólo se tacha, nunca se acredita."""

_CANTIDADES_DEL_INMUEBLE = re.compile(
    rf"(?:{_OP_MINIMO}\s+|{_OP_TOPE}\s+)?(?:de\s+)?(?<![\w.,])\d+\s*(?:banos?|medios?\s+banos?|"
    r"(?:cuartos?|habitacion(?:es)?)\s+de\s+bano|parqueaderos?|parqueos?|estacionamientos?|"
    rf"garajes?|pisos|plantas|niveles|bodegas?|ascensores?)\b(?:\s+{_OP_MINIMO_POST}\b)?")
"""Cantidades de OTRAS partes del inmueble —«2 baños», «mínimo 2 cuartos de baño», «2
parqueaderos»—. No son de ninguna dimensión de V0, pero tampoco contaminan: se tachan. El
lookbehind ante los dígitos evita el retroceso cuadrático sobre una tira larga de números."""

_TOPE_NEGADO = re.compile(r"\bno mas de\b")
"""«No más de 900 USD» es un tope; su «no» no niega la cláusula."""

# ── la preparación del texto ───────────────────────────────────────────────────────────

_LARGO_MAXIMO = 4000
"""Un mensaje más largo no se analiza: falla cerrado. Ningún pedido de vivienda lo necesita, y es
el tope que deja acotado el costo de cada expresión regular (revisión R2: una tira de 40 000
dígitos costaba decenas de segundos de CPU síncrona dentro del camino async del chat)."""
_ESPACIOS = re.compile(r"[^\S\n]+")
_DOS_PUNTOS = re.compile(r"(?<!\d)\s*:\s*|\s*:\s*(?!\d)")
_Y_O = re.compile(r"\by\s*/\s*o\b")
_ENTRE = re.compile(r"(\bentre\s+(?:unos\s+)?(?:\$\s*)?\d[\d.,]*(?:\s*[^\W\d_]+)?)\s+y\s+")
_Y_ENTRE_NUMEROS = re.compile(r"(?<![\w.,])(\d[\d.,]*)\s+y\s+(?=(?:\$\s*)?\d)")
"""«2 y 3 dormitorios» es una alternativa. El lookbehind impide que el «2» de «m2» convierta
«mínimo 80 m2 y 3 dormitorios» en una disyunción y pierda las dos dimensiones (revisión R2)."""
_DISYUNCION_PARTIDA = re.compile(r"(?<![,;.!?¡¿…])[,;.!?¡¿…]+\s*(?=(?:o|u|or)\s)")
"""«al menos 2 dormitorios, o al menos 3», «… ! o 1000 USD»: la puntuación no separa dos hechos,
separa dos alternativas. El lookbehind hace lineal el caso de miles de signos seguidos."""
_CONTINUACION = re.compile(r"\s*(?:o|u|or)\b")
_GUION_DE_FICHA = re.compile(r"\s+[-–—·•|]+\s+")
"""«Cumbayá - 80 m2 - 3 dormitorios mínimo»: en una ficha el guión separa campos, igual que un
punto. Exige espacios a los dos lados, para no partir «3-4 dormitorios»."""
_HAY_NUMERO = re.compile(r"(?<![\w.,])\d")
"""Un número que se escribe como tal. El «2» de «m2» no: «el m2» no es una línea con valor."""
_DIGITO = re.compile(r"\d")
_CLAUSULA_CON_SEPARADOR = re.compile(rf"({_CLAUSULA.pattern})")
_COORDINACION = re.compile(r"\s*(?:y|pero|aunque)\s*")


class _Clausula(NamedTuple):
    texto: str
    pausa_antes: bool                  # puntuación o salto de línea antes (no «y/pero/aunque»)
    interrogativa: bool                # «¿Hasta 900 USD?» pregunta, no declara


def _preparar(plano: str) -> list[_Clausula]:
    """El texto partido en cláusulas.

    - Más de `_LARGO_MAXIMO` caracteres: ninguna cláusula (fail closed).
    - Espacios de cualquier tipo colapsados.
    - Una línea SIN números se une a su vecina: es una etiqueta («Busco depa en Cumbayá») o una
      continuación («o más», «c/u», «es innegociable»), nunca un valor aparte. Una línea que
      empieza por «o» continúa una disyunción. Sólo dos líneas con números seguidas se separan,
      como en una ficha de WhatsApp.
    - «Presupuesto: 900 USD» es UNA cláusula; «entre 2 y 3» y «2 y 3» son alternativas; «y/o» es
      una disyunción; el guión de una ficha («Cumbayá - 80 m2 - 3 dormitorios») separa campos.
    - PAUSA es puntuación o salto de línea; «y», «pero», «aunque» coordinan. Los separadores de
      una cláusula vacía se ACUMULAN, así que «, y» sigue siendo una pausa (en R2 la coma se
      perdía y la cláusula quedaba coordinada).
    """
    if len(plano) > _LARGO_MAXIMO:
        return []
    grupos: list[str] = []
    anterior_con_numero = False
    for linea in _ESPACIOS.sub(" ", plano).split("\n"):
        if not linea.strip():
            continue
        con_numero = bool(_HAY_NUMERO.search(linea))
        if grupos and not (con_numero and anterior_con_numero
                           and not _CONTINUACION.match(linea)):
            grupos[-1] += " " + linea
        else:
            grupos.append(linea)
        anterior_con_numero = con_numero
    clausulas: list[_Clausula] = []
    for g, grupo in enumerate(grupos):
        grupo = _GUION_DE_FICHA.sub(". ", grupo)
        grupo = _ENTRE.sub(r"\1 a ", _Y_O.sub("o", _DOS_PUNTOS.sub(" ", grupo)))
        grupo = _Y_ENTRE_NUMEROS.sub(r"\1 o ", grupo)
        partes = _CLAUSULA_CON_SEPARADOR.split(_DISYUNCION_PARTIDA.sub(" ", grupo))
        antes = "\n" if g else ""
        for i in range(0, len(partes), 2):
            texto = partes[i]
            despues = partes[i + 1] if i + 1 < len(partes) else ""
            if texto.strip():
                clausulas.append(_Clausula(
                    texto,
                    bool(antes) and not _COORDINACION.fullmatch(antes),
                    "¿" in antes or "?" in despues))
                antes = despues
            else:
                antes += despues
    return clausulas


# ── el vocabulario cerrado ──────────────────────────────────────────────────────────────

_SUJETOS_DEL_INMUEBLE = frozenset({
    "casa", "casas", "casita", "departamento", "departamentos", "depa", "depas", "depto",
    "deptos", "dpto", "apartamento", "apartamentos", "apto", "suite", "loft", "duplex",
    "penthouse", "inmueble", "inmuebles", "vivienda", "viviendas", "propiedad", "propiedades",
    "hogar", "arriendo", "arriendos", "alquiler", "alquileres", "renta", "rentas",
    "arrendamiento", "compra", "presupuesto", "precio", "valor", "costo", "total", "tope",
    "limite", "cantidad", "monto", "superficie", "metraje", "construccion", "tamano", "algo"})
"""Lo que puede ser el sujeto de «<X> de <valor>». NO: «piso» (también es el piso de un tope),
ni pronombres o genéricos —«uno», «una», «área», «espacio», «lugar»—: «3 dormitorios con uno de
al menos 15 m2» habla de UN dormitorio, no del inmueble (revisión R2)."""
_ADJETIVOS_DEL_INMUEBLE = frozenset({
    "amueblado", "amueblada", "amueblados", "amuebladas", "amoblado", "amoblada", "amoblados",
    "amobladas", "nuevo", "nueva", "nuevos", "nuevas", "grande", "grandes", "amplio", "amplia",
    "amplios", "amplias", "espacioso", "espaciosa", "bonito", "bonita", "lindo", "linda",
    "moderno", "moderna", "remodelado", "remodelada", "renovado", "renovada", "equipado",
    "equipada", "comodo", "comoda", "acogedor", "acogedora", "iluminado", "iluminada",
    "luminoso", "luminosa", "soleado", "soleada", "ventilado", "ventilada", "independiente",
    "tranquilo", "tranquila", "centrico", "centrica", "bueno", "buena", "buen", "pequeno",
    "pequena", "barato", "barata", "economico", "economica", "accesible", "accesibles",
    "construido", "construida", "construidos", "construidas", "util", "utiles", "privado",
    "privada", "cerrado", "cerrada"})
"""«seguro» NO está: también es un seguro —«el seguro máximo 40 USD»—; «barrio seguro» se admite
como hueco. «accesible» SÍ: la accesibilidad no puede costar más que «amplio» (Fair Housing)."""
_COPULAS_Y_BUSQUEDA = frozenset({
    "sea", "sean", "ser", "es", "son", "sera", "seria", "este", "esten", "estar", "busco",
    "buscamos", "buscando", "estoy", "estamos"})
_SUJETO_DE = _SUJETOS_DEL_INMUEBLE | _COPULAS_Y_BUSQUEDA
_AJENOS_DE_DORMITORIOS = frozenset({
    "hotel", "hoteles", "hostal", "hostales", "edificio", "edificios", "torre", "torres",
    "bloque", "bloques", "residencia", "residencias"})
"""En dormitorios, «<X> de» sólo es ajeno si X CONTIENE habitaciones y no es el inmueble: un
balcón no tiene dormitorios, así que «depa con balcón de mínimo 3 dormitorios» liga."""

_DETERMINANTES = frozenset({
    "el", "la", "los", "las", "un", "una", "unos", "unas", "mi", "mis", "su", "sus", "nuestro",
    "nuestra", "nuestros", "nuestras", "lo", "de", "del", "este", "esta", "ese", "esa"})

_NEUTRAS = frozenset({
    # pronombres, partículas, muletillas
    "yo", "nosotros", "nosotras", "me", "nos", "que", "se", "le", "les", "cual", "cualquier",
    "en", "a", "al", "con", "para", "tambien", "ademas", "solamente", "ideal", "idealmente",
    "realmente", "igual", "bien", "pues", "entonces", "ok", "okey", "vale", "preferencia",
    "preferiblemente", "posible", "aproximadamente", "aprox", "aproximado", "todo", "mejor",
    "realidad", "corrijo", "corrigo", "rectifico", "dicho", "digo", "tipo", "zona", "sector",
    "barrio", "lugar", "sitio", "espacio", "area", "opcion", "opciones", "unidad", "uno",
    "alguno", "alguna", "algun",
    # verbos de búsqueda y requisito (primera persona o subjuntivo, nunca descriptivos)
    "busco", "buscamos", "buscando", "busca", "estoy", "estamos", "soy", "somos", "vivo",
    "vivimos", "necesito", "necesitamos", "quiero", "queremos", "quisiera", "quisieramos",
    "requiero", "requerimos", "prefiero", "preferimos", "tengo", "tenemos", "tenga", "tengan",
    "sea", "sean", "ser", "es", "son", "sera", "seria", "este", "esten", "puedo", "podemos",
    "podria", "podriamos", "pagar", "gastar", "invertir", "comprar", "alquilar", "arrendar",
    "rentar", "vivir", "cueste", "cuesten", "salga", "valga", "ver", "encontrar", "conseguir",
    "tener", "gustaria", "interesa", "acepte", "acepten", "admita", "permita", "dispuesto",
    "dispuesta", "dispuestos", "dispuestas", "estaria", "estariamos",
    # tiempo, sin marcador de dirección ni periodo
    "ahora", "ya", "hoy", "pronto", "urgente", "urgentemente", "proximo", "proxima", "enero",
    "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "setiembre",
    "octubre", "noviembre", "diciembre",
}) | _DETERMINANTES | _SUJETOS_DEL_INMUEBLE | _ADJETIVOS_DEL_INMUEBLE
"""Lo único que puede acompañar a un valor sin impedir que se acredite. CERRADO: una palabra que
no está aquí hace que la cláusula no acredite. Ninguna describe a la PERSONA y ninguna nombra un
lugar: «solo» salió porque «sola» no estaba (sexo, estado civil) y la lista de barrios salió
entera porque hacía que el veredicto dependiera del origen. «más», «mes» y «año» tampoco están:
«para más» es un piso y «al año» es otra escala (una tasa anual acreditada como tope mensual
multiplica el filtro por doce)."""

_PARTICULAS = frozenset({
    "de", "del", "el", "la", "los", "las", "un", "una", "unos", "unas", "a", "al", "en", "con",
    "y", "o", "que", "lo", "es", "son", "sea", "sean", "ser", "seria", "sera", "mi", "mis", "su",
    "sus", "nuestro", "nuestra", "nuestros", "nuestras", "me", "nos", "se", "le", "les"})
"""Lo que queda en un valor SIN sujeto propio: «máximo 50 USD», «que sea de máximo 50 USD»."""

# ── los huecos ─────────────────────────────────────────────────────────────────────────

_AMENIDADES = (r"(?:parqueaderos?|parqueos?|estacionamientos?|garajes?|cocheras?|bodegas?|"
               r"balcon(?:es)?|terrazas?|jardin(?:es)?|patios?|piscinas?|gimnasios?|gym|"
               r"ascensor(?:es)?|rampas?|accesibilidad|servicios(?:\s+basicos)?|luz|agua|"
               r"internet|wifi|gas|alicuotas?|mantenimiento|muebles|lavanderia|guardiania|"
               r"seguridad|vista)")

_NO_ES_LUGAR = (
    rf"(?:{_AMENIDADES}|efectivo|cuotas?|contado|total|gastos?|comida|transporte|"
    r"arriendos?|rentas?|alquiler|expensas|garantia|deposito|anticipo|adelanto|"
    r"presupuesto|precios?|costos?|pagos?|mensualidad|dolar|dolares|usd|mxn|"
    r"pesos|m2|mts2|metro|metros|area|superficie|metraje|dormitorios?|habitacion|habitaciones|"
    r"cuartos?|recamaras?|banos?|planta|plantas|piso|pisos|niveles|"
    r"adelante|arriba|abajo|mas|menos|superior|inferior|encima|debajo|minim[oa]|maxim[oa]|"
    r"tope|limite|base|promedio|general|realidad|cambio|caso|cuanto|serio|venta|oferta)")
"""Lo que NO es un lugar aunque venga detrás de una preposición locativa. Enumera MAGNITUDES
—dinero, área, dirección, partes del inmueble—, nunca personas ni lugares: por eso la carga de la
pregunta cae sobre una lista cerrada y verificable en vez de sobre los nombres de los barrios."""
_PREP_DE_LUGAR = (r"(?:cerca del|cerca de|en la zona de|en el sector de|por la zona de|"
                  r"por el sector de|en|hacia|zona|sector|barrio|urbanizacion|ciudadela)")
_HUECO_DE_LUGAR = re.compile(
    rf"\b{_PREP_DE_LUGAR}\s+(?:(?:el|la|los|las)\s+)?(?!{_NO_ES_LUGAR}\b)[^\W\d_]+"
    rf"(?:\s+(?!{_NO_ES_LUGAR}\b)[^\W\d_]+){{0,2}}")
"""DÓNDE está el inmueble, reconocido por POSICIÓN y no por nombre: «en Cumbayá», «en el sector
de la Coruña», «en Chillogallo o Solanda», «zona norte». R2 tenía una lista cerrada de barrios y
eso hacía dos cosas inaceptables: acreditaba «mudarme de Guayaquil» y no «de Esmeraldas» (origen
nacional), y ponía la carga de la pregunta sobre los barrios que faltaban en la lista. «por» y «a»
quedan FUERA a propósito: «por persona» reparte y «a pagar» no es un lugar."""

_MESES = (r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|"
          r"noviembre|diciembre)")
_TIEMPO = (r"(?:(?:el|la|este|esta|el proximo|la proxima|el siguiente|la siguiente)\s+)?"
           rf"(?:{_MESES}|lunes|martes|miercoles|jueves|viernes|sabado|domingo|ya|hoy|manana|"
           r"ahora|pronto|mes|semana|ano|fin de mes|fin de ano)")
_FRASE_DE_TIEMPO = re.compile(
    rf"\b(?:desde|a partir de|hasta|para)\s+(?:el\s+)?(?:(?<![\w.,])\d{{1,2}}\s+de\s+{_MESES}|"
    rf"{_TIEMPO})\b|"
    r"\b(?:al menos|por lo menos|minimo)\s+(?:por|durante)\s+(?:un|una|dos|tres|seis|\d+)\s+"
    r"(?:anos?|mes(?:es)?|semanas?)\b|"
    rf"(?<![\w.,])\d{{1,2}}\s+de\s+{_MESES}\b")
"""«hasta 900 USD desde octubre», «para el 1 de octubre», «máximo 900 USD al menos por un año»:
complementos de TIEMPO. Se tachan como una unidad —número incluido— y el marcador que los abre no
cuenta como dirección. «o más ahora» sigue siendo un piso."""

_POR_QUE_NO_REPARTE = (
    r"(?:favor|favorcito|fa|fis|ahora|ahorita|el momento|lo pronto|lo general|mes|el mes|"
    r"ultimo|cierto|supuesto|ejemplo|lo tanto|tanto|ende|fin|mientras|si acaso|las dudas|"
    r"suerte|eso|todo|adelantado|la ayuda|tu ayuda|su ayuda|tu tiempo|su tiempo|"
    r"su atencion|tu atencion|la atencion|la informacion|la info|responder|su respuesta|"
    r"tu respuesta|el anuncio|su anuncio|facebook|instagram|marketplace|whatsapp|telefono|"
    r"correo|mensaje|email|mail|internet|trabajo|estudios|aqui|ahi|alla|aca|la zona|el sector|"
    r"la tarde|la manana|la noche)")
"""«por» que NO reparte. Ninguna entrada es religiosa ni describe a la persona: «por Dios» salió
porque «por Alá» y «por la Virgen» no estaban y anulaban el mensaje entero (revisión R2). Ahora
ninguna invocación anula nada: sin señal de la dimensión, la cláusula no cuenta."""

_HUECOS_COMUNES = tuple(re.compile(p) for p in (
    r"\b(?:buen dia|buenos dias|buenas tardes|buenas noches|buenas|hola|que tal|estimados?|"
    r"estimadas?|saludos cordiales|un saludo|saludos|muchas gracias|mil gracias|"
    r"gracias de antemano|de antemano|gracias|quedo atent[oa]|quedo pendiente|"
    r"quedamos atentos|quedamos pendientes|disculpa|disculpe|perdon|oye|mira|por favor|"
    r"porfavor|porfa|por fa|x favor|x fa|por fis|porfis|por favorcito)\b",
    r"\b(?:si o si|sin falta|es innegociable|innegociable|es indispensable|indispensable|"
    r"es imprescindible|imprescindible|es excluyente|excluyente|es flexible|flexible|"
    r"es negociable|negociable|hay margen)\b",
    r"\b(?:tiene que|tienen que|tendria que|tendrian que|debe|deben|deberia|deberian|ha de)\b",
    r"\b(?:mejor dicho|en realidad|o sea|mas bien|de hecho|la verdad|en verdad|me equivoque)\b",
    r"\b(?:mas o menos|todo incluido|me mudo|nos mudamos|me mudare|nos mudaremos|"
    r"me voy a mudar|nos vamos a mudar)\b",
    rf"\b(?:por|x)\s+(?:{_POR_QUE_NO_REPARTE}|(?:un|una|el|la)\s+(?:casa|depa|departamento|"
    r"depto|apartamento|suite|inmueble|vivienda|propiedad|arriendo|alquiler|renta|compra))\b",
    r"\b(?:barrio|zona|sector|lugar|sitio|conjunto|edificio)\s+segur[oa]\b",
    rf"\ba\s+\d+\s*(?:minutos?|mins?|cuadras?|km|kilometros?|metros|pasos)\s+(?:del|de)\b"
    rf"(?:\s+(?:el|la|los|las))?(?:\s+(?!{_NO_ES_LUGAR}\b)[^\W\d_]+){{0,3}}",
    r"\b(?:en|de)\s+planta\s+baja\b|\bsin\s+(?:escalones|gradas|barreras|desniveles)\b|"
    r"\b(?:con\s+)?acceso\s+(?:para|en)\s+silla\s+de\s+ruedas\b",
))

_AMENIDAD = re.compile(
    rf"\b(?:con|sin|y|mas|incluye|incluyendo|incluido|incluida|incluidos|incluidas)\s+"
    rf"(?:todos\s+los\s+|todas\s+las\s+|el\s+|la\s+|los\s+|las\s+|un\s+|una\s+|\d+\s+)?"
    rf"{_AMENIDADES}(?:\s+(?:techad[oa]s?|cubiert[oa]s?|grandes?|ampli[oa]s?|privad[oa]s?|"
    rf"propi[oa]s?|natural|basicos|incluid[oa]s?)){{0,2}}\b|"
    rf"\b{_AMENIDADES}\s+incluid[oa]s?\b|\+\s*{_AMENIDADES}\b")
"""Una amenidad DEL inmueble —«depa CON parqueadero», «SIN ascensor», «más alícuota», «alícuota
incluida»— no tiene precio ni dormitorios propios en esa frase. Sin la preposición delante es el
sujeto del tope, y no liga. PEGADA al operador tampoco —ni a través de «que cueste», «que sea
de»—: «depa con parqueadero máximo 50 USD» puede ser el precio del parqueadero. En el ÁREA no se
admite como hueco: «casa con jardín mínimo 80 m2» puede ser el jardín. «sin» está en la misma
lista que «con» a propósito: si «sin escalones» no negara y «sin ascensor» sí, la accesibilidad
tendría un trato distinto del resto de las amenidades."""

_HUECOS_POR_DIMENSION = {
    BuyerFieldV0.BUDGET_MAX: tuple(re.compile(p) for p in (
        r"\b(?:al mes|por mes|el mes|cada mes|mensuales|mensual|mensualmente)\b",
        r"\b(?:en cuotas|al contado|de contado|en efectivo)\b",
        r"\b(?:no mas|nada mas)\b",
    )) + (_AMENIDAD,),
    BuyerFieldV0.BEDROOMS_MIN: (_AMENIDAD,),
    BuyerFieldV0.AREA_M2_MIN: (),
}

_BENEFICIARIOS = re.compile(
    r"\bpara\s+(?:mis|mi|nuestros|nuestras|nuestro|nuestra|sus|su|los|las)?\s*\d+\s+[^\W\d_]+\b|"
    r"\bpara\s+(?:mis|nuestros|nuestras|sus)\s+[^\W\d_]+\b")
"""«al menos 2 dormitorios para mis 3 hijos», «mínimo 80 m2 para 4 personas»: PARA QUIÉN, en un
mínimo. El número de ese hueco no es candidato y el sustantivo no se lee —«para mis 3 bicicletas»
da lo mismo—. En el tope no se admite: «hasta 900 USD para mis gastos» no es el precio del
inmueble. Residuo conocido: «al menos 15 m2 para 2 carros» liga, porque distinguir personas de
carros exigiría leer el sustantivo."""

_SIN_QUE_NO_NIEGA = re.compile(
    rf"\bsin\s+(?:{_AMENIDADES}|escalones|gradas|barreras|desniveles|amoblar|amueblar)\b")
"""«hasta 900 USD sin escalones», «sin ascensor», «sin parqueadero»: describen el inmueble, no
niegan el tope."""

# ── la dirección ────────────────────────────────────────────────────────────────────────

_MARCA_PISO = (r"(?:o mas|o superior|o arriba|o mayor|para arriba|hacia arriba|pa arriba|"
               r"para adelante|en adelante|como minim[oa]|minim[oa]|minimamente|como piso|"
               r"de piso|como base|al menos|por lo menos|mas de|desde|a partir de|arriba de|"
               r"por encima de|encima de|superior a|no menos de|un poco mas|algo mas|"
               r"puede ser mas|podria ser mas|or more|and up|and above|at least|minimum|"
               r"more than)")
_MARCA_TECHO = (r"(?:o menos|como maxim[oa]|maxim[oa]|max|a lo sumo|como mucho|hasta|"
                r"no mas de|menos de|or less|or fewer|at most|up to)")
_DIRECCIONAL_TOPE = re.compile(
    r"\b(?:como maxim[oa]|no mas de|maxim[oa]|max|hasta|tope|limite)\b")
_OP_AL_INICIO = re.compile(rf"\s*(?:{_OP_MINIMO}|{_OP_TOPE})\b")
_OP_AL_FINAL = re.compile(rf"\b(?:{_OP_MINIMO_POST}|{_OP_TOPE_POST})\s*$")
_NUNCA_POSPUESTO = re.compile(r"\s*(?:hasta|no mas de)\b")
"""«hasta» y «no más de» nunca van detrás de su valor, así que en «2 dormitorios hasta 900 USD»
el «hasta» no puede ser de los dormitorios (revisión R2). Con una CANTIDAD sí se comparte: «2
parqueaderos hasta 100 USD» puede ser el precio de los parqueaderos."""


@functools.lru_cache(maxsize=4)
def _reversa(dim: BuyerFieldV0) -> tuple[re.Pattern, re.Pattern]:
    """(antes del valor, después del valor) para la dirección CONTRARIA, con sus símbolos:
    «+900 USD», «> 900 USD», «≥ 900 USD», «900 USD (+)», «900 USD ↑» son PISOS."""
    if dim is BuyerFieldV0.BUDGET_MAX:
        antes = rf"(?:\b{_MARCA_PISO}\b|\+|>=?|≥|=>)"
        despues = rf"(?:{_MARCA_PISO}\b|\(\s*\+\s*\)|\+(?!\s*[^\W\d_])|↑|>)"
    else:
        antes = rf"(?:\b{_MARCA_TECHO}\b|<=?|≤)"
        despues = rf"(?:{_MARCA_TECHO}\b|\(\s*-\s*\)|↓)"
    return (re.compile(rf"{antes}\s*(?:de\s+|un\s+|unos\s+|los\s+|mi\s+)*(?:\$\s*)?$"),
            re.compile(rf"{_PERIODO}\s*{despues}"))


# ── las señales de la dimensión en OTRA cláusula ────────────────────────────────────────

_NUMERO_EN_LETRAS = (r"(?:dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|"
                     r"catorce|quince|dieci\w+|veinte|veinti\w+|treinta|cuarenta|cincuenta|"
                     r"sesenta|setenta|ochenta|noventa|cien|ciento|doscientos|trescientos|"
                     r"cuatrocientos|quinientos|seiscientos|setecientos|ochocientos|"
                     r"novecientos|mil|millon|millones)")
"""«uno/una/un» quedan fuera: son artículos y aparecerían en cualquier frase."""
_LETRA_NUMERO = re.compile(rf"\b{_NUMERO_EN_LETRAS}\b")
_CUANTIFICA = rf"(?:(?<![\w.,])\d[\d.,]*|\b{_NUMERO_EN_LETRAS}\b)"
_NOMBRE_DE_DIMENSION = (
    r"(?:presupuesto|tope|limite|precio|costo|pago|cuota|mensualidad|alicuota|expensas|"
    r"arriendo|renta|alquiler|dolar|dolares|usd|mxn|pesos|m2|mts2|metro|metros|area|superficie|"
    r"metraje|dormitorios?|habitacion|habitaciones|cuartos?|recamaras?|bedrooms?)")
_CONTEO = re.compile(
    rf"\b(?:somos|son|seremos|seriamos|tengo|tenemos|vivimos|hay)\s+(?:unos\s+)?{_CUANTIFICA}|"
    rf"{_CUANTIFICA}\s+(?!(?:de|del|el|la|los|las|un|una|a|al|en|y|o|u|que|por|para|con|sin|"
    rf"mas|menos|arriba|abajo|adelante|como|minim[oa]|maxim[oa]|cada|x|no|si|es|son|lo|"
    rf"{_NUMERO_EN_LETRAS})\b)(?!{_NOMBRE_DE_DIMENSION}\b)[^\W\d_]{{3,}}")
"""Un número que CUENTA algo —«somos 4», «2 perros», «dos hijos»— no es un valor de ninguna
dimensión. Se reconoce por la FORMA: detrás va un sustantivo que no es de la dimensión; delante,
un verbo de cantidad. El sustantivo no se lee, así que «2 perros» y «2 hijos» pesan igual. La
exclusión de `_NOMBRE_DE_DIMENSION` es la que impide que «mil dólares» se tome por un conteo y
pierda su condición de rival."""
_SENAL_NUMERICA = re.compile(_CUANTIFICA)
_SENAL_DE_REPARTO = re.compile(r"\bpor\s+(?:cada\s+)?[^\W\d_]+|\bx\s+[^\W\d_]+|"
                               r"\bcada\s+[^\W\d_]+|\bc\s*/\s*u\b|\bper\s+capita\b")
_SENAL_DE_DIRECCION = re.compile(
    rf"\b(?:{_MARCA_PISO}|{_MARCA_TECHO}|mas|menos|arriba|abajo|adelante|superior|inferior|"
    rf"encima|debajo)\b|[+<>≤≥↑↓]")
_SENAL_DE_DIMENSION = {
    BuyerFieldV0.BUDGET_MAX: re.compile(
        r"\b(?:presupuesto|tope|limite|pagar|pago|precio|costo|cuesta|arriendo|renta|alquiler|"
        r"cuota|mensualidad|alicuota|expensas|usd|dolar(?:es)?|mxn|pesos)\b|\$"),
    BuyerFieldV0.BEDROOMS_MIN: re.compile(
        r"\b(?:dormitorios?|habitacion(?:es)?|cuartos?|recamaras?|bedrooms?)\b"),
    BuyerFieldV0.AREA_M2_MIN: re.compile(
        r"\b(?:m2|mts2|metros?|area|superficie|metraje)\b|m²"),
}


# ── la cláusula ─────────────────────────────────────────────────────────────────────────


class _Frase(NamedTuple):
    inicio: int
    fin: int
    direccional: bool                  # tiene operador de dirección propio
    cantidad: bool                     # es una cantidad del inmueble, no una dimensión


def _a_decimal(token: str) -> Decimal:
    return Decimal(token.replace(".", "").replace(",", ""))


def _encajes(patrones, clausula: str) -> list[tuple[int, int, Decimal, str]]:
    return [(m.start(), m.end(), _a_decimal(m.group("n")), m.group(0))
            for p in patrones for m in p.finditer(clausula)]


def _dentro(pos: int, tramos) -> bool:
    return any(ini <= pos < fin for ini, fin, *_ in tramos)


def _gramatica(cur: str | None) -> dict:
    tope = cur or _MONEDA_GENERICA
    return {
        BuyerFieldV0.BUDGET_MAX: (_liga_presupuesto(tope), _candidatos_presupuesto(tope)),
        BuyerFieldV0.BEDROOMS_MIN: (_LIGA_DORMITORIOS, _CANDIDATOS_DORMITORIOS),
        BuyerFieldV0.AREA_M2_MIN: (_LIGA_AREA, _CANDIDATOS_AREA),
    }


def _opuestas(dim: BuyerFieldV0, cur: str | None):
    """Las formas del OTRO extremo de la misma dimensión: el piso de un tope, el techo de un
    mínimo. No son rivales del valor, son su rango."""
    if dim is BuyerFieldV0.BUDGET_MAX:
        return _pisos_de_presupuesto(cur or _MONEDA_GENERICA)
    return _TECHOS_DORMITORIOS if dim is BuyerFieldV0.BEDROOMS_MIN else _TECHOS_AREA


def _direccional(dim: BuyerFieldV0, texto: str) -> bool:
    return dim is not BuyerFieldV0.BUDGET_MAX or bool(_DIRECCIONAL_TOPE.search(texto))


def _frases_ajenas(clausula: str, dim: BuyerFieldV0) -> list[_Frase]:
    """Frases de las OTRAS dimensiones y cantidades del inmueble."""
    frases: list[_Frase] = []
    for d, (ligan, mencionan) in _gramatica(None).items():
        if d is dim:
            continue
        ligadas = [_Frase(a, b, _direccional(d, t), False)
                   for a, b, _n, t in _encajes(ligan, clausula)]
        frases += ligadas
        frases += [_Frase(a, b, False, False) for a, b, *_ in _encajes(mencionan, clausula)
                   if not any(f.inicio <= a and b <= f.fin for f in ligadas)]
    frases += [_Frase(m.start(), m.end(), False, True)
               for m in _CANTIDADES_DEL_INMUEBLE.finditer(clausula)]
    return frases


def _tiempos(clausula: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _FRASE_DE_TIEMPO.finditer(clausula)]


def _invertida(clausula, tramo, dim, ajenas, tiempos) -> bool:
    """¿Un marcador de la dirección contraria, pegado al valor, lo invalida?"""
    ini, fin, _, texto = tramo
    antes_re, despues_re = _reversa(dim)
    marcas = []
    m = antes_re.search(clausula, 0, ini)
    if m is not None:
        marcas.append(m.start())
    m = despues_re.match(clausula, fin)
    if m is not None and m.end() > fin:
        marcas.append(m.end() - 1)
    for pos in marcas:
        if _dentro(pos, tiempos):
            continue                                  # complemento de tiempo, no dirección
        if not (_dentro(pos, ajenas) and _direccional(dim, texto)):
            return True
    return False


def _operador_compartido(clausula, tramo, ajenas) -> bool:
    """«900 USD mínimo 3 dormitorios», «2 dormitorios al menos 900 USD de presupuesto»: el
    operador del valor está pegado a otra frase que no tiene el suyo DIRECCIONAL, así que puede
    ser de las dos."""
    ini, fin, _, texto = tramo
    for f in ajenas:
        if f.direccional:
            continue
        if f.fin <= ini and not clausula[f.fin:ini].strip() and _OP_AL_INICIO.match(texto):
            if f.cantidad or not _NUNCA_POSPUESTO.match(texto):
                return True
        if fin <= f.inicio and not clausula[fin:f.inicio].strip() and _OP_AL_FINAL.search(texto):
            return True
    return False


def _de_ajeno(clausula, tramo, dim, ajenas) -> bool:
    """«<X> de <valor>»: el valor habla de X."""
    ini = tramo[0]
    m = re.search(r"\bde\s+(?:un\s+|una\s+)?$", clausula[:ini])
    if m is None:
        return False
    izquierda = clausula[:m.start()].rstrip()
    if any(f.inicio < len(izquierda) <= f.fin for f in ajenas):
        return True                                   # «3 dormitorios de al menos 12 m2»
    palabras = re.findall(r"[^\W\d_]+", _HUECO_DE_LUGAR.sub(" ", izquierda))
    if not palabras:
        return False                                  # «de 3 dormitorios para arriba»
    if dim is BuyerFieldV0.BEDROOMS_MIN:
        return palabras[-1] in _AJENOS_DE_DORMITORIOS
    while palabras and (palabras[-1] in _ADJETIVOS_DEL_INMUEBLE
                        or palabras[-1] in ("en", "el", "la", "los", "las", "del")):
        palabras.pop()
    return not palabras or palabras[-1] not in _SUJETO_DE   # sólo adjetivos: ¿de qué?


_ENLACE = re.compile(r"\b(?:tiene que ser|debe ser|que|cueste|cuesten|sea|sean|salga|salgan|"
                     r"valga|valgan|tenga|tengan|este|esten|de|es|sera|seria)\b")


def _amenidad_pegada(clausula, tramo, dim) -> bool:
    """«depa con parqueadero máximo 50 USD», «depa con alícuota QUE SEA DE máximo 80 USD»: el
    tope puede ser el de la amenidad. Las palabras de enlace no separan (revisión R2)."""
    if dim is not BuyerFieldV0.BUDGET_MAX:
        return False
    return any(not _ENLACE.sub(" ", clausula[m.end():tramo[0]]).strip()
               for m in _AMENIDAD.finditer(clausula, 0, tramo[0]))


def _tachar(texto: str, tramos) -> str:
    chars = list(texto)
    for ini, fin, *_ in tramos:
        for i in range(ini, fin):
            chars[i] = " "
    return "".join(chars)


def _limpiar(resto: str, dim: BuyerFieldV0) -> str:
    resto = _HUECO_DE_LUGAR.sub(" ", resto)
    for hueco in _HUECOS_COMUNES + _HUECOS_POR_DIMENSION[dim]:
        resto = hueco.sub(" ", resto)
    if dim is not BuyerFieldV0.BUDGET_MAX:
        resto = _BENEFICIARIOS.sub(" ", resto)
    return resto


def _palabras_ajenas(texto: str, permitidas=_NEUTRAS) -> list[str]:
    return [p for p in re.findall(r"[^\W\d_]+", texto) if p not in permitidas]


def _clausula_acredita(clausula: str, valor, dim: BuyerFieldV0, cur: str | None) -> str | None:
    """El resto limpio de la cláusula si acredita el valor —sirve para saber si el valor tiene
    sujeto propio—, o `None`."""
    ligan, mencionan = _gramatica(cur if dim is BuyerFieldV0.BUDGET_MAX else None)[dim]
    ligadas = _encajes(ligan, clausula)
    propias = ligadas + _encajes(mencionan, clausula)
    if {t[2] for t in propias} != {valor}:
        return None                                   # candidatos: exactamente este valor
    elegidas = [t for t in ligadas if t[2] == valor]
    if not elegidas:
        return None                                   # sin su operador no liga
    ajenas = _frases_ajenas(clausula, dim)
    tiempos = _tiempos(clausula)
    if any(a < f.fin and f.inicio < b for a, b, *_ in propias for f in ajenas):
        return None                                   # solape: el operador es de las dos
    tachar = [(a, b) for a, b, *_ in propias] + [(f.inicio, f.fin) for f in ajenas] + tiempos
    for tramo in elegidas:
        if (_invertida(clausula, tramo, dim, ajenas, tiempos)
                or _operador_compartido(clausula, tramo, ajenas)
                or _de_ajeno(clausula, tramo, dim, ajenas)
                or _amenidad_pegada(clausula, tramo, dim)):
            return None
        rango = re.search(r"\bdesde\s+(?:\$\s*)?\d[\d.,]*\s+$", clausula[:tramo[0]])
        if rango is not None and tramo[3].startswith("hasta"):
            tachar.append((rango.start(), tramo[0]))  # «desde 700 hasta 900 USD»
    resto = _limpiar(_tachar(clausula, tachar), dim)
    if _DIGITO.search(resto) or _palabras_ajenas(resto):
        return None
    return resto


# ── el mensaje ──────────────────────────────────────────────────────────────────────────


def _sobrante(clausula: str, dim: BuyerFieldV0, cur: str | None):
    """(frases propias, frases del otro extremo, lo que queda sin reconocer)."""
    ligan, mencionan = _gramatica(cur if dim is BuyerFieldV0.BUDGET_MAX else None)[dim]
    propias = _encajes(ligan, clausula) + _encajes(mencionan, clausula)
    opuestas = [(a, b) for a, b, *_ in _encajes(_opuestas(dim, cur), clausula)]
    ajenas = [(f.inicio, f.fin) for f in _frases_ajenas(clausula, dim)]
    resto = _tachar(clausula, [(a, b) for a, b, *_ in propias] + opuestas + ajenas
                    + _tiempos(clausula))
    return propias, opuestas, _CONTEO.sub(" ", _limpiar(resto, dim))


def _reconocida(clausula: _Clausula, dim: BuyerFieldV0, cur: str | None) -> bool:
    """No queda nada sin entender: requisitos de otras dimensiones, cortesía, lugar, tiempo,
    conteos de personas o de cosas. Una cláusula así no puede llevarse el valor."""
    _p, _o, resto = _sobrante(clausula.texto, dim, cur)
    return not (_DIGITO.search(resto) or _LETRA_NUMERO.search(resto) or _palabras_ajenas(resto))


def _otra_clausula_segura(clausula: str, valor, dim: BuyerFieldV0, cur: str | None) -> bool:
    """FAIL-CLOSED. Una cláusula con una SEÑAL de la dimensión —número en dígitos o en letras,
    unidad, operador, dirección, reparto— tiene que estar reconocida ENTERA; si no, no se sabe
    qué le hace al valor. Sin señal, habla de otra cosa y no cuenta.

    En R2 cada peligro tenía su propia regla (rival, eco, reparto, marca suelta) y todas fallaban
    ABIERTAS: bastaba un dígito o una palabra fuera de la lista para desactivarlas.
    """
    propias, opuestas, resto = _sobrante(clausula, dim, cur)
    if any(n != valor and not any(a <= i and f <= b for a, b in opuestas)
           for i, f, n, _t in propias):
        return False                                  # otro valor de la misma dimensión: rival
    senal = bool(propias or opuestas or _SENAL_NUMERICA.search(resto)
                 or _SENAL_DE_REPARTO.search(resto) or _SENAL_DE_DIRECCION.search(resto)
                 or _SENAL_DE_DIMENSION[dim].search(resto))
    if not senal:
        return True
    return not (_DIGITO.search(resto) or _LETRA_NUMERO.search(resto)
                or _palabras_ajenas(resto))


_SINTAGMA_NOMINAL = re.compile(r"\s*(?:el|la|los|las|un|una|unos|unas|mi|mis|su|sus|nuestro|"
                               r"nuestra|nuestros|nuestras|lo de|lo del)\s+[^\W\d_]+")
_RELATIVO = re.compile(r"\s*(?:y\s+)?(?:que|cuyo|cuya|donde)\b")
_PREPOSICION_INICIAL = re.compile(r"\s*(?:para|de|del|en|por|con|a|al)\b")


def _es_etiqueta(texto: str, dim: BuyerFieldV0) -> bool:
    """«Parqueadero», «Alícuota»: hasta tres palabras, todas determinantes o desconocidas. Un
    verbo o una muletilla neutra —«Estoy sola», «Busco depa»— NO es una etiqueta; si lo fuera, el
    veredicto dependería de adjetivos que describen a la persona.

    En DORMITORIOS no se aplica: una etiqueta suelta ahí es casi siempre el lugar («Cumbayá - 80
    m2 - 3 dormitorios mínimo») y lo único que puede tener dormitorios y no ser el inmueble es un
    edificio, que ya cubren `_AJENOS_DE_DORMITORIOS` y el sintagma nominal.
    """
    if dim is BuyerFieldV0.BEDROOMS_MIN:
        return False
    palabras = re.findall(r"[^\W\d_]+", texto)
    return (1 <= len(palabras) <= 3
            and all(p in _DETERMINANTES or p not in _NEUTRAS for p in palabras))


def _acaba_en_amenidad(texto: str) -> bool:
    return any(m.end() == len(texto.rstrip()) for m in _AMENIDAD.finditer(texto))


def _tema_ajeno(clausulas: list[_Clausula], i: int, resto_valor: str, dim: BuyerFieldV0,
                cur: str | None) -> bool:
    """¿El valor, que no tiene sujeto propio, se lo lleva el TEMA de una cláusula vecina?

    T1  valor desnudo («máximo 50 USD») detrás de un sintagma nominal o una etiqueta ajenos
        —«El parqueadero, por favor. Máximo 50 USD»—, saltando las cláusulas ya reconocidas. Un
        requisito listado con coma («…, parqueadero, máximo 800 USD») NO es un tema: el tema
        lleva determinante.
    T1b en el ÁREA, una vecina que TERMINA nombrando una amenidad —«casa con jardín amplio y
        bonito, mínimo 50 m2»—: los 50 m2 pueden ser del jardín. Misma política que dentro de la
        cláusula, donde el área no admite amenidades como hueco.
    T2  valor en relativo («…, que tenga al menos 100 m2»): su antecedente es la última palabra
        de la cláusula anterior.
    T3  valor seguido de un complemento ajeno —«Máximo 50 USD, por favor, para el parqueadero»—.
    T4  valor que empieza por un adjetivo: continúa la cláusula anterior.
    """
    actual = clausulas[i].texto
    desnudo = not [p for p in re.findall(r"[^\W\d_]+", resto_valor) if p not in _PARTICULAS]
    j = i - 1
    while j >= 0 and _reconocida(clausulas[j], dim, cur):
        j -= 1
    if desnudo and j >= 0:
        vecina = clausulas[j].texto
        if _palabras_ajenas(_limpiar(vecina, dim)) and (_SINTAGMA_NOMINAL.match(vecina)
                                                        or _es_etiqueta(vecina, dim)):
            return True                                                              # T1
        if dim is BuyerFieldV0.AREA_M2_MIN and _acaba_en_amenidad(vecina):
            return True                                                              # T1b
    if _RELATIVO.match(actual) and i > 0:
        antecedente = re.findall(r"[^\W\d_]+", _limpiar(clausulas[i - 1].texto, dim))
        if antecedente and antecedente[-1] not in _NEUTRAS:
            return True                                                              # T2
    j = i + 1
    while j < len(clausulas) and _reconocida(clausulas[j], dim, cur):
        j += 1
    if j < len(clausulas) and any(c.pausa_antes for c in clausulas[i + 1:j + 1]):
        vecina = clausulas[j].texto
        if (_PREPOSICION_INICIAL.match(vecina) and not _HAY_NUMERO.search(vecina)
                and _palabras_ajenas(_limpiar(vecina, dim))):
            return True                                                              # T3
    primera = re.match(r"\s*(?:el\s+|la\s+)?([^\W\d_]+)", actual)
    if (primera and primera.group(1) in _ADJETIVOS_DEL_INMUEBLE and i > 0
            and _palabras_ajenas(_limpiar(clausulas[i - 1].texto, dim))):
        return True                                                                  # T4
    return False


def _valor_ligado(plano: str, valor, dim: BuyerFieldV0, cur: str | None = None) -> bool:
    """¿Alguna cláusula AFIRMATIVA liga EXACTAMENTE este valor a su dimensión, dentro de la
    gramática cerrada, sin que ninguna otra cláusula del MENSAJE lo ponga en duda?"""
    clausulas = _preparar(plano)
    for i, clausula in enumerate(clausulas):
        texto = _SIN_QUE_NO_NIEGA.sub(" ", _TOPE_NEGADO.sub(" ", clausula.texto))
        if clausula.interrogativa or _NEGACION.search(texto):
            continue                                  # pregunta o negación: no declara
        resto = _clausula_acredita(clausula.texto, valor, dim, cur)
        if resto is None:
            continue
        if _tema_ajeno(clausulas, i, resto, dim, cur):
            continue
        if all(_otra_clausula_segura(c.texto, valor, dim, cur)
               for j, c in enumerate(clausulas) if j != i):
            return True
        return False                                  # una señal que no se entiende: ambiguo
    return False


def _evidencia_budget(mutacion, plano: str) -> bool:
    moneda = _patron_de_moneda(mutacion.currency)
    if moneda is None:
        return False
    return _valor_ligado(plano, mutacion.amount, BuyerFieldV0.BUDGET_MAX, moneda.pattern)


def _evidencia_bedrooms(mutacion, plano: str) -> bool:
    return _valor_ligado(plano, mutacion.bedrooms_min, BuyerFieldV0.BEDROOMS_MIN)


def _evidencia_area(mutacion, plano: str) -> bool:
    return _valor_ligado(plano, mutacion.area_m2_min, BuyerFieldV0.AREA_M2_MIN)


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
                      r"excluyentes?|si o si|sin excepcion(?:es)?)")
"""R2d · sin `obligatorio`: en WhatsApp «lo de las mascotas es obligatorio» es tan a menudo
una PREGUNTA sin signos («¿tengo que contestarlo?») como una declaración."""
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

_LOCUCION_NEUTRA = re.compile(r"\bsin (?:duda|problema|problemas)\b|\bun poco\b")
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
    invertir invierto inversion buy purchase rent invest
    usd dolar dolares mxn pesos
    dormitorio dormitorios habitacion habitaciones cuarto cuartos recamara recamaras
    m2 m² metros metro cuadrados cuadrado superficie area
    mascota mascotas perro perros gato gatos pet pets acepte acepten admita admitan permita
    permitan
    ya no quita quitar quitame elimina eliminar borra borrar olvida olvidar descarta descartar
""".split())
"""Qué palabras puede traer una cláusula de VALOR para contar como parte reconocida del
mensaje. El verificador de cada mutación es permisivo con lo que rodea al valor —su trabajo es
otro—, así que «mi esposo dice que máximo 900 USD» lo acredita igual. Para la cobertura de
ESTRICTA no basta: la cláusula tiene que ser SÓLO valor. Otra lista blanca, no una negra."""


def _solo_vocabulario_de_valor(clausula: str) -> bool:
    return all(t in _VOCABULARIO_DE_VALOR or t.replace(".", "").replace(",", "").isdigit()
               for t in clausula.split())


_DISYUNCION = re.compile(r"\bo\b(?!\s+mas\b)")
_PISO = re.compile(r"\b(?:desde|minimo|al menos|mas de)\b")


def _es_valor(clausula: str, valores) -> list:
    """Las durables del mensaje que ESTA cláusula acredita por sí sola, y sin nada más.

    R2d · una disyunción («3 recámaras o 150 m2») no es un valor: es una alternativa, y
    reconocerla como parte de una declaración estricta endurecería sólo una de las dos."""
    if not _solo_vocabulario_de_valor(clausula) or _DISYUNCION.search(clausula):
        return []
    return [m for m in valores if _VERIFICADOR[type(m)](m, clausula)]


def _valor_de(clausula: str, campo: BuyerFieldV0, valores) -> bool:
    """¿La cláusula es un valor DECLARADO de ESE campo que termina en su ancla?

    R2d · sólo un `Set*`: «ya no quiero al menos 2 dormitorios sí o sí» acredita el RETIRO,
    y un marcador pegado a un retiro no endurece nada. Y un tope no puede ser un piso:
    «presupuesto desde 900 USD, innegociable» no declara un máximo."""
    declarados = [m for m in _es_valor(clausula, valores)
                  if campo_de_mutacion(m) is campo
                  and isinstance(m, (SetBudgetMax, SetBedroomsMin, SetAreaM2Min, SetPetsRequired))]
    if not declarados:
        return False
    if campo is BuyerFieldV0.BUDGET_MAX and _PISO.search(clausula):
        return False
    return bool(re.search(rf"\b{_ANCLA_DEL_VALOR[campo]}\s*$", clausula))


def _acredita_estricta(campo: BuyerFieldV0, plano: str, valores) -> bool:
    if "?" in plano or "¿" in plano:
        return False
    if _acredita_flexible(campo, plano):
        return False          # R2d · el mismo mensaje también la declara flexible
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
        ultima = i == len(clausulas) - 1 or all(_CORTESIA.match(x) for x in clausulas[i + 1:])
        if _solo_marcador(c) and i > 0 and ultima and _valor_de(clausulas[i - 1], campo, valores):
            # R2d · sólo como CIERRE: «Indispensable: que acepten mascotas» encabeza lo que
            # viene después, y atarlo a lo anterior endurecía la dimensión equivocada.
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
