"""FASE 1 — ¿pueden los contratos representar la realidad que YA existe en el repo?

Hasta aquí, los seis contratos estaban probados contra ejemplos escritos a mano. Estas
pruebas los enfrentan a las **formas reales** del repositorio: las columnas de
`ActivoInmutable` y `TransaccionTemporal`, lo que devuelve `calcular_encaje()`, lo que
devuelve `walk_score`, y lo que hay (y lo que no) para trazar una ejecución.

**No son adaptadores.** No viven en `app/`, no se reutilizan y nadie los importa: son
fixtures de compatibilidad. Los adaptadores de producción son F5 (inventario), F4
(lugar) y F2 (decisión).

LA REGLA QUE GOBIERNA ESTE ARCHIVO: cuando una capacidad actual **no puede** poblar un
campo, se usa `None` / `unknown` / `insufficient_evidence` / `limitations`. **No se
inventa dato.** Que estas pruebas pasen sin inventar nada es lo que demuestra que los
contratos describen el mundo real y no uno imaginado.
"""

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.contracts.common_v0 import Money, Objective, RankingEntryV0
from app.contracts.buyer_v0 import (
    BuyerContextV0,
    CommuteAnchorV0,
    CriterionOrigin,
    DecisionCriterionV0,
    FieldEvidence,
    Financial,
    Mobility,
    Operator,
    PropertyRequirements,
)
from app.contracts.decision_v0 import (
    BuyerContextRefV0,
    DecisionContextV0,
    ExplanationV0,
    MatchDimensionV0,
    MatchV0,
    PlaceContextRefV0,
    PropertyContextRefV0,
    StrengthV0,
    UncertaintyV0,
)
from app.contracts.evidence_v0 import (
    EvidenceRefV0,
    PersistencePolicy,
    SourceType,
)
from app.contracts.place_v0 import (
    GeoPoint,
    MeasureStatus,
    NamedMeasureV0,
    NearbyPlaceV0,
    PlaceContextV0,
    PlaceMeasureV0,
)
from app.contracts.property_v0 import (
    PROVIDER_TYPE_CONTEXTO,
    Availability,
    InventoryClass,
    Location,
    Media,
    Operation,
    PropertyAttribute,
    PropertyContextV0,
    PropertyProvenanceV0,
    Quality,
    Transaction,
)
from app.contracts.trace_v0 import (
    CallStatus,
    DecisionTraceV0,
    DerivedFeatureV0,
    FactUsedV0,
    PolicyAppliedV0,
    ProviderCallV0,
    TraceUncertaintyV0,
)

AHORA = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────────
# Formas REALES del repositorio, copiadas de su definición
# ─────────────────────────────────────────────────────────────────────────────────

ACTIVO_INMUTABLE = {
    # app/models.py::ActivoInmutable — columnas tal cual
    "id": uuid.UUID("11111111-2222-3333-4444-555555555555"),
    "geom": (-78.4867, -0.1807),          # Geometry(POINT, 4326) → (lon, lat)
    "direccion_estandarizada": "Av. Coruña y San Ignacio, La Floresta, Quito",
    "piso_altura": 3,
    "walk_score": 82,
    "walk_score_fuente": "osm",
    "score_ruido_predictivo": "medio",    # String(10) — heurística, sin fuente medida
    "volumen_trafico_historico": 0,
    "densidad_poblacional_pico": 0,
    "caracteristicas": {                  # JSONB, 25 llaves observadas, sin tipar
        "dormitorios": 2,
        "area_m2": 90,
        "amoblado": True,
        "precio": 200,                    # ← contradice la transacción. Doc 03, activo REAL
        "fotos": ["https://cdn.example/1.jpg"],
    },
    "imagen_url": "https://cdn.example/portada.jpg",
    "created_at": datetime(2026, 7, 1, 9, 30, tzinfo=timezone.utc),
}

