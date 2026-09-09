"""
Rutas a pie EN VIVO con Google Routes API (capa "desde la tierra").

Dado un punto (un inmueble), encuentra sus servicios cercanos CON coordenadas
(Places searchNearby) y traza la ruta peatonal real a cada uno (computeRoutes,
modo WALK), devolviendo la línea (polyline decodificada) + el tiempo exacto.

Va por el BACKEND: la GOOGLE_MAPS_API_KEY nunca toca el frontend. Si no hay key,
devuelve None y el mapa simplemente no muestra rutas.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy import text

from app.config import settings
from app.contracts.evidence_v0 import EvidenceRefV0, PersistencePolicy, SourceType
from app.contracts.place_v0 import (
    GeoPoint,
    MeasureStatus,
    NamedMeasureV0,
    NearbyPlaceV0,
    NearestTransitV0,
    PlaceContextV0,
    PlaceMeasureV0,
)
from app.database import engine
from app.entorno import _CATEGORIAS, _nombre_valido
from app.isocronas import isocrona
from app.walk_score import _haversine_m, walk_score_para

# Timeout por llamada a Google (Places/Directions). El path del mapa hace 2 secuenciales;
# 5s mantiene el peor caso en ~10s, holgado bajo el wait_for(13s) del endpoint.
_TIMEOUT = 5.0
_RADIO_M = 1500

# El foso degrada en silencio POR DISEÑO (si la capa propia falla, el comprador ve el
# entorno de Google en vez de un error). Pero degradar callado significa que el producto
# "funciona" mostrando menos verdad y nadie se entera — el género de fallo de
# docs/AUDITORIA_Fallos_Silenciosos_2026-07-31.md. La degradación se conserva; el
# silencio no.
log = logging.getLogger("foso")


def _avisar_capa_caida(donde: str, exc: Exception) -> None:
    """Registra una caída de la capa propia distinguiendo la causa.

    La distinción importa: que FALTE la vista es un problema de despliegue (la
    migración 023 no corrió en este entorno) y se arregla una vez; un error de
    conexión es transitorio. Tratarlos igual manda a buscar al lugar equivocado —
    misma lección que el incidente del cierre masivo: "no pude consultar" no es
    "no existe".
    """
    detalle = str(exc)
    if "pois_vivos" in detalle and ("does not exist" in detalle or "no existe" in detalle):
        log.error(
            "foso=capa_caida donde=%s causa=vista_ausente — la vista `pois_vivos` no "
            "existe en esta base: falta aplicar migrations/023_curacion_engancha_poi.sql. "
            "El entorno está cayendo a Google y la curación del corredor NO se aplica.",
            donde,
        )
    else:
        log.warning("foso=capa_caida donde=%s causa=%s: %s",
                    donde, type(exc).__name__, detalle[:300])


def _decode_polyline(enc: str) -> list[list[float]]:
    """Decodifica un polyline de Google (precisión 5) → lista de [lon, lat]."""
    coords: list[list[float]] = []
    index = lat = lng = 0
    n = len(enc)
    while index < n:
        for is_lat in (True, False):
            shift = result = 0
            while True:
                b = ord(enc[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if (result & 1) else (result >> 1)
            if is_lat:
                lat += delta
            else:
                lng += delta
        coords.append([lng / 1e5, lat / 1e5])
    return coords


# Categorías de vida diaria para "qué hay cerca" (diverso y DETERMINÍSTICO).
_CATS_ENTORNO = ["salud", "farmacia", "supermercado", "educacion", "parque", "centro_comercial"]

# ── Capa PROPIA (foso): pois_propios en PostGIS. Ver docs/SPEC_Foso_Capa_de_Datos.md ──
# Subtipos de transporte "masivos" (Metro/tren/terminal) — héroes de plusvalía, se
# priorizan sobre una simple parada de bus aunque estén más lejos (paridad con Google).
_TRANSPORTE_MASIVO = ["metro", "estacion_tren", "terminal_bus", "estacion"]
_RADIO_TRANSP_M = 3000  # el hub masivo puede estar más lejos (mismo criterio que Google)

# ⚠️ Las lecturas de entorno van contra la VISTA `pois_vivos`, NUNCA contra la tabla
# `pois_propios` (migración 023). La vista aplica el overlay de curación del corredor:
# un POI que un corredor marcó cerrado en terreno desaparece para TODOS los inmuebles
# del barrio, no solo para la ficha donde se capturó. Es la propagación que convierte
# cada visita en un activo acumulativo — el foso sobre el foso (SPEC_Foso §1.8).
#
# Y NO se filtra por `operativo` aquí: la vista ya lo resolvió, y hacerlo de nuevo
# rompería el caso "el origen lo dio de baja pero el corredor lo confirmó en terreno"
# (el humano estuvo ahí ayer; Overture es de hace un mes).
_PROPIOS_ENTORNO_SQL = text("""
    SELECT DISTINCT ON (categoria)
        id, categoria, nombre, marca, verificado_en,
        ST_Y(geom) AS lat, ST_X(geom) AS lon,
        ROUND(ST_Distance(geom::geography,
              ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography))::int AS distancia_m
    FROM pois_vivos
    WHERE categoria = ANY(:cats)
      AND ST_DWithin(geom::geography,
                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :max_m)
    ORDER BY categoria, geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
""")

_PROPIOS_TRANSPORTE_SQL = text("""
    SELECT id, nombre, verificado_en, ST_Y(geom) AS lat, ST_X(geom) AS lon,
        ROUND(ST_Distance(geom::geography,
              ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography))::int AS distancia_m,
        (categoria_overture = ANY(:masivo)) AS es_masivo
    FROM pois_vivos
    WHERE categoria = 'transporte'
      AND ST_DWithin(geom::geography,
                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :max_m)
    ORDER BY (categoria_overture = ANY(:masivo)) DESC,
             geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
    LIMIT 1
""")


def _fecha(v: object) -> str | None:
    """`verificado_en` (timestamptz o None) → 'AAAA-MM-DD' para la UI, o None.

    Mismo recorte que `info_verificacion()` en app/entorno_curacion.py: al comprador
    le sirve el día en que un corredor pisó el lugar, no la hora exacta.
    """
    if not v:
        return None
    return (v.isoformat() if hasattr(v, "isoformat") else str(v))[:10] or None


async def _servicios_propios(lat: float, lon: float) -> dict[str, dict]:
    """
    Servicio más cercano POR categoría desde NUESTRA capa (pois_propios, PostGIS).
    Reemplaza 7 llamadas a Google Places por 2 queries a la DB propia (el foso).

    Transporte: prioriza el hub masivo (Metro/terminal) aunque una parada esté más
    cerca — misma semántica que _mejor_transporte con Google.

    Devuelve {cat: item}. Una categoría AUSENTE = hueco en nuestra capa en este punto
    (periferia / fuera del bbox de Quito); el llamador la rellena con Google.
    """
    out: dict[str, dict] = {}
    try:
        async with engine.connect() as conn:
            filas = (await conn.execute(_PROPIOS_ENTORNO_SQL, {
                "lat": lat, "lon": lon, "max_m": _RADIO_M, "cats": _CATS_ENTORNO,
            })).mappings().all()
            for f in filas:
                out[f["categoria"]] = {
                    # Mismo criterio que en _nearest_propio: la marca solo cuando el
                    # nombre es genérico ("Farmacia", "Tienda"…).
                    "nombre": _nombre_poi(f["nombre"], f["marca"]),
                    "lat": f["lat"], "lon": f["lon"],
                    "distancia_m": f["distancia_m"], "cat": f["categoria"],
                    "marca": f["marca"], "fuente": "propio",
                    # Fecha en que un corredor pisó ESTE lugar (None = nadie todavía).
                    # Alimenta el flag `fresco` del Mapa Vivo y la insignia del anuncio.
                    "verificado_en": _fecha(f["verificado_en"]),
                    # Identidad del POI: lo que el corredor cierra/confirma en terreno.
                    "poi_id": f["id"],
                }
            tr = (await conn.execute(_PROPIOS_TRANSPORTE_SQL, {
                "lat": lat, "lon": lon, "max_m": _RADIO_TRANSP_M,
                "masivo": _TRANSPORTE_MASIVO,
            })).mappings().first()
            if tr:
                out["transporte"] = {
                    "nombre": tr["nombre"], "lat": tr["lat"], "lon": tr["lon"],
                    "distancia_m": tr["distancia_m"], "cat": "transporte",
                    "es_masivo": bool(tr["es_masivo"]), "fuente": "propio",
                    "verificado_en": _fecha(tr["verificado_en"]),
                    "poi_id": tr["id"],
                }
    except Exception as exc:  # noqa: BLE001 — si la capa/DB falla, el llamador cae a Google
        _avisar_capa_caida("_servicios_propios", exc)
        return {}
    return out


async def entorno_curable(lat: float, lon: float) -> list[dict]:
    """Los POIs que el corredor puede cerrar/confirmar en terreno, con su `poi_id`.

    Sale de `_servicios_propios` A PROPÓSITO — la MISMA query que arma el entorno que
    ve el comprador. Así lo que el corredor corrige es, por construcción, exactamente
    lo que se está mostrando; si se duplicara la consulta, las dos listas podrían
    divergir y el corredor estaría curando algo que nadie ve.

    Cada item trae el `poi_id` que convierte la curación en alcance CIUDAD (migración
    023). Los lugares que no estén en la capa propia no aparecen aquí: se curan por
    texto libre, como siempre.
    """
    servicios = await _servicios_propios(lat, lon)
    out: list[dict] = []
    for cat, s in servicios.items():
        if not s.get("poi_id"):
            continue
        out.append({
            "poi_id": s["poi_id"],
            "nombre": s.get("nombre") or _CAT_LABEL.get(cat, cat),
            "categoria": cat,
            "etiqueta": _CAT_LABEL.get(cat, cat),
            "emoji": _CAT_EMOJI.get(cat, "📍"),
            "distancia_m": s.get("distancia_m"),
            "verificado_en": s.get("verificado_en"),
        })
    out.sort(key=lambda x: (x["distancia_m"] is None, x["distancia_m"] or 0))
    return out


# La verificación de terreno que le corresponde a CADA inmueble. Un solo viaje a la DB
# para todo el panel — por tarjeta serían 2 queries × N.
#
# ⚠️ El DISTINCT ON por (activo, categoría) no es un detalle de rendimiento, es de
# HONESTIDAD: cuenta solo los POIs que el entorno REALMENTE muestra (el más cercano de
# cada categoría), no cualquiera dentro del radio. Un lugar verificado a 1.400 m que
# ninguna ficha exhibe no puede encender la insignia — eso sería inflar el dato, justo
# lo que el guardrail del pin-anillo prohíbe ("la calidez es registro, no pulgar en la
# balanza").
_VERIFICACION_ENTORNO_SQL = text("""
    WITH mostrados AS (
        SELECT DISTINCT ON (a.id, pv.categoria)
               a.id AS activo_id, pv.verificado_en
        FROM activos_inmutables a
        JOIN pois_vivos pv
          ON ST_DWithin(pv.geom::geography, a.geom::geography, :max_m)
        WHERE a.id = ANY(CAST(:ids AS uuid[])) AND a.geom IS NOT NULL
        ORDER BY a.id, pv.categoria, pv.geom <-> a.geom
    )
    SELECT activo_id, max(verificado_en) AS verificado_en
    FROM mostrados
    WHERE verificado_en IS NOT NULL
    GROUP BY activo_id
