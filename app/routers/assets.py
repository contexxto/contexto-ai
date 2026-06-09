import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from geoalchemy2.elements import WKTElement
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ActivoInmutable
from app.schemas import ActivoCreateRequest, ActivoResponse

router = APIRouter(prefix="/api/v1/assets", tags=["Assets — Catastro Inmutable"])


@router.get(
    "/geojson",
    summary="Catastro como GeoJSON (para el Mapa Vivo)",
    description=(
        "Devuelve todos los activos como una FeatureCollection GeoJSON, con sus "
        "métricas (ruido, walk score, vegetación, tipo, estado) como properties. "
        "Pensado para alimentar la vista de mapa del frontend."
    ),
)
async def assets_geojson(db: AsyncSession = Depends(get_db)) -> dict:
    rows = (
        await db.execute(
            text(
                "SELECT a.id::text AS id, a.direccion_estandarizada AS direccion, "
                "       a.tipo_activo, a.piso_altura, a.walk_score, "
                "       a.score_ruido_predictivo AS ruido, "
                "       a.porcentaje_cobertura_vegetal AS vegetacion, "
                "       a.volumen_trafico_historico AS trafico, "
                "       a.imagen_url, "
                "       ST_X(a.geom) AS lon, ST_Y(a.geom) AS lat, "
                "       f.estado_revision, f.confianza_extraccion "
                "FROM activos_inmutables a "
                "LEFT JOIN ficha_tecnica_mantenimiento f ON f.activo_id = a.id "
                "WHERE a.geom IS NOT NULL"
            )
        )
    ).mappings().all()

    features = []
    for r in rows:
        if r["lon"] is None or r["lat"] is None:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(r["lon"]), float(r["lat"])]},
            "properties": {
                "id": r["id"],
                "direccion": r["direccion"],
                "tipo_activo": r["tipo_activo"],
                "piso_altura": r["piso_altura"],
                "walk_score": r["walk_score"],
                "ruido": r["ruido"],
                "vegetacion": float(r["vegetacion"]) if r["vegetacion"] is not None else None,
                "trafico": r["trafico"],
                "imagen_url": r["imagen_url"],
                "estado_revision": r["estado_revision"],
                "confianza": float(r["confianza_extraccion"]) if r["confianza_extraccion"] is not None else None,
            },
        })

    return {"type": "FeatureCollection", "features": features}


@router.get(
    "/near",
    summary="¿Puedo vivir aquí? — activos cerca de un punto (radio)",
    description=(
        "Devuelve, como GeoJSON, los activos dentro de un radio (metros) de un punto "
        "(lat/lon) — pensado para la geolocalización del usuario. Ordenados por "
        "distancia. Filtro opcional por operación (arriendo/venta). Si no hay activos "
        "en el radio, devuelve una FeatureCollection vacía (cobertura honesta)."
    ),
)
async def assets_near(
    lat: float,
    lon: float,
    radius_m: int = 500,
    operacion: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    radius_m = max(50, min(radius_m, 5000))

    op_clause = ""
    params = {"lat": lat, "lon": lon, "radius": radius_m}
    if operacion:
        op_clause = (
            " AND EXISTS (SELECT 1 FROM transacciones_temporales t "
            "WHERE t.activo_id = a.id AND t.tipo_operacion ILIKE :op)"
        )
        params["op"] = operacion.strip()

    rows = (
        await db.execute(
            text(
                "SELECT a.id::text AS id, a.direccion_estandarizada AS direccion, "
                "       a.tipo_activo, a.piso_altura, a.walk_score, "
                "       a.score_ruido_predictivo AS ruido, "
                "       a.porcentaje_cobertura_vegetal AS vegetacion, "
                "       a.volumen_trafico_historico AS trafico, a.imagen_url, "
                "       ST_X(a.geom) AS lon, ST_Y(a.geom) AS lat, "
                "       f.estado_revision, "
                "       ROUND(ST_Distance(a.geom::geography, "
                "         ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)::numeric, 0) AS distancia_m "
                "FROM activos_inmutables a "
                "LEFT JOIN ficha_tecnica_mantenimiento f ON f.activo_id = a.id "
                "WHERE a.geom IS NOT NULL AND ST_DWithin(a.geom::geography, "
                "      ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius)"
                + op_clause +
                " ORDER BY distancia_m ASC"
            ),
            params,
        )
    ).mappings().all()

    features = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [float(r["lon"]), float(r["lat"])]},
        "properties": {
            "id": r["id"], "direccion": r["direccion"], "tipo_activo": r["tipo_activo"],
            "piso_altura": r["piso_altura"], "walk_score": r["walk_score"], "ruido": r["ruido"],
            "vegetacion": float(r["vegetacion"]) if r["vegetacion"] is not None else None,
            "trafico": r["trafico"], "imagen_url": r["imagen_url"],
            "estado_revision": r["estado_revision"],
            "distancia_m": int(r["distancia_m"]) if r["distancia_m"] is not None else None,
        },
    } for r in rows]

    return {
        "type": "FeatureCollection",
        "centro": {"lat": lat, "lon": lon, "radius_m": radius_m},
        "total": len(features),
        "features": features,
    }


@router.post(
    "/",
    response_model=ActivoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar nuevo activo inmutable",
    description="Inscribe una coordenada física permanente en el Catastro Vivo.",
)
async def create_asset(
    payload: ActivoCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> ActivoResponse:
    point_wkt = WKTElement(
        f"POINT({payload.longitude} {payload.latitude})",
        srid=4326,
    )

    asset = ActivoInmutable(
        id=uuid.uuid4(),
        geom=point_wkt,
        direccion_estandarizada=payload.direccion_estandarizada,
        piso_altura=payload.piso_altura,
        walk_score=payload.walk_score,
        score_ruido_predictivo=payload.score_ruido_predictivo,
        porcentaje_cobertura_vegetal=payload.porcentaje_cobertura_vegetal,
        tipo_activo=payload.tipo_activo,
    )

    db.add(asset)
    await db.flush()
    await db.refresh(asset)

    return ActivoResponse(
        id=asset.id,
        direccion_estandarizada=asset.direccion_estandarizada,
        piso_altura=asset.piso_altura,
        walk_score=asset.walk_score,
        score_ruido_predictivo=asset.score_ruido_predictivo,
        porcentaje_cobertura_vegetal=float(asset.porcentaje_cobertura_vegetal) if asset.porcentaje_cobertura_vegetal else None,
        tipo_activo=asset.tipo_activo,
        created_at=asset.created_at,
    )
