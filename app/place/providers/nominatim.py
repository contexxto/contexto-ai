"""Nominatim: coordenadas -> lugar legible. SOLO el geocodificado INVERSO (PLAN04-2.2).

POR QUE ESTABA EN EL SITIO EQUIVOCADO. `_reverse_geocode` vivia en `app/agent/tools.py`,
el modulo de las herramientas del agente, y NINGUNA herramienta la llamaba: sus tres
llamadores estan los tres en `app/rutas.py`. Era un proveedor de Place alojado en el
paquete del agente, y por eso `rutas.py` tenia que importarla de forma diferida.

ESTE MODULO NO ES "TODO NOMINATIM", Y LA DISTINCION IMPORTA. El repositorio llama a
Nominatim desde tres sitios y aqui vive UNO: el inverso. Siguen fuera, deliberadamente y
sin autorizacion para moverlos, el geocodificado DIRECTO de `tool_geocode_address`
(`app/agent/tools.py`, donde Nominatim es el respaldo de Google) y el de
`app/routers/assets.py`. Mismo criterio que con Google en esta misma extraccion: el
nombre comercial del proveedor no es la capacidad. Directo e inverso responden preguntas
opuestas, fallan por separado y tienen consumidores distintos.

SE MOVIO TAL CUAL. `user_agent`, timeout, idioma, zoom, `addressdetails`, el executor, el
regreso a `None` y la tupla de excepciones son los de siempre, byte a byte. Se anota una
sola cosa sin tocarla: `Exception` en esa tupla subsume a las dos de geopy, asi que esta
funcion se traga CUALQUIER fallo y lo convierte en `None`. Corregirlo seria cambiar
comportamiento y esta unidad no lo autoriza.
"""

from __future__ import annotations

import asyncio

from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from geopy.geocoders import Nominatim


async def _reverse_geocode(lat: float, lon: float) -> dict | None:
    """Coordenadas → lugar legible (barrio, ciudad, país). Funciona en todo el mundo."""
    def _sync():
        geo = Nominatim(user_agent="contexto_ai_v2", timeout=8)
        return geo.reverse((lat, lon), language="es", zoom=16, addressdetails=True)
    try:
        loc = await asyncio.get_event_loop().run_in_executor(None, _sync)
    except (GeocoderTimedOut, GeocoderUnavailable, Exception):  # noqa: BLE001
        return None
    if not loc:
        return None
    a = getattr(loc, "raw", {}).get("address", {}) or {}
    return {
        "texto": loc.address,
        "barrio": a.get("suburb") or a.get("neighbourhood") or a.get("quarter") or a.get("city_district"),
        "ciudad": a.get("city") or a.get("town") or a.get("municipality") or a.get("county"),
        "pais": a.get("country"),
    }
