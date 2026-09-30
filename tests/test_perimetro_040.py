"""PLACE-SOURCE-PERIMETER · la 040 cierra la fuente del contexto de lugar sin cambiar el producto.

  A · sin base: la migración hace SOLO lo que dice (RLS sin FORCE en las dos tablas,
      `security_invoker` en la vista, REVOKE a PUBLIC y a los tres roles sobre tablas, vista y
      secuencias, compuertas fail-closed) y nada más (ni políticas, ni GRANT, ni DML, ni otras
      relaciones).
  B · PostgreSQL 15 real (`TEST_DATABASE_URL`, también en el CI): con un dueño NO superusuario con
      BYPASSRLS —el doble del `postgres` de producción— la 040 se aplica con el aplicador del
      producto. `entorno_curacion` la crea el DDL REAL (`ensure_curacion_table`), `pois_vivos` es
      la vista REAL de la 023 y `pois_propios` un doble de forma (sin PostGIS en el CI). Los tres
      roles quedan sin nada, el dueño conserva su CRUD y las filas sobreviven intactas.

El banco completo (control positivo, compuertas, mutaciones, roles ausentes, PG15, PG17 y PostGIS
con las migraciones reales 014→023) está en `tests/arnes_perimetro_040.py`, que necesita Docker.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from sqlalchemy import text

import app.entorno_curacion as curacion

RAIZ = Path(__file__).resolve().parents[1]
M040 = RAIZ / "migrations" / "040_place_source_perimeter.sql"
M023 = RAIZ / "migrations" / "023_curacion_engancha_poi.sql"
ROLES = ("anon", "authenticated", "service_role")
PRIVS = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
RELS = ("public.pois_propios", "public.entorno_curacion", "public.pois_vivos")
DUENO = "p040_owner"
ACTIVO = "0cb128c9-0000-4000-8000-0000000040a1"
CORREDOR = "0cb128c9-0000-4000-8000-0000000040c1"


def _sin_comentarios(sql: str) -> str:
    return "\n".join(l.split("--", 1)[0] for l in sql.splitlines())


# ─────────────────────────────── A · sin base ────────────────────────────────
def test_la_040_hace_solo_lo_que_dice():
    cuerpo = _sin_comentarios(M040.read_text(encoding="utf-8"))
    assert cuerpo.strip().startswith("BEGIN;") and cuerpo.rstrip().endswith("COMMIT;")
    assert "SET LOCAL lock_timeout" in cuerpo
    assert "ALTER TABLE public.pois_propios ENABLE ROW LEVEL SECURITY;" in cuerpo
    assert "ALTER TABLE public.entorno_curacion ENABLE ROW LEVEL SECURITY;" in cuerpo
    assert "ALTER VIEW public.pois_vivos SET (security_invoker = true);" in cuerpo
    assert ("REVOKE ALL PRIVILEGES ON TABLE public.pois_propios, public.entorno_curacion, "
            "public.pois_vivos FROM PUBLIC;") in cuerpo
    assert "REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM PUBLIC" in cuerpo
    assert "REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM %I" in cuerpo
    assert "ARRAY['anon', 'authenticated', 'service_role']" in cuerpo
    # Las secuencias se localizan por dependencia, no por nombre.
    assert "pg_depend" in cuerpo and "relkind = 'S'" in cuerpo
    # Nada de lo que la unidad no autoriza.
    assert not re.search(r"(?i)\bFORCE\s+ROW\s+LEVEL", cuerpo.replace("relforcerowsecurity", ""))
    assert not re.search(r"(?i)\bCREATE\s+POLICY\b", cuerpo)
    assert not re.search(r"(?i)^\s*(INSERT|UPDATE|DELETE|TRUNCATE)\b", cuerpo, re.M)
    assert not re.search(r"(?i)\bGRANT\b", cuerpo)
    # Solo el perímetro: las dos tablas y su vista. Ni `activos_inmutables` ni el respaldo.
    rels = set(re.findall(r"public\.([a-z_0-9]+)", cuerpo))
    assert rels == {"pois_propios", "entorno_curacion", "pois_vivos"}, rels
    # Las compuertas fail-closed, todas.
    for compuerta in ("no existe", "no es una vista", "el dueño no es quien aplica", "ya existen",
                      "publicación de replicación", "además de pois_vivos", "funciones que mencionan",
                      "triggers en el perímetro", "RLS no quedó activado", "apareció FORCE",
                      "security_invoker = true", "quedan privilegios en pie",
                      "quedan privilegios de columna", "sobre la secuencia", "perdió"):
        assert compuerta in cuerpo, compuerta


def test_el_rollback_documentado_es_el_inverso_exacto():
    sql = M040.read_text(encoding="utf-8")
    rollback = sql.split("-- ── ROLLBACK", 1)[1]
    for linea in ("ALTER TABLE public.pois_propios DISABLE ROW LEVEL SECURITY;",
                  "ALTER TABLE public.entorno_curacion DISABLE ROW LEVEL SECURITY;",
                  "ALTER VIEW public.pois_vivos RESET (security_invoker);"):
        assert linea in rollback, linea
    # Todo el ROLLBACK está comentado: aplicar la 040 nunca lo ejecuta.
    assert all(l.startswith("--") or not l.strip() for l in rollback.splitlines()[1:])


# ──────────────────────────── B · Postgres 15 real ────────────────────────────
URL = os.getenv("TEST_DATABASE_URL", "")
pg = pytest.mark.skipif(not URL, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas")

DOBLE_POIS = """
CREATE TABLE public.pois_propios (
    id bigserial PRIMARY KEY, nombre text, categoria text NOT NULL, categoria_overture text,
    geom text NOT NULL,  -- doble de forma: geometry(Point,4326) en producción (sin PostGIS en el CI)
    fuente text NOT NULL DEFAULT 'overture', confianza real, overture_id text, osm_id text,
    marca text, direccion text, operativo boolean DEFAULT true,
    actualizado_en timestamptz NOT NULL DEFAULT now(), ciudad text NOT NULL DEFAULT 'quito',
    CONSTRAINT ck_pois_fuente CHECK (fuente IN ('overture','osm')))
