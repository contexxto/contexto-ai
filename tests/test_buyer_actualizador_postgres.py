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


AUTH_MINIMO = (
    "CREATE SCHEMA IF NOT EXISTS auth",
    "CREATE TABLE IF NOT EXISTS auth.users (id uuid PRIMARY KEY)",
)
"""La FK de la 028 apunta a `auth.users`, que en producción gestiona Supabase. Mismo mínimo
que usa `test_buyer_store_postgres.py`."""


@pytest.fixture
async def sesiones():
    """Deja el esquema listo y devuelve una FÁBRICA de sesiones — no una sesión.

    Cada escritor concurrente necesita la SUYA: compartir una sesión entre dos coroutines no
    mediría concurrencia, mediría dos escrituras en la misma transacción.

    La migración se aplica por su camino real (`app.esquema_requerido`), no ejecutando el SQL
    a mano: es la lección de AUTH-READ-GATE.1 — si el aplicador de producción no sabe leer
    este fichero, estos tests tienen que enterarse.
    """
    _guardia_produccion()
    motor = create_async_engine(URL, pool_size=5)
    hacer = async_sessionmaker(motor, expire_on_commit=False)

    from app.esquema_requerido import aplicar_migracion

    async with hacer() as s:
        await s.execute(text("DROP TABLE IF EXISTS buyer_context_revisions CASCADE"))
        await s.execute(text("DROP TABLE IF EXISTS buyer_context_heads CASCADE"))
        await s.execute(text("DROP TABLE IF EXISTS auth.users CASCADE"))
        for sentencia in AUTH_MINIMO:
            await s.execute(text(sentencia))
        await s.commit()
        await aplicar_migracion("migrations/028_buyer_context_store.sql", db=s)
        await aplicar_migracion("migrations/029_buyer_source_message_id_nonempty.sql", db=s)
        await s.commit()

    yield hacer
    await motor.dispose()


@pytest.fixture
async def comprador(sesiones):
    """Un sujeto autenticado real: la 028 exige FK contra `auth.users`, y esa exigencia es
    parte de lo que se está probando —la raíz del comprador es el sujeto autenticado."""
    uid = str(uuid.uuid4())
    async with sesiones() as s:
        await s.execute(text("INSERT INTO auth.users (id) VALUES (CAST(:u AS uuid))"),
                        {"u": uid})
        await s.commit()
    return uid


def _proponente(*propuestas):
    async def proponer(_texto):
        return propuestas
    return proponer


def _msg(mid, texto):
    return IdentifiedUserMessage(message_id=mid, text=texto)


async def _escritor(hacer, buyer_id, mensaje, propuesta):
    """Un escritor COMPLETO: abre su sesión, actualiza y **hace commit dentro**.

    Es lo que hace que el test mida concurrencia en vez de colgarse. El store congela que con
    `db=...` el commit es del llamante; si el `commit` viviera después del `gather`, el primer
    escritor retendría su transacción y su `FOR UPDATE` mientras el segundo espera el lock, y
    el `gather` esperaría a los dos. Deadlock — y al salir sin commit, la escritura se iría en
    rollback.
    """
    async with hacer() as sesion:
        try:
            resultado = await actualizar(buyer_id, mensaje, retrieved_at=T0,
                                         proponente=_proponente(propuesta), db=sesion)
            await sesion.commit()
            return resultado
        except Exception:
            await sesion.rollback()
            raise


async def _limpiar(hacer, buyer_id):
    async with hacer() as s:
        await s.execute(text("DELETE FROM buyer_context_revisions "
                             "WHERE buyer_id = CAST(:b AS uuid)"), {"b": buyer_id})
        await s.execute(text("DELETE FROM buyer_context_heads "
                             "WHERE buyer_id = CAST(:b AS uuid)"), {"b": buyer_id})
        await s.commit()


