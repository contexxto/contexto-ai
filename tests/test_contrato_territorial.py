"""G20-B1 · el bloque autoritativo dice qué AFIRMACIÓN autoriza la evidencia.

LA PREGUNTA QUE ESTA UNIDAD RESUELVE:

    G20-A demostró que decirle al modelo QUÉ SABEMOS no basta.
    G20-B1 comprueba si decirle, por el canal autoritativo, QUÉ PUEDE AFIRMAR sí basta.

EVIDENCIA QUE OBLIGA A INTENTARLO POR ESTE CANAL Y NO POR OTRO. En el canary limpio de
G20-A (2026-08-30T19:05:11Z, hilo sin un solo mensaje previo) el modelo recibió, en el
resultado de tool y legible por máquina:

    relacion_recuperacion   within_radius
    pertenencia_territorial unknown
    ancla_busqueda          punto (-0.20934, -78.484919)
    distancia_metros        572.0

y escribió «Encontré 1 departamento en arriendo EN LA FLORESTA». No fue falta de contexto:
fue contradicción de estado explícito. En cambio `encaje_contexto` —el bloque autoritativo—
dicta frases obligatorias para PRESUPUESTO y no se violó ni una vez en los 13 turnos del
corpus. Ese canal tiene historial de obediencia; el resultado de tool no lo tenía.

    evidence  ≠  claim authorization

LA REGLA DURA DE ESTA UNIDAD: la relación territorial se deriva EXCLUSIVAMENTE de los
ToolMessages del TURNO ACTUAL. Sin fallback al historial. `_collect_asset_ids` sí cae al
hilo completo (`or _ids_en(messages, limit)`) y para ids eso es compatibilidad histórica
razonable; para AUTORIDAD territorial sería gobernar la respuesta de hoy con la búsqueda de
ayer. Es el guard más importante de G20-B1 y por eso es M1.

EL LABEL. `tool_search_nearby_assets` recibe tres floats y NO conoce la consulta. El
topónimo vive sólo en el ToolMessage de `tool_geocode_address` del mismo turno
(`address_input` / `address_resolved`). Se correlacionan por COORDENADA: en producción el
`ancla_busqueda` coincide exacto con el punto geocodificado. Si no coinciden, el lugar NO
se nombra — se describe como «el punto usado para la búsqueda». Nunca se reconstruye desde
direcciones ni desde turnos viejos.

FUERA DE ALCANCE, deliberadamente: el borde sin cards (`G20-B1-NOCARDS-01`, KNOWN/DEFERRED
— `bloque_autoritativo` sigue devolviendo "" sin tarjetas), G20-C (scope leakage), G20-D
(comparativos, POLICY-BLOCKED) y G20-M (anotación en el panel, contaminaría el experimento).
"""
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.decision.assembler import _relacion_territorial_del_turno
from app.encaje_contexto import bloque_autoritativo

# El turno REAL del canary de producción, congelado.
ANCLA = {"latitude": -0.20934, "longitude": -78.484919, "geometry_type": "point"}
DIST = 572.0
DIRECCION = "Calle Alemania E12-34 y Gonzalez Suarez, Quito"
CONSULTA = "La Floresta, Quito, Ecuador"
RESUELTO = "La Floresta, Mariscal Sucre, Distrito Metropolitano de Quito, Pichincha, Ecuador"


def _geocode(lat=ANCLA["latitude"], lon=ANCLA["longitude"], consulta=CONSULTA):
    return ToolMessage(
        name="tool_geocode_address", tool_call_id="tc-geo",
        content=json.dumps({"found": True, "address_input": consulta,
                            "address_resolved": RESUELTO, "latitude": lat, "longitude": lon,
                            "geometry_type": "point", "source": "nominatim"}))


def _search(ancla=ANCLA, dist=DIST, pedido=1200, usado=1200):
    cuerpo = {"assets": [{"id": "ee9ff315", "direccion_estandarizada": DIRECCION,
                          "caminabilidad": 100, "walk_score_fuente": None,
                          "distancia_metros": dist}],
              "total": 1, "pertenencia_territorial": "unknown",
              "radius_requested_m": pedido, "radius_searched_m": usado}
    if ancla is not None:
        cuerpo["ancla_busqueda"] = ancla
        cuerpo["relacion_recuperacion"] = "within_radius"
    return ToolMessage(name="tool_search_nearby_assets", tool_call_id="tc-search",
                       content=json.dumps(cuerpo))


