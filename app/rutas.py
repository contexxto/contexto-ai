"""
Rutas a pie EN VIVO con Google Routes API (capa "desde la tierra").

Dado un punto (un inmueble), encuentra sus servicios cercanos CON coordenadas
(Places searchNearby) y traza la ruta peatonal real a cada uno (computeRoutes,
modo WALK), devolviendo la línea (polyline decodificada) + el tiempo exacto.

Va por el BACKEND: la GOOGLE_MAPS_API_KEY nunca toca el frontend. Si no hay key,
devuelve None y el mapa simplemente no muestra rutas.
"""
from __future__ import annotations

import asyncio

import httpx

from app.config import settings
from app.entorno import _CATEGORIAS, _nombre_valido
from app.walk_score import _haversine_m

_TIMEOUT = 8.0
_RADIO_M = 1500


def _decode_polyline(enc: str) -> list[list[float]]:
    """Decodifica un polyline de Google (precisión 5) → lista de [lon, lat]."""
    coords: list[list[float]] = []
    index = lat = lng = 0
    n = len(enc)
    while index < n:
        for is_lat in (True, False):
            shift = result = 0
            while True:
                b = ord(enc[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if (result & 1) else (result >> 1)
            if is_lat:
                lat += delta
            else:
                lng += delta
        coords.append([lng / 1e5, lat / 1e5])
    return coords


# Mapa tipo-de-Google → categoría (para elegir servicios DIVERSOS, no 3 farmacias).
_TIPO_CAT = {c["google"]: c["key"] for c in _CATEGORIAS}
for _t in ("subway_station", "bus_station", "train_station", "transit_station"):
    _TIPO_CAT[_t] = "transporte"


async def _servicios_con_coords(lat: float, lon: float, key: str, n: int = 3) -> list[dict]:
    """El servicio más cercano POR CATEGORÍA (diverso), priorizando transporte."""
    tipos = [c["google"] for c in _CATEGORIAS] + ["subway_station", "bus_station", "train_station"]
    body = {
        "includedTypes": tipos,
        "maxResultCount": 20,
        "rankPreference": "DISTANCE",
        "languageCode": "es",
        "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": float(_RADIO_M)}},
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "places.displayName,places.location,places.types",
    }
    verify = settings.ssl_verify.lower() != "false"
    async with httpx.AsyncClient(verify=verify, timeout=_TIMEOUT) as c:
        r = await c.post("https://places.googleapis.com/v1/places:searchNearby", json=body, headers=headers)
        r.raise_for_status()
        places = r.json().get("places", [])

    # El más cercano por categoría.
    mejor: dict[str, dict] = {}
    for pl in places:
        loc = pl.get("location", {})
        nombre = (pl.get("displayName") or {}).get("text")
        if "latitude" not in loc or not _nombre_valido(nombre):
            continue
        cat = next((_TIPO_CAT[t] for t in pl.get("types", []) if t in _TIPO_CAT), None)
        if not cat:
            continue
        d = int(_haversine_m(lat, lon, loc["latitude"], loc["longitude"]))
        if cat not in mejor or d < mejor[cat]["distancia_m"]:
            mejor[cat] = {"nombre": nombre, "lat": loc["latitude"], "lon": loc["longitude"], "distancia_m": d}

    # Búsqueda dedicada del hub de transporte (Metro/terminal): suele estar más
    # lejos que los 20 resultados generales, pero es el héroe de plusvalía.
    if "transporte" not in mejor:
        try:
            tbody = {
                "includedTypes": ["subway_station", "bus_station", "train_station", "transit_station"],
                "maxResultCount": 5, "rankPreference": "DISTANCE", "languageCode": "es",
                "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": 2500.0}},
            }
            async with httpx.AsyncClient(verify=verify, timeout=_TIMEOUT) as c2:
                tr = await c2.post("https://places.googleapis.com/v1/places:searchNearby", json=tbody, headers=headers)
                tr.raise_for_status()
                for pl in tr.json().get("places", []):
                    loc = pl.get("location", {})
                    nombre = (pl.get("displayName") or {}).get("text")
                    if "latitude" in loc and _nombre_valido(nombre):
                        mejor["transporte"] = {"nombre": nombre, "lat": loc["latitude"], "lon": loc["longitude"],
                                               "distancia_m": int(_haversine_m(lat, lon, loc["latitude"], loc["longitude"]))}
                        break
        except Exception:  # noqa: BLE001
            pass

    if not mejor:
        return []
    # Priorizar transporte (Metro/terminal) + completar con los más cercanos distintos.
    orden = sorted(mejor.values(), key=lambda i: i["distancia_m"])
    res: list[dict] = []
    if "transporte" in mejor:
        res.append(mejor["transporte"])
    for it in orden:
        if len(res) >= n:
            break
        if it not in res:
            res.append(it)
    res.sort(key=lambda i: i["distancia_m"])
    return res[:n]


async def _ruta_a_pie(client: httpx.AsyncClient, o_lat: float, o_lon: float,
                      d_lat: float, d_lon: float, key: str) -> dict | None:
    body = {
        "origin": {"location": {"latLng": {"latitude": o_lat, "longitude": o_lon}}},
        "destination": {"location": {"latLng": {"latitude": d_lat, "longitude": d_lon}}},
        "travelMode": "WALK",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline",
    }
    r = await client.post("https://routes.googleapis.com/directions/v2:computeRoutes", json=body, headers=headers)
    r.raise_for_status()
    routes = r.json().get("routes", [])
    if not routes:
        return None
    rt = routes[0]
    dur = str(rt.get("duration", "0s"))
    secs = int(dur[:-1]) if dur.endswith("s") and dur[:-1].isdigit() else 0
    enc = (rt.get("polyline") or {}).get("encodedPolyline", "")
    return {
        "duracion_min": max(1, round(secs / 60)),
        "distancia_m": rt.get("distanceMeters"),
        "coords": _decode_polyline(enc) if enc else [],
    }


async def rutas_desde(lat: float, lon: float, n: int = 3) -> list[dict] | None:
    """Rutas peatonales reales a los N servicios más cercanos. None si no hay key."""
    key = settings.google_maps_api_key
    if not key:
        return None
    try:
        servicios = await _servicios_con_coords(lat, lon, key, n)
        if not servicios:
            return []
        verify = settings.ssl_verify.lower() != "false"
        async with httpx.AsyncClient(verify=verify, timeout=_TIMEOUT) as c:
            rutas = await asyncio.gather(
                *[_ruta_a_pie(c, lat, lon, s["lat"], s["lon"], key) for s in servicios],
                return_exceptions=True,
            )
        out = []
        for s, rt in zip(servicios, rutas):
            if isinstance(rt, dict) and rt.get("coords"):
                out.append({"nombre": s["nombre"], "destino": [s["lon"], s["lat"]], **rt})
        return out
    except Exception:  # noqa: BLE001
        return None
