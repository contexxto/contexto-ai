"""G20-B1-R2 · DISPLAYED-ENTITY EVIDENCE BINDING.

QUÉ DESTAPÓ R1. La normalización de tipos hizo que el canal territorial FUNCIONARA por
primera vez, y al funcionar dejó ver una violación más profunda: la distancia que el bloque
autoritativo atribuye «al candidato mostrado» sale de `assets[0]` del resultado crudo —el más
cercano que devolvió el SQL— y no de la tarjeta que la persona ve. Entre uno y otro hay dos
filtros (operación, tipo), un ranking y un recorte.

EL CASO REAL, sobre el mismo turno del canary, cambiando sólo las preferencias declaradas:

    prefs {operacion: venta}
      visible : b1810dd2 a 716.6 m  ·  7887ff3e a 823.6 m
      oculto  : ee9ff315 a 572 m   (es ARRIENDO: el filtro lo sacó del panel)
      emitido : «el candidato mostrado está a 572 m de ese punto»   ← FALSO

Es la clase de defecto que G20 existe para prevenir: el canal que el sistema trata como
verdad del turno afirmando algo que la evidencia no sostiene. Y es peor que un número
equivocado — es una afirmación sobre una entidad que la persona no puede ver.

    la identidad de la entidad NO es metadato accesorio:
    es parte de la AUTORIDAD de la afirmación

EL INVARIANTE QUE ESTA UNIDAD FIJA:

  1. toda distancia autoritativa va ligada, por IDENTIDAD ESTABLE, a una tarjeta
     efectivamente visible después de filtros y ordenamiento;
  2. prohibido `assets[0]`, índices paralelos o la posición como sustituto de identidad;
  3. una entidad filtrada NO aporta afirmaciones sobre una entidad visible;
  4. sin enlace, o con enlace ambiguo, se OMITE la distancia — y la prohibición territorial
     y `pertenencia_territorial=unknown` permanecen;
  5. con varias tarjetas, ninguna distancia singular puede presentarse como propiedad
     genérica «del candidato mostrado»: cada cifra identifica a su sujeto.

EL IDENTIFICADOR NO SE INVENTA. `id` (uuid) ya es canónico y compartido: el ToolMessage lo
trae por activo, `_collect_asset_ids` lo extrae de ahí, `_fetch_cards_rows` trae las filas
por ese id y `_card_from_row` lo copia a la tarjeta. El bloque autoritativo YA liga por id en
la priorización (`c.get("id") == aid`). R2 usa ese mismo camino.

FUERA DE ALCANCE, por decisión de gatekeeper: `G20-B1-NOCARDS-01` (que la prohibición se
emita con cero tarjetas) y `G20-B1-CONTAINMENT-01` (dónde vive el `try` de `encaje_node`).
Ambas siguen abiertas y NO se tocan aquí.
"""
import asyncio
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.decision import assembler
from app.decision.assembler import _relacion_territorial_del_turno, construir_panel
from app.encaje_contexto import bloque_autoritativo

ARTEFACTO = (Path(__file__).parent / "fixtures"
             / "g20_b1_canary_void_20260830T204022Z.json")

CONSULTA = "La Floresta, Quito, Ecuador"

# Los cinco activos REALES del turno, con su operación y su distancia tal como vienen del cable.
OCULTO_ARRIENDO = "ee9ff315-5947-40bc-be09-632ace6b7991"   # 572.0 m — el MÁS CERCANO
VISIBLE_VENTA_1 = "b1810dd2-3e8c-4bc3-a27d-f80efde43cb7"   # 716.6 m
VISIBLE_VENTA_2 = "7887ff3e-9e5e-4921-b652-f9a61ecee0b2"   # 823.6 m

PREFS_VENTA = {"operacion": "venta"}
PREFS_ARRIENDO = {"operacion": "arriendo", "presupuesto_max": 900}


def _artefacto() -> dict:
    with open(ARTEFACTO, encoding="utf-8") as f:
        return json.load(f)


