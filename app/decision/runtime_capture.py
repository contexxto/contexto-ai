"""F3-DECISION-INPUT-BRIDGE · las ENTRADAS de la decisión visible, fuera del grafo.

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

De ahí la regla dura de este módulo: **el productor nunca hace `set()`, sólo compromete.**
Sólo el dueño del turno abre y cierra.

## R0F1 · POR QUÉ SE COMPROMETE Y NO SE DEPOSITA

La primera versión depositaba ANTES de decidir, y el grafo resultó ser un bucle: `encaje`
corre una vez por ronda de herramientas. Con el depósito por delante, esta secuencia dejaba
una captura mentirosa:

```
ronda 1   decide A   éxito     → el panel visible es A
ronda 2   deposita B → revienta → el nodo conserva el panel A
                                  y la caja se había quedado con B
```

Un contrafactual sobre B comparado contra el panel A no mide nada: el delta vendría del
arnés, no del campo. Así que el commit ocurre **después** de que la decisión existió, y una
tentativa fallida no toca la captura vigente. La correspondencia la da el FLUJO DE CONTROL.

## EL WITNESS NO ES EL FUNDAMENTO

Se guarda además una huella semántica del resultado, pero sólo como comprobación adicional.
Dos ejecuciones pueden producir ids y orden idénticos y partir de filas distintas —una señal
que las preferencias legacy no miran, como mascotas, no cambia el panel pero sí cambiaría un
contrafactual—. Cotejar por ids daría por buena la captura equivocada. El witness detecta
desalineamientos; no es lo que establece la identidad.

## LO QUE NO ES

No es un contrato público, ni `DecisionContextV0`, ni `DecisionTraceV0`, ni trazabilidad F6.
No se serializa, no se persiste, no se loguea, no sale en ninguna respuesta y no toca el
panel. Es un puntero efímero que vive lo que vive el turno.

Y no transporta nada del comprador: el tipo no tiene dónde ponerlo, y hay un guard
estructural que lo vigila.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum


class DesenlaceCaptura(StrEnum):
    """Qué decisión vigente representa la caja. Vocabulario CERRADO."""

    DECISION = "decision"
    """Hubo panel: la caja trae las entradas exactas con las que se decidió."""

    VACIA = "vacia"
    """La ejecución vigente salió por la puerta temprana —sin activos en el turno, o el
    catastro degradó— y **no hubo entradas**. Se registra igual, y a propósito: dejar la
    captura anterior en pie afirmaría que corresponde a un panel que ya fue sustituido."""


class Correspondencia(StrEnum):
    """El resultado de cotejar la captura con lo que se ve. Para que un consumidor futuro
    falle CERRADO en vez de comparar contra el panel equivocado."""

    COINCIDE = "coincide"
    NO_COINCIDE = "no_coincide"
    SIN_CAPTURA = "sin_captura"
    VACIA = "vacia"


@dataclass(frozen=True)
class DecisionInputCapture:
    """Las ENTRADAS exactas con las que se decidió el turno. Referencias, no copias.

    Captura mínima a propósito: sólo lo que una segunda ejecución del mismo núcleo no
    debería reconstruir. `messages`, `preferencias` y `session_id` no están aquí porque ya
    salen del grafo por su camino —`AgentState`— y duplicarlos daría dos fuentes para lo
    mismo.

    `ids` sí se captura aunque `_collect_asset_ids` sea pura: depende del recorte
    (`_MAX_CARDS * 2`) y de los mensajes en ese instante exacto. Volver a derivarlo sería
    reconstruir el universo en vez de reutilizarlo, que es justo lo que este puente evita.
    """

    rows: list
    curaciones: dict
    ids: list
    witness: tuple
    """Huella semántica del panel que estas entradas produjeron. Comprobación, no identidad:
    ver la nota del encabezado sobre por qué cotejar por ids no basta."""


@dataclass
class DecisionCaptureBox:
    """El buzón del turno. Se crea uno por petición y se tira al terminar.

    Mutable a propósito: es lo único que atraviesa la frontera de tareas de asyncio sin
    depender de un rebind que no propaga.

    Guarda **la última ejecución exitosa**, no un historial: lo que interesa es qué decidió
    el panel vigente, y una lista de rondas invitaría a elegir la equivocada.
    """

    desenlace: DesenlaceCaptura | None = field(default=None)
    entradas: DecisionInputCapture | None = field(default=None)
    commits: int = 0
    """Sólo para pruebas y diagnóstico. No se persiste ni se loguea."""

    @property
    def hay_captura(self) -> bool:
        """¿Hay entradas utilizables? Un panel vacío NO cuenta: se registró, pero no hay
        nada con lo que volver a decidir."""
        return self.desenlace is DesenlaceCaptura.DECISION and self.entradas is not None


_captura_actual: contextvars.ContextVar[DecisionCaptureBox | None] = contextvars.ContextVar(
    "contexto_captura_decision", default=None)
"""El canal. `default=None` significa «no hay turno observando», que es el estado normal y
el de toda la suite que no lo instala."""


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


def huella_del_panel(panel: dict) -> tuple:
    """La semántica del panel que sirve para cotejar, en forma comparable y estable.

    Lleva el orden visible, lo descartado y, por activo, los ejes que una comparación
    necesitaría: encaje visible, medido, cobertura, razones y requisitos duros. NO lleva
    `score_version` — no viaja en la tarjeta, es una constante de módulo, y afirmar que sí
    vendría en `cards` sería describir un campo que no existe.
    """
    def _de(c: dict) -> tuple:
        return (
            c.get("id"),
            c.get("encaje"),
            c.get("encaje_medido"),
            c.get("encaje_cobertura"),
            tuple(r.get("texto") for r in (c.get("encaje_razones") or ())),
            tuple(c.get("duros_incumplidos") or ()),
        )

    return (
        tuple(_de(c) for c in panel.get("cards") or ()),
        tuple(_de(c) for c in panel.get("descartadas") or ()),
    )


def comprometer(rows, curaciones, ids, panel: dict) -> None:
    """Fija las entradas de una decisión que YA existió. **No hace `set()` jamás.**

    Se llama con el panel en la mano, después de que el núcleo devolvió: si el cálculo
    revienta, esta función no llega a ejecutarse y la captura vigente queda intacta. Ahí está
    toda la corrección de R0F1 — no en el witness, sino en dónde está la llamada.

    Sin buzón no pasa nada: ni error, ni aviso, ni salida distinta. La captura es
    observabilidad opcional, y el panel tiene que comportarse igual con ella y sin ella.
    """
    caja = _captura_actual.get()
    if caja is None:
        return
    caja.desenlace = DesenlaceCaptura.DECISION
    caja.entradas = DecisionInputCapture(rows=rows, curaciones=curaciones, ids=ids,
                                         witness=huella_del_panel(panel))
    caja.commits += 1


def comprometer_vacia() -> None:
    """Registra que la decisión vigente NO tuvo entradas, y borra la anterior.

    El turno sin activos, o con el catastro degradado, devuelve un panel vacío que sustituye
    al que hubiera antes. Conservar la captura previa haría creer que corresponde al panel
    vigente, que es el mismo defecto que R0F1 viene a cerrar — sólo que por la puerta de
    atrás. No se inventan filas vacías: no pasaron por el núcleo.
    """
    caja = _captura_actual.get()
    if caja is None:
        return
    caja.desenlace = DesenlaceCaptura.VACIA
    caja.entradas = None
    caja.commits += 1


def cotejar(caja: DecisionCaptureBox | None, panel_visible: dict) -> Correspondencia:
    """¿La captura corresponde al panel que se está viendo? Para fallar CERRADO.

    No es lo que establece la correspondencia —eso lo da el flujo de control— sino la
    comprobación que permite a un consumidor futuro negarse a comparar cuando algo no cuadra.
    """
    if caja is None or caja.desenlace is None:
        return Correspondencia.SIN_CAPTURA
    if caja.desenlace is DesenlaceCaptura.VACIA or caja.entradas is None:
        return Correspondencia.VACIA
    return (Correspondencia.COINCIDE
            if caja.entradas.witness == huella_del_panel(panel_visible)
            else Correspondencia.NO_COINCIDE)
