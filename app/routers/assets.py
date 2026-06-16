import asyncio
import io
import json
import uuid

import segno
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from geoalchemy2.elements import WKTElement
from geopy.geocoders import Nominatim
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, get_current_user, get_optional_user
from app.config import settings
from app.database import AsyncSessionLocal, get_db
from app.limiter import limiter
from app.models import ActivoInmutable
from app.schemas import ActivoCreateRequest, ActivoResponse
from app.entorno import entorno_destacado, limpiar_texto_servicios
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
async def assets_geojson(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser | None = Depends(get_optional_user),
) -> dict:
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

    # Protección del foso: los scores premium (walk, ruido, vegetación, tráfico,
    # conectividad, servicios) SOLO se entregan a usuarios con sesión. El público
    # ve el mapa (pin + dirección + tipo) pero no puede bajar el catastro completo.
    con_scores = user is not None

    features = []
    for r in rows:
        if r["lon"] is None or r["lat"] is None:
            continue
        props: dict = {
            "id": r["id"],
            "direccion": r["direccion"],
            "tipo_activo": r["tipo_activo"],
            "piso_altura": r["piso_altura"],
            "imagen_url": r["imagen_url"],
        }
        if con_scores:
            props.update({
                "walk_score": r["walk_score"],
                "ruido": r["ruido"],
                "vegetacion": float(r["vegetacion"]) if r["vegetacion"] is not None else None,
                "trafico": r["trafico"],
                "conectividad": r["conectividad"],
                "servicios_cercanos": r["servicios_cercanos"],
                "estado_revision": r["estado_revision"],
                "confianza": float(r["confianza_extraccion"]) if r["confianza_extraccion"] is not None else None,
            })
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(r["lon"]), float(r["lat"])]},
            "properties": props,
        })

    return {"type": "FeatureCollection", "features": features, "scores_incluidos": con_scores}


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


class MapaComandoRequest(BaseModel):
    pregunta: str = Field(..., min_length=1, max_length=300)
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


@router.post("/mapa/comando", summary="Mapa conversacional: pregunta → acciones de mapa")
@limiter.limit("40/minute")
async def mapa_comando(request: Request, payload: MapaComandoRequest) -> dict:
    from app.rutas import comando_mapa
    return await comando_mapa(payload.pregunta, payload.lat, payload.lon)


@router.get("/mapa/aura", summary="Tarjeta de aura proactiva: barrio + Walk Score + titular")
@limiter.limit("40/minute")
async def mapa_aura(
    request: Request,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
) -> dict:
    from app.rutas import aura_zona
    return await aura_zona(lat, lon)


