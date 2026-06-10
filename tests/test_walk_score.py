"""
Tests offline del Walk Score real (app/walk_score.py).
No tocan red: prueban la lógica pura de scoring con POIs sintéticos.
"""
from app.walk_score import _decay, _haversine_m, compute_walk_score

# Punto de referencia (La Carolina, Quito aprox.)
LAT, LON = -0.1807, -78.4836


def _poi(dlat_m: float, dlon_m: float, **tags) -> dict:
    """POI desplazado ~dlat_m/dlon_m metros del punto base (aprox.)."""
    return {
        "lat": LAT + dlat_m / 111_320.0,
        "lon": LON + dlon_m / 111_320.0,
        "tags": tags,
    }


def test_decay_monotono_y_limites():
    assert _decay(0) == 1.0
    assert _decay(400) == 1.0
    assert _decay(2400) == 0.0
    assert _decay(5000) == 0.0
    # Estrictamente decreciente en la zona media.
    assert _decay(500) > _decay(1000) > _decay(2000) > 0.0


def test_haversine_cero_y_positivo():
    assert _haversine_m(LAT, LON, LAT, LON) == 0.0
    d = _haversine_m(LAT, LON, LAT + 0.01, LON)
    assert 1050 < d < 1150  # ~1.1 km por 0.01° de latitud


def test_sin_pois_score_cero():
    out = compute_walk_score([], LAT, LON)
    assert out["walk_score"] == 0
    assert out["fuente"] == "osm"
    assert out["pois_analizados"] == 0


def test_zona_caminable_score_alto():
    # Mezcla rica de servicios MUY cerca (≤150 m) → debe dar score alto.
    pois = [
        _poi(50, 0, shop="supermarket"),
        _poi(0, 60, amenity="restaurant"),
        _poi(70, 0, amenity="restaurant"),
        _poi(0, 90, amenity="cafe"),
        _poi(100, 0, shop="bakery"),
        _poi(0, 120, amenity="pharmacy"),
        _poi(80, 80, amenity="bank"),
        _poi(120, 0, leisure="park"),
        _poi(0, 140, amenity="school"),
        _poi(60, 60, highway="bus_stop"),
    ]
    out = compute_walk_score(pois, LAT, LON)
    assert out["walk_score"] >= 80
    assert out["pois_analizados"] == 10


def test_zona_aislada_score_bajo():
    # Pocos servicios y lejos (≥2 km) → score bajo.
    pois = [
        _poi(2100, 0, shop="convenience"),
        _poi(0, 2200, amenity="restaurant"),
    ]
    out = compute_walk_score(pois, LAT, LON)
    assert out["walk_score"] <= 15


def test_densidad_premia_mas_opciones():
    cerca = _poi(80, 0, amenity="restaurant")
    uno = compute_walk_score([cerca], LAT, LON)
    varios = compute_walk_score(
        [cerca, _poi(90, 0, amenity="restaurant"), _poi(100, 0, amenity="restaurant")],
        LAT, LON,
    )
    # Más restaurantes cercanos → mayor contribución de la categoría densa.
    assert varios["desglose"]["restaurantes"] > uno["desglose"]["restaurantes"]


def test_tags_no_reconocidos_no_aportan():
    pois = [_poi(50, 0, building="yes"), _poi(60, 0, highway="residential")]
    out = compute_walk_score(pois, LAT, LON)
    assert out["walk_score"] == 0
