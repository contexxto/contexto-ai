"""
Los 4 fallos reproducidos en contexxto.com el 2026-07-30
(docs/BATALLA_Hiinmo_vs_Contexto_2026-07-30.md), cada uno con su repro literal.

Diagnóstico transversal del informe: en 3 corridas de la MISMA consulta el panel devolvió
scores idénticos (el motor es determinístico) mientras la prosa cambió cada vez y nunca
coincidió con el ranking. La causa no era el modelo: era que el modelo NUNCA VEÍA lo que el
motor calculó — el encaje se computaba DESPUÉS de que la respuesta ya estaba escrita.

Por eso estos tests atacan la frontera motor↔prosa en las dos direcciones:
  · que el motor no produzca números mentirosos (fallos 2 y 4, en app/encaje.py);
  · que el panel no muestre lo que no es una opción (fallo 3, en chat._recortar_grid);
  · que lo que el motor calculó LLEGUE al modelo antes de escribir (fallos 1 y 4,
    en app/encaje_contexto.py + el nodo `encaje` del grafo).

Consultas de reproducción del informe:
  A (arriendo) "…departamento en Quito… perro… no tengo carro… Presupuesto 700 dólares al mes."
  B (venta)    "Departamento de 2 dormitorios en venta en Cumbayá hasta 150000 dólares"
"""
import asyncio
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent import graph as agent_graph
from app.agent.tools import tool_priorizar_opcion
from app.encaje import calcular_encaje, estado_presupuesto
from app.encaje_contexto import bloque_autoritativo
from app.routers import chat


# ── Utilidades: un turno real (Human → Tool(search) → AI) contra filas de catastro ──
def _row(rid, **over):
    row = {
        "id": rid, "direccion": f"Dir {rid}", "tipo_activo": "Departamento",
        "operacion": "ARRIENDO", "precio": 380, "imagen_url": None,
        "caminabilidad": 95, "ruido": "BAJO", "vegetacion": 42,
        "lat": -0.18, "lon": -78.48,
        "caracteristicas": {"num_dormitorios": 2, "acepta_mascotas": True},
        "servicios_cercanos": "🌳 Parque a ~300 m",
        "conectividad": "🚇 Metro a ~500 m (7 min a pie)",
    }
    row.update(over)
    return row


def _turno(texto, ids, extra_tools=()):
    msgs = [HumanMessage(content=texto),
            ToolMessage(content=json.dumps({"assets": [{"id": i} for i in ids]}),
                        name="tool_search_nearby_assets", tool_call_id="t1")]
    msgs.extend(extra_tools)
    msgs.append(AIMessage(content="Encontré algunas opciones."))
    return msgs


def _panel(monkeypatch, ids, rows, prefs):
    async def fake_fetch(_ids):
        return (rows, {})
    monkeypatch.setattr(chat, "_fetch_cards_rows", fake_fetch)
    return asyncio.run(chat.construir_panel(_turno("consulta", ids), preferencias=prefs))


# Las prefs de la consulta A tal como las declara el usuario del informe.
_PREFS_A = {"operacion": "arriendo", "tipo_inmueble": "departamento", "presupuesto_max": 700,
            "tranquilidad": True, "caminable": True, "area_verde": True, "acepta_mascotas": True}

# El inventario de la corrida A (los mismos precios del informe).
_INVENTARIO_A = [
    _row("d380", precio=380), _row("d290", precio=290), _row("d550", precio=550),
    _row("d710", precio=710), _row("d990", precio=990), _row("d1130", precio=1130),
]


# ══ FALLO 4 — "encajan con tu presupuesto de $700" incluyendo un $710 ═══════════════
# El más peligroso: una afirmación FALSA sobre dinero, en un producto cuyo argumento es el
# rigor. El motor sí lo sabía (le daba 80%, no 100%); la prosa lo escribía mal.

def test_fallo4_el_motor_dice_el_exceso_en_dolares_no_solo_los_dos_precios():
    r = calcular_encaje({"presupuesto_max": 700}, {"precio": 710})
    texto = r["razones"][0]["texto"]
    assert "Sobre tu tope por $10" in texto, texto
    assert r["score"] != 100


