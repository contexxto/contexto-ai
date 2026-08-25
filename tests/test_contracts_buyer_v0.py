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
    CriterionOrigin,
    CriterionStatus,
    DecisionCriterionV0,
    Direction,
    FieldEvidence,
    Financial,
    Mobility,
    Money,
    Objective,
    Operator,
    PlacePreference,
    PropertyRequirements,
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


def _criterio(**cambios):
    base = dict(
        criterion_id="c-1",
        dimension="bedrooms",
        operator=Operator.GTE,
        value=3,
        origin=CriterionOrigin.STATED,
    )
    base.update(cambios)
    return DecisionCriterionV0(**base)


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
    """Misma primitiva, campos distintos: lo que cambia es cómo se usan."""
    dura = _criterio(criterion_id="c-dura", dimension="stairs", operator=Operator.NOT_EXISTS, value=None)
    blanda = _criterio(criterion_id="c-blanda", dimension="park_distance_m", operator=Operator.LTE, value=500, unit="m")
    b = _comprador(hard_constraints=(dura,), soft_preferences=(blanda,))
    assert b.hard_constraints[0].criterion_id == "c-dura"
    assert b.soft_preferences[0].criterion_id == "c-blanda"


def test_un_tradeoff_dice_que_se_cambia_por_que():
    """Un peso dice "esto vale 0,7"; un tradeoff se puede verificar contra una opción."""
    t = Tradeoff(gives_up="20 minutos más de trayecto", gains="un dormitorio más")
    assert t.gives_up and t.gains
    assert not hasattr(t, "weight")


def test_una_restriccion_ya_no_es_prosa():
    """El cambio de fondo de la revisión: guardarlas como texto obligaba a reparsear
    prosa para comprobarlas, y reparsear prosa con un LLM es donde se cuelan las
    alucinaciones que FASE 0 se pasó cerrando."""
    with pytest.raises(ValidationError):
        _comprador(hard_constraints=("sin escalones",))


# ── la primitiva de criterio ─────────────────────────────────────────────────────


def test_un_criterio_es_evaluable_sin_reparsear_prosa():
    c = _criterio()
    assert (c.dimension, c.operator, c.value) == ("bedrooms", Operator.GTE, 3)


def test_el_operador_no_conoce_el_dominio_inmobiliario():
    """Un `Operator` con valores tipo MIN_BEDROOMS obligaría a tocar la primitiva cada
    vez que apareciera una dimensión nueva."""
    valores = {o.value for o in Operator}
    assert not any(
        t in v for v in valores for t in ("bedroom", "area", "price", "property", "pet")
    )


def test_el_valor_tiene_que_encajar_con_el_operador():
    """Sin esto, `GTE` con "tres" se guarda tan tranquilo y revienta meses después, en
    el evaluador, lejos de donde se creó."""
    with pytest.raises(ValidationError, match="necesita un número"):
        _criterio(operator=Operator.GTE, value="tres")
    with pytest.raises(ValidationError, match="no lleva value"):
        _criterio(operator=Operator.EXISTS, value=3)
    with pytest.raises(ValidationError, match="necesita un value"):
        _criterio(operator=Operator.EQ, value=None)
    with pytest.raises(ValidationError, match="colección"):
        _criterio(operator=Operator.IN, value="quito")
    with pytest.raises(ValidationError, match="vacía"):
        _criterio(operator=Operator.IN, value=())
    with pytest.raises(ValidationError, match="valor único"):
        _criterio(operator=Operator.EQ, value=("a", "b"))


def test_ordenar_booleanos_no_significa_nada():
    """`bool` es subclase de `int` en Python, así que `GTE True` colaría sin esto."""
    with pytest.raises(ValidationError, match="necesita un número"):
        _criterio(operator=Operator.GT, value=True)


def test_presencia_y_ausencia_se_expresan_con_su_operador():
    c = _criterio(dimension="stairs", operator=Operator.NOT_EXISTS, value=None)
    assert c.value is None and c.unit is None


def test_un_criterio_pertenece_a_una_lista_de_valores():
    c = _criterio(dimension="barrio", operator=Operator.IN, value=("Cumbayá", "La Floresta"))
    assert c.value == ("Cumbayá", "La Floresta")


def test_origen_y_ciclo_de_vida_son_ejes_independientes():
    """Con un solo enum (`stated|inferred|retracted`) estas dos combinaciones no se
    podían expresar: retirar un criterio borraba de dónde había salido."""
    assert {o.value for o in CriterionOrigin} == {"stated", "inferred"}
    assert {s.value for s in CriterionStatus} == {"active", "retracted"}

    inferido_vigente = _criterio(origin=CriterionOrigin.INFERRED)
    assert inferido_vigente.origin is CriterionOrigin.INFERRED
    assert inferido_vigente.esta_activo is True

    declarado_retirado = _criterio(
        origin=CriterionOrigin.STATED, status=CriterionStatus.RETRACTED
    )
    assert declarado_retirado.origin is CriterionOrigin.STATED
    assert declarado_retirado.esta_activo is False


