"""
Tests del motor de ORDEN (app/orden.py) — el criterio con que la persona ve los
candidatos, extraído del `sort` inline que vivía en chat.py.

El caso que motivó el módulo es `test_ficha_incompleta_no_corona_el_panel`: el promedio
ponderado del encaje solo cuenta las dimensiones CON señal ("no castigamos lo que no
sabemos", correcto), y el efecto colateral era que un inmueble sin datos podía puntuar
100% y encabezar el panel sobre uno bien documentado — enseñándole al corredor que
hidratar mal conviene.

Puros: sin DB, sin LLM, sin red. El cableado con el panel real se cubre en
tests/test_orden_encaje.py (que sigue verde: los contratos heredados no cambian).
"""
import pytest

from app.encaje import calcular_encaje
from app.orden import (
    encaje_ajustado,
    explicar_orden,
    hay_algo_que_ordenar,
    ordenar_candidatos,
)


def _c(cid, encaje=None, cobertura=None, duros=None):
    """Tarjeta ya construida: `encaje` es el número VISIBLE (ya moderado por evidencia en
    chat._ajustar_a_entero), que es exactamente por el que ordena el módulo."""
    return {"id": cid, "encaje": encaje, "encaje_cobertura": cobertura,
            "duros_incumplidos": duros or []}


# ── El contrato central: lo que se ve es lo que ordena ──────────────────────────────

def test_ordena_por_el_numero_visible_de_mayor_a_menor():
    # La promesa que la persona lee en pantalla: izquierda→derecha, de más a menos encaje.
    cards = [_c("c", 61), _c("a", 88), _c("b", 74)]
    orden = ordenar_candidatos(cards)
    visibles = [c["encaje"] for c in orden]
    assert visibles == sorted(visibles, reverse=True) == [88, 74, 61]


def test_el_modulo_no_re_ajusta_lo_que_ya_viene_ajustado():
    # Doble ajuste = el número pintado y el orden vuelven a divergir. La cobertura viaja en
    # la tarjeta para el registro auditable, pero NO debe volver a mover el orden.
    cards = [_c("alto_con_poca_evidencia", 90, cobertura=0.1), _c("bajo_completo", 70, 1.0)]
    assert [c["id"] for c in ordenar_candidatos(cards)] == ["alto_con_poca_evidencia",
                                                            "bajo_completo"]


def test_ficha_completa_no_paga_nada_por_estar_completa():
    # cobertura 1.0 → el ajustado ES el score. Quien hidrata bien no es penalizado.
    assert encaje_ajustado(82, 1.0) == 82.0
    assert encaje_ajustado(0, 1.0) == 0.0
    assert encaje_ajustado(100, 1.0) == 100.0


def test_el_encogimiento_es_simetrico():
    # "No sé" no puede coronar a nadie, pero tampoco hundirlo: un score bajo con poca
    # evidencia SUBE hacia el neutro. Misma regla que hace que score=None no sea 0.
    assert encaje_ajustado(100, 0.2) < 100
    assert encaje_ajustado(20, 0.2) > 20
    assert encaje_ajustado(50, 0.01) == pytest.approx(50.0)  # el neutro es punto fijo


def test_el_ajuste_no_depende_del_conjunto():
    # El punto neutro es una constante, no una media del lote: el ajustado de un inmueble
    # no cambia porque aparezca otro. Un número que se mueve con el inventario sería
    # imposible de auditar y haría saltar el badge entre turnos.
    assert encaje_ajustado(90, 0.5) == encaje_ajustado(90, 0.5)
    a, b = _c("a", 70), _c("b", 60)
    par = [x["id"] for x in ordenar_candidatos([a, b])]
    trio = [x["id"] for x in ordenar_candidatos([a, b, _c("c", 99)]) if x["id"] != "c"]
    assert par == trio


# ── Llave 1: requisitos duros ───────────────────────────────────────────────────────

def test_requisito_duro_incumplido_va_despues_aunque_puntue_mas():
    # Pediste departamento y esto es una casa: no es lo que pediste, no puede ir primero
    # por más que su encaje topado siga siendo alto respecto del resto.
    casa = _c("casa", encaje=49, cobertura=1.0, duros=["tipo_inmueble"])
    depto = _c("depto", encaje=40, cobertura=1.0)

    assert [c["id"] for c in ordenar_candidatos([casa, depto])] == ["depto", "casa"]


# ── Contratos heredados del sort que reemplaza ──────────────────────────────────────

def test_sin_encaje_en_ninguna_preserva_el_orden_de_entrada():
    # Sin preferencias declaradas no se inventa un ranking: manda el orden espacial.
    cards = [_c("A"), _c("B"), _c("C")]
    assert [c["id"] for c in ordenar_candidatos(cards)] == ["A", "B", "C"]
    assert hay_algo_que_ordenar(cards) is False


