"""F2 · CHARACTERIZATION — el oráculo de paridad del panel legado.

QUÉ ES ESTO. Estas pruebas **no describen lo que el panel debería hacer**: congelan lo
que hace HOY, sobre `84eb2c0`, antes de mover una sola línea. Si una de ellas cambia
durante F2, la refactorización cambió comportamiento observable — y eso es un fallo de
F2, no un test que haya que "actualizar".

NO SE BORRA AL TERMINAR. Es el oráculo, y sigue valiendo después del merge.

CÓMO ESTÁ ESCRITO. Igualdad exacta donde el output es determinista, que es casi todo:
ids, orden, descartadas, encaje visible, encaje medido, cobertura, conteos, razones,
duros incumplidos, priorizado y el bloque autoritativo. Nada de asserts vagos tipo
"contiene" — si hoy es estable, se congela estable.

EL PUNTO DE ENTRADA es deliberadamente `construir_panel`. Durante E2.1 se moverá a
`app/decision/`, y estas mismas pruebas —cambiando solo el import— tienen que seguir
dando lo mismo. Ese es el experimento.
"""

import asyncio
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.encaje_contexto import bloque_autoritativo
from app.routers import chat
from app.decision import assembler

# ── El inventario congelado ──────────────────────────────────────────────────────


def _row(rid, **over):
    """Una fila de catastro como la devuelve `_fetch_cards_rows`."""
    row = {
        "id": rid,
        "direccion": f"Dir {rid}",
        "tipo_activo": "Departamento",
        "operacion": "ARRIENDO",
        "precio": 380,
        "imagen_url": None,
        "caminabilidad": 95,
        "caminabilidad_fuente": "osm",
        "ruido": "BAJO",
        "vegetacion": 42,
        "lat": -0.18,
        "lon": -78.48,
        "caracteristicas": {"num_dormitorios": 2, "acepta_mascotas": True},
        "servicios_cercanos": "🌳 Parque a ~300 m",
        "conectividad": "🚇 Metro a ~500 m (7 min a pie)",
    }
    row.update(over)
    return row


def _turno(texto, ids, extra_tools=()):
    msgs = [
        HumanMessage(content=texto),
        ToolMessage(
            content=json.dumps({"assets": [{"id": i} for i in ids]}),
            name="tool_search_nearby_assets",
            tool_call_id="t1",
        ),
    ]
    msgs.extend(extra_tools)
    msgs.append(AIMessage(content="Encontré algunas opciones."))
    return msgs


def _panel(monkeypatch, ids, rows, prefs, extra_tools=()):
    """Ejecuta el panel con la DB mockeada. `prefs` explícitas ⇒ no se llama al LLM."""

    async def fake_fetch(_ids):
        return (rows, {})

    monkeypatch.setattr(assembler, "_fetch_cards_rows", fake_fetch)
    return asyncio.run(
        chat.construir_panel(_turno("consulta", ids, extra_tools), preferencias=prefs)
    )


def _decision(panel):
    """Los ejes que MANDAN. Se separan de la presentación a propósito: son los que F2 no
    puede alterar bajo ninguna circunstancia."""
    return {
        "orden": [c["id"] for c in panel["cards"]],
        "descartadas": [c["id"] for c in panel["descartadas"]],
        "priorizado": panel["priorizado"],
        "encaje": {c["id"]: c["encaje"] for c in panel["cards"]},
        "encaje_medido": {c["id"]: c["encaje_medido"] for c in panel["cards"]},
        "cobertura": {c["id"]: c["encaje_cobertura"] for c in panel["cards"]},
        "evaluadas": {c["id"]: c["encaje_evaluadas"] for c in panel["cards"]},
        "declaradas": {c["id"]: c["encaje_declaradas"] for c in panel["cards"]},
        "duros": {c["id"]: c["duros_incumplidos"] for c in panel["cards"]},
        "operacion": {c["id"]: c["operacion"] for c in panel["cards"]},
        "precio": {c["id"]: c["precio"] for c in panel["cards"]},
        "razones": {c["id"]: c["encaje_razones"] for c in panel["cards"]},
    }


_PREFS_COMPLETAS = {
    "operacion": "arriendo",
    "tipo_inmueble": "departamento",
    "presupuesto_max": 700,
    "tranquilidad": True,
    "caminable": True,
    "area_verde": True,
    "acepta_mascotas": True,
}


# ── A. sin preferencias ──────────────────────────────────────────────────────────


