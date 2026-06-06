import json
import uuid
from typing import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from app.agent.graph import compiled_graph
from app.agent.state import AgentState

router = APIRouter(prefix="/api/v1/chat", tags=["Chat — Agente Conversacional"])


class ChatRequest(BaseModel):
    message: str
    # Si el cliente no envía session_id, generamos uno nuevo (sesión de un solo turno).
    # Para conversaciones multi-turno, el cliente debe reutilizar el mismo session_id.
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    model_config = {"json_schema_extra": {"example": {
        "message": "¿Cómo es el ruido y la habitabilidad en La Carolina, Quito?",
        "session_id": "carlos-session-001",
    }}}


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    tool_calls_made: int = 0


def _langgraph_config(session_id: str) -> dict:
    """Construye el config de LangGraph con el thread_id de sesión."""
    return {"configurable": {"thread_id": session_id}}


async def _stream_agent(message: str, session_id: str) -> AsyncIterator[str]:
    """Streams agent token chunks como Server-Sent Events, con memoria de sesión."""
    config = _langgraph_config(session_id)
    input_state: AgentState = {
        "messages": [HumanMessage(content=message)],
        "spatial_context": {},
        "sql_results": [],
    }

    async for event in compiled_graph.astream_events(input_state, config=config, version="v2"):
        kind = event.get("event")

        if kind == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if chunk and hasattr(chunk, "content") and isinstance(chunk.content, str):
                if chunk.content:
                    yield f"data: {json.dumps({'token': chunk.content, 'session_id': session_id})}\n\n"

        elif kind == "on_tool_start":
            tool_name = event.get("name", "")
            yield f"data: {json.dumps({'tool_call': tool_name})}\n\n"

    yield f"data: {json.dumps({'done': True, 'session_id': session_id})}\n\n"


@router.post(
    "/",
    response_model=ChatResponse,
    summary="Consultar al Agente Contexto AI",
    description=(
        "Envía un mensaje al agente con memoria de sesión. "
        "Reutiliza el mismo `session_id` para mantener el hilo conversacional. "
        "Añade `?stream=true` para respuesta en tiempo real (SSE)."
    ),
)
async def chat(request: ChatRequest, stream: bool = False):
    if stream:
        return StreamingResponse(
            _stream_agent(request.message, request.session_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    config = _langgraph_config(request.session_id)
    input_state: AgentState = {
        "messages": [HumanMessage(content=request.message)],
        "spatial_context": {},
        "sql_results": [],
    }

    final_state = await compiled_graph.ainvoke(input_state, config=config)
    messages = final_state["messages"]

    # La última respuesta del LLM sin tool_calls pendientes
    reply = next(
        (m.content for m in reversed(messages)
         if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None)),
        "Sin respuesta del agente.",
    )

    tool_calls = sum(1 for m in messages if hasattr(m, "type") and m.type == "tool")

    return ChatResponse(
        reply=reply,
        session_id=request.session_id,
        tool_calls_made=tool_calls,
    )


@router.get(
    "/{session_id}/history",
    summary="Historial de una sesión",
    description="Recupera los mensajes almacenados para un session_id dado.",
)
async def get_session_history(session_id: str):
    config = _langgraph_config(session_id)
    state = await compiled_graph.aget_state(config)

    if not state or not state.values:
        return {"session_id": session_id, "messages": [], "turns": 0}

    messages = state.values.get("messages", [])
    history = [
        {
            "role": "user" if isinstance(m, HumanMessage) else "assistant",
            "content": m.content if isinstance(m.content, str) else str(m.content),
        }
        for m in messages
        if isinstance(m, (HumanMessage, AIMessage)) and not getattr(m, "tool_calls", None)
    ]

    return {
        "session_id": session_id,
        "turns": sum(1 for h in history if h["role"] == "user"),
        "messages": history,
    }
