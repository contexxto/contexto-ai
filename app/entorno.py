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

import re


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
    # Rótulo: el SERVICIO (la UPC es un lugar con dirección), no la cualidad del barrio.
    # "Seguridad" a secas se lee como "¿es seguro aquí?", que el canon Fair Housing
    # prohíbe afirmar. Ver migración 021.
    {"key": "seguridad", "emoji": "🛡️", "label": "UPC (policía comunitaria)",
     "osm": lambda t: t.get("amenity") == "police", "google": "police"},
    {"key": "parque", "emoji": "🌳", "label": "Parque",
     "osm": lambda t: t.get("leisure") in {"park", "garden"}, "google": "park"},
    {"key": "supermercado", "emoji": "🛒", "label": "Supermercado",
     "osm": lambda t: t.get("shop") == "supermarket", "google": "supermarket"},
    {"key": "farmacia", "emoji": "💊", "label": "Farmacia",
     "osm": lambda t: t.get("amenity") == "pharmacy" or t.get("shop") == "chemist", "google": "pharmacy"},
]


# Nombres-placeholder de OSM/Google que no aportan (ej. "ID 1906", solo números).
_PLACEHOLDER = re.compile(r"^(id\s*\d+|sin\s*nombre|\d+|área\s*verde.*\d+)$", re.I)

# Etiquetas personales/genéricas que la gente registra en mapas y NO son destinos
# reales (ej. alguien fija "TRABAJO" o "CASA" en Google Maps y se filtra como POI).
_GENERICOS = {
    "trabajo", "casa", "mi casa", "mi trabajo", "hogar", "oficina", "mi oficina",
    "local", "departamento", "depto", "tienda", "negocio", "edificio", "lote",
    "terreno", "domicilio", "aqui", "aquí",
}


def _nombre_valido(nombre: str | None) -> bool:
    if not nombre:
        return False
    n = nombre.strip()
    return not _PLACEHOLDER.match(n) and n.casefold() not in _GENERICOS


# Limpieza al SERVIR (no depende de recalcular): quita segmentos cuyo nombre sea
# genérico/basura de un texto YA formateado tipo
# "🛍️ TRABAJO a ~257 m · 💊 Farmacia X a ~62 m".
_SEG_SUFIJO = re.compile(r"\s*a\s*~?\s*[\d.,]+\s*m\.?$", re.I)
_SEG_PREFIJO = re.compile(r"^[^0-9A-Za-zÁÉÍÓÚÑÜáéíóúñü]+")  # emojis/símbolos iniciales


def limpiar_texto_servicios(texto: str | None) -> str | None:
    """Filtra POIs basura (nombres genéricos) de un texto de servicios ya guardado."""
    if not texto:
        return texto
    out = []
    for seg in (s.strip() for s in texto.split("·")):
        if not seg:
            continue
        nombre = _SEG_PREFIJO.sub("", _SEG_SUFIJO.sub("", seg)).strip()
        if _nombre_valido(nombre):
            out.append(seg)
    return " · ".join(out) if out else None


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
            if not _nombre_valido(tags.get("name")) or not cat["osm"](tags):
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

# ── La llamada a Google Places vive ahora en `app/place/providers/google.py` (PLAN04-2.2)
# Se MOVIO, no se copio: aqui no queda un segundo cuerpo. Con ella viajaron su radio y su
# plazo, que eran suyos y de nadie mas, y alli llevan prefijo propio para que no puedan
# confundirse con los de la operacion del Place path.
#
# LO QUE SE QUEDA ES LA ELECCION. `entorno_destacado` decide entre Google y OSM, y eso es
# politica de seleccion entre dos proveedores: nunca vive dentro de un proveedor. Y
# `extraer_entorno_osm` y `_formatear` se quedan porque son calculo y presentacion sobre
# POIs ya descargados, no I/O.
#
# EL IMPORT ES DIFERIDO A PROPOSITO, y no por estilo: `app/place/providers/google.py`
# importa de ESTE modulo su taxonomia (`_CATEGORIAS`, `_nombre_valido`, `_formatear`). Un
# import de nivel de modulo en esta direccion cerraria el ciclo. Se resuelve en el punto de
# uso, en cada llamada, y hay prueba de que el ciclo no existe.


async def entorno_destacado(lat: float, lon: float, pois: list[dict] | None) -> dict | None:
    """
    Entorno destacado del inmueble. Usa Google Places si hay API key (en vivo);
    si no, o si Google falla, cae a OSM (con los POIs ya descargados). None si
    no hay nada que destacar.
    """
    if settings.google_maps_api_key:
        from app.place.providers.google import _entorno_google  # diferido: evita ciclo
        g = await _entorno_google(lat, lon, settings.google_maps_api_key)
        if g is not None:
            return g
    if pois:
        return extraer_entorno_osm(pois, lat, lon)
    return None
