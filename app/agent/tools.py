"""
Precision tools for the Contexto AI agent.
Both tools connect directly to the async engine to remain framework-agnostic
(no FastAPI dependency injection — tools are called inside LangGraph execution).
"""
import json
from typing import Any
from uuid import UUID

from langchain_core.tools import tool
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
    noise levels, walk scores, and traffic volumes. Use this tool whenever
    the user asks about a neighborhood, street, or area.

    Args:
        latitude: WGS84 latitude of the search center.
        longitude: WGS84 longitude of the search center.
        radius_meters: Search radius in meters (default 800m — a 10-min walk).
    """
    query = """
        SELECT
            a.id::text,
            a.direccion_estandarizada,
            a.piso_altura,
            a.walk_score,
            a.score_ruido_predictivo,
            a.volumen_trafico_historico,
            a.densidad_poblacional_pico,
            a.porcentaje_cobertura_vegetal,
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
    Retrieve the complete structural specifications and maintenance lifecycle log
    for a specific property asset.

    Returns pipe types, construction year, structure material, finish quality,
    and full preventive maintenance history (cistern, roof, facade, electrical).
    Use this when the user asks about a specific property's condition, investment
    value, or structural health.

    Args:
        activo_id: UUID of the immutable asset.
    """
    query = """
        SELECT
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
            a.direccion_estandarizada,
            a.walk_score,
            a.score_ruido_predictivo,
            a.volumen_trafico_historico
        FROM ficha_tecnica_mantenimiento f
        JOIN activos_inmutables a ON a.id = f.activo_id
        WHERE f.activo_id = :activo_id
    """
    rows = await _fetch_rows(query, {"activo_id": activo_id})

    if not rows:
        return json.dumps({
            "specs": None,
            "message": f"No maintenance log found for asset {activo_id}. The owner has not registered structural data yet."
        })

    return json.dumps({"specs": rows[0]}, default=str)


AGENT_TOOLS = [tool_search_nearby_assets, tool_fetch_asset_lifecycle_specs]
