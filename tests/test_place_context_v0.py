"""PLAN04-1.2 — `PlaceContextV0` producido de verdad desde `analizar_zona()`.

QUE SE PRUEBA, Y POR QUE ASI

Antes de esta unidad el contrato existia y nadie lo producia. El riesgo de "producirlo"
no es que el objeto salga mal: es que salga bien Y AL LADO, mientras la salida de siempre
se sigue construyendo por su cuenta. Eso seria dos verdades sobre el mismo punto, que es
peor que una sola verdad imperfecta.

Por eso las pruebas no miran solo la forma del objeto. Miran la DIRECCION de la
dependencia: que el numero y la prosa que ve el consumidor salgan del objeto, y que
cambiar el objeto cambie lo que se ve. Un objeto decorativo pasaria cualquier prueba de
forma; no pasa estas.

CERO RED: `_recolectar_zona` es la unica funcion que la toca, y aqui no se llama nunca.
Todo lo demas es puro, que es exactamente lo que esta unidad vino a conseguir.
"""

from __future__ import annotations

import json
import pathlib
import uuid
from datetime import datetime, timezone

import pytest

from app.contracts.evidence_v0 import SourceType
from app.contracts.place_v0 import MeasureStatus, PlaceContextV0
from app.rutas import (
    _CAT_EMOJI,
    MateriaDeZona,
    _min_pie,
    _nombre_limpio,
    derivar_salida_legacy,
    ensamblar_place_context,
    prosa_conectividad,
    prosa_servicios,
)

