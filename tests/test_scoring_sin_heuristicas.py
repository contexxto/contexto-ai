"""E0.4 del Trust Gate — ningún dato sin fuente altera el ranking, y el motor va versionado.

D3 del Execution Plan 1.0 (2026-08-24) cerró la discusión: ruido, tráfico y vegetación
salen del scoring mientras no exista una fuente defendible. Permanecen visibles como
insufficient_evidence, pero no mueven el número.

Lo que estaba pasando: `tranquilidad` era una de las 8 dimensiones de la lista blanca de
encaje.py, con peso 1.0, y su única fuente es scores_heuristicos.scores_para — una tabla
de 7 sectores de Quito escrita a mano más un desplazamiento derivado del hash SHA-256 de
la dirección. El motor de decisión puntuaba sobre un dato inventado.

Por qué importa más allá de la honestidad: la factualidad es una de las métricas del
benchmark que decide si la tesis de Contexto vive. Con heurísticas dentro del score, la
condición D estaría midiendo en parte la calidad de una invención.

Este archivo blinda el invariante. Si alguien devuelve una heurística al promedio, rompe
aquí y tiene que justificarlo.
"""
import pytest

from app.encaje import (
    DIMENSIONES,
    INSUFICIENTE,
    SCORE_VERSION,
    calcular_encaje,
)

# Señales cuya única procedencia es scores_heuristicos.scores_para. Ninguna puede,
# por sí sola, producir un número de encaje.
SENALES_SIN_FUENTE = [
    ("tranquilidad", {"ruido": "BAJO"}),
    ("tranquilidad", {"ruido": "MEDIO"}),
    ("tranquilidad", {"ruido": "ALTO"}),
    ("area_verde", {"vegetacion": 90}),
    ("area_verde", {"vegetacion": 10}),
]


@pytest.mark.parametrize("dimension,senal", SENALES_SIN_FUENTE)
def test_una_heuristica_sola_no_produce_score(dimension, senal):
    r = calcular_encaje({dimension: True}, senal)
    assert r["score"] is None, (
        f"{dimension} puntuó sobre {senal}, que sale de la tabla de sectores. "
        "Ningún dato sin fuente material puede alterar el ranking (D3)."
    )
    assert r["dimensiones_evaluadas"] == []


@pytest.mark.parametrize("dimension,senal", SENALES_SIN_FUENTE)
def test_la_heuristica_se_explica_aunque_no_puntue(dimension, senal):
    """D3 pide conservarlas visibles: "no tenemos medición" es información, el silencio no."""
    razon = calcular_encaje({dimension: True}, senal)["razones"][0]
    assert razon["cumple"] == INSUFICIENTE
    assert razon["aporta"] is False
    assert razon["texto"], "la dimensión debe seguir explicándose al comprador"
    assert razon["fuente"] is None, "sin fuente defendible no se declara ninguna"


def test_el_ruido_no_mueve_el_ranking():
    """Dos inmuebles idénticos salvo el ruido deben empatar. Es el corazón de E0.4."""
    prefs = {"tranquilidad": True, "caminable": True}
    silencioso = calcular_encaje(prefs, {"ruido": "BAJO", "walk_score": 70})
    ruidoso = calcular_encaje(prefs, {"ruido": "ALTO", "walk_score": 70})
    assert silencioso["score"] == ruidoso["score"]
    assert silencioso["cobertura"] == ruidoso["cobertura"]


def test_la_vegetacion_no_mueve_el_ranking():
    prefs = {"area_verde": True, "caminable": True}
    frondoso = calcular_encaje(prefs, {"vegetacion": 95, "walk_score": 70})
    pelado = calcular_encaje(prefs, {"vegetacion": 5, "walk_score": 70})
    assert frondoso["score"] == pelado["score"]


def test_el_parque_medido_si_mueve_el_ranking():
    """El contrapunto: lo que tiene fuente sigue contando. E0.4 no es apagar dimensiones,
    es apagar invenciones."""
    prefs = {"area_verde": True}
    cerca = calcular_encaje(prefs, {"parque_min": 4})
    lejos = calcular_encaje(prefs, {"parque_min": 25})
    assert cerca["score"] > lejos["score"]
    assert cerca["razones"][0]["fuente"] == "mapa"


def test_el_trafico_nunca_estuvo_en_la_lista_blanca():
    """D3 nombra tráfico junto a ruido y vegetación. Aquí no hubo nada que retirar:
    nunca fue una dimensión puntuable. Se deja escrito para que no se añada por
    simetría algún día sin una fuente detrás."""
    assert not any("trafico" in d or "tráfico" in d for d in DIMENSIONES)


def test_el_score_viaja_versionado():
    """Sin versión, dos corridas no son comparables y el benchmark no puede reproducirse."""
    con_score = calcular_encaje({"caminable": True}, {"walk_score": 80})
    sin_score = calcular_encaje({"caminable": True}, {})
    assert con_score["score_version"] == SCORE_VERSION
    # También cuando no hay nada que puntuar: la rama temprana no puede olvidarla.
    assert sin_score["score"] is None
    assert sin_score["score_version"] == SCORE_VERSION


def test_la_version_identifica_al_motor_post_trust_gate():
    assert isinstance(SCORE_VERSION, str) and SCORE_VERSION.strip()
    assert SCORE_VERSION == "encaje-v0"