def _turno(*tools, texto="Busco arriendo en La Floresta"):
    """Un turno: HumanMessage + la AIMessage que llama + los ToolMessage."""
    return [HumanMessage(content=texto), AIMessage(content="", tool_calls=[]), *tools]


def _cards():
    return [{"id": "ee9ff315", "direccion": DIRECCION, "precio": 630.0,
             "operacion": "ARRIENDO", "encaje": 100, "encaje_razones": []}]


# ══ 1 · PANEL · la relación se deriva del turno actual ═══════════════════════════════
def test_el_turno_actual_produce_relacion_territorial():
    r = _relacion_territorial_del_turno(_turno(_geocode(), _search()))
    assert r is not None
    assert r["relacion_recuperacion"] == "within_radius"
    assert r["pertenencia_territorial"] == "unknown"
    assert r["ancla_busqueda"]["geometry_type"] == "point"
    assert r["distancia_metros"] == DIST
    assert r["radius_requested_m"] == 1200
    assert r["radius_searched_m"] == 1200


def test_sin_tool_de_busqueda_no_hay_relacion():
    """No se fabrica: sin la tool que la produce, no hay relación que declarar."""
    assert _relacion_territorial_del_turno(_turno(_geocode())) is None


def test_la_pertenencia_nunca_se_vuelve_booleana():
    r = _relacion_territorial_del_turno(_turno(_geocode(), _search()))
    assert r["pertenencia_territorial"] == "unknown"
    assert r["pertenencia_territorial"] not in (True, False, "true", "false", "inside")


# ══ 2 · AUTORIDAD TEMPORAL · nunca heredar ══════════════════════════════════════════
def test_dos_turnos_manda_el_ULTIMO():
    """Turno N-1 con ancla A, turno N con ancla B: el panel de N debe traer B."""
    ancla_b = {"latitude": -0.1807, "longitude": -78.4678, "geometry_type": "point"}
    previos = _turno(_geocode(), _search(), texto="Busco en La Carolina")
    actuales = _turno(_geocode(lat=ancla_b["latitude"], lon=ancla_b["longitude"],
                               consulta="La Floresta, Quito, Ecuador"),
                      _search(ancla=ancla_b, dist=310.0))
    r = _relacion_territorial_del_turno(previos + actuales)
    assert r["ancla_busqueda"]["latitude"] == ancla_b["latitude"]
    assert r["distancia_metros"] == 310.0


def test_si_el_turno_actual_NO_busco_no_se_hereda():
    """EL GUARD DE LA UNIDAD. El turno N-1 tuvo relación; el turno N no llamó a ninguna
    tool de búsqueda. Heredar la del turno anterior sería gobernar la respuesta de hoy con
    la autoridad de ayer — el peor modo de fallo de este mecanismo, y silencioso."""
    previos = _turno(_geocode(), _search())
    actuales = [HumanMessage(content="¿y cuántos dormitorios tiene?"),
                AIMessage(content="Tiene 2.")]
    assert _relacion_territorial_del_turno(previos + actuales) is None


# ══ 3 · EL LABEL · sólo si el ancla corresponde al geocode del mismo turno ═══════════
def test_el_lugar_se_nombra_cuando_el_ancla_coincide_con_el_geocode():
    r = _relacion_territorial_del_turno(_turno(_geocode(), _search()))
    assert r["consulta"] == CONSULTA


def test_si_el_ancla_NO_coincide_con_el_geocode_no_se_nombra_el_lugar():
    """El modelo puede geocodificar un sitio y buscar alrededor de OTRO punto. Atribuir el
    topónimo a esa búsqueda sería inventar la correlación."""
    otro = {"latitude": -0.1500, "longitude": -78.4000, "geometry_type": "point"}
    r = _relacion_territorial_del_turno(_turno(_geocode(), _search(ancla=otro)))
    assert r is not None
    assert r.get("consulta") is None


def test_sin_geocode_en_el_turno_no_se_nombra_el_lugar():
    r = _relacion_territorial_del_turno(_turno(_search()))
    assert r is not None
    assert r.get("consulta") is None


# ══ 4 · EL BLOQUE AUTORITATIVO · qué se puede afirmar ═══════════════════════════════
def _bloque():
    return bloque_autoritativo(
        _cards(), {"operacion": "arriendo", "presupuesto_max": 900.0}, [], (None, None),
        relacion_territorial=_relacion_territorial_del_turno(_turno(_geocode(), _search())))


def test_el_bloque_declara_la_proximidad_como_lo_demostrado():
    b = _bloque().lower()
    assert "572" in b
    assert "punto" in b