_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "place_context_1_2_quito.json"
_INSTANTE = datetime(2026, 9, 8, 15, 30, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def congelado() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def materia_de(congelado, **cambios) -> MateriaDeZona:
    """La materia del punto congelado, con los retoques que pida cada caso."""
    ruta = congelado["ruta_a_pie_al_transporte"]
    servicios = [dict(s) for s in congelado["servicios"]]
    transporte = next((s for s in servicios if s["cat"] == "transporte"), None)
    base = dict(
        lat=congelado["punto"]["lat"],
        lon=congelado["punto"]["lon"],
        lugar=dict(congelado["lugar"]),
        walk=dict(congelado["walk"]),
        servicios=servicios,
        se_consultaron_servicios=True,
        transporte=transporte,
        transporte_distancia_m=ruta["distancia_m"],
        transporte_minutos=ruta["duracion_min"],
        transporte_ruta_medida=True,
        recuperado_en=_INSTANTE,
    )
    base.update(cambios)
    return MateriaDeZona(**base)


# ── buscadores de evidencia, NUNCA por indice ────────────────────────────────
#
# Desde R1 una medida puede traer mas de una evidencia —la caminabilidad trae el calculo
# de Contexto y los insumos de OSM; el transporte trae el descubrimiento de la parada y,
# si la hubo, la medicion de Routes—. Leer `evidence[0]` haria que la prueba dependiera
# del orden en que se escribieron, y ese orden no es parte del contrato.


def evidencias(medida, *, tipo=None, proveedor=None):
    """Las evidencias que coinciden con lo que las IDENTIFICA."""
    return [e for e in medida.evidence
            if (tipo is None or e.source_type is tipo)
            and (proveedor is None or e.provider == proveedor)]


def proveedores(medida) -> set:
    return {e.provider for e in medida.evidence}


def todos_los_proveedores(contexto) -> set:
    """Todo proveedor citado en cualquier rincon del objeto."""
    medidas = [contexto.walkability, contexto.nearest_transit, contexto.nearby_places]
    medidas += [d.measure for d in contexto.environment]
    return {e.provider for m in medidas if m is not None for e in m.evidence}


# ── (A) el comportamiento legacy no cambia ───────────────────────────────────
# El oraculo REIMPLEMENTA el algoritmo anterior a esta unidad, tal cual estaba en
# `analizar_zona` sobre 4275655. Comparar contra el es la unica forma de afirmar
# "no cambia nada" sin tener una sola prueba previa de esta funcion — porque no la habia.


_METRO = "\U0001f687"
_PARADA = "\U0001f68f"
_PIN = "\U0001f4cd"


def salida_del_algoritmo_ANTERIOR(m: MateriaDeZona) -> dict:
    conect_txt = None
    if m.transporte:
        masivo = m.transporte.get("es_masivo", False)
        icono = _METRO if masivo else _PARADA
        tipo = "" if masivo else " (parada de bus, NO es Metro)"
        conect_txt = (f"{icono} {_nombre_limpio(m.transporte['nombre'])}{tipo} "
                      f"a ~{m.transporte_distancia_m} m ({m.transporte_minutos} min a pie)")
    otros = [s for s in m.servicios if s.get("cat") != "transporte"]
    serv_txt = ", ".join(
        "{} {} (~{} m)".format(
            _CAT_EMOJI.get(s.get("cat"), _PIN), _nombre_limpio(s["nombre"]), s["distancia_m"]
        )
        for s in otros
    ) or None
    return {
        "lugar": m.lugar,
        "walk_score": m.walk.get("walk_score"),
        "conectividad": conect_txt,
        "servicios": m.servicios,
        "servicios_texto": serv_txt,
        "pois_analizados": m.walk.get("pois_analizados", 0),
    }


PARADA_DE_BUS = {
    "nombre": "Parada Naciones Unidas", "cat": "transporte", "distancia_m": 210,
    "es_masivo": False, "lat": -0.1751, "lon": -78.4862, "fuente": "propio",
}

ESCENARIOS = {
    "nominal": {},
    "sin ruta medida": {"transporte_ruta_medida": False,
                        "transporte_distancia_m": 640, "transporte_minutos": _min_pie(640)},
    "parada de bus, no masivo": {"transporte": PARADA_DE_BUS,
                                 "transporte_distancia_m": 210,
                                 "transporte_minutos": _min_pie(210),
                                 "transporte_ruta_medida": False},
    "sin transporte": {"transporte": None, "transporte_distancia_m": None,
                       "transporte_minutos": None, "transporte_ruta_medida": False},
    "overpass caido": {"walk": {}},
    "overpass sin pois": {"walk": {"walk_score": 0, "fuente": "osm", "pois_analizados": 0}},
    "sin llave de google": {"servicios": [], "se_consultaron_servicios": False,
                            "transporte": None, "transporte_distancia_m": None,
                            "transporte_minutos": None, "transporte_ruta_medida": False},
}


CLAVES_HISTORICAS = (
    "lugar", "walk_score", "conectividad", "servicios", "servicios_texto",
    "pois_analizados",
)


@pytest.mark.parametrize("escenario", sorted(ESCENARIOS))
def test_las_claves_historicas_son_IDENTICAS_a_las_del_algoritmo_anterior(
    congelado, escenario
):
    """PARIDAD TOTAL sobre las seis claves de siempre, en todos los escenarios.

    Incluye el caso que motivó la opción C: con el proveedor respondiendo y cero POIs,
    `walk_score` sigue siendo `0`. Lo que cambia no es ese número, sino que ahora sale
    del objeto con su evidencia detrás en vez de colarse desde la materia prima.
    """
    m = materia_de(congelado, **ESCENARIOS[escenario])
    obtenida = derivar_salida_legacy(ensamblar_place_context(m), m)
    esperada = salida_del_algoritmo_ANTERIOR(m)
    assert {k: obtenida[k] for k in CLAVES_HISTORICAS} == esperada, escenario


def test_la_salida_conserva_las_historicas_y_ANADE_la_procedencia(congelado):
    """La clave nueva es ADITIVA: ningún consumidor deja de encontrar lo que leía."""
    m = materia_de(congelado)
    salida = derivar_salida_legacy(ensamblar_place_context(m), m)
    assert set(salida) == set(CLAVES_HISTORICAS) | {"caminabilidad_fuente"}


@pytest.mark.parametrize(
    "transporte,icono,aviso",
    [
        (None, _METRO, False),                 # el masivo del punto congelado
        (PARADA_DE_BUS, _PARADA, True),
    ],
)
def test_la_prosa_distingue_MASIVO_de_parada_de_bus(congelado, transporte, icono, aviso):
    """No es cosmética: «(parada de bus, NO es Metro)» existe para que nadie compre
    creyendo que tiene Metro a dos cuadras. El punto congelado solo trae transporte
    masivo, así que sin este caso el icono y el aviso no se ejercitan nunca."""
    cambios = {} if transporte is None else {
        "transporte": transporte, "transporte_distancia_m": transporte["distancia_m"],
        "transporte_minutos": _min_pie(transporte["distancia_m"]),
        "transporte_ruta_medida": False,
    }
    m = materia_de(congelado, **cambios)
    contexto = ensamblar_place_context(m)
    texto = prosa_conectividad(contexto)

    assert texto.startswith(icono)
    assert ("parada de bus, NO es Metro" in texto) is aviso
    assert contexto.nearest_transit.value.mode == ("parada" if aviso else "masivo")
    assert texto == salida_del_algoritmo_ANTERIOR(m)["conectividad"]


def test_los_escalares_de_la_prosa_no_ganan_decimales(congelado):
    """El contrato guarda `float`; la prosa de siempre imprime `int`. Sin el redondeo de
    presentacion, «~1520 m» se convertiria en «~1520.0 m» y el texto cambiaria."""
    m = materia_de(congelado)
    texto = prosa_conectividad(ensamblar_place_context(m))
    assert "1520 m" in texto and "1520.0" not in texto
    assert "(19 min a pie)" in texto


# ── (B) AUTORIDAD: lo que se ve sale del objeto ──────────────────────────────


def test_el_numero_de_caminabilidad_sale_del_OBJETO(congelado):
    """Si alguien devolviera el objeto a la decoracion y leyera la materia, esto cae."""
    m = materia_de(congelado)
    contexto = ensamblar_place_context(m)
    alterado = contexto.model_copy(
        update={"walkability": contexto.walkability.model_copy(update={"value": 42.0})}
    )
    assert derivar_salida_legacy(alterado, m)["walk_score"] == 42
    assert m.walk["walk_score"] == 78, "la materia no se toca"


def test_la_prosa_de_conectividad_sale_del_OBJETO(congelado):
    m = materia_de(congelado)
    contexto = ensamblar_place_context(m)
    t = contexto.nearest_transit.value.model_copy(update={"name": "Parada Inventada"})
    alterado = contexto.model_copy(
        update={"nearest_transit": contexto.nearest_transit.model_copy(update={"value": t})}
    )
    assert "Parada Inventada" in derivar_salida_legacy(alterado, m)["conectividad"]
    assert m.transporte["nombre"] == "Estación El Labrador", "la materia no se toca"


def test_la_prosa_de_servicios_sale_del_OBJETO(congelado):
    m = materia_de(congelado)
    contexto = ensamblar_place_context(m)
    lugares = tuple(
        p.model_copy(update={"name": "Servicio Inventado"}) if i == 0 else p
        for i, p in enumerate(contexto.nearby_places.value)
    )
    alterado = contexto.model_copy(
        update={"nearby_places": contexto.nearby_places.model_copy(update={"value": lugares})}
    )
    assert "Servicio Inventado" in derivar_salida_legacy(alterado, m)["servicios_texto"]


def test_sin_objeto_no_hay_prosa(congelado):
    """Vaciar el objeto vacia la prosa. Si la prosa sobreviviera, vendria de otro sitio."""
    m = materia_de(congelado)
    vacio = PlaceContextV0(
        location=ensamblar_place_context(m).location, assembled_at=_INSTANTE,
    )
    assert prosa_conectividad(vacio) is None
    assert prosa_servicios(vacio) is None


# ── (C) PROCEDENCIA ──────────────────────────────────────────────────────────


def test_la_caminabilidad_separa_EL_CALCULO_de_los_INSUMOS(congelado):
    """R1. El puntaje no lo publica OSM: lo calcula Contexto sobre insumos de OSM.

    Fundir las dos cosas en una sola referencia con `provider="overpass"` atribuia
    nuestro metodo al proveedor de los datos, y de paso borraba que el metodo es
    nuestro. Son dos actos distintos y van por separado.
    """
    medida = ensamblar_place_context(materia_de(congelado)).walkability
    assert medida.status is MeasureStatus.AVAILABLE

    calculo = evidencias(medida, tipo=SourceType.OWN_MEASUREMENT)
    assert len(calculo) == 1, "el calculo propio tiene que estar, y una sola vez"
    assert calculo[0].provider == "contexto", "lo produjo Contexto, no el proveedor"
    assert calculo[0].es_medicion is True
    assert "214" in calculo[0].methodology, "la metodologia debe decir sobre cuantos POIs"

    insumos = evidencias(medida, tipo=SourceType.PUBLIC_DATASET, proveedor="overpass")
    assert len(insumos) == 1, "los insumos de OSM tienen que estar acreditados"
    assert "OpenStreetMap" in insumos[0].methodology
    assert "214" in insumos[0].methodology


@pytest.mark.parametrize(
    "medida_real,tipo_esperado,es_medicion",
    [(True, SourceType.PROVIDER_API, True), (False, SourceType.HEURISTIC_ESTIMATE, False)],
)
def test_los_minutos_a_pie_distinguen_MEDIDO_de_ESTIMADO(
    congelado, medida_real, tipo_esperado, es_medicion
):
    """La distincion que la prosa de hoy hace invisible: «19 min a pie» se lee igual
    venga de Google Routes o de dividir la linea recta entre 80."""
    m = materia_de(congelado, transporte_ruta_medida=medida_real)
    dim = ensamblar_place_context(m).environment[0]
    assert dim.dimension == "transporte_minutos_a_pie"
    assert len(dim.measure.evidence) == 1, "los minutos salen de un solo acto"
    evidencia = dim.measure.evidence[0]
    assert evidencia.source_type is tipo_esperado
    assert evidencia.es_medicion is es_medicion
    if not es_medicion:
        assert evidencia.limitations, "una estimacion no puede entrar callada"


def test_los_minutos_estimados_NO_van_a_travel_to_anchors(congelado):
    """`travel_to_anchors` es, por contrato, el trayecto a un ancla DEL COMPRADOR,
    correlacionado por `anchor_id`. Una parada de bus no es el ancla de nadie: meterla
    ahi colonizaria con Place una costura que el contrato reserva para Buyer."""
    assert ensamblar_place_context(materia_de(congelado)).travel_to_anchors == ()


# ── (D) DATOS AUSENTES ───────────────────────────────────────────────────────


WALK_CAIDO = {}
WALK_VACIO = {"walk_score": 0, "fuente": "osm", "pois_analizados": 0}
WALK_RICO = {"walk_score": 78, "fuente": "osm", "pois_analizados": 214}


def test_caso_1_proveedor_CAIDO_es_insuficiente_y_sin_valor(congelado):
    """Se consultó y no hubo respuesta: la dimensión se evaluó, la evidencia no alcanza.
    No es `unknown`, que diría que ni se intentó."""
    medida = ensamblar_place_context(materia_de(congelado, walk=WALK_CAIDO)).walkability
    assert medida.status is MeasureStatus.INSUFFICIENT_EVIDENCE
    assert medida.value is None
    assert medida.evidence == ()
    assert medida.limitations, "la insuficiencia tiene que decir por que"


def test_caso_2_proveedor_OK_con_cero_pois_es_un_CERO_MEDIDO(congelado):
    """El caso que costó una adjudicación.

    La consulta se hizo, la respuesta llegó, y el cálculo sobre esa respuesta da 0. Eso
    ES una medición y borrarla perdería información real. Lo que exige es declarar qué
    no puede sostener: un 0 por cobertura nula no distingue «zona sin comercios» de
    «zona que OSM no tiene mapeada».
    """
    medida = ensamblar_place_context(materia_de(congelado, walk=WALK_VACIO)).walkability
    assert medida.status is MeasureStatus.AVAILABLE
    assert medida.value == 0.0
    assert medida.evidence, "un cero medido también necesita procedencia"
    assert evidencias(medida, tipo=SourceType.OWN_MEASUREMENT), "el calculo sigue siendo nuestro"
    assert evidencias(medida, proveedor="overpass"), "y los insumos siguen siendo de OSM"
    assert medida.limitations, "un 0 por cobertura nula no puede entrar callado"
    assert any("cobertura" in l for l in medida.limitations)


def test_caso_3_proveedor_OK_con_pois_trae_el_valor_calculado(congelado):
    medida = ensamblar_place_context(materia_de(congelado, walk=WALK_RICO)).walkability
    assert medida.status is MeasureStatus.AVAILABLE
    assert medida.value == 78.0
    assert medida.limitations == (), "con cobertura real no hay límite que declarar"


def test_los_casos_1_y_2_NO_se_confunden(congelado):
    """La discriminación que pide el mandato: caída del proveedor frente a respuesta
    vacía. Antes las dos acababan en «sin valor»; ahora solo una."""
    caido = ensamblar_place_context(materia_de(congelado, walk=WALK_CAIDO)).walkability
    vacio = ensamblar_place_context(materia_de(congelado, walk=WALK_VACIO)).walkability
    assert caido.status is not vacio.status
    assert (caido.value, vacio.value) == (None, 0.0)
    assert (bool(caido.evidence), bool(vacio.evidence)) == (False, True)


def test_sin_llave_de_google_es_UNKNOWN_y_no_INSUFICIENTE(congelado):
    """«No se pregunto» y «se pregunto y no habia» son cosas distintas."""
    m = materia_de(congelado, servicios=[], se_consultaron_servicios=False,
                   transporte=None, transporte_distancia_m=None,
                   transporte_minutos=None, transporte_ruta_medida=False)
    contexto = ensamblar_place_context(m)
    assert contexto.nearby_places.status is MeasureStatus.UNKNOWN
    assert contexto.nearest_transit.status is MeasureStatus.UNKNOWN


def test_con_llave_y_sin_resultados_es_INSUFICIENTE(congelado):
    m = materia_de(congelado, servicios=[], se_consultaron_servicios=True,
                   transporte=None, transporte_distancia_m=None,
                   transporte_minutos=None, transporte_ruta_medida=False)
    contexto = ensamblar_place_context(m)
    assert contexto.nearby_places.status is MeasureStatus.INSUFFICIENT_EVIDENCE
    assert contexto.nearest_transit.status is MeasureStatus.INSUFFICIENT_EVIDENCE


def test_sin_transporte_no_hay_dimension_de_minutos(congelado):
    """La dimension AUSENTE dice algo sobre esta consulta, no sobre el lugar."""
    m = materia_de(congelado, transporte=None, transporte_distancia_m=None,
                   transporte_minutos=None, transporte_ruta_medida=False)
    assert ensamblar_place_context(m).environment == ()


@pytest.mark.parametrize(
    "walk,score,fuente",
    [
        (WALK_CAIDO, None, None),
        (WALK_VACIO, 0, "osm"),
        (WALK_RICO, 78, "osm"),
    ],
)
def test_la_procedencia_legacy_se_DERIVA_del_objeto(congelado, walk, score, fuente):
    """`caminabilidad_fuente` con CERO POIs pasa de `None` a `"osm"`, y ese es el único
    cambio de conducta de esta unidad.

    La regla anterior vivía en el consumidor y era `"osm" if pois else None`: mentía
    justo en el caso 2, donde el cálculo SÍ se hizo sobre OSM. Ahora la procedencia
    viaja desde la evidencia, que es quien la sabe. Cuánta cobertura hubo lo sigue
    diciendo `cobertura`, que es su sitio.
    """
    m = materia_de(congelado, walk=walk)
    salida = derivar_salida_legacy(ensamblar_place_context(m), m)
    assert salida["walk_score"] == score
    assert salida["caminabilidad_fuente"] == fuente


def test_la_procedencia_sale_de_la_EVIDENCIA_y_no_de_un_literal(congelado):
    """Si alguien la fijara a `"osm"`, cambiar el tipo de evidencia no cambiaría nada."""
    from app.contracts.place_v0 import PlaceMeasureV0
    from app.rutas import procedencia_caminabilidad_legacy

    contexto = ensamblar_place_context(materia_de(congelado))
    calculo = evidencias(contexto.walkability, tipo=SourceType.OWN_MEASUREMENT)[0]
    heuristica = calculo.model_copy(
        update={"source_type": SourceType.HEURISTIC_ESTIMATE,
                "limitations": ("estimada, no medida",)}
    )
    alterado = contexto.model_copy(
        update={"walkability": PlaceMeasureV0[float](
            status=MeasureStatus.AVAILABLE, value=50.0, evidence=(heuristica,))}
    )
    assert procedencia_caminabilidad_legacy(alterado) == "heuristico"


# ── (E) UN SOLO FETCH ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analizar_zona_recolecta_UNA_SOLA_VEZ(congelado, monkeypatch):
    """El riesgo real de introducir un objeto es pedir los datos dos veces: una para el
    objeto y otra para la salida de siempre. Eso duplicaria coste y latencia y podria
    devolver dos verdades distintas del mismo punto."""
    import app.rutas as rutas

    veces = []

    async def _falso(lat, lon):
        veces.append((lat, lon))
        return materia_de(congelado)

    monkeypatch.setattr(rutas, "_recolectar_zona", _falso)
    salida = await rutas.analizar_zona(-0.1755, -78.4858)

    assert len(veces) == 1, f"se recolecto {len(veces)} veces"
    assert salida["walk_score"] == 78


@pytest.mark.asyncio
async def test_place_context_de_tambien_recolecta_una_sola_vez(congelado, monkeypatch):
    import app.rutas as rutas

    veces = []

    async def _falso(lat, lon):
        veces.append((lat, lon))
        return materia_de(congelado)

    monkeypatch.setattr(rutas, "_recolectar_zona", _falso)
    contexto = await rutas.place_context_de(-0.1755, -78.4858)

    assert len(veces) == 1
    assert isinstance(contexto, PlaceContextV0)


# ── (F) el objeto es serializable, que es para lo que existe ─────────────────


def test_el_contexto_va_y_vuelve_de_json_sin_perder_nada(congelado):
    contexto = ensamblar_place_context(materia_de(congelado))
    assert PlaceContextV0.model_validate_json(contexto.model_dump_json()) == contexto


def test_esta_fixture_es_de_1_2_y_NO_del_loop_de_1_6(congelado):
    """1.6 pide 1 buyer + 10 properties + sus places congelados. Esto es un punto suelto.
    Dar esta fixture por 1.6 daria por avanzada una unidad que no lo esta."""
    assert set(congelado) >= {"punto", "lugar", "walk", "servicios"}
    assert "buyer" not in congelado and "properties" not in congelado
    assert "1.6" in " ".join(congelado["_por_que_existe"])


# ── (G) el consumidor real: tool_analyze_location ────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "walk,caminabilidad,fuente,cobertura",
    [
        (WALK_CAIDO, None, None, "sin datos"),
        (WALK_VACIO, 0, "osm", "sin datos"),
        (WALK_RICO, 78, "osm", "rica"),
    ],
)
async def test_tool_analyze_location_recibe_la_procedencia_corregida(
    congelado, monkeypatch, walk, caminabilidad, fuente, cobertura
):
    """El único consumidor de esta costura, por su nombre real.

    Es aquí donde se ve la correccion: con el proveedor respondiendo y cero POIs, la
    tool afirmaba `caminabilidad: 0` con `caminabilidad_fuente: null` —un número sin
    procedencia, que es lo que el contrato existe para impedir—. Ahora dice `"osm"`, y
    la falta de cobertura la sigue diciendo `cobertura: "sin datos"`.
    """
    import app.rutas as rutas
    from app.agent.tools import tool_analyze_location

    m = materia_de(congelado, walk=walk)

    async def _falso(lat, lon):
        return derivar_salida_legacy(ensamblar_place_context(m), m)

    monkeypatch.setattr(rutas, "analizar_zona", _falso)
    crudo = await tool_analyze_location.ainvoke(
        {"latitude": -0.1755, "longitude": -78.4858}
    )
    salida = json.loads(crudo)

    assert salida["caminabilidad"] == caminabilidad
    assert salida["caminabilidad_fuente"] == fuente
    assert salida["cobertura"] == cobertura


