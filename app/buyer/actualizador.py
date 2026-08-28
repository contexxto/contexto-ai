"""E3.2b.3 · Buyer Updater Orchestrator — la única costura que escribe memoria del comprador.

```
buyer_id autenticado + IdentifiedUserMessage
        ↓  cargar_ultima
        ↓  interpretar_mensaje      modelo · falible
        ↓  reducir                  puro
        ↓  anexar_revision          idempotencia + concurrencia en la BASE
        ↓
ResultadoUpdater tipado
```

Las piezas ya existían y estaban probadas por separado. Lo que faltaba —y es de lo que trata
este módulo— es **qué significa procesar exactamente una vez un mensaje** cuando hay fallos,
mensajes que no cambian nada, y dos conversaciones tocando al mismo comprador a la vez.

## El vacío y el no-op NO son lo mismo, y confundirlos rompe la idempotencia

`interpretar_mensaje` degrada cualquier fallo del proponente a cero propuestas. Así que "no
hay nada que escribir" tiene dos causas con consecuencias opuestas:

```
LOTE VACÍO            el modelo falló, o no dijo nada del comprador
                      → NO se persiste · NO se sella el mensaje · reintentable

LOTE CON TURN_ONLY    se entendió el mensaje y resultó no ser preferencia
o REJECTED            → SÍ se persiste una revisión sin cambio semántico
```

**Por qué se persiste algo que no cambia nada.** Sin esa revisión, un mensaje interpretado hoy
como `TURN_ONLY` no deja rastro; si un reintento futuro lo interpretara como `DURABLE`, el
store no tendría contra qué comparar y la divergencia entraría como estado nuevo. Con la
revisión no-op:

```
primer intento   TURN_ONLY  →  revisión N, mismo estado semántico
reintento        DURABLE    →  mismo source_message_id, estado distinto
                            →  BuyerIdempotencyConflict
```

Eso convierte la idempotencia en una propiedad **del mensaje procesado**, no sólo de los
mensajes que casualmente mutaron algo. La alternativa sería una tabla de
`processed_message_id` aparte; con revisiones no-op no hace falta infraestructura nueva.

## Concurrencia entre mensajes · la misma filosofía que C1-C5, un nivel arriba

El store impide el *lost update* levantando `BuyerRevisionConflict`, pero no decide qué hacer
después. Aquí sí:

```
A toca budget · B toca bedrooms   disjuntos  →  rebase sobre la última y reintento
A toca budget · B toca budget     solapan    →  CONFLICTO · nunca last-write-wins
A no toca nada (TURN_ONLY)        ∅          →  rebase seguro
```

Las rutas tocadas incluyen las de las `AMBIGUOUS`, no sólo las durables: abrir una pregunta
sobre el presupuesto también es tocar el presupuesto, y dos conversaciones haciéndolo a la vez
no son disjuntas.

## Lo que NO hace

No toca el grafo, no responde al usuario y no repregunta. Devuelve un resultado tipado para
que el wiring de E3.2b.4 no tenga que inferir el desenlace de excepciones o de `None` — y para
que **alguien** consuma los `unresolved_questions`, que es lo único que cierra el ciclo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.buyer.extractor import AfirmacionAmbiguous, AfirmacionDurable
from app.buyer.interprete import interpretar_mensaje
from app.buyer.reductor import reducir, ruta_de_campo
from app.buyer.store import (
    BuyerIdempotencyConflict,
    BuyerRevisionConflict,
    anexar_revision,
    cargar_ultima,
)
from app.contracts.buyer_v0 import BuyerContextV0

logger = logging.getLogger(__name__)


class EstadoActualizacion(StrEnum):
    """El desenlace, explícito. **Ninguno se infiere de una excepción ni de un `None`.**

    Que el shadow wiring tenga que distinguir "no se escribió porque el modelo falló" de "no
    se escribió porque ya estaba hecho" leyendo tipos de excepción sería pedirle que reconstruya
    una decisión que aquí ya se tomó.
    """

    CREADA = "creada"
    """Revisión nueva con cambio semántico real."""

    NO_OP = "no_op"
    """Revisión nueva SIN cambio semántico. Existe para sellar el `source_message_id`."""

    REPLAY = "replay"
    """Ya estaba procesado con el mismo resultado. Se devuelve lo que había."""

    VACIO = "vacio"
    """Cero propuestas: no se escribió y **el mensaje sigue sin procesar**. Reintentable."""

    CONFLICTO = "conflicto"
    """Otra conversación tocó las mismas rutas. No se escribió: nunca last-write-wins."""

    FALLIDO = "fallido"
    """El mismo mensaje ya produjo un estado DISTINTO. Divergencia real, no se traga."""


@dataclass(frozen=True)
class ResultadoUpdater:
    estado: EstadoActualizacion
    contexto: BuyerContextV0 | None = None
    revision: int | None = None
    motivo: str | None = None

    @property
    def persistido(self) -> bool:
        return self.estado in (EstadoActualizacion.CREADA, EstadoActualizacion.NO_OP,
                               EstadoActualizacion.REPLAY)

    @property
    def procesado(self) -> bool:
        """¿Queda el mensaje sellado? **`VACIO` no lo sella**, y ésa es la diferencia que
        justifica tener dos estados en vez de uno."""
        return self.persistido


# ── Rutas tocadas · la unidad de la concurrencia ───────────────────────────────────


def rutas_tocadas(lote) -> frozenset[str]:
    """Las rutas del contrato que este lote pretende afectar.

    Incluye las de las `AMBIGUOUS`, no sólo las durables: abrir una pregunta sobre el
    presupuesto también reclama el presupuesto, y si otra conversación lo cambió a la vez, las
    dos actualizaciones no son independientes por mucho que una sólo escriba la pregunta.
    """
    rutas = set()
    for afirmacion in lote.afirmaciones:
        if isinstance(afirmacion, AfirmacionDurable):
            rutas.add(ruta_de_campo(afirmacion.campo))
        elif isinstance(afirmacion, AfirmacionAmbiguous):
            rutas.add(ruta_de_campo(afirmacion.campo))
    return frozenset(rutas)


_LECTORES = {
    "objective": lambda c: c.objective,
    "financial.budget_max": lambda c: c.financial.budget_max,
    "property_requirements.bedrooms_min": lambda c: c.property_requirements.bedrooms_min,
    "property_requirements.area_m2_min": lambda c: c.property_requirements.area_m2_min,
    "property_requirements.pets_allowed_required":
        lambda c: c.property_requirements.pets_allowed_required,
}
"""Cerrado sobre las cinco rutas de V0. Si aparece una sexta, el meta-test la caza."""


def rutas_divergentes(base: BuyerContextV0 | None, otro: BuyerContextV0) -> frozenset[str]:
    """Qué rutas cambiaron entre el estado que leímos y el que hay ahora.

    Se comparan también las preguntas abiertas: si otra conversación abrió un `unresolved`
    sobre una ruta, esa ruta está en disputa aunque su valor no haya cambiado.
    """
    if base is None:
        return frozenset(_LECTORES)
    distintas = {ruta for ruta, leer in _LECTORES.items() if leer(base) != leer(otro)}
    preguntas_base = {q.about_field for q in base.unresolved_questions}
    preguntas_otro = {q.about_field for q in otro.unresolved_questions}
    return frozenset(distintas | (preguntas_base ^ preguntas_otro) - {None})


# ── El orquestador ─────────────────────────────────────────────────────────────────


def _contexto_inicial(buyer_id: str, retrieved_at: datetime) -> BuyerContextV0:
    """El comprador que nunca tuvo estado. **No inventa semántica temporal.**

    `updated_at` es obligatorio en el contrato pero el store lo REESCRIBE al persistir con el
    instante real de la escritura, y `_canonico` lo excluye de la comparación. Se pasa
    `retrieved_at` —que es un instante verdadero, el del procesamiento— en vez de un `now()`
    nuevo: no añade una cuarta fuente de tiempo a una capa que acaba de separar tres.
    """
    return BuyerContextV0(buyer_id=buyer_id, context_revision=None, updated_at=retrieved_at)


async def actualizar(
    buyer_id: str,
    mensaje,
    *,
    retrieved_at: datetime,
    proponente=None,
    db=None,
) -> ResultadoUpdater:
    """Procesa UN mensaje contra la memoria del comprador. La única costura que escribe.

    `buyer_id` tiene que venir de `claims.sub` — la raíz autenticada, nunca de un cuerpo de
    petición ni del modelo. Un anónimo no puede crear estado durable, y por eso el vacío se
    rechaza aquí en vez de dejar que el store lo descubra: un `buyer_id` vacío que llega al
    store ya viajó por media aplicación.
    """
    if not (buyer_id or "").strip():
        return ResultadoUpdater(
            EstadoActualizacion.FALLIDO,
            motivo="sin comprador autenticado: un anónimo no crea estado durable")

    lote = await interpretar_mensaje(mensaje, proponente)

    if not lote.afirmaciones:
        # Cero propuestas puede ser un fallo del modelo. Sellar el mensaje aquí lo daría por
        # procesado para siempre; dejarlo sin sellar permite reintentarlo.
        return ResultadoUpdater(
            EstadoActualizacion.VACIO,
            motivo="el intérprete no produjo afirmaciones: no se sella el mensaje")

    tocadas = rutas_tocadas(lote)
    base = await cargar_ultima(buyer_id, db=db)

    for intento in (1, 2):
        contexto_base = base if base is not None else _contexto_inicial(buyer_id, retrieved_at)
        candidato = reducir(contexto_base, lote, retrieved_at)
        try:
            persistida = await anexar_revision(
                buyer_id, mensaje.message_id, candidato,
                expected_revision=contexto_base.context_revision, db=db)
        except BuyerIdempotencyConflict as e:
            return ResultadoUpdater(EstadoActualizacion.FALLIDO, motivo=str(e))
        except BuyerRevisionConflict as e:
            if intento == 2:
                return ResultadoUpdater(EstadoActualizacion.CONFLICTO, motivo=str(e))
            ultima = await cargar_ultima(buyer_id, db=db)
            if ultima is None:
                return ResultadoUpdater(EstadoActualizacion.CONFLICTO, motivo=str(e))
            solapan = tocadas & rutas_divergentes(base, ultima)
            if solapan:
                # NO last-write-wins. Es C1 entre mensajes: dos declaraciones sobre la misma
                # dimensión, sin nada que autorice elegir una, no se resuelven adivinando.
                return ResultadoUpdater(
                    EstadoActualizacion.CONFLICTO,
                    motivo=f"otra conversación tocó {sorted(solapan)} desde la base leída")
            logger.info("rebase del updater sobre la revisión %s (disjunto de %s)",
                        ultima.context_revision, sorted(tocadas))
            base = ultima
            continue

        return _clasificar(persistida, contexto_base)

    return ResultadoUpdater(EstadoActualizacion.CONFLICTO,
                            motivo="no se pudo rebasar sobre el estado vigente")


def _clasificar(persistida, contexto_base: BuyerContextV0) -> ResultadoUpdater:
    """Traduce lo que hizo el store a un desenlace que el llamante pueda leer sin adivinar.

    `creada=False` es el replay: el mensaje ya estaba procesado con el mismo resultado. Se
    distingue de `NO_OP` —que sí escribió— porque no es lo mismo *"ya estaba hecho"* que
    *"acabo de sellar un mensaje que no cambió nada"*.
    """
    if not persistida.creada:
        return ResultadoUpdater(EstadoActualizacion.REPLAY, persistida.contexto,
                                persistida.revision,
                                motivo="el mensaje ya se había procesado con el mismo estado")

    from app.buyer.store import _canonico

    cambio = _canonico(persistida.contexto) != _canonico(contexto_base)
    return ResultadoUpdater(
        EstadoActualizacion.CREADA if cambio else EstadoActualizacion.NO_OP,
        persistida.contexto, persistida.revision,
        motivo=None if cambio else "sin cambio semántico; la revisión sella el mensaje")
