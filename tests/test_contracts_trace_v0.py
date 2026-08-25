"""E1.6 — DecisionTraceV0.

Una traza sirve para responder después "¿qué movió este resultado?". Estas pruebas
defienden las dos condiciones para que eso siga siendo cierto: que registre lo que
ENTRÓ y no todo lo disponible, y que no se convierta en un almacén de lo que ya vive en
otro sitio —ni de lo que nunca debe guardarse—.
"""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contracts.decision_v0 import BuyerContextRefV0
from app.contracts.trace_v0 import (
    CONTRACT_VERSION,
    CallStatus,
    DecisionTraceV0,
    DerivedFeatureV0,
    FactUsedV0,
    PolicyAppliedV0,
    ProviderCallV0,
    TraceRankingEntryV0,
    TraceUncertaintyV0,
    json_schema,
)

AHORA = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)


def _traza(**cambios):
    """Fixture MÍNIMO válido: una ejecución determinista que no consultó a nadie."""
    base = dict(
        trace_id="t-1",
        task_id="task-1",
        buyer_ref=BuyerContextRefV0(buyer_id="b-1", context_revision=2),
        inventory_snapshot_id=None,
        model_config_hash=None,
        final_output_hash="sha256:abc123",
        created_at=AHORA,
    )
    base.update(cambios)
    return DecisionTraceV0(**base)


def _traza_representativa():
    """Fixture con una llamada, un hecho, una feature, una política y un ranking."""
    return _traza(
        inventory_snapshot_id="inv-2026-08-25",
        model_config_hash="sha256:modelo",
        provider_calls=(
            ProviderCallV0(
                call_id="c-1",
                provider="valhalla",
                operation="isochrone",
                started_at=AHORA,
                status=CallStatus.OK,
                latency_ms=412,
                evidence_ids=("ev-1",),
            ),
        ),
        facts_used=(
            FactUsedV0(fact_path="property.transaction.price", evidence_ids=("ev-2",)),
            FactUsedV0(
                fact_path="buyer.hard_constraints[criterion_id=budget-max]",
                evidence_ids=("ev-3",),
            ),
        ),
        derived_features=(
            DerivedFeatureV0(
                name="minutos_a_oficina",
                value=28.0,
                methodology="matriz de tiempos de Valhalla, modo transit",
                evidence_ids=("ev-1",),
            ),
        ),
        policies_applied=(
            PolicyAppliedV0(
                policy_id="fair-housing", policy_version="2026-06", outcome="passed"
            ),
        ),
        uncertainties=(
            TraceUncertaintyV0(
                code="ruido_sin_medicion",
                description="no hay estación de medición cerca del punto",
            ),
        ),
        ranking=(
            TraceRankingEntryV0(
                provider_id="portal-x",
                property_id="4471",
                rank=1,
                score=0.82,
                score_version="encaje-v0",
            ),
        ),
    )


# ── fixtures y esquema ───────────────────────────────────────────────────────────


def test_el_fixture_minimo_es_valido():
    t = _traza()
    assert t.provider_calls == ()
    assert t.ranking == ()


def test_una_ejecucion_determinista_no_consulta_a_nadie():
    """`provider_calls` vacío es un estado normal, no una traza incompleta."""
    assert _traza().provider_calls == ()


def test_el_fixture_representativo_es_valido():
    t = _traza_representativa()
    assert len(t.provider_calls) == 1
    assert len(t.facts_used) == 2
    assert t.derived_features[0].name == "minutos_a_oficina"
    assert t.policies_applied[0].policy_id == "fair-housing"
    assert t.ranking[0].rank == 1


def test_el_json_schema_se_genera():
    esquema = json_schema()
    for campo in (
        "trace_id", "task_id", "buyer_ref", "inventory_snapshot_id",
        "model_config_hash", "provider_calls", "facts_used", "derived_features",
        "policies_applied", "uncertainties", "ranking", "final_output_hash",
        "created_at",
    ):
        assert campo in esquema["properties"], f"falta el campo {campo}"