def test_tool_analyze_location_no_vuelve_a_INFERIR_la_procedencia():
    """La regla vieja vivía en el fuente de la tool. Si volviera, esto cae.

    Se mira el AST y no el texto: el comentario que explica por qué se retiró la regla
    CITA la regla, así que un `grep` se detectaría a sí mismo. Lo que se exige es que el
    valor de `caminabilidad_fuente` sea una lectura del dict —`a[...]`— y no una
    expresión condicional que lo deduzca de otra cosa.
    """
    import ast
    import pathlib as _pl

    import app.agent.tools as tools

    arbol = ast.parse(_pl.Path(tools.__file__).read_text(encoding="utf-8"))
    funcion = next(
        n for n in ast.walk(arbol)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "tool_analyze_location"
    )
    valores = [
        v for d in ast.walk(funcion) if isinstance(d, ast.Dict)
        for k, v in zip(d.keys, d.values)
        if isinstance(k, ast.Constant) and k.value == "caminabilidad_fuente"
    ]
    assert len(valores) == 1, "la tool debe declarar la procedencia una sola vez"
    valor = valores[0]
    assert isinstance(valor, ast.Subscript), (
        f"la procedencia se vuelve a deducir aquí ({ast.dump(valor)[:70]}) en vez de "
        "leerse de la salida derivada del objeto"
    )
    assert isinstance(valor.value, ast.Name) and valor.value.id == "a"
    assert valor.slice.value == "caminabilidad_fuente"


