"""F3.0b — la costura de entrada: el último mensaje del usuario, con su identidad real.

F3.0a demostró que la identidad que el Buyer Harness necesita **ya existe**: `add_messages`
le asigna un UUID4 a cada `HumanMessage` al ingerirlo, el id se mantiene estable entre turnos
y el serializador del checkpointer lo conserva. Lo que faltaba no era crearla — era dejar de
tirarla en `assembler.py:188`, donde `[m.content for m in messages]` convierte objetos con
identidad en cadenas anónimas.

Este módulo es el carril nuevo. No sustituye al legacy:

    LEGACY (autoridad productiva)     messages → _user_texts → extraer_preferencias → dict
    F3     (todavía no autoritativo)  messages → ultimo_mensaje_usuario_identificado → IdentifiedUserMessage → [STOP]

LA REGLA QUE GOBIERNA TODO ESTE ARCHIVO: el `message_id` **se toma, no se fabrica**. No lo
propone un modelo, no se deriva del texto, no se genera aquí. Sale del `HumanMessage.id` que
ya está en el estado. Si no está, esta costura falla cerrado — porque un id inventado
produciría una `EvidenceRefV0` que valida y miente sobre su propio origen, que es exactamente
la familia de defectos que F2 se pasó cerrando (`place_id`, `score_version`, `decision_id`).

Un hash del texto tampoco sirve como identidad, y conviene decir por qué: dos turnos con el
mismo texto —"sí", "y qué más?"— colapsarían en el mismo id, y una corrección posterior sería
indistinguible de la declaración original.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict, Field


class MensajeSinIdentidad(RuntimeError):
    """Hay un mensaje del usuario que alimentaría el Buyer Harness y no trae `id`.

    Fail-closed **solo en el carril nuevo**: el legacy sigue funcionando y el producto no se
    rompe. Se levanta en vez de rellenar porque la alternativa —inventar un id— haría que la
    procedencia de un criterio apuntara a un mensaje que no existe.

    En condiciones normales no debería ocurrir: `add_messages` asigna el id al ingerir. Que
    ocurra significa que el mensaje llegó por un camino que no pasó por el grafo, y eso es
    justo lo que conviene que duela.
    """


class IdentifiedUserMessage(BaseModel):
    """Un mensaje del usuario que sabe de dónde viene. **Interna, no es contrato F1.**

    Mínima a propósito: `message_id` y `text`. Todo lo demás —timestamp, sesión, orden— se
    puede añadir cuando exista un consumidor que lo necesite; añadirlo ahora sería decidir
    por E3.2 sin evidencia.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: str = Field(min_length=1)
    """El `HumanMessage.id` tal cual. Es lo que un futuro `EvidenceRefV0` podrá citar como
    `source_id` — ver §EVIDENCEREF MAPPING del reporte 10."""

    text: str = Field(min_length=1)
    """El texto literal. **Sigue siendo texto libre sin sanitizar**: no ha pasado por ninguna
    barrera Fair Housing. Convertirlo en criterios exige atravesar la barrera determinista
    antes; ver §FAIR HOUSING BOUNDARY del reporte 10."""


def _es_util(m) -> bool:
    """Un `HumanMessage` con contenido real. Mismo filtro que el legacy `_user_texts`, para
    que los dos carriles no discrepen sobre qué cuenta como mensaje del usuario."""
    return (isinstance(m, HumanMessage)
            and isinstance(m.content, str)
            and bool(m.content.strip()))


def ultimo_mensaje_usuario_identificado(messages) -> IdentifiedUserMessage | None:
    """El ÚLTIMO mensaje del usuario en el hilo, con su identidad.

    Determinista: el más reciente que cumple `_es_util`. Selección por posición, sin
    heurística.

    ── LO QUE ESTA FUNCIÓN **NO** AFIRMA ───────────────────────────────────────────────

        identificado ≠ nuevo
        último       ≠ sin procesar

    Devuelve el último mensaje del transcript. **No sabe si ya fue procesado antes**, y no
    puede saberlo: la novedad no es una propiedad del transcript, es una propiedad del
    estado persistido. Un retry, un replay, una reanudación del grafo o una ejecución
    duplicada devolverían el MISMO `message_id`, y eso es correcto — es el mismo mensaje.

    Por eso el nombre dice `ultimo_…` y no `nuevo_…`: prometer novedad sería prometer una
    garantía que solo puede dar el Buyer Store. La idempotencia se resuelve allí
    —`(buyer_id, source_message_id)` no debe producir dos revisiones— no aquí.

    Devuelve `None` cuando no hay ningún mensaje del usuario. `None` no es un fallo: es
    "no hay nada que procesar", y se distingue a propósito de `MensajeSinIdentidad`, que sí
    lo es. Es la misma distinción ausente-≠-vacío que gobierna los contratos de F1.

    Levanta `MensajeSinIdentidad` si el mensaje existe y no trae `id`.
    """
    utiles = [m for m in (messages or []) if _es_util(m)]
    if not utiles:
        return None

    ultimo = utiles[-1]
    identidad = getattr(ultimo, "id", None)
    if not isinstance(identidad, str) or not identidad.strip():
        raise MensajeSinIdentidad(
            f"el último mensaje del usuario ({ultimo.content[:40]!r}…) no trae `id`. "
            "No se fabrica uno: una EvidenceRef con procedencia inventada es peor que no "
            "tener evidencia. El carril legacy no se ve afectado."
        )

    return IdentifiedUserMessage(message_id=identidad, text=ultimo.content)
