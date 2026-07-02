"""Tests del eje de OPERACION (arriendo/venta) — hallazgo del workflow del 2026-07-01.

Bug de raiz: el sistema NO tenia eje de operacion. El extractor de preferencias tenia un
schema cerrado de 7 dimensiones, ninguna era operacion, asi que 'arriendo hasta 800 al mes'
capturaba solo presupuesto_max=800 y TIRABA el 'arriendo'. Luego _score_presupuesto comparaba
$256.500 (precio de VENTA) contra $800 (canon MENSUAL de arriendo) como misma magnitud → la
venta aparecia en el Mapa Vivo mezclada con arriendos de $800/mes.

Fix (decisiones del founder confirmadas): (1) capturar 'operacion' como senal APARTE del encaje
(enum cerrado arriendo|venta, no puntua); (2) filtrar tarjetas/pines a la operacion declarada
SOLO si el usuario la declaro — exploracion de zona ('que hay cerca') sigue mixta; (3) inmuebles
sin operacion registrada NO se excluyen (dato faltante != no encaja); (4) presupuesto sigue
BLANDO (⚠️), no filtro duro; (5) si nada coincide, degrada mostrando lo mas cercano (no vacia).
"""
import asyncio
import json

from langchain_core.messages import ToolMessage

from app import preferencias as prefs_mod
from app.encaje import calcular_encaje
from app.routers import chat


# ── _sanitizar: operacion como enum controlado, canal aparte del encaje ──────────────

def test_sanitizar_acepta_operacion_enum_y_normaliza_caja():
    assert prefs_mod._sanitizar({"operacion": "Arriendo"}) == {"operacion": "arriendo"}
    assert prefs_mod._sanitizar({"operacion": "VENTA"}) == {"operacion": "venta"}
    assert prefs_mod._sanitizar({"operacion": " venta "}) == {"operacion": "venta"}


def test_sanitizar_rechaza_operacion_fuera_del_enum():
    # Cualquier valor fuera del enum cerrado se descarta: no abre la whitelist Fair Housing.
    assert prefs_mod._sanitizar({"operacion": "alquiler_temporal"}) == {}
    assert prefs_mod._sanitizar({"operacion": 3}) == {}
    assert prefs_mod._sanitizar({"operacion": True}) == {}
    assert prefs_mod._sanitizar({"operacion": None}) == {}


def test_operacion_convive_con_dimensiones_reales():
    # operacion pasa junto a las dimensiones normales, sin descartarlas.
    out = prefs_mod._sanitizar({"operacion": "arriendo", "presupuesto_max": 800, "tranquilidad": True})
    assert out == {"operacion": "arriendo", "presupuesto_max": 800.0, "tranquilidad": True}


def test_operacion_no_contamina_el_score_de_encaje():
    # operacion NO es dimension de encaje: agregarla a las prefs no cambia el score ni aparece
    # como razon. Es la separacion Fair-Housing/filtro-duro (canal aparte de DIMENSIONES).
    inm = {"precio": 500}
    base = calcular_encaje({"presupuesto_max": 800}, inm)
    con_op = calcular_encaje({"presupuesto_max": 800, "operacion": "arriendo"}, inm)
    assert base["score"] == con_op["score"]
    assert "operacion" not in [r["dimension"] for r in con_op["razones"]]


# ── build_result_cards: el filtro de operacion ───────────────────────────────────────

def _tool_msg(ids):
    """Fabrica el ToolMessage de una busqueda como el que produce un turno real."""
    return ToolMessage(
        content=json.dumps({"assets": [{"id": i} for i in ids]}),
        name="tool_find_assets_by_text",
        tool_call_id="t1",
    )


def _row(rid, operacion, precio=500):
    return {
        "id": rid, "direccion": f"Dir {rid}", "tipo_activo": "Departamento",
        "imagen_url": None, "caminabilidad": 90, "ruido": "BAJO", "vegetacion": 40,
        "servicios_cercanos": None, "conectividad": None,
        "lat": -0.18, "lon": -78.48, "caracteristicas": {},
        "operacion": operacion, "precio": precio,
    }


def _cards(monkeypatch, ids, rows, preferencias):
    async def fake_fetch(_ids):
        return (rows, {})
    monkeypatch.setattr(chat, "_fetch_cards_rows", fake_fetch)
    return asyncio.run(chat.build_result_cards([_tool_msg(ids)], preferencias=preferencias))


def test_filtra_a_arriendo_cuando_el_usuario_lo_declara(monkeypatch):
    # El caso reportado en vivo: pidio arriendo, aparecia una VENTA de $256.500 mezclada.
    ids = ["A", "B", "C"]
    rows = [_row("A", "ARRIENDO"), _row("B", "VENTA", 256500), _row("C", "ARRIENDO")]
    cards = _cards(monkeypatch, ids, rows, {"operacion": "arriendo"})
    assert [c["id"] for c in cards] == ["A", "C"]  # la VENTA (B) queda fuera


def test_filtra_a_venta_cuando_el_usuario_lo_declara(monkeypatch):
    ids = ["A", "B", "C"]
    rows = [_row("A", "ARRIENDO"), _row("B", "VENTA", 256500), _row("C", "VENTA", 180000)]
    cards = _cards(monkeypatch, ids, rows, {"operacion": "venta"})
    assert [c["id"] for c in cards] == ["B", "C"]


