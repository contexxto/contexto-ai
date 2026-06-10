import json
import re
import secrets
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, Security, status
from fastapi.responses import StreamingResponse
from fastapi.security.api_key import APIKeyHeader
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.agent import graph as agent_graph
from app.agent.state import AgentState
from app.auth import CurrentUser, get_current_user, get_optional_user
from app.config import settings
from app.database import AsyncSessionLocal
from app.limiter import limiter

router = APIRouter(prefix="/api/v1/chat", tags=["Chat — Agente Conversacional"])

# ── Seguridad ────────────────────────────────────────────────
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(_api_key_header)) -> None:
    """Valida el header X-API-Key. Si API_KEY no está configurada, permite todo (dev)."""
    configured = settings.api_key
    if not configured:
        return  # dev local: sin restricción
    # Comparación en tiempo constante → no filtra la llave por timing.
    if not api_key or not secrets.compare_digest(api_key, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida o ausente.",
        )


async def _tag_session_owner(session_id: str, user: CurrentUser | None) -> None:
    """Liga la conversación al usuario autenticado (privacidad). Best-effort."""
    if not user:
        return
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    "INSERT INTO chat_sessions (session_id, user_id) VALUES (:sid, :uid) "
                    "ON CONFLICT (session_id) DO UPDATE "
                    "SET user_id = COALESCE(chat_sessions.user_id, :uid)"
                ),
                {"sid": session_id, "uid": user.user_id},
            )
            await db.commit()
    except Exception:  # noqa: BLE001 — etiquetar no debe romper el chat
        pass


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

    async for event in agent_graph.compiled_graph.astream_events(input_state, config=config, version="v2"):
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
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("15/minute")
async def chat(
    request: Request,
    payload: ChatRequest,
    stream: bool = False,
    user: CurrentUser | None = Depends(get_optional_user),
):
    # Si el usuario está autenticado, la conversación queda ligada a él (privacidad).
    await _tag_session_owner(payload.session_id, user)
    if stream:
        return StreamingResponse(
            _stream_agent(payload.message, payload.session_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    config = _langgraph_config(payload.session_id)
    input_state: AgentState = {
        "messages": [HumanMessage(content=payload.message)],
        "spatial_context": {},
        "sql_results": [],
    }

    final_state = await agent_graph.compiled_graph.ainvoke(input_state, config=config)
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
        session_id=payload.session_id,
        tool_calls_made=tool_calls,
    )


class SessionPatch(BaseModel):
    titulo: str | None = None
    pinned: bool | None = None


@router.get(
    "/sessions",
    summary="Listar conversaciones (fijadas primero, luego recientes)",
    description=(
        "Lista los hilos del checkpointer combinados con sus metadatos "
        "(título personalizado, pin). Excluye las archivadas."
    ),
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("60/minute")
async def list_sessions(
    request: Request,
    limit: int = 30,
    user: CurrentUser | None = Depends(get_optional_user),
):
    # Privacidad: solo las conversaciones del usuario autenticado. El invitado no
    # tiene lista persistente (evita ver hilos de otros).
    if not user:
        return {"sessions": []}
    limit = max(1, min(limit, 100))
    try:
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT cs.session_id, cs.titulo, cs.pinned, "
                        "  (SELECT MAX(c.checkpoint_id) FROM checkpoints c "
                        "   WHERE c.thread_id = cs.session_id) AS ultimo "
                        "FROM chat_sessions cs "
                        "WHERE cs.user_id = :uid AND COALESCE(cs.archived, false) = false "
                        "ORDER BY cs.pinned DESC, ultimo DESC NULLS LAST "
                        "LIMIT :n"
                    ),
                    {"uid": user.user_id, "n": limit},
                )
            ).mappings().all()
    except Exception:
        return {"sessions": []}

    sesiones = []
    for r in rows:
        sid = r["session_id"]
        titulo_auto, turnos = None, 0
        try:
            state = await agent_graph.compiled_graph.aget_state(_langgraph_config(sid))
            msgs = (state.values or {}).get("messages", []) if state else []
            user_msgs = [mm for mm in msgs if isinstance(mm, HumanMessage)]
            turnos = len(user_msgs)
            if user_msgs:
                c = user_msgs[0].content
                titulo_auto = (c if isinstance(c, str) else str(c)).strip()[:80]
        except Exception:
            pass
        titulo = (r["titulo"] or None) or titulo_auto or "Conversación sin título"
        sesiones.append({
            "session_id": sid,
            "titulo": titulo,
            "pinned": bool(r["pinned"]),
            "turnos": turnos,
        })

    sesiones.sort(key=lambda s: not s["pinned"])
    return {"sessions": sesiones}


