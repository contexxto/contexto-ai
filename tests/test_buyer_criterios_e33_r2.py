"""F3-E3.3-R2 · lo que la revisión adversarial post-merge encontró en E3.3, cerrado.

Cada prueba reproduce un escenario que un revisor independiente ejecutó contra `main =
da82d42` y que un segundo agente reprodujo por su cuenta. Los identificadores (#NN) son los
del informe de la revisión.

```
R2-1  una rigidez no endurece el valor VIEJO si el nuevo del mismo mensaje quedó en duda   #1 #5
R2-2  tras un retiro, un valor redeclarado nace sin la rigidez retirada          #2 #11 #20 #23
R2-3  el vocabulario de dimensión es el NOMBRE de la dimensión, no "máximo" ni "área"  #7 #17 #24
R2-4  negación, modalidad y voz ajena bloquean — también a través de una coma           #8
R2-5  una corrección que la guarda no acredita compite: no gana la polaridad retirada     #6
R2-6  la rigidez sin valor abre la pregunta de su dimensión                             #13
R2-7  sólo se re-proyecta lo que el lote toca (bases anteriores a E3.3)                 #3 #12
R2-8  el papel de una evidencia se lee de un código estable, no de la prosa         #15 #18
R2-9  ningún log repite lo que el modelo leyó del mensaje                               #16
R2-10 el puente de adyacencia: "máximo 900 USD, es innegociable"                     #14 #25
R2-11 concurrencia: QUIÉN sostiene la rigidez también es estado de la ruta              #19
R2-12 la coletilla "¿no?" no se traga la afirmación                                    #21
R2-13 "ideal" adjetivo no es flexibilidad                                               #10
R2-14 R8 y R12 sobre el resultado completo, arrastrados incluidos                        #4
```
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from decimal import Decimal

import pytest

from app.buyer import actualizador as act
from app.buyer.actualizador import EstadoActualizacion, actualizar, rutas_divergentes
from app.buyer.boundary import (
    CAMPOS_CON_CRITERIO, BuyerCurrencyV0, BuyerFieldV0, ClearBudgetMax, DeclaracionRigidezV0,
    Disposicion, RigidezV0, SetAreaM2Min, SetBedroomsMin, SetBudgetMax,
    SetPetsRequired,
)
from app.buyer.extractor import (
    AfirmacionRejected, RigidezNoAcreditada, TraduccionNoAutorizada, autorizar_rigidez,
    autorizar_rigidez_por_adyacencia,
)
from app.buyer.interprete import PropuestaRigidezV0, PropuestaV0, _parsear, interpretar
from app.buyer.mensaje import IdentifiedUserMessage
from app.buyer.reductor import (
    _CODIGO_RIGIDEZ, _METODOLOGIA_RIGIDEZ, ReduccionImposible, reducir, rigidez_de_evidencia,
)
from app.buyer.store import _canonico
from app.contracts.buyer_v0 import BuyerContextV0, CriterionStatus

T0 = dt.datetime(2026, 9, 23, 12, 0, tzinfo=dt.timezone.utc)
USD = BuyerCurrencyV0.USD
F = BuyerFieldV0
E, FL = RigidezV0.ESTRICTA, RigidezV0.FLEXIBLE


def _msg(texto, mid):
    return IdentifiedUserMessage(message_id=mid, text=texto)


def _dur(m):
    return PropuestaV0(disposicion=Disposicion.DURABLE, mutacion=m, motivo="declarado")


def _amb(campo):
    return PropuestaV0(disposicion=Disposicion.AMBIGUOUS, campo=campo, motivo="no exacto")


def _rig(campo, rigidez, motivo="declarado"):
    return PropuestaRigidezV0(campo=campo, rigidez=rigidez, motivo=motivo)


def _vacio():
    return BuyerContextV0(buyer_id="b-1", updated_at=T0)


def _paso(contexto, texto, *propuestas, mid, cuando=T0):
    return reducir(contexto, interpretar(_msg(texto, mid), list(propuestas)), cuando)


def _lista(contexto, campo):
    for lista in ("hard_constraints", "soft_preferences"):
        for c in getattr(contexto, lista):
            if c.criterion_id == campo.value:
                return lista, c
    return None, None


def _preguntas(contexto):
    return sorted(q.about_field for q in contexto.unresolved_questions)


def _ok(texto, campo, rigidez):
    try:
        autorizar_rigidez(DeclaracionRigidezV0(campo=campo, rigidez=rigidez), texto)
        return True
    except TraduccionNoAutorizada:
        return False


def _poblada():
    """A mitad de conversación: las cuatro dimensiones con valor, todas en soft."""
    return _paso(_vacio(), "máximo 900 USD, al menos 2 dormitorios, mínimo 80 m2, "
                           "necesito que acepten mascotas",
                 _dur(SetBudgetMax(amount=Decimal(900), currency=USD)),
                 _dur(SetBedroomsMin(bedrooms_min=2)), _dur(SetAreaM2Min(area_m2_min=80.0)),
                 _dur(SetPetsRequired()), mid="m-0")


# ══ R2-1 · la rigidez no se pega al valor que la persona abandonaba ═════════════════


@pytest.mark.parametrize("texto, propuestas", [
    ("ahora puedo llegar hasta mil dólares, el presupuesto es innegociable",
     [_dur(SetBudgetMax(amount=Decimal(1000), currency=USD)), _rig(F.BUDGET_MAX, E)]),
    ("máximo 900 USD o 1000 USD, el presupuesto es innegociable",
     [_dur(SetBudgetMax(amount=Decimal(900), currency=USD)),
      _dur(SetBudgetMax(amount=Decimal(1000), currency=USD)), _rig(F.BUDGET_MAX, E)]),
])
def test_R2_1_una_rigidez_NO_endurece_el_valor_viejo_si_el_nuevo_quedo_en_duda(texto,
                                                                                propuestas):
    base = _paso(_vacio(), "mi presupuesto máximo es 800 USD",
                 _dur(SetBudgetMax(amount=Decimal(800), currency=USD)), mid="m-1")
    c = _paso(base, texto, *propuestas, mid="m-2")

    assert c.hard_constraints == (), "el 800 que la persona abandonaba quedó innegociable"
    lista, criterio = _lista(c, F.BUDGET_MAX)
    assert lista == "soft_preferences" and criterio.value == 800
    assert "financial.budget_max" in _preguntas(c)


def test_R2_1_con_el_valor_nuevo_ACREDITADO_la_rigidez_si_aplica():
    """El control: el mismo mensaje con la cifra acreditable endurece el valor NUEVO."""
    base = _paso(_vacio(), "mi presupuesto máximo es 800 USD",
                 _dur(SetBudgetMax(amount=Decimal(800), currency=USD)), mid="m-1")
    c = _paso(base, "ahora mi presupuesto máximo es 1000 USD, el presupuesto es innegociable",
              _dur(SetBudgetMax(amount=Decimal(1000), currency=USD)), _rig(F.BUDGET_MAX, E),
              mid="m-2")
    lista, criterio = _lista(c, F.BUDGET_MAX)
    assert lista == "hard_constraints" and criterio.value == 1000
    assert _preguntas(c) == []


# ══ R2-2 · el retiro reinicia la rigidez ═════════════════════════════════════════════


def test_R2_2_tras_un_retiro_el_valor_redeclarado_nace_SOFT():
    c = _paso(_vacio(), "máximo 900 USD, el presupuesto es innegociable",
              _dur(SetBudgetMax(amount=Decimal(900), currency=USD)), _rig(F.BUDGET_MAX, E),
              mid="m-1")
    c = _paso(c, "ya no tengo tope de presupuesto", _dur(ClearBudgetMax()), mid="m-2")
    assert _lista(c, F.BUDGET_MAX)[0] == "hard_constraints"      # el retirado documenta

    c = _paso(c, "mi presupuesto máximo es 1200 USD",
              _dur(SetBudgetMax(amount=Decimal(1200), currency=USD)), mid="m-3")
    lista, criterio = _lista(c, F.BUDGET_MAX)
    assert lista == "soft_preferences", "la rigidez de un requisito RETIRADO revivió sola"
    assert criterio.status is CriterionStatus.ACTIVE and criterio.value == 1200
    assert [(e.source_id, rigidez_de_evidencia(e)) for e in criterio.evidence] == [
        ("m-3", None)]


def test_R2_2_si_lo_vuelve_a_declarar_estricto_si_nace_HARD():
    c = _paso(_vacio(), "máximo 900 USD, el presupuesto es innegociable",
              _dur(SetBudgetMax(amount=Decimal(900), currency=USD)), _rig(F.BUDGET_MAX, E),
              mid="m-1")
    c = _paso(c, "ya no tengo tope de presupuesto", _dur(ClearBudgetMax()), mid="m-2")
    c = _paso(c, "mi presupuesto máximo es 1200 USD, el presupuesto es innegociable",
              _dur(SetBudgetMax(amount=Decimal(1200), currency=USD)), _rig(F.BUDGET_MAX, E),
              mid="m-3")
    assert _lista(c, F.BUDGET_MAX)[0] == "hard_constraints"


def test_R2_2_R10_sigue_valiendo_para_un_criterio_VIGENTE():
    """El límite del arreglo: cambiar el número sin retirar conserva la rigidez."""
    c = _paso(_vacio(), "máximo 900 USD, el presupuesto es innegociable",
              _dur(SetBudgetMax(amount=Decimal(900), currency=USD)), _rig(F.BUDGET_MAX, E),
              mid="m-1")
    c = _paso(c, "mejor máximo 950 USD",
              _dur(SetBudgetMax(amount=Decimal(950), currency=USD)), mid="m-2")
    assert _lista(c, F.BUDGET_MAX)[0] == "hard_constraints"


# ══ R2-3 · el vocabulario de dimensión ══════════════════════════════════════════════


_FRASES_QUE_NO_NOMBRAN_EL_REQUISITO = [
    ("un máximo de 20 minutos al trabajo es innegociable", F.BUDGET_MAX),
    ("el límite de ruido es innegociable", F.BUDGET_MAX),
    ("que el edificio tenga máximo 5 pisos es obligatorio", F.BUDGET_MAX),
    ("soy católico, así que máximo a 10 minutos de la iglesia sí o sí", F.BUDGET_MAX),
    ("tenemos dos niños, máximo 15 minutos al colegio es indispensable", F.BUDGET_MAX),
    ("tengo 70 años, máximo un piso de escaleras es indispensable", F.BUDGET_MAX),
    ("un cuarto de oración sí o sí", F.BEDROOMS_MIN),
    ("un cuarto de servicio es indispensable", F.BEDROOMS_MIN),
    ("tenemos tres niños, el cuarto de juegos es indispensable", F.BEDROOMS_MIN),
    ("tenemos dos niños, un área de juegos es indispensable", F.AREA_M2_MIN),
    ("mi esposa usa silla de ruedas, un área de circulación amplia es obligatoria",
     F.AREA_M2_MIN),
    ("el área verde es indispensable", F.AREA_M2_MIN),
]


@pytest.mark.parametrize("texto, campo", _FRASES_QUE_NO_NOMBRAN_EL_REQUISITO)
def test_R2_3_la_guarda_NO_acredita_si_no_se_nombra_el_requisito(texto, campo):
    assert not _ok(texto, campo, E)


@pytest.mark.parametrize("texto, campo", _FRASES_QUE_NO_NOMBRAN_EL_REQUISITO)
def test_R2_3_un_proponente_HOSTIL_sobre_una_base_POBLADA_no_endurece_nada(texto, campo):
    """La prueba que faltaba: con valores ya declarados, que es lo normal a mitad de
    conversación. La hostil de E3.3 corría sobre una base vacía y no ejercitaba la guarda."""
    hostil = [_rig(c, E) for c in CAMPOS_CON_CRITERIO]
    c = _paso(_poblada(), texto, *hostil, mid="m-1")
    assert c.hard_constraints == ()


@pytest.mark.parametrize("texto, campo", [
    ("el presupuesto es innegociable", F.BUDGET_MAX),
    ("los dormitorios son indispensables", F.BEDROOMS_MIN),
    ("las habitaciones son indispensables", F.BEDROOMS_MIN),
    ("los cuartos son indispensables", F.BEDROOMS_MIN),
    ("los metros cuadrados son innegociables", F.AREA_M2_MIN),
    ("la superficie es obligatoria", F.AREA_M2_MIN),
    ("las mascotas son indispensables", F.PETS_REQUIRED),
])
def test_R2_3_nombrar_el_requisito_SIGUE_acreditando(texto, campo):
    assert _ok(texto, campo, E)


# ══ R2-4 · negación, modalidad y voz ajena ══════════════════════════════════════════


@pytest.mark.parametrize("texto, campo", [
    ("nunca dije que el presupuesto fuera innegociable", F.BUDGET_MAX),
    ("jamás dije que los dormitorios fueran indispensables", F.BEDROOMS_MIN),
    ("nadie dijo que el presupuesto sea innegociable", F.BUDGET_MAX),
    ("no diría que, hoy por hoy, los dormitorios sean indispensables", F.BEDROOMS_MIN),
    ("antes el presupuesto era innegociable", F.BUDGET_MAX),
    ("mi esposo dice que el presupuesto es innegociable", F.BUDGET_MAX),
    ("me pregunto si los dormitorios son indispensables", F.BEDROOMS_MIN),
    ("¿es obligatorio que acepten mascotas", F.PETS_REQUIRED),
    ("no creo, la verdad, que el presupuesto sea flexible", F.BUDGET_MAX),
    ("si el presupuesto fuera flexible buscaría en Cumbayá", F.BUDGET_MAX),
    ("mi presupuesto es poco flexible", F.BUDGET_MAX),
    ("mi presupuesto es nada negociable", F.BUDGET_MAX),
    ("quería saber si el presupuesto es negociable", F.BUDGET_MAX),
])
def test_R2_4_ni_estricta_ni_flexible_se_acreditan(texto, campo):
    for r in (E, FL):
        assert not _ok(texto, campo, r), (texto, r)


@pytest.mark.parametrize("texto, rigidez", [
    ("Sí, el presupuesto es innegociable", E),
    ("No, el presupuesto es flexible", FL),
    ("Bueno, el presupuesto es flexible", FL),
])
def test_R2_4_una_particula_sola_no_niega_lo_que_sigue(texto, rigidez):
    """Responder "sí" o "no" antes de la coma no condiciona ni niega la cláusula siguiente."""
    assert _ok(texto, F.BUDGET_MAX, rigidez)


def test_R2_4_ESTRICTA_exige_la_ORACION_entera_limpia_y_la_otra_oracion_no_cuenta():
    """R2b. Para endurecer, ninguna parte de la oración puede negar, condicionar o citar —ni
    antes ni después del marcador, ni tras una «y» o unos dos puntos—. Es un falso negativo
    aceptado en «no tengo mascotas, pero…»: la persona puede decirlo en otra oración."""
    assert not _ok("no tengo mascotas, pero el presupuesto es innegociable", F.BUDGET_MAX, E)
    assert _ok("No tengo mascotas. El presupuesto es innegociable", F.BUDGET_MAX, E)
    assert _ok("no tengo carro. El presupuesto es flexible", F.BUDGET_MAX, FL)


# ══ R2-5 · la corrección que la guarda no acredita compite ═══════════════════════════


@pytest.mark.parametrize("texto", [
    "el presupuesto es innegociable... no, perdón, es flexible",
    "antes el presupuesto era innegociable, pero ahora ya es flexible",
])
def test_R2_5_la_polaridad_retirada_NO_gana_sola(texto):
    base = _paso(_vacio(), "máximo 900 USD",
                 _dur(SetBudgetMax(amount=Decimal(900), currency=USD)), mid="m-1")
    c = _paso(base, texto, _rig(F.BUDGET_MAX, E), _rig(F.BUDGET_MAX, FL), mid="m-2")
    assert c.hard_constraints == (), "ganó la rigidez que la persona retiró"


def test_R2_5_la_no_acreditada_deja_su_REJECTED_y_no_crea_estado():
    lote = interpretar(_msg("es flexible", "m-1"), [_rig(F.BUDGET_MAX, FL)])
    assert lote.rigideces == ()
    assert [(type(a), a.campo) for a in lote.afirmaciones] == [
        (AfirmacionRejected, F.BUDGET_MAX)]


def test_R2_5_la_misma_polaridad_una_acreditada_y_otra_no_es_repeticion():
    lote = interpretar(_msg("el presupuesto es innegociable, innegociable de verdad", "m-1"),
                       [_rig(F.BUDGET_MAX, E), _rig(F.BUDGET_MAX, E)])
    assert lote.rigideces == (DeclaracionRigidezV0(campo=F.BUDGET_MAX, rigidez=E),)


def test_R2_5_la_corregida_ACREDITADA_sigue_ganando():
    lote = interpretar(
        _msg("el presupuesto es innegociable. perdón, en realidad el presupuesto es flexible",
             "m-1"), [_rig(F.BUDGET_MAX, E), _rig(F.BUDGET_MAX, FL)])
    assert lote.rigideces == (DeclaracionRigidezV0(campo=F.BUDGET_MAX, rigidez=FL),)


def test_R2_5_RigidezNoAcreditada_no_admite_una_dimension_fuera_de_la_whitelist():
    with pytest.raises(Exception):
        RigidezNoAcreditada(campo=F.OBJECTIVE, rigidez=E, motivo="x")


# ══ R2-6 · rigidez sin valor abre la pregunta ═══════════════════════════════════════


def test_R2_6_rigidez_sin_valor_abre_la_pregunta_de_su_dimension():
    c = _paso(_vacio(), "el presupuesto es flexible", _rig(F.BUDGET_MAX, FL), mid="m-1")
    assert c.hard_constraints == () and c.soft_preferences == ()
    assert _preguntas(c) == ["financial.budget_max"]


def test_R2_6_la_respuesta_cierra_la_pregunta_y_entra_en_soft():
    c = _paso(_vacio(), "los dormitorios son indispensables", _rig(F.BEDROOMS_MIN, E),
              mid="m-1")
    c = _paso(c, "al menos 2 dormitorios", _dur(SetBedroomsMin(bedrooms_min=2)), mid="m-2")
    assert _preguntas(c) == []
    assert _lista(c, F.BEDROOMS_MIN)[0] == "soft_preferences"


def test_R2_6_por_el_orquestador_ya_no_es_NO_OP(store):
    r = _actualizar(_msg("el presupuesto es flexible", "m-1"), _rig(F.BUDGET_MAX, FL))
    assert r.estado is EstadoActualizacion.CREADA
    assert _preguntas(r.contexto) == ["financial.budget_max"]


# ══ R2-7 · bases anteriores a E3.3 ══════════════════════════════════════════════════


def _legada():
    """Una revisión como las que escribía el reductor de 5be2bab6: valores y procedencia,
    ningún criterio."""
    c = _poblada()
    return c.model_copy(update={"hard_constraints": (), "soft_preferences": ()})


def test_R2_7_un_TURN_ONLY_sobre_una_base_legada_sigue_siendo_NO_OP():
    base = _legada()
    c = _paso(base, "gracias",
              PropuestaV0(disposicion=Disposicion.TURN_ONLY, motivo="cortesía"), mid="m-1")
    assert _canonico(c) == _canonico(base)


def test_R2_7_tocar_UNA_dimension_proyecta_SOLO_esa():
    c = _paso(_legada(), "al menos 3 dormitorios", _dur(SetBedroomsMin(bedrooms_min=3)),
              mid="m-1")
    assert [k.criterion_id for k in c.soft_preferences] == ["bedrooms_min"]


def test_R2_7_escrituras_DISJUNTAS_sobre_una_base_legada_se_REBASAN(store):
    store.revisiones.append(_legada().model_copy(update={"context_revision": 0}))
    store.por_mensaje["m-0"] = 0
    _actualizar(_msg("al menos 3 dormitorios", "m-A"), _dur(SetBedroomsMin(bedrooms_min=3)))

    _leer_rancio(store, 0)
    r = _actualizar(_msg("mi presupuesto máximo es 1000 USD", "m-B"),
                    _dur(SetBudgetMax(amount=Decimal(1000), currency=USD)))

    assert r.estado is EstadoActualizacion.REBASEADA, r.motivo
    assert r.contexto.financial.budget_max.amount == Decimal(1000)
    assert r.contexto.property_requirements.bedrooms_min == 3


# ══ R2-8 · el papel de la evidencia por código ══════════════════════════════════════


def test_R2_8_los_codigos_de_rigidez_son_IDENTIFICADORES_PERSISTIDOS():
    """Si esto falla, alguien cambió un código que ya vive en revisiones persistidas.
    Hace falta una migración, no editar este test."""
    assert _CODIGO_RIGIDEZ == {E: "[rigidez:estricta]", FL: "[rigidez:flexible]"}
    for rigidez, metodologia in _METODOLOGIA_RIGIDEZ.items():
        assert metodologia.startswith(_CODIGO_RIGIDEZ[rigidez])


def test_R2_8_corregir_la_PROSA_de_la_metodologia_no_congela_la_memoria():
    c = _paso(_vacio(), "máximo 900 USD, el presupuesto es innegociable",
              _dur(SetBudgetMax(amount=Decimal(900), currency=USD)), _rig(F.BUDGET_MAX, E),
              mid="m-1")
    duro = c.hard_constraints[0]
    reescrita = tuple(
        e.model_copy(update={"methodology": "[rigidez:estricta] otra redacción, con tildes"})
        if rigidez_de_evidencia(e) else e for e in duro.evidence)
    c = c.model_copy(update={"hard_constraints": (duro.model_copy(
        update={"evidence": reescrita}),)})
    c = _paso(c, "al menos 2 dormitorios", _dur(SetBedroomsMin(bedrooms_min=2)), mid="m-2")
    assert _lista(c, F.BUDGET_MAX)[0] == "hard_constraints"


# ══ R2-9 · logs sin el input ════════════════════════════════════════════════════════


def test_R2_9_ningun_descarte_registra_lo_que_el_modelo_leyo(caplog):
    """El centinela va en el VALOR que no valida: es lo que el `ValidationError` repite en
    `input_value`. Ponerlo en un campo válido haría la prueba vacua —la primera versión lo
    era, y la mutación N12 sobrevivió—."""
    centinela = "Calle-Centinela-Secreta-4471"
    with caplog.at_level(logging.WARNING, logger="app.buyer.interprete"):
        salida = _parsear({
            "afirmaciones": [{"disposicion": "durable", "motivo": "x",
                              "mutacion": {"tipo": "set_budget_max", "amount": centinela,
                                           "currency": "USD"}}],
            "rigideces": [{"campo": centinela, "rigidez": "estricta", "motivo": "x"}],
        })
    assert salida == ()
    assert len(caplog.records) == 2, "el control necesita que los dos descartes se registren"
    assert centinela not in caplog.text


def test_R2_9_el_control_del_centinela_NO_es_vacuo():
    """Sin el filtro, el error de Pydantic SÍ repite el centinela. Si esto dejara de ser
    cierto, la prueba de arriba no probaría nada."""
    from pydantic import ValidationError

    centinela = "Calle-Centinela-Secreta-4471"
    try:
        PropuestaRigidezV0.model_validate({"campo": centinela, "rigidez": "estricta",
                                           "motivo": "x"})
    except ValidationError as e:
        assert centinela in str(e)
    else:
        pytest.fail("se esperaba un ValidationError")


# ══ R2-10 · el puente de adyacencia ═════════════════════════════════════════════════


@pytest.mark.parametrize("texto, mutacion, campo, rigidez", [
    ("máximo 900 USD, es innegociable",
     SetBudgetMax(amount=Decimal(900), currency=USD), F.BUDGET_MAX, E),
    ("máximo 900 USD y es innegociable",
     SetBudgetMax(amount=Decimal(900), currency=USD), F.BUDGET_MAX, E),
    ("al menos 2 dormitorios, sí o sí", SetBedroomsMin(bedrooms_min=2), F.BEDROOMS_MIN, E),
    ("necesito al menos 2 dormitorios sí o sí", SetBedroomsMin(bedrooms_min=2),
     F.BEDROOMS_MIN, E),
])
def test_R2_10_el_marcador_SOLO_tras_el_valor_se_acredita(texto, mutacion, campo, rigidez):
    autorizar_rigidez_por_adyacencia(DeclaracionRigidezV0(campo=campo, rigidez=rigidez),
                                     mutacion, texto)


@pytest.mark.parametrize("texto, mutacion, campo", [
    ("máximo 900 USD, la ubicación es indispensable",       # sin palabra sucia: sólo el
     SetBudgetMax(amount=Decimal(900), currency=USD), F.BUDGET_MAX),  # relleno lo frena
    ("máximo 900 USD, mi hijo es indispensable",
     SetBudgetMax(amount=Decimal(900), currency=USD), F.BUDGET_MAX),
    ("máximo 900 USD, al menos 2 dormitorios, es indispensable",
     SetBudgetMax(amount=Decimal(900), currency=USD), F.BUDGET_MAX),
    ("máximo 900 USD, ¿es innegociable?",
     SetBudgetMax(amount=Decimal(900), currency=USD), F.BUDGET_MAX),
    ("máximo 900 USD, nunca innegociable",
     SetBudgetMax(amount=Decimal(900), currency=USD), F.BUDGET_MAX),
    ("es innegociable, máximo 900 USD",
     SetBudgetMax(amount=Decimal(900), currency=USD), F.BUDGET_MAX),
    # R2b · no cruza oraciones: la del medio podía ser una pregunta que se llevaba el marcador
    ("Máximo 900 USD. Es innegociable.",
     SetBudgetMax(amount=Decimal(900), currency=USD), F.BUDGET_MAX),
    ("Máximo 900 USD. ¿Tienen algo de 3 dormitorios? Es indispensable.",
     SetBudgetMax(amount=Decimal(900), currency=USD), F.BUDGET_MAX),
    # R2b · la oración del valor tiene que estar limpia también para el puente
    ("mi esposo dice que máximo 900 USD, es innegociable",
     SetBudgetMax(amount=Decimal(900), currency=USD), F.BUDGET_MAX),
    ("si me aprueban el crédito, máximo 1200 USD, es innegociable",
     SetBudgetMax(amount=Decimal(1200), currency=USD), F.BUDGET_MAX),
    # R2b · «lo que es indispensable:» apunta a lo que viene DESPUÉS
    ("Máximo 900 USD, lo que es indispensable: al menos 2 dormitorios",
     SetBudgetMax(amount=Decimal(900), currency=USD), F.BUDGET_MAX),
])
def test_R2_10_el_puente_NO_cruza_lo_que_no_es_solo_marcador(texto, mutacion, campo):
    with pytest.raises(TraduccionNoAutorizada):
        autorizar_rigidez_por_adyacencia(DeclaracionRigidezV0(campo=campo, rigidez=E),
                                         mutacion, texto)


def test_R2_10_el_puente_endurece_la_dimension_ADYACENTE_y_no_otra():
    c = _paso(_vacio(), "máximo 900 USD, al menos 2 dormitorios, es indispensable",
              _dur(SetBudgetMax(amount=Decimal(900), currency=USD)),
              _dur(SetBedroomsMin(bedrooms_min=2)),
              _rig(F.BUDGET_MAX, E), _rig(F.BEDROOMS_MIN, E), mid="m-1")
    assert [k.criterion_id for k in c.hard_constraints] == ["bedrooms_min"]
    assert [k.criterion_id for k in c.soft_preferences] == ["budget_max"]


def test_R2_10_sin_valor_acreditado_detras_no_hay_puente():
    """"Tenemos dos niños, es indispensable": ningún valor acreditado en el mensaje."""
    c = _paso(_poblada(), "tenemos dos niños, es indispensable",
              _dur(SetBedroomsMin(bedrooms_min=2)), *[_rig(k, E) for k in CAMPOS_CON_CRITERIO],
              mid="m-1")
    assert c.hard_constraints == ()


def test_R2_10_el_ejemplo_que_ensena_el_prompt_PASA_la_guarda():
    """#14: el ejemplo positivo de la regla 9 no pasaba la guarda."""
    c = _paso(_vacio(), "máximo 900 USD y es innegociable",
              _dur(SetBudgetMax(amount=Decimal(900), currency=USD)), _rig(F.BUDGET_MAX, E),
              mid="m-1")
    assert [k.criterion_id for k in c.hard_constraints] == ["budget_max"]


