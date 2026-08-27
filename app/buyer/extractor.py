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
es exigir que el texto **hable de la dimensión que se va a escribir**.

`autorizar_traduccion` es esa exigencia, y es determinista a propósito: un modelo no puede
tender el puente persona → requisito de propiedad porque el puente se comprueba fuera de él.

`[PENDIENTE · E3.2b.1a-B]` Esa guarda comprueba hoy **dimensión, no valor**: protege
`persona → dimensión incorrecta` y NO protege `dimensión correcta → valor inventado`. Los
`Clear*` además quedan autorizados por omisión. Se anota aquí para que la sección de arriba
no se lea como si la guarda ya estuviera completa.

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
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.buyer.boundary import (
    BuyerFieldV0,
    BuyerMutationV0,
    Disposicion,
    SetAreaM2Min,
    SetBedroomsMin,
    SetBudgetMax,
    SetObjective,
    SetPetsRequired,
    campo_de_mutacion,
)

_CERRADO = ConfigDict(frozen=True, extra="forbid")


def _norm(texto: str) -> str:
    """Minúsculas sin acentos. Comparar `"mínimo"` con `"minimo"` no es interpretar: es no
    fallar por una tilde."""
    plano = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in plano if unicodedata.category(c) != "Mn")


# ── La autorización semántica ──────────────────────────────────────────────────────
#
# Cada tipo de mutación exige que el texto hable de SU dimensión. No es un detector de
# intención —eso puede proponerlo un modelo— sino la condición sin la cual ninguna propuesta
# se acepta. El vocabulario es cerrado y se amplía a mano, con la misma disciplina que
# `encaje.DIMENSIONES`.

_MINIMO = r"(al menos|como minimo|minimo|minimum|at least|o mas|o más|en adelante|desde)"

_VOCABULARIO: dict[type, tuple[str, ...]] = {
    SetObjective: (r"\b(comprar|compra|adquirir|buy|purchase|"
                   r"alquilar|arrendar|rentar|rent|"
                   r"invertir|inversion|invest)\b",),
    SetBudgetMax: (r"\b(presupuesto|budget|maximo|max|hasta|tope)\b",),
    # La dimensión Y el mínimo, por separado: "2 dormitorios" nombra la dimensión pero no
    # declara un mínimo, y V0 solo modela mínimos.
    SetBedroomsMin: (r"\b(dormitorio|dormitorios|habitacion|habitaciones|"
                     r"cuarto|cuartos|recamara|recamaras|bedroom|bedrooms)\b", _MINIMO),
    SetAreaM2Min: (r"(\bm2\b|\bm²|metros? cuadrados?|square meters?)", _MINIMO),
    SetPetsRequired: (r"\b(mascota|mascotas|perro|perros|gato|gatos|pet|pets)\b",
                      r"\b(acepte|acepten|admita|admitan|permita|permitan|"
                      r"necesito|necesitamos|debe|tiene que|allowed|required)\b"),
}


class TraduccionNoAutorizada(Exception):
    """El texto no habla de la dimensión que la mutación quiere escribir.

    No es un error del usuario ni del modelo: es la guarda haciendo su trabajo. El caso que
    la justifica es `"tenemos dos niños"` → `SetBedroomsMin(2)`, donde la mutación es válida
    para el tipo y la inferencia es exactamente la que Fair Housing prohíbe.
    """


def autorizar_traduccion(mutacion, texto: str) -> None:
    """Levanta si el texto no da soporte explícito a la dimensión de la mutación.

    Comprueba **dimensión, no valor**: que el texto hable de presupuesto, no que hable de
    *este* presupuesto. Cerrar esa segunda mitad —y la autorización por omisión de los
    `Clear*`— es `[PENDIENTE · E3.2b.1a-B]`, no una propiedad que esta función ya tenga.

    Los `Clear*` no aparecen en `_VOCABULARIO`, y hay que ser exacto sobre lo que eso
    significa hoy: **no se comprueba nada sobre ellos**. `_VOCABULARIO.get` devuelve `None` y
    la función retorna sin validar, así que quedan **autorizados por omisión**. La intención
    es que su autorización sea la retractación explícita —y por eso no se les exige
    vocabulario de la dimensión que están borrando—, pero nadie la comprueba todavía:
    `resolver_intramensaje` resuelve conflictos entre declaraciones, no verifica que un
    `Clear` venga de una retractación. `[PENDIENTE · E3.2b.1a-B]`
    """
    patrones = _VOCABULARIO.get(type(mutacion))
    if patrones is None:
        return
    plano = _norm(texto)
    for patron in patrones:
        if not re.search(patron, plano):
            raise TraduccionNoAutorizada(
                f"{type(mutacion).__name__} sin soporte textual para su dimensión"
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