def test_sin_operacion_declarada_muestra_inventario_mixto(monkeypatch):
    # Exploracion de zona ('que hay cerca'): NO se filtra, se preserva el Mapa Vivo ZONA.
    ids = ["A", "B", "C"]
    rows = [_row("A", "ARRIENDO"), _row("B", "VENTA", 256500), _row("C", "ARRIENDO")]
    cards = _cards(monkeypatch, ids, rows, {})  # sin operacion declarada
    assert [c["id"] for c in cards] == ["A", "B", "C"]  # mixto intacto


def test_inmueble_sin_operacion_registrada_no_se_excluye(monkeypatch):
    # Dato faltante != no encaja: un inmueble sin fila en transacciones (operacion None) pasa.
    ids = ["A", "B", "C"]
    rows = [_row("A", "ARRIENDO"), _row("B", None), _row("C", "VENTA", 256500)]
    cards = _cards(monkeypatch, ids, rows, {"operacion": "arriendo"})
    assert [c["id"] for c in cards] == ["A", "B"]  # A (arriendo) y B (sin dato); C (venta) fuera


def test_degrada_mostrando_lo_mas_cercano_si_nada_coincide(monkeypatch):
    # Si toda la zona es VENTA y el usuario pidio ARRIENDO, NO vaciar el turno: mostrar lo mas
    # cercano (el badge VENTA de cada tarjeta mantiene la honestidad).
    ids = ["A", "B"]
    rows = [_row("A", "VENTA", 256500), _row("B", "VENTA", 180000)]
    cards = _cards(monkeypatch, ids, rows, {"operacion": "arriendo"})
    assert [c["id"] for c in cards] == ["A", "B"]  # degradacion, no lista vacia


def test_respeta_tope_de_seis_tarjetas_tras_filtrar(monkeypatch):
    # Con holgura de recoleccion (2×6) el filtro tiene material, pero el tope visible sigue 6.
    ids = [f"A{i}" for i in range(8)]
    rows = [_row(i, "ARRIENDO") for i in ids]
    cards = _cards(monkeypatch, ids, rows, {"operacion": "arriendo"})
    assert len(cards) == 6
    assert [c["id"] for c in cards] == ids[:6]  # los 6 primeros (mas cercanos)


def test_monitoreo_pasivo_se_excluye_al_declarar_operacion(monkeypatch):
    # MONITOREO_PASIVO = activo vigilado, NO en mercado: al declarar operacion nunca se ofrece.
    ids = ["A", "B", "C"]
    rows = [_row("A", "ARRIENDO"), _row("B", "MONITOREO_PASIVO"), _row("C", "ARRIENDO")]
    cards = _cards(monkeypatch, ids, rows, {"operacion": "arriendo"})
    assert [c["id"] for c in cards] == ["A", "C"]  # B (monitoreo) fuera


def test_monitoreo_pasivo_no_se_recuela_en_la_degradacion(monkeypatch):
    # Hallazgo adversarial: si NADA coincide (toda la zona es venta+monitoreo y pidio arriendo),
    # la degradacion debe mostrar solo lo OFERTABLE (venta), nunca re-colar el MONITOREO_PASIVO.
    ids = ["A", "B", "C"]
    rows = [_row("A", "VENTA", 256500), _row("B", "MONITOREO_PASIVO"), _row("C", "VENTA", 180000)]
    cards = _cards(monkeypatch, ids, rows, {"operacion": "arriendo"})
    assert [c["id"] for c in cards] == ["A", "C"]  # degradacion a ventas; B (monitoreo) fuera


def test_comparar_rechaza_operaciones_distintas(monkeypatch):
    # El bug de raiz (mezclar magnitudes) tambien era alcanzable por COMPARAR: comparar un
    # arriendo contra una venta contra un mismo presupuesto_max da un delta sin sentido.
    import types

    rows = [_row("A", "ARRIENDO", 800), _row("B", "VENTA", 256500)]

    async def fake_state(_cfg):
        return types.SimpleNamespace(values={"messages": []})
    monkeypatch.setattr(chat, "agent_graph",
                        types.SimpleNamespace(compiled_graph=types.SimpleNamespace(aget_state=fake_state)))

    async def fake_prefs(_textos):
        return {"operacion": "arriendo", "presupuesto_max": 800}
    monkeypatch.setattr(chat, "extraer_preferencias", fake_prefs)

    async def fake_fetch(_ids):
        return (rows, {})
    monkeypatch.setattr(chat, "_fetch_cards_rows", fake_fetch)

    res = asyncio.run(chat.comparar_inmuebles("s", "A", "B"))
    assert res["ok"] is False
    assert "arriendo" in res["message"].lower() and "venta" in res["message"].lower()


def test_comparar_permite_misma_operacion(monkeypatch):
    # Dos inmuebles de la MISMA operacion sí se comparan (magnitudes homogeneas).
    import types

    rows = [_row("A", "ARRIENDO", 700), _row("B", "ARRIENDO", 800)]

    async def fake_state(_cfg):
        return types.SimpleNamespace(values={"messages": []})
    monkeypatch.setattr(chat, "agent_graph",
                        types.SimpleNamespace(compiled_graph=types.SimpleNamespace(aget_state=fake_state)))

    async def fake_prefs(_textos):
        return {"operacion": "arriendo", "presupuesto_max": 800}
    monkeypatch.setattr(chat, "extraer_preferencias", fake_prefs)

    async def fake_fetch(_ids):
        return (rows, {})
    monkeypatch.setattr(chat, "_fetch_cards_rows", fake_fetch)

    res = asyncio.run(chat.comparar_inmuebles("s", "A", "B"))
    assert res["ok"] is True
    assert {c["id"] for c in res["cards"]} == {"A", "B"}