TRANSACCION_TEMPORAL = {
    # app/models.py::TransaccionTemporal
    "id": uuid.UUID("66666666-7777-8888-9999-000000000000"),
    "activo_id": ACTIVO_INMUTABLE["id"],
    "tipo_operacion": "arriendo",
    "precio": 180.00,                     # ← el precio bueno
    "estado_anuncio": "disponible",
    "fecha_publicacion": datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
    "fecha_cierre": None,
}

ENCAJE = {
    # app/encaje.py::calcular_encaje — forma de retorno real
    "score": 78,
    "cobertura": 0.6,
    "score_version": "encaje-v0",
    "razones": [
        {"dimension": "presupuesto", "cumple": True, "s": 1.0},
        {"dimension": "dormitorios", "cumple": True, "s": 1.0},
        {"dimension": "tranquilidad", "cumple": None, "s": None,
         "estado": "insufficient_evidence"},   # E0.4 dejó este estado visible
    ],
}

WALK_SCORE = {"score": 82, "fuente": "osm"}   # app/walk_score.py

_MAPEO_OPERACION = {"venta": Operation.SALE, "arriendo": Operation.RENT}
_MAPEO_DISPONIBILIDAD = {
    "disponible": Availability.AVAILABLE,
    "reservado": Availability.RESERVED,
    "vendido": Availability.SOLD,
    "arrendado": Availability.SOLD,
}
_LLAVES_QUE_NO_SON_ATRIBUTOS = {"precio", "fotos"}


# ─────────────────────────────────────────────────────────────────────────────────
# E1.1 — EvidenceRefV0 desde la procedencia REAL que existe hoy
# ─────────────────────────────────────────────────────────────────────────────────


def _evidencia_de_caminabilidad(fuente: str | None) -> EvidenceRefV0:
    """`walk_score_fuente` es la columna que E0.3 destapó: el motor decía
    "OpenStreetMap" sobre valores que no siempre venían de ahí."""
    if fuente == "osm":
        return EvidenceRefV0(
            evidence_id="ev-walk-osm",
            source_type=SourceType.PUBLIC_DATASET,
            provider="osm",
            observed_at=None,     # OSM no dice de cuándo es el dato del punto
            retrieved_at=AHORA,
            methodology="walk_score sobre red peatonal OSM (app/walk_score.py)",
            persistence_policy=PersistencePolicy.PERSISTABLE,
        )
    return EvidenceRefV0(
        evidence_id="ev-walk-heuristico",
        source_type=SourceType.HEURISTIC_ESTIMATE,
        observed_at=None,
        retrieved_at=AHORA,
        methodology="estimación por zona; no hay red peatonal mapeada",
        persistence_policy=PersistencePolicy.PERSISTABLE,
        limitations=("no es una medición sobre red; no comparable con un score OSM",),
    )


def test_la_procedencia_real_de_la_caminabilidad_entra_sin_mentir():
    """Las dos ramas de `walk_score_fuente` producen evidencias DISTINGUIBLES. Eso es
    E0.3 cerrado en el contrato: ya no hay forma de que la estimada se presente como
    medida."""
    medida = _evidencia_de_caminabilidad("osm")
    estimada = _evidencia_de_caminabilidad("heuristico")

    assert medida.es_medicion is True
    assert estimada.es_medicion is False
    assert estimada.limitations, "una heurística sin límites declarados no se construye"


def test_una_fuente_desconocida_no_se_convierte_en_medicion():
    """`walk_score_fuente` es nullable. `None` cae en la rama heurística, que declara sus
    límites — no en la rama OSM."""
    assert _evidencia_de_caminabilidad(None).es_medicion is False


# ─────────────────────────────────────────────────────────────────────────────────
# E1.3 — PropertyContextV0 desde ActivoInmutable + TransaccionTemporal
# ─────────────────────────────────────────────────────────────────────────────────