""")


async def verificacion_de_entorno(activo_ids: list[str]) -> dict[str, str]:
    """{activo_id: 'AAAA-MM-DD'} — cuándo pisó un corredor algún lugar de ese entorno.

    Es la propagación hecha visible: un corredor verifica la farmacia parado en el
    inmueble A y el inmueble B de enfrente hereda la insignia, porque comparten el POI.
    Sin esto la migración 023 acumula verdad que nadie ve.

    Ausente del dict = nadie ha caminado ese entorno todavía (≠ error).
    """
    if not activo_ids:
        return {}
    try:
        async with engine.connect() as conn:
            filas = (await conn.execute(_VERIFICACION_ENTORNO_SQL, {
                "ids": [str(i) for i in activo_ids], "max_m": _RADIO_M,
            })).mappings().all()
        return {str(f["activo_id"]): _fecha(f["verificado_en"]) for f in filas}
    except Exception as exc:  # noqa: BLE001 — sin insignia, nunca sin tarjetas
        _avisar_capa_caida("verificacion_de_entorno", exc)
        return {}


# Categorías que NUESTRA capa cubre (= CHECK de pois_propios, migración 021).
# Desde 2026-07-27 son TODAS: el branch "ruta a X" ya no llama a Google en ningún caso
# (Google solo entra si un punto queda fuera del bbox de la ciudad cargada).
_CATS_PROPIAS = {"salud", "farmacia", "supermercado", "educacion",
                 "parque", "centro_comercial", "transporte",
                 "iglesia", "seguridad"}

# "metro" / "terminal" en la frase → subtipos de nuestra capa (espejo de los tipos de Google).
_SUBTIPOS_PROPIOS = {
    "metro": ["metro", "estacion_tren", "estacion"],
    "terminal": ["terminal_bus"],
}

_PROPIOS_NEAREST_SQL = text("""
    SELECT nombre, marca, verificado_en,
        ST_Y(geom) AS lat, ST_X(geom) AS lon,
        ROUND(ST_Distance(geom::geography,
              ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography))::int AS distancia_m,
        (categoria_overture = ANY(:masivo)) AS es_masivo
    FROM pois_vivos
    WHERE categoria = :cat
      -- CAST(... AS text[]) y NO `:subtipos::text[]`: el `::` del cast se come el
      -- bindparam en SQLAlchemy y el parámetro queda literal en el SQL.
      AND (cardinality(CAST(:subtipos AS text[])) = 0
           OR categoria_overture = ANY(CAST(:subtipos AS text[])))
      AND ST_DWithin(geom::geography,
                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :max_m)
    ORDER BY (categoria_overture = ANY(:masivo)) DESC,
             geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
    LIMIT 8
