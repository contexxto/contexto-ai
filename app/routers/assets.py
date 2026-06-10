import asyncio
import io
import uuid

import segno
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import Response
from geoalchemy2.elements import WKTElement
from geopy.geocoders import Nominatim
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, get_current_user
from app.config import settings
from app.database import AsyncSessionLocal, get_db
from app.models import ActivoInmutable
from app.schemas import ActivoCreateRequest, ActivoResponse
from app.scores_heuristicos import scores_para
from app.walk_score import walk_score_para

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
                "       a.conectividad, "
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
                "conectividad": r["conectividad"],
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
                "       a.volumen_trafico_historico AS trafico, a.conectividad, a.imagen_url, "
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
            "trafico": r["trafico"], "conectividad": r["conectividad"], "imagen_url": r["imagen_url"],
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


@router.get(
    "/{activo_id}/qr.svg",
    summary="QR del letrero inteligente (enlace permanente al inmueble)",
    description=(
        "Genera el código QR (SVG) que codifica el enlace profundo al inmueble "
        "({app}/a/{id}). Al escanearlo, el usuario abre el agente con ese activo "
        "cargado. Pensado para imprimir en letreros de arriendo/venta."
    ),
)
async def asset_qr(activo_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Response:
    exists = (
        await db.execute(
            text("SELECT 1 FROM activos_inmutables WHERE id = :id"),
            {"id": str(activo_id)},
        )
    ).first()
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activo no encontrado.")

    url = f"{settings.public_app_url.rstrip('/')}/a/{activo_id}"
    qr = segno.make(url, error="h")  # alta corrección → tolera desgaste del letrero
    buff = io.BytesIO()
    qr.save(buff, kind="svg", scale=8, border=2, dark="#0E0D13", light="#ffffff")
    return Response(content=buff.getvalue(), media_type="image/svg+xml")


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


# ── Publicar mi inmueble (propietario particular o corredor) ────────────────
class PublishRequest(BaseModel):
    direccion: str = Field(..., min_length=5, max_length=255)
    tipo_activo: str = Field(default="Departamento")
    operacion: str = Field(..., description="arriendo | venta")
    precio: float | None = Field(default=None, ge=0)
    piso_altura: int = Field(default=1, ge=1, le=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


async def _geocode(direccion: str) -> tuple[float, float] | None:
    """Geocodifica una dirección de Quito vía Nominatim (best-effort)."""
    def _sync(q: str):
        return Nominatim(user_agent="contexto_ai_v2", timeout=8).geocode(q, language="es")
    for q in dict.fromkeys([
        f"{direccion.strip()}, Quito, Ecuador",
        f"{direccion.strip()}, Ecuador",
        f"{direccion.split(' y ')[0].strip()}, Quito, Ecuador",
    ]):
        try:
            loc = await asyncio.get_event_loop().run_in_executor(None, _sync, q)
        except Exception:  # noqa: BLE001
            loc = None
        if loc:
            return round(loc.latitude, 6), round(loc.longitude, 6)
    return None


async def _recompute_walk_score(asset_id: str, lat: float, lon: float) -> None:
    """
    Recalcula el Walk Score REAL (OSM) en segundo plano y actualiza el activo.
    Presupuesto generoso (20s) porque ya NO bloquea la respuesta al usuario:
    Render puede tardar más que en local en alcanzar Overpass. Idempotente y
    silencioso ante fallos (si Overpass no responde, se queda el heurístico).
    """
    try:
        ws = await walk_score_para(lat, lon, timeout=20.0)
        if ws is None:
            return
        conect = (ws.get("conectividad") or {}).get("texto")
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("UPDATE activos_inmutables SET walk_score = :w, conectividad = :c WHERE id = :id"),
                {"w": ws["walk_score"], "c": conect, "id": asset_id},
            )
            await session.commit()
    except Exception:  # noqa: BLE001 — best-effort; nunca debe tumbar nada
        pass


@router.post(
    "/publish",
    status_code=status.HTTP_201_CREATED,
    summary="Publicar mi inmueble (cualquier usuario autenticado)",
    description=(
        "Permite a un propietario particular o corredor publicar su inmueble sin "
        "intermediarios. Asigna scores heurísticos por zona, geocodifica si no se "
        "envían coordenadas, liga el activo a su dueño y registra la operación/precio. "
        "Devuelve el id y el enlace del QR para el letrero."
    ),
)
async def publish_asset(
    payload: PublishRequest,
    background: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # 1) Coordenadas: usar las provistas o geocodificar la dirección.
    lat, lon = payload.latitude, payload.longitude
    if lat is None or lon is None:
        geo = await _geocode(payload.direccion)
        if not geo:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No pudimos ubicar la dirección. Revísala o comparte tu ubicación (lat/lon).",
            )
        lat, lon = geo

    # 2) Scores heurísticos por zona (capa base, refinable con visión).
    sc = scores_para(payload.direccion, payload.tipo_activo)
    sc["walk_score_fuente"] = "heuristico"

    # 2b) Walk Score REAL desde OpenStreetMap (foso de datos). Intento inline
    #     CORTO (5s): si Overpass responde rápido, el usuario ve el score real
    #     de una vez. Si no, no bloqueamos: se queda el heurístico y un job en
    #     segundo plano lo recalcula con presupuesto mayor (ver más abajo).
    conectividad_txt: str | None = None
    try:
        ws = await asyncio.wait_for(walk_score_para(lat, lon, timeout=5.0), timeout=6)
    except Exception:  # noqa: BLE001 — timeout o red: caemos al heurístico
        ws = None
    if ws is not None:
        sc["walk_score"] = ws["walk_score"]
        sc["walk_score_fuente"] = ws["fuente"]
        sc["walk_score_desglose"] = ws["desglose"]
        conectividad_txt = (ws.get("conectividad") or {}).get("texto")

    aid = uuid.uuid4()
    asset = ActivoInmutable(
        id=aid,
        geom=WKTElement(f"POINT({lon} {lat})", srid=4326),
        direccion_estandarizada=payload.direccion.strip(),
        piso_altura=payload.piso_altura,
        walk_score=sc["walk_score"],
        score_ruido_predictivo=sc["score_ruido_predictivo"],
        porcentaje_cobertura_vegetal=sc["porcentaje_cobertura_vegetal"],
        tipo_activo=payload.tipo_activo,
    )
    db.add(asset)
    await db.flush()

    # 3) Ligar al dueño y registrar la operación/precio (transitorio).
    #    Los CHECK de la tabla exigen MAYÚSCULAS (ARRIENDO/VENTA, ACTIVO).
    op_norm = (payload.operacion or "").strip().upper()
    if op_norm not in ("ARRIENDO", "VENTA", "MONITOREO_PASIVO"):
        op_norm = "ARRIENDO"
    await db.execute(
        text("UPDATE activos_inmutables SET owner_user_id = :u, owner_agency_id = :a, "
             "conectividad = :c WHERE id = :id"),
        {"u": user.user_id, "a": user.agency_id, "c": conectividad_txt, "id": str(aid)},
    )
    await db.execute(
        text(
            "INSERT INTO transacciones_temporales (id, activo_id, tipo_operacion, precio, estado_anuncio) "
            "VALUES (:tid, :aid, :op, :precio, 'ACTIVO')"
        ),
        {"tid": str(uuid.uuid4()), "aid": str(aid), "op": op_norm, "precio": payload.precio},
    )
    await db.commit()

    # 4) Si el intento inline no consiguió el Walk Score real, recalcularlo en
    #    segundo plano (sin hacer esperar al usuario, que ya tiene su QR).
    if sc.get("walk_score_fuente") != "osm":
        background.add_task(_recompute_walk_score, str(aid), lat, lon)

    return {
        "id": str(aid),
        "direccion": payload.direccion.strip(),
        "scores": sc,
        "conectividad": conectividad_txt,
        "deep_link": f"{settings.public_app_url.rstrip('/')}/a/{aid}",
    }
