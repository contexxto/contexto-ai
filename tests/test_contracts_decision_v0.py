"""E1.5 — DecisionContextV0.

Lo que estas pruebas defienden es la frontera: este contrato REFERENCIA los tres
contextos, no los contiene. Y no valida que las referencias resuelvan — eso es el
assembler de F2, que es donde los tres están disponibles a la vez.
"""

import ast
import json
import pathlib
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contracts.decision_v0 import (
    CONTRACT_VERSION,
    BuyerContextRefV0,
    DecisionContextV0,
    PlaceContextRefV0,
    PropertyContextRefV0,
    json_schema,
)

AHORA = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)


def _decision(**cambios):
    base = dict(
        decision_id="d-1",
        created_at=AHORA,
        buyer=BuyerContextRefV0(buyer_id="b-1", context_revision=2),
        property=PropertyContextRefV0(provider_id="portal-x", property_id="4471"),
        place=PlaceContextRefV0(place_id="quito:la-floresta:1"),
        score_version="encaje-v0",
    )
    base.update(cambios)
    return DecisionContextV0(**base)


# ── referencia, no contenido ─────────────────────────────────────────────────────


def test_no_contiene_los_contextos_completos():
    """Un DecisionContext que arrastrara copias de los tres sería un snapshot, y la
    reproducibilidad profunda es de DecisionTraceV0.

    Se mira la ESTRUCTURA del esquema —qué modelos quedan embebidos en `$defs`— y no su
    texto: los nombres de los contextos aparecen legítimamente en los docstrings que
    explican por qué no están.
    """
    embebidos = set(json_schema().get("$defs", {}))
    assert embebidos == {
        "BuyerContextRefV0", "PropertyContextRefV0", "PlaceContextRefV0"
    }, f"modelos embebidos inesperados: {embebidos}"


def test_tampoco_los_importa():
    """La ausencia se comprueba sobre el AST y no sobre el texto: los nombres aparecen
    legítimamente en los docstrings que explican esta separación."""
    import app.contracts.decision_v0 as modulo

    arbol = ast.parse(pathlib.Path(modulo.__file__).read_text(encoding="utf-8"))
    importados = {
        alias.name
        for n in ast.walk(arbol)
        if isinstance(n, ast.ImportFrom)
        for alias in n.names
    }
    for clase in ("BuyerContextV0", "PropertyContextV0", "PlaceContextV0"):
        assert clase not in importados, f"importa {clase}: eso es contenerlo, no referenciarlo"


def test_las_referencias_son_pequenas():
    """Cada una lleva identidad y versión, nada más."""
    assert set(BuyerContextRefV0.model_fields) == {
        "buyer_id", "context_revision", "contract_version"
    }
    assert set(PropertyContextRefV0.model_fields) == {
        "provider_id", "property_id", "contract_version"
    }
    assert set(PlaceContextRefV0.model_fields) == {"place_id", "contract_version"}


# ── identidad precisa, no referencias débiles ────────────────────────────────────


def test_la_referencia_al_inmueble_conserva_proveedor_e_id():
    """`property_id` solo es único dentro de su proveedor: sin el par, dos inmuebles
    distintos de dos portales se confunden."""
    r = PropertyContextRefV0(provider_id="portal-x", property_id="4471")
    assert r.identidad_externa == ("portal-x", "4471")
    otro = PropertyContextRefV0(provider_id="portal-y", property_id="4471")
    assert r != otro


def test_el_proveedor_no_es_opcional_en_la_referencia():
    with pytest.raises(ValidationError):
        PropertyContextRefV0(property_id="4471")


def test_la_referencia_al_comprador_conserva_la_revision_del_estado():
    """Un comprador cambia de opinión: una decisión tomada sobre la revisión 2 no se
    explica con la revisión 5."""
    r = BuyerContextRefV0(buyer_id="b-1", context_revision=2)
    assert r.context_revision == 2
    assert r != BuyerContextRefV0(buyer_id="b-1", context_revision=5)


def test_sin_revision_es_legitimo_pero_no_se_inventa_un_numero():
    """Mientras F3 no construya el store con historial, no hay revisiones que citar."""
    assert BuyerContextRefV0(buyer_id="b-1").context_revision is None


def test_la_referencia_al_lugar_exige_identificador():
    """En PlaceContextV0 `place_id` es opcional —un cálculo de paso vale— pero para
    PARTICIPAR EN UNA DECISIÓN hay que poder volver a nombrarlo."""
    with pytest.raises(ValidationError):
        PlaceContextRefV0()
    assert PlaceContextRefV0(place_id="quito:1").place_id == "quito:1"


def test_cada_referencia_declara_la_version_del_contrato_al_que_apunta():
    d = _decision()
    assert d.buyer.contract_version == "buyer-context-v0"
    assert d.property.contract_version == "property-context-v0"
    assert d.place.contract_version == "place-context-v0"


def test_las_versiones_de_las_referencias_no_se_falsean():
    datos = _decision().model_dump(mode="json")
    datos["place"]["contract_version"] = "place-context-v1"
    with pytest.raises(ValidationError):
        DecisionContextV0.model_validate(datos)


