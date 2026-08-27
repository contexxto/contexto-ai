"""E3.1b · Buyer Store contra PostgreSQL REAL.

Los dobles no bastan aquí, y la unidad anterior dejó claro por qué: en AUTH-READ-GATE.1 una
suite de 102 tests sobre una tabla en memoria dio verde mientras el SQL real fallaba al
prepararse. Una tabla que almacena filas no parsea SQL, no aplica `UNIQUE`, no toma
bloqueos y no ejecuta `FOR UPDATE`. Las dos garantías centrales de este store —idempotencia
y control de concurrencia— **viven en la base**, así que solo la base puede demostrarlas.

## Cómo se corre

```bash
docker compose up -d db
TEST_DATABASE_URL=postgresql+asyncpg://usuario:clave@localhost:5432/buyer_store_test \\
    python -m pytest tests/test_buyer_store_postgres.py -v
```

Sin `TEST_DATABASE_URL` se **saltan**. Un `skip` aquí significa "esta evidencia no se
produjo", y el reporte lo dice con esas palabras en vez de dar por buena una suite verde.

## Candados contra escribir en producción

`TEST_DATABASE_URL` es obligatoria y **no** cae por defecto a `settings.database_url`. La
fixture además aborta si la URL huele a Supabase o a un pooler. Estos tests hacen `DROP
TABLE` y crean cuentas: apuntarlos a producción sería destruir datos reales.

## `auth.users` en la base de pruebas

La FK de la 028 apunta a `auth.users`, que en producción la gestiona Supabase y en un
Postgres desnudo no existe. La fixture crea el mínimo (`id uuid primary key`) para poder
ejercitar **la FK de verdad**, incluido el borrado en cascada. No se relaja la FK para que
los tests pasen: se reproduce el entorno donde esa FK es válida.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import pathlib
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.buyer.store import (
    BuyerIdempotencyConflict,
    BuyerRevisionConflict,
    BuyerStoreError,
    anexar_revision,
    cargar_revision,
    cargar_ultima,
)
from app.contracts.buyer_v0 import BuyerContextV0, Objective

URL = os.getenv("TEST_DATABASE_URL", "")

pytestmark = [
    pytest.mark.skipif(not URL, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas"),
    pytest.mark.asyncio,
]

AUTH_MINIMO = (
    "CREATE SCHEMA IF NOT EXISTS auth",
    "CREATE TABLE IF NOT EXISTS auth.users (id uuid PRIMARY KEY)",
)


def _contexto(buyer_id: str, objetivo: Objective = Objective.UNKNOWN,
              stage: str | None = None) -> BuyerContextV0:
    return BuyerContextV0(
        buyer_id=buyer_id,
        objective=objetivo,
        stage=stage,
        updated_at=dt.datetime(2026, 8, 27, 12, 0, tzinfo=dt.timezone.utc),
    )


@pytest_asyncio.fixture
async def db():
    if "supabase.com" in URL or "pooler" in URL:
        pytest.fail("TEST_DATABASE_URL apunta a producción. Abortado.")

    motor = create_async_engine(URL)
    sesion = async_sessionmaker(motor, expire_on_commit=False)

    async with sesion() as s:
        await s.execute(text("DROP TABLE IF EXISTS buyer_context_revisions CASCADE"))
        await s.execute(text("DROP TABLE IF EXISTS buyer_context_heads CASCADE"))
        await s.execute(text("DROP TABLE IF EXISTS auth.users CASCADE"))
        for sentencia in AUTH_MINIMO:
            await s.execute(text(sentencia))
        await s.commit()

    async with sesion() as s:
        yield s

    await motor.dispose()


async def _migrar(db):
    """Aplica la 028 por SU CAMINO REAL: el aplicador de producción, no una copia.

    Es la lección de AUTH-READ-GATE.1: allí el aplicador tenía un fallo que los tests no
    veían porque ejecutaban el SQL por otra vía. Si `aplicar_migracion` no sabe ejecutar
    este fichero, estos tests tienen que fallar.
    """
    from app.esquema_requerido import aplicar_migracion
    await aplicar_migracion("migrations/028_buyer_context_store.sql", db=db)


async def _cuenta(db) -> str:
    """Crea un sujeto autenticado en el `auth.users` de pruebas."""
    uid = str(uuid.uuid4())
    await db.execute(text("INSERT INTO auth.users (id) VALUES (CAST(:u AS uuid))"), {"u": uid})
    await db.commit()
    return uid


@pytest_asyncio.fixture
async def migrada(db):
    await _migrar(db)
    return db


# ── 1-2 · la migración ─────────────────────────────────────────────────────────────


async def test_la_028_aplica_desde_cero(db):
    await _migrar(db)
    tablas = {f[0] for f in (await db.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name LIKE 'buyer_context%'"))).all()}
    assert tablas == {"buyer_context_heads", "buyer_context_revisions"}

    # La invariante de idempotencia es una restricción de la BASE, no una comprobación
    # en Python. Si no existe, el store tiene una ventana bajo concurrencia.
    restricciones = {f[0] for f in (await db.execute(text(
        "SELECT conname FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
        "WHERE t.relname = 'buyer_context_revisions'"))).all()}
    assert "uq_buyer_context_revisions_mensaje" in restricciones


async def test_la_028_es_idempotente(db):
    await _migrar(db)
    columnas = (await db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'buyer_context_revisions' ORDER BY ordinal_position"))).all()
    await _migrar(db)          # segunda pasada
    assert (await db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'buyer_context_revisions' ORDER BY ordinal_position"))).all() == columnas


# ── 3-6 · revisiones y round-trip ──────────────────────────────────────────────────


async def test_el_primer_estado_es_la_revision_cero(migrada):
    b = await _cuenta(migrada)
    r = await anexar_revision(b, "m-1", _contexto(b), None, db=migrada)

    assert r.revision == 0 and r.creada is True
    assert r.contexto.context_revision == 0


async def test_round_trip_exacto_por_el_contrato(migrada):
    b = await _cuenta(migrada)
    original = _contexto(b, Objective.RENT, stage="explorando")
    await anexar_revision(b, "m-1", original, None, db=migrada)

    leido = await cargar_ultima(b, db=migrada)
    assert isinstance(leido, BuyerContextV0)
    assert leido.objective is Objective.RENT
    assert leido.stage == "explorando"
    assert leido.buyer_id == b
    assert leido.updated_at == original.updated_at
    assert leido.context_revision == 0


async def test_el_segundo_mensaje_avanza_a_la_revision_uno(migrada):
    b = await _cuenta(migrada)
    await anexar_revision(b, "m-1", _contexto(b), None, db=migrada)
    r = await anexar_revision(b, "m-2", _contexto(b, Objective.BUY), 0, db=migrada)

    assert r.revision == 1 and r.creada is True
    assert (await cargar_ultima(b, db=migrada)).objective is Objective.BUY


async def test_el_historial_conserva_las_revisiones_anteriores(migrada):
    b = await _cuenta(migrada)
    await anexar_revision(b, "m-1", _contexto(b, Objective.RENT), None, db=migrada)
    await anexar_revision(b, "m-2", _contexto(b, Objective.BUY), 0, db=migrada)

    cero = await cargar_revision(b, 0, db=migrada)
    uno = await cargar_revision(b, 1, db=migrada)

    assert cero.objective is Objective.RENT, "la revisión 0 se sobrescribió"
    assert uno.objective is Objective.BUY
    assert (await db_filas(migrada, b)) == 2


async def db_filas(db, buyer_id) -> int:
    return (await db.execute(text(
        "SELECT count(*) FROM buyer_context_revisions WHERE buyer_id = CAST(:b AS uuid)"),
        {"b": buyer_id})).scalar()


# ── 7-8 · idempotencia ─────────────────────────────────────────────────────────────


async def test_el_reintento_del_mismo_mensaje_NO_crea_otra_revision(migrada):
    b = await _cuenta(migrada)
    ctx = _contexto(b, Objective.RENT)
    primera = await anexar_revision(b, "m-1", ctx, None, db=migrada)

    # El reintento llega con el `expected_revision` viejo, como llegaría de verdad.
    repetida = await anexar_revision(b, "m-1", ctx, None, db=migrada)

    assert repetida.creada is False
    assert repetida.revision == primera.revision == 0
    assert await db_filas(migrada, b) == 1


async def test_el_mismo_mensaje_con_estado_DISTINTO_falla_ruidosamente(migrada):
    """La idempotencia no puede ocultar divergencia.

    Si la misma evidencia produce dos estados, lo que hay delante es un extractor no
    determinista o un replay corrupto. Devolver lo viejo en silencio dejaría ese fallo
    invisible justo donde más importa.
    """
    b = await _cuenta(migrada)
    await anexar_revision(b, "m-1", _contexto(b, Objective.RENT), None, db=migrada)

    with pytest.raises(BuyerIdempotencyConflict):
        await anexar_revision(b, "m-1", _contexto(b, Objective.BUY), None, db=migrada)

    assert await db_filas(migrada, b) == 1, "hubo escritura tras el conflicto"
    assert (await cargar_ultima(b, db=migrada)).objective is Objective.RENT


# ── 9-10 · concurrencia ────────────────────────────────────────────────────────────


async def test_una_revision_esperada_rancia_no_sobrescribe(migrada):
    b = await _cuenta(migrada)
    await anexar_revision(b, "m-1", _contexto(b), None, db=migrada)
    await anexar_revision(b, "m-2", _contexto(b, Objective.BUY), 0, db=migrada)

    # Llega alguien que leyó cuando la vigente era 0.
    with pytest.raises(BuyerRevisionConflict):
        await anexar_revision(b, "m-3", _contexto(b, Objective.RENT), 0, db=migrada)

    assert await db_filas(migrada, b) == 2
    assert (await cargar_ultima(b, db=migrada)).objective is Objective.BUY


async def test_dos_conexiones_REALES_compitiendo_por_la_misma_revision(migrada):
    """LA PRUEBA QUE NINGÚN DOBLE PUEDE DAR.

    Dos conexiones distintas, con transacciones distintas, escribiendo desde el mismo
    `expected_revision`. El `FOR UPDATE` de la cabeza las serializa: exactamente una crea
    la revisión siguiente y la otra encuentra el estado ya avanzado.

    Sin bloqueo, ambas leerían la misma revisión, ambas se creerían al día, y una pisaría
    a la otra sin que nadie se entere — que es exactamente el `lost update` que este
    módulo existe para impedir.
    """
    b = await _cuenta(migrada)
    await anexar_revision(b, "m-0", _contexto(b), None, db=migrada)

    motor = create_async_engine(URL)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)

    async def escribir(mensaje: str, objetivo: Objective):
        async with fabrica() as s:
            try:
                return await anexar_revision(b, mensaje, _contexto(b, objetivo), 0, db=s)
            except BuyerStoreError as e:
                return e

    try:
        a, c = await asyncio.gather(
            escribir("m-a", Objective.RENT),
            escribir("m-b", Objective.BUY),
        )
    finally:
        await motor.dispose()

    exitos = [r for r in (a, c) if not isinstance(r, Exception)]
    conflictos = [r for r in (a, c) if isinstance(r, BuyerRevisionConflict)]

    assert len(exitos) == 1, f"escribieron {len(exitos)}: hubo lost update o doble revisión"
    assert len(conflictos) == 1, f"el perdedor no dio BuyerRevisionConflict: {a} / {c}"
    assert exitos[0].revision == 1

    assert await db_filas(migrada, b) == 2, "el historial tiene revisiones de más"
    revisiones = [f[0] for f in (await migrada.execute(text(
        "SELECT context_revision FROM buyer_context_revisions "
        "WHERE buyer_id = CAST(:b AS uuid) ORDER BY context_revision"), {"b": b})).all()]
    assert revisiones == [0, 1], f"revisiones no monotónicas: {revisiones}"


# ── 11-13 · aislamiento, identidad y ciclo de vida ─────────────────────────────────


async def test_dos_compradores_no_mezclan_revisiones(migrada):
    b1, b2 = await _cuenta(migrada), await _cuenta(migrada)
    await anexar_revision(b1, "m-1", _contexto(b1, Objective.RENT), None, db=migrada)
    await anexar_revision(b2, "m-1", _contexto(b2, Objective.BUY), None, db=migrada)

    assert (await cargar_ultima(b1, db=migrada)).objective is Objective.RENT
    assert (await cargar_ultima(b2, db=migrada)).objective is Objective.BUY
    # El mismo `source_message_id` en dos compradores distintos es legítimo: la unicidad
    # es por (buyer_id, source_message_id), no global.
    assert await db_filas(migrada, b1) == 1 and await db_filas(migrada, b2) == 1


async def test_un_contexto_de_OTRO_comprador_no_se_persiste(migrada):
    b1, b2 = await _cuenta(migrada), await _cuenta(migrada)

    with pytest.raises(BuyerStoreError):
        await anexar_revision(b1, "m-1", _contexto(b2), None, db=migrada)

    assert await db_filas(migrada, b1) == 0
    assert await cargar_ultima(b1, db=migrada) is None


async def test_borrar_la_cuenta_borra_cabeza_e_historial(migrada):
    b = await _cuenta(migrada)
    await anexar_revision(b, "m-1", _contexto(b), None, db=migrada)
    await anexar_revision(b, "m-2", _contexto(b, Objective.BUY), 0, db=migrada)
    assert await db_filas(migrada, b) == 2

    await migrada.execute(text("DELETE FROM auth.users WHERE id = CAST(:u AS uuid)"), {"u": b})
    await migrada.commit()

    assert await db_filas(migrada, b) == 0, "el historial sobrevivió a la cuenta"
    assert (await migrada.execute(text(
        "SELECT count(*) FROM buyer_context_heads WHERE buyer_id = CAST(:b AS uuid)"),
        {"b": b})).scalar() == 0


async def test_un_buyer_id_sin_cuenta_no_puede_persistir(migrada):
    """La FK es real: no hay comprador sin sujeto autenticado detrás."""
    huerfano = str(uuid.uuid4())
    with pytest.raises(Exception) as e:
        await anexar_revision(huerfano, "m-1", _contexto(huerfano), None, db=migrada)
    assert "foreign key" in str(e.value).lower() or "violates" in str(e.value).lower()


# ── 14 · una fila corrupta no se presenta como contexto válido ─────────────────────


async def test_una_fila_que_no_valida_falla_LOUD(migrada):
    from app.buyer.store import BuyerContextCorrupto

    b = await _cuenta(migrada)
    await anexar_revision(b, "m-1", _contexto(b), None, db=migrada)

    # Se corrompe el snapshot a mano: `buyer_id` es obligatorio en el contrato.
    await migrada.execute(text(
        "UPDATE buyer_context_revisions SET context_json = CAST(:j AS jsonb) "
        "WHERE buyer_id = CAST(:b AS uuid)"),
        {"b": b, "j": '{"version": "buyer-context-v0"}'})
    await migrada.commit()

    with pytest.raises(BuyerContextCorrupto):
        await cargar_ultima(b, db=migrada)