def test_el_origen_hay_que_declararlo():
    """Sin default, por la misma razón que `observed_at` en E1.1: un origen por omisión
    sería una afirmación que nadie tomó."""
    with pytest.raises(ValidationError, match="origin"):
        DecisionCriterionV0(
            criterion_id="c-1", dimension="bedrooms", operator=Operator.GTE, value=3
        )


def test_un_criterio_retirado_se_conserva_entero():
    """Permanece en el contexto con su id y su evidencia: saber que alguien descartó un
    criterio es información, y borrarlo hace que el sistema vuelva a proponer lo que ya
    rechazó."""
    c = _criterio(status=CriterionStatus.RETRACTED, evidence=(_evidencia(),))
    b = _comprador(hard_constraints=(c,))
    guardado = b.hard_constraints[0]
    assert guardado.criterion_id == "c-1"
    assert guardado.evidence
    assert guardado.esta_activo is False


def test_el_contrato_no_gestiona_el_ciclo_de_vida():
    """Cómo se pasa de ACTIVE a RETRACTED es Buyer Harness: aquí no hay historial, ni
    updater, ni resolución de conflictos."""
    for prohibido in ("retract", "activate", "resolve_conflict", "merge"):
        assert not hasattr(DecisionCriterionV0, prohibido)


def test_la_evidencia_del_criterio_viaja_dentro_del_criterio():
    """Y no por una ruta tipo `hard_constraints[0]`, que deja de apuntar a lo mismo en
    cuanto cambia el orden del array."""
    c = _criterio(evidence=(_evidencia(),))
    assert isinstance(c.evidence[0], EvidenceRefV0)


def test_el_criterion_id_es_unico_en_todo_el_contexto():
    """Solo sirve como referencia estable si no se repite."""
    with pytest.raises(ValidationError, match="repetido"):
        _comprador(
            hard_constraints=(_criterio(criterion_id="c-1"),),
            soft_preferences=(_criterio(criterion_id="c-1", dimension="area_m2"),),
        )


def test_el_contrato_no_evalua_criterios():
    """F1 representa; Decision Core evalúa."""
    for prohibido in ("evaluate", "matches", "check", "parse", "apply"):
        assert not hasattr(DecisionCriterionV0, prohibido)


def test_una_preferencia_de_lugar_lleva_sentido_pero_no_peso():
    p = PlacePreference(dimension="ruido", direction=Direction.LESS)
    assert p.direction is Direction.LESS
    assert PlacePreference(dimension="ruido").direction is Direction.UNSPECIFIED
    assert not hasattr(p, "weight")


# ── regla 3: `stage` no es el eje de `intencion.py` ──────────────────────────────


def test_el_vocabulario_de_stage_queda_abierto_en_v0():
    """Decisión explícita, no descuido: valores como orienting/narrowing/validating son
    razonables pero son una HIPÓTESIS sobre cómo decide la gente, sin evidencia de
    producto detrás. Congelarlos en un enum les daría la misma fuerza que a un hecho
    medido. Se cerrará cuando exista esa evidencia."""
    esquema = json_schema()["properties"]["stage"]
    assert "enum" not in str(esquema), "stage se cerró a enum sin evidencia de uso"
    assert _comprador(stage="narrowing").stage == "narrowing"
    assert _comprador(stage="cualquier-vocabulario-futuro").stage is not None


def test_stage_admite_no_saber():
    assert _comprador().stage is None


def test_un_stage_en_blanco_no_es_un_stage():
    """Abierto no es lo mismo que vacío: si no hay señal, el valor es `None`."""
    with pytest.raises(ValidationError):
        _comprador(stage="")


def test_la_documentacion_fija_que_stage_es_el_eje_de_decision():
    """La ortogonalidad con `app/intencion.py` ya no la puede forzar el tipo —es el
    precio, asumido, de no congelar una hipótesis sin evidencia—, así que tiene que
    estar escrita donde alguien la lea antes de rellenar el campo.

    Esta prueba se cae si alguien borra esa explicación del módulo.
    """
    import app.contracts.buyer_v0 as modulo

    doc = (modulo.__doc__ or "").lower()
    assert "intencion.py" in doc
    assert "ortogonal" in doc or "no el calor comercial" in doc
    assert "decisión" in doc


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
    assert b.stage is None
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
        hard_constraints=(_criterio(criterion_id="c-h", dimension="stairs",
                                   operator=Operator.NOT_EXISTS, value=None,
                                   evidence=(_evidencia(),)),),
        soft_preferences=(_criterio(criterion_id="c-s", dimension="park_distance_m",
                                    operator=Operator.LTE, value=500, unit="m"),),
        tradeoffs=(Tradeoff(gives_up="10 minutos", gains="un dormitorio"),),
        stage="narrowing",
        field_evidence=(FieldEvidence(field="financial.budget_max", evidence=_evidencia()),),
        unresolved_questions=(UnresolvedQuestion(question="¿mascotas?"),),
        context_revision=2,
    )
    assert BuyerContextV0.model_validate(original.model_dump(mode="json")) == original


def test_el_contexto_no_se_edita_despues_de_creado():
    b = _comprador()
    with pytest.raises(ValidationError):
        b.stage = "committing"


def test_las_colecciones_tampoco_se_mutan_por_dentro():
    b = _comprador(hard_constraints=(_criterio(),))
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
