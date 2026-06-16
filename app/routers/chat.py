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


# ── Handoff en vivo al corredor (dentro de Contexto, sin WhatsApp) ──────────
_HANDOFF_DDL = [
    "CREATE TABLE IF NOT EXISTS handoff_sesion (session_id text PRIMARY KEY, "
    "activo_id uuid, estado text DEFAULT 'solicitado', corredor_id uuid, "
    "lead_user_id uuid, lead_email text, "
    "creado_en timestamptz DEFAULT now(), actualizado_en timestamptz DEFAULT now())",
    "ALTER TABLE handoff_sesion ADD COLUMN IF NOT EXISTS lead_user_id uuid",
    "ALTER TABLE handoff_sesion ADD COLUMN IF NOT EXISTS lead_email text",
    "ALTER TABLE handoff_sesion ADD COLUMN IF NOT EXISTS push_subscription jsonb",
    "CREATE TABLE IF NOT EXISTS handoff_mensaje (id bigserial PRIMARY KEY, "
    "session_id text, autor text, texto text, creado_en timestamptz DEFAULT now())",
    "CREATE INDEX IF NOT EXISTS ix_handoff_msg_sid ON handoff_mensaje (session_id, id)",
    # Suscripción push + email de usuarios autenticados (corredores) → notificarles
    # cuando un lead pide hablar o escribe. El email se captura del JWT al suscribirse.
    "CREATE TABLE IF NOT EXISTS push_usuario (user_id uuid PRIMARY KEY, "
    "email text, subscription jsonb, actualizado_en timestamptz DEFAULT now())",
]
_handoff_ready = False


async def ensure_handoff_tables(db) -> None:
    """Crea las tablas de handoff si no existen (idempotente, una vez por proceso)."""
    global _handoff_ready
    if _handoff_ready:
        return
    for ddl in _HANDOFF_DDL:
        await db.execute(text(ddl))
    await db.commit()
    _handoff_ready = True


def activo_de_session(session_id: str) -> str | None:
    """qr-{activo_uuid(36)}-{device_uuid} → activo_uuid (posición fija; el device también es uuid)."""
    if session_id.startswith("qr-") and len(session_id) >= 39:
        cand = session_id[3:39]
        try:
            return str(uuid.UUID(cand))
        except ValueError:
            return None
    return None


async def _corredor_de_activo(db, activo_id: str | None) -> tuple[str | None, dict | None]:
    """Email + suscripción push del corredor dueño de un inmueble (para notificarle).
    Resuelve dueño directo (owner_user_id) o dueño de la agencia (owner_agency_id)."""
    if not activo_id:
        return None, None
    try:
        owner = (await db.execute(text(
            "SELECT COALESCE(a.owner_user_id, ag.owner_user)::text AS owner "
            "FROM activos_inmutables a LEFT JOIN agencies ag ON ag.id = a.owner_agency_id "
            "WHERE a.id = :id"), {"id": activo_id})).scalar()
        if not owner:
            return None, None
        row = (await db.execute(text(
            "SELECT email, subscription FROM push_usuario WHERE user_id = :u"),
            {"u": owner})).mappings().first()
    except Exception:  # noqa: BLE001 — tablas aún no creadas
        return None, None
    if not row:
        return None, None
    return row.get("email"), row.get("subscription")


def _notificar_corredor(activo_id: str | None, title: str, body: str) -> None:
    """Dispara (fire-and-forget) la notificación al corredor dueño del inmueble.
    Abre directo en el CRM. No bloquea la respuesta HTTP."""
    if not activo_id:
        return
    import asyncio as _aio

    async def _run() -> None:
        async with AsyncSessionLocal() as db:
            await ensure_handoff_tables(db)
            email, sub = await _corredor_de_activo(db, activo_id)
        if not email and not sub:
            return
        from app.notifications import send_notification
        await send_notification(
            email=email, push_subscription=sub,
            title=title, body=body, url="/?crm=1",
            email_subject=title,
        )

    _aio.create_task(_run())


async def transcript_de_sesion(session_id: str) -> list[dict]:
    """Transcripción usuario/asistente de la sesión (para que el corredor lea el hilo)."""
    try:
        state = await agent_graph.compiled_graph.aget_state(_langgraph_config(session_id))
    except Exception:  # noqa: BLE001
        return []
    msgs = (state.values or {}).get("messages", []) if (state and state.values) else []
    out: list[dict] = []
    for m in msgs:
        if isinstance(m, HumanMessage):
            c = _CTX_RE.sub("", m.content if isinstance(m.content, str) else str(m.content)).strip()
            if c and not c.startswith("El usuario escaneó el QR"):
                out.append({"autor": "lead", "texto": c})
        elif isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
            c = m.content if isinstance(m.content, str) else str(m.content)
            if c.strip():
                out.append({"autor": "agente", "texto": c})
    return out