def test_el_ida_y_vuelta_por_json_conserva_todo():
    original = _traza_representativa()
    crudo = original.model_dump(mode="json")
    assert DecisionTraceV0.model_validate(crudo) == original


def test_el_contrato_lleva_su_version_como_literal():
    assert _traza().contract_version == CONTRACT_VERSION == "decision-trace-v0"
    datos = _traza().model_dump(mode="json")
    datos["contract_version"] = "decision-trace-v1"
    with pytest.raises(ValidationError):
        DecisionTraceV0.model_validate(datos)


# ── ausencia declarada, no omitida ───────────────────────────────────────────────


def test_hay_que_declarar_que_no_hay_snapshot():
    """Un campo que desaparece en silencio es indistinguible de uno que nadie rellenó."""
    datos = _traza().model_dump(mode="json")
    del datos["inventory_snapshot_id"]
    with pytest.raises(ValidationError, match="inventory_snapshot_id"):
        DecisionTraceV0.model_validate(datos)


def test_hay_que_declarar_que_no_hay_model_config_hash():
    datos = _traza().model_dump(mode="json")
    del datos["model_config_hash"]
    with pytest.raises(ValidationError, match="model_config_hash"):
        DecisionTraceV0.model_validate(datos)


def test_los_dos_se_pueden_declarar_ausentes_explicitamente():
    t = _traza(inventory_snapshot_id=None, model_config_hash=None)
    assert t.inventory_snapshot_id is None
    assert t.model_config_hash is None
    crudo = t.model_dump(mode="json")
    assert crudo["inventory_snapshot_id"] is None
    assert crudo["model_config_hash"] is None


def test_la_politica_de_benchmark_no_esta_congelada_aqui():
    """Una traza sin snapshot y sin hash de modelo es válida en el contrato base. Exigir
    ambos para que valga como benchmark es F6."""
    assert _traza().final_output_hash


# ── V0 son ejecuciones completadas ───────────────────────────────────────────────


def test_final_output_hash_es_obligatorio():
    with pytest.raises(ValidationError):
        _traza(final_output_hash="")
    datos = _traza().model_dump(mode="json")
    del datos["final_output_hash"]
    with pytest.raises(ValidationError):
        DecisionTraceV0.model_validate(datos)


def test_no_hay_estados_de_ciclo_de_vida():
    """running/pending/failed/cancelled/partial sería infraestructura antes de
    necesitarla; si hace falta, es otra versión."""
    texto = json.dumps(json_schema()).lower()
    for prohibido in ('"running"', '"pending"', '"cancelled"', '"partial"'):
        assert prohibido not in texto
    assert "status" not in json_schema()["properties"]


# ── ids, tiempos, inmutabilidad ──────────────────────────────────────────────────


@pytest.mark.parametrize("campo", ["trace_id", "task_id", "final_output_hash"])
def test_los_identificadores_no_pueden_ir_vacios(campo):
    with pytest.raises(ValidationError):
        _traza(**{campo: ""})


def test_los_instantes_llevan_zona_horaria():
    with pytest.raises(ValidationError, match="zona horaria"):
        _traza(created_at=datetime(2026, 8, 25, 12, 0, 0))
    with pytest.raises(ValidationError, match="zona horaria"):
        ProviderCallV0(
            call_id="c-1", provider="x", operation="y",
            started_at=datetime(2026, 8, 25), status=CallStatus.OK,
        )


def test_created_at_no_sustituye_la_fecha_de_la_evidencia():
    """Una traza creada hoy puede haber usado evidencia de hace meses."""
    props = set(json_schema()["properties"])
    assert "observed_at" not in props
    assert _traza().created_at == AHORA


def test_la_traza_no_se_edita_despues_de_creada():
    t = _traza()
    with pytest.raises(ValidationError):
        t.final_output_hash = "otro"


def test_las_colecciones_son_inmutables():
    t = _traza_representativa()
    assert isinstance(t.facts_used, tuple)
    with pytest.raises(AttributeError):
        t.facts_used.append(FactUsedV0(fact_path="colado"))


def test_no_se_aceptan_campos_extra():
    with pytest.raises(ValidationError):
        _traza(prompt="el prompt completo")


