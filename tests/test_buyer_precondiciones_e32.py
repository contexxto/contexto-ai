"""E3.2 · 1 — las tres precondiciones que E3.1b dejó abiertas, cerradas y probadas.

Salieron de la revisión de código del PR #131 y quedaron escritas en el §10 del reporte 14.
Ninguna era explotable en E3.1b —el store no tenía consumidor productivo— pero las tres se
rompen **justo al conectar el store**, que es lo que hace E3.2.

```
1A  updated_at es metadata del store, no estado del comprador
1B  la propiedad de la transacción sigue a la propiedad de la sesión
1C  source_message_id no puede ser vacío — en Python Y en el esquema
```

Los tests que necesitan motor están marcados y se saltan sin `TEST_DATABASE_URL`. Los de 1A
y el lado Python de 1C no lo necesitan.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.buyer.store import (
    BuyerRevisionConflict,
    BuyerStoreError,
    _canonico,
    anexar_revision,
    cargar_ultima,
)
from app.contracts.buyer_v0 import BuyerContextV0, Objective

URL = os.getenv("TEST_DATABASE_URL", "")
necesita_motor = pytest.mark.skipif(
    not URL, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas")

T1 = dt.datetime(2026, 8, 27, 12, 0, tzinfo=dt.timezone.utc)
T2 = dt.datetime(2026, 8, 28, 9, 30, tzinfo=dt.timezone.utc)


def _ctx(buyer_id, ts=T1, **extra) -> BuyerContextV0:
    return BuyerContextV0(buyer_id=buyer_id, updated_at=ts, **extra)


# ══ 1A · `updated_at` es metadata ═══════════════════════════════════════════════════


def test_1A_updated_at_NO_entra_en_la_forma_canonica():
    """El fallo que E3.1b no podía ver: sus fixtures usaban un timestamp fijo, así que la
    propiedad no era observable con esa entrada."""
    b = str(uuid.uuid4())
    assert _canonico(_ctx(b, T1)) == _canonico(_ctx(b, T2))


def test_1A_un_cambio_REAL_de_estado_sigue_diferenciandose():
    """Excluir `updated_at` no puede volverse una excusa para tragar divergencias."""
    b = str(uuid.uuid4())
    assert _canonico(_ctx(b, T1, objective=Objective.RENT)) != \
           _canonico(_ctx(b, T2, objective=Objective.BUY))


@necesita_motor
@pytest.mark.asyncio
async def test_1A_el_reintento_con_updated_at_DISTINTO_es_idempotente(migrada):
    """EL TEST QUE E3.1b NO TENÍA.

    Mismo comprador, mismo `source_message_id`, mismo estado semántico, `updated_at`
    distintos. Antes de E3.2 esto daba `BuyerIdempotencyConflict` — el store acusaba de no
    determinista a un extractor que sí lo era.
    """
    b = await _cuenta(migrada)
    primera = await anexar_revision(b, "m-1", _ctx(b, T1, objective=Objective.RENT), None,
                                    db=migrada)
    await migrada.commit()

    repetida = await anexar_revision(b, "m-1", _ctx(b, T2, objective=Objective.RENT), None,
                                     db=migrada)

    assert repetida.creada is False
    assert repetida.revision == primera.revision
    assert await _filas(migrada, b) == 1


@necesita_motor
@pytest.mark.asyncio
async def test_1A_el_store_ASIGNA_updated_at_ignorando_el_del_llamante(migrada):
    """El updater no debe generar `datetime.now()` dentro del payload semántico; el instante
    de persistencia lo pone el store."""
    b = await _cuenta(migrada)
    antiguo = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)

    r = await anexar_revision(b, "m-1", _ctx(b, antiguo), None, db=migrada)
    await migrada.commit()

    assert r.contexto.updated_at != antiguo, "se conservó el timestamp del llamante"
    assert r.contexto.updated_at.tzinfo is not None, "el instante persistido no lleva zona"
    leido = await cargar_ultima(b, db=migrada)
    assert leido.updated_at == r.contexto.updated_at


# ══ 1B · propiedad de la transacción ════════════════════════════════════════════════


@necesita_motor
@pytest.mark.asyncio
async def test_1B_con_sesion_PROPIA_el_store_confirma(motor):
    """Caso A: `db=None` → el store abre su sesión y es dueño del commit."""
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as s:
        b = await _cuenta(s)

    import app.buyer.store as almacen
    original = almacen.AsyncSessionLocal
    almacen.AsyncSessionLocal = fabrica
    try:
        await anexar_revision(b, "m-1", _ctx(b), None)          # sin db=
    finally:
        almacen.AsyncSessionLocal = original

    async with fabrica() as verificacion:
        assert await cargar_ultima(b, db=verificacion) is not None, "no quedó confirmado"


@necesita_motor
@pytest.mark.asyncio
async def test_1B_con_sesion_INYECTADA_el_rollback_del_llamante_manda(motor):
    """Caso B: el store escribe, el llamante deshace → no queda nada.

    Es la prueba de que el store dejó de confirmar por su cuenta. Con el `commit()` de
    E3.1b, esta escritura habría sobrevivido al rollback del llamante.
    """
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as s:
        b = await _cuenta(s)

    async with fabrica() as s:
        await anexar_revision(b, "m-1", _ctx(b), None, db=s)
        await s.rollback()

    async with fabrica() as verificacion:
        assert await cargar_ultima(b, db=verificacion) is None, "sobrevivió al rollback"


@necesita_motor
@pytest.mark.asyncio
async def test_1B_con_sesion_INYECTADA_el_commit_del_llamante_persiste(motor):
    """Caso C: el mismo camino, confirmado por quien es dueño de la transacción."""
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as s:
        b = await _cuenta(s)

    async with fabrica() as s:
        await anexar_revision(b, "m-1", _ctx(b, objective=Objective.BUY), None, db=s)
        await s.commit()

    async with fabrica() as verificacion:
        leido = await cargar_ultima(b, db=verificacion)
        assert leido is not None and leido.objective is Objective.BUY


@necesita_motor
@pytest.mark.asyncio
async def test_1B_al_fallar_NO_deshace_el_trabajo_del_llamante(motor):
    """Caso D, y el que de verdad justifica el cambio.

    El llamante tiene trabajo propio pendiente en su sesión. El store levanta
    `BuyerRevisionConflict`. Con el `rollback()` de E3.1b, ese trabajo ajeno —que el store
    nunca vio— desaparecía sin que nadie lo pidiera.
    """
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as s:
        b = await _cuenta(s)
        await s.execute(text("CREATE TABLE IF NOT EXISTS trabajo_ajeno (nota text)"))
        await s.commit()

    async with fabrica() as s:
        await s.execute(text("INSERT INTO trabajo_ajeno (nota) VALUES ('del llamante')"))

        # `expected_revision=5` sobre un comprador sin estado: conflicto seguro.
        with pytest.raises(BuyerRevisionConflict):
            await anexar_revision(b, "m-1", _ctx(b), 5, db=s)

        # El trabajo del llamante sigue vivo en SU transacción.
        vivo = (await s.execute(text("SELECT count(*) FROM trabajo_ajeno"))).scalar()
        assert vivo == 1, "el store deshizo trabajo que no era suyo"
        await s.commit()

    async with fabrica() as verificacion:
        assert (await verificacion.execute(
            text("SELECT count(*) FROM trabajo_ajeno"))).scalar() == 1


# ══ 1C · `source_message_id` no vacío ═══════════════════════════════════════════════


@pytest.mark.parametrize("vacio", ["", "   ", "\t", "\n"])
def test_1C_python_rechaza_el_message_id_vacio_ANTES_de_la_base(vacio):
    b = str(uuid.uuid4())
    with pytest.raises(BuyerStoreError, match="source_message_id"):
        asyncio.run(anexar_revision(b, vacio, _ctx(b), None, db=None))


@necesita_motor
@pytest.mark.asyncio
@pytest.mark.parametrize("vacio", ["", "   "])
async def test_1C_el_ESQUEMA_tambien_lo_rechaza(migrada, vacio):
    """La tercera capa. Las dos primeras protegen UN camino; un backfill o un segundo
    escritor futuro no pasan por `anexar_revision`."""
    b = await _cuenta(migrada)
    with pytest.raises(Exception) as e:
        await migrada.execute(text(
            "INSERT INTO buyer_context_heads (buyer_id, current_revision) "
            "VALUES (CAST(:b AS uuid), 0) ON CONFLICT DO NOTHING"), {"b": b})
        await migrada.execute(text(
            "INSERT INTO buyer_context_revisions "
            "  (buyer_id, context_revision, source_message_id, context_json) "
            "VALUES (CAST(:b AS uuid), 0, :m, CAST('{}' AS jsonb))"), {"b": b, "m": vacio})
    assert "ck_buyer_revisions_message_id_no_vacio" in str(e.value) or \
           "check constraint" in str(e.value).lower()
    await migrada.rollback()


@necesita_motor
@pytest.mark.asyncio
async def test_1C_un_message_id_normal_sigue_pasando(migrada):
    """El `CHECK` no puede ser tan estricto que rompa el camino legítimo."""
    b = await _cuenta(migrada)
    r = await anexar_revision(b, "msg-normal-123", _ctx(b), None, db=migrada)
    await migrada.commit()
    assert r.creada is True



@necesita_motor
@pytest.mark.asyncio
async def test_1B_al_fallar_NO_deja_trabajo_PROPIO_a_medias(motor):
    """LA OTRA MITAD DE 1B, y la que faltaba.

    `BuyerRevisionConflict` documenta "no se escribió nada". Sin savepoint eso era falso con
    sesión inyectada: el `INSERT` de la cabeza ocurre ANTES de comprobar
    `expected_revision`, así que el conflicto dejaba una cabeza huérfana que el `commit` del
    llamante confirmaba.

    Las dos garantías tienen que cumplirse **a la vez**:

        deshacer del store  →  NO borra trabajo ajeno
        fallo del store     →  NO deja trabajo propio parcial
    """
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as s:
        b = await _cuenta(s)
        await s.execute(text("CREATE TABLE IF NOT EXISTS trabajo_ajeno (nota text)"))
        await s.execute(text("DELETE FROM trabajo_ajeno"))
        await s.commit()

    async with fabrica() as s:
        await s.execute(text("INSERT INTO trabajo_ajeno (nota) VALUES ('del llamante')"))

        with pytest.raises(BuyerRevisionConflict):
            await anexar_revision(b, "m-1", _ctx(b), 5, db=s)

        await s.commit()          # el llamante conserva LO SUYO

    async with fabrica() as v:
        ajeno = (await v.execute(text("SELECT count(*) FROM trabajo_ajeno"))).scalar()
        cabezas = (await v.execute(text(
            "SELECT count(*) FROM buyer_context_heads WHERE buyer_id = CAST(:b AS uuid)"),
            {"b": b})).scalar()
        revisiones = await _filas(v, b)

    assert ajeno == 1, "el store deshizo trabajo que no era suyo"
    assert cabezas == 0, "el conflicto dejó una cabeza huérfana: 'no se escribió nada' es falso"
    assert revisiones == 0


@necesita_motor
@pytest.mark.asyncio
async def test_1C_la_029_no_se_confunde_con_un_conname_homonimo_de_OTRA_tabla(motor):
    """`conname` no es único por base de datos.

    Si otra tabla tiene ya una restricción con ese nombre, comprobar solo `conname` haría
    creer que la 029 está aplicada — y `buyer_context_revisions` se quedaría sin el `CHECK`,
    en silencio. Por eso la comprobación va acotada por `conrelid`.
    """
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as s:
        # Se retira el CHECK y se planta un homónimo en otra tabla ANTES de reaplicar.
        await s.execute(text(
            "ALTER TABLE buyer_context_revisions "
            "DROP CONSTRAINT IF EXISTS ck_buyer_revisions_message_id_no_vacio"))
        await s.execute(text("DROP TABLE IF EXISTS senuelo"))
        await s.execute(text("CREATE TABLE senuelo (x text)"))
        await s.execute(text(
            "ALTER TABLE senuelo ADD CONSTRAINT ck_buyer_revisions_message_id_no_vacio "
            "CHECK (length(btrim(x)) > 0)"))
        await s.commit()

    async with fabrica() as s:
        from app.esquema_requerido import aplicar_migracion
        await aplicar_migracion("migrations/029_buyer_source_message_id_nonempty.sql", db=s)

    async with fabrica() as v:
        propia = (await v.execute(text(
            "SELECT count(*) FROM pg_constraint "
            "WHERE conname = 'ck_buyer_revisions_message_id_no_vacio' "
            "  AND conrelid = 'buyer_context_revisions'::regclass"))).scalar()
    assert propia == 1, "el homónimo de otra tabla hizo que la 029 se saltara su trabajo"


@necesita_motor
@pytest.mark.asyncio
async def test_1B_un_error_TIPADO_tampoco_deja_el_savepoint_abierto(motor):
    """El último hueco de la frontera transaccional.

    `BuyerContextCorrupto` hereda de `BuyerStoreError`, y el `except BuyerStoreError: raise`
    lo re-lanzaba SIN cerrar el savepoint. Sale de `_rehidratar(previa)` dentro del
    savepoint, cuando el `(buyer_id, source_message_id)` ya existe pero su revisión dejó de
    validar.

    No hay pérdida de datos —a diferencia del caso de la cabeza huérfana— pero el store
    devolvía el control al llamante con una transacción anidada **suya** todavía abierta.
    Eso rompe la frontera que 1B acaba de formalizar: el llamante no puede razonar sobre su
    propia transacción si el store deja la suya a medias dentro.
    """
    from app.buyer.store import BuyerContextCorrupto

    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as s:
        b = await _cuenta(s)
        await s.execute(text("CREATE TABLE IF NOT EXISTS trabajo_ajeno (nota text)"))
        await s.execute(text("DELETE FROM trabajo_ajeno"))
        await s.commit()

    # Una revisión ya CONFIRMADA que después deja de validar (el contrato exige `buyer_id`).
    async with fabrica() as s:
        await anexar_revision(b, "m-1", _ctx(b, objective=Objective.RENT), None, db=s)
        await s.commit()
    async with fabrica() as s:
        await s.execute(text(
            "UPDATE buyer_context_revisions SET context_json = CAST(:j AS jsonb) "
            "WHERE buyer_id = CAST(:b AS uuid)"),
            {"b": b, "j": '{"version": "buyer-context-v0"}'})
        await s.commit()

    async with fabrica() as s:
        await s.execute(text("INSERT INTO trabajo_ajeno (nota) VALUES ('del llamante')"))

        with pytest.raises(BuyerContextCorrupto):
            await anexar_revision(b, "m-1", _ctx(b, objective=Objective.RENT), None, db=s)

        assert not s.in_nested_transaction(),             "el store devolvió el control con su savepoint todavía abierto"

        await s.commit()

    async with fabrica() as v:
        assert (await v.execute(text("SELECT count(*) FROM trabajo_ajeno"))).scalar() == 1
        assert await _filas(v, b) == 1, "el store añadió una revisión pese al error"
        crudo = (await v.execute(text(
            "SELECT context_json::text FROM buyer_context_revisions "
            "WHERE buyer_id = CAST(:b AS uuid)"), {"b": b})).scalar()
        assert "buyer_id" not in crudo, "la revisión corrupta fue modificada"

# ── Infraestructura ────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def motor():
    if "supabase.com" in URL or "pooler" in URL:
        pytest.fail("TEST_DATABASE_URL apunta a producción. Abortado.")
    m = create_async_engine(URL)
    fabrica = async_sessionmaker(m, expire_on_commit=False)
    async with fabrica() as s:
        await s.execute(text("DROP TABLE IF EXISTS buyer_context_revisions CASCADE"))
        await s.execute(text("DROP TABLE IF EXISTS buyer_context_heads CASCADE"))
        await s.execute(text("DROP TABLE IF EXISTS trabajo_ajeno"))
        # El señuelo del test de `conname` homónimo: si sobrevive entre tests, la 029 lo
        # encontraría en el arranque y el fallo aparecería como error de fixture en vez de
        # como el assert que lo explica.
        await s.execute(text("DROP TABLE IF EXISTS senuelo"))
        await s.execute(text("DROP TABLE IF EXISTS auth.users CASCADE"))
        await s.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))
        await s.execute(text("CREATE TABLE IF NOT EXISTS auth.users (id uuid PRIMARY KEY)"))
        await s.commit()
    async with fabrica() as s:
        await _aplicar(s)
    yield m
    await m.dispose()


@pytest_asyncio.fixture
async def migrada(motor):
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as s:
        yield s


async def _aplicar(s):
    """Las dos migraciones, por el aplicador REAL de producción."""
    from app.esquema_requerido import aplicar_migracion
    await aplicar_migracion("migrations/028_buyer_context_store.sql", db=s)
    await aplicar_migracion("migrations/029_buyer_source_message_id_nonempty.sql", db=s)


async def _cuenta(s) -> str:
    uid = str(uuid.uuid4())
    await s.execute(text("INSERT INTO auth.users (id) VALUES (CAST(:u AS uuid))"), {"u": uid})
    await s.commit()
    return uid


async def _filas(s, buyer_id) -> int:
    return (await s.execute(text(
        "SELECT count(*) FROM buyer_context_revisions WHERE buyer_id = CAST(:b AS uuid)"),
        {"b": buyer_id})).scalar()
