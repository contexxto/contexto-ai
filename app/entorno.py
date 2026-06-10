"""
Entorno destacado de un inmueble — los "imanes de vida" cercanos que hacen
fabuloso un informe: centro comercial, colegios, iglesia, UPC (seguridad),
salud, parques, supermercado, farmacia. Con nombre y distancia.

Estrategia de fuentes (decisión del producto):
- GOOGLE MAPS PLACES (primario, si hay API key): nombres ricos y completos.
  Se usa EN VIVO; por términos de Google no se persiste su contenido a largo
  plazo más allá de lo permitido.
- OPENSTREETMAP (respaldo y base persistible del catastro): gratis, propio,
  reutiliza los POIs que ya descargamos para el Walk Score.

`extraer_entorno_osm(pois, lat, lon)` es PURA (sin red) → testeable.
`entorno_destacado(lat, lon, pois)` decide la fuente y devuelve el texto.
"""
from __future__ import annotations

import asyncio

import httpx

from app.config import settings
from app.walk_score import _haversine_m

# Categorías de "imanes de vida": etiqueta + emoji + matcher OSM + tipo Google.
# Orden = prioridad de presentación.
_CATEGORIAS: list[dict] = [
    {"key": "centro_comercial", "emoji": "🛍️", "label": "Centro comercial",
     "osm": lambda t: t.get("shop") == "mall", "google": "shopping_mall"},
    {"key": "educacion", "emoji": "🏫", "label": "Educación",
     "osm": lambda t: t.get("amenity") in {"school", "college", "university", "kindergarten"}, "google": "school"},
    {"key": "salud", "emoji": "🏥", "label": "Salud",
     "osm": lambda t: t.get("amenity") in {"hospital", "clinic", "doctors"}, "google": "hospital"},
    {"key": "iglesia", "emoji": "⛪", "label": "Iglesia",
     "osm": lambda t: t.get("amenity") == "place_of_worship", "google": "church"},
    {"key": "seguridad", "emoji": "🛡️", "label": "Seguridad (UPC)",
     "osm": lambda t: t.get("amenity") == "police", "google": "police"},
    {"key": "parque", "emoji": "🌳", "label": "Parque",
     "osm": lambda t: t.get("leisure") in {"park", "garden"}, "google": "park"},
    {"key": "supermercado", "emoji": "🛒", "label": "Supermercado",
     "osm": lambda t: t.get("shop") == "supermarket", "google": "supermarket"},
    {"key": "farmacia", "emoji": "💊", "label": "Farmacia",
     "osm": lambda t: t.get("amenity") == "pharmacy" or t.get("shop") == "chemist", "google": "pharmacy"},
]
_RADIO_M = 1200
_TIMEOUT = 6.0


def _formatear(items: list[dict]) -> str:
    """items: [{emoji,label,nombre,distancia_m}] → texto compacto."""
    partes = [f"{i['emoji']} {i['nombre'] or i['label']} a ~{i['distancia_m']} m" for i in items]
    return " · ".join(partes)


def extraer_entorno_osm(pois: list[dict], lat: float, lon: float, max_items: int = 8) -> dict | None:
    """De los POIs ya descargados, el más cercano CON NOMBRE por categoría. PURA."""
    items: list[dict] = []
    for cat in _CATEGORIAS:
        mejor = None
        for p in pois:
            tags = p.get("tags") or {}
            if not tags.get("name") or not cat["osm"](tags):
                continue
            d = _haversine_m(lat, lon, p["lat"], p["lon"])
            if mejor is None or d < mejor[0]:
                mejor = (d, tags["name"])
        if mejor:
            items.append({"key": cat["key"], "emoji": cat["emoji"], "label": cat["label"],
                          "nombre": mejor[1], "distancia_m": int(mejor[0])})
    if not items:
        return None
    items.sort(key=lambda i: i["distancia_m"])
    items = items[:max_items]
    return {"fuente": "osm", "items": items, "texto": _formatear(items)}


async def _google_nearest(client, cat: dict, lat: float, lon: float, key: str) -> dict | None:
    """El lugar más cercano de UNA categoría vía Places API (New)."""
    body = {
        "includedTypes": [cat["google"]],
        "maxResultCount": 5,
        "rankPreference": "DISTANCE",
        "languageCode": "es",
        "locationRestriction": {
            "circle": {"center": {"latitude": lat, "longitude": lon}, "radius": float(_RADIO_M)}
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "places.displayName,places.location",
    }
    resp = await client.post("https://places.googleapis.com/v1/places:searchNearby",
                             json=body, headers=headers)
    resp.raise_for_status()
    mejor = None
    for pl in resp.json().get("places", []):
        loc = pl.get("location", {})
        if "latitude" not in loc:
            continue
        d = _haversine_m(lat, lon, loc["latitude"], loc["longitude"])
        if mejor is None or d < mejor[0]:
            mejor = (d, (pl.get("displayName") or {}).get("text"))
    if mejor is None:
        return None
    return {"key": cat["key"], "emoji": cat["emoji"], "label": cat["label"],
            "nombre": mejor[1], "distancia_m": int(mejor[0])}


async def _entorno_google(lat: float, lon: float, key: str, max_items: int = 8) -> dict | None:
    """
    Enriquecimiento EN VIVO con la Places API (New) — compatible con la Clave de
    Demo de Maps. Una llamada POR categoría (el más cercano), así garantizamos
    colegio, UPC, etc. aunque haya muchas tiendas más cerca.
    """
    verify = settings.ssl_verify.lower() != "false"
    async with httpx.AsyncClient(verify=verify, timeout=_TIMEOUT) as c:
        resultados = await asyncio.gather(
            *[_google_nearest(c, cat, lat, lon, key) for cat in _CATEGORIAS],
            return_exceptions=True,
        )
    items = [r for r in resultados if isinstance(r, dict)]
    if not items:
        return None  # todas fallaron o sin resultados → el llamador cae a OSM
    items.sort(key=lambda i: i["distancia_m"])
    items = items[:max_items]
    return {"fuente": "google", "items": items, "texto": _formatear(items)}


async def entorno_destacado(lat: float, lon: float, pois: list[dict] | None) -> dict | None:
    """
    Entorno destacado del inmueble. Usa Google Places si hay API key (en vivo);
    si no, o si Google falla, cae a OSM (con los POIs ya descargados). None si
    no hay nada que destacar.
    """
    if settings.google_maps_api_key:
        g = await _entorno_google(lat, lon, settings.google_maps_api_key)
        if g is not None:
            return g
    if pois:
        return extraer_entorno_osm(pois, lat, lon)
    return None
