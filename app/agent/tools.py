"""
Precision tools for the Contexto AI agent.
Both tools connect directly to the async engine to remain framework-agnostic
(no FastAPI dependency injection — tools are called inside LangGraph execution).
"""
import asyncio
import json
import re
from typing import Any

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from langchain_core.tools import tool
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.entorno import limpiar_texto_servicios
from app.entorno_curacion import aplicar_curacion


async def _fetch_rows(query: str, params: dict) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(text(query), params)
        rows = result.mappings().all()
        return [dict(row) for row in rows]


def _limpiar_servicios_en(row: dict) -> dict:
    """Filtra POIs basura (nombres genéricos como TRABAJO) del servicios_cercanos
    guardado, para que el agente nunca los mencione (el dato puede estar estancado)."""
    if isinstance(row, dict) and row.get("servicios_cercanos"):
        row["servicios_cercanos"] = limpiar_texto_servicios(row["servicios_cercanos"])
    return row


@tool
async def tool_search_nearby_assets(
    latitude: float,
    longitude: float,
    radius_meters: int = 800,
) -> str:
    """
    Search for registered immutable assets within a geographic radius.

    Returns a JSON list of nearby properties with their habitability scores,
    noise levels, walkability scores, and traffic volumes. Use this tool whenever
    the user asks about a neighborhood, street, or area.

    Args:
        latitude: WGS84 latitude of the search center.
        longitude: WGS84 longitude of the search center.
        radius_meters: Search radius in meters (default 1500m when coming from geocoded address,
                       800m when the user provides exact coordinates).
    """
    query = """
        SELECT
            a.id::text,
            a.direccion_estandarizada,
            a.tipo_activo,
            a.piso_altura,
            a.walk_score AS caminabilidad,
            a.score_ruido_predictivo,
            a.volumen_trafico_historico,
            a.densidad_poblacional_pico,
            a.porcentaje_cobertura_vegetal,
            a.conectividad,
            a.servicios_cercanos,
            ROUND(
                ST_Distance(
                    a.geom::geography,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                )::numeric, 1
            ) AS distancia_metros
        FROM activos_inmutables a
        WHERE ST_DWithin(
            a.geom::geography,
            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
            :radius
        )
        ORDER BY distancia_metros ASC
        LIMIT 10
    """
    # Radio progresivo: con inventario escaso, un radio fijo deja fuera inmuebles
    # relevantes que están un poco más lejos. Si no hay nada, expandimos antes de
    # rendirnos — y devolvemos el radio usado para que el agente sea honesto con la distancia.
    radii = [radius_meters] + [r for r in (3000, 6000) if r > radius_meters]
    rows: list = []
    used = radius_meters
    for r in radii:
        rows = await _fetch_rows(query, {"lat": latitude, "lon": longitude, "radius": r})
        used = r
        if rows:
            break

    if not rows:
        return json.dumps({
            "assets": [], "radius_searched_m": used,
            "message": f"No registered assets within {used} m of this point.",
        })

    rows = [_limpiar_servicios_en(r) for r in rows]
    return json.dumps({
        "assets": rows, "total": len(rows), "radius_searched_m": used,
        "note": "distancia_metros = how far each asset is from the search point; be honest about distance if it is large.",
    }, default=str)


_STOP_WORDS = {"de", "la", "el", "y", "del", "los", "las", "en", "con", "por",
               "un", "una", "al", "a", "calle", "av", "avenida", "pasaje", "sector"}


