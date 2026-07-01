"""Tests de la directiva de mapa (app/routers/chat.py _map_seed_from_cards).

La directiva {modo, foco, capas, pines} es el "MECANISMO ÚNICO" del SPEC_Mapa_Vivo: el mapa
es función de ESTO, no de results planos. Verificamos: forma, bbox, que los pines llevan solo
lo del mapa (encaje/fresco/badge/dirección) y NUNCA precio (guardrail), y degradación honesta.
"""
from app.routers.chat import _map_seed_from_cards


def _card(cid, lat, lon, **over):
    c = {
        "id": cid, "lat": lat, "lon": lon, "direccion": f"Dir {cid}", "tipo_activo": "Departamento",
        "precio": 900, "encaje": 80, "fresco": False, "pois": [{"emoji": "🌳", "minutos": 3, "texto": "Parque"}],
    }
    c.update(over)
    return c


def test_sin_cards_es_none():
    assert _map_seed_from_cards([]) is None


def test_sin_coords_es_none():
    # Cards sin lat/lon (geom nula) → no hay nada que encuadrar.
    assert _map_seed_from_cards([_card("a", None, None)]) is None


def test_forma_y_bbox():
    cards = [_card("a", -0.18, -78.48), _card("b", -0.20, -78.50, encaje=60, fresco=True)]
    ms = _map_seed_from_cards(cards)
    assert ms["modo"] == "zona"
    assert set(ms) == {"modo", "foco", "capas", "pines"}
    # bbox = [[minLon, minLat], [maxLon, maxLat]]
    assert ms["foco"]["bbox"] == [[-78.50, -0.20], [-78.48, -0.18]]
    assert len(ms["pines"]) == 2


def test_pin_lleva_lo_del_mapa_no_precio():
    ms = _map_seed_from_cards([_card("a", -0.18, -78.48)])
    p = ms["pines"][0]
    assert set(p) == {"id", "lat", "lon", "encaje", "fresco", "badge", "direccion", "tipo_activo"}
    assert "precio" not in p  # guardrail del SPEC: el pin NUNCA lleva precio
    assert p["encaje"] == 80 and p["badge"]["emoji"] == "🌳"


def test_capas_reflejan_lo_presente():
    # Con encaje y con fresco → ambas capas.
    ms = _map_seed_from_cards([_card("a", -0.18, -78.48, fresco=True)])
    assert "encaje" in ms["capas"] and "verificacion" in ms["capas"]
    # Sin encaje (None) y sin fresco → ninguna capa.
    ms2 = _map_seed_from_cards([_card("a", -0.18, -78.48, encaje=None, fresco=False)])
    assert ms2["capas"] == []


def test_ignora_cards_sin_coords_mezcladas():
    cards = [_card("a", -0.18, -78.48), _card("b", None, None)]
    ms = _map_seed_from_cards(cards)
    assert len(ms["pines"]) == 1 and ms["pines"][0]["id"] == "a"
