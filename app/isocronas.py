"""
Isócronas peatonales EN VIVO con Valhalla auto-hospedado (Ladrillo #7 del foso).

Valhalla corre en Docker (ghcr.io/valhalla/valhalla-scripted) con los tiles de
Ecuador; expone POST /isochrone. Este módulo:
  - pide la isócrona peatonal de un punto (uno o varios contornos, en minutos),
  - la cachea por inmueble en isocronas_inmueble (inventario FIJO → se computa 1 vez),
  - y resuelve la CUÑA: búsqueda por ancla+tiempo (isócrona del ancla EN VIVO →
    ST_Contains filtra el inventario fijo). Ver docs/SPEC_Foso_Capa_de_Datos.md §2.

Sin API keys: es propio (Google TOS prohíbe almacenar isócronas; ODbL de OSM no).
Si Valhalla no está arriba, isocrona() devuelve None y los llamadores degradan (el
mapa no pinta isócronas; la cuña puede caer a radio euclidiano).
"""
from __future__ import annotations

import json

from sqlalchemy import text

# ── La llamada a Valhalla vive ahora en `app/place/providers/valhalla.py` (PLAN04-2.2) ──
# Se MOVIO, no se copio: aqui no queda un segundo cuerpo de `isocrona`. Con ella viajaron su
# plazo, su contorno por defecto y su logger, que eran suyos y de nadie mas.
#
# LO QUE SE QUEDA, Y POR QUE. La persistencia y la CUNA. `guardar_isocronas_inmueble` escribe
# el upsert idempotente sobre `isocronas_inmueble`; `buscar_por_ancla_tiempo` cruza el
# poligono con el inventario fijo por `ST_Contains`. Ninguna de las dos es una llamada a
# Valhalla: una guarda lo que el proveedor trajo y la otra lo usa para filtrar. El proveedor
# obtiene el poligono; lo que se hace con el es nuestro.
#
# Este modulo ya no importa `httpx` ni `settings`: eran exclusivos de la llamada y se fueron
# con ella. Conserva `json` y `text`, que usan las dos funciones de arriba.
#
# POR QUE ESTE IMPORT ES EL SEAM. `buscar_por_ancla_tiempo` resuelve `isocrona` en ESTE
# espacio de nombres, y `app/routers/assets.py` la importa de forma DIFERIDA desde aqui, asi
# que parchear `app.isocronas.isocrona` sigue alcanzando a los dos. `app/rutas.py`, que la
# importo a nivel de modulo, sigue ligandola en el suyo y no se toca.
from app.place.providers.valhalla import (  # noqa: E402,F401 — fachada
    _CONTORNOS_DEFECTO,
    _TIMEOUT,
    isocrona,
    logger,
)

_UPSERT_ISOCRONA = text("""
    INSERT INTO isocronas_inmueble (activo_id, minutos, geom)
    VALUES (:activo_id, :minutos,
            ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326)))
    ON CONFLICT (activo_id, minutos)
    DO UPDATE SET geom = EXCLUDED.geom, generado_en = now()
""")


async def guardar_isocronas_inmueble(conn, activo_id, features: list[dict]) -> int:
    """Upsert de las isócronas de un inmueble (inventario fijo). Devuelve nº guardadas."""
    n = 0
    for f in features:
        await conn.execute(_UPSERT_ISOCRONA, {
            "activo_id": str(activo_id),
            "minutos": f["minutos"],
            "geojson": json.dumps(f["geometry"]),
        })
        n += 1
    return n


_WEDGE_SQL = text("""
    WITH ancla AS (
        SELECT ST_SetSRID(ST_GeomFromGeoJSON(:ancla_geojson), 4326) AS poly,
               ST_SetSRID(ST_MakePoint(:ancla_lon, :ancla_lat), 4326) AS pt
    )
    SELECT a.id::text AS id, a.direccion_estandarizada AS direccion,
           ROUND(ST_Distance(a.geom::geography, ancla.pt::geography))::int AS metros_al_ancla
    FROM activos_inmutables a, ancla
    WHERE a.geom IS NOT NULL AND ST_Contains(ancla.poly, a.geom)
    ORDER BY metros_al_ancla ASC
""")


async def buscar_por_ancla_tiempo(conn, ancla_lat: float, ancla_lon: float,
                                  minutos: int = 30) -> list[dict] | None:
    """La CUÑA: inventario a ≤ `minutos` a pie del ancla (trabajo/colegio del usuario).

    El ancla NO está pre-computada → 1 llamada en vivo a /isochrone; con su polígono,
    ST_Contains filtra el inventario fijo. Devuelve inmuebles ordenados por cercanía al
    ancla, o None si Valhalla no está disponible (el llamador puede caer a radio recto).
    Point-in-polygon sobre pocos miles de puntos es trivial; el valor es que respeta la
    topografía/tráfico de Quito, donde el radio euclidiano miente.
    """
    isos = await isocrona(ancla_lat, ancla_lon, [minutos])
    if not isos:
        return None
    poly = isos[0]["geometry"]
    filas = (await conn.execute(_WEDGE_SQL, {
        "ancla_geojson": json.dumps(poly),
        "ancla_lat": ancla_lat, "ancla_lon": ancla_lon,
    })).mappings().all()
    return [dict(f) for f in filas]
