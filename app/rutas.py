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
        # Primero Metro/tren/terminal (héroe de plusvalía); si no hay, bus.
        for tipos_t in (["subway_station", "train_station", "light_rail_station"], ["bus_station", "transit_station"]):
            if "transporte" in mejor:
                break
            try:
                tbody = {
                    "includedTypes": tipos_t, "maxResultCount": 5, "rankPreference": "DISTANCE",
                    "languageCode": "es",
                    "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": 3000.0}},
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


# ── Mapa conversacional: pregunta → acciones de mapa ────────────────────────
_PALABRAS_CAT = {
    "transporte": ["metro", "estacion", "estación", "terminal", "parada", "bus", "transporte"],
    "educacion": ["colegio", "escuela", "educacion", "educación", "universidad", "guarderia", "guardería"],
    "salud": ["hospital", "salud", "clinica", "clínica", "consultorio", "medico", "médico", "doctor"],
    "farmacia": ["farmacia", "botica"],
    "supermercado": ["super", "mercado", "supermercado", "tienda", "abasto", "víveres", "viveres"],
    "parque": ["parque", "area verde", "área verde", "verde", "jardin", "jardín"],
    "iglesia": ["iglesia", "templo", "misa", "parroquia"],
    "seguridad": ["upc", "policia", "policía", "seguridad", "patrulla"],
    "centro_comercial": ["centro comercial", "mall", "quicentro", "comercial"],
}
_CAT_GOOGLE = {c["key"]: [c["google"]] for c in _CATEGORIAS}
_CAT_GOOGLE["transporte"] = ["subway_station", "train_station", "bus_station", "transit_station"]
_CAT_LABEL = {
    "transporte": "🚇 transporte", "educacion": "🏫 educación", "salud": "🏥 salud",
    "farmacia": "💊 farmacia", "supermercado": "🛒 supermercado", "parque": "🌳 parque",
    "iglesia": "⛪ iglesia", "seguridad": "🛡️ seguridad", "centro_comercial": "🛍️ centro comercial",
}


async def _nearest_categoria(lat: float, lon: float, cat: str, key: str) -> dict | None:
    body = {
        "includedTypes": _CAT_GOOGLE.get(cat, []), "maxResultCount": 8, "rankPreference": "DISTANCE",
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
            for pl in r.json().get("places", []):
                loc = pl.get("location", {})
                nombre = (pl.get("displayName") or {}).get("text")
                if "latitude" in loc and _nombre_valido(nombre):
                    return {"nombre": nombre, "lat": loc["latitude"], "lon": loc["longitude"],
                            "distancia_m": int(_haversine_m(lat, lon, loc["latitude"], loc["longitude"]))}
    except Exception:  # noqa: BLE001
        pass
    return None


async def comando_mapa(pregunta: str, lat: float, lon: float) -> dict:
    """Interpreta una pregunta y devuelve {texto, acciones} para que el mapa reaccione."""
    key = settings.google_maps_api_key
    if not key:
        return {"texto": "El mapa interactivo necesita Google Maps activo.", "acciones": []}
    p = (pregunta or "").lower()

    # 1) ¿Pide una ruta a una categoría?
    cat = next((c for c, kws in _PALABRAS_CAT.items() if any(k in p for k in kws)), None)
    if cat:
        dest = await _nearest_categoria(lat, lon, cat, key)
        if not dest:
            return {"texto": f"No encontré {_CAT_LABEL.get(cat, cat)} cerca de ese punto.", "acciones": []}
        try:
            async with httpx.AsyncClient(verify=settings.ssl_verify.lower() != "false", timeout=_TIMEOUT) as c:
                ruta = await _ruta_a_pie(c, lat, lon, dest["lat"], dest["lon"], key)
        except Exception:  # noqa: BLE001
            ruta = None
        if ruta and ruta.get("coords"):
            etiqueta = f"🚶 {ruta['duracion_min']} min · {dest['nombre']}"
            return {
                "texto": f"Ilumino la ruta a **{dest['nombre']}**: {ruta['duracion_min']} min a pie ({ruta['distancia_m']} m).",
                "acciones": [{"tipo": "ruta", "coords": ruta["coords"], "destino": [dest["lon"], dest["lat"]],
                              "etiqueta": etiqueta, "color": "#5EEAD4"}],
            }
        return {"texto": f"Encontré {dest['nombre']} a {dest['distancia_m']} m, pero no pude trazar la ruta.",
                "acciones": [{"tipo": "puntos", "items": [{"coords": [dest["lon"], dest["lat"]], "etiqueta": dest["nombre"]}], "color": "#5EEAD4"}]}

    # 2) ¿Pide ver lo que hay alrededor?
    if any(k in p for k in ["cerca", "servicios", "que hay", "qué hay", "alrededor", "entorno", "rodea"]):
        servicios = await _servicios_con_coords(lat, lon, key, 6)
        if not servicios:
            return {"texto": "No encontré servicios mapeados en este punto.", "acciones": []}
        items = [{"coords": [s["lon"], s["lat"]], "etiqueta": f"{s['nombre']} ({s['distancia_m']} m)"} for s in servicios]
        return {"texto": "Enciendo los servicios cercanos en el mapa.", "acciones": [{"tipo": "puntos", "items": items, "color": "#5EEAD4"}]}

    # 3) Fallback: guía
    return {"texto": "Pídeme algo como *“ruta al Metro”*, *“colegio más cercano”* o *“qué hay cerca”* y lo ilumino en el mapa.",
            "acciones": []}


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
