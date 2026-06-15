"""
Precision tools for the Contexto AI agent.
Both tools connect directly to the async engine to remain framework-agnostic
(no FastAPI dependency injection — tools are called inside LangGraph execution).
"""
import asyncio
import json
from typing import Any

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from langchain_core.tools import tool
from sqlalchemy import text

from app.database import AsyncSessionLocal


async def _fetch_rows(query: str, params: dict) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(text(query), params)
        rows = result.mappings().all()
        return [dict(row) for row in rows]


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
    rows = await _fetch_rows(query, {"lat": latitude, "lon": longitude, "radius": radius_meters})

    if not rows:
        return json.dumps({"assets": [], "message": "No registered assets found in this radius."})

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
        WHERE a.id = :activo_id
    """
    rows = await _fetch_rows(query, {"activo_id": activo_id})

    if not rows:
        return json.dumps({
            "specs": None,
            "message": f"No asset found with id {activo_id}. This QR/id is not registered in the catastro."
        })

    return json.dumps({"specs": rows[0]}, default=str)


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


# ── Capa de inversión: motor financiero honesto sobre dato verificado ────────
# Parámetros por mercado (defaults Ecuador/LATAM; configurables a futuro).
_INV = {
    "costo_adquisicion_pct": 0.07,    # notaría, registro, alcabala, etc.
    "vacancia_meses": 1.0,            # ~1 mes/año sin arrendar
    "mantenimiento_pct_renta": 0.05,  # 5% de la renta anual
    "predial_pct_precio": 0.005,      # impuesto predial anual aprox.
}


def _veredicto_bruta(b: float) -> str:
    if b >= 7:
        return "muy buena (renta atractiva)"
    if b >= 5:
        return "buena (sobre el umbral de inversión)"
    if b >= 3.5:
        return "marginal (apenas; revisa los gastos)"
    return "baja como renta — solo tendría sentido por revalorización/ubicación, no por flujo"


def _analisis_inversion(precio: float, area: float | None, renta_mensual: float,
                        alicuota_mensual: float | None) -> dict:
    """Cálculo PURO de la inversión. Sin red, sin efectos."""
    renta_anual = renta_mensual * 12
    bruta = renta_anual / precio * 100
    inversion_total = precio * (1 + _INV["costo_adquisicion_pct"])
    gastos = ((alicuota_mensual or 0) * 12
              + renta_mensual * _INV["vacancia_meses"]
              + renta_anual * _INV["mantenimiento_pct_renta"]
              + precio * _INV["predial_pct_precio"])
    neta = (renta_anual - gastos) / inversion_total * 100
    return {
        "rentabilidad_bruta_pct": round(bruta, 1),
        "rentabilidad_neta_pct": round(neta, 1),
        "precio_m2": round(precio / area) if area else None,
        "renta_anual_usd": round(renta_anual),
        "inversion_total_estimada_usd": round(inversion_total),
        "veredicto": _veredicto_bruta(bruta),
    }


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
    query = """
        SELECT
            a.direccion_estandarizada,
            a.tipo_activo,
            a.caracteristicas,
            (SELECT t.precio FROM transacciones_temporales t
             WHERE t.activo_id = a.id ORDER BY t.fecha_publicacion DESC LIMIT 1) AS precio,
            (f.activo_id IS NOT NULL) AS tiene_ficha_tecnica
        FROM activos_inmutables a
        LEFT JOIN ficha_tecnica_mantenimiento f ON f.activo_id = a.id
        WHERE a.id = :id
    """
    rows = await _fetch_rows(query, {"id": activo_id})
    if not rows:
        return json.dumps({"message": f"No asset found with id {activo_id}."})
    r = rows[0]
    car = r.get("caracteristicas") or {}
    if isinstance(car, str):
        try:
            car = json.loads(car)
        except Exception:  # noqa: BLE001
            car = {}

    precio = float(r["precio"]) if r.get("precio") is not None else None
    area = car.get("area_total_m2")
    renta = car.get("renta_mensual_estimada")
    alicuota = car.get("alicuota")

    # Inputs faltantes → honestidad total, sin inventar.
    faltan = [n for n, v in (("precio", precio), ("área (m²)", area),
                             ("renta mensual estimada", renta)) if not v]
    if faltan:
        return json.dumps({
            "direccion": r["direccion_estandarizada"], "puede_calcular": False,
            "faltan_inputs": faltan,
            "mensaje": "Para analizar la inversión faltan: " + ", ".join(faltan)
                       + ". El dueño puede agregarlos en la ficha del inmueble.",
        }, ensure_ascii=False, default=str)

    kpis = _analisis_inversion(precio, float(area), float(renta), alicuota)

    # Chequeo honesto de la CALIDAD del input (el diferenciador).
    alertas = ["La renta es una ESTIMACIÓN del corredor, no un contrato verificado."]
    b = kpis["rentabilidad_bruta_pct"]
    if b > 14:
        alertas.append("Rentabilidad implausiblemente alta — verifica que el precio y la renta sean correctos.")
    elif b < 3.5:
        alertas.append("La renta estimada parece baja para el precio — vale la pena verificarla; podría cambiar el veredicto.")
    if not r["tiene_ficha_tecnica"]:
        alertas.append("Estado estructural SIN verificar (ficha técnica pendiente) — riesgo de reparaciones no cuantificado.")

    return json.dumps({
        "direccion": r["direccion_estandarizada"], "tipo_activo": r["tipo_activo"],
        "puede_calcular": True,
        "inputs": {"precio_usd": precio, "area_m2": area,
                   "renta_mensual_estimada_usd": renta, "alicuota_mensual_usd": alicuota},
        "kpis": kpis,
        "supuestos": "Adquisición 7% · vacancia 1 mes/año · mantenimiento 5% de renta · predial 0.5%/año (configurables por mercado)",
        "alertas_honestas": alertas,
        "umbral_referencia": "Bruta >5% se considera buena inversión de renta en LATAM (sobre el costo de oportunidad).",
    }, ensure_ascii=False, default=str)


AGENT_TOOLS = [
    tool_geocode_address,
    tool_search_nearby_assets,
    tool_fetch_asset_lifecycle_specs,
    tool_analyze_location,
    tool_analyze_investment,
]
