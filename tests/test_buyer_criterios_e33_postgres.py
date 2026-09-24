"""F3-E3.3-HARD-SOFT-R1 · los criterios contra PostgreSQL REAL.

La idempotencia offline compara objetos en memoria. La de verdad compara lo que VUELVE de
un JSONB: un `80.0` que regresara como `80`, o un instante con otro formato, haría que el
replay honesto de un mensaje pareciera divergencia — y sólo la base puede demostrar que no.

Mismas fixtures y mismos candados que `test_buyer_store_postgres.py`: sin
`TEST_DATABASE_URL` se saltan, y un `skip` significa "esta evidencia no se produjo".
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from app.buyer.boundary import (
    BuyerCurrencyV0, BuyerFieldV0, ClearPetsRequired, DeclaracionRigidezV0, RigidezV0,
    SetAreaM2Min, SetBudgetMax, SetPetsRequired,
)
from app.buyer.extractor import AfirmacionDurable, construir_lote
from app.buyer.mensaje import IdentifiedUserMessage
from app.buyer.reductor import reducir
from app.buyer.store import (
    BuyerIdempotencyConflict, _canonico, anexar_revision, cargar_ultima,
)
from app.contracts.buyer_v0 import BuyerContextV0, CriterionStatus
from tests.test_buyer_store_postgres import (  # noqa: F401 — fixtures
    URL, _cuenta, db, db_filas, migrada,
)

pytestmark = [
    pytest.mark.skipif(not URL, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas"),
    pytest.mark.asyncio,
]

T0 = dt.datetime(2026, 9, 23, 12, 0, tzinfo=dt.timezone.utc)
F = BuyerFieldV0


def _lote(mid, afirmaciones=(), rigideces=()):
    return construir_lote(IdentifiedUserMessage(message_id=mid, text="x"),
                          [AfirmacionDurable(mutacion=m, motivo="x") for m in afirmaciones],
                          list(rigideces))


def _rig(campo, rigidez):
    return DeclaracionRigidezV0(campo=campo, rigidez=rigidez)


async def _con_los_cuatro_estados(migrada, b):
    """hard ACTIVE · soft ACTIVE con float · RETRACTED · y un valor Decimal→int."""
    c = BuyerContextV0(buyer_id=b, updated_at=T0)
    pasos = [
        ("m-1", [SetBudgetMax(amount=Decimal(900), currency=BuyerCurrencyV0.USD),
                 SetAreaM2Min(area_m2_min=80.0), SetPetsRequired()],
         [_rig(F.BUDGET_MAX, RigidezV0.ESTRICTA)]),
        ("m-2", [ClearPetsRequired()], [_rig(F.PETS_REQUIRED, RigidezV0.ESTRICTA)]),
    ]
    revision = None
    for mid, mutaciones, rigideces in pasos:
        c = reducir(c, _lote(mid, mutaciones, rigideces), T0)
        persistida = await anexar_revision(b, mid, c, revision, db=migrada)
        await migrada.commit()
        c, revision = persistida.contexto, persistida.revision
    return c, revision


async def test_los_criterios_hacen_el_viaje_por_JSONB_sin_cambiar(migrada):
    b = await _cuenta(migrada)
    escrito, _ = await _con_los_cuatro_estados(migrada, b)
    leido = await cargar_ultima(b, db=migrada)

    assert [(k.criterion_id, k.status) for k in leido.hard_constraints] == [
        ("budget_max", CriterionStatus.ACTIVE), ("pets_required", CriterionStatus.RETRACTED)]
    assert [k.criterion_id for k in leido.soft_preferences] == ["area_m2_min"]
    area = leido.soft_preferences[0]
    assert area.value == 80.0 and isinstance(area.value, float)
    assert leido.hard_constraints[0].value == 900 and isinstance(
        leido.hard_constraints[0].value, int)
    assert leido.hard_constraints == escrito.hard_constraints
    assert leido.soft_preferences == escrito.soft_preferences


async def test_el_REPLAY_de_una_rigidez_es_idempotente_en_la_base(migrada):
    """El caso de RETRY IDEMPOTENT: mismo mensaje, otro `retrieved_at`, contra lo que se
    leyó del JSONB. Sin la limpieza de la evidencia de los criterios en `_canonico`, esto
    es `BuyerIdempotencyConflict`."""
    b = await _cuenta(migrada)
    c, revision = await _con_los_cuatro_estados(migrada, b)

    lote = _lote("m-3", rigideces=[_rig(F.BUDGET_MAX, RigidezV0.FLEXIBLE)])
    primera = await anexar_revision(b, "m-3", reducir(c, lote, T0), revision, db=migrada)
    await migrada.commit()

    tarde = reducir(c, lote, T0 + dt.timedelta(minutes=7))
    assert _canonico(tarde) == _canonico(primera.contexto)
    repetida = await anexar_revision(b, "m-3", tarde, revision, db=migrada)
    await migrada.commit()

    assert repetida.creada is False
    assert repetida.revision == primera.revision
    assert await db_filas(migrada, b) == 3
    assert [k.criterion_id for k in repetida.contexto.soft_preferences] == [
        "budget_max", "area_m2_min"]


async def test_el_mismo_mensaje_con_OTRA_rigidez_falla_ruidosamente(migrada):
    b = await _cuenta(migrada)
    c, revision = await _con_los_cuatro_estados(migrada, b)

    await anexar_revision(b, "m-3", reducir(
        c, _lote("m-3", rigideces=[_rig(F.BUDGET_MAX, RigidezV0.FLEXIBLE)]), T0),
        revision, db=migrada)
    await migrada.commit()

    with pytest.raises(BuyerIdempotencyConflict):
        await anexar_revision(b, "m-3", reducir(
            c, _lote("m-3", rigideces=[_rig(F.AREA_M2_MIN, RigidezV0.ESTRICTA)]), T0),
            revision, db=migrada)
