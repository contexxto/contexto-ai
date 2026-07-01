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


class AgentState(TypedDict):
    # Full conversational history — add_messages merges instead of overwriting
    messages: Annotated[list, add_messages]

    # Spatial context parsed from user intent (lat/lon, search radius)
    spatial_context: SpatialContext

    # Raw DB results injected into LLM context to ground responses
    sql_results: list[dict[str, Any]]
