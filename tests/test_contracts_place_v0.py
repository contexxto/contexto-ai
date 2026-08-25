"""E1.4 — PlaceContextV0.

La regla que estas pruebas defienden es una sola: **"no sabemos" no se puede confundir
con "tenemos un valor"**. Es E0.3 y E0.4 convertidos en invariante — la caminabilidad
que afirmaba "OpenStreetMap" sobre un número estimado, y el ruido y la vegetación que
movían el score ±50 y ±80 puntos sin una sola medición detrás.
"""

import json
import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.contracts.common_v0 import TravelMode
from app.contracts.evidence_v0 import (
    EvidenceRefV0,
    PersistencePolicy,
    SourceType,
)
from app.contracts.place_v0 import (
    CONTRACT_VERSION,
    GeoPoint,
    IsochroneV0,
    MeasureStatus,
    NamedMeasureV0,
    NearbyPlaceV0,
    NearestTransitV0,
    PlaceContextV0,
    PlaceMeasureV0,
    TravelToAnchorV0,
    json_schema,
)

AHORA = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)

_POLIGONO = json.dumps(
    {"type": "Polygon", "coordinates": [[[-78.5, -0.2], [-78.4, -0.2], [-78.4, -0.1], [-78.5, -0.2]]]}
)


def _medida(**cambios):
    return EvidenceRefV0(
        **{
            "source_type": SourceType.OWN_MEASUREMENT,
            "observed_at": AHORA,
            "retrieved_at": AHORA,
            "methodology": "distancia por red peatonal OSM a POI de pois_propios",
            "persistence_policy": PersistencePolicy.PERSISTABLE,
            **cambios,
        }
    )


def _lugar(**cambios):
    base = dict(location=GeoPoint(lat=-0.18, lon=-78.48), assembled_at=AHORA)
    base.update(cambios)
    return PlaceContextV0(**base)


# ── la regla central: estado y valor ─────────────────────────────────────────────


def test_available_exige_valor():
    with pytest.raises(ValidationError, match="sin value"):
        PlaceMeasureV0[float](status=MeasureStatus.AVAILABLE, evidence=(_medida(),))


def test_available_exige_evidencia():
    """Un valor sin procedencia es exactamente lo que en E0.4 movía el ranking."""
    with pytest.raises(ValidationError, match="sin evidence"):
        PlaceMeasureV0[float](status=MeasureStatus.AVAILABLE, value=82.0)


def test_available_con_valor_y_evidencia_es_valido():
    m = PlaceMeasureV0[float](
        status=MeasureStatus.AVAILABLE, value=82.0, evidence=(_medida(),)
    )
    assert m.hay_valor is True
    assert m.value == 82.0


@pytest.mark.parametrize(
    "estado", [MeasureStatus.UNKNOWN, MeasureStatus.INSUFFICIENT_EVIDENCE]
)
def test_sin_valor_defendible_no_se_rellena_con_un_numero(estado):
    """El relleno sintético es el defecto de E0.4 en una línea."""
    with pytest.raises(ValidationError, match="sintética"):
        PlaceMeasureV0[float](status=estado, value=50.0)


@pytest.mark.parametrize(
    "estado", [MeasureStatus.UNKNOWN, MeasureStatus.INSUFFICIENT_EVIDENCE]
)
def test_sin_valor_defendible_tampoco_se_rellena_con_una_categoria(estado):
    with pytest.raises(ValidationError, match="sintética"):
        PlaceMeasureV0[str](status=estado, value="medio")


@pytest.mark.parametrize(
    "estado", [MeasureStatus.UNKNOWN, MeasureStatus.INSUFFICIENT_EVIDENCE]
)
def test_los_dos_estados_sin_valor_son_construibles(estado):
    m = PlaceMeasureV0[float](status=estado)
    assert m.value is None
    assert m.hay_valor is False


def test_unknown_e_insufficient_evidence_no_son_lo_mismo():
    """`unknown` = la dimensión está en el contexto y su valor se desconoce.
    `insufficient_evidence` = se evaluó y la evidencia no alcanzó. La segunda dice que
    alguien miró."""
    assert MeasureStatus.UNKNOWN != MeasureStatus.INSUFFICIENT_EVIDENCE
    a = PlaceMeasureV0[float](status=MeasureStatus.UNKNOWN)
    b = PlaceMeasureV0[float](status=MeasureStatus.INSUFFICIENT_EVIDENCE)
    assert a != b