def test_fallo4_estado_presupuesto_es_la_fuente_unica_de_esa_resta():
    dentro = estado_presupuesto(700, 380)
    assert dentro["dentro"] is True and dentro["exceso"] == 0
    sobre = estado_presupuesto(700, 710)
    assert sobre["dentro"] is False and sobre["exceso"] == 10
    assert sobre["etiqueta"] == "sobre tu tope por $10"
    # Sin tope o sin precio no se inventa un veredicto.
    assert estado_presupuesto(None, 710) is None and estado_presupuesto(700, None) is None


def test_fallo4_el_bloque_le_marca_al_modelo_dentro_y_sobre(monkeypatch):
    panel = _panel(monkeypatch, [c["id"] for c in _INVENTARIO_A], _INVENTARIO_A, _PREFS_A)
    bloque = bloque_autoritativo(panel["cards"], _PREFS_A, panel["descartadas"])

    assert "TOPE DE PRESUPUESTO: $700 al mes" in bloque
    # La línea del $710 lleva el veredicto en mayúsculas, imposible de leer como "entra", y
    # la frase obligatoria PEGADA al dato (la prohibición general del prompt se respetaba en la
    # lista y se rompía tres párrafos después: "$710, justo en tu tope").
    linea710 = [ln for ln in bloque.splitlines() if "$710" in ln][0]
    assert "SOBRE TU TOPE POR $10" in linea710, linea710
    assert "se pasa $10 de tu tope" in linea710
    assert "justo en tu tope" in linea710 and "PROHIBIDO" in linea710
    # Y las que sí entran vienen marcadas DENTRO.
    assert "DENTRO de tu tope" in [ln for ln in bloque.splitlines() if "$380" in ln][0]
    # La instrucción explícita viaja con el dato, no solo en el prompt estático.
    assert "nunca lleva ✅" in bloque
    # Y el ENCABEZADO viene contado por el motor: la frase que la persona lee primero es la
    # que en vivo salía falsa ("4 departamentos que encajan con tu presupuesto de $700", con
    # uno de $710), incluso cuando cada ítem estaba bien marcado más abajo.
    assert "CONTEO PARA TU ENCABEZADO — son 4 opciones: 3 dentro de tu tope de $700 y 1 que se pasa." in bloque
    assert "PROHIBIDO abrir con «4 opciones que encajan con tu presupuesto de $700»" in bloque


def test_fallo4_el_conteo_se_adapta_a_cada_caso(monkeypatch):
    from app.encaje_contexto import _conteo_presupuesto

    def card(precio):
        return {"precio": precio}
    # Todas dentro → se puede afirmar que entran.
    assert "las 2 entran en tu tope de $700" in " ".join(
        _conteo_presupuesto([card(300), card(400)], 700))
    # Ninguna dentro → se dice de frente, antes de mostrarlas.
    assert "NINGUNA entra en tu tope" in " ".join(_conteo_presupuesto([card(900)], 700))
    # Sin precio publicado no se afirma nada sobre el presupuesto.
    assert _conteo_presupuesto([card(None)], 700) == []


# ══ FALLO 2 — 100% de encaje a algo que incumple las dos condiciones pedidas ════════
# Repro: "departamento de 2 dormitorios" → tarjeta ganadora = casa de 3 pisos, 4 dormitorios,
# "100% encaje contigo", "Cumple tus 2+ dormitorios (4)". Nadie pidió "2+".

_PREFS_B = {"operacion": "venta", "tipo_inmueble": "departamento", "dormitorios": 2,
            "presupuesto_max": 150000}


def test_fallo2_la_casa_de_4_dormitorios_ya_no_puede_dar_100():
    casa = _row("casa", tipo_activo="Casa", operacion="VENTA", precio=135400,
                caracteristicas={"num_dormitorios": 4})
    r = calcular_encaje(_PREFS_B, chat._senales_encaje(casa, casa["caracteristicas"]))
    assert r["score"] <= 49, f"la casa sigue puntuando {r['score']}%"
    textos = " | ".join(x["texto"] for x in r["razones"])
    assert "2+" not in textos, f"el motor sigue expandiendo el pedido a '2 o más': {textos}"


