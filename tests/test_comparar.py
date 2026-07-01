"""Tests del modo COMPARAR (app/routers/chat.py comparar_inmuebles).

La función orquesta: estado del hilo (aget_state) → preferencias (LLM) + fetch de 2 inmuebles
→ delta_encaje. Mockeamos las 3 dependencias async (grafo, extractor, query) para probar la
ORQUESTACIÓN pura: guardas (ids inválidos, id inexistente, DB caída → ok:False sin lanzar) y
el happy path (delta coherente con lo declarado). El motor delta ya se prueba en test_encaje.
"""
import asyncio
import types

from app.routers import chat


class _FakeState:
    def __init__(self, messages):
        self.values = {"messages": messages}


def _mk_row(rid, **over):
    row = {
        "id": rid, "direccion": f"Dir {rid}", "tipo_activo": "Departamento",
        "operacion": "arriendo", "precio": 700, "imagen_url": None,
        "caminabilidad": 80, "ruido": "BAJO", "vegetacion": 40,
        "lat": -0.18, "lon": -78.48,
        "caracteristicas": {"num_dormitorios": 2, "acepta_mascotas": True},
        "servicios_cercanos": "🌳 Parque a ~300 m",
        "conectividad": "🚇 Metro a ~500 m (7 min a pie)",
    }
    row.update(over)
    return row


def _patch(monkeypatch, prefs, rows, *, state=None, fetched=...):
    async def fake_state(_cfg):
        return _FakeState([]) if state is None else state
    monkeypatch.setattr(chat, "agent_graph",
                        types.SimpleNamespace(compiled_graph=types.SimpleNamespace(aget_state=fake_state)))

    async def fake_prefs(_textos):
        return prefs
    monkeypatch.setattr(chat, "extraer_preferencias", fake_prefs)

    async def fake_fetch(_ids):
        return (rows, {}) if fetched is ... else fetched
    monkeypatch.setattr(chat, "_fetch_cards_rows", fake_fetch)


# ── Guardas (nunca lanza; degrada a ok:False) ────────────────────────────────────────
def test_ids_iguales_o_vacios_no_comparan():
    assert asyncio.run(chat.comparar_inmuebles("s", "a", "a"))["ok"] is False
    assert asyncio.run(chat.comparar_inmuebles("s", "", "b"))["ok"] is False
    assert asyncio.run(chat.comparar_inmuebles("s", "a", ""))["ok"] is False


def test_id_inexistente_degrada(monkeypatch):
    _patch(monkeypatch, {"tranquilidad": True}, [_mk_row("A")])  # falta B
    res = asyncio.run(chat.comparar_inmuebles("s", "A", "B"))
    assert res["ok"] is False and "inmueble" in res["message"].lower()


def test_fetch_none_degrada(monkeypatch):
    _patch(monkeypatch, {}, [], fetched=None)  # DB caída
    assert asyncio.run(chat.comparar_inmuebles("s", "A", "B"))["ok"] is False


def test_estado_sin_sesion_no_lanza(monkeypatch):
    # aget_state devuelve None (sesión sin estado) → sin preferencias, pero compara igual.
    _patch(monkeypatch, {}, [_mk_row("A"), _mk_row("B")], state=None)

    async def fake_state(_cfg):
        return None
    monkeypatch.setattr(chat, "agent_graph",
                        types.SimpleNamespace(compiled_graph=types.SimpleNamespace(aget_state=fake_state)))
    res = asyncio.run(chat.comparar_inmuebles("s", "A", "B"))
    assert res["ok"] is True
    # Sin preferencias declaradas: el delta no tiene dimensiones (no inventa un veredicto).
    assert res["delta"]["dimensiones"] == []


# ── Happy path: delta coherente con lo declarado ─────────────────────────────────────
def test_happy_delta_gana_el_que_encaja(monkeypatch):
    rows = [_mk_row("A", precio=650), _mk_row("B", precio=950, ruido="ALTO")]
    _patch(monkeypatch, {"tranquilidad": True, "presupuesto_max": 800}, rows)
    res = asyncio.run(chat.comparar_inmuebles("s", "A", "B"))
    assert res["ok"] is True
    assert len(res["cards"]) == 2
    d = res["delta"]
    assert set(d) >= {"a", "b", "dimensiones"}
    por = {x["dimension"]: x for x in d["dimensiones"]}
    # A gana ambas: ruido BAJO vs ALTO, y precio 650≤800 vs 950 sobre presupuesto.
    assert por["tranquilidad"]["gana"] == "a"
    assert por["presupuesto_max"]["gana"] == "a"
    # Las cards salen en orden (id_a, id_b) para calzar con delta.a / delta.b.
    assert res["cards"][0]["id"] == "A" and res["cards"][1]["id"] == "B"


def test_caracteristicas_no_dict_no_lanza(monkeypatch):
    # jsonb no-objeto: "5" (str→int truthy) y [1,2] (list) NO deben reventar (.get →
    # AttributeError → 500). Se tratan como inmueble sin specs, no como un error.
    rows = [_mk_row("A", caracteristicas="5"), _mk_row("B", caracteristicas=[1, 2])]
    _patch(monkeypatch, {"min_dormitorios": 2}, rows)
    res = asyncio.run(chat.comparar_inmuebles("s", "A", "B"))
    assert res["ok"] is True and len(res["cards"]) == 2


def test_happy_cards_llevan_encaje(monkeypatch):
    rows = [_mk_row("A"), _mk_row("B")]
    _patch(monkeypatch, {"caminable": True}, rows)
    res = asyncio.run(chat.comparar_inmuebles("s", "A", "B"))
    # Con preferencia declarada (caminable) y walk_score presente, las cards traen encaje.
    assert res["cards"][0]["encaje"] is not None