def test_la_evidencia_puede_explicar_la_insuficiencia_sin_volverse_un_valor():
    """Que exista una referencia no significa que haya un número."""
    m = PlaceMeasureV0[float](
        status=MeasureStatus.INSUFFICIENT_EVIDENCE,
        evidence=(
            _medida(
                source_type=SourceType.HEURISTIC_ESTIMATE,
                limitations=("solo hay una estación de medición y está a 4 km",),
            ),
        ),
        limitations=("no hay medición de ruido en este punto",),
    )
    assert m.evidence
    assert m.value is None
    assert m.hay_valor is False


def test_una_dimension_ausente_sigue_siendo_valida():
    """Ausente = no evaluada, no solicitada, o no ensamblada en ESTE contexto. No dice
    nada sobre el lugar; dice algo sobre esta consulta."""
    lugar = _lugar()
    assert lugar.walkability is None
    assert lugar.nearest_transit is None
    assert lugar.environment == ()


def test_la_serializacion_conserva_la_diferencia_entre_ausencia_e_insuficiencia():
    """El riesgo real: que al pasar por JSON las dos se vuelvan lo mismo y aguas abajo
    nadie pueda distinguir "no lo miramos" de "lo miramos y no alcanza"."""
    ausente = _lugar()
    insuficiente = _lugar(
        walkability=PlaceMeasureV0[float](status=MeasureStatus.INSUFFICIENT_EVIDENCE)
    )

    crudo_a = ausente.model_dump(mode="json")
    crudo_i = insuficiente.model_dump(mode="json")
    assert crudo_a["walkability"] is None
    assert crudo_i["walkability"]["status"] == "insufficient_evidence"
    assert crudo_i["walkability"]["value"] is None

    assert PlaceContextV0.model_validate(crudo_a).walkability is None
    vuelta = PlaceContextV0.model_validate(crudo_i).walkability
    assert vuelta.status is MeasureStatus.INSUFFICIENT_EVIDENCE
    assert vuelta.value is None


# ── heurísticas: pueden llevar valor, pero declarando ─────────────────────────────


def test_una_heuristica_real_puede_llevar_valor_si_declara_metodologia_y_limites():
    """No están prohibidas: a veces son lo único que hay. Lo prohibido es que entren
    calladas o disfrazadas de medición."""
    m = PlaceMeasureV0[float](
        status=MeasureStatus.AVAILABLE,
        value=60.0,
        evidence=(
            _medida(
                source_type=SourceType.HEURISTIC_ESTIMATE,
                methodology="estimación por zona a partir de densidad de vías",
                limitations=("no hay red peatonal mapeada en este sector",),
            ),
        ),
    )
    assert m.value == 60.0
    assert m.evidence[0].es_medicion is False
    assert m.evidence[0].limitations


def test_una_heuristica_sin_limites_no_llega_ni_a_construirse():
    """Lo corta E1.1 antes: la evidencia no se puede crear."""
    with pytest.raises(ValidationError, match="limitations"):
        _medida(source_type=SourceType.HEURISTIC_ESTIMATE, limitations=())


@pytest.mark.parametrize("dimension", ["ruido", "trafico", "vegetacion"])
def test_ruido_trafico_y_vegetacion_sin_evidencia_no_pueden_traer_valor(dimension):
    """Las tres dimensiones concretas de E0.4, con el defecto cerrado por construcción."""
    with pytest.raises(ValidationError, match="sin evidence"):
        NamedMeasureV0(
            dimension=dimension,
            measure=PlaceMeasureV0[float](status=MeasureStatus.AVAILABLE, value=50.0),
        )