def test_fallo2_el_tipo_pedido_filtra_el_panel(monkeypatch):
    rows = [_row("casa1", tipo_activo="Casa", operacion="VENTA", precio=135400),
            _row("depto1", operacion="VENTA", precio=140000),
            _row("quinta1", tipo_activo="Quinta", operacion="VENTA", precio=149000)]
    panel = _panel(monkeypatch, ["casa1", "depto1", "quinta1"], rows, _PREFS_B)
    assert [c["id"] for c in panel["cards"]] == ["depto1"]


def test_fallo2_sin_departamentos_degrada_pero_no_corona_a_la_casa(monkeypatch):
    # El caso real de Cumbayá: el inventario es de casas y quintas. No vaciamos el panel
    # (mostrar qué SÍ existe informa), pero lo que se muestra lleva su número honesto.
    rows = [_row("casa1", tipo_activo="Casa", operacion="VENTA", precio=135400,
                 caracteristicas={"num_dormitorios": 4}),
            _row("quinta1", tipo_activo="Quinta", operacion="VENTA", precio=149000,
                 caracteristicas={"num_dormitorios": 3})]
    panel = _panel(monkeypatch, ["casa1", "quinta1"], rows, _PREFS_B)
    assert panel["cards"], "no debe vaciar el turno"
    for c in panel["cards"]:
        assert c["encaje"] <= 49, f"{c['id']} muestra {c['encaje']}% sin ser un departamento"
        assert c["duros_incumplidos"] == ["tipo_inmueble"]
    # Y el bloque se lo dice al modelo con todas las letras.
    bloque = bloque_autoritativo(panel["cards"], _PREFS_B, panel["descartadas"])
    assert "NO ES EL TIPO QUE PIDIÓ" in bloque


# ══ FALLO 3 — el presupuesto no filtraba el panel ══════════════════════════════════
# Con techo de $700 el panel mostró $990 (40%) y $1.130 (37%).

def test_fallo3_el_panel_corta_lo_que_no_es_una_opcion(monkeypatch):
    panel = _panel(monkeypatch, [c["id"] for c in _INVENTARIO_A], _INVENTARIO_A, _PREFS_A)
    visibles = [c["id"] for c in panel["cards"]]
    assert "d990" not in visibles and "d1130" not in visibles, visibles
    # El "casi entra" SÍ se conserva (el informe lo pide explícitamente), bien etiquetado.
    assert "d710" in visibles
    assert any("Sobre tu tope por $10" in r["texto"]
               for c in panel["cards"] if c["id"] == "d710" for r in c["encaje_razones"])
    # Lo cortado no se pierde: viaja como 'descartadas' para que el modelo NO lo ofrezca.
    assert {c["id"] for c in panel["descartadas"]} == {"d990", "d1130"}


def test_fallo3_el_corte_nunca_vacia_el_panel(monkeypatch):
    # Si TODO está fuera de presupuesto, mostrar cero tarjetas no informa: se conserva la
    # mejor, con su número honesto, y el modelo la ve marcada SOBRE.
    rows = [_row("caro1", precio=2000), _row("caro2", precio=3000)]
    panel = _panel(monkeypatch, ["caro1", "caro2"], rows, _PREFS_A)
    assert len(panel["cards"]) == 1 and panel["cards"][0]["id"] == "caro1"


def test_fallo3_sin_preferencias_no_se_corta_nada(monkeypatch):
    # "No sé" no es "no sirve": sin necesidades declaradas el encaje es None en todas y el
    # panel se preserva tal cual (exploración de zona).
    rows = [_row("A", precio=990), _row("B", precio=1130)]
    panel = _panel(monkeypatch, ["A", "B"], rows, {})
    assert [c["id"] for c in panel["cards"]] == ["A", "B"]


# ══ FALLO 1 — la prosa contradecía al propio motor ═════════════════════════════════
# Repro A-3: "Te los ordeno por encaje" y entregó el orden EXACTAMENTE invertido, además de
# omitir el 92% (su propia mejor opción) de una lista que decía tener 3 elementos.

