import asyncio
import io
import json
import logging
import re
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
from app.entorno_curacion import (
    aplicar_curacion,
    ensure_curacion_table,
    fetch_curaciones,
    info_verificacion,
    parse_servicios,
)
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


# ── Banner "letrero" (operación + datos + QR + teléfono), listo para imprimir ───────────
# Feedback en vivo (2026-07-02): el QR pelado con "Imprime y pégalo en el letrero" invita
# poco a escanear. Se genera en el BACKEND con Pillow (PDF/PNG server-side es más confiable
# para imprimir que componerlo en el navegador, y no exige agregar html2canvas al frontend).
# Iteró en vivo: foto → "SE ARRIENDA/SE VENDE" grande; se quitó el precio; se sumó el
# teléfono del corredor bien visible; y finalmente se rediseñó a print-first (ver paleta).
# Paleta print-first: el banner es para IMPRIMIR y pegar en un letrero físico. El diseño
# anterior (fondo casi-negro con paneles oscuros) salía manchado, chupaba tóner y perdía
# todos los matices al fotocopiar (feedback en vivo 2026-07-02: "queda todo oscuro sin
# matices"). Se rediseñó a FONDO BLANCO (papel = cero tinta), tinta oscura y color solo
# como acento fuerte (banda de operación + caja del teléfono), que se lee de lejos y
# sobrevive a una fotocopia en blanco y negro.
_WHITE = (255, 255, 255)     # fondo (papel)
_INK = (17, 16, 24)          # texto principal + encabezado (casi negro sobre blanco)
_INK_SOFT = (90, 88, 104)    # texto secundario / muted
_TEAL = (18, 122, 116)       # ARRIENDO: banda + caja (teal profundo → texto blanco a ~5:1, imprime mejor)
_GOLD = (224, 168, 48)       # VENTA / DISPONIBLE: banda + caja (ámbar)
_LINE = (222, 224, 230)      # marco fino del QR
# DejaVu Sans (instalada via apt en Dockerfile, fonts-dejavu-core) — TTF real para texto
# nitido. Si no esta (dev local sin la fuente del sistema), degradamos al bitmap font de
# PIL: el banner se sigue generando, solo con tipografia fea, nunca rompe el endpoint.
_FUENTES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
_FUENTES_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _fuente_letrero(size: int, negrita: bool = False):
    from PIL import ImageFont
    for path in (_FUENTES_BOLD if negrita else _FUENTES_REGULAR):
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001 — fuente no instalada en este entorno
            continue
    return ImageFont.load_default()


def _envolver_texto(draw, texto: str, fuente, max_ancho: int) -> list[str]:
    """Envuelve `texto` en lineas que no excedan max_ancho (en px) con `fuente`."""
    palabras = (texto or "").split()
    lineas: list[str] = []
    actual = ""
    for palabra in palabras:
        candidata = f"{actual} {palabra}".strip()
        if draw.textlength(candidata, font=fuente) <= max_ancho or not actual:
            actual = candidata
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def _fuente_ajustada_a_ancho(draw, texto: str, max_ancho: int, tam_inicial: int, tam_min: int = 40):
    """Fuente en negrita lo más grande posible (arrancando en `tam_inicial`) tal que
    `texto` en una sola línea quepa en `max_ancho` px. Usado para el "SE ARRIENDA"/
    "SE VENDE" del letrero — debe leerse grande y de lejos, pero sin desbordar el
    banner con direcciones/tipos de inmueble más largos de lo esperado."""
    tam = tam_inicial
    while tam > tam_min:
        fuente = _fuente_letrero(tam, True)
        if draw.textlength(texto, font=fuente) <= max_ancho:
            return fuente
        tam -= 4
    return _fuente_letrero(tam_min, True)


def _telefono_visible(numero_wsp: str | None) -> str | None:
    """Formato legible del WhatsApp del corredor para el letrero — pensado para quien NO
    sabe escanear un QR y necesita poder MARCAR el número a mano desde su celular.
    Caso Ecuador (593 + 9 dígitos, el piloto actual): se muestra en formato local con el
    0 inicial de celular (ej. 593984171860 -> 0984171860), que es como la gente reconoce
    y marca un número en Ecuador — NO el formato internacional con código de país, que
    nadie usa para marcar de memoria. Para otros países (sin regla local codificada aún),
    se muestra con '+' internacional como fallback razonable."""
    if not numero_wsp:
        return None
    if numero_wsp.startswith("593") and len(numero_wsp) == 12:
        return "0" + numero_wsp[3:]
    return "+" + numero_wsp