# ── solo IDs de evidencia, nunca objetos ─────────────────────────────────────────


def test_no_hay_evidence_ref_embebidos():
    """Se comprueba sobre la ESTRUCTURA del esquema, no sobre su texto."""
    embebidos = set(json_schema().get("$defs", {}))
    assert "EvidenceRefV0" not in embebidos
    for modelo in ("ProviderCallV0", "FactUsedV0", "DerivedFeatureV0", "TraceUncertaintyV0"):
        items = json_schema()["$defs"][modelo]["properties"]["evidence_ids"]["items"]
        assert items["type"] == "string", f"{modelo} embebe objetos, no ids"


def test_no_hay_contextos_embebidos():
    embebidos = set(json_schema().get("$defs", {}))
    for entero in ("BuyerContextV0", "PropertyContextV0", "PlaceContextV0"):
        assert entero not in embebidos
    assert "BuyerContextRefV0" in embebidos


def test_el_comprador_va_por_referencia_y_no_degradado_a_un_string():
    t = _traza()
    assert isinstance(t.buyer_ref, BuyerContextRefV0)
    assert t.buyer_ref.context_revision == 2


def test_los_evidence_ids_sobreviven_la_serializacion():
    original = _traza_representativa()
    crudo = original.model_dump(mode="json")
    assert crudo["provider_calls"][0]["evidence_ids"] == ["ev-1"]
    assert crudo["facts_used"][0]["evidence_ids"] == ["ev-2"]
    assert crudo["derived_features"][0]["evidence_ids"] == ["ev-1"]
    vuelta = DecisionTraceV0.model_validate(crudo)
    assert vuelta.facts_used[1].evidence_ids == ("ev-3",)


def test_un_evidence_id_vacio_o_repetido_no_referencia_nada():
    with pytest.raises(ValidationError, match="no referencia ninguna evidencia"):
        FactUsedV0(fact_path="x", evidence_ids=("  ",))
    with pytest.raises(ValidationError, match="evidence_id repetido"):
        FactUsedV0(fact_path="x", evidence_ids=("ev-1", "ev-1"))


def test_aqui_la_evidencia_puede_faltar_a_diferencia_de_la_decision():
    """La traza registra lo que pasó, huecos incluidos: una llamada que falló no produce
    evidencia. Exigirla obligaría a inventarse ids para que el objeto validara, y la
    traza dejaría de ser un registro fiel."""
    fallida = ProviderCallV0(
        call_id="c-1", provider="overpass", operation="nearby",
        started_at=AHORA, status=CallStatus.TIMEOUT,
    )
    assert fallida.evidence_ids == ()
    assert FactUsedV0(fact_path="property.attributes[key=bedrooms]").evidence_ids == ()


# ── llamadas a proveedores: nada sensible ────────────────────────────────────────


def test_no_se_guarda_nada_sensible_ni_payloads():
    campos = set(ProviderCallV0.model_fields)
    for prohibido in (
        "api_key", "key", "token", "headers", "payload", "request", "response",
        "body", "url", "signed_url", "raw",
    ):
        assert prohibido not in campos, f"ProviderCallV0 guardaría {prohibido}"


def test_la_llamada_es_provider_neutral():
    """Vocabulario abierto: un proveedor nuevo no obliga a tocar el contrato."""
    antes = json_schema()
    ProviderCallV0(
        call_id="c-9", provider="proveedor_inexistente_2027",
        operation="lo_que_sea", started_at=AHORA, status=CallStatus.OK,
    )
    assert json_schema() == antes
    assert "enum" not in str(json_schema()["$defs"]["ProviderCallV0"]["properties"]["provider"])


def test_el_estado_de_la_llamada_es_el_nuestro_y_no_el_del_proveedor():
    assert {s.value for s in CallStatus} == {"ok", "error", "timeout"}


def test_dos_llamadas_no_comparten_call_id():
    def llamada(ident):
        return ProviderCallV0(
            call_id=ident, provider="x", operation="y",
            started_at=AHORA, status=CallStatus.OK,
        )

    with pytest.raises(ValidationError, match="call_id repetido"):
        _traza(provider_calls=(llamada("c-1"), llamada("c-1")))