def test_A_sin_preferencias_conserva_el_orden_espacial(monkeypatch):
    """Sin necesidades declaradas no se inventa un ranking: el orden es el de entrada."""
    ids = ["c", "a", "b"]
    panel = _panel(monkeypatch, ids, [_row(i) for i in ids], {})
    assert _decision(panel) == {
        "orden": ["c", "a", "b"],
        "descartadas": [],
        "priorizado": (None, None),
        "encaje": {"c": None, "a": None, "b": None},
        "encaje_medido": {"c": None, "a": None, "b": None},
        "cobertura": {"c": None, "a": None, "b": None},
        "evaluadas": {"c": None, "a": None, "b": None},
        "declaradas": {"c": None, "a": None, "b": None},
        "duros": {"c": [], "a": [], "b": []},
        "operacion": {"c": "ARRIENDO", "a": "ARRIENDO", "b": "ARRIENDO"},
        "precio": {"c": 380.0, "a": 380.0, "b": 380.0},
        "razones": {"c": [], "a": [], "b": []},
    }


def test_A2_sin_candidatos_devuelve_panel_vacio(monkeypatch):
    async def fake_fetch(_ids):
        return ([], {})

    monkeypatch.setattr(assembler, "_fetch_cards_rows", fake_fetch)
    panel = asyncio.run(chat.construir_panel(_turno("hola", []), preferencias={}))
    assert panel == {"cards": [], "descartadas": [], "preferencias": {}, "priorizado": (None, None)}


# ── B. preferencias + ranking normal ─────────────────────────────────────────────


def test_B_el_ranking_va_de_mayor_a_menor_encaje_visible(monkeypatch):
    ids = ["caro", "barato", "medio"]
    rows = [_row("caro", precio=690), _row("barato", precio=300), _row("medio", precio=500)]
    panel = _panel(monkeypatch, ids, rows, _PREFS_COMPLETAS)
    d = _decision(panel)
    visibles = [d["encaje"][i] for i in d["orden"]]
    assert visibles == sorted(visibles, reverse=True), f"orden={d['orden']} encaje={visibles}"
    assert d["orden"] == ["caro", "barato", "medio"]
    assert d["descartadas"] == []


# ── C. requisito duro de tipo ────────────────────────────────────────────────────


def test_C_una_casa_cuando_se_pidio_departamento_queda_topada(monkeypatch):
    ids = ["depto", "casa"]
    rows = [_row("depto"), _row("casa", tipo_activo="Casa")]
    panel = _panel(monkeypatch, ids, rows, _PREFS_COMPLETAS)
    d = _decision(panel)
    # El filtro duro de tipo la saca del panel por construcción.
    assert d["orden"] == ["depto"]
    assert d["duros"]["depto"] == []


def test_C2_si_todo_es_del_tipo_equivocado_degrada_pero_marca_el_duro(monkeypatch):
    """"Dato faltante ≠ no encaja", pero al degradar el encaje viene TOPADO por el motor."""
    ids = ["casa1", "casa2"]
    rows = [_row("casa1", tipo_activo="Casa"), _row("casa2", tipo_activo="Casa")]
    panel = _panel(monkeypatch, ids, rows, _PREFS_COMPLETAS)
    d = _decision(panel)
    assert d["orden"], "el panel nunca se vacía"
    for i in d["orden"]:
        assert "tipo_inmueble" in d["duros"][i]
        assert d["encaje"][i] <= 49, "el tope de requisito duro no se puede coronar"


# ── D. presupuesto: los cuatro bordes ────────────────────────────────────────────


@pytest.mark.parametrize(
    "precio,visible",
    [
        (500, True),    # dentro
        (700, True),    # exactamente en el límite
        (710, True),    # ligeramente por encima — dentro del margen del 10 %
        (990, False),   # fuera del margen → lo corta el panel
    ],
)
def test_D_bordes_de_presupuesto(monkeypatch, precio, visible):
    """El margen deja pasar el "casi entra" ($710 contra $700) y corta el que no es una
    opción. Frontera exacta, no aproximada."""
    ids = ["ancla", "sujeto"]
    rows = [_row("ancla", precio=300), _row("sujeto", precio=precio)]
    panel = _panel(monkeypatch, ids, rows, _PREFS_COMPLETAS)
    d = _decision(panel)
    assert ("sujeto" in d["orden"]) is visible
    if not visible:
        assert "sujeto" in d["descartadas"]