def test_sin_encaje_puntuable_degrada_al_final_pero_no_desaparece():
    cards = [_c("sin_senal"), _c("bueno", 80, 1.0), _c("regular", 60, 1.0)]
    orden = ordenar_candidatos(cards)
    assert [c["id"] for c in orden] == ["bueno", "regular", "sin_senal"]
    assert len(orden) == 3
    assert orden[-1]["encaje"] is None  # sigue honesto: "sin dato", no un 0% inventado


def test_el_empate_es_estable_y_no_muta_la_entrada():
    cards = [_c("primero", 70, 1.0), _c("segundo", 70, 1.0)]
    orden = ordenar_candidatos(cards)
    assert [c["id"] for c in orden] == ["primero", "segundo"]
    assert cards[0]["id"] == "primero"  # la lista original queda intacta
    assert orden is not cards


# ── Defensivo: la tarjeta puede venir de un historial viejo o de la DB ──────────────

def test_cobertura_ausente_no_penaliza():
    # Una tarjeta de un camino que aún no calcula cobertura (historial viejo) no puede
    # perder posición por un campo que no existía. Ausente == 1.0.
    vieja = {"id": "vieja", "encaje": 90}
    nueva = _c("nueva", 80, 1.0)
    assert [c["id"] for c in ordenar_candidatos([nueva, vieja])] == ["vieja", "nueva"]


@pytest.mark.parametrize("basura", ["", "ochenta", None, True, float("nan"), float("inf")])
def test_encaje_no_numerico_se_trata_como_sin_dato(basura):
    assert encaje_ajustado(basura, 1.0) is None


def test_cobertura_basura_no_revienta_ni_saca_del_rango():
    assert encaje_ajustado(80, "mucha") == 80.0   # incoercible → 1.0 (no penaliza)
    assert encaje_ajustado(80, 5) == 80.0         # se topa en 1.0
    assert encaje_ajustado(80, -3) == 50.0        # se topa en 0.0 → neutro puro


def test_lista_vacia_o_none():
    assert ordenar_candidatos([]) == []
    assert ordenar_candidatos(None) == []
    assert explicar_orden([]) == []


# ── El registro auditable ───────────────────────────────────────────────────────────

def test_explicar_orden_deja_el_rastro_completo():
    a = _c("A", 62, 1.5 / 6.5); a["encaje_medido"] = 100   # ficha incompleta ya moderada
    b = _c("B", 75, 1.0); b["encaje_medido"] = 75          # ficha completa, sin moderar
    filas = explicar_orden([a, b])

    assert [f["id"] for f in filas] == ["B", "A"]
    assert [f["posicion"] for f in filas] == [0, 1]
    # Cada fila permite reconstruir la decisión: el visible, el crudo y la evidencia.
    assert filas[1]["encaje"] == 62 and filas[1]["encaje_medido"] == 100
    assert filas[1]["cobertura"] == pytest.approx(1.5 / 6.5)


# ── La cobertura que emite el motor de encaje es la que el orden consume ────────────

def test_cobertura_del_motor_refleja_el_peso_evaluado():
    prefs = {"tipo_inmueble": "departamento", "presupuesto_max": 800,
             "tranquilidad": True, "caminable": True}
    completo = {"tipo_activo": "Departamento", "precio": 700, "ruido": "BAJO", "walk_score": 90}
    parcial = {"tipo_activo": "Departamento", "precio": 700}  # sin ruido ni walk_score

    r_completo = calcular_encaje(prefs, completo)
    r_parcial = calcular_encaje(prefs, parcial)

    assert r_completo["cobertura"] == pytest.approx(1.0)
    # peso evaluado = tipo(1.0) + presupuesto(1.5) = 2.5 · declarado = 4.5
    assert r_parcial["cobertura"] == pytest.approx(2.5 / 4.5)
    # El parcial puntúa MÁS alto en crudo (solo se le promedia lo bueno)...
    assert r_parcial["score"] > r_completo["score"]
    # ...pero moderado por su evidencia baja, y el completo (cobertura 1.0) no se toca.
    aj_parcial = encaje_ajustado(r_parcial["score"], r_parcial["cobertura"])
    aj_completo = encaje_ajustado(r_completo["score"], r_completo["cobertura"])
    assert aj_completo == r_completo["score"]
    assert aj_parcial < aj_completo


def test_sin_nada_evaluable_la_cobertura_es_cero_y_el_score_none():
    r = calcular_encaje({"tranquilidad": True}, {"tipo_activo": "Departamento"})
    assert r["score"] is None and r["cobertura"] == 0.0


# ── Cableado real con el panel (el módulo puro puede estar bien y chat.py mal) ──────