async def _generar_letrero_png(
    *, activo_id: uuid.UUID, direccion: str | None, tipo_activo: str | None,
    operacion: str | None, telefono_wsp: str | None,
) -> bytes:
    from PIL import Image, ImageDraw

    # Diseño print-first "banda de color" (V2, elegido en vivo 2026-07-02): fondo BLANCO,
    # la operación en una banda de color de borde a borde con texto de máximo contraste, y
    # el teléfono del corredor en una caja del mismo color bajo el QR. El lienzo se dibuja
    # generoso y se RECORTA al contenido + un margen inferior uniforme — así este diseño
    # (más compacto que el anterior de 2200px) no deja media hoja en blanco ni corta el pie.
    W = 1240
    CANVAS_H = 2400
    img = Image.new("RGB", (W, CANVAS_H), _WHITE)
    draw = ImageDraw.Draw(img)

    def _centrar(texto: str, fuente, y: int, fill) -> None:
        b = draw.textbbox((0, 0), texto, font=fuente)
        draw.text(((W - (b[2] - b[0])) // 2 - b[0], y - b[1]), texto, font=fuente, fill=fill)

    # Color de operación (teal = arriendo, ámbar = venta/disponible) y el color de texto que
    # contrasta contra esa banda: blanco sobre teal, tinta oscura sobre el ámbar más claro.
    es_arriendo = operacion == "arriendo"
    acc = _TEAL if es_arriendo else _GOLD
    texto_sobre_acc = _WHITE if es_arriendo else _INK
    op_texto = {"arriendo": "SE ARRIENDA", "venta": "SE VENDE"}.get(operacion, "DISPONIBLE")

    # ── Encabezado de marca: barra en tinta con un acento de color a la derecha ──
    header_h = 116
    draw.rectangle([0, 0, W, header_h], fill=_INK)
    draw.rectangle([W - 14, 0, W, header_h], fill=acc)
    draw.text((60, 30), "CONTEXTO AI", font=_fuente_letrero(46, True), fill=_WHITE)
    draw.text((62, 82), "Cada lugar tiene un aura", font=_fuente_letrero(22), fill=(180, 210, 206))

    # ── Banda de operación: bloque de color full-width con "SE ARRIENDA"/"SE VENDE" auto-fit
    # (reemplaza la foto — feedback en vivo: en el letrero FÍSICO lo que se lee de lejos es
    # el tipo de operación en grande, no una foto chica que igual se ve al escanear el QR).
    banda_y, banda_h = header_h + 70, 300
    draw.rectangle([0, banda_y, W, banda_y + banda_h], fill=acc)
    fuente_op = _fuente_ajustada_a_ancho(draw, op_texto, W - 140, tam_inicial=170)
    b_op = draw.textbbox((0, 0), op_texto, font=fuente_op)
    _centrar(op_texto, fuente_op, banda_y + (banda_h - (b_op[3] - b_op[1])) // 2, texto_sobre_acc)
    y = banda_y + banda_h + 60

    # ── Dirección (hasta 2 líneas) + tipo·operación en tinta sobre blanco ──
    if direccion:
        for linea in _envolver_texto(draw, direccion, _fuente_letrero(46, True), W - 120)[:2]:
            draw.text((60, y), linea, font=_fuente_letrero(46, True), fill=_INK)
            y += 58
    y += 6
    # El precio NO va en el banner (feedback en vivo, 2026-07-02) — el letrero atrae la
    # llamada/escaneo; el precio se conversa con el corredor, no se negocia desde el letrero.
    sub = " · ".join(x for x in [
        (tipo_activo or "").capitalize() or None,
        (operacion or "").capitalize() or None,
    ] if x)
    if sub:
        draw.text((60, y), sub, font=_fuente_letrero(32), fill=_INK_SOFT)
        y += 78

    # ── Llamado a la acción + QR grande sobre blanco con marco fino ──
    y += 8
    draw.text((60, y), "Escanea para conocer este lugar", font=_fuente_letrero(38, True), fill=_INK)
    y += 66
    url = f"{settings.public_app_url.rstrip('/')}/a/{activo_id}"
    qr = segno.make(url, error="h")
    qr_buf = io.BytesIO()
    qr.save(qr_buf, kind="png", scale=10, border=1, dark="#111018", light="#ffffff")
    qr_img = Image.open(qr_buf)
    qr_lado = 520
    qr_img = qr_img.resize((qr_lado, qr_lado), Image.LANCZOS)
    qr_x0 = (W - qr_lado) // 2
    draw.rectangle([qr_x0 - 13, y - 13, qr_x0 + qr_lado + 13, y + qr_lado + 13], outline=_LINE, width=3)
    img.paste(qr_img, (qr_x0, y))
    y += qr_lado + 44

    # ── Teléfono del corredor — LO MÁS VISIBLE bajo el QR (feedback en vivo, 2026-07-02: hay
    # gente que no sabe usar el QR; el número para marcar a mano es el respaldo). Caja del
    # color de la operación, texto contrastado. Solo se dibuja si el corredor cargó su
    # WhatsApp — degradable, el banner sigue siendo válido sin él (el QR solo también sirve).
    tel = _telefono_visible(telefono_wsp)
    if tel:
        _centrar("¿No puedes escanear? Llámanos:", _fuente_letrero(30), y, _INK_SOFT)
        y += 52
        # tam_inicial=150 (mismo peso visual que "SE ARRIENDA"/"SE VENDE"): el corredor pidió
        # que este número sea LO MÁS VISIBLE del letrero, no un dato chico al pie.
        fuente_tel = _fuente_ajustada_a_ancho(draw, tel, W - 160, tam_inicial=150)
        bt = draw.textbbox((0, 0), tel, font=fuente_tel)
        tw, th = bt[2] - bt[0], bt[3] - bt[1]
        pad_x, pad_y = 56, 34
        caja_w, caja_h = tw + 2 * pad_x, th + 2 * pad_y
        caja_x0 = (W - caja_w) // 2
        draw.rounded_rectangle([caja_x0, y, caja_x0 + caja_w, y + caja_h], radius=22, fill=acc)
        draw.text((caja_x0 + pad_x - bt[0], y + pad_y - bt[1]), tel, font=fuente_tel, fill=texto_sobre_acc)
        y += caja_h

    # ── Pie + recorte al contenido (deja un margen inferior uniforme, sin hoja en blanco) ──
    y += 56
    draw.text((60, y), "contexxto.com", font=_fuente_letrero(24), fill=_INK_SOFT)
    y += 40
    # min(...) como red de seguridad: recortar MÁS ALLÁ del lienzo haría que PIL extienda con
    # negro (justo el defecto "todo oscuro" que este rediseño elimina). No ocurre en la
    # práctica (contenido máx ~1850px << CANVAS_H), pero la guarda lo vuelve imposible.
    img = img.crop((0, 0, W, min(y + 44, CANVAS_H)))

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


@router.get(
    "/{activo_id}/letrero.png",
    summary="Banner imprimible del letrero (SE ARRIENDA/SE VENDE + QR + teléfono)",
    description=(
        "Genera un banner PNG listo para imprimir: 'SE ARRIENDA'/'SE VENDE' en letras "
        "grandes (legible de lejos, en el letrero físico), el QR de /a/{id} y — si el "
        "corredor cargó su WhatsApp — el teléfono bien visible bajo el QR, para quien no "
        "sabe escanear. Sin foto (ya se ve al escanear) y sin precio (se conversa con el "
        "corredor, no se negocia desde el letrero)."
    ),
)
async def asset_letrero(activo_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Response:
    row = (await db.execute(text(
        "SELECT a.direccion_estandarizada AS direccion, a.tipo_activo, "
        "       t.tipo_operacion AS operacion "
        "FROM activos_inmutables a "
        "LEFT JOIN LATERAL (SELECT tipo_operacion FROM transacciones_temporales tt "
        "  WHERE tt.activo_id = a.id ORDER BY fecha_publicacion DESC LIMIT 1) t ON true "
        "WHERE a.id = :id"), {"id": str(activo_id)})).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inmueble no encontrado.")

    operacion = (row["operacion"] or "").lower() or None
    from app.routers.chat import _whatsapp_de_activo
    telefono_wsp = await _whatsapp_de_activo(db, str(activo_id))

    png = await _generar_letrero_png(
        activo_id=activo_id, direccion=row["direccion"], tipo_activo=row["tipo_activo"],
        operacion=operacion, telefono_wsp=telefono_wsp,
    )
    return Response(content=png, media_type="image/png")


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
    car = row["caracteristicas"]
    if isinstance(car, str):
        car = json.loads(car or "{}")
    car = car if isinstance(car, dict) else {}  # jsonb no-objeto → {} (car.get nunca lanza)
    return analizar_inversion(
        direccion=row["direccion_estandarizada"], tipo_activo=row["tipo_activo"],
        precio=float(tx["precio"]) if tx and tx["precio"] is not None else None,
        area=car.get("area_total_m2"), renta_mensual=car.get("renta_mensual_estimada"),
        alicuota_mensual=car.get("alicuota"), tiene_ficha=bool(row["tiene_ficha_tecnica"]),
    )


def _scores_fuente(walk_score_fuente: str | None) -> dict:
    """Procedencia declarada POR score para el anuncio (foso de honestidad).

    Solo la caminabilidad es variable: 'osm' cuando se contó sobre comercios REALES,
    'heuristico'/None cuando quedó la estimación por zona (Overpass no respondió). El
    front rotula cada dato con su verdad y deja de afirmar OSM para todos.

    Ruido, vegetación y tráfico son heurísticos POR CONSTRUCCIÓN
    (scores_heuristicos.scores_para): estimación por zona, nunca medición. Se declaran
    'heuristico' fijos a propósito — el día que uno se mida de verdad, se cambia aquí,
    pero jamás se reclama una medición que no existe."""
    return {
        "caminabilidad": walk_score_fuente,
        "ruido": "heuristico",
        "vegetacion": "heuristico",
        "trafico": "heuristico",
    }


_walk_score_fuente_ready = False


async def ensure_walk_score_fuente_column(db) -> None:
    """Autocrea activos_inmutables.walk_score_fuente si falta (Migration 017),
    idempotente y una sola vez por proceso. Persiste la PROCEDENCIA del walk_score
    ('osm' = comercios reales | 'heuristico' = estimación por zona) para que el
    anuncio rotule cada dato con su verdad en vez de afirmar OSM para todos.

    Calca el patrón de los demás ensure_* del repo (ensure_handoff_tables,
    ensure_aura_cache_table): ejecuta el DDL y deja que un fallo BURBUJEE. NO lo
    silenciamos: el SELECT/INSERT que sigue asume la columna, así que tragarse el
    error dejaría una promesa falsa y un 500 opaco más abajo. El rol de la app tiene
    privilegio DDL (ya crea columnas en profiles/handoff en runtime), así que la
    ADD COLUMN IF NOT EXISTS es segura e idempotente."""
    global _walk_score_fuente_ready
    if _walk_score_fuente_ready:
        return
    await db.execute(text(
        "ALTER TABLE activos_inmutables ADD COLUMN IF NOT EXISTS walk_score_fuente text"))
    await db.commit()
    _walk_score_fuente_ready = True


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
    # Auto-sana la columna de procedencia antes de leerla (Migration 017 en runtime).
    await ensure_walk_score_fuente_column(db)
    row = (await db.execute(text(
        "SELECT a.id::text AS id, a.direccion_estandarizada AS direccion, a.tipo_activo, "
        "       a.piso_altura, a.walk_score, a.walk_score_fuente, "
        "       a.score_ruido_predictivo AS ruido, "
        "       a.porcentaje_cobertura_vegetal AS vegetacion, "
        "       a.volumen_trafico_historico AS trafico, a.conectividad, "
        "       a.servicios_cercanos, a.caracteristicas, a.imagen_url, "
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

    car = row["caracteristicas"]
    if isinstance(car, str):
        car = json.loads(car or "{}")
    car = car if isinstance(car, dict) else {}  # jsonb no-objeto → {} (car.get nunca lanza)

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

    # Overlay de curación del corredor (Catastro Vivo) + insignia de verificación.
    _curaciones = await fetch_curaciones(db, str(activo_id))
    _servicios = limpiar_texto_servicios(aplicar_curacion(row["servicios_cercanos"], _curaciones))

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
        "scores_fuente": _scores_fuente(row["walk_score_fuente"]),
        "conectividad": row["conectividad"],
        "servicios_cercanos": _servicios,
        "caracteristicas": car,
        # Foto canónica del catastro → galería del anuncio (si no hay fotos en caracteristicas).
        "fotos": car.get("fotos") or ([row["imagen_url"]] if row["imagen_url"] else []),
        "ficha": ficha,
        "inversion": inversion,
        "entorno_verificado": info_verificacion(_curaciones),
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

    # Captura datos para notificación ANTES de cerrar la sesión de DB.
    h_row = (await db.execute(
        text("SELECT lead_email, push_subscription FROM handoff_sesion WHERE session_id = :s"),
        {"s": session_id})).mappings().first()
    addr = (await db.execute(
        text("SELECT direccion FROM activos_inmutables WHERE id = :id"),
        {"id": str(activo_id)})).scalar()

    await db.commit()

    # Notifica al lead (fire-and-forget: no bloquea la respuesta al corredor).
    # La URL /a/{activo_id} reanuda la conversación del handoff en su dispositivo.
    import asyncio as _aio
    from app.notifications import send_notification
    corredor_nombre = getattr(user, "nombre", None) or "El corredor"
    inmueble_txt = f" sobre {addr}" if addr else ""
    _aio.create_task(send_notification(
        email=(h_row or {}).get("lead_email"),
        push_subscription=(h_row or {}).get("push_subscription"),
        title=f"💬 {corredor_nombre} te respondió",
        body=f"Tienes un mensaje nuevo{inmueble_txt}. Ábrelo para continuar la conversación.",
        url=f"/a/{activo_id}",
        email_subject=f"💬 {corredor_nombre} te respondió en Contexto AI",
    ))

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


async def _pois_geo(lat: float, lon: float) -> list[dict]:
    """POIs cercanos CON coordenadas para el Mapa Vivo (AURA-SINGLE): el inmueble leído
    como espacio. Google Places en vivo (searchNearby por categoría, SIN routing — el
    ruteo peatonal real es 2C). Degradable: sin key o ante fallo de Google → [] y el mapa
    muestra solo el inmueble, nunca rompe el anuncio."""
    key = settings.google_maps_api_key
    if not key:
        return []
    try:
        from app.rutas import _CAT_COLOR, _CAT_EMOJI, _servicios_con_coords
        servicios = await _servicios_con_coords(lat, lon, key, n=6)
    except Exception as e:  # noqa: BLE001 — Google caído/quota/timeout/import → sin pines, no rompas el anuncio
        # Degradamos a [] (el mapa muestra solo el inmueble), pero NO en silencio: logueamos
        # el tipo de fallo para que quota agotada / import roto sean visibles en producción.
        logging.getLogger(__name__).warning("aura _pois_geo degradado a []: %s: %s", type(e).__name__, e)
        return []
    pois: list[dict] = []
    for s in servicios:
        if s.get("lat") is None or s.get("lon") is None:
            continue
        cat = s.get("cat")
        dm = s.get("distancia_m")
        pois.append({
            "nombre": s.get("nombre"),
            "lat": s["lat"],
            "lon": s["lon"],
            "distancia_m": dm,
            # ~80 m/min, honesto: estimamos un poco de más, no de menos (igual que la tarjeta).
            "minutos": max(1, round(dm / 80)) if dm else None,
            "cat": cat,
            "emoji": _CAT_EMOJI.get(cat, "\U0001F4CD"),
            "color": _CAT_COLOR.get(cat, "#9C99AC"),
            "fuente": "google",
        })
    return pois


# ── Caché de POIs del Mapa Vivo (AURA-SINGLE) ────────────────────────────────
# _pois_geo hace ~7 llamadas a Google Places por inmueble. Como vive en
# `activos_INMUTABLES` (su geom no cambia) y los servicios alrededor cambian lento,
# cacheamos el resultado por activo_id con TTL largo → de "~7 llamadas Google por
# VISTA del anuncio" a "~7 por inmueble cada N días". Hace AURA-SINGLE casi gratis.
_AURA_CACHE_DDL = [
    "CREATE TABLE IF NOT EXISTS aura_pois_cache ("
    "  activo_id uuid PRIMARY KEY,"
    "  pois jsonb NOT NULL,"
    "  computed_at timestamptz NOT NULL DEFAULT now())",
]
_AURA_CACHE_TTL_DIAS = 30
_aura_cache_ready = False


async def ensure_aura_cache_table(db) -> None:
    """Crea la tabla de caché si no existe (idempotente, una vez por proceso)."""
    global _aura_cache_ready
    if _aura_cache_ready:
        return
    for ddl in _AURA_CACHE_DDL:
        await db.execute(text(ddl))
    await db.commit()
    _aura_cache_ready = True


async def _pois_geo_cached(db, activo_id, lat: float, lon: float) -> list[dict]:
    """POIs con coords, cacheados POR INMUEBLE. Lee la caché fresca (≤ TTL); si no hay
    o expiró, computa vía Google y la rellena. Solo cachea resultados NO vacíos: un []
    suele ser un fallo transitorio de Google, no 'sin servicios' → no lo congelamos N
    días. Toda la caché es best-effort: si la BD falla, caemos a Google sin romper /aura."""
    try:
        await ensure_aura_cache_table(db)
        hit = (await db.execute(
            text("SELECT pois FROM aura_pois_cache "
                 "WHERE activo_id = :id AND computed_at > now() - (:ttl * interval '1 day')"),
            {"id": str(activo_id), "ttl": _AURA_CACHE_TTL_DIAS},
        )).mappings().first()
        if hit is not None:
            pois = hit["pois"]
            return json.loads(pois) if isinstance(pois, str) else pois
    except Exception as e:  # noqa: BLE001 — caché caída / tabla no lista → recomputamos
        # rollback OBLIGATORIO: un db.execute fallido deja la AsyncSession en transacción
        # abortada; el commit del teardown de get_db reventaría con PendingRollbackError (→500).
        await db.rollback()
        logging.getLogger(__name__).warning("aura cache: lectura falló (%s: %s), recomputo", type(e).__name__, e)

    pois = await _pois_geo(lat, lon)
    if pois:  # no congelar un [] transitorio
        try:
            await db.execute(
                text("INSERT INTO aura_pois_cache (activo_id, pois, computed_at) "
                     "VALUES (:id, :pois::jsonb, now()) "
                     "ON CONFLICT (activo_id) DO UPDATE "
                     "SET pois = EXCLUDED.pois, computed_at = now()"),
                {"id": str(activo_id), "pois": json.dumps(pois)},
            )
            await db.commit()
        except Exception as e:  # noqa: BLE001 — fallo de escritura de caché no debe romper /aura
            await db.rollback()  # limpia la transacción abortada (ver nota arriba)
            logging.getLogger(__name__).warning("aura cache: escritura falló (%s: %s)", type(e).__name__, e)
    return pois


async def _isocronas_geo_cached(db, activo_id, lat: float | None, lon: float | None) -> list[dict]:
    """Isócronas peatonales (15/30 min) CACHEADAS por inmueble, para AURA-SINGLE.

    Mismo patrón que _pois_geo_cached: el batch (scripts/valhalla_isocronas_batch.py)
    ya precomputó isocronas_inmueble para el inventario existente — lectura es gratis
    (una query a PostGIS). Si el inmueble es nuevo (aún no pasó por el batch), hace UNA
    llamada en vivo a Valhalla y la persiste, para que la próxima vista sea instantánea.
    Degradable: sin Valhalla / sin coords → [] y el mini-mapa simplemente no pinta
    isócronas (los POIs y el pin del inmueble igual se muestran)."""
    try:
        filas = (await db.execute(
            text("SELECT minutos, ST_AsGeoJSON(geom)::json AS geometry "
                 "FROM isocronas_inmueble WHERE activo_id = :id ORDER BY minutos"),
            {"id": str(activo_id)},
        )).mappings().all()
        if filas:
            return [{"minutos": f["minutos"], "geometry": f["geometry"]} for f in filas]
    except Exception as e:  # noqa: BLE001 — tabla no lista / error transitorio
        await db.rollback()  # limpia la transacción abortada (mismo motivo que _pois_geo_cached)
        logging.getLogger(__name__).warning("aura isocronas: lectura falló (%s: %s)", type(e).__name__, e)

    if lat is None or lon is None:
        return []
    from app.isocronas import guardar_isocronas_inmueble, isocrona
    feats = await isocrona(lat, lon)  # None si Valhalla no responde → degrada a []
    if not feats:
        return []
    try:
        await guardar_isocronas_inmueble(db, activo_id, feats)
        await db.commit()
    except Exception as e:  # noqa: BLE001 — fallo de escritura no debe romper /aura
        await db.rollback()
        logging.getLogger(__name__).warning("aura isocronas: escritura falló (%s: %s)", type(e).__name__, e)
    return feats


@router.get(
    "/{activo_id}/aura",
    summary="Mapa Vivo AURA-SINGLE: el inmueble + sus POIs cercanos con coordenadas",
    description=(
        "El inmueble re-centrado en su entorno + sus POIs cercanos CON lat/lon e "
        "isócronas peatonales (motor propio, Valhalla) para plotearlos en el mini-mapa "
        "del anuncio (modo AURA-SINGLE, docs/SPEC_Mapa_Vivo.md). Va SEPARADO de "
        "/anuncio a propósito: el anuncio pinta al instante y este endpoint carga los "
        "pines/isócronas aparte, para que la latencia de Google/Valhalla no bloquee el "
        "primer paint. Público (mismo criterio que /anuncio: el dueño puso un QR para "
        "que el público lo vea)."
    ),
)
@limiter.limit("30/minute")
async def asset_aura(
    request: Request,
    activo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = (
        await db.execute(
            text("SELECT ST_Y(geom) AS lat, ST_X(geom) AS lon, tipo_activo "
                 "FROM activos_inmutables WHERE id = :id"),
            {"id": str(activo_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inmueble no encontrado.")
    # Público a propósito (igual que /anuncio): el dueño puso un QR para que el público lo vea;
    # solo expone ESTE activo. Si en el futuro hay estados de visibilidad/archivado, filtrar aquí.
    lat = float(row["lat"]) if row["lat"] is not None else None
    lon = float(row["lon"]) if row["lon"] is not None else None
    pois = await _pois_geo_cached(db, activo_id, lat, lon) if (lat is not None and lon is not None) else []
    isocronas = await _isocronas_geo_cached(db, activo_id, lat, lon) if (lat is not None and lon is not None) else []
    return {"lat": lat, "lon": lon, "tipo_activo": row["tipo_activo"], "pois": pois, "isocronas": isocronas}


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
        car = car if isinstance(car, dict) else {}  # jsonb no-objeto → {} (car.get nunca lanza)
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


# ── Curación del entorno por el corredor (el "loop" del Catastro Vivo) ───────
# El corredor sabe antes que el mapa: marca POIs cerrados y agrega los nuevos.
# Se guarda como overlay (autor + fecha) sobre el texto hidratado, reversible.
class CuracionRequest(BaseModel):
    accion: str = Field(..., description="cerrado | agregado")
    nombre: str = Field(..., min_length=2, max_length=120)
    categoria: str | None = Field(default=None, max_length=60)
    distancia_m: int | None = Field(default=None, ge=0, le=20000)
    # El corredor captura su GPS junto al lugar nuevo; el backend calcula la
    # distancia real con el geom del inmueble. (Nunca se teclea un metro a ojo.)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    # Foto del lugar (URL ya subida a Storage). Se captura ahora; el display
    # (anuncio / mapa) llega después — el dato ya queda guardado, sin re-fotografiar.
    foto: str | None = Field(default=None, max_length=600)


@router.get(
    "/{activo_id}/entorno",
    summary="Entorno editable del inmueble (servicios base + curación del corredor)",
)
async def get_entorno(
    activo_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await ensure_curacion_table(db)
    await _assert_owner(db, activo_id, user)
    row = (await db.execute(
        text("SELECT servicios_cercanos FROM activos_inmutables WHERE id = :id"),
        {"id": str(activo_id)},
    )).mappings().first()
    curaciones = await fetch_curaciones(db, str(activo_id))
    return {
        "servicios_base": parse_servicios((row or {}).get("servicios_cercanos")),
        "curaciones": curaciones,
        "verificado": info_verificacion(curaciones),
    }


@router.post(
    "/{activo_id}/entorno",
    summary="Curar el entorno: marcar un servicio cerrado o agregar uno nuevo",
)
@limiter.limit("60/minute")
async def post_entorno(
    request: Request,
    activo_id: uuid.UUID,
    payload: CuracionRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await ensure_curacion_table(db)
    await _assert_owner(db, activo_id, user)
    accion = payload.accion.strip().lower()
    if accion not in ("cerrado", "agregado"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Acción inválida.")
    # La categoría es obligatoria al AGREGAR (lista curada en el front, no texto
    # libre): datos consistentes para el grafo y los íconos del mapa.
    if accion == "agregado" and not (payload.categoria and payload.categoria.strip()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "La categoría es obligatoria para agregar un lugar.")

    # Si el corredor capturó su GPS junto al lugar nuevo, calculamos la distancia
    # REAL con el geom del inmueble (PostGIS) — nunca un metro tecleado a ojo.
    distancia = payload.distancia_m
    if accion == "agregado" and payload.lat is not None and payload.lon is not None:
        d = (await db.execute(
            text("SELECT ST_Distance(geom::geography, "
                 "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS d "
                 "FROM activos_inmutables WHERE id = :id"),
            {"lon": payload.lon, "lat": payload.lat, "id": str(activo_id)},
        )).mappings().first()
        if d and d["d"] is not None:
            distancia = int(round(d["d"]))

    await db.execute(
        text("INSERT INTO entorno_curacion (activo_id, accion, nombre, categoria, distancia_m, lat, lon, foto, corredor_id) "
             "VALUES (:a, :ac, :n, :c, :d, :lat, :lon, :f, :u)"),
        {"a": str(activo_id), "ac": accion, "n": payload.nombre.strip(),
         "lat": payload.lat, "lon": payload.lon, "f": (payload.foto or None),
         "c": (payload.categoria or None), "d": distancia, "u": user.user_id},
    )
    await db.commit()
    curaciones = await fetch_curaciones(db, str(activo_id))
    return {"ok": True, "curaciones": curaciones, "verificado": info_verificacion(curaciones)}


@router.delete(
    "/{activo_id}/entorno/{curacion_id}",
    summary="Deshacer una curación del entorno",
)
async def delete_entorno(
    activo_id: uuid.UUID,
    curacion_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await ensure_curacion_table(db)
    await _assert_owner(db, activo_id, user)
    await db.execute(
        text("DELETE FROM entorno_curacion WHERE id = :id AND activo_id = :a"),
        {"id": curacion_id, "a": str(activo_id)},
    )
    await db.commit()
    curaciones = await fetch_curaciones(db, str(activo_id))
    return {"ok": True, "curaciones": curaciones, "verificado": info_verificacion(curaciones)}


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
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> ActivoResponse:
    point_wkt = WKTElement(
        f"POINT({payload.longitude} {payload.latitude})",
        srid=4326,
    )

    # El ORM mapea walk_score_fuente incondicionalmente → todo INSERT nombra la columna.
    # Auto-sánala antes del flush para no reventar si este es el primer endpoint del proceso
    # y la Migration 017 no corrió aún. La procedencia queda NULL (origen opaco del payload →
    # el anuncio degrada a "estimación", el lado seguro); el job _recompute la sube a 'osm'.
    await ensure_walk_score_fuente_column(db)
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

    # Causa raíz del hueco de entorno (2026-07-01): este endpoint es el único punto de
    # alta que usan los scripts de carga masiva (p.ej. scripts/hidratar_activos.py), y
    # antes de este fix NUNCA encolaba el enriquecimiento real (Overpass + Google
    # Routes/Places) — solo /publish lo hacía. Resultado: 39/40 activos en producción
    # nacían sin servicios_cercanos/conectividad hasta que alguien corría un backfill
    # manual. Encolamos aquí, igual que /publish (línea ~1341), para que todo activo
    # nuevo llegue completo sin depender de un backfill posterior.
    background.add_task(_recompute_walk_score, str(asset.id), payload.latitude, payload.longitude)

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
    # WhatsApp del corredor (opcional). Vive en el PERFIL (aplica a todos sus inmuebles),
    # no en el activo. Habilita el botón "Continuar por WhatsApp" del handoff.
    telefono_wsp: str | None = Field(default=None, max_length=32)


def _normalizar_wsp(raw: str | None) -> str | None:
    """Deja el número en formato wa.me: solo dígitos (código de país + número), sin '+',
    sin '00' de prefijo internacional, sin espacios. Ej. '+593 99 912 3456' o
    '00593999123456' -> '593999123456'. None si queda vacío (así NO pisa el número
    existente del perfil cuando el campo se manda en blanco).

    Bug real detectado en revisión (2026-07-02, antes de mergear el bloque de teléfono
    del letrero): un corredor ecuatoriano lo más probable es que teclee su número tal
    como lo ve en su propio celular — formato LOCAL con el 0 inicial (ej.
    '0984171860'), no en formato internacional. Sin este bloque, ese '0984171860' se
    guardaba TAL CUAL (sin código de país) y el enlace wa.me/0984171860 del botón de
    WhatsApp queda roto en silencio (wa.me exige código de país) — y además
    `_telefono_visible` no lo reconocía como ecuatoriano y mostraba "+0984171860" en el
    banner, un numero no marcable. Se completa a formato internacional (593 + 9
    dígitos) SOLO para el patrón inequívoco de celular ecuatoriano (0 + 9 dígitos, 10
    en total); si el corredor ya escribió el código de país (empieza con dígito != 0,
    o ya trae 593/+593), este bloque no aplica."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 10:
        digits = "593" + digits[1:]
    return digits or None


async def _guardar_wsp_corredor(db, user_id: str, raw: str | None) -> None:
    """Persiste el WhatsApp normalizado en profiles.telefono_wsp del corredor.
    No hace nada si viene vacío (preserva el valor previo)."""
    tel = _normalizar_wsp(raw)
    if not tel:
        return
    from app.routers.chat import ensure_perfil_wsp
    await ensure_perfil_wsp(db)
    await db.execute(
        text("UPDATE profiles SET telefono_wsp = :w WHERE user_id = :u"),
        {"w": tel, "u": user_id},
    )


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
        # Conectividad y entorno: PRIMERO Google (analizar_zona usa Google Routes para la
        # caminata REAL al Metro, no la línea recta de OSM). OSM queda solo de respaldo.
        from app.rutas import analizar_zona  # lazy: evita import circular
        try:
            az = await analizar_zona(lat, lon)
        except Exception:  # noqa: BLE001
            az = {}
        conect = az.get("conectividad") or (extraer_conectividad(pois, lat, lon) or {}).get("texto")
        ent = az.get("servicios_texto") or (await entorno_destacado(lat, lon, pois) or {}).get("texto")
        async with AsyncSessionLocal() as session:
            # Recalcular con éxito == POIs reales de OSM → la procedencia pasa a 'osm'
            # (ws["fuente"] es siempre "osm" aquí). Auto-sana la columna por si el proceso
            # arrancó por este job antes de cualquier publish/anuncio.
            await ensure_walk_score_fuente_column(session)
            await session.execute(
                text("UPDATE activos_inmutables SET walk_score = :w, walk_score_fuente = :f, "
                     "conectividad = :c, servicios_cercanos = :s WHERE id = :id"),
                {"w": ws["walk_score"], "f": ws["fuente"], "c": conect, "s": ent, "id": asset_id},
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
    # Auto-sana la columna de procedencia antes de insertarla (Migration 017 en runtime).
    await ensure_walk_score_fuente_column(db)
    asset = ActivoInmutable(
        id=aid,
        geom=WKTElement(f"POINT({lon} {lat})", srid=4326),
        direccion_estandarizada=payload.direccion.strip(),
        piso_altura=payload.piso_altura,
        walk_score=sc["walk_score"],
        walk_score_fuente=sc["walk_score_fuente"],
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
    # WhatsApp del corredor → su perfil (si lo mandó). Habilita el botón del handoff.
    await _guardar_wsp_corredor(db, user.user_id, payload.telefono_wsp)
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
    # Permite al corredor cargar/actualizar su WhatsApp editando un inmueble ya publicado.
    telefono_wsp: str | None = Field(default=None, max_length=32)


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
            text("SELECT direccion_estandarizada AS dir, tipo_activo AS tipo, "
                 "ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lon "
                 "FROM activos_inmutables WHERE id = :id"),
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

    lat, lon = cur["lat"], cur["lon"]
    geom_reubicado = False
    if direccion_cambio:
        # 1) Re-geocodificar (si falla, mantenemos coords previas).
        geo = await _geocode(nueva_dir)
        if geo:
            lat, lon = geo
            sets.append("geom = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)")
            params["lat"], params["lon"] = lat, lon
            geom_reubicado = True
        # 2) La capa base de la dirección VIEJA quedó obsoleta (posible otra zona).
        #    Recalcular la heurística SÍNCRONA (scores_para es puro/determinístico, sin red)
        #    y marcar walk_score_fuente='heuristico' deja el score Y su rótulo coherentes con
        #    la NUEVA ubicación de inmediato. Sin esto, un 'osm' viejo mentiría "comercios
        #    reales" sobre otra dirección hasta que el job de fondo confirme — o para siempre
        #    si Overpass falla. El job luego SUBE la caminabilidad a 'osm' al contar POIs reales.
        await ensure_walk_score_fuente_column(db)
        base = scores_para(nueva_dir, payload.tipo_activo or cur["tipo"])
        sets += ["walk_score = :ws", "walk_score_fuente = 'heuristico'",
                 "score_ruido_predictivo = :ruido", "porcentaje_cobertura_vegetal = :veg"]
        params["ws"] = base["walk_score"]
        params["ruido"] = base["score_ruido_predictivo"]
        params["veg"] = base["porcentaje_cobertura_vegetal"]

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

    # WhatsApp del corredor → su perfil (permite cargarlo editando un inmueble ya publicado).
    await _guardar_wsp_corredor(db, user.user_id, payload.telefono_wsp)

    await db.commit()

    # Reubicado → la caché de POIs (Mapa Vivo AURA-SINGLE) quedó atada al punto VIEJO:
    # invalidar para que /aura recompute en la nueva ubicación (la precisión verificada es el
    # foso, no servir POIs de otra dirección). Best-effort y DESPUÉS del commit: el geom ya
    # está persistido; si la tabla de caché aún no existe, el fallo no afecta la edición.
    if geom_reubicado:
        try:
            await db.execute(text("DELETE FROM aura_pois_cache WHERE activo_id = :id"),
                             {"id": str(activo_id)})
            await db.commit()
        except Exception as e:  # noqa: BLE001 — tabla aún no creada / error transitorio
            await db.rollback()
            logging.getLogger(__name__).warning("aura cache: invalidación tras reubicación falló (%s)", type(e).__name__)

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
