"""H2 · el contrato espacial de las herramientas, tal como lo LEE el modelo.

EL DEFECTO. La descripción de `tool_find_assets_by_text` decía «Only fall back to
tool_geocode_address if this returns nothing», y el SYSTEM_PROMPT lo repetía («2º) SOLO si no hay
coincidencia por nombre → tool_geocode_address»). Encontrar un inmueble por texto bloqueaba así
la ruta espacial. Los modelos nuevos la obedecen al pie de la letra: en `encaje_lidera` («vivir
cerca de la Estación Quitumbe»), claude-sonnet-5 (0/4) y claude-sonnet-5-5 (0/6) nunca
geocodificaron ni buscaron alrededor, y no pudieron dar la distancia al Metro. 4.5 lo hacía
2 de cada 4 veces porque desobedecía la regla.

LA SEPARACIÓN NUEVA:
  · buscar por texto → encontrar inventario relevante; NO demuestra distancia ni cercanía;
  · geocodificar / análisis espacial → demostrar proximidad, distancia, transporte.
  · afirmar distancia sin evidencia espacial del turno → obtenerla o abstenerse;
  · sin dimensión espacial en la pregunta → no se fuerza ninguna herramienta.

Los controles de `encaje_lidera` son deterministas (sin modelo): sólo la ruta espacial produce
la relación territorial con distancias ligadas a las tarjetas, que es lo único que el producto
entrega al modelo como autoridad de distancia. Una búsqueda por texto no la produce.
"""
import asyncio
import json
import math
import re

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent import graph as G
from app.agent import tools as T
from app.decision.assembler import _relacion_territorial_del_turno

DESCRIPCIONES = {t.name: t.description for t in T.AGENT_TOOLS}
PROMPT = G.SYSTEM_PROMPT.content
# El prompt parte las frases en varias líneas con sangría: se compara con el espacio colapsado.
PLANO = " ".join(PROMPT.split())


# ── el contrato ────────────────────────────────────────────────────────────────────────
def test_la_regla_de_geocoding_solo_como_fallback_quedo_retirada():
    for nombre, texto in DESCRIPCIONES.items():
        assert not re.search(r"only\s+fall\s*back", texto, re.I), f"{nombre} conserva «only fall back»"
        assert not re.search(r"when our catastro has no match\.", texto), \
            f"{nombre} restringe el geocoding a «no match»"
    assert not re.search(r"SOLO si no hay coincidencia por nombre", PLANO)
    assert not re.search(r"sirve solo como respaldo para ubicar una zona", PLANO)


def test_buscar_por_texto_declara_que_no_demuestra_distancia():
    d = DESCRIPCIONES["tool_find_assets_by_text"]
    assert "does NOT establish distance, proximity or transport" in d
    assert "tool_analyze_location" in d and "tool_search_nearby_assets" in d


def test_el_geocoder_sirve_para_ubicar_un_punto_de_referencia():
    d = DESCRIPCIONES["tool_geocode_address"]
    assert "REFERENCE POINT" in d
    assert "approximate" in d  # la cautela de Nominatim con estaciones del Metro sigue dicha


def test_el_prompt_exige_evidencia_espacial_o_abstencion():
    assert "encontrar un inmueble por texto NO demuestra que esté" in PLANO
    assert "o abstente y di que no tienes esa medición" in PLANO


def test_el_prompt_no_fuerza_herramientas_sin_dimension_espacial():
    assert "Si la pregunta no tiene dimensión espacial, no dispares herramientas espaciales" in PLANO
    # y la regla de oro de encontrar inventario por texto PRIMERO sigue en pie
    assert "usa SIEMPRE tool_find_assets_by_text PRIMERO" in PLANO


# ── controles de encaje_lidera (deterministas, sin modelo) ─────────────────────────────
ESTACION = (-0.2980, -78.5570)
INVENTARIO = [
    {"id": "q1", "direccion_estandarizada": "Av. Mariscal Sucre S48-20 y Quitumbe Ñan, Quitumbe, Quito",
     "tipo_activo": "Departamento", "operacion": "ARRIENDO", "precio": 380, "lat": -0.2968, "lon": -78.5561},
    {"id": "q2", "direccion_estandarizada": "Calle Amaru Ñan S45-110, Quitumbe, Quito",
     "tipo_activo": "Departamento", "operacion": "VENTA", "precio": 78000, "lat": -0.2945, "lon": -78.5540},
    {"id": "q3", "direccion_estandarizada": "Pasaje Turubamba S50-15, Quitumbe, Quito",
     "tipo_activo": "Casa", "operacion": "VENTA", "precio": 95000, "lat": -0.3110, "lon": -78.5600},
]