# ── (H) PLAN04-1.2-R1 · identidad estable y procedencia leida del dato ───────
#
# Las cuatro cosas que R1 vino a cerrar, y por que cada una importa fuera del contrato:
#
#   · la identidad de la evidencia era aleatoria, asi que «el objeto es el mismo» no era
#     una afirmacion comprobable;
#   · la lista de servicios se atribuia ENTERA a Google Places, incluidos los POIs de
#     nuestra capa —el foso acreditado a un tercero—;
#   · medir la caminata con Routes BORRABA de donde habia salido la parada;
#   · la traduccion legacy leia `evidence[0]`, asi que reordenar la evidencia habria
#     cambiado lo que ve el consumidor sin tocar un dato.


NAMESPACE_DECLARADO = "contexto.ai/place/evidence/v0"


def id_esperado(materia, dimension, ev) -> str:
    """Reimplementacion independiente del esquema de identidad.

    No compara contra una constante congelada —eso se rompería al reescribir una
    metodologia, que es cambio legitimo— sino contra la REGLA: `uuid5` sobre
    (punto, instante, dimension, origen, contenido). Un `uuid4` o un `hash()` no la
    cumplen ni por casualidad.
    """
    ns = uuid.uuid5(uuid.NAMESPACE_URL, NAMESPACE_DECLARADO)
    semilla = "\x1f".join((
        repr(materia.lat), repr(materia.lon), materia.recuperado_en.isoformat(),
        dimension, ev.source_type.value, ev.provider or "", ev.source_id or "",
        ev.methodology, "\x1e".join(ev.limitations),
    ))
    return str(uuid.uuid5(ns, semilla))