@router.get("/{activo_id}/investment", summary="Análisis de inversión del activo (API-first)")
@limiter.limit("30/minute")
async def asset_investment(
    request: Request,
    activo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Análisis de inversión de un inmueble registrado: yields, precio/m², veredicto y
    alertas honestas. Mismo motor que usa el agente (app.inversion) — la web, el
    agente y los integradores B2B son clientes del MISMO recurso (principio API-first).
    """
    from app.inversion import analizar_inversion
    row = (await db.execute(text(
        "SELECT a.direccion_estandarizada, a.tipo_activo, a.caracteristicas, "
        "(f.activo_id IS NOT NULL) AS tiene_ficha_tecnica "
        "FROM activos_inmutables a "
        "LEFT JOIN ficha_tecnica_mantenimiento f ON f.activo_id = a.id "
        "WHERE a.id = :id"), {"id": str(activo_id)})).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Activo no encontrado")
    tx = (await db.execute(text(
        "SELECT precio FROM transacciones_temporales WHERE activo_id = :id "
        "ORDER BY fecha_publicacion DESC LIMIT 1"), {"id": str(activo_id)})).mappings().first()
    car = row["caracteristicas"] or {}
    if isinstance(car, str):
        car = json.loads(car)
    return analizar_inversion(
        direccion=row["direccion_estandarizada"], tipo_activo=row["tipo_activo"],
        precio=float(tx["precio"]) if tx and tx["precio"] is not None else None,
        area=car.get("area_total_m2"), renta_mensual=car.get("renta_mensual_estimada"),
        alicuota_mensual=car.get("alicuota"), tiene_ficha=bool(row["tiene_ficha_tecnica"]),
    )


@router.get(
    "/{activo_id}/anuncio",
    summary="Detalle público del inmueble (página de anuncio del QR)",
    description=(
        "Devuelve el detalle público de UN inmueble que su dueño publicó (el que abre "
        "el QR del letrero): fotos, características, capa base (caminabilidad/ruido/"
        "vegetación), conectividad, ficha técnica verificada y, si es venta, el análisis "
        "de inversión. Es público a propósito — el dueño puso un QR para que el público "
        "lo vea. No expone el catastro completo, solo este activo."
    ),
)
@limiter.limit("60/minute")
async def asset_anuncio(
    request: Request,
    activo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = (await db.execute(text(
        "SELECT a.id::text AS id, a.direccion_estandarizada AS direccion, a.tipo_activo, "
        "       a.piso_altura, a.walk_score, a.score_ruido_predictivo AS ruido, "
        "       a.porcentaje_cobertura_vegetal AS vegetacion, "
        "       a.volumen_trafico_historico AS trafico, a.conectividad, "
        "       a.servicios_cercanos, a.caracteristicas, "
        "       t.tipo_operacion AS operacion, t.precio, "
        '       ftm."año_construccion" AS anio_construccion, ftm.tipo_estructura, '
        "       ftm.tipo_tuberia, ftm.calidad_acabados, "
        "       ftm.ultima_impermeabilizacion_techo, ftm.ultimo_cambio_cableado_electrico, "
        "       ftm.ultimo_mantenimiento_cisterna, ftm.ultima_pintura_fachada, "
        "       ftm.descripcion_mejoras, ftm.estado_revision, ftm.confianza_extraccion, "
        "       (ftm.activo_id IS NOT NULL) AS tiene_ficha "
        "FROM activos_inmutables a "
        "LEFT JOIN LATERAL (SELECT tipo_operacion, precio FROM transacciones_temporales tt "
        "  WHERE tt.activo_id = a.id ORDER BY fecha_publicacion DESC LIMIT 1) t ON true "
        "LEFT JOIN ficha_tecnica_mantenimiento ftm ON ftm.activo_id = a.id "
        "WHERE a.id = :id"), {"id": str(activo_id)})).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inmueble no encontrado.")

    car = row["caracteristicas"] or {}
    if isinstance(car, str):
        car = json.loads(car or "{}")

    operacion = (row["operacion"] or "").lower() or None
    precio = float(row["precio"]) if row["precio"] is not None else None

    ficha = None
    if row["tiene_ficha"]:
        def _d(v):
            return v.isoformat() if v else None
        ficha = {
            "anio_construccion": row["anio_construccion"],
            "tipo_estructura": row["tipo_estructura"],
            "tipo_tuberia": row["tipo_tuberia"],
            "calidad_acabados": row["calidad_acabados"],
            "ultima_impermeabilizacion_techo": _d(row["ultima_impermeabilizacion_techo"]),
            "ultimo_cambio_cableado_electrico": _d(row["ultimo_cambio_cableado_electrico"]),
            "ultimo_mantenimiento_cisterna": _d(row["ultimo_mantenimiento_cisterna"]),
            "ultima_pintura_fachada": _d(row["ultima_pintura_fachada"]),
            "descripcion_mejoras": row["descripcion_mejoras"],
            "estado_revision": row["estado_revision"],
            "confianza": float(row["confianza_extraccion"]) if row["confianza_extraccion"] is not None else None,
        }

    # Inversión: solo si es venta (en arriendo el canon ya es la renta).
    inversion = None
    if operacion == "venta":
        from app.inversion import analizar_inversion
        inversion = analizar_inversion(
            direccion=row["direccion"], tipo_activo=row["tipo_activo"], precio=precio,
            area=car.get("area_total_m2"), renta_mensual=car.get("renta_mensual_estimada"),
            alicuota_mensual=car.get("alicuota"), tiene_ficha=bool(row["tiene_ficha"]),
        )

    return {
        "id": row["id"],
        "direccion": row["direccion"],
        "tipo_activo": row["tipo_activo"],
        "piso_altura": row["piso_altura"],
        "operacion": operacion,
        "precio": precio,
        "precio_negociable": bool(car.get("precio_negociable")),
        "scores": {
            "caminabilidad": row["walk_score"],
            "ruido": row["ruido"],
            "vegetacion": float(row["vegetacion"]) if row["vegetacion"] is not None else None,
            "trafico": row["trafico"],
        },
        "conectividad": row["conectividad"],
        "servicios_cercanos": limpiar_texto_servicios(row["servicios_cercanos"]),
        "caracteristicas": car,
        "ficha": ficha,
        "inversion": inversion,
    }


async def _leads_de_activo(db: AsyncSession, activo_id: str, direccion: str | None = None) -> list[dict]:
    """Interesados (deduplicados por dispositivo) de UN inmueble. Reutilizable por
    el panel por-propiedad y por el CRM agregado del corredor."""
    from app.routers.chat import intencion_de_sesion, ensure_handoff_tables
    # Fuente: checkpointer de LangGraph (thread_id == session_id, qr-{activo}-{device}-…).
    try:
        thread_ids = (await db.execute(
            text("SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id LIKE :p"),
            {"p": f"qr-{activo_id}-%"},
        )).scalars().all()
    except Exception:  # noqa: BLE001 — tabla aún no creada / checkpointer en memoria
        thread_ids = []
    handoff_map: dict[str, dict] = {}
    try:
        await ensure_handoff_tables(db)
        h_rows = (await db.execute(
            text("SELECT session_id, estado, lead_email FROM handoff_sesion WHERE session_id LIKE :p"),
            {"p": f"qr-{activo_id}-%"},
        )).mappings().all()
        handoff_map = {r["session_id"]: {"estado": r["estado"], "email": r["lead_email"]} for r in h_rows}
    except Exception:  # noqa: BLE001
        handoff_map = {}

    prefix = f"qr-{activo_id}-"
    by_device: dict[str, dict] = {}
    for sid in thread_ids:
        try:
            a = await intencion_de_sesion(sid)
        except Exception:  # noqa: BLE001
            continue
        if not a.get("turnos"):
            continue  # solo escaneó / sin mensajes propios → aún no es un lead real
        device = sid[len(prefix):len(prefix) + 36] or sid
        ho = handoff_map.get(sid) or {}
        email = ho.get("email")
        lead = {
            "session_id": sid, "activo_id": str(activo_id), "direccion": direccion,
            "lead": email or f"Lead #{device[:4]}",
            "email": email,
            "estado": a["estado"], "nivel": a["nivel"], "score": a["score"],
            "resumen": a["resumen"], "razones": a["razones"],
            "handoff_sugerido": a["handoff_sugerido"], "accion_sugerida": a["accion_sugerida"],
            "handoff_estado": ho.get("estado"),
        }
        prev = by_device.get(device)
        if prev is None or (bool(lead["handoff_estado"]), lead["score"]) > (bool(prev["handoff_estado"]), prev["score"]):
            by_device[device] = lead
    return list(by_device.values())


def _funnel_y_orden(leads: list[dict]) -> dict:
    from app.intencion import ESTADOS
    funnel = {e: 0 for e in ESTADOS}
    for ld in leads:
        funnel[ld["estado"]] = funnel.get(ld["estado"], 0) + 1
    leads.sort(key=lambda x: (bool(x["handoff_estado"]), x["handoff_sugerido"], x["score"]), reverse=True)
    return {"total": len(leads), "funnel": funnel, "leads": leads}


@router.get(
    "/mine/leads",
    summary="CRM del corredor — interesados de TODOS sus inmuebles",
    description="Agrega los interesados de todas las propiedades del corredor (o su agencia), "
                "clasificados por el motor de intención. Solo corredores/agencias.",
)
@limiter.limit("20/minute")
async def mine_leads(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    params: dict = {"u": user.user_id}
    where = "owner_user_id = :u"
    if user.agency_id:
        where += " OR owner_agency_id = :a"
        params["a"] = user.agency_id
    rows = (await db.execute(
        text(f"SELECT id::text AS id, direccion_estandarizada AS direccion "
             f"FROM activos_inmutables WHERE {where}"), params)).mappings().all()
    all_leads: list[dict] = []
    for r in rows:
        all_leads.extend(await _leads_de_activo(db, r["id"], r["direccion"]))
    return _funnel_y_orden(all_leads)


@router.get(
    "/{activo_id}/leads",
    summary="Interesados del inmueble (CRM de intención por propiedad)",
)
@limiter.limit("30/minute")
async def asset_leads(
    request: Request,
    activo_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _assert_owner(db, activo_id, user)
    leads = await _leads_de_activo(db, str(activo_id))
    return _funnel_y_orden(leads)


class CorredorMsg(BaseModel):
    texto: str = Field(..., min_length=1, max_length=2000)


@router.get(
    "/{activo_id}/leads/{session_id}/conversacion",
    summary="Conversación completa de un interesado (para el corredor)",
)
@limiter.limit("60/minute")
async def lead_conversacion(
    request: Request, activo_id: uuid.UUID, session_id: str,
    user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> dict:
    await _assert_owner(db, activo_id, user)
    if not session_id.startswith(f"qr-{activo_id}-"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La sesión no es de este inmueble.")
    from app.routers.chat import transcript_de_sesion, ensure_handoff_tables
    trans = await transcript_de_sesion(session_id)
    try:
        await ensure_handoff_tables(db)
        rows = (await db.execute(text(
            "SELECT autor, texto FROM handoff_mensaje WHERE session_id = :s ORDER BY id ASC"),
            {"s": session_id})).mappings().all()
        hmsgs = [{"autor": r["autor"], "texto": r["texto"]} for r in rows]
        estado = (await db.execute(text(
            "SELECT estado FROM handoff_sesion WHERE session_id = :s"), {"s": session_id})).scalar()
    except Exception:  # noqa: BLE001
        hmsgs, estado = [], None
    return {"transcript": trans, "handoff": hmsgs, "estado": estado}


@router.post(
    "/{activo_id}/leads/{session_id}/responder",
    summary="El corredor responde al interesado (in-platform, sin WhatsApp)",
)
@limiter.limit("40/minute")
async def responder_lead(
    request: Request, activo_id: uuid.UUID, session_id: str, payload: CorredorMsg,
    user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> dict:
    await _assert_owner(db, activo_id, user)
    if not session_id.startswith(f"qr-{activo_id}-"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La sesión no es de este inmueble.")
    from app.routers.chat import ensure_handoff_tables
    await ensure_handoff_tables(db)
    await db.execute(text(
        "INSERT INTO handoff_sesion (session_id, activo_id, estado, corredor_id) "
        "VALUES (:s, :a, 'activo', :u) ON CONFLICT (session_id) DO UPDATE "
        "SET estado = 'activo', corredor_id = :u, actualizado_en = now()"),
        {"s": session_id, "a": str(activo_id), "u": user.user_id})
    await db.execute(text(
        "INSERT INTO handoff_mensaje (session_id, autor, texto) VALUES (:s, 'corredor', :t)"),
        {"s": session_id, "t": payload.texto.strip()})
    await db.commit()
    return {"ok": True}


@router.get(
    "/{activo_id}/rutas",
    summary="Rutas a pie a los servicios cercanos (Google Routes, en vivo)",
)
@limiter.limit("30/minute")
async def asset_rutas(
    request: Request,
    activo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = (
        await db.execute(
            text("SELECT ST_Y(geom) AS lat, ST_X(geom) AS lon FROM activos_inmutables WHERE id = :id"),
            {"id": str(activo_id)},
        )
    ).mappings().first()
    if not row or row["lat"] is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inmueble no encontrado.")
    from app.rutas import rutas_desde
    rutas = await rutas_desde(float(row["lat"]), float(row["lon"]), n=3)
    return {"rutas": rutas or [], "disponible": rutas is not None}


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
    # Input para la capa de inversión: renta mensual lograble (estimación del corredor).
    renta_mensual_estimada: float | None = Field(default=None, ge=0)
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


# ── Editar mi inmueble (propietario o corredor) ─────────────────────────────
class EditAssetRequest(BaseModel):
    direccion: str | None = Field(default=None, min_length=5, max_length=255)
    tipo_activo: str | None = Field(default=None, max_length=50)
    operacion: str | None = Field(default=None, description="arriendo | venta")
    precio: float | None = Field(default=None, ge=0)
    piso_altura: int | None = Field(default=None, ge=1, le=200)


@router.patch(
    "/{activo_id}",
    summary="Editar mi inmueble (propietario autenticado)",
    description=(
        "Actualiza los datos editables de un inmueble propio: dirección, tipo, "
        "operación, precio y piso. Si la dirección cambia, se vuelve a geocodificar "
        "y recalcular la capa base (Walk Score, conectividad, entorno) en segundo plano. "
        "Solo el dueño (o su agencia) puede editar."
    ),
)
async def edit_asset(
    activo_id: uuid.UUID,
    payload: EditAssetRequest,
    background: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _assert_owner(db, activo_id, user)

    # Estado actual (para detectar si cambió la dirección).
    cur = (
        await db.execute(
            text("SELECT direccion_estandarizada AS dir, ST_Y(geom::geometry) AS lat, "
                 "ST_X(geom::geometry) AS lon FROM activos_inmutables WHERE id = :id"),
            {"id": str(activo_id)},
        )
    ).mappings().first()

    # 1) Campos del activo (dirección / tipo / piso).
    sets, params = [], {"id": str(activo_id)}
    nueva_dir = payload.direccion.strip() if payload.direccion else None
    direccion_cambio = bool(nueva_dir and nueva_dir != (cur["dir"] or "").strip())

    if nueva_dir:
        sets.append("direccion_estandarizada = :dir")
        params["dir"] = nueva_dir
    if payload.tipo_activo:
        sets.append("tipo_activo = :tipo")
        params["tipo"] = payload.tipo_activo
    if payload.piso_altura is not None:
        sets.append("piso_altura = :piso")
        params["piso"] = payload.piso_altura

    # Si cambió la dirección → re-geocodificar (si falla, mantenemos coords previas).
    lat, lon = cur["lat"], cur["lon"]
    if direccion_cambio:
        geo = await _geocode(nueva_dir)
        if geo:
            lat, lon = geo
            sets.append("geom = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)")
            params["lat"], params["lon"] = lat, lon

    if sets:
        await db.execute(
            text(f"UPDATE activos_inmutables SET {', '.join(sets)} WHERE id = :id"),
            params,
        )

    # 2) Operación / precio (transacción más reciente; si no existe, se crea).
    if payload.operacion is not None or payload.precio is not None:
        tset, tparams = [], {"aid": str(activo_id)}
        if payload.operacion is not None:
            op_norm = (payload.operacion or "").strip().upper()
            if op_norm not in ("ARRIENDO", "VENTA", "MONITOREO_PASIVO"):
                op_norm = "ARRIENDO"
            tset.append("tipo_operacion = :op")
            tparams["op"] = op_norm
        if payload.precio is not None:
            tset.append("precio = :precio")
            tparams["precio"] = payload.precio

        upd = await db.execute(
            text("UPDATE transacciones_temporales SET " + ", ".join(tset) +
                 " WHERE id = (SELECT id FROM transacciones_temporales WHERE activo_id = :aid "
                 "ORDER BY fecha_publicacion DESC LIMIT 1)"),
            tparams,
        )
        if upd.rowcount == 0:  # no había transacción → crear una
            op_norm = ((payload.operacion or "arriendo").strip().upper())
            if op_norm not in ("ARRIENDO", "VENTA", "MONITOREO_PASIVO"):
                op_norm = "ARRIENDO"
            await db.execute(
                text("INSERT INTO transacciones_temporales (id, activo_id, tipo_operacion, precio, estado_anuncio) "
                     "VALUES (:tid, :aid, :op, :precio, 'ACTIVO')"),
                {"tid": str(uuid.uuid4()), "aid": str(activo_id),
                 "op": op_norm, "precio": payload.precio},
            )

    await db.commit()

    # 3) Si cambió la dirección, recalcular la capa base en segundo plano.
    if direccion_cambio:
        background.add_task(_recompute_walk_score, str(activo_id), lat, lon)

    return {"id": str(activo_id), "ok": True, "reubicado": direccion_cambio}


@router.post(
    "/{activo_id}/recompute",
    summary="Recalcular la capa base del inmueble (caminabilidad, conectividad, entorno)",
    description=(
        "Vuelve a calcular Walk Score, conectividad y servicios cercanos desde OSM/Google "
        "con los filtros actuales (limpia POIs basura como nombres genéricos). Útil cuando "
        "el dato guardado quedó estancado. Solo el dueño."
    ),
)
@limiter.limit("10/minute")
async def recompute_asset(
    request: Request, activo_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> dict:
    await _assert_owner(db, activo_id, user)
    row = (await db.execute(
        text("SELECT ST_Y(geom) AS lat, ST_X(geom) AS lon FROM activos_inmutables WHERE id = :id"),
        {"id": str(activo_id)},
    )).mappings().first()
    if not row or row["lat"] is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inmueble no encontrado.")
    await _recompute_walk_score(str(activo_id), float(row["lat"]), float(row["lon"]))
    fresh = (await db.execute(
        text("SELECT walk_score, conectividad, servicios_cercanos FROM activos_inmutables WHERE id = :id"),
        {"id": str(activo_id)},
    )).mappings().first()
    return {"ok": True, "walk_score": fresh["walk_score"],
            "conectividad": fresh["conectividad"], "servicios_cercanos": fresh["servicios_cercanos"]}
