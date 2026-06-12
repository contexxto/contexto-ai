import asyncio
import io
import json
import uuid

import segno
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import Response
from geoalchemy2.elements import WKTElement
from geopy.geocoders import Nominatim
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, get_current_user
from app.config import settings
from app.database import AsyncSessionLocal, get_db
from app.limiter import limiter
from app.models import ActivoInmutable
from app.schemas import ActivoCreateRequest, ActivoResponse
from app.entorno import entorno_destacado
from app.scores_heuristicos import scores_para
from app.walk_score import (
    _fetch_pois,
    compute_walk_score,
    extraer_conectividad,
    walk_score_para,
)

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
@limiter.limit("60/minute")
async def assets_geojson(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    rows = (
        await db.execute(
            text(
                "SELECT a.id::text AS id, a.direccion_estandarizada AS direccion, "
                "       a.tipo_activo, a.piso_altura, a.walk_score, "
                "       a.score_ruido_predictivo AS ruido, "
                "       a.porcentaje_cobertura_vegetal AS vegetacion, "
                "       a.volumen_trafico_historico AS trafico, "
                "       a.conectividad, a.servicios_cercanos, "
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
                "servicios_cercanos": r["servicios_cercanos"],
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
@limiter.limit("60/minute")
async def assets_near(
    request: Request,
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
                "       a.volumen_trafico_historico AS trafico, a.conectividad, "
                "       a.servicios_cercanos, a.imagen_url, "
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
            "trafico": r["trafico"], "conectividad": r["conectividad"],
            "servicios_cercanos": r["servicios_cercanos"], "imagen_url": r["imagen_url"],
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


@router.get(
    "/mine",
    summary="Mis publicaciones (inmuebles del usuario / su agencia)",
    description="Lista los inmuebles publicados por el usuario autenticado (o su agencia).",
)
async def my_assets(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # WHERE condicional: evitamos bindear NULL (asyncpg no infiere su tipo).
    params: dict = {"u": user.user_id}
    where = "a.owner_user_id = :u"
    if user.agency_id:
        where += " OR a.owner_agency_id = :a"
        params["a"] = user.agency_id

    rows = (
        await db.execute(
            text(
                "SELECT a.id::text AS id, a.direccion_estandarizada AS direccion, "
                "       a.tipo_activo, a.piso_altura, a.walk_score, "
                "       a.score_ruido_predictivo AS ruido, "
                "       a.porcentaje_cobertura_vegetal AS vegetacion, "
                "       a.conectividad, a.servicios_cercanos, a.caracteristicas, a.created_at, "
                "       t.tipo_operacion AS operacion, t.precio, "
                '       ftm.tipo_tuberia, ftm."año_construccion" AS anio_construccion, '
                "       ftm.tipo_estructura, ftm.calidad_acabados, "
                "       ftm.ultimo_mantenimiento_cisterna, ftm.ultima_impermeabilizacion_techo, "
                "       ftm.ultima_pintura_fachada, ftm.ultimo_cambio_cableado_electrico, "
                "       ftm.monto_invertido_mejoras, ftm.descripcion_mejoras, ftm.foto_evidencias, "
                "       (ftm.activo_id IS NOT NULL) AS tiene_ficha "
                "FROM activos_inmutables a "
                "LEFT JOIN LATERAL ("
                "   SELECT tipo_operacion, precio FROM transacciones_temporales tt "
                "   WHERE tt.activo_id = a.id ORDER BY fecha_publicacion DESC LIMIT 1"
                ") t ON true "
                "LEFT JOIN ficha_tecnica_mantenimiento ftm ON ftm.activo_id = a.id "
                f"WHERE {where} "
                "ORDER BY a.created_at DESC"
            ),
            params,
        )
    ).mappings().all()

    base = settings.public_app_url.rstrip("/")
    items = []
    for r in rows:
        car = r["caracteristicas"]
        if isinstance(car, str):
            car = json.loads(car or "{}")
        car = car or {}
        fotos = car.get("fotos") or []

        ficha = None
        if r["tiene_ficha"]:
            ficha = {
                "tipo_tuberia": r["tipo_tuberia"],
                "anio_construccion": r["anio_construccion"],
                "tipo_estructura": r["tipo_estructura"],
                "calidad_acabados": r["calidad_acabados"],
                "ultimo_mantenimiento_cisterna": r["ultimo_mantenimiento_cisterna"].isoformat() if r["ultimo_mantenimiento_cisterna"] else None,
                "ultima_impermeabilizacion_techo": r["ultima_impermeabilizacion_techo"].isoformat() if r["ultima_impermeabilizacion_techo"] else None,
                "ultima_pintura_fachada": r["ultima_pintura_fachada"].isoformat() if r["ultima_pintura_fachada"] else None,
                "ultimo_cambio_cableado_electrico": r["ultimo_cambio_cableado_electrico"].isoformat() if r["ultimo_cambio_cableado_electrico"] else None,
                "monto_invertido_mejoras": float(r["monto_invertido_mejoras"]) if r["monto_invertido_mejoras"] is not None else None,
                "descripcion_mejoras": r["descripcion_mejoras"],
                "foto_evidencias": json.loads(r["foto_evidencias"]) if r["foto_evidencias"] else [],
            }

        items.append({
            "id": r["id"],
            "direccion": r["direccion"],
            "tipo_activo": r["tipo_activo"],
            "piso_altura": r["piso_altura"],
            "walk_score": r["walk_score"],
            "ruido": r["ruido"],
            "vegetacion": float(r["vegetacion"]) if r["vegetacion"] is not None else None,
            "conectividad": r["conectividad"],
            "servicios_cercanos": r["servicios_cercanos"],
            "operacion": r["operacion"],
            "precio": float(r["precio"]) if r["precio"] is not None else None,
            "portada": fotos[0] if fotos else None,
            "num_fotos": len(fotos),
            "caracteristicas": car,          # datos completos → form abre instantáneo
            "ficha": ficha,                  # datos completos → form abre instantáneo
            "deep_link": f"{base}/a/{r['id']}",
        })
    return {"total": len(items), "publicaciones": items}


# ── Fase 2: Ficha técnica de mantenimiento (con evidencia) ──────────────────
class FichaRequest(BaseModel):
    tipo_tuberia: str | None = Field(default=None, max_length=50)
    anio_construccion: int | None = Field(default=None, ge=1900, le=2100)
    tipo_estructura: str | None = Field(default=None, max_length=50)
    calidad_acabados: str | None = Field(default=None, max_length=30)
    ultimo_mantenimiento_cisterna: str | None = None
    ultima_impermeabilizacion_techo: str | None = None
    ultima_pintura_fachada: str | None = None
    ultimo_cambio_cableado_electrico: str | None = None
    monto_invertido_mejoras: float | None = Field(default=None, ge=0)
    descripcion_mejoras: str | None = None
    foto_evidencias: list[str] | None = None


async def _assert_owner(db: AsyncSession, activo_id: uuid.UUID, user: CurrentUser) -> None:
    row = (
        await db.execute(
            text("SELECT owner_user_id::text AS u, owner_agency_id::text AS a "
                 "FROM activos_inmutables WHERE id = :id"),
            {"id": str(activo_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inmueble no encontrado.")
    es_dueño = row["u"] == user.user_id or (user.agency_id and row["a"] == user.agency_id)
    if not es_dueño:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Este inmueble no es tuyo.")


@router.get("/{activo_id}/ficha", summary="Cargar la ficha técnica (dueño)")
async def get_ficha(
    activo_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _assert_owner(db, activo_id, user)
    f = (
        await db.execute(
            text('SELECT tipo_tuberia, "año_construccion" AS anio_construccion, tipo_estructura, '
                 "calidad_acabados, ultimo_mantenimiento_cisterna, ultima_impermeabilizacion_techo, "
                 "ultima_pintura_fachada, ultimo_cambio_cableado_electrico, monto_invertido_mejoras, "
                 "descripcion_mejoras, foto_evidencias "
                 "FROM ficha_tecnica_mantenimiento WHERE activo_id = :id"),
            {"id": str(activo_id)},
        )
    ).mappings().first()
    if not f:
        return {"ficha": None}
    d = dict(f)
    for k in ("ultimo_mantenimiento_cisterna", "ultima_impermeabilizacion_techo",
              "ultima_pintura_fachada", "ultimo_cambio_cableado_electrico"):
        d[k] = d[k].isoformat() if d.get(k) else None
    d["monto_invertido_mejoras"] = float(d["monto_invertido_mejoras"]) if d.get("monto_invertido_mejoras") is not None else None
    d["foto_evidencias"] = json.loads(d["foto_evidencias"]) if d.get("foto_evidencias") else []
    return {"ficha": d}


@router.post("/{activo_id}/ficha", status_code=status.HTTP_200_OK,
             summary="Guardar la ficha técnica (Fase 2, solo dueño)")
async def save_ficha(
    activo_id: uuid.UUID,
    payload: FichaRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _assert_owner(db, activo_id, user)
    fotos = json.dumps(payload.foto_evidencias) if payload.foto_evidencias else None
    params = {
        "aid": str(activo_id),
        "tuberia": payload.tipo_tuberia,
        "anio": payload.anio_construccion,
        "estructura": payload.tipo_estructura,
        "acabados": payload.calidad_acabados,
        "cisterna": payload.ultimo_mantenimiento_cisterna or None,
        "techo": payload.ultima_impermeabilizacion_techo or None,
        "fachada": payload.ultima_pintura_fachada or None,
        "cableado": payload.ultimo_cambio_cableado_electrico or None,
        "monto": payload.monto_invertido_mejoras,
        "descripcion": payload.descripcion_mejoras,
        "fotos": fotos,
    }
    await db.execute(
        text(
            'INSERT INTO ficha_tecnica_mantenimiento '
            '(id, activo_id, tipo_tuberia, "año_construccion", tipo_estructura, calidad_acabados, '
            ' ultimo_mantenimiento_cisterna, ultima_impermeabilizacion_techo, ultima_pintura_fachada, '
            ' ultimo_cambio_cableado_electrico, monto_invertido_mejoras, descripcion_mejoras, '
            ' foto_evidencias, estado_revision, updated_at) '
            "VALUES (gen_random_uuid(), :aid, :tuberia, :anio, :estructura, :acabados, "
            " :cisterna::date, :techo::date, :fachada::date, :cableado::date, :monto, :descripcion, "
            " :fotos, 'publicado', now()) "
            "ON CONFLICT (activo_id) DO UPDATE SET "
            " tipo_tuberia = EXCLUDED.tipo_tuberia, "
            ' "año_construccion" = EXCLUDED."año_construccion", '
            " tipo_estructura = EXCLUDED.tipo_estructura, "
            " calidad_acabados = EXCLUDED.calidad_acabados, "
            " ultimo_mantenimiento_cisterna = EXCLUDED.ultimo_mantenimiento_cisterna, "
            " ultima_impermeabilizacion_techo = EXCLUDED.ultima_impermeabilizacion_techo, "
            " ultima_pintura_fachada = EXCLUDED.ultima_pintura_fachada, "
            " ultimo_cambio_cableado_electrico = EXCLUDED.ultimo_cambio_cableado_electrico, "
            " monto_invertido_mejoras = EXCLUDED.monto_invertido_mejoras, "
            " descripcion_mejoras = EXCLUDED.descripcion_mejoras, "
            " foto_evidencias = EXCLUDED.foto_evidencias, "
            " updated_at = now()"
        ),
        params,
    )
    await db.commit()
    return {"ok": True, "activo_id": str(activo_id)}


# ── Características comerciales (dormitorios, baños, área, precio…) ───────────
class CaracteristicasRequest(BaseModel):
    area_total_m2: float | None = Field(default=None, ge=0)
    area_construida_m2: float | None = Field(default=None, ge=0)
    num_dormitorios: int | None = Field(default=None, ge=0, le=50)
    num_banos: int | None = Field(default=None, ge=0, le=50)
    num_medio_banos: int | None = Field(default=None, ge=0, le=50)
    num_parqueaderos: int | None = Field(default=None, ge=0, le=50)
    num_bodegas: int | None = Field(default=None, ge=0, le=50)
    amoblado: bool | None = None
    sala: bool | None = None
    comedor: bool | None = None
    estudio: bool | None = None
    cuarto_servicio: bool | None = None
    balcon: bool | None = None
    terraza: bool | None = None
    alicuota: float | None = Field(default=None, ge=0)
    precio_negociable: bool | None = None
    notas: str | None = None
    precio: float | None = Field(default=None, ge=0)
    # Marketing / anuncio
    fotos: list[str] | None = None                  # fotos del inmueble (galería del anuncio)
    amenidades_edificio: list[str] | None = None   # Piscina, Gimnasio, Seguridad 24/7…
    acepta_mascotas: bool | None = None
    ideal_para: str | None = None                   # "ejecutivos, familia amplia…"
    incluye: list[str] | None = None                # Alícuota, Agua, Luz, Internet…


@router.get("/{activo_id}/caracteristicas", summary="Cargar características (dueño)")
async def get_caracteristicas(
    activo_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _assert_owner(db, activo_id, user)
    row = (
        await db.execute(
            text("SELECT caracteristicas FROM activos_inmutables WHERE id = :id"),
            {"id": str(activo_id)},
        )
    ).mappings().first()
    tx = (
        await db.execute(
            text("SELECT precio FROM transacciones_temporales WHERE activo_id = :id "
                 "ORDER BY fecha_publicacion DESC LIMIT 1"),
            {"id": str(activo_id)},
        )
    ).mappings().first()
    car = row["caracteristicas"] if row and row["caracteristicas"] else {}
    if isinstance(car, str):
        car = json.loads(car)
    precio = float(tx["precio"]) if tx and tx["precio"] is not None else None
    return {"caracteristicas": car, "precio": precio}


@router.post("/{activo_id}/caracteristicas", status_code=status.HTTP_200_OK,
             summary="Guardar características (solo dueño)")
async def save_caracteristicas(
    activo_id: uuid.UUID,
    payload: CaracteristicasRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _assert_owner(db, activo_id, user)
    datos = {k: v for k, v in payload.model_dump().items() if v is not None}
    await db.execute(
        text("UPDATE activos_inmutables SET caracteristicas = CAST(:c AS jsonb) WHERE id = :id"),
        {"c": json.dumps(datos), "id": str(activo_id)},
    )
    # Si actualiza el precio, reflejarlo en la transacción activa.
    if payload.precio is not None:
        await db.execute(
            text("UPDATE transacciones_temporales SET precio = :p "
                 "WHERE activo_id = :id AND id = ("
                 "  SELECT id FROM transacciones_temporales WHERE activo_id = :id "
                 "  ORDER BY fecha_publicacion DESC LIMIT 1)"),
            {"p": payload.precio, "id": str(activo_id)},
        )
    await db.commit()
    return {"ok": True, "activo_id": str(activo_id)}


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
        # Un solo fetch de POIs → walk score + conectividad + entorno destacado.
        pois = await _fetch_pois(lat, lon, timeout=20.0)
        if pois is None:
            return
        ws = compute_walk_score(pois, lat, lon)
        conect = (extraer_conectividad(pois, lat, lon) or {}).get("texto")
        ent = (await entorno_destacado(lat, lon, pois) or {}).get("texto")
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("UPDATE activos_inmutables SET walk_score = :w, conectividad = :c, "
                     "servicios_cercanos = :s WHERE id = :id"),
                {"w": ws["walk_score"], "c": conect, "s": ent, "id": asset_id},
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

    # 4) Recalcular SIEMPRE en segundo plano (sin hacer esperar al usuario, que
    #    ya tiene su QR): asegura Walk Score real + conectividad + servicios
    #    cercanos (entorno Google/OSM), aunque el intento inline ya haya
    #    resuelto el walk score. El inline no computa el entorno.
    background.add_task(_recompute_walk_score, str(aid), lat, lon)

    return {
        "id": str(aid),
        "direccion": payload.direccion.strip(),
        "scores": sc,
        "conectividad": conectividad_txt,
        "deep_link": f"{settings.public_app_url.rstrip('/')}/a/{aid}",
    }