""")


# Nombres que no dicen nada al usuario: si el POI trae `marca`, la marca es mejor
# etiqueta. Overture a veces deja el nombre en el genérico de la categoría con la marca
# aparte (93 filas así en Quito) — sin esto, "Farmacia" le ganaba a "Vanttive" a 180 m
# más cerca solo por tener la columna poblada.
_NOMBRES_GENERICOS = {
    "farmacia", "farmacias", "botica", "supermercado", "supermercados", "tienda",
    "minimarket", "mini market", "abarrotes", "hospital", "clinica", "clínica",
    "centro medico", "centro médico", "escuela", "colegio", "parque",
    "centro comercial", "mall",
}


def _nombre_poi(nombre: str | None, marca: str | None) -> str | None:
    """Etiqueta que ve el usuario: la marca solo cuando el nombre no aporta nada."""
    n = (nombre or "").strip()
    if marca and (not n or n.lower() in _NOMBRES_GENERICOS):
        return marca.strip()
    return n or marca


async def _nearest_propio(lat: float, lon: float, cat: str,
                          subtipos: list[str] | None = None) -> dict | None:
    """El POI más cercano de UNA categoría desde nuestra capa (pois_propios).

    Espejo de `_nearest_categoria` (Google) para el branch "ruta a X" del map-chat:
    mismo radio (3 km), misma preferencia de marca reconocible dentro del margen, y
    mismo shape de retorno + `fuente: "propio"`. Devuelve None si la categoría no está
    en nuestra capa o no hay nada cerca → el llamador cae a Google.
    """
    if cat not in _CATS_PROPIAS:
        return None
    try:
        async with engine.connect() as conn:
            filas = (await conn.execute(_PROPIOS_NEAREST_SQL, {
                "lat": lat, "lon": lon, "cat": cat, "max_m": 3000,
                "subtipos": subtipos or [], "masivo": _TRANSPORTE_MASIVO,
            })).mappings().all()
    except Exception as exc:  # noqa: BLE001 — si la capa/DB falla, el llamador cae a Google
        _avisar_capa_caida("_nearest_propio", exc)
        return None
    if not filas:
        return None

    cands = [{"nombre": _nombre_poi(f["nombre"], f["marca"]), "lat": f["lat"], "lon": f["lon"],
              "distancia_m": f["distancia_m"], "cat": cat, "fuente": "propio",
              "es_masivo": bool(f["es_masivo"]),
              "verificado_en": _fecha(f["verificado_en"])} for f in filas]

    elegido = cands[0]
    if cat != "transporte":
        # Misma regla que con Google: una marca reconocible gana si está dentro del margen.
        # Se juzga por el NOMBRE YA RESUELTO (`_nombre_poi`), no por la columna `marca`
        # a secas: lo que decide es que el usuario reconozca la etiqueta que va a leer.
        elegido = next(
            (c for c in cands
             if _es_marca(c["nombre"])
             and c["distancia_m"] <= cands[0]["distancia_m"] + _MARGEN_MARCA_M),
            cands[0],
        )
    return elegido


async def _servicios_con_coords(lat: float, lon: float, key: str, n: int = 6) -> list[dict]:
    """
    El servicio más cercano POR CATEGORÍA. FUENTE PRIMARIA: nuestra capa propia
    (pois_propios, el foso). Google queda como FALLBACK solo para las categorías que
    nuestra capa no cubre en este punto (periferia / fuera de Quito). Así el entorno
    deja de gastar cuota de Google en cada consulta, salvo en los huecos reales.

    Antes: 7 llamadas a Google Places en cada consulta. Ahora: 2 queries a la DB
    propia + Google solo si falta alguna categoría.
    """
    propios = await _servicios_propios(lat, lon)

    # Fallback a Google SOLO para lo que falta en nuestra capa (con key disponible).
    faltantes = [c for c in _CATS_ENTORNO if c not in propios]
    fb_tareas, fb_labels = [], []
    if key:
        if "transporte" not in propios:
            fb_tareas.append(_mejor_transporte(lat, lon, key)); fb_labels.append("transporte")
        for c in faltantes:
            fb_tareas.append(_nearest_categoria(lat, lon, c, key)); fb_labels.append(c)
    if fb_tareas:
        res = await asyncio.gather(*fb_tareas, return_exceptions=True)
        for lab, r in zip(fb_labels, res):
            if isinstance(r, dict):
                r["cat"] = lab
                r.setdefault("fuente", "google")
                propios[lab] = r

    transporte = propios.get("transporte")
    otros = sorted([v for k, v in propios.items() if k != "transporte"],
                   key=lambda i: i["distancia_m"])

    # Priorizar transporte (aunque sea el más lejano) + completar por cercanía, sin duplicar nombres.
    out: list[dict] = []
    vistos: set[str] = set()
    for it in ([transporte] if transporte else []) + otros:
        if not it or it["nombre"] in vistos:
            continue
        out.append(it); vistos.add(it["nombre"])
        if len(out) >= n:
            break
    out.sort(key=lambda i: i["distancia_m"])
    return out


async def _ruta_a_pie(client: httpx.AsyncClient, o_lat: float, o_lon: float,
                      d_lat: float, d_lon: float, key: str) -> dict | None:
    body = {
        "origin": {"location": {"latLng": {"latitude": o_lat, "longitude": o_lon}}},
        "destination": {"location": {"latLng": {"latitude": d_lat, "longitude": d_lon}}},
        "travelMode": "WALK",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline",
    }
    r = await client.post("https://routes.googleapis.com/directions/v2:computeRoutes", json=body, headers=headers)
    r.raise_for_status()
    routes = r.json().get("routes", [])
    if not routes:
        return None
    rt = routes[0]
    dur = str(rt.get("duration", "0s"))
    secs = int(dur[:-1]) if dur.endswith("s") and dur[:-1].isdigit() else 0
    enc = (rt.get("polyline") or {}).get("encodedPolyline", "")
    return {
        "duracion_min": max(1, round(secs / 60)),
        "distancia_m": rt.get("distanceMeters"),
        "coords": _decode_polyline(enc) if enc else [],
    }


# ── Mapa conversacional: pregunta → acciones de mapa ────────────────────────
_PALABRAS_CAT = {
    # "bus" SIN límites de palabra hacía match en "BUSco un colegio" → ruta al Metro (bug
    # real, cazado por regresión 2026-07-28). El caso "bus" suelto lo captura la rama 0b
    # del panorama con \b; aquí queda "autobus" que no colisiona con nada.
    "transporte": ["metro", "estacion", "estación", "terminal", "parada", "autobus", "autobús", "transporte"],
    "educacion": ["colegio", "escuela", "educacion", "educación", "universidad", "guarderia", "guardería"],
    "salud": ["hospital", "salud", "clinica", "clínica", "consultorio", "medico", "médico", "doctor"],
    "farmacia": ["farmacia", "botica"],
    "supermercado": ["super", "mercado", "supermercado", "tienda", "abasto", "víveres", "viveres"],
    "parque": ["parque", "area verde", "área verde", "verde", "jardin", "jardín"],
    "iglesia": ["iglesia", "templo", "misa", "parroquia"],
    "seguridad": ["upc", "policia", "policía", "seguridad", "patrulla"],
    "centro_comercial": ["centro comercial", "mall", "quicentro", "comercial"],
}
_CAT_GOOGLE = {c["key"]: [c["google"]] for c in _CATEGORIAS}
_CAT_GOOGLE["transporte"] = ["subway_station", "train_station", "bus_station", "transit_station"]
_CAT_LABEL = {
    "transporte": "🚇 transporte", "educacion": "🏫 educación", "salud": "🏥 salud",
    "farmacia": "💊 farmacia", "supermercado": "🛒 supermercado", "parque": "🌳 parque",
    # "seguridad" a secas se lee como una cualidad del barrio ("¿es seguro?"), que el
    # canon Fair Housing prohíbe afirmar. El rótulo nombra el SERVICIO: la UPC es un
    # lugar con dirección, como un hospital. Ver migración 021.
    "iglesia": "⛪ iglesia", "seguridad": "🛡️ UPC (policía comunitaria)",
    "centro_comercial": "🛍️ centro comercial",
}
# Ícono + color por categoría (capa visual semántica, estilo Google Maps).
_CAT_EMOJI = {
    "transporte": "🚇", "educacion": "🏫", "salud": "🏥", "farmacia": "💊", "supermercado": "🛒",
    "parque": "🌳", "iglesia": "⛪", "seguridad": "🛡️", "centro_comercial": "🛍️",
}
_CAT_COLOR = {
    "transporte": "#5EEAD4", "educacion": "#9B8CFF", "salud": "#E0685A", "farmacia": "#5EEAD4",
    "supermercado": "#E5C06A", "parque": "#2DBDB6", "iglesia": "#C9C6D6", "seguridad": "#7FB2FF",
    "centro_comercial": "#E5C06A",
}


# Marcas reconocibles (LATAM): se prefieren como destino aunque un genérico esté un poco más cerca.
_MARCAS_ANCLA = (
    "tuti", "supermaxi", "megamaxi", "santa maría", "santa maria", "mi comisariato",
    "akí", "aki", "gran akí", "tía", "tia", "coral",                       # supermercados
    "fybeca", "sana sana", "pharmacys", "medicity", "cruz azul", "difare",  # farmacias
    "quicentro", "el recreo", "scala", "san luis", "el condado", "granados",
    "el bosque", "paseo san francisco", "ventura", "el jardín", "el jardin",  # centros comerciales
)
_MARGEN_MARCA_M = 350  # una marca gana si está a ≤ (más cercano + este margen)


def _es_marca(nombre: str | None) -> bool:
    n = (nombre or "").lower()
    return any(m in n for m in _MARCAS_ANCLA)


async def _nearest_categoria(lat: float, lon: float, cat: str, key: str, tipos: list[str] | None = None) -> dict | None:
    body = {
        "includedTypes": tipos or _CAT_GOOGLE.get(cat, []), "maxResultCount": 8, "rankPreference": "DISTANCE",
        "languageCode": "es",
        "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": 3000.0}},
    }
    headers = {"Content-Type": "application/json", "X-Goog-Api-Key": key,
               "X-Goog-FieldMask": "places.displayName,places.location"}
    verify = settings.ssl_verify.lower() != "false"
    try:
        async with httpx.AsyncClient(verify=verify, timeout=_TIMEOUT) as c:
            r = await c.post("https://places.googleapis.com/v1/places:searchNearby", json=body, headers=headers)
            r.raise_for_status()
            candidatos = []
            for pl in r.json().get("places", []):
                loc = pl.get("location", {})
                nombre = (pl.get("displayName") or {}).get("text")
                if "latitude" in loc and _nombre_valido(nombre):
                    candidatos.append({"nombre": nombre, "lat": loc["latitude"], "lon": loc["longitude"],
                                       "distancia_m": int(_haversine_m(lat, lon, loc["latitude"], loc["longitude"]))})
            if not candidatos:
                return None
            candidatos.sort(key=lambda c: c["distancia_m"])
            nearest = candidatos[0]
            # Prefiere una marca reconocible si está razonablemente cerca (mejor destino para el usuario).
            marca = next((c for c in candidatos
                          if _es_marca(c["nombre"]) and c["distancia_m"] <= nearest["distancia_m"] + _MARGEN_MARCA_M), None)
            return marca or nearest
    except Exception:  # noqa: BLE001
        pass
    return None


# ── Recorrido con Aura: tour narrado de la zona (la "experiencia", no la función) ──
def _min_pie(d_m: int | float | None) -> int:
    """Metros → minutos a pie (~80 m/min)."""
    return max(1, round((d_m or 0) / 80))


def _nombre_limpio(n: str | None, max_len: int = 42) -> str:
    """Recorta nombres kilométricos de Google (corta en separadores y por longitud)."""
    if not n:
        return "este lugar"
    # Google a veces devuelve "Nombre | keyword SEO | keyword | …": nos quedamos con lo 1ro.
    for sep in (" | ", " - ", " — ", " · ", ", "):
        if sep in n:
            n = n.split(sep)[0].strip()
            break
    n = n.strip()
    if len(n) > max_len:
        n = n[:max_len].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return n or "este lugar"


def _interpreta_walk(ws: int | None) -> str:
    if ws is None:
        return "Es una zona con su propio ritmo."
    if ws >= 90:
        return f"Con una caminabilidad de {ws}/100, casi todo está a pie: podrías vivir sin auto."
    if ws >= 75:
        return f"Caminabilidad {ws}/100 — muy caminable; lo esencial lo tienes a la mano."
    if ws >= 55:
        return f"Caminabilidad {ws}/100 — caminable para lo básico; para el resto, un trayecto corto."
    return f"Caminabilidad {ws}/100 — es una zona más de auto que de caminata."


def _aura(ws: int | None, parque: dict | None, transporte: dict | None) -> str:
    verde, metro = parque is not None, transporte is not None
    if ws and ws >= 85 and verde and metro:
        return "conveniencia urbana con pulmón verde"
    if ws and ws >= 85 and metro:
        return "vida urbana conectada, todo a un paso"
    if verde and not metro:
        return "un remanso residencial, verde y tranquilo"
    if metro:
        return "una zona bien conectada con la ciudad"
    if ws and ws >= 70:
        return "un barrio práctico para el día a día"
    return "una zona en crecimiento, con carácter propio"


async def _mejor_transporte(lat: float, lon: float, key: str) -> dict | None:
    """
    Prioriza el hub MASIVO (Metro/tren) aunque haya una parada de bus más cerca.
    Marca es_masivo para NO confundir un Metro con una simple parada de bus.
    """
    metro = await _nearest_categoria(lat, lon, "transporte", key,
                                     tipos=["subway_station", "train_station", "light_rail_station"])
    if metro:
        metro["es_masivo"] = True
        return metro
    bus = await _nearest_categoria(lat, lon, "transporte", key, tipos=["bus_station", "transit_station"])
    if bus:
        bus["es_masivo"] = False
    return bus


async def recorrido_zona(lat: float, lon: float) -> dict:
    """Genera un 'Recorrido con Aura': 4-6 escenas auto-narradas sobre la zona real."""
    key = settings.google_maps_api_key
    from app.agent.tools import _reverse_geocode  # lazy: evita import circular

    tareas: dict = {"geo": _reverse_geocode(lat, lon), "walk": walk_score_para(lat, lon)}
    if key:
        tareas["parque"] = _nearest_categoria(lat, lon, "parque", key)
        tareas["transporte"] = _mejor_transporte(lat, lon, key)
        tareas["super"] = _nearest_categoria(lat, lon, "supermercado", key)
        tareas["salud"] = _nearest_categoria(lat, lon, "salud", key)
    vals = await asyncio.gather(*tareas.values(), return_exceptions=True)
    data = {k: (v if not isinstance(v, Exception) else None) for k, v in zip(tareas.keys(), vals)}

    geo, walk = data.get("geo") or {}, data.get("walk") or {}
    barrio = geo.get("barrio") or geo.get("ciudad") or "esta zona"
    ciudad = geo.get("ciudad")
    ws = walk.get("walk_score")
    pq, tr = data.get("parque"), data.get("transporte")

    escenas: list[dict] = []

    # 1) Identidad de la zona
    lugar = barrio + (f", {ciudad}" if ciudad and ciudad != barrio else "")
    escenas.append({
        "titulo": f"📍 {barrio}",
        "narracion": f"Bienvenido a **{lugar}**. {_interpreta_walk(ws)}",
        "centro": [lon, lat], "zoom": 15.2, "origen": True,
    })

    # 2) El pulmón verde
    if pq:
        nom_pq = _nombre_limpio(pq["nombre"])
        escenas.append({
            "titulo": "🌳 El pulmón del barrio",
            "narracion": f"A {_min_pie(pq['distancia_m'])} min a pie tienes **{nom_pq}** — el lugar para "
                         "correr al amanecer, sacar al perro o un domingo en familia.",
            "centro": [pq["lon"], pq["lat"]], "zoom": 16,
            "puntos": [{"coords": [pq["lon"], pq["lat"]], "etiqueta": f"🌳 {nom_pq}", "color": "#2DBDB6"}],
        })

    # 3) Cómo te mueves (ruta peatonal real al hub de transporte)
    if tr and key:
        try:
            async with httpx.AsyncClient(verify=settings.ssl_verify.lower() != "false", timeout=_TIMEOUT) as c:
                ruta = await _ruta_a_pie(c, lat, lon, tr["lat"], tr["lon"], key)
        except Exception:  # noqa: BLE001
            ruta = None
        es_masivo = any(w in tr["nombre"].lower() for w in ("metro", "estación", "estacion", "terminal"))
        plus = " Estar a pasos del transporte masivo es de las señales que más empujan la plusvalía." if es_masivo else ""
        nom_tr = _nombre_limpio(tr["nombre"])
        if ruta and ruta.get("coords"):
            escenas.append({
                "titulo": "🚶 Tu conexión con la ciudad",
                "narracion": f"**{nom_tr}** está a {ruta['duracion_min']} min caminando.{plus}",
                "centro": [(lon + tr["lon"]) / 2, (lat + tr["lat"]) / 2], "zoom": 14.8,
                "ruta": {"coords": ruta["coords"], "destino": [tr["lon"], tr["lat"]],
                         "etiqueta": f"🚶 {ruta['duracion_min']} min · {nom_tr}", "color": "#5EEAD4"},
            })
        else:
            escenas.append({
                "titulo": "🚶 Tu conexión con la ciudad",
                "narracion": f"**{nom_tr}** a {_min_pie(tr['distancia_m'])} min a pie.{plus}",
                "centro": [tr["lon"], tr["lat"]], "zoom": 15.5,
                "puntos": [{"coords": [tr["lon"], tr["lat"]], "etiqueta": nom_tr, "color": "#5EEAD4"}],
            })

    # 4) Lo cotidiano, a la mano
    cotid = [s for s in (data.get("super"), data.get("salud")) if s]
    if cotid:
        puntos, nombres = [], []
        for s, col in zip(cotid, ("#E5C06A", "#E0685A")):
            nom_s = _nombre_limpio(s["nombre"])
            puntos.append({"coords": [s["lon"], s["lat"]], "etiqueta": f"{nom_s} ({_min_pie(s['distancia_m'])} min)", "color": col})
            nombres.append(f"**{nom_s}** a {_min_pie(s['distancia_m'])} min")
        escenas.append({
            "titulo": "🛒 Lo cotidiano, a la mano",
            "narracion": "Para el día a día: " + " y ".join(nombres) + ".",
            "centro": [sum(p["coords"][0] for p in puntos) / len(puntos), sum(p["coords"][1] for p in puntos) / len(puntos)],
            "zoom": 15.2, "puntos": puntos,
        })

    # 5) El aura (síntesis)
    cierre = "Verde, conectada y caminable." if (pq and tr and ws and ws >= 75) else "Un lugar con identidad propia para vivir."
    escenas.append({
        "titulo": "✨ El aura de la zona",
        "narracion": f"En síntesis, **{barrio}** es **{_aura(ws, pq, tr)}**. {cierre}",
        "centro": [lon, lat], "zoom": 14.4, "origen": True,
    })

    return {
        "texto": f"🎬 Iniciando recorrido por **{barrio}** — {len(escenas)} escenas.",
        "acciones": [{"tipo": "tour", "escenas": escenas}],
    }


# ══ PlaceContextV0 · el objeto es la autoridad ═══════════════════════════════
#
# UNIDAD PLAN04-1.2. Antes de esto, `PlaceContextV0` existía como contrato y NADIE lo
# producía: el dato estaba, el objeto no. Aquí se invierte la dirección.
#
#   ANTES   fetch ─→ prosa                      (el string era el dato)
#   AHORA   fetch ─→ MateriaDeZona ─→ objeto ─→ prosa y salida legacy
#
# El fetch ocurre UNA sola vez, en `_recolectar_zona`. Todo lo demás es puro: dado el
# mismo material, el mismo objeto y la misma prosa. Eso es lo que hace la unidad
# probable sin red.
#
# LO QUE EL CONTRATO NO MODELA, y por qué la salida legacy no puede derivarse ENTERA:
# `PlaceContextV0` describe el LUGAR (caminabilidad, transporte, servicios cercanos).
# No tiene sitio para el reverse-geocode (`lugar`) ni para el volcado crudo de
# `servicios`, y `pois_analizados` es un detalle del método, no una dimensión. Esos tres
# viajan desde la materia prima, marcados uno por uno. Inventarles un hueco en el
# contrato sería decidir el diseño de F1 desde aquí.


@dataclass(frozen=True)
class MateriaDeZona:
    """Lo que devolvió el ÚNICO fetch, sin interpretar.

    Existe para separar «lo que se recuperó» de «lo que se afirma». Mientras esto era
    variables locales dentro de `analizar_zona`, la única forma de probar el ensamblaje
    era hacer red.
    """

    lat: float
    lon: float
    lugar: dict
    walk: dict
    """`{}` cuando `walk_score_para` devolvió None — Overpass no respondió. Distinto de
    un dict con `pois_analizados=0`, que es Overpass respondiendo que no hay nada."""
    servicios: list[dict]
    se_consultaron_servicios: bool
    """Hubo llave de Google y se preguntó. Sin esto, «cero servicios» y «no se preguntó»
    serían indistinguibles, que es justo la confusión que el contrato prohíbe."""
    transporte: dict | None
    transporte_distancia_m: int | float | None
    transporte_minutos: int | float | None
    transporte_ruta_medida: bool
    """True = caminata real por calles (Google Routes). False = estimación recta ÷ 80."""
    recuperado_en: datetime


def _num(v):
    """Renderiza como entero lo que es entero. Hoy TODOS los escalares de la prosa son
    `int` —las distancias salen de SQL con `::int` y los minutos de `round()`—, así que
    esto reproduce el texto de siempre después de pasar por el contrato, donde los
    campos son `float`. Sin esto, «~640 m» se convertiría en «~640.0 m»."""
    if v is None:
        return v
    f = float(v)
    return int(f) if f.is_integer() else v


async def _recolectar_zona(lat: float, lon: float) -> MateriaDeZona:
    """EL ÚNICO FETCH. No interpreta nada: recupera y devuelve."""
    from app.agent.tools import _reverse_geocode  # lazy: evita import circular
    key = settings.google_maps_api_key

    async def _serv():
        return await _servicios_con_coords(lat, lon, key, 6) if key else []

    geo, walk, servicios = await asyncio.gather(
        _reverse_geocode(lat, lon), walk_score_para(lat, lon), _serv(),
        return_exceptions=True,
    )
    geo = geo if isinstance(geo, dict) else {}
    walk = walk if isinstance(walk, dict) else {}
    servicios = servicios if isinstance(servicios, list) else []

    transporte = next((s for s in servicios if s.get("cat") == "transporte"), None)
    dist_m = minutos = None
    medida = False
    if transporte:
        # Caminata REAL por calles (Google Routes), NO en línea recta: la recta miente
        # (ej. Metro a ~640 m en recta = "8 min", pero ~1.5 km caminando = 19 min).
        # Fallback al estimado recta ÷ 80 si Routes falla o no hay coords.
        dist_m = transporte["distancia_m"]
        minutos = _min_pie(dist_m)
        if key and transporte.get("lat") is not None and transporte.get("lon") is not None:
            try:
                async with httpx.AsyncClient(verify=settings.ssl_verify.lower() != "false", timeout=_TIMEOUT) as c:
                    ruta = await _ruta_a_pie(c, lat, lon, transporte["lat"], transporte["lon"], key)
                if ruta and ruta.get("duracion_min"):
                    minutos = ruta["duracion_min"]
                    dist_m = ruta.get("distancia_m") or dist_m
                    medida = True
            except Exception:  # noqa: BLE001
                pass  # nos quedamos con el estimado en línea recta

    return MateriaDeZona(
        lat=lat, lon=lon, lugar=geo, walk=walk, servicios=servicios,
        se_consultaron_servicios=bool(key), transporte=transporte,
        transporte_distancia_m=dist_m, transporte_minutos=minutos,
        transporte_ruta_medida=medida,
        recuperado_en=datetime.now(timezone.utc),
    )


# ── La identidad de la evidencia ─────────────────────────────────────────────
#
# `EvidenceRefV0.evidence_id` cae por defecto en un `uuid4`, y ese default es correcto
# para quien crea evidencia suelta. Aquí no sirve: dos ensamblajes del MISMO material
# producían dos objetos que solo se diferenciaban en las asas, así que «el objeto es el
# mismo» dejaba de ser comprobable —no se podía comparar el JSON— y cualquier consumidor
# que cachee o compare por serialización veía cambios donde no los hay.
#
# Tampoco vale `hash()`: `PYTHONHASHSEED` sala el hash de las cadenas en cada proceso, de
# modo que dos corridas darían asas distintas para el mismo contenido. Se usa `uuid5`, que
# es la misma solución que `app/buyer/reductor.py` ya tomó para la evidencia declarada.
#
# QUÉ ENTRA EN LA IDENTIDAD, y por qué cada pieza:
#
#   · el PUNTO — sin él, dos lugares distintos con la misma metodología compartirían
#     `evidence_id`, y `DecisionContextV0` resuelve sus referencias por ese id: la
#     colisión no sería cosmética, sería citar la evidencia de otro lugar.
#   · el INSTANTE de recuperación — dos lecturas distintas son dos evidencias distintas
#     aunque digan lo mismo; el id no debe fingir que son una sola.
#   · la DIMENSIÓN que respalda — la misma consulta acredita cosas distintas.
#   · el ORIGEN y el CONTENIDO — proveedor, metodología y limitaciones.
#
# NO entra el valor medido, por la misma razón que en el reductor de Buyer: si dos
# lecturas iguales produjeran valores distintos, queremos el mismo id y dos objetos
# distintos, para que la divergencia se vea en vez de esconderse tras dos asas.
_NAMESPACE_EVIDENCIA_LUGAR = uuid.uuid5(
    uuid.NAMESPACE_URL, "contexto.ai/place/evidence/v0"
)


def _identidad_evidencia(materia: MateriaDeZona, dimension: str, campos: dict) -> str:
    """`uuid5` sobre *(punto, instante, dimensión, origen, contenido)*. Determinista."""
    tipo = campos["source_type"]
    semilla = "\x1f".join((
        repr(materia.lat),
        repr(materia.lon),
        materia.recuperado_en.isoformat(),
        dimension,
        tipo.value if isinstance(tipo, SourceType) else str(tipo),
        campos.get("provider") or "",
        campos.get("source_id") or "",
        campos.get("methodology") or "",
        "\x1e".join(campos.get("limitations") or ()),
    ))
    return str(uuid.uuid5(_NAMESPACE_EVIDENCIA_LUGAR, semilla))


def _evidencia(materia: MateriaDeZona, *, dimension: str, **campos) -> EvidenceRefV0:
    """Toda evidencia de esta unidad es de una lectura en vivo: se usa y se tira."""
    campos.setdefault("persistence_policy", PersistencePolicy.RUNTIME_ONLY)
    campos.setdefault("observed_at", None)
    return EvidenceRefV0(
        evidence_id=_identidad_evidencia(materia, dimension, campos),
        retrieved_at=materia.recuperado_en,
        **campos,
    )


# ── De dónde salió cada POI, LEÍDO del dato ──────────────────────────────────
#
# `_servicios_con_coords` mezcla DOS orígenes en una sola lista y lo marca uno por uno en
# `fuente`: `"propio"` es nuestra capa (`pois_propios`, PostGIS) y `"google"` es el relleno
# de Google Places para las categorías que la capa no cubre en ese punto.
#
# Hasta PLAN04-1.2-R1 la lista entera se acreditaba a Google Places. Es decir: un
# supermercado de nuestra propia capa —el foso— se atribuía a un tercero, y con la llave
# de Google ausente se seguía afirmando lo mismo. Es el defecto de E0.3 otra vez, con otra
# ropa: la procedencia viajaba como convención (el nombre de la función) en vez de leerse
# del dato, que es quien la sabe.
_ORIGEN_DE_LA_CAPA_DE_POIS: dict[str, tuple[SourceType, str]] = {
    "propio": (SourceType.OWN_MEASUREMENT, "contexto-capa-propia"),
    "google": (SourceType.PROVIDER_API, "google-places"),
}

_METODO_SERVICIO = {
    "propio": ("servicio más cercano por categoría en la capa propia de POIs, con la "
               "distancia calculada en PostGIS desde el punto consultado"),
    "google": ("servicio más cercano por categoría según Google Places, usado solo para "
               "las categorías que la capa propia no cubre en este punto"),
}

_METODO_PARADA = {
    "propio": ("parada más cercana en la capa propia de POIs, priorizando el hub masivo "
               "aunque otra parada esté más cerca"),
    "google": "parada de transporte más cercana según Google Places",
}

_SIN_ORIGEN_DECLARADO = (
    "la capa de POIs devolvió el dato sin declarar su origen: su procedencia no se puede "
    "acreditar, y un valor sin procedencia no se presenta como disponible"
)


def _evidencia_de_poi(materia: MateriaDeZona, *, dimension: str, fuente,
                      metodos: dict[str, str]) -> EvidenceRefV0 | None:
    """La procedencia de un POI, derivada de su campo `fuente`.

    Devuelve `None` cuando `fuente` no es una de las que la capa produce. NO se inventa un
    origen por defecto: eso es exactamente lo que se vino a cerrar. Quien llama decide qué
    hacer si eso deja la medida sin ninguna evidencia — y el contrato ya dice qué: sin
    procedencia no hay valor disponible.
    """
    origen = _ORIGEN_DE_LA_CAPA_DE_POIS.get(fuente or "")
    if origen is None:
        return None
    tipo, proveedor = origen
    return _evidencia(materia, dimension=dimension, source_type=tipo, provider=proveedor,
                      methodology=metodos[fuente])


def _medir_caminabilidad(materia: MateriaDeZona) -> PlaceMeasureV0[float]:
    """La procedencia de E0.3, hecha estructura. TRES casos, y ninguno se confunde.

      1. el proveedor no respondió       → insufficient_evidence, sin valor
      2. respondió y no había ni un POI  → available, valor 0, con evidencia y con la
                                           limitación de cobertura
      3. respondió con POIs              → available, con el valor calculado

    EL CASO 2 ES EL QUE COSTÓ UNA ADJUDICACIÓN. La tentación es tratarlo como ausencia
    de dato, y es lo contrario: la consulta se hizo, la respuesta llegó, y el cálculo
    sobre esa respuesta da 0. Eso ES una medición —«miramos OSM alrededor de este punto
    y la consulta no devolvió POIs relevantes»— y borrarla perdería información real.
    Decir «no hay nada caminable» sería otra cosa: una afirmación sobre el barrio que
    este dato no sostiene.

    Lo que sí exige es declarar QUÉ no puede sostener: un 0 por cobertura nula no
    distingue «zona sin comercios» de «zona que OSM no tiene mapeada», y confundirlas
    penalizaría a los barrios peor cartografiados, que suelen ser los más pobres. Esa
    limitación viaja en la medida, no en un comentario.

    El caso 1 es `insufficient_evidence` y no `unknown` porque la dimensión SÍ se evaluó:
    se preguntó y no hubo respuesta. `unknown` diría que ni se intentó.

    DOS EVIDENCIAS, NO UNA (PLAN04-1.2-R1). El puntaje no lo publica OSM: lo calcula
    Contexto sobre insumos de OSM. Fundirlo en una sola referencia con
    `provider="overpass"` atribuía nuestro método al proveedor de los datos —y borraba
    de paso que el método es nuestro—. Van separadas: el cálculo es `own_measurement` de
    Contexto, los insumos son el dataset público consultado por Overpass.
    """
    if not materia.walk:
        return PlaceMeasureV0[float](
            status=MeasureStatus.INSUFFICIENT_EVIDENCE,
            limitations=(
                "la capa de POIs no respondió: se consultó y no hubo lectura sobre la "
                "que calcular nada",
            ),
        )

    valor = materia.walk.get("walk_score")
    if valor is None:
        return PlaceMeasureV0[float](
            status=MeasureStatus.INSUFFICIENT_EVIDENCE,
            limitations=("la respuesta llegó sin puntaje de caminabilidad",),
        )

    pois = materia.walk.get("pois_analizados", 0) or 0
    return PlaceMeasureV0[float](
        status=MeasureStatus.AVAILABLE,
        value=float(valor),
        evidence=(
            _evidencia(
                materia,
                dimension="walkability",
                source_type=SourceType.OWN_MEASUREMENT,
                provider="contexto",
                methodology=(
                    f"walk score calculado por Contexto sobre {pois} POIs, con "
                    "decaimiento por distancia y pesos por categoría"
                ),
            ),
            _evidencia(
                materia,
                dimension="walkability",
                source_type=SourceType.PUBLIC_DATASET,
                provider="overpass",
                methodology=(
                    f"{pois} POIs de OpenStreetMap consultados en vivo por Overpass "
                    "alrededor del punto: son los INSUMOS del cálculo, no el puntaje"
                ),
            ),
        ),
        limitations=() if pois else (
            "cobertura nula: la consulta no devolvió ni un POI, así que este 0 no "
            "distingue una zona sin comercios de una zona que OSM no tiene mapeada",
        ),
    )


def _medir_transporte(materia: MateriaDeZona) -> PlaceMeasureV0[NearestTransitV0]:
    """La parada más cercana, con las DOS procedencias que la producen (PLAN04-1.2-R1).

    Descubrir la parada y medir la caminata hasta ella son dos actos distintos, de dos
    orígenes distintos, y hasta R1 compartían una sola referencia cuyo `provider` iba
    cambiando: cuando Google Routes medía la ruta, la evidencia decía `google-routes` y
    de dónde había salido la parada —a menudo nuestra propia capa— desaparecía. Se
    perdía justo la mitad que acredita el foso.

    Ahora el descubrimiento siempre está, leído de `fuente`, y la de Routes se añade
    SOLO cuando midió de verdad. Que la de Routes exista o no es, además, la única señal
    estructural de si `distance_m` es una caminata por calles o una línea recta.
    """
    t = materia.transporte
    if not t:
        if not materia.se_consultaron_servicios:
            return PlaceMeasureV0[NearestTransitV0](
                status=MeasureStatus.UNKNOWN,
                limitations=("no se consultó el proveedor de servicios",),
            )
        return PlaceMeasureV0[NearestTransitV0](
            status=MeasureStatus.INSUFFICIENT_EVIDENCE,
            limitations=("se consultó y no apareció ninguna parada de transporte",),
        )

    descubrimiento = _evidencia_de_poi(
        materia, dimension="nearest_transit", fuente=t.get("fuente"),
        metodos=_METODO_PARADA,
    )
    ruta = _evidencia(
        materia,
        dimension="nearest_transit",
        source_type=SourceType.PROVIDER_API,
        provider="google-routes",
        methodology=(
            "caminata real por calles hasta la parada, medida con Google Routes; de "
            "aquí salen la distancia y la duración cuando la medición existe"
        ),
    ) if materia.transporte_ruta_medida else None

    evidencia = tuple(e for e in (descubrimiento, ruta) if e is not None)
    if not evidencia:
        return PlaceMeasureV0[NearestTransitV0](
            status=MeasureStatus.INSUFFICIENT_EVIDENCE,
            limitations=(_SIN_ORIGEN_DECLARADO,),
        )

    # `mode` recoge la ÚNICA distinción que la capa de POIs expone en esta costura:
    # masivo (metro, estación, terminal) frente a parada. Escribir "metro" aquí sería
    # inventar precisión: una terminal terrestre no es un metro.
    masivo = bool(t.get("es_masivo", False))
    return PlaceMeasureV0[NearestTransitV0](
        status=MeasureStatus.AVAILABLE,
        value=NearestTransitV0(
            distance_m=float(materia.transporte_distancia_m),
            mode="masivo" if masivo else "parada",
            name=_nombre_limpio(t["nombre"]),
        ),
        evidence=evidencia,
    )


def _medir_minutos_a_pie(materia: MateriaDeZona) -> NamedMeasureV0 | None:
    """Los minutos a pie hasta la parada.

    Van en `environment` y NO en `travel_to_anchors`: ese campo declara, por contrato,
    el trayecto hasta un ancla DEL COMPRADOR, correlacionado por `anchor_id`. Una parada
    de bus no es un ancla de nadie, y meterla ahí colonizaría con Place una costura que
    el contrato reserva para Buyer.

    Aquí la procedencia sí distingue lo medido de lo estimado, que en la prosa de hoy es
    invisible: «19 min a pie» se lee igual venga de Google Routes o de dividir la recta
    entre 80.
    """
    if materia.transporte_minutos is None:
        return None
    medida = materia.transporte_ruta_medida
    return NamedMeasureV0(
        dimension="transporte_minutos_a_pie",
        measure=PlaceMeasureV0[float](
            status=MeasureStatus.AVAILABLE,
            value=float(materia.transporte_minutos),
            evidence=(
                _evidencia(
                    materia,
                    dimension="transporte_minutos_a_pie",
                    source_type=(SourceType.PROVIDER_API if medida
                                 else SourceType.HEURISTIC_ESTIMATE),
                    provider="google-routes" if medida else None,
                    methodology=("duración peatonal por calles según Google Routes"
                                 if medida else "distancia en línea recta dividida entre 80 m/min"),
                    limitations=() if medida else (
                        "estimación en línea recta: ignora manzanas, desniveles y "
                        "cruces, y en Quito subestima de forma sistemática",
                    ),
                ),
            ),
        ),
    )


def _medir_servicios(materia: MateriaDeZona) -> PlaceMeasureV0[tuple]:
    """Los servicios cercanos, con UNA evidencia POR ORIGEN presente (PLAN04-1.2-R1).

    No una por servicio —serían seis referencias diciendo lo mismo— y desde luego no una
    sola para toda la lista, que era lo que atribuía a Google Places los POIs de nuestra
    capa. El origen se lee de `fuente`, servicio por servicio, y se agrupa.
    """
    otros = [s for s in materia.servicios if s.get("cat") != "transporte"]
    if not otros:
        if not materia.se_consultaron_servicios:
            return PlaceMeasureV0[tuple](
                status=MeasureStatus.UNKNOWN,
                limitations=("no se consultó el proveedor de servicios",),
            )
        return PlaceMeasureV0[tuple](
            status=MeasureStatus.INSUFFICIENT_EVIDENCE,
            limitations=("se consultó y no apareció ningún servicio cercano",),
        )

    # `sorted` sobre el conjunto: dos ensamblajes del mismo material tienen que producir
    # la misma tupla en el mismo orden, o el objeto deja de ser comparable.
    presentes = sorted({(s.get("fuente") or "") for s in otros})
    evidencia = tuple(
        e for e in (
            _evidencia_de_poi(materia, dimension="nearby_places", fuente=f,
                              metodos=_METODO_SERVICIO)
            for f in presentes
        ) if e is not None
    )
    if not evidencia:
        return PlaceMeasureV0[tuple](
            status=MeasureStatus.INSUFFICIENT_EVIDENCE,
            limitations=(_SIN_ORIGEN_DECLARADO,),
        )

    # Los servicios sin origen reconocible SÍ van en el valor —su distancia se midió—
    # pero la medida declara cuántos son. Callarlo dejaría que se leyeran como
    # acreditados por los orígenes que sí están.
    sin_origen = sum(1 for s in otros
                     if (s.get("fuente") or "") not in _ORIGEN_DE_LA_CAPA_DE_POIS)
    return PlaceMeasureV0[tuple](
        status=MeasureStatus.AVAILABLE,
        value=tuple(
            NearbyPlaceV0(
                category=s.get("cat") or "otros",
                distance_m=float(s["distancia_m"]),
                name=_nombre_limpio(s["nombre"]),
            )
            for s in otros
        ),
        evidence=evidencia,
        limitations=() if not sin_origen else (
            f"{sin_origen} de los {len(otros)} servicios llegaron sin origen declarado: "
            "van en el valor porque su distancia sí se midió, pero su procedencia no "
            "está acreditada",
        ),
    )


def ensamblar_place_context(materia: MateriaDeZona) -> PlaceContextV0:
    """La materia recuperada → el objeto. PURA: sin red, sin reloj propio, sin azar.

    Sin azar es literal y es un requisito: dos llamadas con la MISMA `MateriaDeZona`
    producen el mismo JSON byte a byte. Ver §"La identidad de la evidencia".
    """
    minutos = _medir_minutos_a_pie(materia)
    return PlaceContextV0(
        location=GeoPoint(lat=materia.lat, lon=materia.lon),
        assembled_at=materia.recuperado_en,
        walkability=_medir_caminabilidad(materia),
        nearest_transit=_medir_transporte(materia),
        nearby_places=_medir_servicios(materia),
        environment=(minutos,) if minutos else (),
        limitations=(
            "contexto de un punto, no de un inmueble: no incluye nada del activo",
        ),
    )


# ── la prosa se DERIVA del objeto ────────────────────────────────────────────

def prosa_conectividad(contexto: PlaceContextV0) -> str | None:
    """El texto de conectividad, derivado del objeto y de nada más."""
    medida = contexto.nearest_transit
    if medida is None or not medida.hay_valor:
        return None
    t = medida.value
    masivo = t.mode == "masivo"
    icono = "🚇" if masivo else "🚏"
    tipo = "" if masivo else " (parada de bus, NO es Metro)"
    minutos = next(
        (d.measure.value for d in contexto.environment
         if d.dimension == "transporte_minutos_a_pie" and d.measure.hay_valor),
        None,
    )
    return (f"{icono} {t.name}{tipo} "
            f"a ~{_num(t.distance_m)} m ({_num(minutos)} min a pie)")


def prosa_servicios(contexto: PlaceContextV0) -> str | None:
    """El texto de servicios cercanos, derivado del objeto y de nada más."""
    medida = contexto.nearby_places
    if medida is None or not medida.hay_valor:
        return None
    return ", ".join(
        f"{_CAT_EMOJI.get(p.category, '📍')} {p.name} (~{_num(p.distance_m)} m)"
        for p in medida.value
    ) or None


def _walk_score_legacy(contexto: PlaceContextV0):
    """El número de caminabilidad de la salida legacy. Sale del objeto y de nada más.

    Ya no hay excepción ni compatibilidad que declarar: con los tres casos del
    contrato, el objeto y la salida de siempre coinciden en los tres. Cuando el objeto
    no tiene valor, es porque el proveedor no respondió, y la salida de siempre también
    devolvía `None` ahí.
    """
    medida = contexto.walkability
    return _num(medida.value) if medida is not None and medida.hay_valor else None


# El vocabulario histórico de procedencia de caminabilidad, que vive en la columna
# `activos_inmutables.walk_score_fuente` y que el motor de encaje ya traduce. Esta tabla
# es la ÚNICA traducción del contrato a ese vocabulario: sin ella, el consumidor tendría
# que volver a inferir la procedencia desde el número, que es de donde venía el problema.
#
# La tabla es una LISTA ORDENADA y no un dict por índice, y eso es el arreglo de R1: la
# caminabilidad trae ahora dos evidencias —el cálculo de Contexto y los insumos de OSM— y
# leer `evidence[0]` haría que la respuesta dependiera del orden en que se escribieron.
# Un reordenamiento inocente habría cambiado lo que ve el consumidor sin tocar un dato.
#
# El orden de la lista es PRECEDENCIA declarada, no casualidad: `"osm"` significa, en el
# vocabulario histórico, que el número se calculó sobre comercios reales, así que la
# presencia del dataset de OSM manda sobre cualquier otra etiqueta. `"heuristico"` queda
# para el camino donde no hubo dataset detrás.
_PROCEDENCIA_LEGACY: tuple[tuple[SourceType, str | None, str], ...] = (
    (SourceType.PUBLIC_DATASET, "overpass", "osm"),
    (SourceType.HEURISTIC_ESTIMATE, None, "heuristico"),
)


def procedencia_caminabilidad_legacy(contexto: PlaceContextV0) -> str | None:
    """De dónde sale el número de caminabilidad, en el vocabulario de siempre.

    ANTES esto lo INFERÍA el consumidor con `"osm" if pois else None`, y esa inferencia
    era falsa en el caso 2: con el proveedor respondiendo y cero POIs, el cálculo SÍ se
    hizo sobre OSM y la tool afirmaba `null`. Ahora la procedencia viaja desde la
    evidencia, que es quien la sabe — y se BUSCA en ella, no se lee por índice.
    """
    medida = contexto.walkability
    if medida is None or not medida.hay_valor:
        return None
    for tipo, proveedor, etiqueta in _PROCEDENCIA_LEGACY:
        if any(e.source_type is tipo and (proveedor is None or e.provider == proveedor)
               for e in medida.evidence):
            return etiqueta
    return None


def derivar_salida_legacy(contexto: PlaceContextV0, materia: MateriaDeZona) -> dict:
    """La salida de siempre, derivada del objeto. Sin segundo fetch."""
    return {
        # `lugar` y `servicios` no los modela el contrato; `pois_analizados` es un
        # detalle del método. Los tres vienen de la materia prima, marcados.
        "lugar": materia.lugar,
        "walk_score": _walk_score_legacy(contexto),
        "conectividad": prosa_conectividad(contexto),
        "servicios": materia.servicios,
        "servicios_texto": prosa_servicios(contexto),
        "pois_analizados": materia.walk.get("pois_analizados", 0),
        # Clave NUEVA y aditiva. Existe para que el consumidor deje de inferir la
        # procedencia desde el número de POIs: ahora la trae derivada de la evidencia.
        "caminabilidad_fuente": procedencia_caminabilidad_legacy(contexto),
    }


async def place_context_de(lat: float, lon: float) -> PlaceContextV0:
    """El contexto de un punto como OBJETO. Un solo fetch."""
    return ensamblar_place_context(await _recolectar_zona(lat, lon))


async def analizar_zona(lat: float, lon: float) -> dict:
    """
    FUENTE ÚNICA DE VERDAD de una zona: la consumen el agente (home) y el mapa,
    para que la salida sea idéntica venga de donde venga.

    Combina: lugar (reverse-geocode), Walk Score (OSM) y servicios + transporte
    (Google Places, el MISMO motor que ilumina el mapa).

    Desde PLAN04-1.2 esto es una DERIVACIÓN: se recupera una vez, se ensambla el
    `PlaceContextV0`, y la salida de siempre sale de ese objeto.
    """
    materia = await _recolectar_zona(lat, lon)
    return derivar_salida_legacy(ensamblar_place_context(materia), materia)


async def aura_zona(lat: float, lon: float) -> dict:
    """Tarjeta proactiva ligera: barrio + Walk Score + titular del 'aura' (sin Google)."""
    from app.agent.tools import _reverse_geocode  # lazy: evita import circular
    geo, walk = await asyncio.gather(_reverse_geocode(lat, lon), walk_score_para(lat, lon), return_exceptions=True)
    geo = geo if isinstance(geo, dict) else {}
    walk = walk if isinstance(walk, dict) else {}
    ws = walk.get("walk_score")
    barrio = geo.get("barrio") or geo.get("ciudad") or "tu zona"
    return {
        "barrio": barrio,
        "ciudad": geo.get("ciudad"),
        "walk_score": ws,
        "titular": _interpreta_walk(ws),
    }


# ── Mapa Vivo 2C: isócrona peatonal (motor propio Valhalla, sin Google) ──
_ISO_MIN, _ISO_MAX = 5, 45  # minutos a pie razonables para el overlay


def _intent_isocrona(p: str) -> bool:
    """¿La pregunta pide el ÁREA alcanzable a pie (isócrona), no una ruta puntual?"""
    if "isocron" in p or "isócron" in p:
        return True
    pie = any(k in p for k in ("a pie", "caminando", "andando", "a patas"))
    tiempo = bool(re.search(r"\d+\s*min", p)) or ("minuto" in p)
    alcance = any(k in p for k in ("alcanzo", "alcanz", "llego", "puedo llegar", "qué tan lejos"))
    return (pie and (tiempo or alcance)) or (alcance and tiempo)


def _extraer_minutos(p: str) -> int:
    m = re.search(r"(\d{1,3})\s*min", p) or re.search(r"\b(\d{1,2})\b", p)
    val = int(m.group(1)) if m else 15
    return max(_ISO_MIN, min(_ISO_MAX, val))


# Qué hay DENTRO de la isócrona: la promesa de "todo lo que alcanzas" solo se cumple si se
# dice QUÉ se alcanza. El polígono sin contenido es un mapa bonito; con contenido es la verdad
# del lugar (que es el producto). Los POIs ya están en nuestra capa: un ST_Contains los saca.
_DENTRO_POIS_SQL = text("""
    SELECT categoria, count(*)::int AS n
    FROM pois_vivos
    WHERE ST_Contains(ST_SetSRID(ST_GeomFromGeoJSON(:geo), 4326), geom)
    GROUP BY categoria
    ORDER BY n DESC
