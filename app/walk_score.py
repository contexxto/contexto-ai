"""
Walk Score REAL derivado de OpenStreetMap (primer ladrillo del foso de datos).

A diferencia de los scores heurísticos por sector (capa base sembrada), este
módulo calcula la caminabilidad de una coordenada concreta contando los puntos
de interés (POIs) reales a su alrededor vía la API Overpass de OSM, y aplicando
una función de decaimiento por distancia — la misma idea metodológica de Walk
Score: lo que está a 5 min a pie vale full; a ~30 min, casi nada.

Diseño:
- `compute_walk_score(pois, lat, lon)` es una función PURA (sin red) → testeable.
- `walk_score_para(lat, lon)` hace la llamada a Overpass y delega el cálculo.
- Si Overpass no responde, devuelve None y el llamador cae al heurístico.

Fuente: OpenStreetMap (ODbL). Costo: gratis. Esto es lo que pre-hidrataremos
para toda Quito en una malla, de modo que un activo nuevo tenga score instantáneo.
"""
from __future__ import annotations

import math

import httpx

from app.config import settings

# Endpoints públicos de Overpass (probamos en orden si uno falla).
_OVERPASS_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
_RADIUS_M = 1600          # ~1 milla: cobertura de caminabilidad
_TIMEOUT = 25.0

# Categorías de caminabilidad → peso relativo + tags OSM que las representan.
# Las categorías "densas" (donde más-es-mejor) suman varios POIs cercanos.
_CATEGORIES: dict[str, tuple[float, dict[str, set[str]], bool]] = {
    # nombre:            (peso, {clave_osm: {valores}},               densa?)
    "supermercado":      (3.0, {"shop": {"supermarket", "convenience", "greengrocer", "general"}}, False),
    "restaurantes":      (2.0, {"amenity": {"restaurant", "fast_food"}}, True),
    "cafeterias":        (1.5, {"amenity": {"cafe"}}, True),
    "compras":           (2.0, {"shop": {"mall", "clothes", "department_store", "bakery", "butcher", "shoes", "books"}}, True),
    "salud":             (1.5, {"amenity": {"pharmacy", "hospital", "clinic", "doctors"}, "shop": {"chemist"}}, False),
    "bancos":            (1.0, {"amenity": {"bank", "atm"}}, False),
    "parques":           (1.5, {"leisure": {"park", "garden"}}, False),
    "educacion":         (1.5, {"amenity": {"school", "kindergarten", "university", "college"}}, False),
    "transporte":        (2.0, {"highway": {"bus_stop"}, "public_transport": {"platform", "station", "stop_position"}, "railway": {"station", "subway_entrance", "tram_stop"}}, True),
}
_TOTAL_WEIGHT = sum(w for (w, _, _) in _CATEGORIES.values())
# Pesos decrecientes para categorías densas (premia 2-3 opciones, no infinitas).
_DENSITY_WEIGHTS = (1.0, 0.4, 0.2, 0.1, 0.05)
_DENSITY_MAX = sum(_DENSITY_WEIGHTS)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en metros entre dos coordenadas (esfera)."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _decay(d_m: float) -> float:
    """Decaimiento por distancia a pie: 1.0 a ≤400 m, 0.0 a ≥2400 m."""
    if d_m <= 400:
        return 1.0
    if d_m >= 2400:
        return 0.0
    return max(0.0, 1.0 - ((d_m - 400) / 2000.0) ** 0.7)


def _matches(tags: dict, mapping: dict[str, set[str]]) -> bool:
    for key, values in mapping.items():
        if tags.get(key) in values:
            return True
    return False


def compute_walk_score(pois: list[dict], lat: float, lon: float) -> dict:
    """
    Calcula el Walk Score (0-100) a partir de una lista de POIs ya consultados.
    Función PURA: cada POI es {"lat", "lon", "tags"}. No hace red.
    """
    contribuciones: dict[str, float] = {}
    aporte_total = 0.0

    for nombre, (peso, mapping, densa) in _CATEGORIES.items():
        # Distancias (con decaimiento) de los POIs de esta categoría.
        decays: list[float] = []
        for p in pois:
            tags = p.get("tags") or {}
            if _matches(tags, mapping):
                d = _haversine_m(lat, lon, p["lat"], p["lon"])
                decays.append(_decay(d))
        decays.sort(reverse=True)
        if not decays:
            contribuciones[nombre] = 0.0
            continue

        if densa:
            # Suma ponderada de los mejores N (premia densidad, con rendimientos
            # decrecientes), normalizada contra el máximo fijo: así tener 1 sola
            # opción no satura la categoría, pero 4-5 cercanas sí la maximizan.
            top = decays[: len(_DENSITY_WEIGHTS)]
            ganado = sum(d * w for d, w in zip(top, _DENSITY_WEIGHTS))
            factor = ganado / _DENSITY_MAX
        else:
            factor = decays[0]  # solo el más cercano

        aporte = peso * factor
        contribuciones[nombre] = round(aporte, 3)
        aporte_total += aporte

    score = round(100.0 * aporte_total / _TOTAL_WEIGHT)
    return {
        "walk_score": int(max(0, min(100, score))),
        "fuente": "osm",
        "pois_analizados": len(pois),
        "desglose": contribuciones,
    }


async def _fetch_pois(lat: float, lon: float) -> list[dict] | None:
    """Consulta Overpass por POIs alrededor del punto. None si todo mirror falla."""
    query = (
        "[out:json][timeout:25];("
        f"node(around:{_RADIUS_M},{lat},{lon})[shop];"
        f"node(around:{_RADIUS_M},{lat},{lon})[amenity];"
        f"node(around:{_RADIUS_M},{lat},{lon})[leisure=park];"
        f"node(around:{_RADIUS_M},{lat},{lon})[leisure=garden];"
        f"node(around:{_RADIUS_M},{lat},{lon})[highway=bus_stop];"
        f"node(around:{_RADIUS_M},{lat},{lon})[public_transport];"
        f"node(around:{_RADIUS_M},{lat},{lon})[railway=station];"
        ");out body;"
    )
    verify = settings.ssl_verify.lower() != "false"
    for url in _OVERPASS_MIRRORS:
        try:
            async with httpx.AsyncClient(verify=verify, timeout=_TIMEOUT) as c:
                resp = await c.post(url, data={"data": query},
                                    headers={"User-Agent": "contexto_ai_v2"})
                resp.raise_for_status()
                elements = resp.json().get("elements", [])
        except Exception:  # noqa: BLE001 — best-effort; probamos el siguiente mirror
            continue
        pois = [
            {"lat": e["lat"], "lon": e["lon"], "tags": e.get("tags", {})}
            for e in elements
            if e.get("type") == "node" and "lat" in e and "lon" in e
        ]
        return pois
    return None


async def walk_score_para(lat: float, lon: float) -> dict | None:
    """
    Walk Score real para una coordenada. Devuelve dict con score + desglose,
    o None si Overpass no está disponible (el llamador cae al heurístico).
    """
    pois = await _fetch_pois(lat, lon)
    if pois is None:
        return None
    return compute_walk_score(pois, lat, lon)