@router.post(
    "/{session_id}/handoff",
    summary="El interesado pide hablar con el corredor (handoff en vivo, sin salir de Contexto)",
)
@limiter.limit("20/minute")
async def solicitar_handoff(
    request: Request, session_id: str,
    user: CurrentUser | None = Depends(get_optional_user),
) -> dict:
    activo_id = activo_de_session(session_id)
    async with AsyncSessionLocal() as db:
        await ensure_handoff_tables(db)
        await db.execute(text(
            "INSERT INTO handoff_sesion (session_id, activo_id, estado, lead_user_id, lead_email) "
            "VALUES (:s, :a, 'solicitado', :u, :e) ON CONFLICT (session_id) DO UPDATE "
            "SET actualizado_en = now(), "
            "    lead_user_id = COALESCE(EXCLUDED.lead_user_id, handoff_sesion.lead_user_id), "
            "    lead_email = COALESCE(EXCLUDED.lead_email, handoff_sesion.lead_email)"),
            {"s": session_id, "a": activo_id,
             "u": user.user_id if user else None, "e": user.email if user else None})
        await db.commit()

    # Avisa al corredor: un lead caliente quiere hablar (lo más valioso del embudo).
    quien = (user.nombre or user.email) if user else "Un interesado"
    _notificar_corredor(activo_id,
        "🔥 Un interesado quiere hablar contigo",
        f"{quien} pidió hablar con el corredor. Ábrelo en tu CRM para responderle.")

    return {"ok": True, "estado": "solicitado", "identificado": bool(user)}


class HandoffMsg(BaseModel):
    texto: str = Field(..., min_length=1, max_length=2000)


@router.post(
    "/{session_id}/handoff/mensaje",
    summary="El interesado escribe al corredor (mensaje in-platform)",
)
@limiter.limit("40/minute")
async def handoff_mensaje_lead(
    request: Request, session_id: str, payload: HandoffMsg,
    user: CurrentUser | None = Depends(get_optional_user),
) -> dict:
    async with AsyncSessionLocal() as db:
        await ensure_handoff_tables(db)
        await db.execute(text(
            "INSERT INTO handoff_sesion (session_id, activo_id, estado, lead_user_id, lead_email) "
            "VALUES (:s, :a, 'solicitado', :u, :e) ON CONFLICT (session_id) DO UPDATE SET "
            "    lead_user_id = COALESCE(EXCLUDED.lead_user_id, handoff_sesion.lead_user_id), "
            "    lead_email = COALESCE(EXCLUDED.lead_email, handoff_sesion.lead_email)"),
            {"s": session_id, "a": activo_de_session(session_id),
             "u": user.user_id if user else None, "e": user.email if user else None})
        await db.execute(text(
            "INSERT INTO handoff_mensaje (session_id, autor, texto) VALUES (:s, 'lead', :t)"),
            {"s": session_id, "t": payload.texto.strip()})
        await db.commit()

    # Avisa al corredor que el lead le escribió (con vista previa del mensaje).
    quien = (user.nombre or user.email) if user else "Un interesado"
    preview = payload.texto.strip()
    if len(preview) > 90:
        preview = preview[:90] + "…"
    _notificar_corredor(activo_de_session(session_id),
        f"💬 {quien} te escribió",
        preview)

    return {"ok": True}


@router.get(
    "/{session_id}/handoff",
    summary="Estado + mensajes del handoff (el interesado consulta respuestas del corredor)",
)
@limiter.limit("120/minute")
async def estado_handoff(request: Request, session_id: str, desde: int = 0) -> dict:
    async with AsyncSessionLocal() as db:
        try:
            est = (await db.execute(text(
                "SELECT estado FROM handoff_sesion WHERE session_id = :s"),
                {"s": session_id})).scalar()
            if est is None:
                return {"activo": False, "estado": None, "mensajes": []}
            rows = (await db.execute(text(
                "SELECT id, autor, texto FROM handoff_mensaje "
                "WHERE session_id = :s AND id > :d ORDER BY id ASC"),
                {"s": session_id, "d": desde})).mappings().all()
        except Exception:  # noqa: BLE001 — tablas aún no existen
            return {"activo": False, "estado": None, "mensajes": []}
    return {"activo": True, "estado": est,
            "mensajes": [{"id": r["id"], "autor": r["autor"], "texto": r["texto"]} for r in rows]}