def test_R2_10_el_puente_no_se_apoya_en_un_retiro_ni_en_otra_dimension():
    with pytest.raises(TraduccionNoAutorizada):
        autorizar_rigidez_por_adyacencia(DeclaracionRigidezV0(campo=F.BUDGET_MAX, rigidez=E),
                                         ClearBudgetMax(), "ya no tengo tope, es innegociable")
    with pytest.raises(TraduccionNoAutorizada):
        autorizar_rigidez_por_adyacencia(DeclaracionRigidezV0(campo=F.BUDGET_MAX, rigidez=E),
                                         SetBedroomsMin(bedrooms_min=2),
                                         "al menos 2 dormitorios, es innegociable")


# ══ R2-11 · concurrencia: quién sostiene la rigidez ═════════════════════════════════


def test_R2_11_FLEXIBLE_concurrente_con_ESTRICTA_da_CONFLICTO_y_no_last_write_wins(store):
    """Las dos conversaciones dejan el criterio en SOFT → la lista no cambia. Lo único que
    delata la escritura de A es QUIÉN sostiene la rigidez."""
    _actualizar(_msg("máximo 900 USD", "m-0"),
                _dur(SetBudgetMax(amount=Decimal(900), currency=USD)))
    _actualizar(_msg("el presupuesto es flexible", "m-A"), _rig(F.BUDGET_MAX, FL))
    assert _lista(store.revisiones[-1], F.BUDGET_MAX)[0] == "soft_preferences"

    _leer_rancio(store, 0)
    r = _actualizar(_msg("el presupuesto es innegociable", "m-B"), _rig(F.BUDGET_MAX, E))
    assert r.estado is EstadoActualizacion.CONFLICTO