def test_el_panel_real_no_corona_la_ficha_incompleta(monkeypatch):
    """End-to-end por construir_panel: la ficha sin datos de entorno puntúa MÁS alto y aun
    así no encabeza el carrusel. Mismo patrón de mocking que tests/test_orden_encaje.py."""
    import asyncio
    import json as _json

    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from app.routers import chat

    def _row(rid, **over):
        row = {
            "id": rid, "direccion": f"Dir {rid}", "tipo_activo": "Departamento",
            "operacion": "arriendo", "precio": 700, "imagen_url": None,
            "caminabilidad": None, "ruido": None, "vegetacion": None,
            "lat": -0.18, "lon": -78.48,
            "caracteristicas": {"num_dormitorios": 2},
            "servicios_cercanos": None, "conectividad": None,
        }
        row.update(over)
        return row

    rows = [
        # Solo precio evaluable (dentro del tope) → encaje alto con evidencia mínima.
        _row("incompleta"),
        # Ficha completa: dentro del tope, pero ruido medio y caminabilidad mediana.
        _row("completa", ruido="MEDIO", caminabilidad=55,
             servicios_cercanos="🌳 Parque a ~900 m", conectividad="🚇 Metro a ~1,2 km (18 min a pie)"),
    ]

    async def fake_fetch(_ids):
        return (rows, {})

    async def fake_prefs(_textos):
        return {"tipo_inmueble": "departamento", "presupuesto_max": 800,
                "tranquilidad": True, "caminable": True}

    monkeypatch.setattr(chat, "_fetch_cards_rows", fake_fetch)
    monkeypatch.setattr(chat, "extraer_preferencias", fake_prefs)

    messages = [
        HumanMessage(content="Departamento tranquilo y caminable, hasta 800"),
        ToolMessage(content=_json.dumps({"assets": [{"id": "incompleta"}, {"id": "completa"}]}),
                    name="tool_find_assets_by_text", tool_call_id="t1"),
        AIMessage(content="Encontré estas opciones."),
    ]
    cards = asyncio.run(chat.build_result_cards(messages))
    por_id = {c["id"]: c for c in cards}

    # En CRUDO la incompleta puntúa más (se le promedia solo lo bueno que sí tiene)...
    assert por_id["incompleta"]["encaje_medido"] > por_id["completa"]["encaje_medido"]
    # ...pero el número VISIBLE ya viene moderado por su evidencia, y por eso va después.
    assert por_id["incompleta"]["encaje"] < por_id["completa"]["encaje"]
    assert [c["id"] for c in cards] == ["completa", "incompleta"]
    # La ficha completa no paga peaje: su visible es idéntico a su crudo.
    assert por_id["completa"]["encaje"] == por_id["completa"]["encaje_medido"]


def test_el_panel_se_lee_de_mayor_a_menor_encaje(monkeypatch):
    """El requisito de producto: izquierda→derecha, de más encaje a menos, SIN excepciones.
    Es lo que se rompía si el orden usaba un número distinto del pintado."""
    import asyncio
    import json as _json

    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from app.routers import chat

    def _row(rid, **over):
        row = {"id": rid, "direccion": f"Dir {rid}", "tipo_activo": "Departamento",
               "operacion": "arriendo", "precio": 700, "imagen_url": None,
               "caminabilidad": None, "ruido": None, "vegetacion": None,
               "lat": -0.18, "lon": -78.48, "caracteristicas": {"num_dormitorios": 2},
               "servicios_cercanos": None, "conectividad": None}
        row.update(over)
        return row

    # Mezcla deliberada de fichas ricas y pobres, en desorden de entrada.
    rows = [
        _row("pobre"),
        _row("rica", ruido="BAJO", caminabilidad=88,
             servicios_cercanos="🌳 Parque a ~200 m", conectividad="🚇 Metro a ~400 m (6 min a pie)"),
        _row("media", ruido="ALTO", caminabilidad=40),
        _row("rica2", precio=760, ruido="MEDIO", caminabilidad=75,
             servicios_cercanos="🌳 Parque a ~600 m", conectividad="🚇 Metro a ~900 m (13 min a pie)"),
    ]

    async def fake_fetch(_ids):
        return (rows, {})

    async def fake_prefs(_textos):
        return {"tipo_inmueble": "departamento", "presupuesto_max": 800,
                "tranquilidad": True, "caminable": True, "area_verde": True}

    monkeypatch.setattr(chat, "_fetch_cards_rows", fake_fetch)
    monkeypatch.setattr(chat, "extraer_preferencias", fake_prefs)
    messages = [
        HumanMessage(content="Departamento tranquilo, caminable, con verde, hasta 800"),
        ToolMessage(content=_json.dumps({"assets": [{"id": r["id"]} for r in rows]}),
                    name="tool_find_assets_by_text", tool_call_id="t1"),
        AIMessage(content="Encontré estas."),
    ]
    panel = asyncio.run(chat.construir_panel(messages))
    visibles = [c["encaje"] for c in panel["cards"]]

    assert len(visibles) >= 2, "el caso necesita al menos dos tarjetas para probar el orden"
    assert all(v is not None for v in visibles)
    assert visibles == sorted(visibles, reverse=True), (
        f"el panel debe leerse de mayor a menor encaje visible; llegó: {visibles}"
    )