async def intencion_de_sesion(session_id: str) -> dict:
    """Carga el estado de una sesión y corre el motor de intención. Reutilizable
    por el endpoint de sesión y por el panel de interesados del inmueble."""
    from app.intencion import analizar_intencion

    config = _langgraph_config(session_id)
    try:
        state = await agent_graph.compiled_graph.aget_state(config)
    except Exception:  # noqa: BLE001
        state = None
    messages = (state.values or {}).get("messages", []) if (state and state.values) else []

    mensajes_usuario: list[str] = []
    herramientas = 0
    uso_inversion = False
    for m in messages:
        if isinstance(m, HumanMessage):
            c = m.content if isinstance(m.content, str) else str(m.content)
            c = _CTX_RE.sub("", c).strip()
            # El mensaje técnico del QR no es una señal del usuario; lo omitimos.
            if c and not c.startswith("El usuario escaneó el QR"):
                mensajes_usuario.append(c)
        elif getattr(m, "type", "") == "tool":
            herramientas += 1
            if "investment" in (getattr(m, "name", "") or "").lower():
                uso_inversion = True
        elif isinstance(m, AIMessage):
            for tc in (getattr(m, "tool_calls", None) or []):
                nombre = (tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")) or ""
                if "investment" in nombre.lower():
                    uso_inversion = True

    # Señales del handoff in-platform: pedir corredor es el pico de intención, y los
    # mensajes que el lead escribió al corredor ("quiero reservar una visita") también
    # cuentan como señales (viven en handoff_mensaje, fuera del estado del agente).
    pidio_corredor = False
    try:
        async with AsyncSessionLocal() as db:
            est = (await db.execute(text(
                "SELECT estado FROM handoff_sesion WHERE session_id = :s"), {"s": session_id})).scalar()
            pidio_corredor = est is not None
            if pidio_corredor:
                hmsgs = (await db.execute(text(
                    "SELECT texto FROM handoff_mensaje WHERE session_id = :s AND autor = 'lead' ORDER BY id"),
                    {"s": session_id})).scalars().all()
                mensajes_usuario.extend([t for t in hmsgs if t])
    except Exception:  # noqa: BLE001 — tablas de handoff aún no existen
        pass

    analisis = analizar_intencion(
        mensajes_usuario=mensajes_usuario,
        herramientas_usadas=herramientas,
        es_qr=session_id.startswith("qr-"),
        uso_tool_inversion=uso_inversion,
        pidio_corredor=pidio_corredor,
    )
    analisis["session_id"] = session_id
    return analisis


@router.get(
    "/{session_id}/intencion",
    summary="Estado de intención de una sesión (motor de intención)",
    description=(
        "Clasifica DÓNDE está el deseo del usuario (de 'anónimo' a 'intención de "
        "transacción') con un score explicable. Mismo motor (app.intencion) que "
        "consumirán el agente, el panel del corredor y la API B2B — patrón API-first."
    ),
)
@limiter.limit("60/minute")
async def session_intencion(request: Request, session_id: str) -> dict:
    return await intencion_de_sesion(session_id)


@router.post(
    "/{session_id}/handoff/push",
    summary="Registrar suscripción Web Push del lead (para notificaciones nativas)",
)
@limiter.limit("10/minute")
async def registrar_push_subscription(
    request: Request,
    session_id: str,
    payload: dict,
) -> dict:
    """Guarda la PushSubscription del browser para enviar notificaciones
    cuando el corredor responda. La suscripción viene de
    registration.pushManager.subscribe() en el frontend."""
    if not payload.get("endpoint"):
        raise HTTPException(status_code=400, detail="Suscripción push inválida (sin endpoint).")
    async with AsyncSessionLocal() as db:
        await ensure_handoff_tables(db)
        await db.execute(
            text(
                "UPDATE handoff_sesion SET push_subscription = :sub, actualizado_en = now() "
                "WHERE session_id = :s"
            ),
            {"s": session_id, "sub": json.dumps(payload)},
        )
        await db.commit()
    return {"ok": True}


class PushUsuarioPayload(BaseModel):
    subscription: dict | None = None  # PushSubscription JSON (None si denegó permiso)


@router.post(
    "/push/subscribe",
    summary="Registrar push + email del usuario autenticado (corredor) para notificaciones",
)
@limiter.limit("20/minute")
async def registrar_push_usuario(
    request: Request,
    payload: PushUsuarioPayload,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """El corredor registra su dispositivo (push) y email para recibir avisos
    cuando un lead pide hablar o le escribe. El email se toma del JWT (no del
    cliente). Si denegó el permiso de push, igual guardamos el email."""
    sub = payload.subscription if (payload.subscription and payload.subscription.get("endpoint")) else None
    async with AsyncSessionLocal() as db:
        await ensure_handoff_tables(db)
        await db.execute(
            text(
                "INSERT INTO push_usuario (user_id, email, subscription, actualizado_en) "
                "VALUES (:u, :e, :s, now()) ON CONFLICT (user_id) DO UPDATE SET "
                "  email = COALESCE(EXCLUDED.email, push_usuario.email), "
                "  subscription = COALESCE(EXCLUDED.subscription, push_usuario.subscription), "
                "  actualizado_en = now()"
            ),
            {"u": user.user_id, "e": user.email, "s": json.dumps(sub) if sub else None},
        )
        await db.commit()
    return {"ok": True, "push": bool(sub), "email": bool(user.email)}