""")

# Tope de categorías nombradas: el canon manda cápsulas, no volcado (el exceso de
# información paraliza — Iyengar & Lepper). Con 9 categorías la frase se vuelve un informe;
# con las 6 principales se escanea de un vistazo y el resto se resume en una cola honesta.
_MAX_CATS_DENTRO = 6

_DENTRO_ACTIVOS_SQL = text("""
    SELECT count(*)::int AS n
    FROM activos_inmutables
    WHERE ST_Contains(ST_SetSRID(ST_GeomFromGeoJSON(:geo), 4326), geom)
""")

# Etiqueta legible por categoría: (singular, plural). Descriptivas y neutras — se CUENTA
# equipamiento, nunca se juzga la zona (Fair Housing: medimos y citamos, el usuario juzga).
_ETIQUETA_CAT = {
    "farmacia":         ("farmacia", "farmacias"),
    "supermercado":     ("supermercado", "supermercados"),
    "parque":           ("parque", "parques"),
    "iglesia":          ("iglesia", "iglesias"),
    "centro_comercial": ("centro comercial", "centros comerciales"),
    "educacion":        ("punto de educación", "puntos de educación"),
    "salud":            ("punto de salud", "puntos de salud"),
    "transporte":       ("parada de transporte", "paradas de transporte"),
    "seguridad":        ("punto de seguridad", "puntos de seguridad"),
}


def _frase_dentro(filas: list, activos: int) -> str:
    """Arma la frase de contenido de la isócrona. Vacío → cadena vacía (el llamador omite).

    Cura a las _MAX_CATS_DENTRO categorías más numerosas y resume la cola: informa sin
    volcar. Los conteos son un HECHO de nuestra capa (se mide y se cita); ningún adjetivo
    juzga la zona — eso lo hace el usuario."""
    partes = []
    for f in filas[:_MAX_CATS_DENTRO]:
        n = f["n"]
        sing, plur = _ETIQUETA_CAT.get(f["categoria"], (f["categoria"], f["categoria"]))
        partes.append(f"{n} {sing if n == 1 else plur}")
    resto = len(filas) - _MAX_CATS_DENTRO
    if not partes and not activos:
        return ""
    linea = ""
    if partes:
        linea = "\n\n**Dentro de esa mancha hay:** " + " · ".join(partes)
        # Cola compacta: "· +2 más" pesa menos que "y 2 categorías más" y mantiene el
        # mismo separador de la lista (se escanea de corrido, sin cambiar de ritmo).
        linea += f" · +{resto} más." if resto > 0 else "."
    if activos:
        linea += (f"\n\nY **{activos} inmueble{'s' if activos != 1 else ''}** "
                  f"del catastro dentro del área.")
    return linea


async def _contenido_isocrona(geometry: dict) -> str:
    """Qué hay dentro del polígono, desde NUESTRA capa (pois_propios + catastro).

    Best-effort: si la DB o la geometría fallan, devuelve "" y el mapa igual pinta el
    contorno — nunca se degrada el turno por el detalle."""
    import json as _json
    try:
        geo = _json.dumps(geometry)
        async with engine.connect() as conn:
            filas = (await conn.execute(_DENTRO_POIS_SQL, {"geo": geo})).mappings().all()
            activos = (await conn.execute(_DENTRO_ACTIVOS_SQL, {"geo": geo})).scalar() or 0
        return _frase_dentro(list(filas), int(activos))
    except Exception:  # noqa: BLE001 — el contenido es un extra; el contorno ya vale por sí solo
        return ""


async def _accion_isocrona(lat: float, lon: float, p: str) -> dict:
    """Isócrona peatonal EN VIVO (Valhalla) → polígono + QUÉ se alcanza dentro."""
    minutos = _extraer_minutos(p)
    isos = await isocrona(lat, lon, [minutos])
    if not isos:
        return {"texto": "El motor de isócronas peatonales no está disponible ahora mismo.", "acciones": []}
    contornos = [{"minutos": it["minutos"], "geometry": it["geometry"]} for it in isos]
    texto = (f"Te ilumino **todo lo que alcanzas a {minutos} min a pie** desde aquí — "
             "por calles reales, no en línea recta.")
    # El contenido del área: sin esto, la frase promete algo que no entrega.
    dentro = await _contenido_isocrona(contornos[0]["geometry"])
    if dentro:
        texto += dentro
    else:
        texto += ("\n\nTodavía no tengo equipamiento cargado dentro de esa área — "
                  "es un hueco de nuestra capa aquí, no que no exista nada.")
    return {
        "texto": texto,
        "acciones": [{"tipo": "isocrona", "contornos": contornos, "centro": [lon, lat]}],
    }


# ── Panorama de transporte: TODAS las paradas cercanas + la estación masiva ──
# "Transporte" a secas no es "llévame al Metro": es "¿con qué me muevo desde aquí?".
# La ruta única al hub masivo (ignorando 15 paradas más cercanas) responde otra pregunta.
_PANORAMA_TRANSPORTE_SQL = text("""
    SELECT nombre, categoria_overture, ST_Y(geom) AS lat, ST_X(geom) AS lon,
        ROUND(ST_Distance(geom::geography,
              ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography))::int AS distancia_m,
        (categoria_overture = ANY(:masivo)) AS es_masivo
    FROM pois_vivos
    WHERE categoria = 'transporte'
      AND ST_DWithin(geom::geography,
                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :max_m)
    ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
    LIMIT 60
