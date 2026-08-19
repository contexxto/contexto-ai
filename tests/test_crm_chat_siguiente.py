"""
El endpoint `crm_chat` DEVUELVE la sugerencia — el cableado, no la lógica.

EL HUECO QUE LO ORIGINA (auditoría del 2026-08-19): `tests/test_siguiente.py` cubre
`derivar_siguiente()` con 14 casos, pero **ninguno prueba que el endpoint la entregue**.
Si alguien borra la línea de `app/routers/assets.py`, esos 14 tests siguen en verde y el
chip desaparece del producto sin que nada chille. Es exactamente la clase de fallo
silencioso que costó 1h26m el 2026-08-18 (ver docs/INCIDENTE_2026-08-18_Pools.md): nada
falla, solo deja de funcionar.

Estos tests no tocan la base ni el LLM: se falsea el grafo del CRM y se llama a la función
del endpoint directamente, como en `test_edit_reubicacion_fuente.py`.
"""
import asyncio
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.auth import CurrentUser
from app.limiter import limiter
from app.routers import assets


def _stats_embudo(dormidos=0, hay_registro=True) -> str:
    """La MISMA forma que devuelve tool_stats_embudo (ver app/agent/crm_tools.py)."""
    return json.dumps({
        "total_interesados": 12, "por_etapa": {"intencion": 7},
        "calientes_o_piden_corredor": [], "dormidos": dormidos, "por_reenganchar": [],
        "reparto": {"hay_registro": hay_registro, "interesados": 12},
        "_proveniencia": "Cifras reales del sistema.",
    }, ensure_ascii=False)


def _correr(monkeypatch, tool_json: str | None, *, rol="corredor", explota=False):
    """Invoca crm_chat con un turno falso. `tool_json=None` = turno sin tools."""
    msgs = [HumanMessage(content="¿cómo va mi cartera?")]
    if tool_json is not None:
        msgs.append(ToolMessage(content=tool_json, tool_call_id="t1"))
    msgs.append(AIMessage(content="Tu cartera está así."))

    class _Grafo:
        async def ainvoke(self, _state, config=None):
            return {"messages": msgs}

    import app.agent.crm_graph as crm_graph
    monkeypatch.setattr(crm_graph, "compiled_crm_graph", _Grafo())

    if explota:  # simula un fallo dentro de la derivación
        import app.agent.siguiente as siguiente_mod
        monkeypatch.setattr(siguiente_mod, "derivar_siguiente",
                            lambda _j: (_ for _ in ()).throw(RuntimeError("boom")))

    monkeypatch.setattr(limiter, "enabled", False)  # el rate-limit no es lo que se prueba
    payload = assets.CRMChatReq(message="¿cómo va mi cartera?", modo="estratega")
    user = CurrentUser(user_id="u1", rol=rol)
    return asyncio.run(assets.crm_chat(None, payload, user))


# ══ El cableado ═══════════════════════════════════════════════════════════════════════
def test_la_respuesta_incluye_la_clave_siguiente(monkeypatch):
    """Aunque sea None: el frontend lee `data.siguiente` y la clave debe existir siempre."""
    res = _correr(monkeypatch, None)
    assert "siguiente" in res, "el endpoint dejó de entregar la sugerencia al frontend"


def test_una_tool_con_dormidos_llega_como_sugerencia_al_frontend(monkeypatch):
    """El caso que se vio en producción el 2026-08-18 con el chip real."""
    res = _correr(monkeypatch, _stats_embudo(dormidos=3))
    assert res["siguiente"] == "¿A cuáles de los dormidos les escribo primero?"


def test_sin_registro_de_llegadas_llega_su_sugerencia(monkeypatch):
    res = _correr(monkeypatch, _stats_embudo(dormidos=0, hay_registro=False))
    assert res["siguiente"] == "¿Cómo empiezo a registrar las llegadas?"


def test_un_turno_sin_tools_no_sugiere_nada(monkeypatch):
    """None es una respuesta válida y frecuente — no un fallo."""
    assert _correr(monkeypatch, None)["siguiente"] is None


def test_la_respuesta_del_corredor_no_se_pierde_por_la_sugerencia(monkeypatch):
    """El contrato entero sigue intacto: la sugerencia es un añadido, no un reemplazo."""
    res = _correr(monkeypatch, _stats_embudo(dormidos=2))
    assert res["reply"] == "Tu cartera está así."
    assert res["session_id"] and "panel_seed" in res


# ══ Es un añadido, no una dependencia ═════════════════════════════════════════════════
def test_si_la_derivacion_explota_el_corredor_igual_recibe_su_respuesta(monkeypatch):
    """Best-effort de verdad: un fallo derivando la sugerencia JAMÁS debe tumbar el turno
    que el corredor sí completó. Si alguien quita el try/except, esto se cae."""
    res = _correr(monkeypatch, _stats_embudo(dormidos=3), explota=True)
    assert res["reply"] == "Tu cartera está así."
    assert res["siguiente"] is None


# ══ El alcance sigue cerrado ══════════════════════════════════════════════════════════
def test_un_cliente_no_entra_al_crm_ni_recibe_sugerencias(monkeypatch):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _correr(monkeypatch, _stats_embudo(dormidos=3), rol="cliente")
    assert e.value.status_code == 403