def _inmueble_desde_el_repo() -> PropertyContextV0:
    a, t = ACTIVO_INMUTABLE, TRANSACCION_TEMPORAL
    lon, lat = a["geom"]

    atributos = tuple(
        PropertyAttribute(key=k, value=v)
        for k, v in a["caracteristicas"].items()
        if k not in _LLAVES_QUE_NO_SON_ATRIBUTOS
    ) + (PropertyAttribute(key="piso_altura", value=a["piso_altura"]),)

    return PropertyContextV0(
        # No hay columnas de proveedor en el repo (doc 03: cero apariciones). El
        # inventario propio es su propio proveedor.
        property_id=str(a["id"]),
        provider_id="contexto",
        provider_type=PROVIDER_TYPE_CONTEXTO,
        provider_listing_url=None,
        location=Location(lat=lat, lon=lon, address=a["direccion_estandarizada"]),
        attributes=atributos,
        transaction=Transaction(
            operation=_MAPEO_OPERACION[t["tipo_operacion"]],
            price=Money(amount=Decimal(str(t["precio"])), currency="USD"),
            availability=_MAPEO_DISPONIBILIDAD[t["estado_anuncio"]],
            listed_at=t["fecha_publicacion"],
            closed_at=t["fecha_cierre"],
        ),
        media=Media(images=(a["imagen_url"], *a["caracteristicas"]["fotos"])),
        provenance=PropertyProvenanceV0(
            # No existe `received_at` en el modelo: solo `created_at`. Y el proveedor no
            # declara cuándo actualizó, así que `None` — no se sustituye por received_at.
            received_at=a["created_at"],
            last_updated_at=None,
            inventory_class=InventoryClass.UNKNOWN,
        ),
        quality=Quality(
            completeness=None,   # nadie la calcula hoy: None, no 0.0
            warnings=(
                "el JSONB traía un `precio` que contradecía el de la transacción; "
                "se descartó y el precio se tomó de transaction",
            ),
        ),
    )


def test_un_activo_real_del_repo_entra_completo():
    p = _inmueble_desde_el_repo()
    assert p.location.esta_georreferenciada is True
    assert p.transaction.operation is Operation.RENT
    assert p.transaction.availability is Availability.AVAILABLE
    assert p.identidad_externa == ("contexto", str(ACTIVO_INMUTABLE["id"]))


def test_el_precio_contradictorio_del_jsonb_no_llega_al_contrato():
    """El caso REAL del doc 03: $200 en `caracteristicas`, $180 en la transacción. El
    contrato solo admite uno, y el atributo ni siquiera se puede construir."""
    from pydantic import ValidationError

    p = _inmueble_desde_el_repo()
    assert p.transaction.price.amount == Decimal("180.0")
    assert "precio" not in {a.key for a in p.attributes}

    with pytest.raises(ValidationError, match="transaction.price"):
        PropertyAttribute(key="precio", value=ACTIVO_INMUTABLE["caracteristicas"]["precio"])


def test_un_registro_del_que_no_se_sabe_el_origen_se_declara_unknown():
    """El inventario actual no tiene forma de decir si una ficha es real o hidratada.
    `unknown` es la respuesta honesta; convertirlo en `live` sería inventar."""
    assert _inmueble_desde_el_repo().provenance.inventory_class is InventoryClass.UNKNOWN


def test_lo_que_el_repo_no_tiene_se_declara_ausente_y_no_se_inventa():
    p = _inmueble_desde_el_repo()
    assert p.provider_listing_url is None      # no existe la columna
    assert p.provenance.last_updated_at is None  # el proveedor no lo declara
    assert p.quality.completeness is None        # nadie la calcula


def test_el_inmueble_real_sobrevive_el_ida_y_vuelta():
    p = _inmueble_desde_el_repo()
    assert PropertyContextV0.model_validate(p.model_dump(mode="json")) == p


# ─────────────────────────────────────────────────────────────────────────────────
# E1.4 — PlaceContextV0 desde walk_score, POIs y las heurísticas de E0.4
# ─────────────────────────────────────────────────────────────────────────────────