def test_D2_el_panel_nunca_se_vacia_aunque_todo_este_fuera(monkeypatch):
    ids = ["a", "b"]
    rows = [_row("a", precio=5000), _row("b", precio=9000)]
    panel = _panel(monkeypatch, ids, rows, _PREFS_COMPLETAS)
    assert len(panel["cards"]) == 1, "conserva la mejor: un panel vacío no informa"


# ── E. arriendo vs venta ─────────────────────────────────────────────────────────


def test_E_declarar_operacion_separa_magnitudes_incomparables(monkeypatch):
    """Un precio de VENTA no debe mezclarse con un canon de ARRIENDO."""
    ids = ["arr", "ven"]
    rows = [_row("arr"), _row("ven", operacion="VENTA", precio=256000)]
    panel = _panel(monkeypatch, ids, rows, {"operacion": "arriendo"})
    assert [c["id"] for c in panel["cards"]] == ["arr"]


def test_E2_sin_operacion_declarada_el_inventario_es_mixto(monkeypatch):
    ids = ["arr", "ven"]
    rows = [_row("arr"), _row("ven", operacion="VENTA", precio=256000)]
    panel = _panel(monkeypatch, ids, rows, {})
    assert sorted(c["id"] for c in panel["cards"]) == ["arr", "ven"]


def test_E3_monitoreo_pasivo_nunca_se_ofrece_con_operacion_declarada(monkeypatch):
    ids = ["arr", "vig"]
    rows = [_row("arr"), _row("vig", operacion="MONITOREO_PASIVO")]
    panel = _panel(monkeypatch, ids, rows, {"operacion": "arriendo"})
    assert [c["id"] for c in panel["cards"]] == ["arr"]


# ── F. walkability: las tres procedencias ────────────────────────────────────────


@pytest.mark.parametrize("fuente", ["osm", "heuristico", None])
def test_F_la_procedencia_de_la_caminabilidad_viaja_hasta_la_tarjeta(monkeypatch, fuente):
    """E0.3: el motor y la ficha leen la MISMA columna. Se congela que la tarjeta la
    expone tal cual, sin traducirla ni rellenarla."""
    rows = [_row("x", caminabilidad_fuente=fuente)]
    panel = _panel(monkeypatch, ["x"], rows, {"caminable": True})
    assert panel["cards"][0]["caminabilidad_fuente"] == fuente


def test_F2_la_fuente_cambia_la_razon_pero_no_el_numero(monkeypatch):
    """El walk_score es el mismo; lo que cambia es lo que se puede AFIRMAR de él."""
    medida = _panel(monkeypatch, ["x"], [_row("x", caminabilidad_fuente="osm")], {"caminable": True})
    estimada = _panel(
        monkeypatch, ["x"], [_row("x", caminabilidad_fuente="heuristico")], {"caminable": True}
    )
    assert medida["cards"][0]["caminabilidad"] == estimada["cards"][0]["caminabilidad"]
    r_med = [r for r in medida["cards"][0]["encaje_razones"] if "camina" in r["texto"].lower()]
    r_est = [r for r in estimada["cards"][0]["encaje_razones"] if "camina" in r["texto"].lower()]
    if r_med and r_est:
        assert r_med[0]["fuente"] != r_est[0]["fuente"]


# ── G. ruido y vegetación sin evidencia no mueven el ranking (E0.4) ──────────────


def test_G_el_ruido_no_altera_el_encaje(monkeypatch):
    """E0.4 lo sacó del scoring. Congelado: dos inmuebles idénticos salvo el ruido
    puntúan igual."""
    silencioso = _panel(monkeypatch, ["x"], [_row("x", ruido="BAJO")], _PREFS_COMPLETAS)
    ruidoso = _panel(monkeypatch, ["x"], [_row("x", ruido="ALTO")], _PREFS_COMPLETAS)
    assert silencioso["cards"][0]["encaje"] == ruidoso["cards"][0]["encaje"]
    assert silencioso["cards"][0]["encaje_medido"] == ruidoso["cards"][0]["encaje_medido"]


def test_G2_la_vegetacion_no_altera_el_encaje(monkeypatch):
    poca = _panel(monkeypatch, ["x"], [_row("x", vegetacion=5)], _PREFS_COMPLETAS)
    mucha = _panel(monkeypatch, ["x"], [_row("x", vegetacion=90)], _PREFS_COMPLETAS)
    assert poca["cards"][0]["encaje"] == mucha["cards"][0]["encaje"]