def test_dos_ensamblajes_del_MISMO_material_dan_el_MISMO_JSON(congelado):
    """El requisito de R1, en su forma mas cruda: byte a byte.

    `ensamblar_place_context` se declara pura. Con `evidence_id` cayendo en `uuid4` no lo
    era: dos ensamblajes del mismo material daban objetos distintos, y cualquier
    consumidor que compare o cachee por serializacion veia cambios donde no los hay.
    """
    m = materia_de(congelado)
    uno = ensamblar_place_context(m).model_dump_json()
    otro = ensamblar_place_context(m).model_dump_json()
    assert uno == otro
    assert ensamblar_place_context(m) == ensamblar_place_context(m)


def test_la_identidad_de_la_evidencia_es_uuid5_y_NO_azar(congelado):
    """Que sea estable no basta: tiene que serlo POR CONSTRUCCION.

    Un `uuid4` cacheado en un módulo tambien daria dos ensamblajes iguales dentro de un
    proceso y cambiaria en el siguiente. Aqui se exige la regla completa.
    """
    m = materia_de(congelado)
    contexto = ensamblar_place_context(m)
    for dimension, medida in (("walkability", contexto.walkability),
                              ("nearest_transit", contexto.nearest_transit),
                              ("nearby_places", contexto.nearby_places)):
        for ev in medida.evidence:
            assert uuid.UUID(ev.evidence_id).version == 5, "no es un uuid5"
            assert ev.evidence_id == id_esperado(m, dimension, ev)
    dim = contexto.environment[0]
    assert dim.measure.evidence[0].evidence_id == id_esperado(
        m, dim.dimension, dim.measure.evidence[0])