def _lugar_desde_el_repo() -> PlaceContextV0:
    a = ACTIVO_INMUTABLE
    lon, lat = a["geom"]
    ev_walk = _evidencia_de_caminabilidad(WALK_SCORE["fuente"])

    return PlaceContextV0(
        place_id=f"quito:{a['id']}",
        location=GeoPoint(lat=lat, lon=lon),
        assembled_at=AHORA,
        walkability=PlaceMeasureV0[float](
            status=MeasureStatus.AVAILABLE,
            value=float(WALK_SCORE["score"]),
            evidence=(ev_walk,),
        ),
        nearby_places=PlaceMeasureV0[tuple[NearbyPlaceV0, ...]](
            status=MeasureStatus.AVAILABLE,
            value=(
                NearbyPlaceV0(category="parque", distance_m=314.0),
                NearbyPlaceV0(category="supermercado", distance_m=139.0),
                NearbyPlaceV0(category="transporte", distance_m=86.0),
            ),
            evidence=(
                EvidenceRefV0(
                    evidence_id="ev-pois",
                    source_type=SourceType.OWN_MEASUREMENT,
                    observed_at=AHORA,
                    retrieved_at=AHORA,
                    methodology="POI más cercano por categoría sobre pois_propios",
                    persistence_policy=PersistencePolicy.PERSISTABLE,
                ),
            ),
        ),
        environment=(
            # `score_ruido_predictivo` EXISTE en el modelo como String(10) con valores
            # tipo "medio". E0.4 lo sacó del ranking por no tener fuente medida. Aquí la
            # dimensión está presente, explicada, y SIN valor.
            NamedMeasureV0(
                dimension="ruido",
                measure=PlaceMeasureV0[float](
                    status=MeasureStatus.INSUFFICIENT_EVIDENCE,
                    limitations=(
                        "score_ruido_predictivo es una heurística sin medición; "
                        "E0.4 lo retiró del scoring",
                    ),
                ),
            ),
            NamedMeasureV0(
                dimension="trafico",
                measure=PlaceMeasureV0[float](
                    status=MeasureStatus.INSUFFICIENT_EVIDENCE,
                    limitations=("volumen_trafico_historico está en 0 para todo el inventario",),
                ),
            ),
        ),
    )


def test_la_caminabilidad_real_entra_con_su_procedencia():
    lugar = _lugar_desde_el_repo()
    assert lugar.walkability.value == 82.0
    assert lugar.walkability.evidence[0].es_medicion is True


def test_la_heuristica_de_ruido_del_repo_no_puede_traer_valor():
    """`score_ruido_predictivo` existe en la tabla. El contrato lo deja entrar como
    dimensión explicada, pero no hay dónde poner el número."""
    ruido = next(d for d in _lugar_desde_el_repo().environment if d.dimension == "ruido")
    assert ruido.measure.status is MeasureStatus.INSUFFICIENT_EVIDENCE
    assert ruido.measure.value is None
    assert ruido.measure.limitations


