from typing import Annotated, Any
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class SpatialContext(TypedDict, total=False):
    """Foco espacial del turno para el Mapa Vivo (docs/SPEC_Mapa_Vivo.md, "estados y
    transiciones"). Antes era un placeholder muerto (siempre {}); ahora el endpoint de chat
    escribe aquí el modo/bbox del turno tras responder, para que la transición no pierda el
    foco (riesgo "Session State Drift" del SPEC)."""
    latitude: float
    longitude: float
    radius_meters: int
    target_address: str
    # Directiva de mapa del turno: focus_mode ∈ zona|auras|aura|comparar; bbox del encuadre.
    focus_mode: str
    bbox: list  # [[minLon, minLat], [maxLon, maxLat]]
    capas: list


class _AgentStateCore(TypedDict):
    # Full conversational history — add_messages merges instead of overwriting
    messages: Annotated[list, add_messages]

    # Spatial context parsed from user intent (lat/lon, search radius)
    spatial_context: SpatialContext

    # Raw DB results injected into LLM context to ground responses
    sql_results: list[dict[str, Any]]


class AgentState(_AgentStateCore, total=False):
    """Estado del turno. Las claves de abajo (opcionales) las escribe el nodo `encaje`, que
    corre entre las herramientas y la respuesta: calcula el ENCAJE de lo que la búsqueda
    encontró ANTES de que el modelo escriba, para que la prosa y las tarjetas salgan del
    MISMO objeto. Antes el encaje se calculaba después de responder y el modelo nunca veía
    su propio ranking — de ahí los fallos 1, 3 y 4 de BATALLA_Hiinmo (2026-07-30)."""

    # Necesidades declaradas (schema cerrado de app/preferencias.py), extraídas UNA vez por
    # turno; `preferencias_turno` = nº de mensajes del usuario cuando se extrajeron (la
    # llave del caché: mientras no haya turno nuevo, no se vuelve a llamar al LLM).
    preferencias: dict | None
    preferencias_turno: int

    # Las tarjetas del turno YA puntuadas y ordenadas por el motor — exactamente las que
    # verá la persona. El endpoint las reusa en vez de recalcularlas.
    cards: list[dict[str, Any]]

    # El bloque de texto autoritativo (ranking + restricciones) que llm_node añade al
    # system prompt. Vacío = este turno no encontró inventario que puntuar.
    encaje_contexto: str

    # Lo que el corte del panel dejó fuera: la persona NO lo ve en pantalla. Viaja hasta el
    # endpoint para que `verificacion_prosa` pueda detectar que la respuesta lo ofreció igual
    # (ofrecer lo que no aparece es prometer lo que no hay).
    descartadas: list[dict[str, Any]]