def test_R2_11_la_divergencia_se_ve_aunque_la_lista_sea_la_misma():
    base = _paso(_vacio(), "máximo 900 USD",
                 _dur(SetBudgetMax(amount=Decimal(900), currency=USD)), mid="m-0")
    otro = _paso(base, "el presupuesto es flexible", _rig(F.BUDGET_MAX, FL), mid="m-A")
    assert _lista(base, F.BUDGET_MAX)[0] == _lista(otro, F.BUDGET_MAX)[0]
    assert rutas_divergentes(base, otro) == {"financial.budget_max"}


# ══ R2-12 · coletillas ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize("texto", [
    "el presupuesto es flexible, ¿no?",
    "el presupuesto es flexible, no?",
    "el presupuesto es flexible, ¿verdad?",
])
def test_R2_12_la_coletilla_no_se_traga_la_afirmacion(texto):
    assert _ok(texto, F.BUDGET_MAX, FL)


def test_R2_12_la_pregunta_entera_sigue_sin_declarar():
    assert not _ok("¿el presupuesto es flexible, no?", F.BUDGET_MAX, FL)


# ══ R2-13 · "ideal" ═════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("texto", [
    "mi casa ideal tendría al menos 2 dormitorios y buena luz",
    "busco un lugar ideal para mi familia con al menos 3 dormitorios",
])
def test_R2_13_ideal_adjetivo_no_es_flexibilidad(texto):
    assert not _ok(texto, F.BEDROOMS_MIN, FL)