def test_fallo1_el_modelo_recibe_el_ranking_como_contexto_del_turno(monkeypatch):
    panel = _panel(monkeypatch, [c["id"] for c in _INVENTARIO_A], _INVENTARIO_A, _PREFS_A)
    bloque = bloque_autoritativo(panel["cards"], _PREFS_A, panel["descartadas"])

    assert "CONTEXTO AUTORITATIVO" in bloque
    # El orden del bloque es EXACTAMENTE el de las tarjetas, numerado, y de mayor a menor.
    numeradas = [ln for ln in bloque.splitlines() if ln.strip()[:2] in
                 (f"{i}." for i in range(1, 10))]
    assert len(numeradas) == len(panel["cards"])
    for i, c in enumerate(panel["cards"]):
        assert numeradas[i].strip().startswith(f"{i + 1}.")
        assert c["direccion"] in numeradas[i]
    encajes = [c["encaje"] for c in panel["cards"]]
    assert encajes == sorted(encajes, reverse=True)
    # Y el conteo que el modelo debe respetar está escrito.
    assert f"EN EL PANEL — {len(panel['cards'])} opciones" in bloque


def test_fallo1_el_bloque_nombra_lo_descartado_para_que_no_lo_ofrezca(monkeypatch):
    """Lo descartado se le NOMBRA al modelo (para que no lo invente ni lo niegue) pero marcado
    como lo que no es: opciones. En la repro en vivo, con el rótulo anterior el modelo listó
    un $1.130 descartado como "opción 5" de una lista de 4 tarjetas — la misma incoherencia
    prosa↔panel del fallo 1, al revés."""
    panel = _panel(monkeypatch, [c["id"] for c in _INVENTARIO_A], _INVENTARIO_A, _PREFS_A)
    bloque = bloque_autoritativo(panel["cards"], _PREFS_A, panel["descartadas"])
    assert f"NO SON OPCIONES ({len(panel['descartadas'])})" in bloque
    assert "PROHIBIDO listarlas, numerarlas" in bloque
    assert "EN UNA FRASE" in bloque
    # El conteo que el modelo debe usar es el del panel, escrito explícitamente.
    assert f"tu conteo es el del panel ({len(panel['cards'])})" in bloque
    # Los datos siguen ahí: el modelo puede responder si le preguntan directo, sin inventar.
    for c in panel["descartadas"]:
        assert c["direccion"] in bloque


def test_fallo1_el_bloque_prohibe_renumerar_la_lista(monkeypatch):
    # En vivo el modelo reordenó las mismas 4 opciones "de menor a mayor precio": honesto en el
    # criterio, pero la prosa deja de calzar con el panel. La numeración es la del panel.
    panel = _panel(monkeypatch, [c["id"] for c in _INVENTARIO_A], _INVENTARIO_A, _PREFS_A)
    bloque = bloque_autoritativo(panel["cards"], _PREFS_A, panel["descartadas"])
    assert "mismos inmuebles, misma posición, mismo total" in bloque
    assert "Reordenar o renumerar la lista por precio" in bloque
    # La secuencia va escrita de corrido: una sola línea con el orden literal es mucho más
    # difícil de pasar por alto que la regla en prosa (que el modelo respetaba a medias).
    secuencia = [ln for ln in bloque.splitlines() if ln.startswith("ORDEN OBLIGATORIO")][0]
    for i, c in enumerate(panel["cards"], 1):
        assert f"{i}) {c['direccion']}" in secuencia


def test_fallo1_sin_tarjetas_no_hay_bloque():
    # Sin inventario que puntuar, nada que inyectar: el prompt no se ensucia y el modelo no
    # recibe un ranking vacío que podría intentar rellenar.
    assert bloque_autoritativo([], {"presupuesto_max": 700}) == ""


# ── Reordenar SÍ, en silencio NO ────────────────────────────────────────────────────
# El informe hace la nota justa: en A-1 el razonamiento del modelo era BUENO (priorizó el
# único que confirmaba mascotas). El error no era reordenar, era reordenar en silencio.