@pytest.mark.parametrize("dimension", ["ruido", "trafico", "vegetacion"])
def test_esas_dimensiones_si_pueden_estar_presentes_sin_valor(dimension):
    """E0.4 las sacó del ranking pero conservó su explicación al usuario. Esto es esa
    decisión hecha estructura."""
    n = NamedMeasureV0(
        dimension=dimension,
        measure=PlaceMeasureV0[float](
            status=MeasureStatus.INSUFFICIENT_EVIDENCE,
            limitations=(f"no tenemos medición de {dimension} aquí",),
        ),
    )
    assert n.measure.value is None
    assert n.measure.limitations


def test_una_dimension_del_entorno_no_puede_estar_dos_veces():
    with pytest.raises(ValidationError, match="repetida"):
        _lugar(
            environment=(
                NamedMeasureV0(
                    dimension="ruido",
                    measure=PlaceMeasureV0[float](status=MeasureStatus.UNKNOWN),
                ),
                NamedMeasureV0(
                    dimension="Ruido",
                    measure=PlaceMeasureV0[float](status=MeasureStatus.UNKNOWN),
                ),
            )
        )


# ── nada de scoring ni de elegibilidad ───────────────────────────────────────────


def test_el_contrato_no_puntua_ni_pondera_ni_declara_elegibilidad():
    """Esa decisión es del Decision Harness. Meterla aquí haría que el contrato tomara
    partido sobre algo que todavía no se ha diseñado."""
    texto = json.dumps(json_schema()).lower()
    for prohibido in ('"score"', '"weight"', '"rank"', '"decision_eligible"', '"priority"'):
        assert prohibido not in texto, f"apareció {prohibido}"


def test_ningun_string_humano_como_representacion_primaria():
    """La prosa se DERIVA de este objeto. Si la prosa fuera el dato, habría que
    reparsearla para comprobar cualquier cosa."""
    props = set(json_schema()["properties"])
    for prohibido in ("summary", "description", "resumen", "prosa", "text", "narrative"):
        assert prohibido not in props


# ── caminabilidad: el arreglo de E0.3 hecho estructura ───────────────────────────


def test_la_caminabilidad_lleva_su_procedencia_dentro():
    """Antes el motor decía "OpenStreetMap" sobre un número estimado porque la fuente
    viajaba en una columna que nadie miraba."""
    medida = _lugar(
        walkability=PlaceMeasureV0[float](
            status=MeasureStatus.AVAILABLE,
            value=82.0,
            evidence=(_medida(source_type=SourceType.PUBLIC_DATASET, provider="osm"),),
        )
    )
    estimada = _lugar(
        walkability=PlaceMeasureV0[float](
            status=MeasureStatus.AVAILABLE,
            value=60.0,
            evidence=(
                _medida(
                    source_type=SourceType.HEURISTIC_ESTIMATE,
                    methodology="estimación por zona",
                    limitations=("sin red peatonal mapeada",),
                ),
            ),
        )
    )
    assert medida.walkability.evidence[0].es_medicion is True
    assert estimada.walkability.evidence[0].es_medicion is False
    assert medida.walkability.value != estimada.walkability.value


# ── transporte, servicios, trayectos, isócronas ──────────────────────────────────


def test_la_parada_mas_cercana_es_estructura_y_no_prosa():
    t = NearestTransitV0(distance_m=180.0, mode="metro", name="El Ejido")
    assert (t.distance_m, t.mode) == (180.0, "metro")


def test_los_servicios_cercanos_son_estructura():
    p = NearbyPlaceV0(category="farmacia", distance_m=120.0, name="Fybeca")
    assert p.category == "farmacia"
    m = PlaceMeasureV0[tuple[NearbyPlaceV0, ...]](
        status=MeasureStatus.AVAILABLE, value=(p,), evidence=(_medida(),)
    )
    assert m.value[0].distance_m == 120.0


def test_el_trayecto_a_un_ancla_es_representable_sin_estar_calculado():
    """F1 no implementa `compute_travel_to_anchor`: el contrato solo tiene que poder
    guardar el resultado cuando exista y decir que todavía no existe."""
    sin_calcular = PlaceMeasureV0[TravelToAnchorV0](status=MeasureStatus.UNKNOWN)
    assert sin_calcular.value is None

    calculado = PlaceMeasureV0[TravelToAnchorV0](
        status=MeasureStatus.AVAILABLE,
        value=TravelToAnchorV0(
            anchor_id="a-1", anchor_label="la oficina",
            mode=TravelMode.TRANSIT, duration_minutes=28.0
        ),
        evidence=(_medida(methodology="matriz de tiempos de Valhalla"),),
    )
    assert calculado.value.duration_minutes == 28.0
    assert not hasattr(TravelToAnchorV0, "compute")