def test_R2_13_lo_ideal_si_lo_es():
    assert _ok("lo ideal serían 3 dormitorios", F.BEDROOMS_MIN, FL)


# ══ R2-14 · R8 y R12 sobre todo el resultado ════════════════════════════════════════


def test_R2_14_un_duro_sin_rigidez_ARRASTRADO_tambien_se_levanta():
    """La base trae el presupuesto en hard sin su rigidez; el mensaje toca OTRA dimensión y
    el presupuesto se arrastra. R8 tiene que mirarlo igual."""
    base = _poblada()
    presupuesto = next(k for k in base.soft_preferences if k.criterion_id == "budget_max")
    colado = base.model_copy(update={
        "hard_constraints": (presupuesto,),
        "soft_preferences": tuple(k for k in base.soft_preferences if k is not presupuesto)})
    with pytest.raises(ReduccionImposible):
        _paso(colado, "al menos 3 dormitorios", _dur(SetBedroomsMin(bedrooms_min=3)),
              mid="m-1")


# ══ el doble del store (mismo contrato que en test_buyer_criterios_e33) ══════════════


class _StoreDoble:
    def __init__(self):
        self.revisiones: list = []
        self.por_mensaje: dict = {}

    async def cargar_ultima(self, buyer_id, *, db=None):
        return self.revisiones[-1] if self.revisiones else None

    async def anexar_revision(self, buyer_id, source_message_id, contexto,
                              expected_revision, *, db=None):
        from app.buyer.store import (
            BuyerIdempotencyConflict, BuyerRevisionConflict, RevisionPersistida,
        )
        if source_message_id in self.por_mensaje:
            ya = self.revisiones[self.por_mensaje[source_message_id]]
            if _canonico(ya) != _canonico(contexto):
                raise BuyerIdempotencyConflict("estado distinto")
            return RevisionPersistida(ya, ya.context_revision, creada=False)
        actual = self.revisiones[-1].context_revision if self.revisiones else None
        if expected_revision != actual:
            raise BuyerRevisionConflict(f"esperaba {expected_revision}, está en {actual}")
        nueva = 0 if actual is None else actual + 1
        guardado = contexto.model_copy(update={"context_revision": nueva})
        self.revisiones.append(guardado)
        self.por_mensaje[source_message_id] = nueva
        return RevisionPersistida(guardado, nueva, creada=True)