def _mensajes(mutar_assets=None) -> list:
    """El turno real. `mutar_assets` recibe la lista de activos y puede alterarla."""
    fuera = []
    for m in _artefacto()["messages"]:
        if m["type"] == "human":
            fuera.append(HumanMessage(content=m["content"]))
        elif m["type"] == "ai":
            fuera.append(AIMessage(content=m["content"] or "",
                                   tool_calls=m.get("tool_calls") or []))
        elif m["type"] == "tool":
            contenido = m["content"]
            if mutar_assets and m["name"] == "tool_search_nearby_assets":
                cuerpo = json.loads(contenido)
                cuerpo["assets"] = mutar_assets(cuerpo["assets"])
                contenido = json.dumps(cuerpo, default=str)   # igual que tools.py:303
            fuera.append(ToolMessage(content=contenido, name=m["name"],
                                     tool_call_id=m["tool_call_id"]))
    return fuera


def _assets() -> list[dict]:
    for m in _artefacto()["messages"]:
        if m.get("name") == "tool_search_nearby_assets":
            return json.loads(m["content"])["assets"]
    raise AssertionError("el artefacto perdió el ToolMessage de búsqueda")


def _dir_de(aid: str) -> str:
    return next(a["direccion_estandarizada"] for a in _assets() if a["id"] == aid)


def _rows() -> list[dict]:
    return [{
        "id": a["id"], "direccion": a["direccion_estandarizada"],
        "tipo_activo": a["tipo_activo"], "operacion": a["operacion"],
        "precio": float(a["precio"]), "imagen_url": None,
        "caminabilidad": 90, "caminabilidad_fuente": "osm", "ruido": "BAJO",
        "vegetacion": 40, "lat": -0.2093, "lon": -78.4849,
        "caracteristicas": {"num_dormitorios": 2},
        "servicios_cercanos": "🌳 Parque a ~300 m",
        "conectividad": "🚇 Metro a ~500 m (7 min a pie)",
    } for a in _assets()]


def _panel(monkeypatch, prefs=PREFS_VENTA, mensajes=None):
    async def fake_fetch(_ids):
        return (_rows(), {})

    monkeypatch.setattr(assembler, "_fetch_cards_rows", fake_fetch)
    return asyncio.run(construir_panel(mensajes if mensajes is not None else _mensajes(),
                                       session_id="s-g20b1r2", preferencias=prefs))


def _bloque(monkeypatch, prefs=PREFS_VENTA, mensajes=None):
    """La costura entera, igual que `encaje_node`."""
    p = _panel(monkeypatch, prefs=prefs, mensajes=mensajes)
    return p, bloque_autoritativo(p["cards"], prefs, p["descartadas"], p["priorizado"],
                                  relacion_territorial=p.get("relacion_territorial"))


def _lineas_de_distancia(bloque: str) -> list[str]:
    return [l for l in bloque.splitlines() if " m" in l and "—" in l and l.strip()[0].isdigit()]


# ══ 0 · EL CASO QUE OBLIGA · el más cercano está OCULTO ═════════════════════════════

def test_el_bloque_NO_atribuye_la_distancia_del_activo_oculto(monkeypatch):
    """EL RED DE ESTA UNIDAD.

    `ee9ff315` está a 572 m y es el más cercano, pero es ARRIENDO: con `operacion: venta`
    el filtro lo saca del panel y la persona nunca lo ve. Su distancia no puede describir a
    nadie.
    """
    panel, bloque = _bloque(monkeypatch, prefs=PREFS_VENTA)

    ids_visibles = [c["id"] for c in panel["cards"]]
    assert ids_visibles == [VISIBLE_VENTA_1, VISIBLE_VENTA_2], "cambió el panel del caso base"
    assert OCULTO_ARRIENDO not in ids_visibles

    assert "572 m" not in bloque, "se coló la distancia del activo oculto"
    assert "572" not in bloque
    assert _dir_de(OCULTO_ARRIENDO) not in bloque


def test_la_relacion_solo_liga_ids_visibles(monkeypatch):
    """Invariantes 1 y 3, en la estructura: ids del panel, en su orden, y NADIE más."""
    rel = _panel(monkeypatch, prefs=PREFS_VENTA)["relacion_territorial"]
    assert [d["id"] for d in rel["distancias"]] == [VISIBLE_VENTA_1, VISIBLE_VENTA_2]
    assert [d["distancia_metros"] for d in rel["distancias"]] == [716.6, 823.6]
    assert all(d["id"] != OCULTO_ARRIENDO for d in rel["distancias"])


