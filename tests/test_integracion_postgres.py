"""AUTH-READ-GATE.1 · HOLD-1 — la autoridad contra PostgreSQL REAL.

Todo lo demás de esta unidad prueba que **el código decide bien**. Esto prueba que **el SQL
que toma esa decisión es válido para el motor**: tipos, `CAST`, `ON CONFLICT … RETURNING`,
`now()`, índices parciales, y la semántica de `rowcount` en el claim.

Es la diferencia entre `SQL REVIEWED` y `SQL EXECUTED`, y era el motivo del HOLD.

## Cómo se corre

```bash
docker compose up -d db
TEST_DATABASE_URL=postgresql+asyncpg://contexto:contexto@localhost:5432/contexto_test \
    python -m pytest tests/test_integracion_postgres.py -v
```

Sin `TEST_DATABASE_URL` los tests se **saltan**, no fallan: la suite normal no depende de
tener un motor levantado. Un `skip` aquí significa *"esta evidencia no se ha producido"*, y
el reporte 13 lo dice con esas palabras en vez de dar por buena una suite verde.

## Lo que NUNCA se hace aquí

`TEST_DATABASE_URL` es obligatoria y **no** cae por defecto a `settings.database_url`. Estos
tests crean sesiones, reclaman hilos y revocan capacidades; apuntarlos a producción sería
escribir en las conversaciones de gente real. La ausencia de valor por defecto es el candado.
"""

from __future__ import annotations

import os
import pathlib
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth import CurrentUser
from app.sesion_autoridad import (
    AccesoDenegado,
    Autoridad,
    autorizar_acceso_a_sesion,
    crear_sesion,
    generar_secreto,
    hash_de,
    reclamar_sesion_anonima,
)

URL = os.getenv("TEST_DATABASE_URL", "")