def test_el_mismo_ancla_no_aparece_dos_veces():
    def anclado(ident):
        return PlaceMeasureV0[TravelToAnchorV0](
            status=MeasureStatus.AVAILABLE,
            value=TravelToAnchorV0(anchor_id=ident),
            evidence=(_medida(),),
        )

    with pytest.raises(ValidationError, match="anchor_id repetido"):
        _lugar(travel_to_anchors=(anclado("a-1"), anclado("a-1")))


def test_la_isocrona_exige_un_poligono_cerrado():
    """Un contorno que no cierra no sirve para preguntar si un punto cae dentro."""
    assert IsochroneV0(mode=TravelMode.WALK, minutes=15, geometry_geojson=_POLIGONO)
    with pytest.raises(ValidationError, match="Polygon"):
        IsochroneV0(
            mode=TravelMode.WALK,
            minutes=15,
            geometry_geojson=json.dumps({"type": "LineString", "coordinates": []}),
        )
    with pytest.raises(ValidationError, match="no es JSON"):
        IsochroneV0(mode=TravelMode.WALK, minutes=15, geometry_geojson="a 15 minutos")


# ── frescura, límites, versionado ────────────────────────────────────────────────


def test_la_frescura_de_una_dimension_no_es_la_del_contexto():
    """Se puede ensamblar hoy un contexto con dimensiones observadas hace meses;
    confundir las dos fechas haría parecer fresco lo que no lo es."""
    vieja = AHORA - timedelta(days=200)
    lugar = _lugar(
        walkability=PlaceMeasureV0[float](
            status=MeasureStatus.AVAILABLE,
            value=82.0,
            observed_at=vieja,
            evidence=(_medida(),),
        )
    )
    assert lugar.assembled_at == AHORA
    assert lugar.walkability.observed_at == vieja


def test_no_saber_cuando_se_observo_no_se_sustituye_por_ahora():
    m = PlaceMeasureV0[float](
        status=MeasureStatus.AVAILABLE, value=82.0, evidence=(_medida(),)
    )
    assert m.observed_at is None


def test_los_instantes_llevan_zona_horaria():
    with pytest.raises(ValidationError, match="zona horaria"):
        _lugar(assembled_at=datetime(2026, 8, 25, 12, 0, 0))
    with pytest.raises(ValidationError, match="zona horaria"):
        PlaceMeasureV0[float](
            status=MeasureStatus.UNKNOWN, observed_at=datetime(2026, 8, 25)
        )


def test_el_contrato_lleva_su_version():
    assert _lugar().contract_version == CONTRACT_VERSION == "place-context-v0"


def test_una_version_futura_no_se_cuela():
    datos = _lugar().model_dump(mode="json")
    datos["contract_version"] = "place-context-v1"
    with pytest.raises(ValidationError):
        PlaceContextV0.model_validate(datos)


def test_serializa_y_vuelve_igual_con_todo_lleno():
    original = _lugar(
        place_id="quito:la-floresta:1",
        walkability=PlaceMeasureV0[float](
            status=MeasureStatus.AVAILABLE, value=82.0, evidence=(_medida(),)
        ),
        nearest_transit=PlaceMeasureV0[NearestTransitV0](
            status=MeasureStatus.AVAILABLE,
            value=NearestTransitV0(distance_m=180.0, mode="metro"),
            evidence=(_medida(),),
        ),
        nearby_places=PlaceMeasureV0[tuple[NearbyPlaceV0, ...]](
            status=MeasureStatus.AVAILABLE,
            value=(NearbyPlaceV0(category="parque", distance_m=314.0),),
            evidence=(_medida(),),
        ),
        travel_to_anchors=(
            PlaceMeasureV0[TravelToAnchorV0](status=MeasureStatus.UNKNOWN),
        ),
        isochrones=(
            PlaceMeasureV0[IsochroneV0](
                status=MeasureStatus.AVAILABLE,
                value=IsochroneV0(
                    mode=TravelMode.WALK, minutes=15, geometry_geojson=_POLIGONO
                ),
                evidence=(_medida(provider="valhalla"),),
            ),
        ),
        environment=(
            NamedMeasureV0(
                dimension="ruido",
                measure=PlaceMeasureV0[float](
                    status=MeasureStatus.INSUFFICIENT_EVIDENCE,
                    limitations=("no tenemos medición de ruido aquí",),
                ),
            ),
        ),
        limitations=("el bbox cubre solo Quito",),
    )
    assert PlaceContextV0.model_validate(original.model_dump(mode="json")) == original


