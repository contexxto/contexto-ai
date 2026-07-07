"""
Tools del CRM Vivo — el agente del CORREDOR consulta SUS propios datos (Fase 1).

Barandas (ver docs/DISENO_CRM_Vivo.md):
  - El LLM NUNCA calcula: los números salen de estas tools deterministas (motor de
    intención + funnel + reenganche), el LLM solo los narra.
  - Scoping por owner: el corredor sale de config.configurable (owner_user_id/agency_id),
    inyectado por el servidor desde el JWT — NUNCA es un argumento que el LLM controle.
    Así es imposible por construcción consultar leads de otro corredor.
  - Fair Housing / proveniencia: las tools devuelven la necesidad transaccional declarada
    (estado, nivel, qué preguntó) y rotulan proveniencia (score = heurístico; 'pidió
    corredor' = evento verificado). Nunca atributos de clase protegida.
"""
from __future__ import annotations

import json

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool


def _owner(config: RunnableConfig | None) -> tuple[str | None, str | None]:
    cfg = (config or {}).get("configurable") or {}
    return cfg.get("owner_user_id"), cfg.get("owner_agency_id")


def _match_lead(leads: list[dict], referencia: str) -> dict | None:
    """Encuentra el lead que el corredor nombra. Prioriza coincidencia EXACTA (id corto
    'ba0a' o email) antes de caer a substring, para no traer el interesado equivocado en
    silencio. Pura y testeable. None si no calza."""
    ref = (referencia or "").strip().lstrip("#").lower()
    if not ref:
        return None
    # 1) id corto exacto — la etiqueta es "Lead #xxxx" (device[:4])
    for l in leads:
        if (l.get("lead") or "").lower() == f"lead #{ref}":
            return l
    # 2) email exacto
    for l in leads:
        if (l.get("email") or "").lower() == ref:
            return l
    # 3) substring como respaldo (email o etiqueta), primer match
    for l in leads:
        if ref in (l.get("lead") or "").lower() or ref in (l.get("email") or "").lower():
            return l
    return None


@tool
async def tool_stats_embudo(config: RunnableConfig) -> str:
    """Devuelve el estado ACTUAL del embudo de interesados de TODOS los inmuebles del corredor:
    total, conteo por etapa, cuántos calientes/dormidos/por-reenganchar, y los interesados más
    calientes con su dirección. Son cifras REALES computadas por el sistema. NO recibe argumentos:
    el corredor se resuelve del contexto de sesión."""
    from app.database import AsyncSessionLocal
    from app.routers.assets import _leads_del_corredor, _funnel_y_orden

    owner_user_id, owner_agency_id = _owner(config)
    if not owner_user_id:
        return json.dumps({"error": "Sin contexto de corredor."})
    async with AsyncSessionLocal() as db:
        leads = await _leads_del_corredor(db, owner_user_id, owner_agency_id)
    data = _funnel_y_orden(leads)

    calientes = [
        {"lead": l["lead"], "estado": l["estado"], "nivel": l["nivel"], "score": l["score"],
         "pidio_corredor": bool(l.get("handoff_estado")), "direccion": l.get("direccion")}
        for l in data["leads"] if l["nivel"] == "caliente" or l.get("handoff_estado")
    ][:10]
    por_reenganchar = [
        {"lead": l["lead"], "mensaje_sugerido": (l.get("reenganche") or {}).get("mensaje")}
        for l in data["leads"] if l.get("reenganche")
    ][:10]
    dormidos = sum(1 for l in data["leads"] if l.get("frescura") in ("dormido", "frio_profundo"))

    return json.dumps({
        "total_interesados": data["total"],
        "por_etapa": {k: v for k, v in data["funnel"].items() if v},
        "calientes_o_piden_corredor": calientes,
        "dormidos": dormidos,
        "por_reenganchar": por_reenganchar,
        "_proveniencia": "Cifras reales del sistema. 'score' es heurístico (estimación); "
                         "'pidió corredor' y las etapas son eventos verificados del motor de intención.",
    }, ensure_ascii=False)


@tool
async def tool_timeline_de_lead(referencia: str, config: RunnableConfig) -> str:
    """Devuelve la historia completa de UN interesado del corredor: su conversación con el agente
    (transcript), los mensajes del handoff con el corredor, y su estado/score/razones actuales.
    'referencia' es cómo el corredor nombra al lead: su email, su nombre, o su id corto (ej. '#ba0a'
    o 'ba0a'). Solo busca entre los interesados del corredor (o de su agencia)."""
    from sqlalchemy import text as _text
    from app.database import AsyncSessionLocal
    from app.routers.assets import _leads_del_corredor
    from app.routers.chat import transcript_de_sesion, ensure_handoff_tables

    owner_user_id, owner_agency_id = _owner(config)
    if not owner_user_id:
        return json.dumps({"error": "Sin contexto de corredor."})

    async with AsyncSessionLocal() as db:
        leads = await _leads_del_corredor(db, owner_user_id, owner_agency_id)
        match = _match_lead(leads, referencia)
        if not match:
            return json.dumps({"error": f"No encontré un interesado que calce con '{referencia}' entre tus leads."})
        sid = match["session_id"]
        transcript = await transcript_de_sesion(sid)
        handoff: list[dict] = []
        try:
            await ensure_handoff_tables(db)
            rows = (await db.execute(_text(
                "SELECT autor, texto FROM handoff_mensaje WHERE session_id = :s ORDER BY id ASC"),
                {"s": sid})).mappings().all()
            handoff = [{"autor": r["autor"], "texto": r["texto"]} for r in rows]
        except Exception:  # noqa: BLE001
            await db.rollback()

    return json.dumps({
        "lead": match["lead"], "estado": match["estado"], "nivel": match["nivel"], "score": match["score"],
        "frescura": match.get("frescura"), "direccion": match.get("direccion"),
        "razones": match.get("razones"), "reenganche_sugerido": (match.get("reenganche") or {}).get("mensaje"),
        "transcript": transcript, "handoff": handoff,
        "_proveniencia": "score es heurístico (estimación); las etapas/eventos son del motor de intención.",
    }, ensure_ascii=False)


CRM_TOOLS = [tool_stats_embudo, tool_timeline_de_lead]           # Copiloto (táctico): cartera + timeline por-lead
ESTRATEGA_TOOLS = [tool_stats_embudo]                            # Estratega (cartera): SOLO agregados, sin chat crudo
