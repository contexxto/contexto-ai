"""
Tests offline del Walk Score real (app/walk_score.py).
No tocan red: prueban la lógica pura de scoring con POIs sintéticos.
"""
from app.walk_score import _decay, _haversine_m, compute_walk_score, extraer_conectividad

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


# ── Conectividad (hubs de transporte masivo) ────────────────────────────────

def test_conectividad_sin_hubs_es_none():
    pois = [_poi(50, 0, shop="supermarket"), _poi(60, 0, amenity="restaurant")]
    assert extraer_conectividad(pois, LAT, LON) is None


def test_conectividad_detecta_metro_y_terminal_ordenados():
    pois = [
        _poi(450, 0, amenity="bus_station", name="Terminal Terrestre Quitumbe"),
        _poi(280, 0, railway="station", station="subway", name="Quitumbe"),
        _poi(50, 0, shop="supermarket"),  # ruido: no es hub
    ]
    out = extraer_conectividad(pois, LAT, LON)
    assert out is not None
    # El Metro (más cercano) va primero.
    assert out["hubs"][0]["clase"] == "metro"
    assert out["hubs"][0]["nombre"] == "Quitumbe"
    assert out["hubs"][1]["clase"] == "terminal"
    assert "🚇 Quitumbe" in out["texto"]
    assert "Terminal Terrestre Quitumbe" in out["texto"]


def test_conectividad_hub_sin_nombre_usa_etiqueta():
    pois = [_poi(300, 0, amenity="bus_station")]
    out = extraer_conectividad(pois, LAT, LON)
    assert out["hubs"][0]["nombre"] is None
    assert "Terminal terrestre a ~" in out["texto"]


def test_conectividad_filtra_parqueaderos_de_buses():
    # OSM tagea parqueaderos/depósitos como amenity=bus_station: deben filtrarse.
    pois = [
        _poi(100, 0, amenity="bus_station", name="Estacionamiento para autobuses y camiones"),
        _poi(200, 0, amenity="bus_station", name="Terminal Quitumbe"),
    ]
    out = extraer_conectividad(pois, LAT, LON)
    assert len(out["hubs"]) == 1
    assert out["hubs"][0]["nombre"] == "Terminal Quitumbe"


def test_conectividad_limita_a_max_hubs():
    pois = [
        _poi(100, 0, railway="station", name="A"),
        _poi(200, 0, railway="station", name="B"),
        _poi(300, 0, railway="station", name="C"),
        _poi(400, 0, railway="station", name="D"),
    ]
    out = extraer_conectividad(pois, LAT, LON, max_hubs=3)
    assert len(out["hubs"]) == 3
    assert [h["nombre"] for h in out["hubs"]] == ["A", "B", "C"]


# ── Entorno destacado (servicios cercanos, fuente OSM) ──────────────────────

def test_entorno_osm_sin_servicios_es_none():
    from app.entorno import extraer_entorno_osm
    pois = [_poi(50, 0, highway="bus_stop"), _poi(60, 0, building="yes")]
    assert extraer_entorno_osm(pois, LAT, LON) is None


def test_entorno_osm_detecta_imanes_de_vida_con_nombre_y_orden():
    from app.entorno import extraer_entorno_osm
    pois = [
        _poi(600, 0, shop="mall", name="Quicentro Sur"),
        _poi(300, 0, amenity="school", name="Unidad Educativa Quitumbe"),
        _poi(450, 0, amenity="police", name="UPC Quitumbe"),
        _poi(500, 0, amenity="place_of_worship", name="Iglesia de Quitumbe"),
        _poi(80, 0, amenity="school"),       # sin nombre → se ignora
    ]
    out = extraer_entorno_osm(pois, LAT, LON)
    assert out["fuente"] == "osm"
    # Ordenado por distancia: colegio (300) primero.
    assert out["items"][0]["nombre"] == "Unidad Educativa Quitumbe"
    assert "🏫 Unidad Educativa Quitumbe" in out["texto"]
    assert "🛍️ Quicentro Sur" in out["texto"]
    assert "🛡️ UPC Quitumbe" in out["texto"]


def test_entorno_osm_toma_el_mas_cercano_por_categoria():
    from app.entorno import extraer_entorno_osm
    pois = [
        _poi(800, 0, shop="mall", name="Mall Lejano"),
        _poi(200, 0, shop="mall", name="Mall Cercano"),
    ]
    out = extraer_entorno_osm(pois, LAT, LON)
    nombres = [i["nombre"] for i in out["items"]]
    assert "Mall Cercano" in nombres and "Mall Lejano" not in nombres