def test_dos_puntos_distintos_NO_comparten_evidence_id(congelado):
    """`DecisionContextV0` resuelve sus referencias por `evidence_id`. Dos lugares con la
    misma metodologia compartiendo asa no seria cosmetico: seria citar la evidencia de
    otro lugar."""
    aqui = ensamblar_place_context(materia_de(congelado))
    alla = ensamblar_place_context(materia_de(congelado, lat=-0.2100))
    ids_aqui = {e.evidence_id for e in aqui.walkability.evidence}
    ids_alla = {e.evidence_id for e in alla.walkability.evidence}
    assert ids_aqui and ids_aqui.isdisjoint(ids_alla)


def test_las_dos_evidencias_de_caminabilidad_NO_comparten_asa(congelado):
    """La dimension entra en la identidad, pero tambien el origen: dos evidencias de la
    misma dimension tienen que distinguirse."""
    medida = ensamblar_place_context(materia_de(congelado)).walkability
    assert len({e.evidence_id for e in medida.evidence}) == len(medida.evidence)


# ── procedencia LEIDA de `fuente`, servicio por servicio ─────────────────────


def servicios_con_fuente(congelado, *fuentes):
    """Los servicios del punto congelado, con la `fuente` que pida cada caso."""
    ss = [dict(s) for s in congelado["servicios"] if s["cat"] != "transporte"]
    for s, f in zip(ss, fuentes):
        if f is None:
            s.pop("fuente", None)
        else:
            s["fuente"] = f
    return ss


