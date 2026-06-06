from typing import Annotated, Any
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class SpatialContext(TypedDict, total=False):
    """Geocoded metadata extracted from user intent during the conversation."""
    latitude: float
    longitude: float
    radius_meters: int
    target_address: str


class AgentState(TypedDict):
    # Full conversational history — add_messages merges instead of overwriting
    messages: Annotated[list, add_messages]

    # Spatial context parsed from user intent (lat/lon, search radius)
    spatial_context: SpatialContext

    # Raw DB results injected into LLM context to ground responses
    sql_results: list[dict[str, Any]]
