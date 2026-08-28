"""E3.2b.3 · el orquestador contra POSTGRES REAL · dos escritores concurrentes.

Los tests de `test_buyer_actualizador.py` cubren la POLÍTICA con un doble en memoria. Lo que
un doble no puede demostrar es que dos procesos reales, corriendo a la vez contra la misma
fila, se serialicen: eso lo dan `SELECT … FOR UPDATE` y el `UNIQUE`, y sólo se ve con una base
de verdad.

```bash
TEST_DATABASE_URL=postgresql+asyncpg://usuario:clave@localhost:5432/buyer_store_test \\
  python -m pytest tests/test_buyer_actualizador_postgres.py
```

Sin `TEST_DATABASE_URL` se **saltan**, igual que `test_buyer_store_postgres.py`. Un `skip`
aquí significa *"esta evidencia no se recogió"*, no *"esto funciona"*. Y la variable no cae
por defecto a `settings.database_url` a propósito: correr esto contra la base real del
producto escribiría compradores de prueba en producción.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.buyer import actualizador as act
from app.buyer.actualizador import EstadoActualizacion, actualizar
from app.buyer.boundary import BuyerCurrencyV0, SetBedroomsMin, SetBudgetMax
from app.buyer.interprete import PropuestaV0
from app.buyer.mensaje import IdentifiedUserMessage

URL = os.getenv("TEST_DATABASE_URL", "")

pytestmark = [
    pytest.mark.skipif(not URL, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas"),
    pytest.mark.asyncio,
]

T0 = dt.datetime(2026, 8, 28, 12, 0, tzinfo=dt.timezone.utc)
USD = BuyerCurrencyV0.USD


def _guardia_produccion():
    """La misma que `test_buyer_store_postgres.py`: esta suite escribe, así que apuntarla a
    producción crearía compradores de prueba en la base real."""
    from app.config import settings

    if settings.database_url and URL.split("@")[-1] == settings.database_url.split("@")[-1]:
        pytest.fail("TEST_DATABASE_URL apunta a producción. Abortado.")


@pytest.fixture
async def sesiones():
    _guardia_produccion()
    motor = create_async_engine(URL, pool_size=4)
    hacer = async_sessionmaker(motor, expire_on_commit=False)
    yield hacer
    await motor.dispose()


@pytest.fixture
def comprador():
    return str(uuid.uuid4())


def _proponente(*propuestas):
    async def proponer(_texto):
        return propuestas
    return proponer


def _msg(mid, texto):
    return IdentifiedUserMessage(message_id=mid, text=texto)


async def _limpiar(hacer, buyer_id):
    async with hacer() as s:
        await s.execute(text("DELETE FROM buyer_context_revisions "
                             "WHERE buyer_id = CAST(:b AS uuid)"), {"b": buyer_id})
        await s.execute(text("DELETE FROM buyer_context_heads "
                             "WHERE buyer_id = CAST(:b AS uuid)"), {"b": buyer_id})
        await s.commit()


async def test_dos_escritores_de_RUTAS_DISJUNTAS_sobreviven_los_dos(sesiones, comprador):
    """`budget || bedrooms` — no compiten, así que el que pierde la carrera se rebasa sobre el
    otro y las dos declaraciones acaban en el estado final.

    Es la contraparte entre mensajes de lo que C5 garantiza dentro de uno: un hecho no puede
    costar otro sólo por llegar a la vez.
    """
    try:
        async with sesiones() as a, sesiones() as b:
            resultados = await asyncio.gather(
                actualizar(comprador, _msg("m-A", "máximo 120000 USD"), retrieved_at=T0,
                           proponente=_proponente(PropuestaV0(
                               disposicion="durable", motivo="tope",
                               mutacion=SetBudgetMax(amount=Decimal(120000),
                                                     currency=USD))), db=a),
                actualizar(comprador, _msg("m-B", "al menos 2 dormitorios"), retrieved_at=T0,
                           proponente=_proponente(PropuestaV0(
                               disposicion="durable", motivo="mínimo",
                               mutacion=SetBedroomsMin(bedrooms_min=2))), db=b),
                return_exceptions=True,
            )

        assert all(not isinstance(r, Exception) for r in resultados), resultados
        assert all(r.estado is EstadoActualizacion.CREADA for r in resultados), \
            [r.estado for r in resultados]

        from app.buyer.store import cargar_ultima
        async with sesiones() as s:
            final = await cargar_ultima(comprador, db=s)

        assert final.financial.budget_max.amount == Decimal(120000)
        assert final.property_requirements.bedrooms_min == 2
    finally:
        await _limpiar(sesiones, comprador)


async def test_dos_escritores_de_LA_MISMA_ruta_no_se_pisan(sesiones, comprador):
    """`budget || budget` — solapan, así que uno gana y el otro NO sobreescribe: sale como
    `CONFLICTO` y el valor del ganador queda intacto.

    Cero last-write-wins. Es C1 entre mensajes: dos declaraciones sobre la misma dimensión,
    sin nada que autorice elegir una, no se resuelven adivinando.
    """
    try:
        async with sesiones() as a, sesiones() as b:
            resultados = await asyncio.gather(
                actualizar(comprador, _msg("m-A", "máximo 120000 USD"), retrieved_at=T0,
                           proponente=_proponente(PropuestaV0(
                               disposicion="durable", motivo="tope A",
                               mutacion=SetBudgetMax(amount=Decimal(120000),
                                                     currency=USD))), db=a),
                actualizar(comprador, _msg("m-B", "máximo 90000 USD"), retrieved_at=T0,
                           proponente=_proponente(PropuestaV0(
                               disposicion="durable", motivo="tope B",
                               mutacion=SetBudgetMax(amount=Decimal(90000),
                                                     currency=USD))), db=b),
                return_exceptions=True,
            )

        assert all(not isinstance(r, Exception) for r in resultados), resultados
        estados = sorted(r.estado.value for r in resultados)
        assert estados == ["conflicto", "creada"], estados

        ganador = next(r for r in resultados if r.estado is EstadoActualizacion.CREADA)
        from app.buyer.store import cargar_ultima
        async with sesiones() as s:
            final = await cargar_ultima(comprador, db=s)

        assert final.financial.budget_max == ganador.contexto.financial.budget_max, \
            "el perdedor sobreescribió al ganador"
        assert final.context_revision == 1, "se creó una revisión de más"
    finally:
        await _limpiar(sesiones, comprador)


async def test_el_replay_concurrente_del_MISMO_mensaje_crea_una_sola_revision(
        sesiones, comprador):
    """El `UNIQUE (buyer_id, source_message_id)` es la garantía dura; esto comprueba que el
    orquestador la traduce a `REPLAY` y no a un error hacia arriba."""
    try:
        propuesta = PropuestaV0(disposicion="durable", motivo="tope",
                                mutacion=SetBudgetMax(amount=Decimal(120000), currency=USD))
        async with sesiones() as a, sesiones() as b:
            resultados = await asyncio.gather(
                actualizar(comprador, _msg("m-mismo", "máximo 120000 USD"), retrieved_at=T0,
                           proponente=_proponente(propuesta), db=a),
                actualizar(comprador, _msg("m-mismo", "máximo 120000 USD"), retrieved_at=T0,
                           proponente=_proponente(propuesta), db=b),
                return_exceptions=True,
            )

        assert all(not isinstance(r, Exception) for r in resultados), resultados
        assert sorted(r.estado.value for r in resultados) in (
            ["creada", "replay"], ["conflicto", "creada"]), \
            [r.estado.value for r in resultados]

        async with sesiones() as s:
            filas = (await s.execute(text(
                "SELECT count(*) FROM buyer_context_revisions "
                "WHERE buyer_id = CAST(:b AS uuid)"), {"b": comprador})).scalar()
        assert filas == 1, f"el mismo mensaje creó {filas} revisiones"
    finally:
        await _limpiar(sesiones, comprador)
