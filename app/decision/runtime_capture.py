"""F3-DECISION-INPUT-BRIDGE-R0F · las ENTRADAS de la decisión visible, fuera del grafo.

El problema que resuelve, en una línea: las filas que decidieron el turno nacen y mueren
dentro de `construir_panel`, y quien conoce al comprador vive fuera del grafo. Nunca se
encuentran.

```
chat.py            conoce al principal · NO ve las filas
  └─ grafo
       └─ nodo encaje
            └─ construir_panel   ← aquí nacen las filas, y aquí mueren
```

## LA DIRECCIÓN IMPORTA, Y ES UNA SOLA

```
DECISIÓN / INVENTARIO  ──→  captura per-request  ──→  CHAT     ✅ esto
COMPRADOR              ──→  GRAFO                                ❌ nunca
```

Meter el estado del comprador hacia dentro habría sido más corto y está prohibido por algo
concreto: `AgentState` se checkpointea entero, y `get_checkpoint_metadata` copia a
`checkpoints.metadata` toda clave escalar de `configurable`. Una operación tan inocente como
la cadena `"require_pets"` acabaría escrita en la tabla de checkpoints. Así que el cable va
al revés: sale inventario, no entra comprador.

## POR QUÉ UNA CAJA MUTABLE Y NO UN `set()` DESDE DENTRO

Las tareas de asyncio **copian** el contexto al crearse. Un `set()` hecho dentro de una tarea
hija rebinda sólo su copia y no se ve desde fuera — medido, no supuesto. Lo que sí cruza es
la referencia: si quien abre el turno deja una caja MUTABLE en el `ContextVar`, las tareas
derivadas reciben esa misma caja y lo que depositen en ella se ve al volver.

De ahí la regla dura de este módulo: **el productor nunca hace `set()`, sólo deposita.** Sólo
el dueño del turno abre y cierra.

## LO QUE NO ES

No es un contrato público, ni `DecisionContextV0`, ni `DecisionTraceV0`, ni trazabilidad F6.
No se serializa, no se persiste, no sale en ninguna respuesta y no toca el panel. Es un
puntero efímero que vive lo que vive el turno.

Y no transporta nada del comprador: el tipo no tiene dónde ponerlo, y hay un guard
estructural que lo vigila.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class DecisionInputCapture:
    """Las ENTRADAS exactas con las que se decidió el turno. Referencias, no copias.

    Captura mínima a propósito: sólo lo que una segunda ejecución del mismo núcleo no
    debería reconstruir. `messages` y `preferencias` no están aquí porque ya salen del grafo
    por su camino —`AgentState`—, y duplicarlos daría dos fuentes para lo mismo.

    `ids` sí se captura aunque `_collect_asset_ids` sea pura: depende del recorte
    (`_MAX_CARDS * 2`) y de los mensajes en ese instante exacto. Volver a derivarlo sería
    reconstruir el universo en vez de reutilizarlo, que es justo lo que este puente evita.
    """

    rows: list
    curaciones: dict
    ids: list


@dataclass
class DecisionCaptureBox:
    """El buzón del turno. Se crea uno por petición y se tira al terminar.

    Mutable a propósito: es lo único que atraviesa la frontera de tareas de asyncio sin
    depender de un rebind que no propaga.
    """

    entradas: DecisionInputCapture | None = field(default=None)

    @property
    def hay_captura(self) -> bool:
        return self.entradas is not None


_captura_actual: contextvars.ContextVar[DecisionCaptureBox | None] = contextvars.ContextVar(
    "contexto_captura_decision", default=None)
"""El canal. `default=None` significa «no hay turno observando», que es el estado normal y
el de toda la suite que no lo instale."""


@contextmanager
def capturar_entradas_de_decision():
    """Abre un buzón para ESTE turno y lo cierra pase lo que pase.

    El `reset(token)` va en `finally` y usa el token, no un `set(None)`: si hubiera un
    contexto exterior —una ejecución anidada—, ponerlo a `None` lo dejaría ciego en vez de
    devolverlo a su caja. Con el token, cerrar el interior restaura el exterior.

    No captura excepciones. Una cancelación tiene que propagarse como propagaría sin esto:
    convertir un `CancelledError` en éxito por instrumentar un puente sería exactamente el
    tipo de fallo que nadie ve hasta que importa.
    """
    caja = DecisionCaptureBox()
    token = _captura_actual.set(caja)
    try:
        yield caja
    finally:
        _captura_actual.reset(token)


def caja_actual() -> DecisionCaptureBox | None:
    """El buzón del turno en curso, o `None` si nadie está observando."""
    return _captura_actual.get()


def depositar(rows, curaciones, ids) -> None:
    """Deja las entradas ya usadas en el buzón del turno. **No hace `set()` jamás.**

    Sin buzón no pasa nada: ni error, ni aviso, ni salida distinta. La captura es
    observabilidad opcional, y el panel tiene que comportarse igual con ella y sin ella —
    hay un test de paridad que lo congela.
    """
    caja = _captura_actual.get()
    if caja is None:
        return
    caja.entradas = DecisionInputCapture(rows=rows, curaciones=curaciones, ids=ids)
