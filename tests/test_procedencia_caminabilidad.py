"""E0.3 del Trust Gate — la procedencia de la caminabilidad dice una sola verdad.

Historia, porque explica por qué este archivo existe además de test_scores_fuente.py:

El 2026-07-03 se detectó que el anuncio /a/{id} afirmaba "comercios reales
OpenStreetMap" para todo inmueble, cuando el walk_score nace heurístico
(scores_heuristicos.scores_para) y solo se sobrescribe con OSM si Overpass
responde. Se arregló ESE camino — persistiendo walk_score_fuente y rotulando por
dato— y test_scores_fuente.py lo blindó.

Pero el mismo error vivía en un segundo lugar y ahí nadie lo tocó: el motor de
encaje afirmaba "OpenStreetMap" incondicionalmente en su razón de caminabilidad,
porque _senales_encaje nunca le pasaba la procedencia. Resultado: el mismo activo
daba dos verdades distintas según se mirara la ficha o el encaje. La auditoría lo
listó como uno de los cuatro P0.

Aquí se prueba el invariante que faltaba: la razón del motor refleja la
procedencia PERSISTIDA, y jamás reclama una medición que no existe. El bloque
autoritativo (encaje_contexto:216) deriva su rótulo de esta misma razón, así que
queda cubierto por transitividad.
"""
import pytest

from app.encaje import calcular_encaje
from app.routers.assets import _scores_fuente
from app.routers.chat import _senales_encaje


def _razon_caminable(inmueble: dict) -> dict:
    enc = calcular_encaje({"caminable": True}, inmueble)
    return next(r for r in enc["razones"] if r["dimension"] == "caminable")


def test_fuente_osm_si_afirma_openstreetmap():
    """'osm' == se contó sobre comercios reales. Aquí sí se puede afirmar."""
    r = _razon_caminable({"walk_score": 90, "walk_score_fuente": "osm"})
    assert r["fuente"] == "OpenStreetMap"


@pytest.mark.parametrize("fuente", ["heuristico", None, "", "cualquier-cosa-futura"])
def test_sin_medicion_no_se_afirma_openstreetmap(fuente):
    """El corazón del P0: si no consta que se midió, no se reclama medición.

    Incluye el valor desconocido a propósito — si mañana aparece una procedencia
    nueva sin mapear, debe degradar a estimación, nunca ascender a OSM.
    """
    r = _razon_caminable({"walk_score": 90, "walk_score_fuente": fuente})
    assert r["fuente"] == "estimación por zona"
    assert "OpenStreetMap" not in (r["fuente"] or "")


def test_procedencia_no_altera_el_numero():
    """E0.3 corrige el rótulo, no el peso. Cambiar el score aquí sería E0.4."""
    medido = calcular_encaje({"caminable": True}, {"walk_score": 90, "walk_score_fuente": "osm"})
    estimado = calcular_encaje({"caminable": True}, {"walk_score": 90, "walk_score_fuente": "heuristico"})
    assert medido["score"] == estimado["score"]
    assert medido["cobertura"] == estimado["cobertura"]


def test_sin_walk_score_sigue_siendo_sin_dato():
    """Sin número no hay razón que rotular: se mantiene aporta=False y fuente None."""
    r = _razon_caminable({"walk_score": None, "walk_score_fuente": "osm"})
    assert r["aporta"] is False
    assert r["fuente"] is None


def test_senales_encaje_transporta_la_procedencia():
    """El eslabón que faltaba. La query ya traía el dato (chat.py: walk_score_fuente
    AS caminabilidad_fuente) y la card ya lo usaba; el motor no lo recibía."""
    row = {"tipo_activo": "Departamento", "caminabilidad": 88, "caminabilidad_fuente": "osm"}
    assert _senales_encaje(row, {})["walk_score_fuente"] == "osm"


@pytest.mark.parametrize("persistida", ["osm", "heuristico", None])
def test_motor_y_ficha_no_pueden_divergir(persistida):
    """El invariante que evita que esto se arregle en un camino y no en el otro.

    Ambos leen la MISMA columna persistida; se comprueba que coincidan en si
    afirman medición o no. Los formatos difieren a propósito —la ficha devuelve
    la etiqueta cruda para el front, el motor una frase para la prosa—, así que
    lo que se compara es el veredicto, no el texto.
    """
    ficha_afirma_osm = _scores_fuente(persistida)["caminabilidad"] == "osm"
    motor = _razon_caminable({"walk_score": 75, "walk_score_fuente": persistida})
    motor_afirma_osm = motor["fuente"] == "OpenStreetMap"
    assert ficha_afirma_osm == motor_afirma_osm, (
        f"Con walk_score_fuente={persistida!r} la ficha y el motor discrepan sobre "
        f"si hubo medición: ficha={ficha_afirma_osm}, motor={motor_afirma_osm}"
    )
