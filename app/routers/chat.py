import json
from typing import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.agent.graph import compiled_graph
from app.agent.state import AgentState

router = APIRouter(prefix="/api/v1/chat", tags=["Chat — Agente Conversacional"])


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None

    model_config = {"json_schema_extra": {"example": {
        "message": "¿Cómo es el ruido y la habitabilidad en La Carolina, Quito? Tengo las coordenadas -0.1807, -78.4678",
        "session_id": "session_abc123",
    }}}


class ChatResponse(BaseModel):
    reply: str
    tool_calls_made: int = 0


async def _stream_agent(message: str) -> AsyncIterator[str]:
    """Streams agent token chunks as Server-Sent Events."""
    initial_state: AgentState = {
        "messages": [HumanMessage(content=message)],
        "spatial_context": {},
        "sql_results": [],
    }

    async for event in compiled_graph.astream_events(initial_state, version="v2"):
        kind = event.get("event")

        if kind == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if chunk and hasattr(chunk, "content") and isinstance(chunk.content, str):
                if chunk.content:
                    yield f"data: {json.dumps({'token': chunk.content})}\n\n"

        elif kind == "on_tool_start":
            tool_name = event.get("name", "")
            yield f"data: {json.dumps({'tool_call': tool_name})}\n\n"

    yield "data: [DONE]\n\n"


@router.post(
    "/",
    summary="Consultar al Agente Contexto AI",
    description="Envía un mensaje al agente. Responde con streaming SSE o JSON completo.",
)
async def chat(request: ChatRequest, stream: bool = False):
    if stream:
        return StreamingResponse(
            _stream_agent(request.message),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Non-streaming: run to completion and return final message
    initial_state: AgentState = {
        "messages": [HumanMessage(content=request.message)],
        "spatial_context": {},
        "sql_results": [],
    }

    final_state = await compiled_graph.ainvoke(initial_state)
    messages = final_state["messages"]
    reply = messages[-1].content if messages else "Sin respuesta del agente."

    # Count tool calls made during the run
    tool_calls = sum(
        1 for m in messages
        if hasattr(m, "type") and m.type == "tool"
    )

    return ChatResponse(reply=reply, tool_calls_made=tool_calls)
