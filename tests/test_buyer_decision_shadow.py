"""F3-SHADOW-DECISION-RUNTIME-R0G · la derivación de la operación de mascotas.

QUÉ CONGELA, y qué NO.

    congela    de dónde sale la operación (evidencia estructurada, nunca texto), su
               precedencia, que la ausencia de señal NO es una retirada, y que cualquier
               incertidumbre corta el paso
    NO congela que el comprador mejore la recomendación. R0G no lo pregunta

Este fichero mide las piezas PURAS. La orquestación y las puertas viven en
`test_buyer_decision_shadow_runtime.py`.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.buyer.actualizador import EstadoActualizacion
from app.buyer.boundary import (
    BuyerFieldV0, ClearPetsRequired, SetBedroomsMin, SetPetsRequired,
)
from app.buyer.decision_shadow import (
    ClaseDelta, FuenteDelEstado, OperacionMascotas, RelacionPersistencia,
    aplicar_operacion, clasificar_delta, medir, operacion_de_la_memoria,
    operacion_del_turno, relacion_de_persistencia,
)
from app.buyer.extractor import AfirmacionAmbiguous, AfirmacionDurable, LoteExtraccion
from app.buyer.reductor import reducir
from app.contracts.buyer_v0 import BuyerContextV0

T0 = dt.datetime(2026, 9, 14, 12, 0, tzinfo=dt.timezone.utc)
A = "11111111-1111-4111-8111-111111111111"
CLAVE = "acepta_mascotas"


def _lote(*mutaciones, mid="m-1", ambigua=None):
    afirmaciones = [AfirmacionDurable(motivo="m", mutacion=m) for m in mutaciones]
    if ambigua is not None:
        afirmaciones.append(AfirmacionAmbiguous(motivo="dudoso", campo=ambigua))
    return LoteExtraccion(source_message_id=mid, afirmaciones=afirmaciones)


def _contexto(*lotes):
    """Construye la memoria por el camino REAL: reduciendo, no fabricando el contexto.

    Importa: el discriminador de R0G es que el valor y su `FieldEvidence` se escriben en la
    misma reducción. Un contexto armado a mano podría tener combinaciones que el sistema no
    produce nunca, y el test estaría midiendo un estado imposible.
    """
    ctx = BuyerContextV0(buyer_id=A, updated_at=T0)
    for lote in lotes:
        ctx = reducir(ctx, lote, T0)
    return ctx


# ══ T8-T10 · EL TURNO ACTUAL ═══════════════════════════════════════════════════════


def test_T8_una_durable_SetPetsRequired_da_REQUERIR():
    assert operacion_del_turno(_lote(SetPetsRequired())) is OperacionMascotas.REQUERIR


def test_T9_una_durable_ClearPetsRequired_da_RETIRAR():
    assert operacion_del_turno(_lote(ClearPetsRequired())) is OperacionMascotas.RETIRAR


def test_T10_una_ambigua_sobre_mascotas_da_NO_COMPARABLE():
    """Si la persona está aclarando o contradiciendo, fingir certeza sería lo peor que
    podría hacer el experimento."""
    lote = _lote(ambigua=BuyerFieldV0.PETS_REQUIRED)
    assert operacion_del_turno(lote) is OperacionMascotas.NO_COMPARABLE


def test_T10b_un_turno_que_NO_habla_de_mascotas_devuelve_None():
    """`None` significa «pásale la pregunta a la memoria», y es distinto de `SIN_SENAL`."""
    assert operacion_del_turno(_lote(SetBedroomsMin(bedrooms_min=2))) is None
    assert operacion_del_turno(_lote(ambigua=BuyerFieldV0.BEDROOMS_MIN)) is None
    assert operacion_del_turno(None) is None


def test_T10c_una_durable_GANA_a_una_ambigua_de_otro_campo():
    """La ambigüedad tiene que ser SOBRE mascotas para cortar el paso."""
    lote = _lote(SetPetsRequired(), ambigua=BuyerFieldV0.BEDROOMS_MIN)
    assert operacion_del_turno(lote) is OperacionMascotas.REQUERIR


# ══ T11-T15 · LA MEMORIA PERSISTIDA ════════════════════════════════════════════════


def test_T11_memoria_con_pets_True_da_REQUERIR():
    ctx = _contexto(_lote(SetPetsRequired()))
    assert ctx.property_requirements.pets_allowed_required is True
    assert operacion_de_la_memoria(ctx) is OperacionMascotas.REQUERIR


def test_T12_memoria_con_None_Y_evidencia_da_RETIRAR():
    """Una retirada explícita deja valor `None` **con** evidencia en la ruta."""
    ctx = _contexto(_lote(SetPetsRequired(), mid="m1"), _lote(ClearPetsRequired(), mid="m2"))
    assert ctx.property_requirements.pets_allowed_required is None
    assert operacion_de_la_memoria(ctx) is OperacionMascotas.RETIRAR


def test_T15_memoria_con_None_SIN_evidencia_da_SIN_SENAL():
    """El caso que un `bool | None` ingenuo confundiría con una retirada."""
    ctx = _contexto(_lote(SetBedroomsMin(bedrooms_min=2)))
    assert ctx.property_requirements.pets_allowed_required is None
    assert operacion_de_la_memoria(ctx) is OperacionMascotas.SIN_SENAL

    assert operacion_de_la_memoria(None) is OperacionMascotas.SIN_SENAL
    assert operacion_de_la_memoria(BuyerContextV0(buyer_id=A, updated_at=T0)) \
        is OperacionMascotas.SIN_SENAL


def test_M3_MUTACION_tratar_la_AUSENCIA_como_retirada_se_detecta():
    """Los dos contextos tienen `pets = None`. Sólo la evidencia los separa.

    Si el discriminador mirara únicamente el valor, los dos darían RETIRAR y un comprador
    silencioso borraría una preferencia que la persona declaró en el hilo.
    """
    nunca = _contexto(_lote(SetBedroomsMin(bedrooms_min=2)))
    retirado = _contexto(_lote(SetPetsRequired(), mid="m1"),
                         _lote(ClearPetsRequired(), mid="m2"))

    assert nunca.property_requirements.pets_allowed_required is None
    assert retirado.property_requirements.pets_allowed_required is None
    assert operacion_de_la_memoria(nunca) is not operacion_de_la_memoria(retirado), \
        "el valor solo no distingue silencio de retirada: el guard sería inerte"


def test_la_evidencia_de_un_SET_viejo_NO_puede_confundirse_con_una_retirada():
    """La propiedad que R3 estableció, comprobada aquí sobre el camino real.

    Cardinalidad ≤ 1 por ruta y valor+evidencia escritos en la misma reducción: si la última
    mutación de mascotas hubiera sido un `Set`, el valor sería `True`. Así que `None` con
    evidencia sólo puede venir de un `Clear`.
    """
    from app.buyer.decision_shadow import _RUTA_PETS

    puesto = _contexto(_lote(SetPetsRequired(), mid="m1"))
    retirado = reducir(puesto, _lote(ClearPetsRequired(), mid="m2"), T0)
    luego_otro = reducir(retirado, _lote(SetBedroomsMin(bedrooms_min=2), mid="m3"), T0)

    for ctx in (puesto, retirado, luego_otro):
        assert len([fe for fe in ctx.field_evidence if fe.field == _RUTA_PETS]) <= 1

    assert operacion_de_la_memoria(puesto) is OperacionMascotas.REQUERIR
    assert operacion_de_la_memoria(retirado) is OperacionMascotas.RETIRAR
    assert operacion_de_la_memoria(luego_otro) is OperacionMascotas.RETIRAR, \
        "un turno que no toca mascotas no puede perder la retirada anterior"


def test_una_pregunta_abierta_sobre_mascotas_en_la_MEMORIA_corta_el_paso():
    """Un valor acompañado de una incertidumbre declarada no es una afirmación de la que se
    pueda partir."""
    ctx = _contexto(_lote(SetPetsRequired(), mid="m1"),
                    _lote(ambigua=BuyerFieldV0.PETS_REQUIRED, mid="m2"))
    assert ctx.property_requirements.pets_allowed_required is True
    assert any(q.about_field.endswith("pets_allowed_required")
               for q in ctx.unresolved_questions)
    assert operacion_de_la_memoria(ctx) is OperacionMascotas.NO_COMPARABLE


# ══ T16-T18 · PRECEDENCIA ══════════════════════════════════════════════════════════


@pytest.mark.parametrize("memoria, turno, esperado", [
    # persisted REQUIRE + current CLEAR → CLEAR
    ((SetPetsRequired(),), ClearPetsRequired(), OperacionMascotas.RETIRAR),
    # persisted CLEAR + current SET → REQUIRE
    ((SetPetsRequired(), ClearPetsRequired()), SetPetsRequired(), OperacionMascotas.REQUERIR),
])
def test_T16_T17_el_turno_actual_GANA_a_la_memoria(memoria, turno, esperado):
    """`CURRENT > PERSISTED`. No se revive un estado viejo mientras la persona habla."""
    del memoria  # la memoria ni se consulta: el turno ya decidió
    assert operacion_del_turno(_lote(turno)) is esperado


def test_T18_una_ambigua_actual_gana_a_una_memoria_que_REQUIERE():
    """El caso que M4 muta: la memoria vieja NO puede ganarle a una duda de ahora."""
    memoria = _contexto(_lote(SetPetsRequired()))
    assert operacion_de_la_memoria(memoria) is OperacionMascotas.REQUERIR

    del_turno = operacion_del_turno(_lote(ambigua=BuyerFieldV0.PETS_REQUIRED))
    assert del_turno is OperacionMascotas.NO_COMPARABLE, \
        "la ambigüedad del turno tiene que cortar antes de mirar la memoria"


def test_M4_MUTACION_que_la_memoria_VIEJA_gane_a_la_duda_actual_se_detecta():
    memoria = _contexto(_lote(SetPetsRequired()))
    correcto = operacion_del_turno(_lote(ambigua=BuyerFieldV0.PETS_REQUIRED))
    mutado = operacion_de_la_memoria(memoria)          # la mutación: ignorar el turno
    assert correcto is OperacionMascotas.NO_COMPARABLE
    assert mutado is OperacionMascotas.REQUERIR
    assert correcto is not mutado, "el detector no distingue las dos políticas"


# ══ APLICACIÓN · UNA CLAVE ═════════════════════════════════════════════════════════


def test_la_operacion_toca_UNA_sola_clave_y_no_muta_el_legacy():
    legacy = {"dormitorios": 2, "presupuesto_max": 700}
    copia = dict(legacy)

    requerir = aplicar_operacion(legacy, OperacionMascotas.REQUERIR)
    assert requerir[CLAVE] is True
    assert legacy == copia, "se mutó el legacy: lo visible se decidió con él"

    con_pets = {**legacy, CLAVE: True}
    assert CLAVE not in aplicar_operacion(con_pets, OperacionMascotas.RETIRAR)
    assert aplicar_operacion(con_pets, OperacionMascotas.SIN_SENAL) == con_pets
    assert aplicar_operacion(con_pets, OperacionMascotas.SIN_SENAL) is not con_pets


def test_M2_MUTACION_tocar_un_SEGUNDO_campo_se_detecta():
    legacy = {"dormitorios": 2}
    sombra = aplicar_operacion(legacy, OperacionMascotas.REQUERIR)
    metricas = {"mismo_universo": True, "mismo_orden": True, "deltas_de_score": 0,
                "deltas_de_cobertura": 0, "movimientos_de_rejilla": 0}
    assert clasificar_delta(legacy, sombra, metricas) is ClaseDelta.SIN_DELTA

    sombra[
        "presupuesto_max"] = 300                        # el segundo campo, sólo aquí
    assert clasificar_delta(legacy, sombra, metricas) is ClaseDelta.DELTA_INESPERADO


def test_SIN_SENAL_no_inventa_ni_borra_nada():
    """Las dos direcciones: ni añade mascotas donde no las había, ni las quita donde sí."""
    assert aplicar_operacion({}, OperacionMascotas.SIN_SENAL) == {}
    assert aplicar_operacion({CLAVE: True}, OperacionMascotas.SIN_SENAL) == {CLAVE: True}


# ══ MÉTRICAS Y CLASIFICACIÓN ═══════════════════════════════════════════════════════


def _card(cid, encaje, cobertura=1.0):
    return {"id": cid, "encaje": encaje, "encaje_cobertura": cobertura}


def test_las_metricas_cubren_CARDS_MAS_DESCARTADAS():
    """R0E demostró que mascotas puede empujar un activo bajo el corte de rejilla. Si se
    midiera sólo lo visible, ese activo desaparecería justo en el caso que más dice."""
    v_cards = [_card("a", 100), _card("b", 100), _card("c", 100)]
    s_cards = [_card("a", 100), _card("c", 75, 0.5)]
    s_desc = [_card("b", 50)]

    m = medir(v_cards, [], s_cards, s_desc)
    assert m["mismo_universo"], "el universo tiene que conservarse"
    assert m["visibles"] == 3 and m["sombra"] == 2
    assert m["movimientos_de_rejilla"] == 1
    assert m["deltas_de_score"] == 2 and m["deltas_de_cobertura"] == 1
    assert not m["top1_cambio"] and m["top3_solape"] == 2
    assert m["movimientos_de_posicion"] == 1


def test_T22_sin_cambios_la_clasificacion_es_SIN_DELTA():
    cards = [_card("a", 100), _card("b", 90)]
    m = medir(cards, [], cards, [])
    legacy = {"dormitorios": 2}
    assert clasificar_delta(legacy, dict(legacy), m) is ClaseDelta.SIN_DELTA


def test_T23_T25_un_movimiento_de_rejilla_es_DELTA_ESPERADO():
    """No es un filtro duro nuevo: es consecuencia del score y del corte que ya existía."""
    v = [_card("a", 100), _card("b", 100)]
    m = medir(v, [], [_card("a", 100)], [_card("b", 50)])
    legacy = {"dormitorios": 2}
    sombra = aplicar_operacion(legacy, OperacionMascotas.REQUERIR)
    assert m["movimientos_de_rejilla"] == 1
    assert clasificar_delta(legacy, sombra, m) is ClaseDelta.DELTA_ESPERADO


def test_un_universo_DISTINTO_nunca_es_esperado():
    m = medir([_card("a", 100)], [], [_card("z", 100)], [])
    assert not m["mismo_universo"]
    legacy = {"dormitorios": 2}
    assert clasificar_delta(legacy, aplicar_operacion(legacy, OperacionMascotas.REQUERIR),
                            m) is ClaseDelta.DELTA_INESPERADO


# ══ T26-T29 · RELACIÓN CON LA PERSISTENCIA ═════════════════════════════════════════


def test_T26_con_el_updater_APAGADO_la_relacion_es_NO_INTENTADA():
    assert relacion_de_persistencia(None, updater_encendido=False) \
        is RelacionPersistencia.NO_INTENTADA
    assert relacion_de_persistencia(EstadoActualizacion.CREADA, updater_encendido=False) \
        is RelacionPersistencia.NO_INTENTADA


@pytest.mark.parametrize("estado, esperado", [
    (EstadoActualizacion.CREADA, RelacionPersistencia.ALINEADA),
    (EstadoActualizacion.REPLAY, RelacionPersistencia.ALINEADA),
    (EstadoActualizacion.NO_OP, RelacionPersistencia.ALINEADA),
    (EstadoActualizacion.REBASEADA, RelacionPersistencia.DIVERGIDA),
    (EstadoActualizacion.CONFLICTO, RelacionPersistencia.DIVERGIDA),
    (EstadoActualizacion.FALLIDO, RelacionPersistencia.DIVERGIDA),
    (EstadoActualizacion.VACIO, RelacionPersistencia.NO_INTENTADA),
])
def test_T27_T28_T29_el_mapeo_de_desenlaces(estado, esperado):
    """`REBASEADA` diverge y la comparación sigue siendo válida: se comparó con el estado
    del turno, y lo que se registra es que lo persistido acabó siendo otro. Nunca se
    sustituye retrospectivamente uno por el otro.

    `VACIO` se clasifica aparte a propósito: no se intentó escribir porque no había nada que
    escribir. Presentarlo como fallo sería mentir sobre un camino legítimo.
    """
    assert relacion_de_persistencia(estado, updater_encendido=True) is esperado


def test_el_desenlace_desconocido_se_dice_como_tal():
    """Hoy el llamante NO conoce el desenlace —`actualizar_en_sombra` devuelve `None` y un
    guard de E3.2b.4 prohíbe asignar su resultado—, así que con el updater encendido la
    relación honesta es `NO_OBSERVABLE`. Reportar `NO_INTENTADA` sería falso."""
    assert relacion_de_persistencia(None, updater_encendido=True) \
        is RelacionPersistencia.NO_OBSERVABLE


def test_los_vocabularios_son_CERRADOS():
    """Meta-test: si alguien añade un valor, tiene que venir con su prueba."""
    assert {e.value for e in OperacionMascotas} == {"requerir", "retirar", "sin_senal",
                                                    "no_comparable"}
    assert {e.value for e in FuenteDelEstado} == {"turno_actual", "memoria_persistida",
                                                  "ninguna"}
    assert {e.value for e in ClaseDelta} == {"sin_delta", "delta_esperado",
                                             "delta_inesperado", "no_comparable"}
    assert {e.value for e in RelacionPersistencia} == {"alineada", "divergida",
                                                       "no_intentada", "no_observable"}