@pytest.fixture
def store(monkeypatch):
    doble = _StoreDoble()
    monkeypatch.setattr(act, "cargar_ultima", doble.cargar_ultima)
    monkeypatch.setattr(act, "anexar_revision", doble.anexar_revision)
    return doble


def _actualizar(mensaje, *propuestas, cuando=T0):
    async def proponer(_texto):
        return propuestas
    return asyncio.run(actualizar("b-1", mensaje, retrieved_at=cuando, proponente=proponer))


def _leer_rancio(store, revision):
    original = store.cargar_ultima

    async def leer(buyer_id, *, db=None):
        act.cargar_ultima = original
        return store.revisiones[revision]
    act.cargar_ultima = leer


# ══ R2b · la guarda asimétrica (segunda revisión adversarial) ═══════════════════════


@pytest.mark.parametrize("texto", [
    "no creo que el área y el presupuesto sean innegociables",     # la «y» no corta
    "Mi esposo dice: el presupuesto es innegociable",               # ni los dos puntos
    "el presupuesto es innegociable, dice mi esposo",               # voz ajena pospuesta
    "el presupuesto es innegociable, bueno, no tanto",              # negación pospuesta
    "el presupuesto es innegociable, no lo creo",
    "el presupuesto debería ser innegociable o no?",                # pregunta sin ¿
    "el presupuesto es innegociable, sí o no?",
    "mi esposo cree que el presupuesto es innegociable",            # «cree», no «dice»
    "según mi esposo el presupuesto es innegociable",
    "quizás el presupuesto es innegociable",
    "el presupuesto dejó de ser innegociable",                      # cambio de estado
    "quita lo de innegociable del presupuesto",                     # retractación
    "aunque me pase del presupuesto la seguridad es indispensable", # el sujeto es otro
    "el presupuesto antes era innegociable",
    "el presupuesto es innegociable, ¿verdad?",                    # pedir confirmación
    "el presupuesto es innegociable, ¿cierto?",
])
def test_R2b_ESTRICTA_no_se_acredita_fuera_de_una_oracion_limpia(texto):
    assert not _ok(texto, F.BUDGET_MAX, E)