@tool
async def tool_find_assets_by_text(query: str) -> str:
    """
    Find registered assets in OUR OWN catastro by matching their stored address text
    (and connectivity/services notes) — WITHOUT relying on external geocoding.

    Use this FIRST whenever the user names a street, address, building, or local
    landmark/sector (e.g. "Jorge Salvador Lara", "Quitumbe", "Quicentro Sur").
    OpenStreetMap/Nominatim does NOT know most Quito streets and confuses Metro
    station names, so OUR catastro is the source of truth for finding registered
    properties by name. Only fall back to tool_geocode_address if this returns nothing.

    Returns matching assets with their habitability scores and coordinates (lat/lon).
    You can describe them directly, or call tool_search_nearby_assets with their
    lat/lon for neighborhood context.

    Args:
        query: Free-text street name, address, building or sector in Quito.
    """
    raw = (query or "").strip()
    if not raw:
        return json.dumps({"assets": [], "message": "Empty query."})

    tokens = [t for t in re.split(r"[\s,]+", raw) if len(t) >= 3 and t.lower() not in _STOP_WORDS]
    if not tokens:
        tokens = [raw]

    params: dict[str, Any] = {"phrase": f"%{raw}%"}
    dir_conds = []
    for i, t in enumerate(tokens):
        params[f"t{i}"] = f"%{t}%"
        dir_conds.append(f"a.direccion_estandarizada ILIKE :t{i}")
    direccion_match = "(" + " AND ".join(dir_conds) + ")"

    query_sql = f"""
        SELECT
            a.id::text,
            a.direccion_estandarizada,
            a.tipo_activo,
            a.piso_altura,
            a.walk_score AS caminabilidad,
            a.score_ruido_predictivo,
            a.volumen_trafico_historico,
            a.porcentaje_cobertura_vegetal,
            a.conectividad,
            a.servicios_cercanos,
            t.tipo_operacion AS operacion,
            t.precio,
            ROUND(ST_Y(a.geom::geometry)::numeric, 6) AS lat,
            ROUND(ST_X(a.geom::geometry)::numeric, 6) AS lon,
            (CASE WHEN {direccion_match} THEN 0 ELSE 1 END) AS _rank
        FROM activos_inmutables a
        LEFT JOIN LATERAL (
            SELECT tipo_operacion, precio FROM transacciones_temporales tt
            WHERE tt.activo_id = a.id ORDER BY tt.fecha_publicacion DESC LIMIT 1
        ) t ON true
        WHERE {direccion_match}
           OR a.conectividad ILIKE :phrase
           OR a.servicios_cercanos ILIKE :phrase
        ORDER BY _rank ASC, a.created_at DESC
        LIMIT 10
    """
    rows = await _fetch_rows(query_sql, params)
    if not rows:
        return json.dumps({
            "assets": [],
            "message": (
                f"No registered asset matches '{raw}' by name in the catastro. "
                "It may not be registered yet, or be listed under a different address. "
                "You may try tool_geocode_address as a fallback for zone-level context."
            ),
        })

    for r in rows:
        r.pop("_rank", None)
    rows = [_limpiar_servicios_en(r) for r in rows]
    return json.dumps({"assets": rows, "total": len(rows)}, default=str)


@tool
async def tool_fetch_asset_lifecycle_specs(activo_id: str) -> str:
    """
    Retrieve the full profile of a specific property asset by its UUID.

    ALWAYS returns the asset's permanent environment data — walkability, noise,
    traffic, vegetation, and CONNECTIVITY (nearby Metro / bus terminals, a
    plusvalía signal) — even when no maintenance log exists yet. The structural
    maintenance fields (pipes, year, structure, waterproofing, electrical, etc.)
    are present only if the owner has registered the technical sheet.

    Use this whenever the user scans a QR or asks about a specific property by id.
    If `tiene_ficha_tecnica` is false, still present all the environment data
    (especially walkability and connectivity) as valuable context, and note that
    the structural sheet is pending.

    Args:
        activo_id: UUID of the immutable asset.
    """
    query = """
        SELECT
            a.direccion_estandarizada,
            a.tipo_activo,
            a.piso_altura,
            a.walk_score AS caminabilidad,
            a.score_ruido_predictivo,
            a.volumen_trafico_historico,
            a.porcentaje_cobertura_vegetal,
            a.conectividad,
            a.servicios_cercanos,
            a.caracteristicas,
            t.tipo_operacion AS operacion,
            t.precio,
            f.tipo_tuberia,
            f.año_construccion,
            f.tipo_estructura,
            f.calidad_acabados,
            f.ultimo_mantenimiento_cisterna,
            f.ultima_impermeabilizacion_techo,
            f.ultima_pintura_fachada,
            f.ultimo_cambio_cableado_electrico,
            f.monto_invertido_mejoras,
            f.descripcion_mejoras,
            f.updated_at,
            (f.activo_id IS NOT NULL) AS tiene_ficha_tecnica
        FROM activos_inmutables a
        LEFT JOIN ficha_tecnica_mantenimiento f ON f.activo_id = a.id
        LEFT JOIN LATERAL (
            SELECT tipo_operacion, precio FROM transacciones_temporales tt
            WHERE tt.activo_id = a.id ORDER BY tt.fecha_publicacion DESC LIMIT 1
        ) t ON true
        WHERE a.id = :activo_id
    """
    rows = await _fetch_rows(query, {"activo_id": activo_id})

    if not rows:
        return json.dumps({
            "specs": None,
            "message": f"No asset found with id {activo_id}. This QR/id is not registered in the catastro."
        })

    # Quitamos las "notas" libres del propietario antes de dárselas al agente:
    # ese texto sin verificar (p. ej. "cerca del Trole", "a 20 m", "muy comercial")
    # NO debe presentarse como hecho. Se eliminó del formulario; esto blinda
    # cualquier dato heredado. Robusto a caracteristicas como dict o JSON string.
    row = rows[0]
    car = row.get("caracteristicas")
    if isinstance(car, str):
        try:
            car = json.loads(car)
        except Exception:  # noqa: BLE001
            car = None
    if isinstance(car, dict):
        car.pop("notas", None)
        row["caracteristicas"] = car

    # Overlay de curación del corredor (el "loop" del Catastro Vivo): quita los POIs
    # que el corredor marcó cerrados y añade los que confirmó. El corredor sabe antes
    # que el mapa. Defensivo: si la tabla aún no existe, no rompe.
    try:
        curaciones = await _fetch_rows(
            "SELECT accion, nombre, categoria, distancia_m, creado_en::text AS creado_en "
            "FROM entorno_curacion WHERE activo_id = :a ORDER BY creado_en DESC",
            {"a": activo_id},
        )
    except Exception:  # noqa: BLE001
        curaciones = []
    if curaciones:
        row["servicios_cercanos"] = aplicar_curacion(row.get("servicios_cercanos"), curaciones)

    return json.dumps({"specs": _limpiar_servicios_en(row)}, default=str)


