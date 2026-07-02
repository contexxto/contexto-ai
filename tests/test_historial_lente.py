"""Test: la recarga de historial encadena el MODO del lente turno a turno (histeresis), igual
que el turno EN VIVO — hallazgo adversarial del PR #46.

Antes, get_session_history llamaba _map_seed_from_cards(results) SIN prev_mode, asi que el mapa
recomputaba cada turno sin continuidad y podia caer de ZONA a AURAS, "saltando" respecto de lo
que el usuario vio en vivo (que si encadena via spatial_context.focus_mode).
"""
import asyncio
import json
import types

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.routers import chat


def _turno(user_text, ids):
    tool_json = json.dumps({"assets": [{"id": i} for i in ids]})
    return [
        HumanMessage(content=user_text),
        ToolMessage(content=tool_json, name="tool_find_assets_by_text", tool_call_id="t"),
        AIMessage(content="Aca tenes."),
    ]


def _row(rid):
    return {
        "id": rid, "direccion": f"Dir {rid}", "tipo_activo": "Departamento",
        "imagen_url": None, "caminabilidad": 90, "ruido": "BAJO", "vegetacion": 40,
        "servicios_cercanos": None, "conectividad": None,
        "lat": -0.18, "lon": -78.48, "caracteristicas": {},
        "operacion": "ARRIENDO", "precio": 500,
    }


def test_historial_encadena_histeresis_del_lente(monkeypatch):
    # Turno 1: 3 pines → AURAS (2..4). Turno 2: 5 pines → base ZONA, pero con prev_mode=AURAS y
    # 5<=6 (_UMBRAL_AURAS+2) la histeresis lo MANTIENE en AURAS. Sin encadenar daria ZONA (el bug).
    t1 = _turno("Busco por el centro", ["A", "B", "C"])
    t2 = _turno("¿Y un poco mas alla?", ["A", "B", "C", "D", "E"])
    messages = t1 + t2
    rows = [_row(r) for r in ["A", "B", "C", "D", "E"]]

    async def fake_state(_cfg):
        return types.SimpleNamespace(values={"messages": messages})
    monkeypatch.setattr(chat, "agent_graph",
                        types.SimpleNamespace(compiled_graph=types.SimpleNamespace(aget_state=fake_state)))

    async def fake_prefs(_textos):
        return {}
    monkeypatch.setattr(chat, "extraer_preferencias", fake_prefs)

    async def fake_fetch(_ids):
        return (rows, {})
    monkeypatch.setattr(chat, "_fetch_cards_rows", fake_fetch)

    hist = asyncio.run(chat.get_session_history("s"))
    asistentes = [h for h in hist["messages"] if h["role"] == "assistant"]
    assert len(asistentes) == 2
    assert asistentes[0]["map_seed"]["modo"] == "auras"   # 3 pines
    # El punto del fix: el turno 2 hereda AURAS por histeresis (sin encadenar prev_mode seria "zona").
    assert asistentes[1]["map_seed"]["modo"] == "auras"