def test_el_contexto_no_se_edita_despues_de_creado():
    lugar = _lugar()
    with pytest.raises(ValidationError):
        lugar.place_id = "otro"


def test_no_se_aceptan_campos_extra():
    with pytest.raises(ValidationError):
        _lugar(ruido=50)


def test_el_esquema_expone_los_tres_estados():
    enum_ = json_schema()["$defs"]["MeasureStatus"]["enum"]
    assert set(enum_) == {"available", "unknown", "insufficient_evidence"}


# ── la costura con el comprador: anchor_id, nunca el label ───────────────────────


def test_el_trayecto_exige_anchor_id():
    with pytest.raises(ValidationError, match="anchor_id"):
        TravelToAnchorV0(anchor_label="la oficina")


def test_el_label_no_sustituye_al_id():
    """Correlacionar por texto es cómo un trayecto queda huérfano en silencio porque
    alguien escribió "oficina" donde la persona había dicho "la oficina"."""
    t = TravelToAnchorV0(anchor_id="a-1")
    assert t.anchor_label is None
    assert t.anchor_id == "a-1"

    mismo_id_otro_texto = TravelToAnchorV0(anchor_id="a-1", anchor_label="oficina")
    assert mismo_id_otro_texto.anchor_id == t.anchor_id


def test_dos_anclas_con_el_mismo_texto_no_colisionan_si_el_id_difiere():
    def anclado(ident, etiqueta):
        return PlaceMeasureV0[TravelToAnchorV0](
            status=MeasureStatus.AVAILABLE,
            value=TravelToAnchorV0(anchor_id=ident, anchor_label=etiqueta),
            evidence=(_medida(),),
        )

    lugar = _lugar(travel_to_anchors=(anclado("a-1", "oficina"), anclado("a-2", "oficina")))
    assert len(lugar.travel_to_anchors) == 2


def test_el_lugar_no_importa_el_contrato_del_comprador():
    """No hay clave foránea ni dependencia Place → Buyer: un lugar existe sin que haya
    nadie buscándolo. `anchor_id` es un identificador opaco de correlación."""
    import ast

    import app.contracts.place_v0 as modulo

    arbol = ast.parse(pathlib.Path(modulo.__file__).read_text(encoding="utf-8"))
    importado = {
        n.module or ""
        for n in ast.walk(arbol)
        if isinstance(n, ast.ImportFrom)
    }
    assert not any("buyer" in m for m in importado), f"place importa del comprador: {importado}"
    assert not hasattr(modulo, "CommuteAnchorV0")


def test_un_place_context_base_es_valido_sin_comprador():
    """travel_to_anchors puede estar vacío."""
    lugar = _lugar()
    assert lugar.travel_to_anchors == ()


def test_la_referencia_sobrevive_al_ida_y_vuelta_por_json():
    lugar = _lugar(
        travel_to_anchors=(
            PlaceMeasureV0[TravelToAnchorV0](
                status=MeasureStatus.AVAILABLE,
                value=TravelToAnchorV0(
                    anchor_id="a-1", anchor_label="la oficina", duration_minutes=28.0
                ),
                evidence=(_medida(),),
            ),
        )
    )
    crudo = lugar.model_dump(mode="json")
    assert crudo["travel_to_anchors"][0]["value"]["anchor_id"] == "a-1"
    vuelta = PlaceContextV0.model_validate(crudo)
    assert vuelta.travel_to_anchors[0].value.anchor_id == "a-1"
