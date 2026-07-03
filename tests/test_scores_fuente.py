"""Mejora B (foso de honestidad, 2026-07-03): el anuncio /a/{id} rotula CADA score con su
procedencia real en vez de afirmar "comercios reales OpenStreetMap" para todos.

El bug que motivó esto: Mejora A puso un rótulo FIJO que afirmaba caminabilidad = OSM para
todo inmueble. Pero el walk_score nace heurístico (scores_heuristicos.scores_para) y solo se
sobrescribe con OSM si Overpass responde; si no, queda heurístico y el rótulo MENTÍA. Ahora
persistimos walk_score_fuente y el anuncio declara la verdad por dato.

Estas pruebas blindan el invariante de honestidad: la caminabilidad refleja la fuente
PERSISTIDA, y ruido/vegetación/tráfico nunca se rotulan como medición (son heurísticos por
construcción). Si alguien "mejora" el mapeo para reclamar medición inexistente, esto rompe.
"""
from app.routers.assets import _scores_fuente


def test_caminabilidad_refleja_la_procedencia_persistida():
    # 'osm' == se contó sobre comercios reales; el front puede afirmar OpenStreetMap.
    assert _scores_fuente("osm")["caminabilidad"] == "osm"
    # 'heuristico' == estimación por zona (Overpass no respondió); el front NO afirma OSM.
    assert _scores_fuente("heuristico")["caminabilidad"] == "heuristico"
    # None == legado/desconocida; se degrada a estimación, jamás se inventa OSM.
    assert _scores_fuente(None)["caminabilidad"] is None


def test_ruido_vegetacion_trafico_nunca_reclaman_medicion():
    # Son heurísticos por construcción (scores_para). Sea cual sea la fuente del walk score,
    # jamás deben rotularse como una medición que no existe — ese es el foso de honestidad.
    for fuente in ("osm", "heuristico", None):
        sf = _scores_fuente(fuente)
        assert sf["ruido"] == "heuristico"
        assert sf["vegetacion"] == "heuristico"
        assert sf["trafico"] == "heuristico"


def test_expone_las_cuatro_capas_del_contexto():
    # El anuncio muestra cuatro scores; la procedencia debe existir para los cuatro
    # (aunque hoy tres sean fijas), para que el front nunca se quede sin rótulo.
    sf = _scores_fuente("osm")
    assert set(sf) == {"caminabilidad", "ruido", "vegetacion", "trafico"}