def test_no_queda_una_distancia_singular_generica(monkeypatch):
    """Invariante 5. La forma vieja —una cifra suelta para «el candidato mostrado»— no puede
    sobrevivir ni como campo ni como frase."""
    panel, bloque = _bloque(monkeypatch, prefs=PREFS_VENTA)
    assert "distancia_metros" not in panel["relacion_territorial"], (
        "sigue existiendo la distancia singular: es la puerta por la que volvería el defecto")
    assert "el candidato mostrado está a" not in bloque


def test_cada_distancia_emitida_nombra_a_su_sujeto(monkeypatch):
    """Invariante 5. Dos tarjetas, dos cifras, cada una pegada a SU inmueble."""
    _, bloque = _bloque(monkeypatch, prefs=PREFS_VENTA)
    lineas = _lineas_de_distancia(bloque)
    assert len(lineas) == 2, f"esperaba una línea por inmueble visible, hay {len(lineas)}"
    assert _dir_de(VISIBLE_VENTA_1) in lineas[0] and "716.6 m" in lineas[0]
    assert _dir_de(VISIBLE_VENTA_2) in lineas[1] and "823.6 m" in lineas[1]


# ══ 1 · COINCIDENCIA ÚNICA VÁLIDA ══════════════════════════════════════════════════

def test_coincidencia_unica_valida(monkeypatch):
    """Con `arriendo` + tope 900 el panel deja UNA tarjeta, que además es la más cercana.
    La cifra correcta debe emitirse — R2 no puede volverse mudo por prudencia."""
    panel, bloque = _bloque(monkeypatch, prefs=PREFS_ARRIENDO)
    assert [c["id"] for c in panel["cards"]] == [OCULTO_ARRIENDO]   # aquí SÍ es visible
    rel = panel["relacion_territorial"]
    assert rel["distancias"] == [{"id": OCULTO_ARRIENDO, "distancia_metros": 572.0}]
    assert "572 m" in bloque
    assert _dir_de(OCULTO_ARRIENDO) in bloque


# ══ 2 · REORDENAMIENTO · la cifra sigue a la IDENTIDAD, no a la posición ═══════════

def test_si_el_ranking_reordena_las_distancias_lo_siguen(monkeypatch):
    """Invariante 2. Se invierte el ranking: si algo uniera por índice, las cifras se
    quedarían donde estaban y cada inmueble heredaría la distancia del otro."""
    from app.contracts.common_v0 import RankingEntryV0
    from app.decision.context import PROVIDER_ID_LOCAL

    def ranking_invertido(cards, *, prioritario=None, score_version=None):
        al_reves = sorted(cards, key=lambda c: c["id"], reverse=True)
        return tuple(RankingEntryV0(provider_id=PROVIDER_ID_LOCAL, property_id=c["id"], rank=i)
                     for i, c in enumerate(al_reves, 1))

    monkeypatch.setattr(assembler, "decidir_ranking", ranking_invertido)
    panel, bloque = _bloque(monkeypatch, prefs=PREFS_VENTA)

    orden = [c["id"] for c in panel["cards"]]
    assert orden == [VISIBLE_VENTA_1, VISIBLE_VENTA_2][::-1] or orden == [VISIBLE_VENTA_1,
                                                                          VISIBLE_VENTA_2]
    # sea cual sea el orden, cada id conserva SU distancia
    esperado = {VISIBLE_VENTA_1: 716.6, VISIBLE_VENTA_2: 823.6}
    for d in panel["relacion_territorial"]["distancias"]:
        assert d["distancia_metros"] == esperado[d["id"]]
    # y el texto va en el orden del panel
    assert [d["id"] for d in panel["relacion_territorial"]["distancias"]] == orden


# ══ 3 · SIN ENLACE / ENLACE AMBIGUO · se OMITE la cifra ════════════════════════════

