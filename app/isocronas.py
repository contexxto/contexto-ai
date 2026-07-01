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
import logging

import httpx
from sqlalchemy import text

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 20.0
_CONTORNOS_DEFECTO = (15, 30)  # minutos


async def isocrona(lat: float, lon: float, minutos=_CONTORNOS_DEFECTO) -> list[dict] | None:
    """Isócrona peatonal de un punto. Devuelve [{minutos:int, geometry:GeoJSON}] o None.

    Un solo request cubre todos los contornos. polygons=true → polígonos cerrados
    aptos para point-in-polygon; denoise limpia islas sueltas; generalize simplifica.
    """
    body = {
        "locations": [{"lat": lat, "lon": lon}],
        "costing": "pedestrian",
        "contours": [{"time": int(m)} for m in minutos],
        "polygons": True,
        "denoise": 0.5,
        "generalize": 50,
    }
    verify = settings.ssl_verify.lower() != "false"
    try:
        async with httpx.AsyncClient(verify=verify, timeout=_TIMEOUT) as c:
            r = await c.post(f"{settings.valhalla_url}/isochrone", json=body)
            r.raise_for_status()
            fc = r.json()
    except Exception as exc:  # noqa: BLE001 — Valhalla caído → el llamador degrada
        # Degradamos, pero NO en silencio: el operador debe ver que Valhalla no responde
        # (mismo criterio que routers/assets.py con Google). Distingue "caído" de "vacío".
        logger.warning("Valhalla /isochrone no respondió (%s): %s", type(exc).__name__, exc)
        return None
    out: list[dict] = []
    for feat in fc.get("features", []):
        props = feat.get("properties", {}) or {}
        geom = feat.get("geometry")
        # Con metric='time', Valhalla marca el contorno en properties.contour (minutos).
        m = props.get("contour")
        if not geom or m is None:
            continue
        try:
            minutos_val = int(round(float(m)))
        except (TypeError, ValueError):
            continue  # contorno malformado → descarta la feature, nunca revienta
        out.append({"minutos": minutos_val, "geometry": geom})
    return out or None


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