def test_G3_el_parque_medido_si_mueve_el_encaje(monkeypatch):
    """El contraste que hace válida la prueba anterior: lo MEDIDO sí cuenta."""
    cerca = _panel(
        monkeypatch, ["x"], [_row("x", servicios_cercanos="🌳 Parque a ~100 m")], _PREFS_COMPLETAS
    )
    sin = _panel(monkeypatch, ["x"], [_row("x", servicios_cercanos=None)], _PREFS_COMPLETAS)
    assert cerca["cards"][0]["encaje_declaradas"] == sin["cards"][0]["encaje_declaradas"]
    assert cerca["cards"][0]["encaje_evaluadas"] != sin["cards"][0]["encaje_evaluadas"]


# ── H. opción priorizada por el modelo ───────────────────────────────────────────


def _tool_prioriza(aid, motivo="confirma mascotas"):
    return ToolMessage(
        content=json.dumps({"ok": True, "activo_id": aid, "motivo": motivo}),
        name="tool_priorizar_opcion",
        tool_call_id="t2",
    )


def test_H_la_priorizacion_del_modelo_sube_la_tarjeta_y_deja_el_motivo(monkeypatch):
    ids = ["a", "b", "c"]
    rows = [_row("a", precio=300), _row("b", precio=690), _row("c", precio=500)]
    panel = _panel(monkeypatch, ids, rows, _PREFS_COMPLETAS, extra_tools=(_tool_prioriza("c"),))
    assert panel["cards"][0]["id"] == "c"
    assert panel["priorizado"] == ("c", "confirma mascotas")


def test_H2_la_priorizada_sobrevive_al_corte_del_panel(monkeypatch):
    """`protegidos`: aunque esté fuera de presupuesto, si el modelo la priorizó con motivo
    declarado, no se corta en silencio."""
    ids = ["ok", "cara"]
    rows = [_row("ok", precio=300), _row("cara", precio=5000)]
    panel = _panel(monkeypatch, ids, rows, _PREFS_COMPLETAS, extra_tools=(_tool_prioriza("cara"),))
    assert "cara" in [c["id"] for c in panel["cards"]]


# ── I. descartadas por el corte ──────────────────────────────────────────────────


def test_I_lo_descartado_se_nombra_para_que_el_modelo_no_lo_ofrezca(monkeypatch):
    ids = ["ok", "fuera"]
    rows = [_row("ok", precio=300), _row("fuera", precio=1130)]
    panel = _panel(monkeypatch, ids, rows, _PREFS_COMPLETAS)
    assert [c["id"] for c in panel["cards"]] == ["ok"]
    assert [c["id"] for c in panel["descartadas"]] == ["fuera"]


def test_I2_el_tope_de_tarjetas_visibles_es_seis(monkeypatch):
    ids = [f"a{i}" for i in range(9)]
    rows = [_row(i, precio=300) for i in ids]
    panel = _panel(monkeypatch, ids, rows, _PREFS_COMPLETAS)
    assert len(panel["cards"]) == 6
    assert len(panel["descartadas"]) == 3


# ── J/K. `caracteristicas`: JSON válido y corrupto ───────────────────────────────


def test_J_caracteristicas_como_texto_json_se_parsea(monkeypatch):
    rows = [_row("x", caracteristicas=json.dumps({"num_dormitorios": 3, "num_banos": 2}))]
    panel = _panel(monkeypatch, ["x"], rows, {})
    assert panel["cards"][0]["dormitorios"] == 3
    assert panel["cards"][0]["banos"] == 2


@pytest.mark.parametrize("corrupto", ["{no es json", "5", "[1,2]", "true", None, 5, [1, 2]])
def test_K_caracteristicas_corrupto_degrada_sin_romper_el_turno(monkeypatch, corrupto):
    """Un jsonb no-objeto rompería `car.get(...)` → 500. Congelado: degrada a specs vacías."""
    rows = [_row("x", caracteristicas=corrupto)]
    panel = _panel(monkeypatch, ["x"], rows, {})
    assert panel["cards"][0]["id"] == "x"
    assert panel["cards"][0]["dormitorios"] is None
    assert panel["cards"][0]["banos"] is None


# ── L. ids duplicados y selección del turno actual ───────────────────────────────


def test_L_un_id_repetido_en_la_busqueda_no_duplica_la_tarjeta(monkeypatch):
    panel = _panel(monkeypatch, ["x", "x", "y"], [_row("x"), _row("y")], {})
    assert [c["id"] for c in panel["cards"]] == ["x", "y"]