def test_binding_directo_ausencias_y_ambiguedad():
    """CONTROLES DIRECTOS del ligado.

    Van al ras de `_distancias_ligadas` a propósito. Quitarle el `id` a un activo NO es
    alcanzable de punta a punta —`_collect_asset_ids` deja de recolectarlo y la tarjeta ni
    siquiera entra al panel—, así que probarlo por el camino largo sería teatro: pasaría por
    una razón distinta de la que se quiere fijar. Estas son ramas defensivas y se prueban
    donde viven.
    """
    from app.decision.assembler import _distancias_ligadas

    a1 = {"id": "A", "distancia_metros": "100.0"}
    a2 = {"id": "B", "distancia_metros": "200.0"}
    c = lambda i: {"id": i}

    # tarjeta cuyo id NO aparece entre los activos → sin ligadura
    assert _distancias_ligadas([a1], [c("Z")]) == [{"id": "Z", "distancia_metros": None}]
    # tarjeta sin id → no es ligable, y no se le inventa una identidad
    assert _distancias_ligadas([a1], [{}]) == [{"id": None, "distancia_metros": None}]
    # activo sin id → no puede ligar a nadie
    assert _distancias_ligadas([{"distancia_metros": "100.0"}], [c("A")]) == \
        [{"id": "A", "distancia_metros": None}]
    # id duplicado → ambiguo → se omite, y NO contamina a la otra tarjeta
    dup = [a1, {"id": "A", "distancia_metros": "999.9"}, a2]
    assert _distancias_ligadas(dup, [c("A"), c("B")]) == [
        {"id": "A", "distancia_metros": None}, {"id": "B", "distancia_metros": 200.0}]
    # basura estructural: no revienta y no liga
    assert _distancias_ligadas([None, "x", a2], [c("B")]) == \
        [{"id": "B", "distancia_metros": 200.0}]
    # sin tarjetas visibles no hay distancias que emitir (NOCARDS-01 sigue fuera de alcance)
    assert _distancias_ligadas([a1, a2], []) == []
    # un activo que no corresponde a ninguna tarjeta se descarta ENTERO
    assert _distancias_ligadas([a1, a2], [c("B")]) == \
        [{"id": "B", "distancia_metros": 200.0}]


def test_activo_sin_distancia_lo_dice_en_el_bloque(monkeypatch):
    """Invariante 4, de punta a punta y por la vía que SÍ ocurre: la tarjeta es visible y
    ligable, pero su activo no trae distancia. Se omite esa cifra, se dice que falta, y la
    del otro inmueble no se contamina."""
    def sin_distancia(assets):
        for a in assets:
            if a["id"] == VISIBLE_VENTA_1:
                a.pop("distancia_metros")
        return assets

    panel, bloque = _bloque(monkeypatch, prefs=PREFS_VENTA, mensajes=_mensajes(sin_distancia))
    dist = {d["id"]: d["distancia_metros"] for d in panel["relacion_territorial"]["distancias"]}
    assert dist.get(VISIBLE_VENTA_1) is None
    assert dist.get(VISIBLE_VENTA_2) == 823.6
    assert "716.6 m" not in bloque
    assert "823.6 m" in bloque
    assert "SIN DISTANCIA LIGADA" in bloque
    assert _dir_de(VISIBLE_VENTA_1) in bloque   # se nombra, aunque sin cifra


def test_identificador_duplicado_es_enlace_ambiguo(monkeypatch):
    """Invariante 4. Dos activos con el MISMO id y distancias distintas: no hay forma de
    saber cuál describe a la tarjeta. Elegir una sería inventar la correspondencia."""
    def duplicar(assets):
        clon = dict(assets[0])
        clon["id"] = VISIBLE_VENTA_1
        clon["distancia_metros"] = "999.9"
        return assets + [clon]

    panel, bloque = _bloque(monkeypatch, prefs=PREFS_VENTA, mensajes=_mensajes(duplicar))
    dist = {d["id"]: d["distancia_metros"] for d in panel["relacion_territorial"]["distancias"]}
    assert dist.get(VISIBLE_VENTA_1) is None, "eligió una de dos distancias ambiguas"
    assert "999.9" not in bloque
    assert "716.6 m" not in bloque
    assert dist.get(VISIBLE_VENTA_2) == 823.6, "la ambigüedad de una no puede tumbar a la otra"