async def test_dos_escritores_de_RUTAS_DISJUNTAS_sobreviven_los_dos(sesiones, comprador):
    """`budget || bedrooms` sobre un comprador NUEVO — ninguna toca lo de la otra, así que la
    que pierde la carrera se rebasa y las dos declaraciones acaban en el estado final.

    Es la contraparte entre mensajes de lo que C5 garantiza dentro de uno: un hecho no puede
    costar otro sólo por llegar a la vez. Y es el test que E3.2b.3 tenía SALTADO mientras el
    código lo contradecía — `rutas_divergentes(None, …)` devolvía las cinco rutas.
    """
    try:
        resultados = await asyncio.gather(
            _escritor(sesiones, comprador, _msg("m-A", "máximo 120000 USD"),
                      PropuestaV0(disposicion="durable", motivo="tope",
                                  mutacion=SetBudgetMax(amount=Decimal(120000),
                                                        currency=USD))),
            _escritor(sesiones, comprador, _msg("m-B", "al menos 2 dormitorios"),
                      PropuestaV0(disposicion="durable", motivo="mínimo",
                                  mutacion=SetBedroomsMin(bedrooms_min=2))),
            return_exceptions=True,
        )

        assert all(not isinstance(r, Exception) for r in resultados), resultados
        assert [r.estado for r in resultados] == [EstadoActualizacion.CREADA] * 2,             [r.estado for r in resultados]

        from app.buyer.store import cargar_ultima
        async with sesiones() as s:
            final = await cargar_ultima(comprador, db=s)

        assert final.financial.budget_max.amount == Decimal(120000)
        assert final.property_requirements.bedrooms_min == 2
        assert final.context_revision == 1, "dos escrituras ⇒ revisiones 0 y 1"
    finally:
        await _limpiar(sesiones, comprador)


async def test_dos_escritores_de_LA_MISMA_ruta_no_se_pisan(sesiones, comprador):
    """`budget || budget` sobre un comprador nuevo — solapan, así que uno gana y el otro NO
    sobreescribe. Cero last-write-wins: es C1 entre mensajes."""
    try:
        resultados = await asyncio.gather(
            _escritor(sesiones, comprador, _msg("m-A", "máximo 120000 USD"),
                      PropuestaV0(disposicion="durable", motivo="tope A",
                                  mutacion=SetBudgetMax(amount=Decimal(120000),
                                                        currency=USD))),
            _escritor(sesiones, comprador, _msg("m-B", "máximo 90000 USD"),
                      PropuestaV0(disposicion="durable", motivo="tope B",
                                  mutacion=SetBudgetMax(amount=Decimal(90000),
                                                        currency=USD))),
            return_exceptions=True,
        )

        assert all(not isinstance(r, Exception) for r in resultados), resultados
        assert sorted(r.estado.value for r in resultados) == ["conflicto", "creada"],             [r.estado.value for r in resultados]

        ganador = next(r for r in resultados if r.estado is EstadoActualizacion.CREADA)
        from app.buyer.store import cargar_ultima
        async with sesiones() as s:
            final = await cargar_ultima(comprador, db=s)

        assert final.financial.budget_max == ganador.contexto.financial.budget_max,             "el perdedor sobreescribió al ganador"
        assert final.context_revision == 0, "el perdedor no escribió: sólo hay revisión 0"
    finally:
        await _limpiar(sesiones, comprador)


async def test_el_replay_concurrente_del_MISMO_mensaje_da_CREADA_mas_REPLAY(
        sesiones, comprador):
    """`CREADA + REPLAY`, y **no** `CREADA + CONFLICTO`.

    El store consulta el `source_message_id` ANTES de diagnosticar conflicto de revisión, y
    esa precedencia existe justo para distinguir un reintento de una carrera. Aceptar
    `CONFLICTO` aquí habría dado por bueno que el sistema confunda las dos cosas.
    """
    try:
        propuesta = PropuestaV0(disposicion="durable", motivo="tope",
                                mutacion=SetBudgetMax(amount=Decimal(120000), currency=USD))
        resultados = await asyncio.gather(
            _escritor(sesiones, comprador, _msg("m-mismo", "máximo 120000 USD"), propuesta),
            _escritor(sesiones, comprador, _msg("m-mismo", "máximo 120000 USD"), propuesta),
            return_exceptions=True,
        )

        assert all(not isinstance(r, Exception) for r in resultados), resultados
        assert sorted(r.estado.value for r in resultados) == ["creada", "replay"],             [r.estado.value for r in resultados]

        async with sesiones() as s:
            filas = (await s.execute(text(
                "SELECT count(*) FROM buyer_context_revisions "
                "WHERE buyer_id = CAST(:b AS uuid)"), {"b": comprador})).scalar()
        assert filas == 1, f"el mismo mensaje creó {filas} revisiones"
    finally:
        await _limpiar(sesiones, comprador)