""")

_RADIO_PANORAMA_M = 800     # paradas a ≤10 min a pie (~80 m/min)
_RADIO_MASIVO_M = 2500      # el Metro/terminal se nombra aunque quede más lejos

_ETIQUETA_MASIVO = {"metro": "Metro", "terminal_bus": "terminal",
                    "estacion_tren": "estación de tren", "estacion": "estación"}


def _es_generico(nombre: str | None) -> bool:
    n = (nombre or "").strip().lower()
    return not n or n in ("parada de bus", "parada", "bus stop", "parada de autobús")


async def _panorama_transporte(lat: float, lon: float) -> dict:
    """Todas las paradas a ≤_RADIO_PANORAMA_M + la estación masiva más cercana (hasta
    _RADIO_MASIVO_M). Enciende todos los puntos y NOMBRA lo que enciende (cápsula curada:
    con ~15 paradas, listar todas sería un volcado). Honesto sobre el límite de la capa:
    tenemos paradas y estaciones, no los recorridos de las líneas."""
    try:
        async with engine.connect() as conn:
            filas = (await conn.execute(_PANORAMA_TRANSPORTE_SQL, {
                "lat": lat, "lon": lon, "max_m": _RADIO_MASIVO_M, "masivo": _TRANSPORTE_MASIVO,
            })).mappings().all()
    except Exception:  # noqa: BLE001 — sin capa, el llamador cae al flujo de ruta única
        filas = []
    if not filas:
        return {"texto": "No tengo transporte mapeado cerca de este punto — es un hueco de "
                         "nuestra capa aquí, no que no exista.", "acciones": []}

    paradas = [f for f in filas if not f["es_masivo"] and f["distancia_m"] <= _RADIO_PANORAMA_M]
    masivo = next((f for f in filas if f["es_masivo"]), None)

    # Pins: todas las paradas del radio + el masivo (color distinto, como el pin del mapa).
    items = [{"coords": [f["lon"], f["lat"]],
              "etiqueta": f"🚏 {_nombre_limpio(f['nombre']) if not _es_generico(f['nombre']) else 'Parada de bus'} ({f['distancia_m']} m)",
              "color": "#5E9BE0"} for f in paradas]
    if masivo:
        et = _ETIQUETA_MASIVO.get(masivo["categoria_overture"], "estación")
        items.append({"coords": [masivo["lon"], masivo["lat"]],
                      "etiqueta": f"🚇 {_nombre_limpio(masivo['nombre'])} ({et}, {masivo['distancia_m']} m)",
                      "color": "#5EEAD4"})

    # Texto: el masivo primero (con minutos a pie ~80 m/min), luego las paradas CON nombre
    # (dedup por nombre — la misma parada suele estar 2 veces, una por sentido), luego el
    # conteo del resto. Cápsula, no volcado.
    partes = []
    if masivo:
        mins = max(1, round(masivo["distancia_m"] / 80))
        et = _ETIQUETA_MASIVO.get(masivo["categoria_overture"], "estación")
        partes.append(f"🚇 **{_nombre_limpio(masivo['nombre'])}** ({et}) a {masivo['distancia_m']} m (~{mins} min)")
    vistas: set[str] = set()
    nombradas = []
    for f in paradas:
        n = _nombre_limpio(f["nombre"])
        if _es_generico(n) or n.lower() in vistas:
            continue
        vistas.add(n.lower())
        nombradas.append(f"🚏 {n} ({f['distancia_m']} m)")
        if len(nombradas) >= 4:
            break
    partes.extend(nombradas)
    resto = len(paradas) - len(nombradas)
    if resto > 0:
        partes.append(f"+{resto} parada{'s' if resto != 1 else ''} más")

    texto = ("**Transporte a pie desde aquí:** " + " · ".join(partes) + "."
             + "\n\nTe enciendo todas en el mapa. Aún no tengo los recorridos de las líneas "
               "— te muestro paradas y estaciones."
             + _sello_fuente([{"fuente": "propio"}]))
    return {"texto": texto, "acciones": [{"tipo": "puntos", "items": items, "color": "#5E9BE0"}]}


def _sello_fuente(items: list[dict]) -> str:
    """Proveniencia del dato, en una línea aparte. Honestidad de asteriscos: nuestra capa
    es Overture+OSM conflados y curados — es DATO PROPIO, no "verificado en terreno" (eso
    solo lo es lo que un corredor pisó). Nunca se infla la etiqueta.

    Solo marca lo propio, en positivo; lo que vino de Google no se desmerece ni se oculta."""
    if not items:
        return ""
    propios = sum(1 for s in items if s.get("fuente") == "propio")
    if propios == 0:
        return ""
    if propios == len(items):
        return "\n\n*Todo de nuestra capa propia.*"
    return f"\n\n*{propios} de {len(items)} de nuestra capa propia.*"


async def comando_mapa(pregunta: str, lat: float, lon: float) -> dict:
    """Interpreta una pregunta y devuelve {texto, acciones} para que el mapa reaccione."""
    p = (pregunta or "").lower()

    # 0a) ¿Isócrona peatonal? — motor propio (Valhalla), NO requiere Google.
    if _intent_isocrona(p):
        return await _accion_isocrona(lat, lon, p)

    key = settings.google_maps_api_key

    # 0) ¿Pide un recorrido/tour por la zona? (depende de Google de punta a punta)
    if any(k in p for k in ["tour", "recorre", "recorré", "recorrido", "recorrer", "pasea", "paseo",
                            "muestrame la zona", "muéstrame la zona", "muestrame el barrio",
                            "conoce la zona", "conocer la zona", "enséñame la zona", "ensename la zona"]):
        if not key:
            return {"texto": "El mapa interactivo necesita Google Maps activo.", "acciones": []}
        return await recorrido_zona(lat, lon)

    # 0b) ¿Transporte en GENERAL? ("transporte", "paradas", "buses", "líneas") → panorama:
    # todas las paradas cercanas + la estación masiva. "Metro"/"terminal"/"tren" siguen
    # abajo con su ruta única (ahí el usuario sí nombró un destino concreto). Límites de
    # palabra (\b) a propósito: "bus" sin bordes haría match en "busco".
    if (not re.search(r"\b(metro|terminal|tren)\b", p)
            and re.search(r"\b(transporte|paradas?|bus|buses|l[ií]neas?)\b", p)):
        return await _panorama_transporte(lat, lon)

    # 1) ¿Pide una ruta a una categoría?  NUESTRA CAPA PRIMERO, Google solo por hueco.
    cat = next((c for c, kws in _PALABRAS_CAT.items() if any(k in p for k in kws)), None)
    if cat:
        tipos = None            # tipos de Google (fallback)
        subtipos = None         # subtipos de nuestra capa
        if cat == "transporte":
            if "metro" in p:
                tipos = ["subway_station", "train_station", "light_rail_station"]
                subtipos = _SUBTIPOS_PROPIOS["metro"]
            elif "terminal" in p:
                tipos = ["bus_station"]
                subtipos = _SUBTIPOS_PROPIOS["terminal"]

        # Propio-primero (mismo patrón que _servicios_con_coords). Desde la migración 021
        # nuestra capa cubre las 9 categorías (iglesia y seguridad incluidas): Google solo
        # entra si el punto cae fuera del bbox de la ciudad cargada.
        dest = await _nearest_propio(lat, lon, cat, subtipos)
        if not dest and key:
            dest = await _nearest_categoria(lat, lon, cat, key, tipos)
        if not dest:
            return {"texto": f"No encontré {_CAT_LABEL.get(cat, cat)} cerca de ese punto.", "acciones": []}

        # La ruta a pie sigue siendo Google (Fase 2 del plan: pasarla a Valhalla /route).
        # Sin key aún tenemos el destino: se ilumina el punto aunque no se trace la línea.
        ruta = None
        if key:
            try:
                async with httpx.AsyncClient(verify=settings.ssl_verify.lower() != "false", timeout=_TIMEOUT) as c:
                    ruta = await _ruta_a_pie(c, lat, lon, dest["lat"], dest["lon"], key)
            except Exception:  # noqa: BLE001
                ruta = None
        sello = _sello_fuente([dest])
        if ruta and ruta.get("coords"):
            etiqueta = f"🚶 {ruta['duracion_min']} min · {dest['nombre']}"
            return {
                "texto": (f"Ilumino la ruta a **{dest['nombre']}**: "
                          f"{ruta['duracion_min']} min a pie ({ruta['distancia_m']} m)." + sello),
                "acciones": [{"tipo": "ruta", "coords": ruta["coords"], "destino": [dest["lon"], dest["lat"]],
                              "etiqueta": etiqueta, "color": "#5EEAD4"}],
            }
        return {"texto": f"Encontré **{dest['nombre']}** a {dest['distancia_m']} m, pero no pude trazar la ruta." + sello,
                "acciones": [{"tipo": "puntos", "items": [{"coords": [dest["lon"], dest["lat"]], "etiqueta": dest["nombre"]}], "color": "#5EEAD4"}]}

    # 2) ¿Pide ver lo que hay alrededor?
    if any(k in p for k in ["cerca", "servicios", "que hay", "qué hay", "alrededor", "entorno", "rodea"]):
        servicios = await _servicios_con_coords(lat, lon, key, 6)
        if not servicios:
            return {"texto": "No encontré servicios mapeados en este punto.", "acciones": []}
        items = []
        for s in servicios:
            emoji = _CAT_EMOJI.get(s.get("cat"), "📍")
            if s.get("cat") == "transporte" and not s.get("es_masivo"):
                emoji = "🚏"  # parada de bus, no Metro
            items.append({
                "coords": [s["lon"], s["lat"]],
                "etiqueta": f"{emoji} {_nombre_limpio(s['nombre'])} ({s['distancia_m']} m)",
                "color": _CAT_COLOR.get(s.get("cat"), "#5EEAD4"),
            })
        # Decir QUÉ se encendió, no solo que se encendió: el pin sin nombre obliga a
        # cazarlo en el mapa. Mismo principio que la isócrona — el gesto no es la respuesta.
        # Con el emoji de categoría (el mismo del pin): "Cedicontex (279 m)" solo no dice
        # nada; "🏥 Cedicontex (279 m)" se lee igual que el mapa.
        def _linea(s: dict) -> str:
            e = _CAT_EMOJI.get(s.get("cat"), "📍")
            if s.get("cat") == "transporte" and not s.get("es_masivo"):
                e = "🚏"
            return f"{e} {_nombre_limpio(s['nombre'])} ({s['distancia_m']} m)"
        lista = " · ".join(_linea(s) for s in servicios)
        return {"texto": f"**Lo que tienes cerca:** {lista}." + _sello_fuente(servicios),
                "acciones": [{"tipo": "puntos", "items": items, "color": "#5EEAD4"}]}

    # 3) Fallback: guía
    return {"texto": "Pídeme algo como *“ruta al Metro”*, *“colegio más cercano”* o *“qué hay cerca”* y lo ilumino en el mapa.",
            "acciones": []}


async def rutas_desde(lat: float, lon: float, n: int = 3) -> list[dict] | None:
    """Rutas peatonales reales a los N servicios más cercanos. None si no hay key."""
    key = settings.google_maps_api_key
    if not key:
        return None
    try:
        servicios = await _servicios_con_coords(lat, lon, key, n)
        if not servicios:
            return []
        verify = settings.ssl_verify.lower() != "false"
        async with httpx.AsyncClient(verify=verify, timeout=_TIMEOUT) as c:
            rutas = await asyncio.gather(
                *[_ruta_a_pie(c, lat, lon, s["lat"], s["lon"], key) for s in servicios],
                return_exceptions=True,
            )
        out = []
        for s, rt in zip(servicios, rutas):
            if isinstance(rt, dict) and rt.get("coords"):
                out.append({"nombre": s["nombre"], "destino": [s["lon"], s["lat"]], **rt})
        return out
    except Exception:  # noqa: BLE001
        return None
