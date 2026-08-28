"""E3.2b.2 · el reducer · R1-R7 y R-IDEMP-1.

Aquí el lote se vuelve memoria, así que los fallos de esta capa son los que se quedan. Dos
clases distintas, y las dos tienen tests propios:

```
lo que ESCRIBE MAL     un Clear que inventa valor, una ambigüedad que borra estado
lo que NO SE PUEDE     un contexto parcial, un replay que parece divergente
   REPRODUCIR
```

Puro y offline: sin base, sin reloj, sin modelo. El único instante operacional —`retrieved_at`
— entra como argumento, que es lo que permite fijarlo en los tests sin falsear nada.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from app.buyer.boundary import (
    BuyerCurrencyV0, BuyerFieldV0, BuyerMutationV0, ClearAreaM2Min, ClearBedroomsMin,
    ClearBudgetMax, ClearObjective, ClearPetsRequired, SetAreaM2Min, SetBedroomsMin,
    SetBudgetMax, SetObjective, SetPetsRequired,
)
from app.buyer.extractor import (
    AfirmacionAmbiguous, AfirmacionDurable, AfirmacionRejected, AfirmacionTurnOnly,
    construir_lote,
)
from app.buyer.mensaje import IdentifiedUserMessage
from app.buyer.reductor import (
    ReduccionImposible, evidence_id_determinista, reducir,
)
from app.buyer.store import _canonico
from app.contracts.buyer_v0 import BuyerContextV0, Objective

T0 = dt.datetime(2026, 8, 28, 12, 0, tzinfo=dt.timezone.utc)
USD = BuyerCurrencyV0.USD
F = BuyerFieldV0


def _base(**extra) -> BuyerContextV0:
    return BuyerContextV0(buyer_id="b-1", updated_at=T0, **extra)


def _lote(*afirmaciones, mid="m-1", texto="lo que dijo"):
    return construir_lote(IdentifiedUserMessage(message_id=mid, text=texto),
                          list(afirmaciones))


def _dur(m):
    return AfirmacionDurable(mutacion=m, motivo="declarado")


def _amb(campo):
    return AfirmacionAmbiguous(campo=campo, motivo="no acreditado")


_BUD = SetBudgetMax(amount=Decimal(120000), currency=USD)


# ══ R2 · exhaustividad · las diez variantes ═════════════════════════════════════════


def test_R2_el_reducer_cubre_TODA_la_union_de_mutaciones():
    """META-TEST de totalidad. Si mañana se añade una variante a `BuyerMutationV0` y nadie
    decide qué escribe, esto se pone rojo — en vez de que la mutación se aplique a medias o se
    salte en silencio."""
    import typing

    from app.buyer import reductor

    en_union = set(typing.get_args(typing.get_args(BuyerMutationV0)[0]))
    assert en_union == set(reductor._APLICADORES), (
        f"sin aplicador: {[c.__name__ for c in en_union - set(reductor._APLICADORES)]}")


@pytest.mark.parametrize("mutacion,lee,esperado", [
    (SetObjective(objective=Objective.RENT), lambda c: c.objective, Objective.RENT),
    (SetBedroomsMin(bedrooms_min=3), lambda c: c.property_requirements.bedrooms_min, 3),
    (SetAreaM2Min(area_m2_min=80.0), lambda c: c.property_requirements.area_m2_min, 80.0),
    (SetPetsRequired(), lambda c: c.property_requirements.pets_allowed_required, True),
])
def test_R3_cada_SET_escribe_su_campo(mutacion, lee, esperado):
    assert lee(reducir(_base(), _lote(_dur(mutacion)), T0)) == esperado


def test_R3_el_presupuesto_escribe_monto_Y_moneda():
    c = reducir(_base(), _lote(_dur(_BUD)), T0)
    assert c.financial.budget_max.amount == Decimal(120000)
    assert c.financial.budget_max.currency == "USD"


@pytest.mark.parametrize("previo,limpiar,lee", [
    ({"objective": Objective.BUY}, ClearObjective(), lambda c: c.objective),
    ({"financial": {"budget_max": {"amount": "9", "currency": "USD"}}},
     ClearBudgetMax(), lambda c: c.financial.budget_max),
    ({"property_requirements": {"bedrooms_min": 2}},
     ClearBedroomsMin(), lambda c: c.property_requirements.bedrooms_min),
    ({"property_requirements": {"area_m2_min": 50.0}},
     ClearAreaM2Min(), lambda c: c.property_requirements.area_m2_min),
    ({"property_requirements": {"pets_allowed_required": True}},
     ClearPetsRequired(), lambda c: c.property_requirements.pets_allowed_required),
])
def test_R3_cada_CLEAR_devuelve_el_campo_a_su_AUSENCIA(previo, limpiar, lee):
    """Un `Clear` no inventa otro valor. Va a `None` — o a `UNKNOWN` en el objetivo, que es
    como el contrato expresa "no hay declaración" porque ahí no admite `None`."""
    resultado = lee(reducir(_base(**previo), _lote(_dur(limpiar)), T0))
    assert resultado in (None, Objective.UNKNOWN)


def test_R3_un_CLEAR_sobre_un_campo_VACIO_no_rompe_ni_inventa():
    c = reducir(_base(), _lote(_dur(ClearBudgetMax())), T0)
    assert c.financial.budget_max is None


# ══ R1 · atomicidad ═════════════════════════════════════════════════════════════════


def test_R1_una_mutacion_no_aplicable_no_deja_contexto_PARCIAL():
    """R1: o se aplican todas o ninguna. Un `skip` silencioso dejaría un estado que no es ni
    lo que el usuario dijo ni lo que había, y nadie se enteraría."""
    class Impostora:
        tipo = "set_inventado"

    lote = _lote(_dur(SetObjective(objective=Objective.BUY)))
    # se fuerza una mutación fuera de la unión DESPUÉS de construir el lote, que es la única
    # forma de que llegue aquí: el lote la habría rechazado
    roto = lote.model_copy(update={"afirmaciones": (
        *lote.afirmaciones,
        AfirmacionDurable.model_construct(mutacion=Impostora(), motivo="x"),)})

    with pytest.raises(ReduccionImposible):
        reducir(_base(), roto, T0)


def test_R1_el_contexto_base_no_se_MUTA_nunca():
    base = _base(objective=Objective.RENT)
    reducir(base, _lote(_dur(SetObjective(objective=Objective.BUY))), T0)
    assert base.objective is Objective.RENT


# ══ R4 · TURN_ONLY y REJECTED no tocan memoria ══════════════════════════════════════


def test_R4_turn_only_y_rejected_no_cambian_el_contexto():
    base = _base(objective=Objective.BUY)
    c = reducir(base, _lote(AfirmacionTurnOnly(campo=F.BUDGET_MAX, motivo="pregunta"),
                            AfirmacionRejected(campo=None, motivo="hogar")), T0)
    assert _canonico(c) == _canonico(base)


def test_R4_un_rejected_no_arrastra_la_durable_del_mismo_mensaje():
    """C5 llega hasta aquí: la mitad prohibida no puede costar la declarada."""
    c = reducir(_base(), _lote(AfirmacionRejected(campo=None, motivo="dos niños"),
                               _dur(_BUD)), T0)
    assert c.financial.budget_max.amount == Decimal(120000)


# ══ R5 · AMBIGUOUS abre pregunta y NO borra ═════════════════════════════════════════


def test_R5_una_ambiguedad_NO_borra_el_valor_previo():
    """LA REGLA QUE MÁS IMPORTA DE ESTA CAPA.

    Sólo una retractación explícita autorizó los `Clear*`. Convertir *"no estoy seguro de lo
    que dijo"* en *"bórralo"* perdería estado que el usuario declaró, por una duda del
    intérprete — y sería un `Clear` clandestino que nadie autorizó.
    """
    base = _base(financial={"budget_max": {"amount": "120000", "currency": "USD"}})
    c = reducir(base, _lote(_amb(F.BUDGET_MAX)), T0)

    assert c.financial.budget_max.amount == Decimal(120000)
    assert [q.about_field for q in c.unresolved_questions] == ["financial.budget_max"]


def test_R5_una_ambiguedad_sin_valor_previo_solo_abre_la_pregunta():
    c = reducir(_base(), _lote(_amb(F.BEDROOMS_MIN)), T0)
    assert c.property_requirements.bedrooms_min is None
    assert [q.about_field for q in c.unresolved_questions] == \
           ["property_requirements.bedrooms_min"]


def test_R5_una_durable_RESUELVE_la_pregunta_abierta_de_su_campo():
    conDuda = reducir(_base(), _lote(_amb(F.BUDGET_MAX)), T0)
    assert conDuda.unresolved_questions

    resuelto = reducir(conDuda, _lote(_dur(_BUD), mid="m-2"), T0)
    assert resuelto.unresolved_questions == ()
    assert resuelto.financial.budget_max.amount == Decimal(120000)


def test_R5_una_durable_no_cierra_la_pregunta_de_OTRO_campo():
    conDuda = reducir(_base(), _lote(_amb(F.BEDROOMS_MIN)), T0)
    resuelto = reducir(conDuda, _lote(_dur(_BUD), mid="m-2"), T0)
    assert [q.about_field for q in resuelto.unresolved_questions] == \
           ["property_requirements.bedrooms_min"]


def test_R5_la_misma_pregunta_no_se_DUPLICA():
    uno = reducir(_base(), _lote(_amb(F.BUDGET_MAX)), T0)
    dos = reducir(uno, _lote(_amb(F.BUDGET_MAX), mid="m-2"), T0)
    assert len(dos.unresolved_questions) == 1


# ══ R6 · la pregunta es determinista, no la prosa del modelo ════════════════════════


def test_R6_el_motivo_del_modelo_NO_se_persiste_como_la_pregunta():
    """Si el texto del modelo fuera la pregunta, dos procesamientos del mismo mensaje darían
    estados distintos y la idempotencia lo denunciaría con razón. La pregunta es del producto.
    """
    a = reducir(_base(), _lote(AfirmacionAmbiguous(campo=F.BUDGET_MAX,
                                                   motivo="dijo dólares, no USD")), T0)
    b = reducir(_base(), _lote(AfirmacionAmbiguous(campo=F.BUDGET_MAX,
                                                   motivo="otra redacción cualquiera")), T0)
    assert a.unresolved_questions == b.unresolved_questions
    assert "dólares" not in a.unresolved_questions[0].question


@pytest.mark.parametrize("campo", list(BuyerFieldV0))
def test_R6_toda_dimension_tiene_pregunta_determinista(campo):
    c = reducir(_base(), _lote(_amb(campo)), T0)
    assert c.unresolved_questions[0].question.strip()


def test_R6_la_pregunta_se_deriva_DEL_CAMPO_no_es_una_constante():
    """Lo escribió la mutación Q3, no el diseño: sustituir el texto por otra CONSTANTE dejaba
    la suite verde. Los asserts de arriba comprueban que la pregunta es determinista y que no
    lleva la prosa del modelo — ninguno comprueba que dependa de la dimensión.

    R6 dice "una formulación determinista POR `BuyerFieldV0`". Una constante también es
    determinista, y no sirve para nada: preguntaría por el presupuesto cuando falta el área.
    """
    preguntas = {
        campo: reducir(_base(), _lote(_amb(campo)), T0).unresolved_questions[0].question
        for campo in BuyerFieldV0
    }
    assert len(set(preguntas.values())) == len(BuyerFieldV0), (
        f"dimensiones distintas comparten pregunta: {preguntas}")


# ══ R7 · procedencia ════════════════════════════════════════════════════════════════


def test_R7_la_ruta_de_la_evidencia_sale_del_CONTRATO_no_del_modelo():
    c = reducir(_base(), _lote(_dur(SetObjective(objective=Objective.BUY)), _dur(_BUD)), T0)
    assert sorted(fe.field for fe in c.field_evidence) == \
           ["financial.budget_max", "objective"]


def test_R7_varias_rutas_pueden_citar_el_MISMO_mensaje():
    """§3: un mensaje puede justificar tres campos, y el contrato lo admite."""
    c = reducir(_base(), _lote(_dur(SetObjective(objective=Objective.BUY)), _dur(_BUD),
                               _dur(SetBedroomsMin(bedrooms_min=2))), T0)
    assert len(c.field_evidence) == 3
    assert {fe.evidence.source_id for fe in c.field_evidence} == {"m-1"}


def test_R7_al_actualizar_un_campo_su_evidencia_se_REEMPLAZA_no_se_acumula():
    """Dejar las dos afirmaría que una declaración vieja respalda el valor nuevo. La revisión
    histórica ya conserva la anterior junto al valor que sí sostenía."""
    uno = reducir(_base(), _lote(_dur(_BUD)), T0)
    dos = reducir(uno, _lote(_dur(SetBudgetMax(amount=Decimal(90000), currency=USD)),
                             mid="m-2"), T0)

    evidencia = [fe for fe in dos.field_evidence if fe.field == "financial.budget_max"]
    assert len(evidencia) == 1
    assert evidencia[0].evidence.source_id == "m-2"


def test_R7_la_evidencia_no_inventa_observed_at():
    """`observed_at=None` es una afirmación —"el origen no dice de cuándo es"— y no un hueco.
    Ponerle `retrieved_at` sería la mentira que `EvidenceRefV0` documenta como el error de
    E0.3: no tenemos timestamp del evento del mensaje."""
    c = reducir(_base(), _lote(_dur(_BUD)), T0)
    assert c.field_evidence[0].evidence.observed_at is None
    assert c.field_evidence[0].evidence.retrieved_at == T0


# ══ R-IDEMP-1 · el replay ═══════════════════════════════════════════════════════════


def test_IDEMP_reducir_dos_veces_el_MISMO_mensaje_da_el_mismo_estado_canonico():
    """EL TEST QUE JUSTIFICA EL PREFLIGHT. Antes de R-IDEMP-1 esto fallaba: `uuid4()` y el
    reloj hacían divergir el canónico, y el store habría levantado
    `BuyerIdempotencyConflict` acusando a un extractor que sí era determinista.

    El segundo `retrieved_at` es DISTINTO a propósito: un reintento ocurre después, y no
    hace falta que ese instante sea estable — hace falta que sea verdadero y que no se
    confunda con estado del comprador.
    """
    lote = _lote(_dur(SetObjective(objective=Objective.BUY)), _dur(_BUD))
    a = reducir(_base(), lote, T0)
    b = reducir(_base(), lote, T0 + dt.timedelta(seconds=37))

    assert _canonico(a) == _canonico(b)


def test_IDEMP_el_mismo_mensaje_con_OTRA_interpretacion_SI_diverge():
    """La excepción no puede cegar el caso que la idempotencia existe para cazar."""
    a = reducir(_base(), _lote(_dur(SetObjective(objective=Objective.BUY))), T0)
    b = reducir(_base(), _lote(_dur(SetObjective(objective=Objective.RENT))), T0)
    assert _canonico(a) != _canonico(b)


def test_IDEMP_otro_mensaje_SI_diverge():
    a = reducir(_base(), _lote(_dur(_BUD), mid="m-1"), T0)
    b = reducir(_base(), _lote(_dur(_BUD), mid="m-2"), T0)
    assert _canonico(a) != _canonico(b)


def test_IDEMP_el_evidence_id_es_determinista_por_buyer_mensaje_y_ruta():
    ident = evidence_id_determinista
    assert ident("b-1", "m-1", "objective") == ident("b-1", "m-1", "objective")
    assert ident("b-1", "m-1", "objective") != ident("b-1", "m-1", "financial.budget_max")
    assert ident("b-1", "m-1", "objective") != ident("b-2", "m-1", "objective")
    assert ident("b-1", "m-1", "objective") != ident("b-1", "m-2", "objective")


def test_IDEMP_el_evidence_id_NO_depende_del_valor():
    """Deliberado: si un replay produjera otro valor, queremos el MISMO id de evidencia y un
    contexto distinto, para que la divergencia se vea en vez de esconderse detrás de dos
    identificadores."""
    a = reducir(_base(), _lote(_dur(SetObjective(objective=Objective.BUY))), T0)
    b = reducir(_base(), _lote(_dur(SetObjective(objective=Objective.RENT))), T0)
    assert a.field_evidence[0].evidence.evidence_id == b.field_evidence[0].evidence.evidence_id
    assert _canonico(a) != _canonico(b)


# ══ pureza ══════════════════════════════════════════════════════════════════════════


def test_el_reducer_no_usa_reloj_ni_azar_ni_base():
    import ast
    import pathlib

    from app.buyer import reductor

    arbol = ast.parse(pathlib.Path(reductor.__file__).read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        cuerpo = getattr(nodo, "body", None)
        if isinstance(cuerpo, list) and cuerpo:
            p = cuerpo[0]
            if isinstance(p, ast.Expr) and isinstance(p.value, ast.Constant) \
                    and isinstance(p.value.value, str):
                cuerpo.pop(0)
    codigo = ast.unparse(arbol)

    for prohibido in ("now(", "utcnow", "uuid4", "random", "AsyncSessionLocal", "sqlalchemy",
                      "anexar_revision", "anthropic"):
        assert prohibido not in codigo, f"el reducer usa {prohibido}"


def test_el_lote_completo_produce_UNA_revision_con_los_tres_hechos():
    """§3: un mensaje es como mucho una revisión, con todos sus hechos dentro."""
    c = reducir(_base(), _lote(_dur(SetObjective(objective=Objective.BUY)), _dur(_BUD),
                               _dur(SetBedroomsMin(bedrooms_min=2))), T0)
    assert c.objective is Objective.BUY
    assert c.financial.budget_max.amount == Decimal(120000)
    assert c.property_requirements.bedrooms_min == 2