@pytest.mark.parametrize("texto, campo", [
    ("tengo 70 años, un dormitorio en planta baja es indispensable", F.BEDROOMS_MIN),
    ("dos cuartos de baño son indispensables", F.BEDROOMS_MIN),
    ("máximo tres cuartos de hora al trabajo es innegociable", F.BEDROOMS_MIN),
    ("un balcón de 10 m2 es indispensable", F.AREA_M2_MIN),
    ("un veterinario cerca para mi perro es indispensable", F.PETS_REQUIRED),
])
def test_R2b_el_requisito_tiene_que_ser_el_SUJETO(texto, campo):
    """Nombrar la dimensión en cualquier función ya no basta: la forma canónica exige que sea
    el sujeto de la declaración."""
    assert not _ok(texto, campo, E)


@pytest.mark.parametrize("texto", [
    "el presupuesto es innegociable",
    "Sí, el presupuesto es innegociable",
    "No, el presupuesto es innegociable",
    "lo del presupuesto es innegociable",
    "mi presupuesto no es negociable",
    "para mí el presupuesto es totalmente innegociable",
    "el presupuesto tiene que ser innegociable",
    "Busco alquilar, máximo 900 USD, y el presupuesto es innegociable",
])
def test_R2b_la_forma_canonica_SI_se_acredita(texto):
    assert _ok(texto, F.BUDGET_MAX, E)