def test_capa_PROPIA_no_atribuye_NADA_a_google_places(congelado):
    """La fixture es toda de nuestra capa. Antes de R1, la medida entera se acreditaba a
    Google Places: el foso, atribuido a un tercero."""
    contexto = ensamblar_place_context(materia_de(congelado))
    assert proveedores(contexto.nearby_places) == {"contexto-capa-propia"}
    assert evidencias(contexto.nearby_places, tipo=SourceType.OWN_MEASUREMENT)
    assert "google-places" not in todos_los_proveedores(contexto)


def test_solo_GOOGLE_se_atribuye_a_google_places(congelado):
    """El caso simetrico: sin capa propia en este punto, el relleno es de Google y se
    dice. Sin este caso, «no atribuye a Google» pasaria tambien con la atribucion rota
    al reves."""
    m = materia_de(congelado,
                   servicios=servicios_con_fuente(congelado, "google", "google", "google"))
    medida = ensamblar_place_context(m).nearby_places
    assert proveedores(medida) == {"google-places"}
    assert evidencias(medida, tipo=SourceType.PROVIDER_API, proveedor="google-places")
    assert not evidencias(medida, tipo=SourceType.OWN_MEASUREMENT)


def test_respuesta_MIXTA_declara_LOS_DOS_origenes(congelado):
    """El caso real de `_servicios_con_coords`: capa propia + relleno de Google para las
    categorias que la capa no cubre en ese punto. UNA evidencia por origen presente."""
    m = materia_de(congelado,
                   servicios=servicios_con_fuente(congelado, "propio", "google", "propio"))
    medida = ensamblar_place_context(m).nearby_places
    assert proveedores(medida) == {"contexto-capa-propia", "google-places"}
    assert len(medida.evidence) == 2, "una por ORIGEN, no una por servicio"
    assert medida.limitations == (), "todos los servicios traen origen declarado"


def test_un_servicio_SIN_fuente_no_se_atribuye_a_nadie(congelado):
    """Fuente sintetica: la capa siempre marca `fuente`, asi que sin infringirla esta
    regla no se ejerceria nunca y neutralizarla no cambiaria nada.

    El servicio SI entra en el valor —su distancia se midio— pero la medida declara
    cuantos llegaron sin origen. Callarlo dejaria que se leyeran como acreditados por
    los origenes que si estan.
    """
    m = materia_de(congelado,
                   servicios=servicios_con_fuente(congelado, None, "propio", "propio"))
    medida = ensamblar_place_context(m).nearby_places
    assert medida.status is MeasureStatus.AVAILABLE
    assert len(medida.value) == 3, "el servicio no se descarta"
    assert proveedores(medida) == {"contexto-capa-propia"}
    assert medida.limitations, "un servicio sin origen no puede entrar callado"
    assert "1 de los 3" in medida.limitations[0]


def test_TODOS_los_servicios_sin_fuente_dejan_la_medida_SIN_valor(congelado):
    """Cuando no queda ni un origen acreditable, el contrato ya dice que hacer: sin
    procedencia no hay valor disponible. Es el mismo invariante de E0.4, aplicado aqui."""
    m = materia_de(congelado,
                   servicios=servicios_con_fuente(congelado, None, None, None))
    contexto = ensamblar_place_context(m)
    assert contexto.nearby_places.status is MeasureStatus.INSUFFICIENT_EVIDENCE
    assert contexto.nearby_places.value is None
    assert contexto.nearby_places.limitations
    assert prosa_servicios(contexto) is None


# ── transporte: descubrimiento y medicion de ruta, por separado ──────────────


def test_ruta_MEDIDA_conserva_descubrimiento_Y_routes(congelado):
    """El defecto que R1 cierra: al medir la caminata, la evidencia pasaba a decir
    `google-routes` y de donde habia salido la parada desaparecia."""
    medida = ensamblar_place_context(
        materia_de(congelado, transporte_ruta_medida=True)).nearest_transit
    assert proveedores(medida) == {"contexto-capa-propia", "google-routes"}
    assert len(medida.evidence) == 2