def test_intentar_meter_el_ruido_como_valor_no_compila():
    """La prueba de que E0.4 no puede volver: ni siquiera se construye el objeto."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        NamedMeasureV0(
            dimension="ruido",
            measure=PlaceMeasureV0[float](status=MeasureStatus.AVAILABLE, value=50.0),
        )


def test_las_dimensiones_que_el_repo_no_calcula_estan_ausentes():
    """Ausente ≠ presente sin valor. Nadie calcula isócronas por inmueble en el flujo
    actual, así que no aparecen."""
    lugar = _lugar_desde_el_repo()
    assert lugar.isochrones == ()
    assert lugar.travel_to_anchors == ()
    assert lugar.nearest_transit is None


def test_el_lugar_real_sobrevive_el_ida_y_vuelta():
    lugar = _lugar_desde_el_repo()
    assert PlaceContextV0.model_validate(lugar.model_dump(mode="json")) == lugar


# ─────────────────────────────────────────────────────────────────────────────────
# E1.2 — BuyerContextV0 desde la forma de preferencias que ya circula
# ─────────────────────────────────────────────────────────────────────────────────


PREFERENCIAS = {
    # Forma que hoy vive en AgentState.preferencias (doc 03: sin tabla, en el checkpoint)
    "operacion": "arriendo",
    "presupuesto_max": 900,
    "dormitorios_min": 2,
    "zonas": ["La Floresta", "Cumbayá"],
}


def _comprador_desde_el_repo() -> BuyerContextV0:
    ev = EvidenceRefV0(
        evidence_id="ev-dijo",
        source_type=SourceType.USER_DECLARED,
        observed_at=AHORA,
        retrieved_at=AHORA,
        methodology="extraído de la conversación (app/preferencias.py)",
        persistence_policy=PersistencePolicy.PERSISTABLE,
    )
    return BuyerContextV0(
        buyer_id="b-real-1",
        objective=Objective.RENT,
        financial=Financial(
            budget_max=Money(amount=Decimal(str(PREFERENCIAS["presupuesto_max"])), currency="USD")
        ),
        property_requirements=PropertyRequirements(
            bedrooms_min=PREFERENCIAS["dormitorios_min"]
        ),
        hard_constraints=(
            DecisionCriterionV0(
                criterion_id="c-presupuesto",
                dimension="price",
                operator=Operator.LTE,
                value=PREFERENCIAS["presupuesto_max"],
                unit="USD",
                origin=CriterionOrigin.STATED,
                evidence=(ev,),
            ),
            DecisionCriterionV0(
                criterion_id="c-zonas",
                dimension="barrio",
                operator=Operator.IN,
                value=tuple(PREFERENCIAS["zonas"]),
                origin=CriterionOrigin.STATED,
                evidence=(ev,),
            ),
        ),
        # `preferencias` no tiene ningún concepto de etapa de decisión; se deja `None`
        # en vez de mapearlo desde intencion.py, que es el otro eje.
        stage=None,
        field_evidence=(FieldEvidence(field="financial.budget_max", evidence=ev),),
        updated_at=AHORA,
    )


def test_las_preferencias_reales_se_vuelven_criterios_evaluables():
    """Lo que hoy es un dict plano se convierte en criterios con operador y procedencia,
    sin reparsear prosa."""
    b = _comprador_desde_el_repo()
    presupuesto = next(c for c in b.hard_constraints if c.criterion_id == "c-presupuesto")
    assert (presupuesto.operator, presupuesto.value, presupuesto.unit) == (
        Operator.LTE, 900, "USD",
    )


def test_el_repo_no_tiene_etapa_de_decision_y_no_se_finge():
    """`intencion.py` mide calor comercial, que es el otro eje. Mapearlo a `stage` sería
    exactamente la confusión que E1.2 congeló."""
    assert _comprador_desde_el_repo().stage is None


def test_ninguna_preferencia_real_trae_household():
    b = _comprador_desde_el_repo()
    assert "household" not in b.model_dump()


# ─────────────────────────────────────────────────────────────────────────────────
# E1.5 — DecisionContextV0 desde lo que devuelve calcular_encaje()
# ─────────────────────────────────────────────────────────────────────────────────


def _decision_desde_el_repo() -> DecisionContextV0:
    razones_con_evidencia = [r for r in ENCAJE["razones"] if r.get("cumple") is True]
    sin_evidencia = [r for r in ENCAJE["razones"] if r.get("estado") == "insufficient_evidence"]

    return DecisionContextV0(
        decision_id="d-real-1",
        created_at=AHORA,
        objective=Objective.RENT,
        buyer=BuyerContextRefV0(buyer_id="b-real-1", context_revision=None),
        property=PropertyContextRefV0(
            provider_id="contexto", property_id=str(ACTIVO_INMUTABLE["id"])
        ),
        place=PlaceContextRefV0(place_id=f"quito:{ACTIVO_INMUTABLE['id']}"),
        score_version=ENCAJE["score_version"],
        match=MatchV0(
            dimensions=tuple(
                MatchDimensionV0(dimension=r["dimension"], evidence_refs=("ev-dijo",))
                for r in razones_con_evidencia
            )
        ),
        strengths=(
            StrengthV0(dimension="parque", evidence_refs=("ev-pois",)),
        ),
        uncertainties=tuple(
            # Las razones en `insufficient_evidence` de E0.4 se vuelven incertidumbres,
            # y aquí sí pueden ir sin evidencia: el problema ES que no la hay.
            UncertaintyV0(statement=f"sin medición para {r['dimension']}")
            for r in sin_evidencia
        ),
        ranking=(
            RankingEntryV0(
                provider_id="contexto",
                property_id=str(ACTIVO_INMUTABLE["id"]),
                rank=1,
                score=float(ENCAJE["score"]),
                score_version=ENCAJE["score_version"],
            ),
        ),
        recommended_next_action=None,   # el flujo actual no emite una acción tipada
        explanation=ExplanationV0(verification_status="verificada"),
        trace_id=None,                  # hoy no se traza; se declara, no se omite
    )


def test_el_encaje_real_se_representa_con_su_score_version():
    d = _decision_desde_el_repo()
    assert d.score_version == "encaje-v0"
    assert d.ranking[0].score == 78.0
    assert d.ranking[0].identidad_externa == ("contexto", str(ACTIVO_INMUTABLE["id"]))


def test_las_razones_sin_evidencia_de_e0_4_se_vuelven_incertidumbres():
    """La dimensión que `calcular_encaje` marca `insufficient_evidence` no se convierte
    en una fortaleza ni desaparece: se declara como lo que es."""
    d = _decision_desde_el_repo()
    assert any("tranquilidad" in u.statement for u in d.uncertainties)
    assert all(u.evidence_refs == () for u in d.uncertainties)


def test_lo_que_el_flujo_actual_no_produce_se_declara_ausente():
    d = _decision_desde_el_repo()
    assert d.recommended_next_action is None
    assert d.trace_id is None
    assert d.buyer.context_revision is None   # no hay store con historial (F3)


def test_la_decision_real_sobrevive_el_ida_y_vuelta():
    d = _decision_desde_el_repo()
    assert DecisionContextV0.model_validate(d.model_dump(mode="json")) == d


# ─────────────────────────────────────────────────────────────────────────────────
# E1.6 — DecisionTraceV0 con lo que hoy se puede saber de una ejecución
# ─────────────────────────────────────────────────────────────────────────────────


def _traza_desde_el_repo() -> DecisionTraceV0:
    """Lo honesto: hoy no hay instrumentación. Lo único observable de una ejecución es
    lo que el propio flujo produce. Los campos que exigirían capturar algo que nadie
    captura se declaran ausentes."""
    return DecisionTraceV0(
        trace_id="t-real-1",
        task_id="conversacion-42",       # el thread del checkpoint de LangGraph
        buyer_ref=BuyerContextRefV0(buyer_id="b-real-1", context_revision=None),
        inventory_snapshot_id=None,      # no existe el concepto de snapshot (F6)
        model_config_hash=None,          # nadie hashea la config del modelo hoy
        provider_calls=(
            ProviderCallV0(
                call_id="c-walk",
                provider="osm",
                operation="walk_score",
                started_at=AHORA,
                status=CallStatus.OK,
                latency_ms=None,          # no se mide latencia hoy
                evidence_ids=("ev-walk-osm",),
            ),
        ),
        facts_used=(
            FactUsedV0(fact_path="property.transaction.price", evidence_ids=()),
            FactUsedV0(fact_path="place.walkability.value", evidence_ids=("ev-walk-osm",)),
            FactUsedV0(
                fact_path="buyer.hard_constraints[criterion_id=c-presupuesto]",
                evidence_ids=("ev-dijo",),
            ),
        ),
        derived_features=(
            DerivedFeatureV0(
                name="encaje_score",
                value=float(ENCAJE["score"]),
                methodology="calcular_encaje() v encaje-v0 (app/encaje.py)",
                evidence_ids=("ev-walk-osm", "ev-pois"),
            ),
        ),
        policies_applied=(
            PolicyAppliedV0(policy_id="fair-housing", policy_version=None, outcome="aplicada"),
        ),
        uncertainties=(
            TraceUncertaintyV0(
                code="ruido_sin_medicion",
                description="score_ruido_predictivo es heurística; E0.4 lo retiró del scoring",
            ),
        ),
        ranking=(
            RankingEntryV0(
                provider_id="contexto",
                property_id=str(ACTIVO_INMUTABLE["id"]),
                rank=1,
                score=float(ENCAJE["score"]),
                score_version=ENCAJE["score_version"],
            ),
        ),
        final_output_hash="sha256:" + "0" * 8,
        created_at=AHORA,
    )


def test_una_traza_con_lo_que_hoy_se_puede_saber_es_valida():
    t = _traza_desde_el_repo()
    assert t.facts_used[0].fact_path == "property.transaction.price"
    assert t.derived_features[0].methodology.startswith("calcular_encaje()")


def test_lo_que_nadie_captura_hoy_se_declara_ausente_no_se_finge():
    """`inventory_snapshot_id` y `model_config_hash` no existen como capacidad. El
    contrato obliga a decirlo en vez de dejar que desaparezcan."""
    t = _traza_desde_el_repo()
    assert t.inventory_snapshot_id is None
    assert t.model_config_hash is None
    assert t.provider_calls[0].latency_ms is None


def test_un_hecho_sin_procedencia_anotada_entra_igual():
    """El precio del inmueble no tiene `EvidenceRefV0` en el inventario actual. La traza
    lo registra con `evidence_ids` vacío en vez de inventarse un id."""
    t = _traza_desde_el_repo()
    precio = next(f for f in t.facts_used if f.fact_path.endswith("price"))
    assert precio.evidence_ids == ()


def test_la_traza_real_sobrevive_el_ida_y_vuelta():
    t = _traza_desde_el_repo()
    assert DecisionTraceV0.model_validate(t.model_dump(mode="json")) == t


# ─────────────────────────────────────────────────────────────────────────────────
# La comprobación que resume el archivo
# ─────────────────────────────────────────────────────────────────────────────────


def test_los_seis_contratos_representan_el_repo_actual_sin_inventar_dato():
    """El resumen: los seis se construyen desde formas reales, todo serializa, y cada
    hueco del sistema actual queda declarado como hueco."""
    objetos = [
        _evidencia_de_caminabilidad("osm"),
        _comprador_desde_el_repo(),
        _inmueble_desde_el_repo(),
        _lugar_desde_el_repo(),
        _decision_desde_el_repo(),
        _traza_desde_el_repo(),
    ]
    for o in objetos:
        json.dumps(o.model_dump(mode="json"))   # todo serializa

    ausencias_declaradas = [
        _inmueble_desde_el_repo().provenance.inventory_class.value,
        _inmueble_desde_el_repo().quality.completeness,
        _comprador_desde_el_repo().stage,
        _decision_desde_el_repo().trace_id,
        _traza_desde_el_repo().inventory_snapshot_id,
    ]
    assert ausencias_declaradas == ["unknown", None, None, None, None]


def test_estos_fixtures_no_son_adaptadores():
    """Viven en tests/, nadie en app/ los importa, y no se exponen como utilidades."""
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parent.parent
    for py in (raiz / "app").rglob("*.py"):
        assert "test_contracts_compatibilidad_repo" not in py.read_text(encoding="utf-8")
