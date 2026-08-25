"""E1.2 — BuyerContextV0.

Las pruebas están agrupadas por las cuatro reglas congeladas. Tres de ellas son
estructurales y se pueden anclar mecánicamente; la cuarta —que las categorías protegidas
tampoco aparezcan en el TEXTO libre— no se puede probar aquí y el módulo lo dice.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.contracts.buyer_v0 import (
    CONTRACT_VERSION,
    BuyerContextV0,
    CommuteAnchor,
    Direction,
    FieldEvidence,
    Financial,
    Mobility,
    Money,
    Objective,
    PlacePreference,
    PropertyRequirements,
    Stage,
    Tradeoff,
    TravelMode,
    UnresolvedQuestion,
    json_schema,
)
from app.contracts.evidence_v0 import (
    EvidenceRefV0,
    PersistencePolicy,
    SourceType,
)

AHORA = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)


def _comprador(**cambios):
    base = dict(buyer_id="b-1", updated_at=AHORA)
    base.update(cambios)
    return BuyerContextV0(**base)


def _evidencia():
    return EvidenceRefV0(
        source_type=SourceType.USER_DECLARED,
        observed_at=AHORA,
        retrieved_at=AHORA,
        methodology="lo dijo en la conversación",
        persistence_policy=PersistencePolicy.PERSISTABLE,
    )


# ── regla 1: `household` es estructuralmente inexistente ─────────────────────────


def test_household_no_es_un_campo_del_contrato():
    """No basta excluirlo del scoring: si el campo existe, alguien lo llena."""
    assert "household" not in json_schema()["properties"]


def test_pasar_household_revienta_al_construir():
    """`extra="forbid"` hace que esto falle aquí y no en una revisión de código."""
    with pytest.raises(ValidationError):
        _comprador(household={"adultos": 2, "ninos": 2})


def test_ninguna_categoria_protegida_es_estructura():
    """Recorre el esquema entero, no solo el primer nivel."""
    import json

    texto = json.dumps(json_schema()).lower()
    prohibidas = [
        "household", "family_status", "familial", "marital", "children_count",
        "race", "ethnicity", "religion", "nationality", "national_origin",
        "gender", "sex", "sexual_orientation", "disability", "handicap", "age_group",
    ]
    encontradas = [p for p in prohibidas if f'"{p}"' in texto]
    assert not encontradas, (
        f"categorías protegidas como estructura: {encontradas}. El Plan 1.0 las "
        "sustituyó por necesidades explícitas del inmueble."
    )


def test_la_necesidad_se_expresa_como_requisito_del_inmueble():
    """"Familia de cuatro" describe a la persona; "tres dormitorios" describe al
    inmueble y es verificable contra él."""
    req = PropertyRequirements(bedrooms_min=3, area_m2_min=90.0, pets_allowed_required=True)
    assert req.bedrooms_min == 3
    assert req.pets_allowed_required is True


def test_accesibilidad_describe_al_inmueble_y_no_a_la_persona():
    """La discapacidad es categoría protegida; un requisito de acceso sin escalones es
    una especificación del inmueble."""
    req = PropertyRequirements(accessibility_requirements=("sin escalones", "ascensor"))
    assert req.accessibility_requirements == ("sin escalones", "ascensor")
    campos = set(PropertyRequirements.model_json_schema()["properties"])
    assert not any("disab" in c or "condition" in c for c in campos)


# ── regla 2: los cuatro registros no se funden ───────────────────────────────────


def test_los_cuatro_registros_existen_por_separado():
    props = set(json_schema()["properties"])
    for campo in ("hard_constraints", "soft_preferences", "tradeoffs", "unresolved_questions"):
        assert campo in props


def test_no_hay_ningun_campo_de_pesos():
    """Regla 2: si apareciera `{dimensión: peso}`, "no puede tener escaleras" y
    "prefiere un parque cerca" pasarían a ser la misma clase de cosa."""
    import json

    texto = json.dumps(json_schema()).lower()
    for sospechoso in ('"weight"', '"weights"', '"score"', '"importance"', '"priority"'):
        assert sospechoso not in texto, f"apareció {sospechoso}: eso es ponderar"


def test_una_restriccion_dura_y_una_preferencia_blanda_no_se_mezclan():
    b = _comprador(
        hard_constraints=("sin escalones",),
        soft_preferences=("que haya un parque cerca",),
    )
    assert b.hard_constraints == ("sin escalones",)
    assert b.soft_preferences == ("que haya un parque cerca",)
    assert set(b.hard_constraints) & set(b.soft_preferences) == set()


def test_un_tradeoff_dice_que_se_cambia_por_que():
    """Un peso dice "esto vale 0,7"; un tradeoff se puede verificar contra una opción."""
    t = Tradeoff(gives_up="20 minutos más de trayecto", gains="un dormitorio más")
    assert t.gives_up and t.gains
    assert not hasattr(t, "weight")


def test_una_restriccion_en_blanco_se_rechaza():
    with pytest.raises(ValidationError, match="en blanco"):
        _comprador(hard_constraints=("  ",))


def test_una_preferencia_de_lugar_lleva_sentido_pero_no_peso():
    p = PlacePreference(dimension="ruido", direction=Direction.LESS)
    assert p.direction is Direction.LESS
    assert PlacePreference(dimension="ruido").direction is Direction.UNSPECIFIED
    assert not hasattr(p, "weight")


# ── regla 3: `stage` no es el eje de `intencion.py` ──────────────────────────────


def test_stage_y_el_embudo_comercial_no_comparten_vocabulario():
    """Prueba mecánica de la regla 3. Si alguien acerca los dos ejes, esto se cae.

    `app/intencion.py` mide cuán cerca está de transaccionar (eje de VENTA).
    `stage` mide cuánto ha convergido sobre lo que quiere (eje de DECISIÓN).
    """
    from app.intencion import ESTADOS

    solapan = {s.value for s in Stage} & set(ESTADOS)
    assert not solapan, (
        f"stage y el embudo comercial comparten {solapan}. Son ejes ortogonales: se "
        "puede tener criterios clarísimos y cero intención de comprar este año."
    )


def test_stage_admite_no_saber_y_no_lo_confunde_con_orientarse():
    """`UNKNOWN` es ignorancia nuestra; `ORIENTING` es una afirmación sobre la persona."""
    assert _comprador().stage is Stage.UNKNOWN
    assert Stage.UNKNOWN != Stage.ORIENTING


# ── regla 4: una sola procedencia ────────────────────────────────────────────────


def test_field_evidence_apunta_a_evidence_ref_v0():
    fe = FieldEvidence(field="financial.budget_max", evidence=_evidencia())
    b = _comprador(field_evidence=(fe,))
    assert isinstance(b.field_evidence[0].evidence, EvidenceRefV0)
    assert b.field_evidence[0].evidence.contract_version == "evidence-ref/v0"


def test_no_hay_un_segundo_sistema_de_procedencia():
    """Los campos de procedencia viven en EvidenceRefV0, no repetidos aquí."""
    props = set(json_schema()["properties"])
    for propio_de_evidencia in ("source_type", "provider", "confidence", "methodology"):
        assert propio_de_evidencia not in props


def test_una_evidencia_inventada_no_pasa_por_field_evidence():
    with pytest.raises(ValidationError):
        FieldEvidence(field="financial.budget_max", evidence={"fuente": "me lo dijeron"})


# ── conocimiento parcial: `unknown` es de primera clase ──────────────────────────


def test_un_comprador_recien_conocido_es_valido_y_casi_todo_vacio():
    """Al empezar una conversación no sabemos nada, y eso tiene que poder representarse
    sin inventar defaults."""
    b = _comprador()
    assert b.objective is Objective.UNKNOWN
    assert b.stage is Stage.UNKNOWN
    assert b.financial.budget_max is None
    assert b.property_requirements.bedrooms_min is None
    assert b.mobility.commute_anchors == ()
    assert b.hard_constraints == ()


def test_lo_que_falta_se_nombra_en_vez_de_suponerse():
    """Sin `unresolved_questions`, un hueco y un descuido son indistinguibles."""
    b = _comprador(
        unresolved_questions=(
            UnresolvedQuestion(
                question="¿cuál es su presupuesto máximo?",
                about_field="financial.budget_max",
            ),
        )
    )
    assert b.financial.budget_max is None
    assert b.unresolved_questions[0].about_field == "financial.budget_max"


# ── movilidad: estructurada, sin resolver ────────────────────────────────────────


def test_un_ancla_guarda_lo_que_dijo_la_persona_sin_resolverlo():
    a = CommuteAnchor(label="la oficina", raw_location="La Carolina", mode=TravelMode.TRANSIT)
    assert a.esta_resuelta is False
    assert a.lat is None


def test_un_ancla_resuelta_conserva_el_texto_original():
    """Si la geocodificación fue mala, el texto original es lo único que lo delata."""
    a = CommuteAnchor(
        label="la oficina", raw_location="La Carolina", lat=-0.18, lon=-78.48
    )
    assert a.esta_resuelta is True
    assert a.raw_location == "La Carolina"


def test_media_coordenada_no_ubica_nada():
    with pytest.raises(ValidationError, match="van juntas"):
        CommuteAnchor(label="oficina", lat=-0.18)


def test_un_ancla_sin_destino_no_es_un_ancla():
    with pytest.raises(ValidationError, match="sin destino"):
        CommuteAnchor(label="la oficina")


def test_el_contrato_no_calcula_trayectos():
    """F1 es contratos. `compute_travel_to_anchor` pertenece a Place Harness."""
    a = CommuteAnchor(label="oficina", raw_location="La Carolina")
    assert not hasattr(a, "compute_travel_to_anchor")
    assert not hasattr(Mobility, "compute_travel_to_anchor")


# ── versionado: contrato vs estado ───────────────────────────────────────────────


def test_version_es_la_del_contrato_y_no_la_del_estado():
    b = _comprador()
    assert b.version == CONTRACT_VERSION == "buyer-context-v0"
    assert b.context_revision is None


def test_la_revision_del_estado_vive_en_otro_campo():
    """Si las dos compartieran campo, sería imposible saber si un cambio viene de que
    la persona dijo algo nuevo o de que cambiaron las reglas del esquema."""
    b = _comprador(context_revision=3)
    assert b.context_revision == 3
    assert b.version == "buyer-context-v0"


def test_una_version_futura_del_contrato_no_se_cuela():
    datos = _comprador().model_dump(mode="json")
    datos["version"] = "buyer-context-v1"
    with pytest.raises(ValidationError):
        BuyerContextV0.model_validate(datos)


def test_no_se_implementa_historial_ni_diff():
    """F1 modela el contrato que F3 podrá persistir; no lo persiste."""
    for prohibido in ("history", "revisions", "diff", "save", "store", "apply_update"):
        assert not hasattr(BuyerContextV0, prohibido)


# ── serialización e inmutabilidad ────────────────────────────────────────────────


def test_serializa_y_vuelve_igual_con_todo_lleno():
    original = _comprador(
        objective=Objective.RENT,
        financial=Financial(budget_max=Money(amount=Decimal("900"), currency="USD")),
        property_requirements=PropertyRequirements(bedrooms_min=2),
        mobility=Mobility(
            commute_anchors=(
                CommuteAnchor(label="oficina", raw_location="La Carolina", max_minutes=30),
            )
        ),
        place_preferences=(PlacePreference(dimension="ruido", direction=Direction.LESS),),
        hard_constraints=("sin escalones",),
        soft_preferences=("parque cerca",),
        tradeoffs=(Tradeoff(gives_up="10 minutos", gains="un dormitorio"),),
        stage=Stage.NARROWING,
        field_evidence=(FieldEvidence(field="financial.budget_max", evidence=_evidencia()),),
        unresolved_questions=(UnresolvedQuestion(question="¿mascotas?"),),
        context_revision=2,
    )
    assert BuyerContextV0.model_validate(original.model_dump(mode="json")) == original


def test_el_contexto_no_se_edita_despues_de_creado():
    b = _comprador()
    with pytest.raises(ValidationError):
        b.stage = Stage.COMMITTING


def test_las_colecciones_tampoco_se_mutan_por_dentro():
    b = _comprador(hard_constraints=("sin escalones",))
    assert isinstance(b.hard_constraints, tuple)
    with pytest.raises(AttributeError):
        b.hard_constraints.append("colado")


def test_el_presupuesto_lleva_moneda():
    """Un número suelto no dice si son 200 000 dólares o pesos."""
    with pytest.raises(ValidationError):
        Money(amount=Decimal("200000"), currency="dolares")
    assert Money(amount=Decimal("200000"), currency="USD").currency == "USD"


def test_updated_at_exige_zona_horaria():
    with pytest.raises(ValidationError, match="zona horaria"):
        _comprador(updated_at=datetime(2026, 8, 25, 12, 0, 0))


def test_el_esquema_nombra_todos_los_campos_minimos():
    props = set(json_schema()["properties"])
    for campo in (
        "buyer_id", "version", "objective", "financial", "property_requirements",
        "mobility", "place_preferences", "hard_constraints", "soft_preferences",
        "tradeoffs", "stage", "field_evidence", "unresolved_questions", "updated_at",
    ):
        assert campo in props, f"el contrato perdió el campo mínimo {campo}"
