"""Test del bug real (feedback en vivo): el encaje desaparecía al RECARGAR una conversación.

get_session_history reconstruye cada turno llamando build_result_cards(turn_tool_msgs) — SOLO
los ToolMessage del turno. build_result_cards internamente hace
extraer_preferencias(_user_texts(messages)), y _user_texts filtra por HumanMessage: al recibir
una lista que NUNCA tiene HumanMessage, siempre devuelve [] → preferencias={} en TODA recarga,
aunque el turno EN VIVO sí las haya extraído bien. El fix acumula los HumanMessage vistos y los
pasa junto con los tool msgs del turno.
"""
import asyncio
import json
import types

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.routers import chat


class _FakeState:
    def __init__(self, messages):
        self.values = {"messages": messages}


def _mk_row(rid, **over):
    row = {
        "id": rid, "direccion": f"Dir {rid}", "tipo_activo": "Departamento",
        "operacion": "arriendo", "precio": 380, "imagen_url": None,
        "caminabilidad": 95, "ruido": "BAJO", "vegetacion": 42,
        "lat": -0.18, "lon": -78.48,
        "caracteristicas": {"num_dormitorios": 2, "acepta_mascotas": True},
        "servicios_cercanos": "🌳 Parque a ~300 m",
        "conectividad": "🚇 Metro a ~500 m (7 min a pie)",
    }
    row.update(over)
    return row


def _mensajes_de_un_turno(user_text, ids):
    """Fabrica {Human, Tool(search), AI} como los que produce un turno real del agente."""
    tool_json = json.dumps({"assets": [{"id": i} for i in ids]})
    return [
        HumanMessage(content=user_text),
        ToolMessage(content=tool_json, name="tool_find_assets_by_text", tool_call_id="t1"),
        AIMessage(content="Encontré un departamento que encaja con tu búsqueda."),
    ]


def _patch(monkeypatch, messages, rows):
    async def fake_state(_cfg):
        return _FakeState(messages)
    monkeypatch.setattr(chat, "agent_graph",
                        types.SimpleNamespace(compiled_graph=types.SimpleNamespace(aget_state=fake_state)))

    # Réplica FIEL del comportamiento real de extraer_preferencias: sin textos → {} (degrada);
    # con textos, extrae SOLO lo que el texto realmente declara (como haría el LLM real) — un
    # mock que devolviera prefs con cualquier texto no-vacío ocultaría el bug real (el punto es
    # que la lista de textos esté poblada CON el mensaje correcto, no solo que no esté vacía).
    async def fake_prefs(textos):
        junto = " ".join(textos).lower()
        prefs = {}
        if "tranquilo" in junto:
            prefs["tranquilidad"] = True
        if "parque" in junto:
            prefs["area_verde"] = True
        if "mascota" in junto:
            prefs["acepta_mascotas"] = True
        if "800" in junto:
            prefs["presupuesto_max"] = 800
        return prefs
    monkeypatch.setattr(chat, "extraer_preferencias", fake_prefs)

    async def fake_fetch(_ids):
        return (rows, {})
    monkeypatch.setattr(chat, "_fetch_cards_rows", fake_fetch)


def test_history_preserva_el_encaje_tras_recargar(monkeypatch):
    # El mensaje del usuario SÍ declara preferencias claras (repro exacta del caso real).
    texto = "Busco departamento en La Carolina, tranquilo, cerca de un parque, que acepte mascotas, hasta 800 al mes"
    rows = [_mk_row("A")]
    messages = _mensajes_de_un_turno(texto, ["A"])
    _patch(monkeypatch, messages, rows)

    hist = asyncio.run(chat.get_session_history("s"))
    turno = hist["messages"][-1]
    assert turno["role"] == "assistant"

    # La card del turno restaurado debe llevar encaje (no None) — antes del fix, SIEMPRE
    # daba None aquí porque _user_texts recibía una lista sin ningún HumanMessage.
    assert turno["results"][0]["encaje"] is not None

    # El map_seed (la directiva que colorea el mapa) también debe llevar el encaje del pin,
    # que es justo lo que reportó el feedback: el mapa caía a "ruido" por falta de encaje.
    assert turno["map_seed"] is not None
    assert turno["map_seed"]["pines"][0]["encaje"] is not None
    assert "encaje" in turno["map_seed"]["capas"]


def test_history_multiturno_acumula_preferencias_de_turnos_previos(monkeypatch):
    # Dos turnos: las preferencias se declaran en el PRIMER mensaje; el segundo turno debe
    # seguir viéndolas (el hilo completo, no solo el mensaje de ESE turno).
    t1 = _mensajes_de_un_turno(
        "Busco departamento en La Carolina, tranquilo, cerca de un parque, que acepte mascotas, hasta 800 al mes",
        ["A"],
    )
    t2 = _mensajes_de_un_turno("¿Y el segundo que me mostraste?", ["B"])
    rows = [_mk_row("A"), _mk_row("B")]
    _patch(monkeypatch, t1 + t2, rows)

    hist = asyncio.run(chat.get_session_history("s"))
    asistentes = [h for h in hist["messages"] if h["role"] == "assistant"]
    assert len(asistentes) == 2
    # Ambos turnos deben llevar encaje: el segundo turno no repite las preferencias en su
    # propio texto, pero deben seguir presentes porque vienen de TODO el hilo acumulado.
    for turno in asistentes:
        assert turno["results"][0]["encaje"] is not None


def test_history_sin_preferencias_declaradas_no_inventa_encaje(monkeypatch):
    # Guardrail de honestidad: si el usuario NUNCA declaró nada, el encaje sigue ausente
    # (None), no un valor inventado — el fix no debe "forzar" un encaje falso.
    t1 = _mensajes_de_un_turno("¿Qué hay cerca de este sector?", ["A"])
    _patch(monkeypatch, t1, [_mk_row("A")])

    hist = asyncio.run(chat.get_session_history("s"))
    turno = hist["messages"][-1]
    assert turno["results"][0]["encaje"] is None
    assert turno["map_seed"]["capas"] == []  # sin encaje ni fresco → ninguna capa