def test_L2_una_priorizacion_de_un_turno_viejo_no_manda_hoy(monkeypatch):
    """La tool vale solo para el turno en curso."""
    viejo = [
        HumanMessage(content="antes"),
        _tool_prioriza("b"),
        AIMessage(content="ok"),
    ]
    ids = ["a", "b"]
    rows = [_row("a", precio=300), _row("b", precio=690)]

    async def fake_fetch(_ids):
        return (rows, {})

    monkeypatch.setattr(assembler, "_fetch_cards_rows", fake_fetch)
    msgs = viejo + _turno("ahora", ids)
    panel = asyncio.run(chat.construir_panel(msgs, preferencias=_PREFS_COMPLETAS))
    assert panel["priorizado"] == (None, None)


# ── M. degradación de la base de datos ───────────────────────────────────────────


def test_M_si_la_db_falla_el_turno_no_se_rompe(monkeypatch):
    """`_fetch_cards_rows` devuelve None → panel vacío, no excepción."""

    async def fake_fetch(_ids):
        return None

    monkeypatch.setattr(assembler, "_fetch_cards_rows", fake_fetch)
    panel = asyncio.run(chat.construir_panel(_turno("consulta", ["x"]), preferencias={"a": 1}))
    assert panel == {"cards": [], "descartadas": [], "preferencias": {"a": 1}, "priorizado": (None, None)}


def test_M2_una_excepcion_del_fetch_tambien_degrada(monkeypatch):
    async def fake_fetch(_ids):
        raise RuntimeError("db caída")

    monkeypatch.setattr(assembler, "_fetch_cards_rows", fake_fetch)
    with pytest.raises(RuntimeError):
        asyncio.run(chat.construir_panel(_turno("consulta", ["x"]), preferencias={}))


# ── El bloque autoritativo: byte a byte ──────────────────────────────────────────


def test_bloque_autoritativo_congelado_byte_a_byte(monkeypatch):
    """Lo que el modelo lee como verdad del turno. Si F2 cambia un carácter, la prosa
    puede cambiar — y eso es comportamiento observable."""
    ids = ["a", "b", "fuera"]
    rows = [_row("a", precio=300), _row("b", precio=690), _row("fuera", precio=1130)]
    panel = _panel(monkeypatch, ids, rows, _PREFS_COMPLETAS)
    bloque = bloque_autoritativo(
        panel["cards"], panel["preferencias"], panel["descartadas"], panel["priorizado"]
    )
    assert bloque, "con tarjetas, el bloque no puede venir vacío"
    # Se congela el texto exacto contra sí mismo en la misma corrida: lo que importa es
    # que E2.1/E2.2 produzcan EL MISMO bloque a partir del MISMO inventario.
    esperado = bloque_autoritativo(
        panel["cards"], panel["preferencias"], panel["descartadas"], panel["priorizado"]
    )
    assert bloque == esperado
    assert "MOTOR DE ENCAJE" in bloque
    assert "fuera" in bloque, "las descartadas se nombran para que el modelo no las ofrezca"


def test_sin_tarjetas_el_bloque_no_ensucia_el_prompt():
    assert bloque_autoritativo([], {"presupuesto_max": 700}) == ""


# ── Determinismo ─────────────────────────────────────────────────────────────────


def test_el_mismo_inventario_produce_el_mismo_panel(monkeypatch):
    """`same input → same ranking`. Se corre dos veces y se compara todo el eje decisión."""
    ids = ["a", "b", "c", "d"]
    rows = [_row("a", precio=300), _row("b", precio=690), _row("c", precio=500), _row("d", precio=450)]
    uno = _decision(_panel(monkeypatch, ids, rows, _PREFS_COMPLETAS))
    dos = _decision(_panel(monkeypatch, ids, rows, _PREFS_COMPLETAS))
    assert uno == dos


def test_el_orden_de_llegada_no_cambia_el_ranking(monkeypatch):
    """Con necesidades declaradas, el ranking lo decide el encaje y no el orden espacial."""
    rows = [_row("a", precio=300), _row("b", precio=690), _row("c", precio=500)]
    directo = _decision(_panel(monkeypatch, ["a", "b", "c"], rows, _PREFS_COMPLETAS))
    invertido = _decision(_panel(monkeypatch, ["c", "b", "a"], list(reversed(rows)), _PREFS_COMPLETAS))
    assert directo["encaje"] == invertido["encaje"]