@router.patch(
    "/sessions/{session_id}",
    summary="Renombrar o fijar una conversación",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("60/minute")
async def update_session(
    request: Request, session_id: str, payload: SessionPatch,
    user: CurrentUser = Depends(get_current_user),
):
    if payload.titulo is None and payload.pinned is None:
        raise HTTPException(status_code=400, detail="Nada que actualizar (titulo o pinned).")

    uid = user.user_id
    # Asegura la fila (ligada al usuario), luego aplica los cambios SOLO si es suya.
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO chat_sessions (session_id, user_id) VALUES (:sid, :uid) "
                "ON CONFLICT (session_id) DO UPDATE "
                "SET user_id = COALESCE(chat_sessions.user_id, :uid)"
            ),
            {"sid": session_id, "uid": uid},
        )
        if payload.titulo is not None:
            await db.execute(
                text("UPDATE chat_sessions SET titulo = :t, updated_at = now() "
                     "WHERE session_id = :sid AND user_id = :uid"),
                {"t": payload.titulo.strip()[:120], "sid": session_id, "uid": uid},
            )
        if payload.pinned is not None:
            await db.execute(
                text("UPDATE chat_sessions SET pinned = :p, updated_at = now() "
                     "WHERE session_id = :sid AND user_id = :uid"),
                {"p": payload.pinned, "sid": session_id, "uid": uid},
            )
        await db.commit()
    return {"session_id": session_id, "ok": True}


@router.delete(
    "/sessions/{session_id}",
    summary="Eliminar (archivar) una conversación",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("60/minute")
async def delete_session(
    request: Request, session_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    # Solo archiva si la conversación es del usuario (o aún no tiene dueño).
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO chat_sessions (session_id, archived, user_id) "
                "VALUES (:sid, true, :uid) "
                "ON CONFLICT (session_id) DO UPDATE SET archived = true, updated_at = now() "
                "WHERE chat_sessions.user_id = :uid OR chat_sessions.user_id IS NULL"
            ),
            {"sid": session_id, "uid": user.user_id},
        )
        await db.commit()
    return {"session_id": session_id, "archived": True}


# ── Compartir conversación: enlace público de solo lectura (estilo Claude) ──
_CTX_RE = re.compile(r"\s*\[Contexto del sistema:.*?\]", re.S)


@router.post(
    "/sessions/{session_id}/share",
    summary="Crear/activar el enlace público de la conversación",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("30/minute")
async def share_session(
    request: Request, session_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    token = secrets.token_urlsafe(9)
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO chat_sessions (session_id, user_id, share_token, is_public) "
                "VALUES (:sid, :uid, :tok, true) "
                "ON CONFLICT (session_id) DO UPDATE SET "
                "  share_token = COALESCE(chat_sessions.share_token, :tok), "
                "  is_public = true, "
                "  user_id = COALESCE(chat_sessions.user_id, :uid) "
                "WHERE chat_sessions.user_id = :uid OR chat_sessions.user_id IS NULL"
            ),
            {"sid": session_id, "uid": user.user_id, "tok": token},
        )
        await db.commit()
        row = (
            await db.execute(
                text("SELECT share_token, is_public FROM chat_sessions WHERE session_id = :sid"),
                {"sid": session_id},
            )
        ).mappings().first()
    tok = (row or {}).get("share_token") or token
    return {"token": tok, "path": f"/s/{tok}", "is_public": bool((row or {}).get("is_public"))}


@router.delete(
    "/sessions/{session_id}/share",
    summary="Revocar el enlace público (volver a privado)",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("30/minute")
async def unshare_session(
    request: Request, session_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("UPDATE chat_sessions SET is_public = false WHERE session_id = :sid AND user_id = :uid"),
            {"sid": session_id, "uid": user.user_id},
        )
        await db.commit()
    return {"session_id": session_id, "is_public": False}


@router.get(
    "/shared/{token}",
    summary="Ver una conversación compartida (público, solo lectura)",
)
@limiter.limit("60/minute")
async def get_shared(request: Request, token: str) -> dict:
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                text("SELECT session_id, titulo FROM chat_sessions WHERE share_token = :t AND is_public = true"),
                {"t": token},
            )
        ).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no válido o revocado.")

    sid = row["session_id"]
    out: list[dict] = []
    try:
        state = await agent_graph.compiled_graph.aget_state(_langgraph_config(sid))
        msgs = (state.values or {}).get("messages", []) if state else []
        for m in msgs:
            if isinstance(m, HumanMessage):
                c = m.content if isinstance(m.content, str) else str(m.content)
                c = _CTX_RE.sub("", c).strip()           # oculta el [Contexto del sistema...]
                if c:
                    out.append({"role": "user", "content": c})
            elif isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
                c = m.content if isinstance(m.content, str) else str(m.content)
                if c.strip():
                    out.append({"role": "assistant", "content": c})
    except Exception:  # noqa: BLE001
        pass

    titulo = row["titulo"] or (out[0]["content"][:80] if out else "Conversación")
    return {"titulo": titulo, "messages": out}


@router.get(
    "/{session_id}/history",
    summary="Historial de una sesión",
    description="Recupera los mensajes almacenados para un session_id dado.",
)
async def get_session_history(session_id: str):
    config = _langgraph_config(session_id)
    state = await agent_graph.compiled_graph.aget_state(config)

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