# ── hechos y features derivadas ──────────────────────────────────────────────────


def test_el_hecho_se_referencia_por_ruta_semantica_y_no_por_indice():
    """`[criterion_id=budget-max]` sigue apuntando a lo mismo cuando el array se
    reordena; `[0]` no. Misma lección que hizo nacer criterion_id y anchor_id."""
    f = FactUsedV0(fact_path="buyer.hard_constraints[criterion_id=budget-max]")
    assert "criterion_id=" in f.fact_path


def test_una_feature_derivada_sin_metodologia_no_existe():
    """Recrearía exactamente el problema que cerró FASE 0: un número que nadie puede
    reproducir ni discutir."""
    with pytest.raises(ValidationError):
        DerivedFeatureV0(name="x", value=1.0, methodology="")
    with pytest.raises(ValidationError):
        DerivedFeatureV0(name="x", value=1.0)


def test_el_valor_derivado_es_serializable_a_json():
    for valor in (True, 3, 2.5, "alto", ("a", "b"), None):
        f = DerivedFeatureV0(name="x", value=valor, methodology="m")
        json.dumps(f.model_dump(mode="json"))


# ── políticas ────────────────────────────────────────────────────────────────────


def test_el_resultado_de_una_politica_queda_abierto_en_v0():
    """Inventar ahora un enum de resultados congelaría una taxonomía de políticas que
    todavía no existe."""
    assert "enum" not in str(json_schema()["$defs"]["PolicyAppliedV0"]["properties"]["outcome"])
    assert PolicyAppliedV0(policy_id="p", outcome="lo_que_haga_falta").outcome


def test_una_politica_puede_no_estar_versionada():
    assert PolicyAppliedV0(policy_id="p", outcome="passed").policy_version is None


# ── ranking ──────────────────────────────────────────────────────────────────────


def test_el_ranking_conserva_la_identidad_estable():
    e = TraceRankingEntryV0(provider_id="portal-x", property_id="4471", rank=1)
    assert e.identidad_externa == ("portal-x", "4471")


def test_la_posicion_empieza_en_uno():
    with pytest.raises(ValidationError):
        TraceRankingEntryV0(provider_id="p", property_id="1", rank=0)


def test_un_score_sin_su_version_no_es_comparable():
    with pytest.raises(ValidationError, match="score_version"):
        TraceRankingEntryV0(provider_id="p", property_id="1", rank=1, score=0.8)


def test_un_ranking_sin_numeros_es_valido():
    e = TraceRankingEntryV0(provider_id="p", property_id="1", rank=1)
    assert e.score is None and e.score_version is None


def test_los_empates_son_legitimos_pero_el_mismo_inmueble_dos_veces_no():
    empate = (
        TraceRankingEntryV0(provider_id="p", property_id="1", rank=1),
        TraceRankingEntryV0(provider_id="p", property_id="2", rank=1),
    )
    assert _traza(ranking=empate)

    with pytest.raises(ValidationError, match="repetido en el ranking"):
        _traza(
            ranking=(
                TraceRankingEntryV0(provider_id="p", property_id="1", rank=1),
                TraceRankingEntryV0(provider_id="p", property_id="1", rank=2),
            )
        )


def test_el_ranking_no_trae_la_explicacion_de_cada_inmueble():
    """Eso es DecisionContextV0."""
    campos = set(TraceRankingEntryV0.model_fields)
    assert campos == {"provider_id", "property_id", "rank", "score", "score_version"}


# ── lo que no se construye en F1 ─────────────────────────────────────────────────


def test_no_hay_persistencia_ni_instrumentacion_ni_assembler():
    import app.contracts.trace_v0 as modulo

    for prohibido in (
        "save", "store", "persist", "capture", "instrument", "emit",
        "assemble", "run", "benchmark",
    ):
        assert not hasattr(DecisionTraceV0, prohibido)
        assert not hasattr(modulo, prohibido)