def test_priorizar_exige_motivo():
    sin = json.loads(asyncio.run(tool_priorizar_opcion.ainvoke({"activo_id": "d550", "motivo": ""})))
    assert sin["ok"] is False
    con = json.loads(asyncio.run(tool_priorizar_opcion.ainvoke(
        {"activo_id": "d550", "motivo": "es el único que confirma que acepta mascotas"})))
    assert con["ok"] is True and con["activo_id"] == "d550"


def test_priorizar_mueve_el_panel_y_queda_declarado_en_el_bloque(monkeypatch):
    rows = _INVENTARIO_A
    priorizacion = ToolMessage(
        content=json.dumps({"ok": True, "activo_id": "d550",
                            "motivo": "es el único que confirma que acepta mascotas"}),
        name="tool_priorizar_opcion", tool_call_id="t2")

    async def fake_fetch(_ids):
        return (rows, {})
    monkeypatch.setattr(chat, "_fetch_cards_rows", fake_fetch)
    msgs = _turno("consulta", [c["id"] for c in rows], extra_tools=[priorizacion])
    panel = asyncio.run(chat.construir_panel(msgs, preferencias=_PREFS_A))

    assert panel["cards"][0]["id"] == "d550", "el panel debe moverse con el modelo"
    assert panel["priorizado"][0] == "d550"
    bloque = bloque_autoritativo(panel["cards"], _PREFS_A, panel["descartadas"],
                                 panel["priorizado"])
    assert "PRIORIZACIÓN TUYA YA APLICADA" in bloque
    assert "acepta mascotas" in bloque
    # El resto del orden del motor se conserva bajo el elegido (no se baraja todo).
    resto = [c["encaje"] for c in panel["cards"][1:]]
    assert resto == sorted(resto, reverse=True)


def test_priorizacion_de_un_turno_viejo_no_manda_hoy(monkeypatch):
    # Una priorización es del turno en que se declaró. Si mandara siempre, el panel de los
    # turnos siguientes quedaría anclado a un motivo que ya nadie leyó.
    vieja = ToolMessage(content=json.dumps({"ok": True, "activo_id": "d550", "motivo": "x y z"}),
                        name="tool_priorizar_opcion", tool_call_id="t0")
    msgs = ([HumanMessage(content="turno 1"), vieja, AIMessage(content="ok")]
            + _turno("turno 2", [c["id"] for c in _INVENTARIO_A]))

    async def fake_fetch(_ids):
        return (_INVENTARIO_A, {})
    monkeypatch.setattr(chat, "_fetch_cards_rows", fake_fetch)
    panel = asyncio.run(chat.construir_panel(msgs, preferencias=_PREFS_A))
    assert panel["priorizado"] == (None, None)
    assert panel["cards"][0]["id"] != "d550", "el panel volvió al orden del motor"


# ── El cableado: el ranking se calcula ANTES de la prosa ────────────────────────────
def test_el_grafo_puntua_entre_las_herramientas_y_la_respuesta():
    """La topología ES el arreglo de raíz: tools → encaje → llm. Antes era tools → llm y el
    encaje se calculaba después de responder, así que el modelo escribía a ciegas."""
    b = agent_graph._graph_builder
    assert "encaje" in b.nodes
    assert ("tools", "encaje") in b.edges and ("encaje", "llm") in b.edges
    assert ("tools", "llm") not in b.edges, "la prosa no puede saltarse el motor"


def test_el_turno_actual_manda_sobre_el_historial(monkeypatch):
    """El panel habla de la búsqueda de AHORA. Antes el barrido empezaba por el mensaje más
    viejo del hilo y se llenaba con los inmuebles del primer turno."""
    viejos = _turno("turno 1", ["d990", "d1130"])
    nuevos = _turno("turno 2", ["d290", "d380"])
    assert chat._collect_asset_ids(viejos + nuevos) == ["d290", "d380"]
    # Pero un seguimiento sin búsqueda nueva ("muéstrame las fichas") no vacía el panel.
    seguimiento = viejos + [HumanMessage(content="muéstrame las fichas"), AIMessage(content="ok")]
    assert chat._collect_asset_ids(seguimiento) == ["d990", "d1130"]
