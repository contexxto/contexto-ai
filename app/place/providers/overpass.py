"""Overpass: SOLO el I/O contra OpenStreetMap. La caminabilidad NO se calcula aqui.

LA LINEA, Y POR QUE ESTA EXACTAMENTE AHI. Este modulo trae POIs. El puntaje de
caminabilidad, la conectividad, los pesos por categoria, el decaimiento por distancia y la
clasificacion de hubs se quedan en `app/walk_score.py`, que es donde viven porque son
METODO DE CONTEXTO, no respuesta de un tercero.

No es una preferencia de estilo: es una decision ya adjudicada en PLAN04-1.2 y escrita en
`app/place/assembler.py`. Alli la caminabilidad emite DOS evidencias, no una — el puntaje
con `provider="contexto"` y los insumos con `provider="overpass"`— justamente porque
atribuir el numero a Overpass borraba de quien era el metodo. Mover `walk_score_para` o
`compute_walk_score` a este fichero volveria a cometer ese error, esta vez en la
estructura de directorios. El proveedor obtiene datos; Contexto calcula.

QUE SE MOVIO. `_fetch_pois` y las constantes de su llamada: los mirrors, el radio de la
consulta y el plazo. La query, el orden de intento de los mirrors, el `User-Agent`, el
filtrado de elementos y el regreso a `None` cuando TODOS los mirrors fallan son los de
siempre, sin tocar.

SOBRE `_TIMEOUT`. Es el plazo de esta llamada HTTP, pero ademas es el valor por defecto de
`walk_score_para`, que se queda en `app/walk_score.py` y lo unico que hace con el es
reenviarlo aqui. Viaja con el I/O y `walk_score.py` lo reimporta, para que exista UN solo
plazo y no dos copias que se separen sin que nadie se entere.

DEGRADACION, TAL CUAL ESTABA: si un mirror falla se prueba el siguiente; si fallan todos
se devuelve `None`. `None` NO significa "no hay nada alrededor" —eso es una lista vacia—
sino "el proveedor no contesto", y de esa diferencia depende que `PlaceContextV0` emita
`insufficient_evidence` en vez de un cero con pinta de medicion.
"""

from __future__ import annotations

import httpx

from app.config import settings

# Endpoints públicos de Overpass (probamos en orden si uno falla).
_OVERPASS_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
_RADIUS_M = 1600          # ~1 milla: cobertura de caminabilidad
_TIMEOUT = 6.0            # corto: el publish no debe colgarse en una API externa


async def _fetch_pois(lat: float, lon: float, timeout: float = _TIMEOUT) -> list[dict] | None:
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
            async with httpx.AsyncClient(verify=verify, timeout=timeout) as c:
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