@pytest.mark.parametrize("texto", [
    "ya no, el presupuesto es flexible",
    "ya no es innegociable, el presupuesto es flexible",
    "nada de eso, el presupuesto es flexible",
    "el presupuesto sí es negociable",
    "eso sí, el presupuesto es flexible",
    "corrijo lo que dije, el presupuesto es flexible",
    "era broma, el presupuesto es flexible",
    "no no, el presupuesto es flexible",
    "ni modo, el presupuesto es flexible",
    "el presupuesto es flexible, ok?",
    "el presupuesto es innegociable... no, perdón, es flexible",
    "máximo 900 USD, pero no es indispensable",
])
def test_R2b_FLEXIBLE_acepta_las_correcciones_naturales(texto):
    """La dirección cara de FLEXIBLE es el falso NEGATIVO: el criterio se queda duro."""
    assert _ok(texto, F.BUDGET_MAX, FL)


@pytest.mark.parametrize("texto", [
    "el presupuesto no es flexible",
    "el presupuesto es cero negociable",
    "el presupuesto es apenas flexible",
    "no creo que el presupuesto sea flexible",
    "si el presupuesto fuera flexible buscaría en Cumbayá",
    "quería saber si el presupuesto es negociable",
    "el presupuesto es flexible o no?",
    "el precio es negociable",
])
def test_R2b_FLEXIBLE_no_se_acredita_si_se_niega_o_se_suspende(texto):
    assert not _ok(texto, F.BUDGET_MAX, FL)


def test_R2b_la_anafora_FLEXIBLE_exige_que_el_mensaje_hable_de_UNA_sola_dimension():
    assert _ok("mínimo 80 m2, idealmente", F.AREA_M2_MIN, FL)
    assert not _ok("máximo 900 USD, al menos 2 dormitorios, es flexible", F.BUDGET_MAX, FL)


def test_R2b_una_lectura_NO_acreditada_no_veta_la_declaracion_de_la_persona():
    """#12: «antes era innegociable, pero ahora…» — la lectura del pasado no se acredita y ya
    no anula la flexible que sí se acreditó."""
    base = _paso(_vacio(), "máximo 800 USD, el presupuesto es innegociable",
                 _dur(SetBudgetMax(amount=Decimal(800), currency=USD)), _rig(F.BUDGET_MAX, E),
                 mid="m-1")
    c = _paso(base, "Antes el presupuesto era innegociable, pero ahora el presupuesto es "
                    "flexible", _rig(F.BUDGET_MAX, E), _rig(F.BUDGET_MAX, FL), mid="m-2")
    assert _lista(c, F.BUDGET_MAX)[0] == "soft_preferences"