pytestmark = [
    pytest.mark.skipif(not URL, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas"),
    pytest.mark.asyncio,
]

U1 = CurrentUser(user_id=str(uuid.uuid4()))
U2 = CurrentUser(user_id=str(uuid.uuid4()))
ACTIVO = str(uuid.uuid4())

# Lo mínimo de `chat_sessions` anterior a la 027, para que la migración tenga qué alterar.
# Se replica la forma de `migrations/006_chat_sessions.sql` + `008_auth_roles.sql`.
BASE = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id  TEXT PRIMARY KEY,
    user_id     UUID,
    titulo      TEXT,
    is_public   BOOLEAN NOT NULL DEFAULT false,
    share_token TEXT,
    archived    BOOLEAN NOT NULL DEFAULT false,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_chat_sessions_user ON chat_sessions (user_id);
"""


@pytest_asyncio.fixture
async def db(monkeypatch):
    """Base limpia por test, con la 027 aplicada por su propio fichero — no a mano."""
    if "supabase.com" in URL or "pooler" in URL:
        pytest.fail("TEST_DATABASE_URL apunta a producción. Abortado.")

    motor = create_async_engine(URL, poolclass=None)
    sesion = async_sessionmaker(motor, expire_on_commit=False)

    async with sesion() as s:
        await s.execute(text("DROP TABLE IF EXISTS chat_sessions CASCADE"))
        await s.execute(text(BASE))
        await s.commit()

    # `AsyncSessionLocal` de la app apunta al motor de pruebas: el código bajo test es el
    # real, sin `db=` inyectado, igual que en producción.
    monkeypatch.setattr("app.sesion_autoridad.AsyncSessionLocal", sesion)
    monkeypatch.setattr("app.esquema_requerido.AsyncSessionLocal", sesion)

    async with sesion() as s:
        yield s

    await motor.dispose()


async def _aplicar_027(s):
    sql = pathlib.Path("migrations/027_session_resume_capability.sql").read_text(encoding="utf-8")
    await s.execute(text(sql))
    await s.commit()


async def _columnas(s) -> dict[str, tuple[str, str, str | None]]:
    filas = (await s.execute(text(
        "SELECT column_name, data_type, is_nullable, column_default "
        "FROM information_schema.columns WHERE table_name = 'chat_sessions'"))).all()
    return {f[0]: (f[1], f[2], f[3]) for f in filas}


# ── 5 · la migración contra el motor ───────────────────────────────────────────────


async def test_027_se_aplica_y_crea_las_cuatro_columnas(db):
    await _aplicar_027(db)
    cols = await _columnas(db)

    esperado = {
        "resume_token_hash":   ("text", "YES"),
        "resume_issued_at":    ("timestamp with time zone", "YES"),
        "resume_revoked_at":   ("timestamp with time zone", "YES"),
        "creada_por_servidor": ("boolean", "NO"),
    }
    for nombre, (tipo, nulable) in esperado.items():
        assert nombre in cols, f"la 027 no creó {nombre}"
        assert cols[nombre][0] == tipo, f"{nombre}: {cols[nombre][0]} != {tipo}"
        assert cols[nombre][1] == nulable, f"{nombre}: nullable {cols[nombre][1]} != {nulable}"

    assert "false" in (cols["creada_por_servidor"][2] or "").lower()


async def test_027_es_IDEMPOTENTE_de_verdad(db):
    """Correrla dos veces no puede fallar ni duplicar nada. Es lo que permite reaplicarla
    sin miedo en un despliegue que se reintenta."""
    await _aplicar_027(db)
    antes = await _columnas(db)

    await _aplicar_027(db)          # segunda pasada
    assert await _columnas(db) == antes


async def test_las_filas_legacy_sobreviven_a_la_migracion(db):
    """Un hilo con dueño y otro anónimo, creados ANTES de la 027, siguen ahí después — el
    primero autorizable por identidad, el segundo sin capacidad (pérdida deliberada)."""
    await db.execute(text(
        "INSERT INTO chat_sessions (session_id, user_id) VALUES "
        "('legacy-con-dueno', CAST(:u AS uuid)), ('legacy-anonima', NULL)"), {"u": U2.user_id})
    await db.commit()

    await _aplicar_027(db)

    filas = {f[0]: f for f in (await db.execute(text(
        "SELECT session_id, user_id::text, resume_token_hash, creada_por_servidor "
        "FROM chat_sessions ORDER BY session_id"))).all()}

    assert filas["legacy-con-dueno"][1] == U2.user_id
    assert filas["legacy-anonima"][1] is None
    # El DEFAULT rellena las filas existentes sin reescribir la tabla (PG >= 11).
    assert filas["legacy-con-dueno"][3] is False
    # Ninguna capacidad emitida retroactivamente. No se puede, y no se hace.
    assert all(f[2] is None for f in filas.values())


async def test_el_legacy_con_dueno_autoriza_y_el_anonimo_no(db):
    await _aplicar_027(db)
    await db.execute(text(
        "INSERT INTO chat_sessions (session_id, user_id) VALUES "
        "('legacy-con-dueno', CAST(:u AS uuid)), ('legacy-anonima', NULL)"), {"u": U2.user_id})
    await db.commit()

    assert await autorizar_acceso_a_sesion("legacy-con-dueno", U2, None) is Autoridad.OWNER

    with pytest.raises(AccesoDenegado):
        await autorizar_acceso_a_sesion("legacy-con-dueno", U1, None)
    with pytest.raises(AccesoDenegado):
        await autorizar_acceso_a_sesion("legacy-anonima", None, generar_secreto())


# ── 6 · la autoridad, con el módulo real contra el motor real ──────────────────────


@pytest_asyncio.fixture
async def migrada(db):
    await _aplicar_027(db)
    return db


async def test_bootstrap_anonimo_guarda_el_HASH_y_nunca_el_secreto(migrada):
    creada = await crear_sesion(None, activo_id=ACTIVO)
    assert creada.resume_secret

    fila = (await migrada.execute(text(
        "SELECT user_id, resume_token_hash, resume_issued_at, creada_por_servidor "
        "FROM chat_sessions WHERE session_id = :s"), {"s": creada.session_id})).first()

    assert fila[0] is None, "una sesión anónima no puede nacer con dueño"
    assert fila[1] == hash_de(creada.resume_secret)
    assert fila[1] != creada.resume_secret, "el secreto en claro está en la base"
    assert fila[2] is not None, "no se selló resume_issued_at"
    assert fila[3] is True, "la creó el servidor y no quedó marcado"

    # El secreto crudo no aparece en NINGUNA columna de la fila.
    todo = (await migrada.execute(text(
        "SELECT chat_sessions::text FROM chat_sessions WHERE session_id = :s"),
        {"s": creada.session_id})).scalar()
    assert creada.resume_secret not in todo


async def test_bootstrap_autenticado_no_emite_capacidad(migrada):
    creada = await crear_sesion(U1, activo_id=ACTIVO)
    assert creada.resume_secret is None

    fila = (await migrada.execute(text(
        "SELECT user_id::text, resume_token_hash FROM chat_sessions WHERE session_id = :s"),
        {"s": creada.session_id})).first()
    assert fila[0] == U1.user_id and fila[1] is None


async def test_el_prefijo_del_QR_sobrevive_al_motor(migrada):
    """Siete consultas de `assets.py` dependen de `LIKE 'qr-{activo}-%'`."""
    creada = await crear_sesion(None, activo_id=ACTIVO)
    assert creada.session_id.startswith(f"qr-{ACTIVO}-")

    encontrada = (await migrada.execute(text(
        "SELECT session_id FROM chat_sessions WHERE session_id LIKE :p"),
        {"p": f"qr-{ACTIVO}-%"})).scalar()
    assert encontrada == creada.session_id


async def test_cross_owner_REAL_contra_el_motor(migrada):
    de_u2 = (await crear_sesion(U2, activo_id=ACTIVO)).session_id

    assert await autorizar_acceso_a_sesion(de_u2, U2, None) is Autoridad.OWNER
    with pytest.raises(AccesoDenegado):
        await autorizar_acceso_a_sesion(de_u2, U1, None)
    with pytest.raises(AccesoDenegado):
        await autorizar_acceso_a_sesion(de_u2, U1, generar_secreto())


async def test_la_capacidad_propia_abre_y_la_ajena_no(migrada):
    propia = await crear_sesion(None, activo_id=ACTIVO)
    otra = await crear_sesion(None, activo_id=ACTIVO)

    assert await autorizar_acceso_a_sesion(
        propia.session_id, None, propia.resume_secret) is Autoridad.ANONYMOUS_CAPABILITY

    with pytest.raises(AccesoDenegado):
        await autorizar_acceso_a_sesion(propia.session_id, None, otra.resume_secret)
    with pytest.raises(AccesoDenegado):
        await autorizar_acceso_a_sesion(propia.session_id, None, None)
    with pytest.raises(AccesoDenegado):
        await autorizar_acceso_a_sesion("session-no-existe", None, propia.resume_secret)


async def test_el_claim_asigna_dueno_y_revoca_EN_LA_BASE(migrada):
    """El ciclo completo del caso 6, verificado leyendo las filas después."""
    anonima = await crear_sesion(None, activo_id=ACTIVO)

    await reclamar_sesion_anonima(anonima.session_id, U1, anonima.resume_secret)

    fila = (await migrada.execute(text(
        "SELECT user_id::text, resume_revoked_at FROM chat_sessions WHERE session_id = :s"),
        {"s": anonima.session_id})).first()
    assert fila[0] == U1.user_id, "el claim no asignó dueño"
    assert fila[1] is not None, "la capacidad no quedó revocada"

    # La capacidad vieja ya no sirve — ni para su antiguo dueño anónimo…
    with pytest.raises(AccesoDenegado):
        await autorizar_acceso_a_sesion(anonima.session_id, None, anonima.resume_secret)
    # …ni para otro autenticado que la hubiera copiado.
    with pytest.raises(AccesoDenegado):
        await autorizar_acceso_a_sesion(anonima.session_id, U2, anonima.resume_secret)
    # Y el nuevo dueño entra por identidad.
    assert await autorizar_acceso_a_sesion(anonima.session_id, U1, None) is Autoridad.OWNER


async def test_un_claim_sobre_hilo_ajeno_no_toca_NADA(migrada):
    """TOCTOU y apropiación, contra el motor: el `WHERE` no se cumple, `rowcount` es 0, y la
    función levanta en vez de callar. La fila de U2 queda intacta."""
    de_u2 = (await crear_sesion(U2, activo_id=ACTIVO)).session_id
    antes = (await migrada.execute(text(
        "SELECT user_id::text FROM chat_sessions WHERE session_id = :s"), {"s": de_u2})).scalar()

    with pytest.raises(AccesoDenegado):
        await reclamar_sesion_anonima(de_u2, U1, generar_secreto())

    despues = (await migrada.execute(text(
        "SELECT user_id::text FROM chat_sessions WHERE session_id = :s"), {"s": de_u2})).scalar()
    assert despues == antes == U2.user_id


async def test_el_bootstrap_no_emite_capacidad_para_un_id_existente(migrada):
    """`ON CONFLICT DO NOTHING RETURNING` contra el motor: si el id ya estaba, no hay fila
    devuelta y no se emite capacidad. Es lo que impide pedir una llave para un hilo ajeno."""
    from app.sesion_autoridad import _ejecutar_creacion

    creada = await crear_sesion(None, activo_id=ACTIVO)
    hash_original = (await migrada.execute(text(
        "SELECT resume_token_hash FROM chat_sessions WHERE session_id = :s"),
        {"s": creada.session_id})).scalar()

    # Se fuerza la colisión insertando con el MISMO id.
    async with migrada.begin_nested():
        with pytest.raises(AccesoDenegado):
            await _forzar_colision(migrada, creada.session_id)

    assert (await migrada.execute(text(
        "SELECT resume_token_hash FROM chat_sessions WHERE session_id = :s"),
        {"s": creada.session_id})).scalar() == hash_original, "se re-emitió la capacidad"


async def _forzar_colision(db, session_id: str):
    """Reproduce el camino de creación con un id ya tomado."""
    from app.sesion_autoridad import _ejecutar_creacion
    import app.sesion_autoridad as sa

    original = sa._nuevo_session_id
    sa._nuevo_session_id = lambda _a: session_id
    try:
        await _ejecutar_creacion(db, None, ACTIVO)
    finally:
        sa._nuevo_session_id = original


# ── 7 · los híbridos: el SQL de `_alcances_autorizados` contra el motor ────────────


NOTIF = """
CREATE TABLE IF NOT EXISTS notificacion (
    id bigserial PRIMARY KEY,
    destinatario_user_id uuid,
    destinatario_session text,
    titulo text NOT NULL,
    cuerpo text, url text, session_id text, activo_id uuid,
    creada_en timestamptz NOT NULL DEFAULT now(),
    leida_en timestamptz
);
"""


@pytest_asyncio.fixture
async def avisos(migrada):
    """Avisos de U1 (por cuenta), de U2 (por cuenta) y de una sesión anónima."""
    await migrada.execute(text("DROP TABLE IF EXISTS notificacion"))
    await migrada.execute(text(NOTIF))
    anonima = await crear_sesion(None, activo_id=ACTIVO)
    de_u2 = (await crear_sesion(U2, activo_id=ACTIVO)).session_id

    await migrada.execute(text(
        "INSERT INTO notificacion (destinatario_user_id, destinatario_session, titulo) VALUES "
        "(CAST(:u1 AS uuid), NULL, 'de U1'), "
        "(CAST(:u2 AS uuid), NULL, 'de U2'), "
        "(NULL, :sa, 'de la sesion anonima'), "
        "(NULL, :s2, 'de la sesion de U2')"),
        {"u1": U1.user_id, "u2": U2.user_id, "sa": anonima.session_id, "s2": de_u2})
    await migrada.commit()
    return {"db": migrada, "anonima": anonima, "de_u2": de_u2}


async def _titulos(db, condiciones, params):
    filas = (await db.execute(text(
        f"SELECT titulo FROM notificacion WHERE ({' OR '.join(condiciones)}) ORDER BY id"),
        params)).all()
    return [f[0] for f in filas]


async def test_hibrido_solo_cuenta(avisos):
    """MODO CUENTA — el SQL generado se ejecuta y devuelve solo lo de U1."""
    from app.routers.chat import _alcances_autorizados
    from starlette.requests import Request

    pet = Request({"type": "http", "method": "GET", "path": "/", "headers": [],
                   "client": ("t", 0), "query_string": b""})
    cond, params = await _alcances_autorizados(pet, None, U1)
    assert await _titulos(avisos["db"], cond, params) == ["de U1"]


async def test_hibrido_cuenta_mas_sesion_propia(avisos):
    from app.routers.chat import _alcances_autorizados
    from starlette.requests import Request

    anonima = avisos["anonima"]
    pet = Request({"type": "http", "method": "GET", "path": "/",
                   "headers": [(b"x-session-resume", anonima.resume_secret.encode())],
                   "client": ("t", 0), "query_string": b""})
    cond, params = await _alcances_autorizados(pet, anonima.session_id, U1)
    assert await _titulos(avisos["db"], cond, params) == ["de U1", "de la sesion anonima"]


async def test_hibrido_sesion_AJENA_solo_devuelve_la_cuenta(avisos):
    """B.1 caso 6, contra el motor: U1 aporta la sesión de U2 y NO ve nada de U2."""
    from app.routers.chat import _alcances_autorizados
    from starlette.requests import Request

    pet = Request({"type": "http", "method": "GET", "path": "/", "headers": [],
                   "client": ("t", 0), "query_string": b""})
    cond, params = await _alcances_autorizados(pet, avisos["de_u2"], U1)

    titulos = await _titulos(avisos["db"], cond, params)
    assert titulos == ["de U1"]
    assert "de U2" not in titulos and "de la sesion de U2" not in titulos


async def test_hibrido_anonimo_sin_capacidad_es_404(avisos):
    from fastapi import HTTPException
    from app.routers.chat import _alcances_autorizados
    from starlette.requests import Request

    pet = Request({"type": "http", "method": "GET", "path": "/", "headers": [],
                   "client": ("t", 0), "query_string": b""})
    with pytest.raises(HTTPException) as e:
        await _alcances_autorizados(pet, avisos["de_u2"], None)
    assert e.value.status_code == 404


async def test_marcar_leidas_con_sesion_ajena_no_toca_filas_de_U2(avisos):
    """La mutación, verificada LEYENDO la base después: el `UPDATE` acotado por los alcances
    autorizados no puede alcanzar los avisos de U2."""
    from app.routers.chat import _alcances_autorizados
    from starlette.requests import Request

    db = avisos["db"]
    pet = Request({"type": "http", "method": "GET", "path": "/", "headers": [],
                   "client": ("t", 0), "query_string": b""})
    cond, params = await _alcances_autorizados(pet, avisos["de_u2"], U1)

    r = await db.execute(text(
        "UPDATE notificacion SET leida_en = now() WHERE leida_en IS NULL "
        f"AND ({' OR '.join(cond)})"), params)
    await db.commit()

    assert r.rowcount == 1, "debería marcar solo el aviso de cuenta de U1"
    sin_leer = [f[0] for f in (await db.execute(text(
        "SELECT titulo FROM notificacion WHERE leida_en IS NULL ORDER BY id"))).all()]
    assert "de U2" in sin_leer and "de la sesion de U2" in sin_leer
