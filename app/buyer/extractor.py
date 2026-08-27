"""E3.2b.1 · Extractor + routing situacional — la capa determinista.

Convierte **un** `IdentifiedUserMessage` en un lote ordenado de decisiones: qué del mensaje
es estado durable del comprador, qué es contexto del turno, qué es ambiguo y qué no debe
crear estado.

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

## Routing POR AFIRMACIÓN, no por mensaje

Un mensaje mezcla cosas. *"Quiero comprar, máximo 120000 USD y algo tranquilo"* tiene dos
hechos persistibles y uno que no lo es; tratar el mensaje como una sola disposición
perdería los dos primeros por culpa del tercero.

## Lo que NO hace

No aplica mutaciones, no construye `BuyerContextV0`, no toca el store, no crea
`field_evidence`, no resuelve conflictos entre mensajes y no detecta novedad —*identificado
≠ nuevo*: eso lo resuelve el store por `(buyer_id, source_message_id)`.
"""

from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.buyer.boundary import (
    BuyerMutationV0,
    Disposicion,
    SetAreaM2Min,
    SetBedroomsMin,
    SetBudgetMax,
    SetObjective,
    SetPetsRequired,
    ruta_contractual,
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

    Los `Clear*` no aparecen aquí: su autorización es la retractación explícita, que resuelve
    `resolver_intramensaje`. Mezclar las dos comprobaciones haría que un `CLEAR` legítimo
    exigiera vocabulario de la dimensión que está borrando.
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


# ── El resultado por afirmación ────────────────────────────────────────────────────


class Afirmacion(BaseModel):
    """Una decisión sobre UN hecho del mensaje. Reutiliza `Disposicion` de la frontera: dos
    vocabularios para lo mismo divergirían."""

    model_config = _CERRADO

    disposicion: Disposicion
    mutacion: BuyerMutationV0 | None = None
    motivo: str = Field(min_length=1)

    @model_validator(mode="after")
    def _solo_durable_muta(self) -> Afirmacion:
        if self.disposicion is Disposicion.DURABLE and self.mutacion is None:
            raise ValueError("DURABLE exige mutación")
        if self.disposicion is not Disposicion.DURABLE and self.mutacion is not None:
            raise ValueError(f"{self.disposicion} no puede llevar mutación")
        return self

    @property
    def ruta(self) -> str | None:
        return ruta_contractual(self.mutacion) if self.mutacion is not None else None


class LoteExtraccion(BaseModel):
    """Lo que un mensaje produce. **Ordenado y con una sola mutación durable por ruta.**

    El orden importa porque sin él no se puede describir *"dijo A y luego B"*. La unicidad por
    ruta importa más: si llegaran dos mutaciones del mismo path sin resolver, el reducer las
    aplicaría en orden y **ganaría la última** — que es un *last-write-wins* dentro del
    mensaje, exactamente la política que C1 prohíbe.

    Por eso el lote **no se puede construir** en ese estado. Es un fallo del extractor, no
    algo que el reducer deba arreglar.
    """

    model_config = _CERRADO

    source_message_id: str = Field(min_length=1)
    afirmaciones: tuple[Afirmacion, ...] = ()

    @model_validator(mode="after")
    def _una_mutacion_por_ruta(self) -> LoteExtraccion:
        rutas = [a.ruta for a in self.afirmaciones if a.ruta is not None]
        repetidas = {r for r in rutas if rutas.count(r) > 1}
        if repetidas:
            raise ValueError(
                f"dos mutaciones durables para {sorted(repetidas)}: el conflicto se resuelve "
                f"en el extractor (C4), no dejando que el orden decida"
            )
        return self

    @property
    def mutaciones(self) -> tuple:
        """Solo las durables, en orden. Es lo que consumirá el reducer de E3.2b.2."""
        return tuple(a.mutacion for a in self.afirmaciones
                     if a.disposicion is Disposicion.DURABLE)


# ── C1-C5 · la política intramensaje ───────────────────────────────────────────────

# OJO con el `\b` final: las alternativas que acaban en signo de puntuación —`no,`— nunca
# casarían, porque tras la coma viene un espacio y ahí no hay frontera de palabra. Van en su
# propia rama. Lo destapó el primer smoke test: "quiero comprar... no, alquilar" daba
# `corr=False` y la corrección se perdía en silencio.
_CORRECCION = re.compile(
    r"\bno[,.]|"
    r"\b(mejor|en realidad|realmente|perdon|perdona|disculpa|"
    r"me equivoque|corrijo|actually|rather)\b")

_DISYUNCION = re.compile(r"\b(o|u|or)\b")


def hay_autocorreccion(texto: str) -> bool:
    """¿El mensaje marca EXPLÍCITAMENTE que se está corrigiendo?

    Sin marca explícita, dos declaraciones incompatibles son ambigüedad, no corrección (C3).
    Tratarlas como corrección sería adivinar cuál quiso decir — y adivinar en la dirección de
    "la última" es el *last-write-wins* que C1 prohíbe.
    """
    plano = _norm(texto)
    if _DISYUNCION.search(plano) and not _CORRECCION.search(plano):
        return False       # "comprar o alquilar" propone dos, no corrige una
    return bool(_CORRECCION.search(plano))


def resolver_intramensaje(afirmaciones, texto: str) -> tuple[Afirmacion, ...]:
    """Colapsa las afirmaciones que compiten por la misma ruta. C1-C5.

    ```
    A · misma ruta, mismo valor      → deduplica
    B · misma ruta, valores distintos + autocorrección explícita → la última
    C · misma ruta, valores distintos SIN autocorrección → AMBIGUOUS para esa ruta
    ```

    **La corrección SELECCIONA una declaración; no completa la que falte.** `"120000 USD…
    no, 100000"` no hereda la moneda: la segunda declaración está incompleta y por tanto
    nunca llegó a ser una mutación válida. Heredarla sería inventar procedencia.

    C5: lo que no compite por esa ruta **no se toca**. Un `REJECTED` no arrastra hechos
    independientes del mismo mensaje.
    """
    por_ruta: dict[str, list[Afirmacion]] = {}
    sueltas: list[Afirmacion] = []
    for a in afirmaciones:
        if a.ruta is None:
            sueltas.append(a)
        else:
            por_ruta.setdefault(a.ruta, []).append(a)

    resueltas: list[Afirmacion] = []
    for ruta, grupo in por_ruta.items():
        if len(grupo) == 1:
            resueltas.append(grupo[0])
            continue
        distintas = {a.mutacion for a in grupo}
        if len(distintas) == 1:                                   # A · repetición
            resueltas.append(grupo[0])
        elif hay_autocorreccion(texto):                           # B · corrección
            resueltas.append(grupo[-1])
        else:                                                     # C · conflicto
            resueltas.append(Afirmacion(
                disposicion=Disposicion.AMBIGUOUS,
                motivo=f"dos declaraciones incompatibles para {ruta} sin corrección explícita",
            ))

    # Se conserva el orden de aparición; las sueltas no compiten con nada.
    return tuple(sueltas + resueltas)


def construir_lote(mensaje, afirmaciones) -> LoteExtraccion:
    """El lote final: se resuelve el conflicto intramensaje ANTES de construirlo.

    El `source_message_id` sale del mensaje tal cual. **No se fabrica ni se deriva**: es lo
    que un `EvidenceRefV0` podrá citar, y un id sintético dejaría de apuntar a un
    `HumanMessage` que existe.
    """
    return LoteExtraccion(
        source_message_id=mensaje.message_id,
        afirmaciones=resolver_intramensaje(afirmaciones, mensaje.text),
    )