@tool
async def tool_geocode_address(address: str) -> str:
    """
    Convert a human-readable address or neighborhood name into geographic coordinates
    (latitude and longitude) using OpenStreetMap Nominatim.

    Use this tool FIRST whenever the user provides an address, street name, or
    neighborhood (e.g. "Av. Colon y 10 de Agosto", "Cumbaya", "Centro Historico")
    instead of explicit coordinates. Once you have the coordinates, use
    tool_search_nearby_assets to find properties near that location.

    Args:
        address: Free-text address, intersection, or place name in Quito, Ecuador.
    """
    # Append Quito context to improve geocoding accuracy
    query = f"{address.strip()}, Quito, Ecuador"

    def _geocode_sync(q: str):
        geolocator = Nominatim(user_agent="contexto_ai_v2", timeout=8)
        return geolocator.geocode(q, language="es")

    # Build progressive fallback queries (most specific → least specific)
    fallback_queries = [
        query,                                              # "Av. X y Z, Quito, Ecuador"
        f"{address.strip()}, Ecuador",                     # sin "Quito"
        f"{address.split(' y ')[0].strip()}, Quito, Ecuador",  # solo primera calle/barrio
        f"{address.strip().split(',')[0]}, Quito, Ecuador",    # antes de la primera coma
    ]

    try:
        location = None
        for q in dict.fromkeys(fallback_queries):  # deduplicate preserving order
            location = await asyncio.get_event_loop().run_in_executor(None, _geocode_sync, q)
            if location:
                break

        if location is None:
            return json.dumps({
                "found": False,
                "message": (
                    f"No se encontraron coordenadas para '{address}'. "
                    "Intenta con una dirección más específica o incluye el barrio/sector."
                ),
            })

        return json.dumps({
            "found": True,
            "address_input": address,
            "address_resolved": location.address,
            "latitude": round(location.latitude, 6),
            "longitude": round(location.longitude, 6),
            "tip": "Use tool_search_nearby_assets with radius_meters=2000 for geocoded addresses (Nominatim may offset slightly).",
        })

    except (GeocoderTimedOut, GeocoderUnavailable):
        return json.dumps({
            "found": False,
            "message": "Servicio de geocoding temporalmente no disponible. Pide al usuario las coordenadas.",
        })


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


