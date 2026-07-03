"""
Test del bug real (feedback en vivo, demo Mazatlán con Ricardo, 2026-07-03): las tarjetas
del mapa se devolvían en el orden crudo de la búsqueda espacial/similitud, NO por qué tan
bien encajaban con lo que el usuario pidió. En la demo, la PEOR opción (37% de encaje, fuera
de presupuesto, zona ruidosa) apareció PRIMERA en el carrusel — contradiciendo la promesa
central del producto de curaduría ("1-3 mejores opciones primero", nunca listas sin criterio).

build_result_cards ahora reordena por `encaje` descendente ANTES de recortar a _MAX_CARDS,
pero SOLO cuando hay algo real que ordenar: sin preferencias declaradas (encaje=None en
todas), el orden espacial/similitud original se preserva tal cual — no se inventa un
ranking donde no hay necesidad declarada que puntuar. Las tarjetas individuales sin encaje
puntuable (None: falta señal, no "no encaja") degradan al final, nunca desaparecen ni se
muestran como 0% falso.

Reusa el patrón de mocking de test_history_encaje.py (mismo módulo bajo prueba).
"""
import asyncio
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.routers import chat


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
        AIMessage(content="Encontré unos inmuebles que podrían servirte."),
    ]


def _patch_prefs_tranquilidad_presupuesto(monkeypatch):
    # Réplica fiel del comportamiento real de extraer_preferencias (como en
    # test_history_encaje.py): solo extrae lo que el texto realmente declara.
    async def fake_prefs(textos):
        junto = " ".join(textos).lower()
        prefs = {}
        if "tranquilo" in junto:
            prefs["tranquilidad"] = True
        if "800" in junto:
            prefs["presupuesto_max"] = 800
        return prefs
    monkeypatch.setattr(chat, "extraer_preferencias", fake_prefs)


def _patch_fetch(monkeypatch, rows):
    async def fake_fetch(_ids):
        return (rows, {})
    monkeypatch.setattr(chat, "_fetch_cards_rows", fake_fetch)


def test_tarjetas_se_reordenan_por_encaje_descendente(monkeypatch):
    # Repro exacta del bug de la demo: la búsqueda espacial trae primero al inmueble caro y
    # ruidoso (peor encaje) y al final al barato y silencioso (mejor encaje) — el orden
    # crudo NO debe sobrevivir cuando el usuario declaró lo que le importa.
    rows = [
        _mk_row("caro_ruidoso", precio=1130, ruido="ALTO"),   # peor encaje: fuera de presupuesto + ruido alto
        _mk_row("medio", precio=550, ruido="MEDIO"),
        _mk_row("barato_silencioso", precio=380, ruido="BAJO"),  # mejor encaje: dentro de presupuesto + silencioso
    ]
    _patch_fetch(monkeypatch, rows)
    _patch_prefs_tranquilidad_presupuesto(monkeypatch)

    texto = "Busco departamento tranquilo, hasta 800 al mes"
    messages = _mensajes_de_un_turno(texto, ["caro_ruidoso", "medio", "barato_silencioso"])

    cards = asyncio.run(chat.build_result_cards(messages))

    encajes = [c["encaje"] for c in cards]
    assert encajes == sorted(encajes, reverse=True), (
        f"las tarjetas deben venir ordenadas de mayor a menor encaje, llegaron: {encajes}"
    )
    # La peor opción (fuera de presupuesto, ruido alto) NO debe encabezar el carrusel —
    # exactamente el defecto que se vio en vivo.
    assert cards[0]["id"] == "barato_silencioso"
    assert cards[-1]["id"] == "caro_ruidoso"


def test_sin_preferencias_declaradas_preserva_el_orden_espacial(monkeypatch):
    # Sin nada que el usuario haya declarado, el encaje es None en todas las tarjetas
    # (guardrail de honestidad: "no sé" no es "no encaja") — el sort no debe inventar un
    # ranking ahí: el orden espacial/similitud original se preserva tal cual.
    rows = [_mk_row("A"), _mk_row("B"), _mk_row("C")]
    _patch_fetch(monkeypatch, rows)

    async def fake_prefs_vacio(_textos):
        return {}
    monkeypatch.setattr(chat, "extraer_preferencias", fake_prefs_vacio)

    messages = _mensajes_de_un_turno("¿Qué hay en este sector?", ["A", "B", "C"])
    cards = asyncio.run(chat.build_result_cards(messages))

    assert [c["id"] for c in cards] == ["A", "B", "C"]
    assert all(c["encaje"] is None for c in cards)


def test_tarjeta_sin_encaje_puntuable_degrada_al_final_no_desaparece(monkeypatch):
    # Con preferencias declaradas, una tarjeta que no tiene NINGUNA señal relevante para
    # puntuar (encaje=None individual, no por falta de preferencias sino por falta de dato
    # en ESE inmueble) no debe saltar al frente ni desaparecer: degrada al final, sin
    # inventar un 0% ni un ranking falso.
    rows = [
        _mk_row("sin_senal", precio=None, ruido=None),  # nada que puntuar para tranquilidad/presupuesto
        _mk_row("buen_encaje", precio=380, ruido="BAJO"),
    ]
    _patch_fetch(monkeypatch, rows)
    _patch_prefs_tranquilidad_presupuesto(monkeypatch)

    texto = "Busco departamento tranquilo, hasta 800 al mes"
    messages = _mensajes_de_un_turno(texto, ["sin_senal", "buen_encaje"])

    cards = asyncio.run(chat.build_result_cards(messages))

    assert cards[0]["id"] == "buen_encaje"
    assert cards[0]["encaje"] is not None
    assert cards[-1]["id"] == "sin_senal"
    assert cards[-1]["encaje"] is None  # sigue siendo honesto: "sin dato", no un número inventado