# ── anclas: por id y solo por id ─────────────────────────────────────────────────


def test_las_anclas_se_referencian_por_id():
    d = _decision(anchor_ids=("a-1", "a-2"))
    assert d.anchor_ids == ("a-1", "a-2")


def test_no_hay_ningun_campo_de_label_en_la_decision():
    """Correlacionar por texto es lo que se cerró en E1.2/E1.4."""
    texto = json.dumps(json_schema()).lower()
    for prohibido in ('"anchor_label"', '"label"'):
        assert prohibido not in texto


def test_modificar_el_label_de_un_ancla_no_afecta_la_referencia():
    """La decisión apunta al id; el nombre puede cambiar cuantas veces quiera."""
    from app.contracts.buyer_v0 import CommuteAnchorV0

    antes = CommuteAnchorV0(anchor_id="a-1", label="la oficina", raw_location="X")
    despues = antes.model_copy(update={"label": "la oficina vieja"})

    d = _decision(anchor_ids=(antes.anchor_id,))
    assert d.anchor_ids == (despues.anchor_id,)
    assert antes.label != despues.label


def test_una_decision_puede_no_mirar_trayectos():
    assert _decision().anchor_ids == ()


def test_un_ancla_no_se_referencia_dos_veces():
    with pytest.raises(ValidationError, match="anchor_id repetido"):
        _decision(anchor_ids=("a-1", "a-1"))


def test_un_id_en_blanco_no_referencia_nada():
    with pytest.raises(ValidationError, match="no referencia nada"):
        _decision(anchor_ids=("  ",))


# ── lo que NO se construye en F1 ─────────────────────────────────────────────────


def test_no_hay_resolver_ni_fetch_ni_assembler():
    """Todo eso es F2/F6."""
    import app.contracts.decision_v0 as modulo

    for prohibido in (
        "resolve", "resolver", "fetch", "load", "assemble", "assembler",
        "snapshot", "hash", "store", "save",
    ):
        assert not hasattr(DecisionContextV0, prohibido)
        assert not hasattr(modulo, prohibido)


def test_no_valida_que_las_referencias_resuelvan():
    """NO PUEDE: no tiene los contextos delante, solo referencias. Fingir aquí esa
    validación daría una garantía falsa. El invariante —todo anchor_id usado existe en
    BuyerContextV0.commute_anchors— es del assembler de F2."""
    d = _decision(
        buyer=BuyerContextRefV0(buyer_id="no-existe"),
        anchor_ids=("ancla-que-nadie-declaro",),
    )
    assert d.anchor_ids == ("ancla-que-nadie-declaro",)


def test_no_trae_scoring_nuevo():
    texto = json.dumps(json_schema()).lower()
    for prohibido in ('"score"', '"weight"', '"rank"', '"decision_eligible"'):
        assert prohibido not in texto


def test_no_duplica_la_evidencia_de_los_contextos():
    """La evidencia vive en los contextos referenciados; copiarla aquí convertiría este
    objeto en el snapshot que se decidió que no fuera."""
    assert "evidence" not in json_schema()["properties"]


# ── score_version, versionado, serialización ─────────────────────────────────────


def test_registra_bajo_que_reglas_se_decidio():
    """Mismo campo que E0.4 introdujo en calcular_encaje(): dos números producidos por
    reglas distintas no son comparables, y sin registrar la regla nadie lo sabría."""
    assert _decision().score_version == "encaje-v0"
    with pytest.raises(ValidationError):
        _decision(score_version="")


def test_el_contrato_lleva_su_version():
    assert _decision().contract_version == CONTRACT_VERSION == "decision-context-v0"


def test_una_version_futura_no_se_cuela():
    datos = _decision().model_dump(mode="json")
    datos["contract_version"] = "decision-context-v1"
    with pytest.raises(ValidationError):
        DecisionContextV0.model_validate(datos)


def test_las_referencias_sobreviven_el_ida_y_vuelta():
    original = _decision(anchor_ids=("a-1", "a-2"))
    crudo = original.model_dump(mode="json")
    assert crudo["property"]["provider_id"] == "portal-x"
    assert crudo["property"]["property_id"] == "4471"
    assert crudo["buyer"]["context_revision"] == 2
    assert crudo["place"]["place_id"] == "quito:la-floresta:1"
    assert crudo["anchor_ids"] == ["a-1", "a-2"]

    vuelta = DecisionContextV0.model_validate(crudo)
    assert vuelta == original
    assert vuelta.property.identidad_externa == ("portal-x", "4471")


def test_created_at_exige_zona_horaria():
    with pytest.raises(ValidationError, match="zona horaria"):
        _decision(created_at=datetime(2026, 8, 25, 12, 0, 0))


def test_la_decision_no_se_edita_despues_de_creada():
    d = _decision()
    with pytest.raises(ValidationError):
        d.score_version = "encaje-v1"


def test_no_se_aceptan_campos_extra():
    with pytest.raises(ValidationError):
        _decision(buyer_context={"todo": "el objeto"})