def test_R2b_una_correccion_natural_sobre_una_base_DURA_relaja():
    """#12 con el texto de R2-5, ahora que FLEXIBLE acepta la anáfora de una sola dimensión."""
    base = _paso(_vacio(), "máximo 800 USD, el presupuesto es innegociable",
                 _dur(SetBudgetMax(amount=Decimal(800), currency=USD)), _rig(F.BUDGET_MAX, E),
                 mid="m-1")
    c = _paso(base, "el presupuesto es innegociable... no, perdón, es flexible",
              _rig(F.BUDGET_MAX, E), _rig(F.BUDGET_MAX, FL), mid="m-2")
    assert _lista(c, F.BUDGET_MAX)[0] == "soft_preferences"


def test_R2b_FLEXIBLE_SI_se_aplica_aunque_el_valor_nuevo_quede_en_duda():
    """#1: relajar en la duda es seguro; endurecer no."""
    base = _paso(_vacio(), "máximo 800 USD, el presupuesto es innegociable",
                 _dur(SetBudgetMax(amount=Decimal(800), currency=USD)), _rig(F.BUDGET_MAX, E),
                 mid="m-1")
    c = _paso(base, "ahora puedo hasta mil dólares, el presupuesto es flexible",
              _dur(SetBudgetMax(amount=Decimal(1000), currency=USD)), _rig(F.BUDGET_MAX, FL),
              mid="m-2")
    lista, criterio = _lista(c, F.BUDGET_MAX)
    assert lista == "soft_preferences" and criterio.value == 800
    c = _paso(c, "mi presupuesto máximo es 1000 USD",
              _dur(SetBudgetMax(amount=Decimal(1000), currency=USD)), mid="m-3")
    assert _lista(c, F.BUDGET_MAX)[0] == "soft_preferences", "revivió la ESTRICTA vieja"


def test_R2b_una_pregunta_ABIERTA_de_antes_bloquea_endurecer():
    """#2: la duda en un mensaje anterior también cuenta."""
    c = _paso(_vacio(), "mi presupuesto máximo es 800 USD",
              _dur(SetBudgetMax(amount=Decimal(800), currency=USD)), mid="m-1")
    c = _paso(c, "creo que ahora puedo hasta mil dólares",
              PropuestaV0(disposicion=Disposicion.AMBIGUOUS, campo=F.BUDGET_MAX,
                          motivo="monto en letras"), mid="m-2")
    assert "financial.budget_max" in _preguntas(c)
    c = _paso(c, "el presupuesto es innegociable", _rig(F.BUDGET_MAX, E), mid="m-3")
    assert c.hard_constraints == ()


def test_R2b_las_revisiones_de_E33_se_siguen_leyendo():
    """#3: E3.3 persistía la metodología sin código. Un duro de entonces sigue siendo duro."""
    from app.buyer.reductor import _METODOLOGIA_E33

    c = _paso(_vacio(), "máximo 900 USD, el presupuesto es innegociable",
              _dur(SetBudgetMax(amount=Decimal(900), currency=USD)), _rig(F.BUDGET_MAX, E),
              mid="m-1")
    duro = c.hard_constraints[0]
    como_e33 = tuple(e.model_copy(update={"methodology": _METODOLOGIA_E33[E]})
                     if rigidez_de_evidencia(e) else e for e in duro.evidence)
    legado = c.model_copy(update={"hard_constraints": (duro.model_copy(
        update={"evidence": como_e33}),)})
    c = _paso(legado, "gracias", PropuestaV0(disposicion=Disposicion.TURN_ONLY,
                                              motivo="cortesía"), mid="m-2")
    assert _lista(c, F.BUDGET_MAX)[0] == "hard_constraints"


def test_R2b_el_log_no_repite_una_CLAVE_inventada(caplog):
    """#16: en `extra_forbidden` el `loc` es la clave que eligió el modelo."""
    centinela = "Calle-Centinela-Secreta-4471"
    with caplog.at_level(logging.WARNING, logger="app.buyer.interprete"):
        _parsear({"afirmaciones": [], "rigideces": [
            {"campo": "budget_max", "rigidez": "estricta", "motivo": "x", centinela: "y"}]})
    assert len(caplog.records) == 1
    assert centinela not in caplog.text and "<clave extra>" in caplog.text


def test_R2b_R12_tambien_sobre_lo_ARRASTRADO():
    """#21: la mitad de R2-14 que faltaba."""
    from app.contracts.buyer_v0 import CriterionOrigin

    base = _poblada()
    inferido = base.soft_preferences[0].model_copy(update={"origin": CriterionOrigin.INFERRED})
    colado = base.model_copy(update={"soft_preferences": (inferido, *base.soft_preferences[1:])})
    with pytest.raises(ReduccionImposible):
        _paso(colado, "al menos 3 dormitorios", _dur(SetBedroomsMin(bedrooms_min=3)),
              mid="m-1")


def test_R2b_un_retiro_con_rigidez_en_el_mismo_mensaje_la_descarta():
    """#22: sin valor que endurecer, la rigidez no se aplica; el retiro manda."""
    c = _paso(_poblada(), "ya no tengo tope de presupuesto, el presupuesto es innegociable",
              _dur(ClearBudgetMax()), _rig(F.BUDGET_MAX, E), mid="m-1")
    lista, criterio = _lista(c, F.BUDGET_MAX)
    assert lista == "soft_preferences" and criterio.status is CriterionStatus.RETRACTED


def test_R2b_si_la_ULTIMA_lectura_no_se_acredita_no_gana_la_anterior():
    """R2-5 sin la anáfora: «tal vez flexible» no se acredita, y aun así retira la estricta
    que la precedía. Nada cambia: el criterio se queda donde estaba."""
    base = _paso(_vacio(), "máximo 900 USD",
                 _dur(SetBudgetMax(amount=Decimal(900), currency=USD)), mid="m-1")
    c = _paso(base, "el presupuesto es innegociable. Bueno, tal vez flexible",
              _rig(F.BUDGET_MAX, E), _rig(F.BUDGET_MAX, FL), mid="m-2")
    assert c.hard_constraints == ()