def test_ruta_ESTIMADA_conserva_descubrimiento_y_NO_inventa_routes(congelado):
    """Sin medicion no hay evidencia de Routes. Que exista o no es la unica senal
    estructural de si `distance_m` es una caminata por calles o una linea recta."""
    medida = ensamblar_place_context(
        materia_de(congelado, transporte_ruta_medida=False,
                   transporte_distancia_m=640,
                   transporte_minutos=_min_pie(640))).nearest_transit
    assert proveedores(medida) == {"contexto-capa-propia"}
    assert not evidencias(medida, proveedor="google-routes")


def test_la_parada_de_GOOGLE_se_atribuye_a_google_places(congelado):
    """El descubrimiento tambien se lee de `fuente`, no se asume propio."""
    parada = dict(PARADA_DE_BUS, fuente="google")
    medida = ensamblar_place_context(
        materia_de(congelado, transporte=parada, transporte_distancia_m=210,
                   transporte_minutos=_min_pie(210),
                   transporte_ruta_medida=False)).nearest_transit
    assert proveedores(medida) == {"google-places"}


def test_una_parada_SIN_fuente_ni_ruta_no_se_presenta_como_disponible(congelado):
    """Fuente sintetica, por el mismo motivo que en servicios. Sin descubrimiento
    acreditado y sin Routes no queda ninguna evidencia, y una parada sin procedencia no
    se publica: tambien desaparece de la prosa."""
    parada = {k: v for k, v in PARADA_DE_BUS.items() if k != "fuente"}
    contexto = ensamblar_place_context(
        materia_de(congelado, transporte=parada, transporte_distancia_m=210,
                   transporte_minutos=_min_pie(210), transporte_ruta_medida=False))
    assert contexto.nearest_transit.status is MeasureStatus.INSUFFICIENT_EVIDENCE
    assert contexto.nearest_transit.value is None
    assert prosa_conectividad(contexto) is None


# ── la traduccion legacy no depende del ORDEN de la evidencia ────────────────


def test_la_procedencia_legacy_NO_depende_del_ORDEN_de_la_evidencia(congelado):
    """La caminabilidad trae dos evidencias. Con `evidence[0]`, invertirlas cambiaba lo
    que ve el consumidor sin que ningun dato cambiara."""
    from app.contracts.place_v0 import PlaceMeasureV0
    from app.rutas import procedencia_caminabilidad_legacy

    contexto = ensamblar_place_context(materia_de(congelado))
    original = contexto.walkability
    assert len(original.evidence) >= 2, "sin dos evidencias esta prueba no mide nada"
    invertido = contexto.model_copy(
        update={"walkability": PlaceMeasureV0[float](
            status=original.status, value=original.value,
            evidence=tuple(reversed(original.evidence)),
            limitations=original.limitations)}
    )
    assert (procedencia_caminabilidad_legacy(invertido)
            == procedencia_caminabilidad_legacy(contexto) == "osm")


def test_el_ORDEN_de_los_origenes_es_una_funcion_del_dato(congelado):
    """`sorted` sobre las fuentes, y no el orden en que un `set` decida iterar.

    El hash de las cadenas va salado por proceso (`PYTHONHASHSEED`), asi que un `set`
    puede iterar distinto en la corrida siguiente y el JSON dejaria de ser identico ENTRE
    procesos —que es la mitad util de la promesa de esta unidad—. Dentro de un solo
    proceso esa deriva no se puede observar, asi que se mide la propiedad que la impide:
    el orden es una funcion del dato, y esta declarado.
    """
    m = materia_de(congelado,
                   servicios=servicios_con_fuente(congelado, "propio", "google", "propio"))
    medida = ensamblar_place_context(m).nearby_places
    assert [e.provider for e in medida.evidence] == ["google-places", "contexto-capa-propia"]


def test_sin_VALOR_no_hay_procedencia_aunque_SOBRE_evidencia(congelado):
    """Fuente sintetica, y el reverso exacto de E0.3.

    El contrato permite evidencia con `insufficient_evidence` —una fuente puede existir y
    no alcanzar—. Ahi la traduccion legacy tiene que callar: un numero que no existe no
    puede tener procedencia. Con el productor de hoy ese estado nunca trae evidencia, asi
    que sin construirlo a mano la guarda no se ejerceria nunca.
    """
    from app.contracts.place_v0 import PlaceMeasureV0
    from app.rutas import _walk_score_legacy, procedencia_caminabilidad_legacy

    contexto = ensamblar_place_context(materia_de(congelado))
    sin_valor = contexto.model_copy(update={"walkability": PlaceMeasureV0[float](
        status=MeasureStatus.INSUFFICIENT_EVIDENCE,
        evidence=contexto.walkability.evidence,
        limitations=("la lectura llego pero no alcanza para un puntaje",))})

    assert procedencia_caminabilidad_legacy(sin_valor) is None
    assert _walk_score_legacy(sin_valor) is None
