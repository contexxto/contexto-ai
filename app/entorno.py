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


def extraer_entorno_osm(pois: list[dict], lat: float, lon: float, max_items: int = 6) -> dict | None:
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


async def _entorno_google(lat: float, lon: float, key: str, max_items: int = 6) -> dict | None:
    """
    Enriquecimiento EN VIVO con la Places API (New) — compatible con la Clave de
    Demo de Maps (gratis, sandbox). Una sola llamada: searchNearby con todos los
    tipos, ordenado por distancia; luego el más cercano por categoría.
    """
    url = "https://places.googleapis.com/v1/places:searchNearby"
    verify = settings.ssl_verify.lower() != "false"
    body = {
        "includedTypes": [c["google"] for c in _CATEGORIAS],
        "maxResultCount": 20,
        "rankPreference": "DISTANCE",
        "languageCode": "es",
        "locationRestriction": {
            "circle": {"center": {"latitude": lat, "longitude": lon}, "radius": float(_RADIO_M)}
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "places.displayName,places.location,places.types",
    }
    try:
        async with httpx.AsyncClient(verify=verify, timeout=_TIMEOUT) as c:
            resp = await c.post(url, json=body, headers=headers)
            resp.raise_for_status()
            places = resp.json().get("places", [])
    except Exception:  # noqa: BLE001 — si Google falla, el llamador cae a OSM
        return None

    # Más cercano por categoría (un lugar puede traer varios "types").
    mejor: dict[str, tuple] = {}
    for pl in places:
        loc = pl.get("location", {})
        if "latitude" not in loc:
            continue
        tipos = pl.get("types", [])
        nombre = (pl.get("displayName") or {}).get("text")
        d = _haversine_m(lat, lon, loc["latitude"], loc["longitude"])
        for cat in _CATEGORIAS:
            if cat["google"] in tipos:
                if cat["key"] not in mejor or d < mejor[cat["key"]][0]:
                    mejor[cat["key"]] = (d, nombre, cat)
                break
    if not mejor:
        return None

    items = [{"key": cat["key"], "emoji": cat["emoji"], "label": cat["label"],
              "nombre": nombre, "distancia_m": int(d)} for (d, nombre, cat) in mejor.values()]
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