"""


def _vista_de_la_023() -> str:
    m = re.search(r"CREATE OR REPLACE VIEW pois_vivos AS.*?;", _sin_comentarios(M023.read_text(encoding="utf-8")), re.S)
    assert m, "no se encontró la vista pois_vivos en la 023"
    return m.group(0)


async def _limpia(cx):
    await cx.execute(text("DROP VIEW IF EXISTS public.pois_vivos CASCADE"))
    await cx.execute(text("DROP TABLE IF EXISTS public.entorno_curacion, public.pois_propios CASCADE"))


@pytest.fixture
async def banco(monkeypatch):
    """El perímetro creado como un dueño NOSUPERUSER + BYPASSRLS —con el DDL real de la curación
    y la vista real de la 023— y nacido con la exposición medida en producción."""
    from app.config import settings
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    if settings.database_url and URL.split("@")[-1] in settings.database_url:
        pytest.fail("TEST_DATABASE_URL apunta a la base del producto. Abortado.")
    admin = create_async_engine(URL, poolclass=NullPool)
    async with admin.begin() as cx:
        for rol in ROLES:
            await cx.execute(text(
                f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{rol}') "
                f"THEN CREATE ROLE {rol} NOLOGIN; END IF; END $$;"))
        await cx.execute(text(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{DUENO}') "
            f"THEN CREATE ROLE {DUENO} NOLOGIN NOSUPERUSER BYPASSRLS; END IF; END $$;"))
        await cx.execute(text(f"GRANT USAGE, CREATE ON SCHEMA public TO {DUENO}"))
        await cx.execute(text("GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role"))
        await _limpia(cx)

    motores = []

    def motor(rol):
        m = create_async_engine(URL, poolclass=NullPool, connect_args={
            "server_settings": {"role": rol, "search_path": "public"}})
        motores.append(m)
        return m

    dueno = motor(DUENO)
    Sesion = async_sessionmaker(dueno, expire_on_commit=False)
    async with dueno.begin() as cx:
        await cx.execute(text(DOBLE_POIS))
    monkeypatch.setattr(curacion, "_curacion_ready", False)
    async with Sesion() as s:
        await curacion.ensure_curacion_table(s)          # el DDL REAL del producto
    async with dueno.begin() as cx:
        await cx.execute(text(_vista_de_la_023()))       # la vista REAL de la 023
        await cx.execute(text("GRANT ALL PRIVILEGES ON TABLE public.pois_propios, public.entorno_curacion, "
                              "public.pois_vivos TO anon, authenticated, service_role"))
        await cx.execute(text("GRANT ALL PRIVILEGES ON SEQUENCE public.pois_propios_id_seq, "
                              "public.entorno_curacion_id_seq TO anon, authenticated, service_role"))
        await cx.execute(text(
            "INSERT INTO public.pois_propios (nombre, categoria, geom, fuente, osm_id) VALUES "
            "('Parque sintético', 'parque', 'POINT(-78.48 -0.18)', 'osm', 'node/401'), "
            "('Farmacia sintética', 'farmacia', 'POINT(-78.48 -0.18)', 'overture', NULL), "
            "('Súper sintético', 'supermercado', 'POINT(-78.48 -0.18)', 'osm', 'node/404')"))
        await cx.execute(text(
            "INSERT INTO public.entorno_curacion (activo_id, accion, nombre, corredor_id, poi_id) VALUES "
            f"('{ACTIVO}', 'agregado', 'Lugar sintético del corredor', '{CORREDOR}', NULL), "
            f"('{ACTIVO}', 'cerrado', 'Súper sintético', '{CORREDOR}', "
            "(SELECT id FROM public.pois_propios WHERE osm_id = 'node/404'))"))
    try:
        yield {"admin": admin, "motor": motor, "dueno": dueno, "Sesion": Sesion}
    finally:
        for m in motores:
            await m.dispose()
        async with admin.begin() as cx:
            await _limpia(cx)
        await admin.dispose()


async def _uno(motor, sql):
    async with motor.connect() as cx:
        return (await cx.execute(text(sql))).scalar()


async def _efectivos(admin, rol, rel):
    return [p for p in PRIVS if await _uno(admin, f"SELECT has_table_privilege('{rol}', '{rel}', '{p}')")]


async def _intenta(motor, sql):
    try:
        async with motor.begin() as cx:
            await cx.execute(text(sql))
        return "ok"
    except Exception as e:  # noqa: BLE001
        return type(getattr(e, "orig", e)).__name__ + ": " + str(getattr(e, "orig", e))[:90]


async def _huella(banco):
    return await _uno(banco["dueno"],
                      "SELECT md5((SELECT string_agg(t::text, '|' ORDER BY t.id) FROM public.pois_propios t)) || ':' || "
                      "md5((SELECT string_agg(t::text, '|' ORDER BY t.id) FROM public.entorno_curacion t))")


async def _aplica_040(banco):
    from app.esquema_requerido import aplicar_migracion
    async with banco["Sesion"]() as s:
        await aplicar_migracion(str(M040), db=s)


@pg
async def test_040_cierra_tablas_vista_y_secuencias_y_el_dueno_conserva_el_crud(banco):
    admin, motor = banco["admin"], banco["motor"]
    # CONTROL POSITIVO: la exposición de producción está reproducida.
    for rel in ("public.pois_propios", "public.entorno_curacion"):
        assert await _uno(admin, f"SELECT relrowsecurity FROM pg_class WHERE oid = '{rel}'::regclass") is False
    for rol in ROLES:
        for rel in RELS:
            assert await _efectivos(admin, rol, rel) == list(PRIVS), (rol, rel)
        assert await _uno(admin, f"SELECT has_sequence_privilege('{rol}', 'public.pois_propios_id_seq', 'UPDATE')")
    assert await _uno(motor("anon"), "SELECT count(*) FROM public.pois_vivos") == 2  # el `cerrado` no sale
    assert await _intenta(motor("anon"), "INSERT INTO public.entorno_curacion (activo_id, accion, nombre) "
                                         f"VALUES ('{ACTIVO}', 'cerrado', 'x')") == "ok"
    async with banco["dueno"].begin() as cx:
        await cx.execute(text("DELETE FROM public.entorno_curacion WHERE nombre = 'x'"))
    huella, vivos = await _huella(banco), await _uno(banco["dueno"], "SELECT count(*) FROM public.pois_vivos")

    await _aplica_040(banco)

    for rel in ("public.pois_propios", "public.entorno_curacion"):
        estado = await _uno(admin, "SELECT relrowsecurity::text || '|' || relforcerowsecurity::text "
                                   f"FROM pg_class WHERE oid = '{rel}'::regclass")
        assert estado == "true|false", (rel, estado)
    assert await _uno(admin, "SELECT count(*) FROM pg_policies WHERE schemaname = 'public' "
                             "AND tablename IN ('pois_propios', 'entorno_curacion')") == 0
    assert await _uno(admin, "SELECT 'security_invoker=true' = ANY (reloptions) FROM pg_class "
                             "WHERE oid = 'public.pois_vivos'::regclass") is True
    for rol in ROLES:
        for rel in RELS:
            assert await _efectivos(admin, rol, rel) == [], (rol, rel)
        for seq in ("public.pois_propios_id_seq", "public.entorno_curacion_id_seq"):
            for p in ("USAGE", "SELECT", "UPDATE"):
                assert not await _uno(admin, f"SELECT has_sequence_privilege('{rol}', '{seq}', '{p}')"), (rol, seq, p)
        m = motor(rol)
        for sql in ("SELECT count(*) FROM public.pois_propios",
                    "SELECT count(*) FROM public.pois_vivos",
                    "INSERT INTO public.pois_propios (nombre, categoria, geom) VALUES ('x', 'parque', 'POINT(0 0)')",
                    "UPDATE public.pois_propios SET nombre = 'x'",
                    f"INSERT INTO public.entorno_curacion (activo_id, accion, nombre) VALUES ('{ACTIVO}', 'cerrado', 'x')",
                    "DELETE FROM public.entorno_curacion",
                    "TRUNCATE public.entorno_curacion",
                    "SELECT setval('public.pois_propios_id_seq', 1)"):
            r = await _intenta(m, sql)
            assert "InsufficientPrivilege" in r and "permission denied" in r, (rol, sql, r)
    publico = await _uno(admin, "SELECT count(*) FROM pg_class c, aclexplode(c.relacl) a WHERE a.grantee = 0 AND c.oid IN "
                                "('public.pois_propios'::regclass, 'public.entorno_curacion'::regclass, "
                                "'public.pois_vivos'::regclass, 'public.pois_propios_id_seq'::regclass, "
                                "'public.entorno_curacion_id_seq'::regclass)")
    assert publico == 0

    # Las filas sobreviven intactas y el backend (el dueño) ve lo mismo por la vista.
    assert await _huella(banco) == huella
    assert await _uno(banco["dueno"], "SELECT count(*) FROM public.pois_vivos") == vivos
    assert await _uno(banco["dueno"], "SELECT count(*) FROM public.pois_vivos WHERE osm_id = 'node/404'") == 0
    # La lectura REAL de la curación (`fetch_curaciones`) sigue funcionando como el dueño.
    async with banco["Sesion"]() as s:
        filas = await curacion.fetch_curaciones(s, ACTIVO)
    assert {f["accion"] for f in filas} == {"agregado", "cerrado"}
    # CRUD del dueño: alta y baja de curaciones (POST/DELETE /entorno) y del refresco de POIs.
    for sql in (f"INSERT INTO public.entorno_curacion (activo_id, accion, nombre, corredor_id) "
                f"VALUES ('{ACTIVO}', 'agregado', 'Nuevo', '{CORREDOR}')",
                "UPDATE public.entorno_curacion SET categoria = 'Parque' WHERE nombre = 'Nuevo'",
                "DELETE FROM public.entorno_curacion WHERE nombre = 'Nuevo'",
                "INSERT INTO public.pois_propios (nombre, categoria, geom, fuente, osm_id) "
                "VALUES ('Temporal', 'salud', 'POINT(0 0)', 'osm', 'node/900') "
                "ON CONFLICT (id) DO NOTHING",
                "UPDATE public.pois_propios SET operativo = false WHERE osm_id = 'node/900'",
                "DELETE FROM public.pois_propios WHERE osm_id = 'node/900'"):
        assert await _intenta(banco["dueno"], sql) == "ok", sql
    # El DDL en runtime del producto sigue funcionando tras la 040.
    curacion._curacion_ready = False
    async with banco["Sesion"]() as s:
        await curacion.ensure_curacion_table(s)
    # Idempotente.
    await _aplica_040(banco)
    assert await _efectivos(admin, "anon", "public.pois_vivos") == []


@pg
async def test_040_resiste_un_re_grant_hostil(banco):
    motor = banco["motor"]
    await _aplica_040(banco)
    anon = motor("anon")
    # SELECT devuelto sobre la TABLA: RLS sin políticas → 0 filas.
    assert await _intenta(banco["dueno"], "GRANT SELECT ON public.pois_propios TO anon") == "ok"
    assert await _uno(anon, "SELECT count(*) FROM public.pois_propios") == 0
    assert await _intenta(banco["dueno"], "REVOKE ALL PRIVILEGES ON public.pois_propios FROM anon") == "ok"
    # SELECT devuelto sobre la VISTA: con security_invoker, choca con las tablas base.
    assert await _intenta(banco["dueno"], "GRANT SELECT ON public.pois_vivos TO anon") == "ok"
    r = await _intenta(anon, "SELECT count(*) FROM public.pois_vivos")
    assert "InsufficientPrivilege" in r and "permission denied for table" in r, r
    # …y aun devolviéndole también las tablas base, RLS no deja ver nada.
    assert await _intenta(banco["dueno"], "GRANT SELECT ON public.pois_propios, public.entorno_curacion TO anon") == "ok"
    assert await _uno(anon, "SELECT count(*) FROM public.pois_vivos") == 0
