"""E1.1 — EvidenceRefV0, la primitiva compartida de evidencia.

Lo que se prueba aquí no es que Pydantic valide (eso ya lo prueba Pydantic). Es que
**las tres reglas del contrato no se puedan violar**, porque son las que en FASE 0
costaron dos defectos:

  · no se inventa procedencia (E0.3: la caminabilidad decía "OpenStreetMap" sin medirlo)
  · lo no medido declara sus límites (E0.4: ruido y vegetación puntuaban sin fuente)
  · ningún proveedor es estructura del contrato

Si alguna de estas pruebas empieza a estorbar, la conversación es sobre la regla, no
sobre la prueba.
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.contracts.evidence_v0 import (
    CONTRACT_VERSION,
    EvidenceRefV0,
    PersistencePolicy,
    SourceType,
    ahora,
    json_schema,
)

AHORA = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)


def _medida(**cambios):
    """Una evidencia medida y válida. Las pruebas cambian un campo cada vez."""
    base = dict(
        source_type=SourceType.OWN_MEASUREMENT,
        source_id="quito:parque:1234",
        observed_at=AHORA - timedelta(days=1),
        retrieved_at=AHORA,
        confidence=0.9,
        methodology="distancia por red peatonal a POI de pois_propios",
        persistence_policy=PersistencePolicy.PERSISTABLE,
    )
    base.update(cambios)
    return EvidenceRefV0(**base)


# ── versionado ───────────────────────────────────────────────────────────────────


def test_el_contrato_lleva_su_version_dentro():
    """Un dato serializado tiene que poder decir bajo qué reglas nació."""
    assert _medida().contract_version == CONTRACT_VERSION == "evidence-ref/v0"
    assert "contract_version" in _medida().model_dump()


def test_una_version_futura_no_se_cuela_como_v0():
    """Deserializar un v1 debe fallar, no degradarse en silencio a v0."""
    datos = _medida().model_dump(mode="json")
    datos["contract_version"] = "evidence-ref/v1"
    with pytest.raises(ValidationError):
        EvidenceRefV0.model_validate(datos)


def test_serializa_y_vuelve_igual():
    original = _medida(limitations=("solo cubre el bbox de Quito",))
    assert EvidenceRefV0.model_validate(original.model_dump(mode="json")) == original


def test_el_json_schema_se_genera_y_nombra_los_campos_minimos():
    esquema = json_schema()
    props = esquema["properties"]
    for campo in (
        "evidence_id", "source_type", "source_id", "observed_at", "retrieved_at",
        "confidence", "methodology", "persistence_policy", "limitations",
    ):
        assert campo in props, f"el contrato perdió el campo mínimo {campo}"


# ── regla 1: no se inventa procedencia ───────────────────────────────────────────


def test_observed_at_no_tiene_valor_por_defecto():
    """El defecto de E0.3 en una línea: si `observed_at` cayera solo a `retrieved_at`,
    todo dato traído hoy afirmaría describir hoy. Hay que decidirlo y escribirlo."""
    with pytest.raises(ValidationError) as e:
        EvidenceRefV0(
            source_type=SourceType.PROVIDER_API,
            provider="google_places",
            retrieved_at=AHORA,
            confidence=None,
            methodology="Places Details",
            persistence_policy=PersistencePolicy.RUNTIME_ONLY,
        )
    assert "observed_at" in str(e.value)


def test_no_saber_cuando_se_observo_es_un_estado_legitimo():
    ev = _medida(observed_at=None)
    assert ev.observed_at is None
    assert ev.retrieved_at == AHORA


def test_no_se_puede_observar_despues_de_haber_traido():
    with pytest.raises(ValidationError, match="posterior a"):
        _medida(observed_at=AHORA + timedelta(seconds=1))


def test_la_confianza_distingue_no_se_de_seguro_que_no():
    """`None` es una abstención; `0.0` es una medición que dice "no merece confianza".
    Colapsarlos es perder información, así que el contrato los mantiene distintos."""
    assert _medida(confidence=None).confidence is None
    assert _medida(confidence=0.0).confidence == 0.0
    assert _medida(confidence=None) != _medida(confidence=0.0, evidence_id="x")


def test_la_confianza_vive_en_el_intervalo_cerrado_cero_uno():
    assert _medida(confidence=0.0).confidence == 0.0
    assert _medida(confidence=1.0).confidence == 1.0
    for fuera in (-0.01, 1.01, 2.0, -1.0):
        with pytest.raises(ValidationError):
            _medida(confidence=fuera)


def test_omitir_la_confianza_cae_en_no_se_y_no_en_un_numero():
    """El default seguro se permite porque `None` es la afirmación humilde. Omitir
    `observed_at`, en cambio, habría caído en "es de ahora": fuerte y falsa."""
    base = dict(
        source_type=SourceType.PROVIDER_API,
        provider="un_proveedor",
        observed_at=None,
        retrieved_at=AHORA,
        methodology="el proveedor entrega alta/media/baja, sin escala numérica",
        persistence_policy=PersistencePolicy.RUNTIME_ONLY,
    )
    assert EvidenceRefV0(**base).confidence is None


def test_no_hay_evidencia_sin_metodologia():
    with pytest.raises(ValidationError):
        _medida(methodology="")


@pytest.mark.parametrize("campo", ["observed_at", "retrieved_at"])
def test_un_instante_sin_zona_horaria_se_rechaza(campo):
    """Naive en esta máquina es Quito y en el runner es UTC: cinco horas de diferencia
    disfrazadas de dato."""
    with pytest.raises(ValidationError, match="zona horaria"):
        _medida(**{campo: datetime(2026, 8, 25, 12, 0, 0)})


def test_el_ayudante_ahora_trae_zona():
    assert ahora().tzinfo is not None


# ── regla 2: lo no medido declara sus límites (E0.4) ──────────────────────────────


def test_una_heuristica_sin_limites_declarados_no_se_construye():
    with pytest.raises(ValidationError, match="limitations"):
        _medida(source_type=SourceType.HEURISTIC_ESTIMATE, limitations=())


def test_una_heuristica_con_limites_declarados_si_entra():
    """La heurística no está prohibida: a veces es lo único que hay, y ES evidencia.
    Lo prohibido es que entre callada o disfrazada de medición."""
    ev = _medida(
        source_type=SourceType.HEURISTIC_ESTIMATE,
        limitations=("estimación por zona; no hay medición en este punto",),
    )
    assert ev.limitations
    assert ev.es_medicion is False


def test_una_limitacion_en_blanco_no_cuenta_como_limitacion():
    with pytest.raises(ValidationError, match="no limita nada"):
        _medida(source_type=SourceType.HEURISTIC_ESTIMATE, limitations=("   ",))


# ── la ausencia de evidencia NO se representa aquí ───────────────────────────────


def test_no_existe_un_source_type_para_la_ausencia_de_evidencia():
    """Decisión de diseño, no descuido.

    Fabricar una EvidenceRefV0 con source_type="unknown" para decir "no tengo nada" es
    inventarse una procedencia para representar su ausencia — el error de E0.3 con otra
    ropa. La ausencia la declara el contrato consumidor:
        status = insufficient_evidence · evidence = [] · limitations = [...]
    """
    valores = {s.value for s in SourceType}
    assert "unknown" not in valores
    assert not any("unknown" in v or "none" in v or "missing" in v for v in valores)


def test_un_source_type_inventado_se_rechaza():
    with pytest.raises(ValidationError):
        _medida(source_type="unknown")


def test_el_contrato_dice_si_algo_se_midio_pero_no_cuanto_vale():
    """`es_medicion` responde la pregunta que E0.3/E0.4 no podían. Cuánto pesa eso en
    el ranking es del motor, no del contrato."""
    assert _medida().es_medicion is True
    assert _medida(source_type=SourceType.USER_DECLARED).es_medicion is True
    assert _medida(
        source_type=SourceType.HEURISTIC_ESTIMATE, limitations=("x",)
    ).es_medicion is False
    assert not hasattr(_medida(), "peso")


# ── regla 3: ningún proveedor es estructura ──────────────────────────────────────


def test_el_esquema_no_tiene_campos_de_ningun_proveedor():
    """Si esto falla, el contrato tomó la forma del mercado de proveedores."""
    campos = set(json_schema()["properties"])
    prohibidos = {
        "google_place_id", "place_id", "overture_id", "osm_id", "valhalla_id",
        "google", "overture", "osm",
    }
    assert not (campos & prohibidos), (
        f"campos de proveedor en el contrato: {campos & prohibidos}. El proveedor es "
        "un VALOR en `provider`, no una forma del esquema."
    )


def test_el_proveedor_viaja_como_valor():
    ev = _medida(source_type=SourceType.PROVIDER_API, provider="google_places")
    assert ev.provider == "google_places"
    assert ev.model_dump()["provider"] == "google_places"


def test_un_proveedor_nuevo_no_obliga_a_tocar_el_contrato():
    """La prueba de fuego: un proveedor que hoy no existe entra sin cambiar el esquema."""
    antes = json_schema()
    _medida(source_type=SourceType.PROVIDER_API, provider="proveedor_inexistente_2027")
    assert json_schema() == antes


def test_no_se_aceptan_campos_extra():
    """`extra='forbid'`: colar `google_place_id` por la puerta de atrás también falla."""
    with pytest.raises(ValidationError):
        _medida(google_place_id="ChIJ...")


# ── política de persistencia: los tres modos ─────────────────────────────────────


def test_soporta_los_tres_modos_de_persistencia():
    assert {p.value for p in PersistencePolicy} == {
        "persistable", "cacheable_temporarily", "runtime_only",
    }


def test_cache_temporal_sin_plazo_no_se_puede_hacer_cumplir():
    with pytest.raises(ValidationError, match="cache_ttl_seconds"):
        _medida(persistence_policy=PersistencePolicy.CACHEABLE_TEMPORARILY)


def test_cache_temporal_con_plazo_es_valida():
    ev = _medida(
        persistence_policy=PersistencePolicy.CACHEABLE_TEMPORARILY,
        cache_ttl_seconds=30 * 24 * 3600,
    )
    assert ev.cache_ttl_seconds == 2592000
    assert ev.puede_guardarse is True


@pytest.mark.parametrize(
    "politica", [PersistencePolicy.PERSISTABLE, PersistencePolicy.RUNTIME_ONLY]
)
def test_un_plazo_donde_no_aplica_es_una_instruccion_contradictoria(politica):
    with pytest.raises(ValidationError, match="no aplica"):
        _medida(persistence_policy=politica, cache_ttl_seconds=60)


def test_runtime_only_no_toca_disco():
    assert _medida(persistence_policy=PersistencePolicy.RUNTIME_ONLY).puede_guardarse is False


def test_un_plazo_de_cero_o_negativo_no_es_un_plazo():
    for malo in (0, -1):
        with pytest.raises(ValidationError):
            _medida(
                persistence_policy=PersistencePolicy.CACHEABLE_TEMPORARILY,
                cache_ttl_seconds=malo,
            )


# ── inmutabilidad e identidad ────────────────────────────────────────────────────


def test_la_evidencia_no_se_edita_despues_de_creada():
    """Una procedencia mutable es una procedencia que alguien puede corregir para que
    cuadre con el resultado."""
    ev = _medida()
    with pytest.raises(ValidationError):
        ev.confidence = 1.0


def test_las_limitaciones_tampoco_se_pueden_mutar_por_dentro():
    """`frozen=True` impide reasignar el campo, pero no impide `.append()` sobre una
    lista. Si `limitations` fuera lista, se podrían borrar los límites de una heurística
    sin tocar nada más — y afirmaríamos una inmutabilidad que no existe."""
    ev = _medida(source_type=SourceType.HEURISTIC_ESTIMATE, limitations=("estimado",))
    assert isinstance(ev.limitations, tuple)
    with pytest.raises(AttributeError):
        ev.limitations.append("colado")
    with pytest.raises(TypeError):
        ev.limitations[0] = "reescrito"


def test_una_lista_de_entrada_se_congela_en_tupla():
    """El caller puede pasar lista; lo que se guarda es inmutable igualmente."""
    ev = _medida(source_type=SourceType.HEURISTIC_ESTIMATE, limitations=["estimado"])
    assert isinstance(ev.limitations, tuple)


def test_cada_evidencia_nace_con_identidad_propia():
    assert _medida().evidence_id != _medida().evidence_id


def test_la_identidad_se_respeta_si_viene_dada():
    assert _medida(evidence_id="ev-fijo-1").evidence_id == "ev-fijo-1"
