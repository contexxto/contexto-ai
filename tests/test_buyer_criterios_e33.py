"""F3-E3.3-HARD-SOFT-R1 · `hard_constraints` y `soft_preferences`, producidos de verdad.

Execution Plan 1.0, E3.3: *"Mover de un único hardcode global a restricciones del comprador,
dentro de whitelist segura. No todo debe convertirse en preferencia ponderada."* Y E3.2,
regla 2: *"inferencia nunca se vuelve hard constraint silenciosamente"*.

Lo que se prueba, en el orden del veredicto de la unidad:

```
A  la guarda de rigidez           lo que NO se puede acreditar es lo importante
B  el intérprete                  la rigidez entra por su propia puerta y no pelea con el valor
C  HARD / SOFT PRODUCER           el reducer los deriva, con la forma y la procedencia correctas
D  CORRECTION HARD↔SOFT           en las dos direcciones, y sin tocar el valor
E  EVIDENCE PRESERVED             la del valor, la de la rigidez y la del retiro, cada una suya
F  RETRY IDEMPOTENT               el replay no es divergencia; la otra interpretación sí
G  concurrencia                   cambiar la rigidez es tocar la ruta
H  PROTECTED-INFERENCE NONE       ni por tipo, ni por guarda, ni por una base contaminada
I  sin ranking todavía            el consumidor no se toca en esta unidad
```

Pura y offline salvo lo que dice lo contrario: sin Postgres, sin LLM.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import typing
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.buyer import actualizador as act
from app.buyer.actualizador import (
    EstadoActualizacion, actualizar, computar_candidato, rutas_divergentes, rutas_tocadas,
)
from app.buyer.boundary import (
    CAMPOS_CON_CRITERIO, BuyerCurrencyV0, BuyerFieldV0, CampoConCriterioV0, ClearBudgetMax,
    ClearPetsRequired, DeclaracionRigidezV0, Disposicion, RigidezV0, SetAreaM2Min,
    SetBedroomsMin, SetBudgetMax, SetObjective, SetPetsRequired,
)
from app.buyer.extractor import (
    AfirmacionDurable, AfirmacionRejected, LoteExtraccion, TraduccionNoAutorizada,
    autorizar_rigidez, construir_lote,
)
from app.buyer.interprete import (
    PropuestaRigidezV0, PropuestaV0, _parsear, _tool_schema, interpretar,
)
from app.buyer.mensaje import IdentifiedUserMessage
from app.buyer.reductor import (
    ReduccionImposible, es_evidencia_de_rigidez, evidence_id_determinista, reducir,
)
from app.buyer.store import _canonico
from app.contracts.buyer_v0 import (
    BuyerContextV0, CriterionOrigin, CriterionStatus, DecisionCriterionV0, Objective, Operator,
)
from app.contracts.evidence_v0 import EvidenceRefV0, PersistencePolicy, SourceType

T0 = dt.datetime(2026, 9, 23, 12, 0, tzinfo=dt.timezone.utc)
USD = BuyerCurrencyV0.USD
F = BuyerFieldV0
E, FL = RigidezV0.ESTRICTA, RigidezV0.FLEXIBLE

_BUD = SetBudgetMax(amount=Decimal(900), currency=USD)
_BED = SetBedroomsMin(bedrooms_min=2)

_DIMENSIONES_PERMITIDAS = {"price", "bedrooms", "area_m2", "pets_allowed"}
_PROTEGIDOS = (
    "household", "children", "familial_status", "race", "ethnicity", "national_origin",
    "religion", "sex", "gender_identity", "sexual_orientation", "disability",
)


def _msg(texto, mid="m-1"):
    return IdentifiedUserMessage(message_id=mid, text=texto)


def _dur(m):
    return PropuestaV0(disposicion=Disposicion.DURABLE, mutacion=m, motivo="declarado")


def _rig(campo, rigidez):
    return PropuestaRigidezV0(campo=campo, rigidez=rigidez, motivo="declarado")


def _vacio():
    return BuyerContextV0(buyer_id="b-1", updated_at=T0)


def _paso(contexto, texto, *propuestas, mid, cuando=T0):
    """Un mensaje por el camino REAL: propuestas → guarda → lote → reducer."""
    return reducir(contexto, interpretar(_msg(texto, mid), list(propuestas)), cuando)


def _criterio(contexto, campo):
    for lista in ("hard_constraints", "soft_preferences"):
        for c in getattr(contexto, lista):
            if c.criterion_id == campo.value:
                return lista, c
    return None, None


def _rigidez_ok(texto, campo, rigidez):
    try:
        autorizar_rigidez(DeclaracionRigidezV0(campo=campo, rigidez=rigidez), texto)
        return True
    except TraduccionNoAutorizada:
        return False


# ══ A · la guarda de rigidez ════════════════════════════════════════════════════════


@pytest.mark.parametrize("texto, campo, rigidez", [
    # R2b: ESTRICTA pegada a un VALOR no es forma canónica; la acredita el puente, que
    # necesita la durable del mensaje (test_R2_10). Sin ella, la guarda local no la acepta.
    ("necesito al menos 2 dormitorios sí o sí", F.BEDROOMS_MIN, None),
    ("el presupuesto es innegociable", F.BUDGET_MAX, E),
    ("mi presupuesto no es negociable", F.BUDGET_MAX, E),
    ("el presupuesto, sin excepción", F.BUDGET_MAX, None),     # la coma corta la cláusula
    ("tope de presupuesto sin excepción", F.BUDGET_MAX, E),
    ("que acepten mascotas es indispensable", F.PETS_REQUIRED, E),
    ("el área es imprescindible", F.AREA_M2_MIN, E),        # R2b: «el área» como SUJETO
    ("el área verde es imprescindible", F.AREA_M2_MIN, None),  # sobra «verde»
    ("la superficie es imprescindible", F.AREA_M2_MIN, E),
    ("el presupuesto es flexible", F.BUDGET_MAX, FL),
    ("los dormitorios son flexibles", F.BEDROOMS_MIN, FL),
    ("idealmente unos 80 m2", F.AREA_M2_MIN, FL),
    ("el presupuesto no es indispensable", F.BUDGET_MAX, FL),
    ("lo de las mascotas es de preferencia", F.PETS_REQUIRED, FL),
])
def test_A_la_guarda_acredita_la_rigidez_DECLARADA(texto, campo, rigidez):
    """`None` en la tabla = no acredita ninguna de las dos: falso negativo conocido, y
    aceptado — la rigidez sigue donde estaba."""
    for r in (E, FL):
        assert _rigidez_ok(texto, campo, r) is (r is rigidez), (texto, r)


def test_A_no_negociable_NO_acredita_flexible():
    """"no negociable" contiene "negociable". Leído por partes diría lo contrario."""
    assert _rigidez_ok("presupuesto no negociable", F.BUDGET_MAX, E)
    assert not _rigidez_ok("presupuesto no negociable", F.BUDGET_MAX, FL)
    assert not _rigidez_ok("los dormitorios no son indispensables", F.BEDROOMS_MIN, E)


@pytest.mark.parametrize("texto, campo", [
    ("máximo 900 USD", F.BUDGET_MAX),                          # 'máximo' es el valor
    ("al menos 2 dormitorios", F.BEDROOMS_MIN),                # 'al menos' también
    ("¿el presupuesto es flexible?", F.BUDGET_MAX),            # pregunta
    ("el presupuesto es flexible?", F.BUDGET_MAX),             # pregunta sin ¿
    ("no creo que el presupuesto sea flexible", F.BUDGET_MAX), # negación suelta
    ("el precio es negociable", F.BUDGET_MAX),                 # el del inmueble
    ("tenemos dos niños, es indispensable", F.BEDROOMS_MIN),   # persona, no requisito
    ("somos una familia grande y el espacio es imprescindible", F.AREA_M2_MIN),
    ("presupuesto 900 USD; los dormitorios son indispensables", F.BUDGET_MAX),  # no local
    ("presupuesto flexible o innegociable, no sé", F.BUDGET_MAX),  # las dos
    ("tengo un perro", F.PETS_REQUIRED),
])
def test_A_la_guarda_NO_acredita_lo_que_no_se_declaro(texto, campo):
    for r in (E, FL):
        assert not _rigidez_ok(texto, campo, r), (texto, r)


def test_A_la_rigidez_de_objective_o_de_un_protegido_no_se_puede_CONSTRUIR():
    """Whitelist por tipo: no se rechaza, no se puede expresar."""
    for campo in (F.OBJECTIVE, "objective", "household", "religion", "children"):
        with pytest.raises(ValidationError):
            DeclaracionRigidezV0(campo=campo, rigidez=E)
        with pytest.raises(ValidationError):
            PropuestaRigidezV0(campo=campo, rigidez=E, motivo="x")


def test_A_la_whitelist_son_exactamente_los_cuatro_requisitos_del_inmueble():
    assert set(CAMPOS_CON_CRITERIO) == {F.BUDGET_MAX, F.BEDROOMS_MIN, F.AREA_M2_MIN,
                                        F.PETS_REQUIRED}
    assert F.OBJECTIVE not in CAMPOS_CON_CRITERIO
    assert CAMPOS_CON_CRITERIO == typing.get_args(CampoConCriterioV0)


def test_A_la_rigidez_no_elige_destino():
    """No hay `path`, `field` ni `value`: el candidato no dice DÓNDE se escribe. El reducer
    deriva el campo del contrato; los nombres de las listas no aparecen en el tipo."""
    for clase in (DeclaracionRigidezV0, PropuestaRigidezV0):
        assert not ({"path", "field", "value"} & set(clase.model_fields))
        for nombre in ("hard_constraints", "soft_preferences"):
            assert nombre not in clase.model_fields


# ══ B · el intérprete ═══════════════════════════════════════════════════════════════


def test_B_una_rigidez_sin_valor_es_un_lote_NO_vacio_y_sin_afirmaciones():
    lote = interpretar(_msg("lo del presupuesto es flexible"), [_rig(F.BUDGET_MAX, FL)])
    assert lote.afirmaciones == ()
    assert lote.rigideces == (DeclaracionRigidezV0(campo=F.BUDGET_MAX, rigidez=FL),)


def test_B_una_rigidez_NO_acreditada_queda_como_REJECTED_y_no_mata_el_valor():
    """Si cayera a AMBIGUOUS competiría con el presupuesto en C1-C5 y lo anularía."""
    lote = interpretar(_msg("máximo 900 USD, a ver"),
                       [_dur(_BUD), _rig(F.BUDGET_MAX, E)])
    assert lote.mutaciones == (_BUD,)
    assert lote.rigideces == ()
    rechazo = [a for a in lote.afirmaciones if isinstance(a, AfirmacionRejected)]
    assert len(rechazo) == 1 and rechazo[0].campo is F.BUDGET_MAX


def test_B_dos_rigideces_distintas_SIN_correccion_no_eligen_ninguna():
    lote = interpretar(_msg("el presupuesto es innegociable y el presupuesto es flexible"),
                       [_rig(F.BUDGET_MAX, E), _rig(F.BUDGET_MAX, FL)])
    assert lote.rigideces == ()
    assert any(isinstance(a, AfirmacionRejected) and a.campo is F.BUDGET_MAX
               for a in lote.afirmaciones)


def test_B_dos_rigideces_distintas_CON_correccion_gana_la_ultima():
    lote = interpretar(
        _msg("el presupuesto es innegociable. perdón, en realidad el presupuesto es flexible"),
        [_rig(F.BUDGET_MAX, E), _rig(F.BUDGET_MAX, FL)])
    assert lote.rigideces == (DeclaracionRigidezV0(campo=F.BUDGET_MAX, rigidez=FL),)


def test_B_la_misma_rigidez_repetida_es_una():
    lote = interpretar(_msg("presupuesto innegociable, repito: presupuesto innegociable"),
                       [_rig(F.BUDGET_MAX, E), _rig(F.BUDGET_MAX, E)])
    assert len(lote.rigideces) == 1


def test_B_el_lote_no_admite_dos_rigideces_de_la_misma_dimension():
    with pytest.raises(ValidationError):
        LoteExtraccion(source_message_id="m", rigideces=(
            DeclaracionRigidezV0(campo=F.BUDGET_MAX, rigidez=E),
            DeclaracionRigidezV0(campo=F.BUDGET_MAX, rigidez=FL)))


def test_B_parsear_lee_rigideces_y_descarta_solo_la_mal_formada():
    propuestas = _parsear({
        "afirmaciones": [{"disposicion": "durable",
                          "mutacion": {"tipo": "set_budget_max", "amount": 900,
                                       "currency": "USD"},
                          "motivo": "tope"}],
        "rigideces": [{"campo": "budget_max", "rigidez": "estricta", "motivo": "dijo"},
                      {"campo": "objective", "rigidez": "estricta", "motivo": "no cabe"},
                      {"campo": "religion", "rigidez": "estricta", "motivo": "no cabe"}],
    })
    assert [type(p).__name__ for p in propuestas] == ["PropuestaV0", "PropuestaRigidezV0"]
    assert propuestas[1].campo is F.BUDGET_MAX


def test_B_el_esquema_ofrece_rigideces_OPCIONALES_y_con_la_whitelist_cerrada():
    esquema = _tool_schema()["input_schema"]
    assert "rigideces" in esquema["properties"]
    assert esquema["required"] == ["afirmaciones"], (
        "exigir rigideces empujaría al modelo a inventarlas")
    import json
    assert esquema["properties"]["rigideces"]["items"] == {
        "$ref": "#/$defs/PropuestaRigidezV0"}
    rigidez = esquema["$defs"]["PropuestaRigidezV0"]
    assert rigidez["properties"]["campo"]["enum"] == [
        "budget_max", "bedrooms_min", "area_m2_min", "pets_required"]
    assert rigidez.get("additionalProperties") is False
    texto = json.dumps(esquema, ensure_ascii=False)
    assert "household" not in texto and "description" not in texto


def test_B_todas_las_referencias_del_esquema_resuelven_DESDE_LA_RAIZ():
    """LA REGRESIÓN MEDIDA CON EL MODELO REAL. Con `$defs` anidados dentro de cada
    propiedad, las `$ref` —relativas a la raíz— no apuntaban a nada, y al añadir
    `rigideces` el modelo empezó a devolver el input entero como TEXTO dentro de
    `afirmaciones` (3/10, y 16/16 en otra variante). `_parsear` lo perdía todo: VACÍO.
    Un esquema con todas sus referencias resolubles es la condición de la que dependía."""
    esquema = _tool_schema()["input_schema"]
    definiciones = esquema.get("$defs", {})
    refs = []

    def recorrer(nodo, dentro_de_propiedad=False):
        if isinstance(nodo, dict):
            if "$defs" in nodo and nodo is not esquema:
                raise AssertionError("hay un `$defs` anidado: sus refs no resuelven")
            if "$ref" in nodo:
                refs.append(nodo["$ref"])
            for v in nodo.values():
                recorrer(v)
        elif isinstance(nodo, list):
            for v in nodo:
                recorrer(v)

    recorrer(esquema)
    assert refs, "el control necesita referencias que resolver"
    for ref in refs:
        assert ref.startswith("#/$defs/") and ref.removeprefix("#/$defs/") in definiciones, ref


def test_B_el_prompt_prohibe_deducir_la_rigidez():
    from app.buyer import interprete

    sistema = interprete._SYSTEM.lower()
    assert "rigideces" in sistema
    assert "nunca la deduzcas" in sistema
    assert "'máximo' y 'al menos' no son rigidez" in sistema


# ══ C · HARD / SOFT PRODUCER ════════════════════════════════════════════════════════


def test_C_un_valor_SIN_rigidez_declarada_va_a_soft_preferences():
    """R9 · regla 2 del plan. Que dijera "máximo" no convierte el tope en descalificador."""
    c = _paso(_vacio(), "mi presupuesto máximo es 900 USD", _dur(_BUD), mid="m-1")
    assert c.hard_constraints == ()
    (criterio,) = c.soft_preferences
    assert (criterio.dimension, criterio.operator, criterio.value, criterio.unit) == (
        "price", Operator.LTE, 900, "USD")
    assert criterio.origin is CriterionOrigin.STATED
    assert criterio.status is CriterionStatus.ACTIVE


def test_C_un_valor_CON_rigidez_estricta_va_a_hard_constraints():
    c = _paso(_vacio(), "necesito al menos 2 dormitorios sí o sí",
              _dur(_BED), _rig(F.BEDROOMS_MIN, E), mid="m-1")
    assert c.soft_preferences == ()
    (criterio,) = c.hard_constraints
    assert (criterio.criterion_id, criterio.dimension, criterio.operator, criterio.value) == (
        "bedrooms_min", "bedrooms", Operator.GTE, 2)


@pytest.mark.parametrize("texto, mutacion, forma", [
    ("máximo 900 USD", _BUD, ("price", Operator.LTE, 900, "USD")),
    ("al menos 2 dormitorios", _BED, ("bedrooms", Operator.GTE, 2, None)),
    ("mínimo 80 m2", SetAreaM2Min(area_m2_min=80.0), ("area_m2", Operator.GTE, 80.0, "m2")),
    ("necesito que acepten mascotas", SetPetsRequired(),
     ("pets_allowed", Operator.EQ, True, None)),
])
def test_C_cada_dimension_tiene_su_forma_EVALUABLE(texto, mutacion, forma):
    """El vocabulario del material de PLAN04-1.6, que es el que leerá el evaluador."""
    c = _paso(_vacio(), texto, _dur(mutacion), mid="m-1")
    (criterio,) = c.soft_preferences
    assert (criterio.dimension, criterio.operator, criterio.value, criterio.unit) == forma


def test_C_objective_no_produce_criterio():
    c = _paso(_vacio(), "quiero comprar", _dur(SetObjective(objective=Objective.BUY)),
              mid="m-1")
    assert c.hard_constraints == () and c.soft_preferences == ()


def test_C_el_orden_de_las_tuplas_NO_depende_del_orden_del_lote():
    texto = "máximo 900 USD, al menos 2 dormitorios, mínimo 80 m2"
    a = _paso(_vacio(), texto, _dur(_BUD), _dur(_BED),
              _dur(SetAreaM2Min(area_m2_min=80.0)), mid="m-1")
    b = _paso(_vacio(), texto, _dur(SetAreaM2Min(area_m2_min=80.0)), _dur(_BED),
              _dur(_BUD), mid="m-1")
    assert [x.criterion_id for x in a.soft_preferences] == [
        "budget_max", "bedrooms_min", "area_m2_min"]
    # Sólo los criterios: `field_evidence` conserva el orden del lote desde E3.2b.2, y eso
    # no es de esta unidad.
    assert a.soft_preferences == b.soft_preferences


def test_C_una_rigidez_sin_valor_no_inventa_un_criterio():
    c = _paso(_vacio(), "el presupuesto es innegociable", _rig(F.BUDGET_MAX, E), mid="m-1")
    assert c.hard_constraints == () and c.soft_preferences == ()


def test_C_el_criterio_y_su_campo_no_pueden_divergir():
    """Se derivan juntos en la misma reducción: el presupuesto no puede decir 900 y su
    criterio otra cosa."""
    c = _paso(_vacio(), "máximo 900 USD", _dur(_BUD), mid="m-1")
    c = _paso(c, "mejor máximo 950 USD",
              _dur(SetBudgetMax(amount=Decimal(950), currency=USD)), mid="m-2")
    _, criterio = _criterio(c, F.BUDGET_MAX)
    assert criterio.value == 950 == int(c.financial.budget_max.amount)


def test_C_un_monto_con_decimales_EXACTOS_se_conserva():
    c = reducir(_vacio(), construir_lote(_msg("x"), [AfirmacionDurable(
        mutacion=SetBudgetMax(amount=Decimal("900.5"), currency=USD), motivo="x")]), T0)
    assert c.soft_preferences[0].value == 900.5


def test_C_un_monto_que_float_no_representa_NO_se_redondea_en_silencio():
    with pytest.raises(ReduccionImposible):
        reducir(_vacio(), construir_lote(_msg("x"), [AfirmacionDurable(
            mutacion=SetBudgetMax(amount=Decimal("12345678901234567.5"), currency=USD),
            motivo="x")]), T0)


def test_C_el_contexto_producido_VALIDA_contra_el_contrato():
    """`model_copy` no valida; esto sí. Identidades únicas incluidas."""
    c = _paso(_vacio(), "máximo 900 USD, el presupuesto es innegociable, al menos 2 dormitorios",
              _dur(_BUD), _dur(_BED), _rig(F.BUDGET_MAX, E), mid="m-1")
    assert c.hard_constraints and c.soft_preferences
    BuyerContextV0.model_validate(c.model_dump())


# ══ D · CORRECTION HARD↔SOFT ═══════════════════════════════════════════════════════


def test_D_corregir_de_HARD_a_SOFT_sin_repetir_el_valor():
    c = _paso(_vacio(), "máximo 900 USD, y el presupuesto es innegociable",
              _dur(_BUD), _rig(F.BUDGET_MAX, E), mid="m-1")
    assert _criterio(c, F.BUDGET_MAX)[0] == "hard_constraints"

    c = _paso(c, "pensándolo bien, el presupuesto es flexible",
              _rig(F.BUDGET_MAX, FL), mid="m-2")
    lista, criterio = _criterio(c, F.BUDGET_MAX)
    assert lista == "soft_preferences"
    assert c.hard_constraints == ()
    assert criterio.value == 900 and criterio.status is CriterionStatus.ACTIVE


def test_D_corregir_de_SOFT_a_HARD():
    c = _paso(_vacio(), "al menos 2 dormitorios", _dur(_BED), mid="m-1")
    assert _criterio(c, F.BEDROOMS_MIN)[0] == "soft_preferences"
    c = _paso(c, "los dormitorios son indispensables", _rig(F.BEDROOMS_MIN, E), mid="m-2")
    assert _criterio(c, F.BEDROOMS_MIN)[0] == "hard_constraints"
    assert c.soft_preferences == ()


def test_D_R10_cambiar_el_VALOR_no_suelta_la_rigidez():
    """La persona corrigió el número, no la rigidez. Soltarla la cambiaría sin declaración."""
    c = _paso(_vacio(), "máximo 900 USD, el presupuesto es innegociable",
              _dur(_BUD), _rig(F.BUDGET_MAX, E), mid="m-1")
    c = _paso(c, "mejor máximo 950 USD",
              _dur(SetBudgetMax(amount=Decimal(950), currency=USD)), mid="m-2")
    lista, criterio = _criterio(c, F.BUDGET_MAX)
    assert lista == "hard_constraints" and criterio.value == 950


def test_D_una_correccion_NO_acreditada_no_mueve_nada():
    c = _paso(_vacio(), "máximo 900 USD, el presupuesto es innegociable",
              _dur(_BUD), _rig(F.BUDGET_MAX, E), mid="m-1")
    antes = _canonico(c)
    c = _paso(c, "¿el presupuesto es flexible?", _rig(F.BUDGET_MAX, FL), mid="m-2")
    assert _criterio(c, F.BUDGET_MAX)[0] == "hard_constraints"
    assert _canonico(c) == antes


def test_D_la_correccion_de_una_dimension_no_toca_las_demas():
    c = _paso(_vacio(), "máximo 900 USD, el presupuesto es innegociable, al menos 2 dormitorios sí o sí",
              _dur(_BUD), _dur(_BED), _rig(F.BUDGET_MAX, E), _rig(F.BEDROOMS_MIN, E),
              mid="m-1")
    c = _paso(c, "el presupuesto es flexible", _rig(F.BUDGET_MAX, FL), mid="m-2")
    assert _criterio(c, F.BEDROOMS_MIN)[0] == "hard_constraints"
    assert _criterio(c, F.BUDGET_MAX)[0] == "soft_preferences"


# ══ E · EVIDENCE PRESERVED ═════════════════════════════════════════════════════════


def test_E_la_evidencia_del_valor_ES_la_de_su_campo():
    c = _paso(_vacio(), "máximo 900 USD", _dur(_BUD), mid="m-1")
    (fe,) = c.field_evidence
    (ev,) = c.soft_preferences[0].evidence
    assert ev == fe.evidence
    assert ev.evidence_id == evidence_id_determinista("b-1", "m-1", "financial.budget_max")


def test_E_hard_lleva_la_evidencia_de_SU_rigidez_con_su_mensaje():
    c = _paso(_vacio(), "máximo 900 USD", _dur(_BUD), mid="m-1")
    c = _paso(c, "el presupuesto es innegociable", _rig(F.BUDGET_MAX, E), mid="m-2")
    criterio = c.hard_constraints[0]
    valor = [e for e in criterio.evidence if not es_evidencia_de_rigidez(e)]
    rigidez = [e for e in criterio.evidence if es_evidencia_de_rigidez(e)]
    assert [e.source_id for e in valor] == ["m-1"]
    assert [e.source_id for e in rigidez] == ["m-2"]
    assert "indispensable" in rigidez[0].methodology
    for e in criterio.evidence:
        assert e.source_type is SourceType.USER_DECLARED and e.observed_at is None


def test_E_corregir_la_rigidez_REEMPLAZA_su_evidencia_y_conserva_la_del_valor():
    c = _paso(_vacio(), "máximo 900 USD, el presupuesto es innegociable",
              _dur(_BUD), _rig(F.BUDGET_MAX, E), mid="m-1")
    c = _paso(c, "el presupuesto es flexible", _rig(F.BUDGET_MAX, FL), mid="m-2")
    criterio = c.soft_preferences[0]
    assert [(e.source_id, es_evidencia_de_rigidez(e)) for e in criterio.evidence] == [
        ("m-1", False), ("m-2", True)]
    assert "flexible" in criterio.evidence[1].methodology


def test_E_R11_un_CLEAR_deja_el_criterio_RETRACTED_con_toda_su_evidencia():
    c = _paso(_vacio(), "máximo 900 USD, el presupuesto es innegociable",
              _dur(_BUD), _rig(F.BUDGET_MAX, E), mid="m-1")
    c = _paso(c, "ya no tengo tope de presupuesto", _dur(ClearBudgetMax()), mid="m-2")

    assert c.financial.budget_max is None
    lista, criterio = _criterio(c, F.BUDGET_MAX)
    assert lista == "hard_constraints"
    assert criterio.status is CriterionStatus.RETRACTED
    assert not criterio.esta_activo
    assert criterio.value == 900, "lo que se retiró sigue legible"
    assert [e.source_id for e in criterio.evidence] == ["m-1", "m-2", "m-1"]


def test_E_R11_un_RETRACTED_se_arrastra_intacto_por_mensajes_que_no_lo_tocan():
    c = _paso(_vacio(), "necesito que acepten mascotas", _dur(SetPetsRequired()), mid="m-1")
    c = _paso(c, "ya no necesito mascotas", _dur(ClearPetsRequired()), mid="m-2")
    retirado = _criterio(c, F.PETS_REQUIRED)[1]
    c = _paso(c, "máximo 900 USD", _dur(_BUD), mid="m-3")
    assert _criterio(c, F.PETS_REQUIRED)[1] == retirado


def test_E_redeclarar_despues_del_retiro_lo_REACTIVA_con_la_evidencia_nueva():
    c = _paso(_vacio(), "máximo 900 USD", _dur(_BUD), mid="m-1")
    c = _paso(c, "ya no tengo tope de presupuesto", _dur(ClearBudgetMax()), mid="m-2")
    c = _paso(c, "máximo 1000 USD",
              _dur(SetBudgetMax(amount=Decimal(1000), currency=USD)), mid="m-3")
    criterio = _criterio(c, F.BUDGET_MAX)[1]
    assert criterio.status is CriterionStatus.ACTIVE and criterio.value == 1000
    assert [e.source_id for e in criterio.evidence] == ["m-3"]


def test_E_el_criterion_id_es_ESTABLE_entre_revisiones_y_listas():
    c = _paso(_vacio(), "máximo 900 USD", _dur(_BUD), mid="m-1")
    ids = [_criterio(c, F.BUDGET_MAX)[1].criterion_id]
    c = _paso(c, "el presupuesto es innegociable", _rig(F.BUDGET_MAX, E), mid="m-2")
    ids.append(_criterio(c, F.BUDGET_MAX)[1].criterion_id)
    c = _paso(c, "ya no tengo tope de presupuesto", _dur(ClearBudgetMax()), mid="m-3")
    ids.append(_criterio(c, F.BUDGET_MAX)[1].criterion_id)
    assert ids == ["budget_max"] * 3


# ══ F · RETRY IDEMPOTENT ═══════════════════════════════════════════════════════════


def test_F_el_replay_con_OTRO_retrieved_at_da_el_mismo_canonico():
    """EL CONTROL QUE LA MUTACIÓN M-IDEMP TIENE QUE ROMPER. La evidencia de la rigidez vive
    dentro del criterio; si `_canonico` sólo limpiara `field_evidence`, esto divergiría."""
    base = _paso(_vacio(), "máximo 900 USD", _dur(_BUD), mid="m-1")
    lote = interpretar(_msg("el presupuesto es innegociable", "m-2"),
                       [_rig(F.BUDGET_MAX, E)])
    a = reducir(base, lote, T0)
    b = reducir(base, lote, T0 + dt.timedelta(seconds=41))

    assert a.hard_constraints[0].evidence[-1].retrieved_at != \
        b.hard_constraints[0].evidence[-1].retrieved_at, "el control necesita instantes distintos"
    assert _canonico(a) == _canonico(b)


def test_F_el_mismo_mensaje_con_OTRA_rigidez_SI_diverge():
    base = _paso(_vacio(), "máximo 900 USD", _dur(_BUD), mid="m-1")
    a = reducir(base, construir_lote(_msg("x", "m-2"), [], [
        DeclaracionRigidezV0(campo=F.BUDGET_MAX, rigidez=E)]), T0)
    b = reducir(base, construir_lote(_msg("x", "m-2"), [], [
        DeclaracionRigidezV0(campo=F.BUDGET_MAX, rigidez=FL)]), T0)
    assert _canonico(a) != _canonico(b)


def test_F_la_limpieza_no_alcanza_a_la_procedencia_de_un_proveedor():
    """El límite de R-IDEMP-1 sigue en pie dentro de los criterios."""
    from app.buyer.store import _limpiar_procedencia_operacional

    ev = EvidenceRefV0(
        evidence_id="e-1", source_type=SourceType.PROVIDER_API, provider="p",
        source_id="s", methodology="m", persistence_policy=PersistencePolicy.CACHEABLE_TEMPORARILY,
        cache_ttl_seconds=60, observed_at=T0, retrieved_at=T0,
    ).model_dump(mode="json")
    _limpiar_procedencia_operacional(ev)
    assert "retrieved_at" in ev and "evidence_id" in ev


class _StoreDoble:
    """El mismo contrato que el doble de `test_buyer_actualizador`: idempotencia por
    `(buyer, mensaje)` con `_canonico`, y conflicto de revisión."""

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


def _proponente(*propuestas):
    async def proponer(_texto):
        return propuestas
    return proponer


def _actualizar(mensaje, *propuestas, cuando=T0):
    return asyncio.run(actualizar("b-1", mensaje, retrieved_at=cuando,
                                  proponente=_proponente(*propuestas)))


def test_F_por_el_orquestador_el_reintento_es_REPLAY_y_no_FALLIDO(store):
    _actualizar(_msg("máximo 900 USD", "m-1"), _dur(_BUD))
    primero = _actualizar(_msg("el presupuesto es innegociable", "m-2"),
                          _rig(F.BUDGET_MAX, E))
    reintento = _actualizar(_msg("el presupuesto es innegociable", "m-2"),
                            _rig(F.BUDGET_MAX, E), cuando=T0 + dt.timedelta(minutes=3))

    assert primero.estado is EstadoActualizacion.CREADA
    assert reintento.estado is EstadoActualizacion.REPLAY
    assert reintento.revision == primero.revision
    assert reintento.contexto.hard_constraints[0].evidence[-1].retrieved_at == T0, (
        "el replay devuelve la revisión ORIGINAL, con su instante")


def test_F_por_el_orquestador_otra_rigidez_del_mismo_mensaje_es_FALLIDO(store):
    _actualizar(_msg("máximo 900 USD", "m-1"), _dur(_BUD))
    _actualizar(_msg("el presupuesto es innegociable; el presupuesto es flexible", "m-2"),
                _rig(F.BUDGET_MAX, E))
    r = _actualizar(_msg("el presupuesto es innegociable; el presupuesto es flexible", "m-2"),
                    _rig(F.BUDGET_MAX, FL))
    assert r.estado is EstadoActualizacion.FALLIDO


def test_F_una_rigidez_sola_NO_es_VACIO_y_sella_el_mensaje(store):
    """Sin esto, "lo del presupuesto es flexible" quedaba sin procesar para siempre."""
    _actualizar(_msg("máximo 900 USD, innegociable el presupuesto", "m-1"),
                _dur(_BUD), _rig(F.BUDGET_MAX, E))
    r = _actualizar(_msg("lo del presupuesto es flexible", "m-2"), _rig(F.BUDGET_MAX, FL))
    assert r.estado is EstadoActualizacion.CREADA
    assert r.contexto.hard_constraints == ()


def test_F_una_rigidez_NO_acreditada_sella_como_NO_OP(store):
    _actualizar(_msg("máximo 900 USD", "m-1"), _dur(_BUD))
    r = _actualizar(_msg("¿el presupuesto es flexible?", "m-2"), _rig(F.BUDGET_MAX, FL))
    assert r.estado is EstadoActualizacion.NO_OP


def test_F_cero_propuestas_sigue_siendo_VACIO(store):
    r = asyncio.run(computar_candidato("b-1", _msg("hola"), retrieved_at=T0,
                                       proponente=_proponente()))
    assert r.estado is EstadoActualizacion.VACIO


# ══ G · concurrencia ═══════════════════════════════════════════════════════════════


def test_G_la_rigidez_TOCA_la_ruta_de_su_dimension():
    lote = interpretar(_msg("el presupuesto es innegociable"), [_rig(F.BUDGET_MAX, E)])
    assert rutas_tocadas(lote) == {"financial.budget_max"}


def test_G_cambiar_SOLO_la_rigidez_es_divergencia_de_esa_ruta():
    base = _paso(_vacio(), "máximo 900 USD", _dur(_BUD), mid="m-1")
    otro = _paso(base, "el presupuesto es innegociable", _rig(F.BUDGET_MAX, E), mid="m-2")
    assert base.financial.budget_max == otro.financial.budget_max
    assert rutas_divergentes(base, otro) == {"financial.budget_max"}


def _leer_rancio(store, revision):
    """B leyó la revisión `revision` antes de que A escribiera encima."""
    original = store.cargar_ultima

    async def leer(buyer_id, *, db=None):
        act.cargar_ultima = original
        return store.revisiones[revision]
    act.cargar_ultima = leer


def test_G_dos_rigideces_CONCURRENTES_de_la_misma_dimension_dan_CONFLICTO(store):
    """Nunca last-write-wins. Sin la rigidez en el estado semántico de la ruta, B se
    rebasaba sobre A y devolvía el presupuesto a flexible sin que nadie lo decidiera."""
    _actualizar(_msg("máximo 900 USD", "m-0"), _dur(_BUD))
    _actualizar(_msg("el presupuesto es innegociable", "m-A"), _rig(F.BUDGET_MAX, E))

    _leer_rancio(store, 0)
    r = _actualizar(_msg("el presupuesto es flexible", "m-B"), _rig(F.BUDGET_MAX, FL))

    assert r.estado is EstadoActualizacion.CONFLICTO
    assert store.revisiones[-1].hard_constraints[0].criterion_id == "budget_max"


def test_G_una_rigidez_concurrente_con_OTRA_dimension_se_REBASA(store):
    _actualizar(_msg("máximo 900 USD, al menos 2 dormitorios", "m-0"), _dur(_BUD), _dur(_BED))
    _actualizar(_msg("el presupuesto es innegociable", "m-A"), _rig(F.BUDGET_MAX, E))

    _leer_rancio(store, 0)
    r = _actualizar(_msg("los dormitorios son indispensables", "m-B"),
                    _rig(F.BEDROOMS_MIN, E))

    assert r.estado is EstadoActualizacion.REBASEADA
    assert [c.criterion_id for c in r.contexto.hard_constraints] == [
        "budget_max", "bedrooms_min"], "el rebase perdió la rigidez de A"


# ══ H · PROTECTED-INFERENCE NONE ═══════════════════════════════════════════════════


_FRASES_SOBRE_LA_PERSONA = (
    "tenemos dos niños, es indispensable",
    "somos una familia grande y el espacio es imprescindible",
    "mi esposa usa silla de ruedas, es obligatorio",
    "soy católico, sí o sí",
    "tengo 70 años, los dormitorios son indispensables para mí",  # ← ésta SÍ declara
)


@pytest.mark.parametrize("texto", _FRASES_SOBRE_LA_PERSONA)
def test_H_un_proponente_HOSTIL_no_convierte_a_la_persona_en_criterio(texto):
    """El peor proponente posible: propone un valor y rigidez estricta en TODAS las
    dimensiones. Ningún VALOR puede salir de una frase sobre la persona; y sin valor, ninguna
    rigidez tiene criterio que mover."""
    propuestas = [
        _dur(SetBedroomsMin(bedrooms_min=2)), _dur(SetAreaM2Min(area_m2_min=120.0)),
        _dur(SetPetsRequired()), _dur(_BUD),
        *[_rig(campo, E) for campo in CAMPOS_CON_CRITERIO],
    ]
    c = _paso(_vacio(), texto, *propuestas, mid="m-1")
    assert c.hard_constraints == () and c.soft_preferences == ()
    assert c.property_requirements.bedrooms_min is None


def test_H_la_rigidez_declarada_SIN_valor_de_la_persona_no_crea_nada_y_luego_no_pesa():
    """"los dormitorios son indispensables para mí" SÍ declara rigidez (la última frase de
    arriba), pero sin valor no hay criterio. Si después declara un valor, entra en SOFT: la
    rigidez de un mensaje sin criterio no se guarda para aplicarse más tarde."""
    c = _paso(_vacio(), _FRASES_SOBRE_LA_PERSONA[-1], _rig(F.BEDROOMS_MIN, E), mid="m-1")
    assert c.hard_constraints == () and c.soft_preferences == ()
    c = _paso(c, "al menos 2 dormitorios", _dur(_BED), mid="m-2")
    assert _criterio(c, F.BEDROOMS_MIN)[0] == "soft_preferences"


def test_H_la_whitelist_no_contiene_ningun_atributo_protegido():
    nombres = {c.value for c in CAMPOS_CON_CRITERIO} | _DIMENSIONES_PERMITIDAS
    for protegido in _PROTEGIDOS:
        assert not any(protegido in n for n in nombres), protegido


@pytest.mark.parametrize("dimension", ["religion", "familial_status", "children", "bedrooms"])
def test_H_una_base_CONTAMINADA_no_se_arrastra_se_levanta(dimension):
    """El contrato admite `dimension='religion'`. Este reducer no: un criterio que no sabe
    mantener no lo copia ni lo borra en silencio. `bedrooms` con un id ajeno tampoco."""
    base = _vacio().model_copy(update={"soft_preferences": (DecisionCriterionV0(
        criterion_id="intrusa", dimension=dimension, operator=Operator.EQ, value="x",
        origin=CriterionOrigin.INFERRED),)})
    with pytest.raises(ReduccionImposible):
        _paso(base, "máximo 900 USD", _dur(_BUD), mid="m-1")


def test_H_R8_un_hard_SIN_rigidez_declarada_en_la_base_se_levanta():
    """R8 comprobado sobre el resultado, no sólo por construcción: una base que trae un
    criterio duro sin la declaración que lo justifica no se perpetúa."""
    base = _paso(_vacio(), "máximo 900 USD", _dur(_BUD), mid="m-1")
    colado = base.model_copy(update={"hard_constraints": base.soft_preferences,
                                     "soft_preferences": ()})
    with pytest.raises(ReduccionImposible):
        _paso(colado, "al menos 2 dormitorios", _dur(_BED), mid="m-2")


def _escenarios_de_esta_suite():
    escenarios = [
        _paso(_vacio(), "máximo 900 USD, el presupuesto es innegociable, al menos 2 dormitorios, "
              "mínimo 80 m2, necesito que acepten mascotas",
              _dur(_BUD), _dur(_BED), _dur(SetAreaM2Min(area_m2_min=80.0)),
              _dur(SetPetsRequired()), _rig(F.BUDGET_MAX, E), mid="m-1"),
    ]
    c = escenarios[0]
    for texto, props, mid in (
        ("el presupuesto es flexible", [_rig(F.BUDGET_MAX, FL)], "m-2"),
        ("ya no tengo tope de presupuesto", [_dur(ClearBudgetMax())], "m-3"),
        ("las mascotas son indispensables", [_rig(F.PETS_REQUIRED, E)], "m-4"),
    ):
        c = _paso(c, texto, *props, mid=mid)
        escenarios.append(c)
    return escenarios


def _todos_los_criterios_de_esta_suite():
    return [k for ctx in _escenarios_de_esta_suite()
            for k in (*ctx.hard_constraints, *ctx.soft_preferences)]


def test_H_todo_criterio_producido_es_STATED_y_de_una_dimension_permitida():
    criterios = _todos_los_criterios_de_esta_suite()
    assert len(criterios) >= 10, "el control necesita criterios de verdad"
    for k in criterios:
        assert k.origin is CriterionOrigin.STATED
        assert k.dimension in _DIMENSIONES_PERMITIDAS
        assert k.evidence and all(e.source_type is SourceType.USER_DECLARED for e in k.evidence)


def test_H_todo_criterio_DURO_tiene_su_rigidez_ESTRICTA_declarada():
    """E3.3-R2: la versión anterior filtraba por la evidencia y nunca miraba
    `hard_constraints`, así que era tautológica. Ahora recorre la LISTA DURA."""
    from app.buyer.reductor import rigidez_de_evidencia

    duros = [k for ctx in _escenarios_de_esta_suite() for k in ctx.hard_constraints]
    assert duros, "el control necesita criterios duros"
    for k in duros:
        assert any(rigidez_de_evidencia(e) is RigidezV0.ESTRICTA for e in k.evidence), \
            f"{k.criterion_id} está en hard_constraints sin rigidez ESTRICTA"


# ══ I · sin ranking todavía ════════════════════════════════════════════════════════


@pytest.mark.parametrize("modulo", ["app/encaje.py", "app/orden.py"])
def test_I_el_ranking_NO_lee_criterios_todavia(modulo):
    """E3.3 los PRODUCE. Consumirlos para descalificar u ordenar es ranking —el punto 6 del
    Gate F3— y exige su propia unidad con `SCORE_VERSION` nueva. El día que se conecten, esta
    guarda cae a propósito."""
    import pathlib

    ruta = pathlib.Path(__file__).resolve().parents[1] / modulo
    if not ruta.exists():
        pytest.skip(f"{modulo} no existe en este árbol")
    fuente = ruta.read_text(encoding="utf-8")
    for campo in ("hard_constraints", "soft_preferences"):
        assert campo not in fuente, f"{modulo} ya lee {campo}: abrir la unidad de ranking"