@tool
async def tool_analyze_location(latitude: float, longitude: float) -> str:
    """
    Analyze the habitability of ANY point on Earth from its coordinates.

    Reverse-geocodes the place (neighborhood, city, country) and computes the LIVE
    environment of that exact spot: walkability, connectivity (Metro / transit hubs)
    and named nearby services. It works ANYWHERE — not only Quito — and even where
    there are NO registered assets.

    Use this whenever the user shares their location, or asks "what is it like to
    live HERE / at this point". After calling it, if useful, you may ALSO call
    tool_search_nearby_assets to add any registered listings nearby.

    Args:
        latitude: WGS84 latitude of the point (e.g. the user's shared location).
        longitude: WGS84 longitude of the point.
    """
    # Fuente ÚNICA de verdad: el MISMO motor que alimenta el mapa, para que la
    # salida del home y la del mapa sean idénticas (mismo Metro, mismos servicios).
    from app.rutas import analizar_zona

    a = await analizar_zona(latitude, longitude)
    pois = a.get("pois_analizados", 0)
    return json.dumps({
        "lugar": a["lugar"],
        "caminabilidad": a["walk_score"],
        "conectividad": a["conectividad"],
        "servicios_cercanos": a["servicios_texto"],
        "pois_analizados": pois,
        "cobertura": "rica" if pois > 100 else ("media" if pois else "sin datos"),
    }, ensure_ascii=False, default=str)


@tool
async def tool_analyze_investment(activo_id: str) -> str:
    """
    Analyze a REGISTERED property as an INVESTMENT: gross/net yield, price per m²,
    and an honest verdict. Uses the declared price, area (m²) and the ESTIMATED
    monthly rent from the listing, plus the maintenance state (risk). Clearly marks
    what is verified data vs an estimate, and never invents missing inputs.

    Use this when the user asks whether a property is a good investment, its yield/
    rentabilidad, or whether to buy it to rent out.

    Args:
        activo_id: UUID of the registered asset in the catastro.
    """
    from app.inversion import analizar_inversion  # fuente única (la usan agente y API REST)

    query = """
        SELECT
            a.direccion_estandarizada,
            a.tipo_activo,
            a.caracteristicas,
            t.precio,
            t.tipo_operacion AS operacion,
            (f.activo_id IS NOT NULL) AS tiene_ficha_tecnica
        FROM activos_inmutables a
        LEFT JOIN ficha_tecnica_mantenimiento f ON f.activo_id = a.id
        LEFT JOIN LATERAL (
            SELECT precio, tipo_operacion FROM transacciones_temporales tt
            WHERE tt.activo_id = a.id ORDER BY tt.fecha_publicacion DESC LIMIT 1
        ) t ON true
        WHERE a.id = :id
    """
    rows = await _fetch_rows(query, {"id": activo_id})
    if not rows:
        return json.dumps({"message": f"No asset found with id {activo_id}."})
    r = rows[0]

    # El análisis de inversión (yield de COMPRA, precio/m²) aplica solo a VENTA.
    # En arriendo no hay precio de compra → no calcular (daría números absurdos).
    operacion = (r.get("operacion") or "").upper()
    if operacion and operacion != "VENTA":
        return json.dumps({
            "puede_calcular": False,
            "operacion": operacion.lower(),
            "message": (
                "Este inmueble está en ARRIENDO, no en venta. El análisis de inversión "
                "(rentabilidad de compra, precio/m²) aplica a inmuebles en VENTA. Aquí no "
                "ofrezcas yield de compra; enfócate en el canon, lo que incluye y la zona."
            ),
        }, ensure_ascii=False)

    car = r.get("caracteristicas") or {}
    if isinstance(car, str):
        try:
            car = json.loads(car)
        except Exception:  # noqa: BLE001
            car = {}

    resultado = analizar_inversion(
        direccion=r["direccion_estandarizada"], tipo_activo=r["tipo_activo"],
        precio=float(r["precio"]) if r.get("precio") is not None else None,
        area=car.get("area_total_m2"), renta_mensual=car.get("renta_mensual_estimada"),
        alicuota_mensual=car.get("alicuota"), tiene_ficha=bool(r["tiene_ficha_tecnica"]),
    )
    return json.dumps(resultado, ensure_ascii=False, default=str)


AGENT_TOOLS = [
    tool_find_assets_by_text,
    tool_geocode_address,
    tool_search_nearby_assets,
    tool_fetch_asset_lifecycle_specs,
    tool_analyze_location,
    tool_analyze_investment,
]