# ══ 4 · LA PROHIBICIÓN NO DEPENDE DE LA CIFRA ══════════════════════════════════════

def test_sin_ninguna_distancia_ligada_la_prohibicion_permanece(monkeypatch):
    """Invariante 4, su mitad importante. Se ensucian TODAS las distancias: el bloque pierde
    las cifras y NO pierde la restricción. Si esto se cayera, bastaría un payload sucio para
    dejar al modelo sin gobierno territorial — el mismo fail-open que el gatekeeper vetó en
    CONTAINMENT-01, entrando por la puerta de los datos."""
    def basura(assets):
        for a in assets:
            a["distancia_metros"] = "no-es-un-numero"
        return assets

    panel, bloque = _bloque(monkeypatch, prefs=PREFS_VENTA, mensajes=_mensajes(basura))
    rel = panel["relacion_territorial"]
    assert [d["id"] for d in rel["distancias"]] == [VISIBLE_VENTA_1, VISIBLE_VENTA_2]
    assert "NINGUNA distancia quedó ligada" in bloque

    assert all(d["distancia_metros"] is None for d in rel["distancias"])
    assert rel["pertenencia_territorial"] == "unknown"
    assert "RELACIÓN TERRITORIAL · QUÉ PUEDES AFIRMAR" in bloque
    assert "pertenencia territorial: NO ESTÁ ESTABLECIDA" in bloque
    assert f"que el inmueble esté «en {CONSULTA}»" in bloque
    assert "no digas que está fuera ni que no pertenece" in bloque


# ══ 5 · LO QUE R2 NO PUEDE ROMPER (G20-B1 y R1) ════════════════════════════════════

def test_se_conserva_current_turn_only():
    """El guard de G20-B1: la relación sale SÓLO del turno actual."""
    previos = _mensajes()
    actuales = [HumanMessage(content="¿y cuántos dormitorios tiene?"),
                AIMessage(content="Tiene 2.")]
    assert _relacion_territorial_del_turno(previos + actuales) is None


def test_se_conserva_el_label_binding(monkeypatch):
    """El otro guard de G20-B1: sin igualdad EXACTA de coordenadas, el lugar NO se nombra."""
    msgs = _mensajes()
    for i, m in enumerate(msgs):
        if getattr(m, "name", None) == "tool_geocode_address":
            g = json.loads(m.content)
            g["latitude"] = -0.5   # ya no coincide con el ancla de la búsqueda
            msgs[i] = ToolMessage(content=json.dumps(g), name=m.name,
                                  tool_call_id=m.tool_call_id)
    panel, bloque = _bloque(monkeypatch, prefs=PREFS_VENTA, mensajes=msgs)
    assert panel["relacion_territorial"]["consulta"] is None
    assert CONSULTA not in bloque
    assert "el punto de búsqueda NO corresponde a ningún lugar nombrado" in bloque
    # y las distancias, que no dependen del topónimo, siguen ligadas
    distancias = [d["distancia_metros"] for d in panel["relacion_territorial"]["distancias"]]
    assert distancias == [716.6, 823.6]


def test_se_conserva_la_normalizacion_de_tipos_de_R1(monkeypatch):
    """R1 no se pierde: en el cable son str y salen float."""
    assert all(isinstance(a["distancia_metros"], str) for a in _assets())
    rel = _panel(monkeypatch, prefs=PREFS_VENTA)["relacion_territorial"]
    assert all(isinstance(d["distancia_metros"], float) for d in rel["distancias"])


@pytest.mark.parametrize("basura", ["abc", "NaN", float("inf"), -1, True, None])
def test_R1_sigue_rechazando_lo_que_no_es_distancia(monkeypatch, basura):
    def ensuciar(assets):
        for a in assets:
            if a["id"] == VISIBLE_VENTA_1:
                a["distancia_metros"] = basura
        return assets

    panel, _ = _bloque(monkeypatch, prefs=PREFS_VENTA, mensajes=_mensajes(ensuciar))
    dist = {d["id"]: d["distancia_metros"] for d in panel["relacion_territorial"]["distancias"]}
    assert dist.get(VISIBLE_VENTA_1) is None
    assert dist.get(VISIBLE_VENTA_2) == 823.6
