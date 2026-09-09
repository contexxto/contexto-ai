"""Google como proveedor: Places y Routes, que NO son la misma capacidad (PLAN04-2.2).

Que las dos APIs lleven el mismo nombre comercial no las hace una sola cosa: Places
descubre lugares y Routes mide una caminata. Se quedan separadas —dos funciones, dos
endpoints, dos formas de fallar— porque el dia que una se caiga la otra tiene que poder
seguir, y porque la unidad 1.2 las acredita como evidencias distintas.

Este modulo no conoce la capa propia y no decide cuando se le pregunta: eso lo hace
`app/rutas.py`, que es quien tiene la politica. Aqui solo se llama y se traduce la
respuesta.

UNA ASIMETRIA QUE SE MOVIO TAL CUAL, NO SE ARREGLO. `_ruta_a_pie` recibe el
`httpx.AsyncClient` ya construido: no controla su propio transporte, asi que el timeout y
el `verify` de TLS los decide quien llama. Extraer la funcion mueve la peticion, no la
politica de conexion. `_TIMEOUT` viaja con este modulo porque es el plazo de una llamada a
Google, y `rutas.py` lo reimporta para los sitios de llamada heredados que todavia
conserva.

Endpoints, parametros, timeouts, categorias y fallbacks se movieron TAL CUAL. Sin
reintentos nuevos.
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.entorno import _CATEGORIAS, _nombre_valido
from app.place.providers import _MARGEN_MARCA_M, _es_marca
from app.walk_score import _haversine_m

# Timeout por llamada a Google (Places/Directions). El path del mapa hace 2 secuenciales;
# 5s mantiene el peor caso en ~10s, holgado bajo el wait_for(13s) del endpoint.
_TIMEOUT = 5.0


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


_CAT_GOOGLE = {c["key"]: [c["google"]] for c in _CATEGORIAS}
_CAT_GOOGLE["transporte"] = ["subway_station", "train_station", "bus_station", "transit_station"]


async def _nearest_categoria(lat: float, lon: float, cat: str, key: str, tipos: list[str] | None = None) -> dict | None:
    body = {
        "includedTypes": tipos or _CAT_GOOGLE.get(cat, []), "maxResultCount": 8, "rankPreference": "DISTANCE",
        "languageCode": "es",
        "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": 3000.0}},
    }
    headers = {"Content-Type": "application/json", "X-Goog-Api-Key": key,
               "X-Goog-FieldMask": "places.displayName,places.location"}
    verify = settings.ssl_verify.lower() != "false"
    try:
        async with httpx.AsyncClient(verify=verify, timeout=_TIMEOUT) as c:
            r = await c.post("https://places.googleapis.com/v1/places:searchNearby", json=body, headers=headers)
            r.raise_for_status()
            candidatos = []
            for pl in r.json().get("places", []):
                loc = pl.get("location", {})
                nombre = (pl.get("displayName") or {}).get("text")
                if "latitude" in loc and _nombre_valido(nombre):
                    candidatos.append({"nombre": nombre, "lat": loc["latitude"], "lon": loc["longitude"],
                                       "distancia_m": int(_haversine_m(lat, lon, loc["latitude"], loc["longitude"]))})
            if not candidatos:
                return None
            candidatos.sort(key=lambda c: c["distancia_m"])
            nearest = candidatos[0]
            # Prefiere una marca reconocible si está razonablemente cerca (mejor destino para el usuario).
            marca = next((c for c in candidatos
                          if _es_marca(c["nombre"]) and c["distancia_m"] <= nearest["distancia_m"] + _MARGEN_MARCA_M), None)
            return marca or nearest
    except Exception:  # noqa: BLE001
        pass
    return None


async def _mejor_transporte(lat: float, lon: float, key: str) -> dict | None:
    """
    Prioriza el hub MASIVO (Metro/tren) aunque haya una parada de bus más cerca.
    Marca es_masivo para NO confundir un Metro con una simple parada de bus.
    """
    metro = await _nearest_categoria(lat, lon, "transporte", key,
                                     tipos=["subway_station", "train_station", "light_rail_station"])
    if metro:
        metro["es_masivo"] = True
        return metro
    bus = await _nearest_categoria(lat, lon, "transporte", key, tipos=["bus_station", "transit_station"])
    if bus:
        bus["es_masivo"] = False
    return bus