def test_el_bloque_declara_que_la_pertenencia_NO_esta_establecida():
    """No basta con «pertenencia = unknown»: G20-A ya probó que enunciar el estado de la
    evidencia no gobierna la afirmación. El bloque debe decir que NO está autorizada."""
    b = _bloque().lower()
    assert "no est" in b          # "no establecida" / "no está establecida"
    assert "pertenen" in b


def test_el_bloque_prohibe_explicitamente_la_afirmacion_de_pertenencia():
    b = _bloque().lower()
    assert "en la floresta" in b   # aparece como la frase PROHIBIDA, citada
    assert any(p in b for p in ("no afirmes", "prohibido", "no autoriz"))


def test_el_bloque_prohibe_centro_corazon_centroide():
    b = _bloque().lower()
    assert any(p in b for p in ("centro", "corazón", "corazon", "centroide"))
    assert any(p in b for p in ("no afirmes", "prohibido", "no autoriz"))


def test_el_bloque_NO_convierte_unknown_en_false():
    """«está fuera» sería tan inventado como «está en». `unknown` restringe lo afirmable;
    no autoriza el contrario.

    OJO CON LA ASERCIÓN: buscar la ausencia de «no pertenece» sería un test roto, porque no
    distingue AFIRMAR de PROHIBIR — y el bloque debe prohibirlo explícitamente. Se exige
    que la negación aparezca DENTRO de la sección de prohibiciones, nunca antes de ella.
    """
    b = _bloque().lower()
    corte = b.find("no afirmes")
    assert corte > 0, "falta la sección de prohibiciones"
    permitido, prohibido = b[:corte], b[corte:]
    # en lo AUTORIZADO no puede aparecer la negación
    for frase in ("fuera de", "no pertenece"):
        assert frase not in permitido
    # y la negación tiene que estar explícitamente vedada
    assert "no digas que está fuera" in prohibido
    assert "no pertenece" in prohibido


# ══ 5 · LAS TRES FAMILIAS ACREDITADAS SIGUEN PERMITIDAS ═════════════════════════════
def test_el_bloque_permite_la_referencia_a_la_consulta():
    """«Buscaste La Floresta» describe intención, no pertenencia. Prohibirlo convertiría
    la política en «nunca menciones el barrio», que es un fallo de diseño."""
    b = _bloque().lower()
    assert "buscaste" in b or "consulta" in b


def test_el_bloque_permite_los_POI_con_nombre_propio():
    """G20-E: «UPC La Floresta a ~13 min» está acreditado — 1 fila exacta en pois_vivos."""
    b = _bloque().lower()
    assert "poi" in b or "nombre propio" in b or "servicio" in b


def test_el_bloque_NO_prohibe_el_toponimo_en_bloque():
    """Un «nunca menciones La Floresta» rompería las tres familias válidas."""
    b = _bloque().lower()
    assert "nunca menciones" not in b
    assert "no menciones la floresta" not in b


# ══ 6 · NO SE ROMPE NADA DE LO QUE YA FUNCIONA ═════════════════════════════════════
def test_sin_relacion_el_bloque_es_identico_al_de_hoy():
    """Compatibilidad: el parámetro es opcional y aditivo."""
    cards, prefs = _cards(), {"operacion": "arriendo", "presupuesto_max": 900.0}
    assert (bloque_autoritativo(cards, prefs, [], (None, None), relacion_territorial=None)
            == bloque_autoritativo(cards, prefs, [], (None, None)))


def test_sin_cards_sigue_devolviendo_vacio():
    """G20-B1-NOCARDS-01 · KNOWN/DEFERRED. El borde no se toca en esta unidad."""
    r = _relacion_territorial_del_turno(_turno(_geocode(), _search()))
    assert bloque_autoritativo([], {}, [], (None, None), relacion_territorial=r) == ""


def test_el_bloque_sigue_gobernando_el_presupuesto():
    """La sección territorial no puede desplazar la que ya se respeta 13/13."""
    b = _bloque()
    assert "900" in b
    assert "630" in b


@pytest.mark.parametrize("clave", ["cards", "descartadas", "preferencias", "priorizado"])
def test_la_relacion_no_altera_el_resto_del_panel(clave):
    """El ranking lo decide el motor de encaje; esta costura sólo describe el retrieval."""
    from app.decision import assembler
    assert hasattr(assembler, "_relacion_territorial_del_turno")
    r = _relacion_territorial_del_turno(_turno(_geocode(), _search()))
    assert clave not in r
