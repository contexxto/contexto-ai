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
import logging
import os
import unicodedata

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

log = logging.getLogger("crm.tools")


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


# ── Playbook de venta honesta (retrieval del Corredor-Brain, bundleado en el repo) ──────────────
# El LLM-wiki "Corredor-Brain" (Serhant/Keller/Corcoran/Hormozi, ya filtrado por foso + Fair Housing)
# se destila a corredor_playbook.json con scripts/export_corredor_playbook.py. La tool lo consulta a
# demanda por AGENTE (modo) + tema — así el prompt no engorda y las tácticas viajan a producción.
_PLAYBOOK_PATH = os.path.join(os.path.dirname(__file__), "corredor_playbook.json")
_PLAYBOOK: dict | None = None


def _load_playbook() -> dict:
    global _PLAYBOOK
    if _PLAYBOOK is None:
        try:
            with open(_PLAYBOOK_PATH, encoding="utf-8") as f:
                _PLAYBOOK = json.load(f)
        except Exception as exc:  # noqa: BLE001 — sin playbook, degrada a vacío (nunca tumba el agente)
            log.warning("playbook no cargó (%s): %s → el CRM sigue sin tácticas de venta",
                        _PLAYBOOK_PATH, exc)
            _PLAYBOOK = {"tacticas": [], "evitar": []}
    return _PLAYBOOK


def _norm(s: str) -> str:
    """minúsculas sin acentos, para match tolerante."""
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _score(entry: dict, qwords: list[str]) -> int:
    hay = _norm(" ".join([entry.get("titulo", ""), " ".join(entry.get("tags", [])),
                          " ".join(entry.get("aliases", [])), entry.get("que_es", ""),
                          entry.get("por_que", "")]))
    return sum(1 for w in qwords if w in hay)


@tool
async def tool_playbook_venta(tema: str, config: RunnableConfig) -> str:
    """Consulta el PLAYBOOK de venta HONESTA del corredor: tácticas de cierre, manejo de objeción,
    follow-up/reenganche, negociación, priorización de cartera y redacción — destiladas de constructores
    REALES de imperios inmobiliarios (Serhant, Keller, Corcoran, Hormozi) y YA filtradas por Fair Housing
    + honestidad. Pásale un 'tema' en lenguaje natural (ej.: 'objeción de precio', 'reenganchar a un
    dormido', 'cómo priorizo mi cartera', 'redactar el primer mensaje', 'pedir un referido'). Devuelve
    tácticas aplicables CON SU CANDADO y atribución 'per <Mogul>', más qué EVITAR (anti-patrones). Aplica
    el candado y cita al mogul; NUNCA uses una táctica sin su candado."""
    pb = _load_playbook()
    cfg = (config or {}).get("configurable") or {}
    tema = (tema or "")[:500]   # cap de longitud (defensa: 'tema' es texto libre del LLM)
    # Ruteo por agente: el Copiloto ve lo TÁCTICO por-lead; el Estratega, lo de CARTERA + coaching.
    permit = {"estratega", "ambos", "corredor"} if cfg.get("modo") == "estratega" else {"copiloto", "ambos"}
    qwords = [w for w in _norm(tema).split() if len(w) > 2]

    cand = [t for t in pb.get("tacticas", []) if t.get("agente") in permit]
    tac = sorted((t for t in cand if _score(t, qwords) > 0), key=lambda t: _score(t, qwords), reverse=True)[:4]
    evi = sorted((e for e in pb.get("evitar", []) if _score(e, qwords) > 0), key=lambda e: _score(e, qwords), reverse=True)[:2]

    return json.dumps({
        "_no_respaldo": True,  # COACHING, no dato de cartera → el guardrail de cifras NO respalda con esto
        "tema": tema,
        "tacticas": [{"titulo": t["titulo"], "per": t.get("mogul", ""), "foso": t.get("foso", ""),
                      "candado": t.get("candado", ""), "que_es": t.get("que_es", ""),
                      "como_aplica": t.get("como_aplica", "")} for t in tac],
        # 'evitar' = ANTI-PATRONES: qué NO hacer. Cada item se marca explícito para que el LLM jamás los aplique.
        "evitar": [{"NO_USAR": e["titulo"], "es_anti_patron": True, "por_que": e.get("por_que", "")} for e in evi],
        "_nota": ("Ninguna táctica específica para ese tema; procede con tu criterio y las barandas."
                  if not tac else
                  "Aplica el 'candado' de cada táctica y atribuye 'per'. Ya pasaron el foso; aun así, "
                  "nunca inventes cifras ni segmentes por clase protegida al aplicarlas."),
    }, ensure_ascii=False)


CRM_TOOLS = [tool_stats_embudo, tool_timeline_de_lead, tool_playbook_venta]   # Copiloto: cartera + timeline + playbook
ESTRATEGA_TOOLS = [tool_stats_embudo, tool_playbook_venta]                    # Estratega: cartera agregada + playbook