def _dist(a, b):
    r, p1, p2 = 6371000.0, math.radians(a[0]), math.radians(b[0])
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(h))


def _fila(a, **extra):
    return {"id": a["id"], "direccion_estandarizada": a["direccion_estandarizada"],
            "tipo_activo": a["tipo_activo"], "piso_altura": None, "caminabilidad": 70,
            "walk_score_fuente": "osm", "score_ruido_predictivo": None, "volumen_trafico_historico": None,
            "densidad_poblacional_pico": None, "porcentaje_cobertura_vegetal": None,
            "conectividad": None, "servicios_cercanos": None, "operacion": a["operacion"],
            "precio": a["precio"], **extra}


async def _rows(query, params):
    if "ST_DWithin" in query:
        centro = (float(params["lat"]), float(params["lon"]))
        cerca = sorted(((round(_dist(centro, (a["lat"], a["lon"])), 1), a) for a in INVENTARIO),
                       key=lambda x: x[0])
        return [_fila(a, distancia_metros=d) for d, a in cerca if d <= float(params["radius"])]
    subs = [v.strip("%").lower() for k, v in sorted(params.items()) if k.startswith("t")]
    return [_fila(a, lat=a["lat"], lon=a["lon"]) for a in INVENTARIO
            if all(s in a["direccion_estandarizada"].lower() for s in subs)]


class _Punto:
    latitude, longitude, address = ESTACION[0], ESTACION[1], "Estación Quitumbe, Quito, Ecuador"


class _Nominatim:
    def __init__(self, *_a, **_k):
        pass

    def geocode(self, _q, **_k):
        return _Punto()


@pytest.fixture
def herramientas(monkeypatch):
    monkeypatch.setattr(T, "_fetch_rows", _rows)
    monkeypatch.setattr(T, "Nominatim", _Nominatim)


def _turno(pasos):
    msgs = [HumanMessage("Busco un lugar para vivir cerca de la Estación Quitumbe.")]
    for i, (tool, args) in enumerate(pasos):
        salida = asyncio.run(tool.ainvoke(args))
        msgs += [AIMessage("", tool_calls=[{"name": tool.name, "args": args, "id": f"t{i}"}]),
                 ToolMessage(salida, tool_call_id=f"t{i}", name=tool.name)]
    return msgs


CARDS = [{"id": a["id"]} for a in INVENTARIO]


def test_control_positivo_la_ruta_espacial_produce_distancias_con_autoridad(herramientas):
    msgs = _turno([
        (T.tool_find_assets_by_text, {"query": "Quitumbe"}),
        (T.tool_geocode_address, {"address": "Estación Quitumbe"}),
        (T.tool_search_nearby_assets, {"latitude": ESTACION[0], "longitude": ESTACION[1],
                                       "radius_meters": 2000}),
    ])
    rel = _relacion_territorial_del_turno(msgs, CARDS)
    assert rel is not None, "la búsqueda alrededor del punto geocodificado no produjo relación territorial"
    por_id = {d["id"]: d["distancia_metros"] for d in rel["distancias"]}
    assert set(por_id) == {"q1", "q2", "q3"}, "la relación no liga una distancia a cada tarjeta"
    assert 100 < float(por_id["q1"]) < 250, "q1 está a ~170 m de la estación"


def test_control_negativo_buscar_por_texto_no_produce_autoridad_de_distancia(herramientas):
    msgs = _turno([(T.tool_find_assets_by_text, {"query": "Quitumbe"})])
    salida = json.loads(msgs[-1].content)
    assert len(salida["assets"]) == 3, "el control necesita que la búsqueda por texto SÍ encuentre inventario"
    assert _relacion_territorial_del_turno(msgs, CARDS) is None
    assert not any("distancia" in k for a in salida["assets"] for k in a), \
        "una búsqueda por texto no debe traer distancias"
