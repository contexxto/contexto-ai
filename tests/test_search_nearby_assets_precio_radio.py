"""Regression test para dos hallazgos reales (feedback en vivo, 2026-07-01):

1) Con la MISMA consulta del usuario, dos corridas devolvieron un set de candidatos
   distinto (un inmueble limitrofe aparecia en una corrida y no en la otra). Causa:
   `tool_search_nearby_assets` dejaba que el LLM eligiera `radius_meters` (800 vs
   1500 segun el docstring), y ST_DWithin con un radio distinto incluye/excluye
   inmuebles borderline. Fix: default fijo (1200m) y guia explicita de "dejalo en
   el default" en vez de sugerir dos valores distintos segun el caso.

2) `tool_search_nearby_assets` no traia precio/operacion (a diferencia de
   tool_find_assets_by_text, que si hace el LEFT JOIN LATERAL a
   transacciones_temporales) — imposible razonar sobre presupuesto en resultados
   de busqueda por radio. Fix: mismo JOIN que ya usa tool_find_assets_by_text.
"""
import asyncio
import json

from app.agent import tools


def test_radius_default_es_fijo_no_ambiguo():
    # El default ya no debe depender de que el LLM "adivine" 800 o 1500 segun el
    # docstring — debe haber UN solo valor fijo documentado.
    assert tools.tool_search_nearby_assets.args["radius_meters"]["default"] == 1200


def test_search_nearby_assets_incluye_precio_y_operacion(monkeypatch):
    fake_row = {
        "id": "abc-123",
        "direccion_estandarizada": "Av. de los Shyris y Suecia, La Carolina",
        "tipo_activo": "Departamento",
        "piso_altura": 4,
        "caminabilidad": 99,
        "score_ruido_predictivo": "MEDIO",
        "volumen_trafico_historico": 9000,
        "densidad_poblacional_pico": None,
        "porcentaje_cobertura_vegetal": 30.0,
        "conectividad": None,
        "servicios_cercanos": None,
        "operacion": "arriendo",
        "precio": 550.0,
        "distancia_metros": 950.0,
    }

    async def fake_fetch_rows(query, params):
        # El punto central del fix: la query ahora debe pedir precio/operacion.
        assert "transacciones_temporales" in query
        assert "t.precio" in query
        assert "t.tipo_operacion" in query
        return [fake_row]

    monkeypatch.setattr(tools, "_fetch_rows", fake_fetch_rows)

    result = asyncio.run(tools.tool_search_nearby_assets.ainvoke({
        "latitude": -0.18, "longitude": -78.48,
    }))
    data = json.loads(result)
    assert data["assets"][0]["precio"] == 550.0
    assert data["assets"][0]["operacion"] == "arriendo"
