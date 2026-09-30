"""AURA-CACHE-PERIMETER · la 039 cierra `public.aura_pois_cache` sin cambiar el producto.

  A · sin base: la migración hace SOLO lo que dice (RLS sin FORCE, REVOKE a PUBLIC y a los tres
      roles, compuertas fail-closed) y nada más (ni políticas, ni DML, ni otras tablas).
  B · PostgreSQL 15 real (`TEST_DATABASE_URL`, también en el CI): con un dueño NO superusuario con
      BYPASSRLS —el doble del `postgres` de producción— la 039 se aplica con el aplicador del
      producto, los tres roles quedan sin nada y el dueño conserva su CRUD.

ACTUALIZACIÓN ESPERADA (MAP-SOURCE-BOUNDARY, 2026-09-30): /aura ya NO lee ni escribe esta caché
—guardaba el resultado de Google Places, y los pines salen ahora de la capa propia—. Las dos
pruebas que decían «/aura sigue sirviendo desde la caché» dicen ahora lo contrario, y con la
tabla envenenada: una entrada fresca en la caché no llega al mapa.

El banco completo (control positivo, compuertas, mutaciones, PG15 y PG17) está en
`tests/arnes_perimetro_039.py`, que necesita Docker.
"""
from __future__ import annotations

import copy
import json
import os
import re
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

import app.routers.assets as assets

RAIZ = Path(__file__).resolve().parents[1]
M039 = RAIZ / "migrations" / "039_aura_pois_cache_perimeter.sql"
ROLES = ("anon", "authenticated", "service_role")
PRIVS = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
DUENO = "p039_owner"
ACTIVO = uuid.UUID("0cb128c9-0000-4000-8000-0000000039a1")
OTRO = uuid.UUID("0cb128c9-0000-4000-8000-0000000039a2")
LAT, LON = -0.1807, -78.4678
EN_CACHE = [{"nombre": "Lugar en caché", "lat": -0.18, "lon": -78.48, "distancia_m": 300,
             "fuente": "google"}]
PROPIO = {"farmacia": {"nombre": "Farmacia propia", "lat": -0.181, "lon": -78.468,
                       "distancia_m": 240, "cat": "farmacia", "fuente": "propio"}}


def _sin_comentarios(sql: str) -> str:
    return "\n".join(l.split("--", 1)[0] for l in sql.splitlines())


# ─────────────────────────────── A · sin base ────────────────────────────────
def test_la_039_hace_solo_lo_que_dice():
    sql = M039.read_text(encoding="utf-8")
    cuerpo = _sin_comentarios(sql)
    assert cuerpo.strip().startswith("BEGIN;") and cuerpo.rstrip().endswith("COMMIT;")
    assert "SET LOCAL lock_timeout" in cuerpo
    assert "ALTER TABLE public.aura_pois_cache ENABLE ROW LEVEL SECURITY;" in cuerpo
    assert "REVOKE ALL PRIVILEGES ON TABLE public.aura_pois_cache FROM PUBLIC;" in cuerpo
    assert "REVOKE ALL PRIVILEGES ON TABLE public.aura_pois_cache FROM %I" in cuerpo
    assert "ARRAY['anon', 'authenticated', 'service_role']" in cuerpo
    # Nada de lo que la unidad no autoriza.
    assert not re.search(r"(?i)\bFORCE\s+ROW\s+LEVEL", cuerpo.replace("relforcerowsecurity", ""))
    assert not re.search(r"(?i)\bCREATE\s+POLICY\b", cuerpo)
    assert not re.search(r"(?i)^\s*(INSERT|UPDATE|DELETE|TRUNCATE)\b", cuerpo, re.M)
    assert not re.search(r"(?i)\bGRANT\b", cuerpo)
    # Solo esta tabla.
    tablas = set(re.findall(r"public\.([a-z_]+)", cuerpo))
    assert tablas == {"aura_pois_cache"}, tablas
    # Las compuertas fail-closed de la 037, todas.
    for compuerta in ("no existe public.aura_pois_cache", "el dueño es", "ya existen",
                      "publicación de replicación", "vistas que dependen", "funciones que mencionan",
                      "RLS no quedó activado", "apareció FORCE", "quedan privilegios en pie",
                      "quedan privilegios de columna", "perdió", "secuencia"):
        assert compuerta in cuerpo, compuerta


# ──────────────────────────── B · Postgres 15 real ────────────────────────────
URL = os.getenv("TEST_DATABASE_URL", "")
pg = pytest.mark.skipif(not URL, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas")


class _CapaPropia:
    """Doble de `rutas._servicios_propios`: la capa propia sin PostGIS (el Postgres de pruebas
    no lo tiene). Cuenta llamadas para demostrar que /aura pregunta a la capa y no a la caché."""

    def __init__(self, respuesta):
        self.respuesta, self.llamadas = respuesta, 0

    async def __call__(self, lat, lon):
        self.llamadas += 1
        return copy.deepcopy(self.respuesta)


def _sin_google(monkeypatch):
    """Cualquier llamada a Google en este camino es un fallo, no un dato."""
    import app.place.providers.google as google

    async def _prohibido(*a, **k):
        raise AssertionError("/aura llamó a Google")
    for nombre in ("_nearest_categoria", "_mejor_transporte", "_ruta_a_pie", "_entorno_google"):
        monkeypatch.setattr(google, nombre, _prohibido)


@pytest.fixture
async def banco(monkeypatch):
    """`public.aura_pois_cache` creada por el DDL REAL como un dueño NOSUPERUSER + BYPASSRLS, y
    nacida con la exposición medida en producción (los tres roles con todo)."""
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
        await cx.execute(text("DROP TABLE IF EXISTS public.aura_pois_cache"))

    motores = []

    def motor(rol):
        m = create_async_engine(URL, poolclass=NullPool, connect_args={
            "server_settings": {"role": rol, "search_path": "public"}})
        motores.append(m)
        return m

    dueno = motor(DUENO)
    monkeypatch.setattr(assets, "_aura_cache_ready", False)
    async with async_sessionmaker(dueno)() as s:
        await assets.ensure_aura_cache_table(s)
    async with dueno.begin() as cx:
        await cx.execute(text("GRANT ALL PRIVILEGES ON TABLE public.aura_pois_cache "
                              "TO anon, authenticated, service_role"))
    try:
        yield {"admin": admin, "motor": motor, "dueno": dueno,
               "Sesion": async_sessionmaker(dueno, expire_on_commit=False)}
    finally:
        for m in motores:
            await m.dispose()
        async with admin.begin() as cx:
            await cx.execute(text("DROP TABLE IF EXISTS public.aura_pois_cache"))
        await admin.dispose()


async def _efectivos(admin, rol):
    async with admin.connect() as cx:
        return [p for p in PRIVS if (await cx.execute(text(
            "SELECT has_table_privilege(:r, 'public.aura_pois_cache', :p)"), {"r": rol, "p": p})).scalar()]


async def _estado(admin):
    async with admin.connect() as cx:
        return dict((await cx.execute(text(
            "SELECT c.relrowsecurity AS rls, c.relforcerowsecurity AS force, "
            "pg_get_userbyid(c.relowner) AS dueno, "
            "(SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='aura_pois_cache') AS politicas "
            "FROM pg_class c WHERE c.oid = 'public.aura_pois_cache'::regclass"))).mappings().first())


async def _intenta(motor, sql):
    try:
        async with motor.begin() as cx:
            await cx.execute(text(sql))
        return "ok"
    except Exception as e:  # noqa: BLE001
        return type(getattr(e, "orig", e)).__name__ + ": " + str(getattr(e, "orig", e))[:80]


async def _aplica_039(banco):
    from app.esquema_requerido import aplicar_migracion
    async with banco["Sesion"]() as s:
        await aplicar_migracion(str(M039), db=s)


@pg
async def test_039_cierra_los_tres_roles_y_el_dueno_conserva_el_crud(banco):
    admin, motor = banco["admin"], banco["motor"]
    # CONTROL POSITIVO: la exposición de producción está reproducida.
    assert (await _estado(admin))["rls"] is False
    for rol in ROLES:
        assert await _efectivos(admin, rol) == list(PRIVS), rol
    assert await _intenta(motor("anon"), "SELECT count(*) FROM public.aura_pois_cache") == "ok"

    await _aplica_039(banco)

    e = await _estado(admin)
    assert e == {"rls": True, "force": False, "dueno": DUENO, "politicas": 0}, e
    for rol in ROLES:
        assert await _efectivos(admin, rol) == [], rol
        m = motor(rol)
        for sql in ("SELECT count(*) FROM public.aura_pois_cache",
                    f"INSERT INTO public.aura_pois_cache (activo_id, pois) VALUES ('{OTRO}', '[]')",
                    "UPDATE public.aura_pois_cache SET pois = '[]'",
                    "DELETE FROM public.aura_pois_cache",
                    "TRUNCATE public.aura_pois_cache"):
            r = await _intenta(m, sql)
            assert "InsufficientPrivilege" in r and "permission denied" in r, (rol, sql, r)
    async with admin.connect() as cx:
        publico = (await cx.execute(text(
            "SELECT count(*) FROM pg_class c, aclexplode(c.relacl) a "
            "WHERE c.oid = 'public.aura_pois_cache'::regclass AND a.grantee = 0"))).scalar()
    assert publico == 0
    # El dueño (el backend) sigue con su CRUD.
    assert await _intenta(banco["dueno"],
                          f"INSERT INTO public.aura_pois_cache (activo_id, pois) VALUES ('{OTRO}', '[]');") == "ok"
    assert await _intenta(banco["dueno"],
                          f"UPDATE public.aura_pois_cache SET computed_at = now() WHERE activo_id = '{OTRO}'") == "ok"
    assert await _intenta(banco["dueno"],
                          f"DELETE FROM public.aura_pois_cache WHERE activo_id = '{OTRO}'") == "ok"
    # Idempotente.
    await _aplica_039(banco)
    assert (await _estado(admin))["rls"] is True


async def _filas_en_cache(banco):
    async with banco["dueno"].connect() as cx:
        return (await cx.execute(text("SELECT count(*) FROM public.aura_pois_cache"))).scalar()


@pg
async def test_039_aura_YA_NO_lee_la_cache_aunque_tenga_una_entrada_fresca(banco, monkeypatch):
    """Tras la 039, y con una entrada FRESCA en la caché para este inmueble —la forma de un
    envenenamiento, o de un resultado viejo de Google—, `_pois_geo` responde desde la capa
    propia, no toca la caché y no llama a Google."""
    import app.rutas as rutas

    await _aplica_039(banco)
    async with banco["dueno"].begin() as cx:
        await cx.execute(text(
            "INSERT INTO public.aura_pois_cache (activo_id, pois, computed_at) "
            "VALUES (:id, CAST(:p AS jsonb), now())"), {"id": str(ACTIVO), "p": json.dumps(EN_CACHE)})
    capa = _CapaPropia(PROPIO)
    monkeypatch.setattr(rutas, "_servicios_propios", capa)
    _sin_google(monkeypatch)

    pois = await assets._pois_geo(LAT, LON)
    assert [p["nombre"] for p in pois] == ["Farmacia propia"]
    assert {p["fuente"] for p in pois} == {"propio"}
    assert capa.llamadas == 1
    assert await _filas_en_cache(banco) == 1, "la caché no se escribe"
    assert not hasattr(assets, "_pois_geo_cached"), "el camino de la caché se retiró entero"


class _FilaUnica:
    def __init__(self, fila):
        self.fila = fila

    def mappings(self):
        return self

    def first(self):
        return self.fila


class _SesionHibrida:
    """Sin PostGIS en el Postgres de pruebas: SOLO la búsqueda del inmueble (`ST_Y(geom)`) se
    responde en memoria. Todo lo demás —la caché— va a la base real, como el dueño."""

    def __init__(self, real):
        self.real = real

    async def execute(self, stmt, params=None):
        if "FROM activos_inmutables" in str(stmt):
            return _FilaUnica({"lat": LAT, "lon": LON, "tipo_activo": "departamento"})
        return await self.real.execute(stmt, params)

    async def commit(self):
        await self.real.commit()

    async def rollback(self):
        await self.real.rollback()


@pg
async def test_039_get_aura_por_http_mismo_contrato_desde_la_capa_propia(banco, monkeypatch):
    import main
    import app.rutas as rutas
    from app.database import get_db
    from app.limiter import limiter

    await _aplica_039(banco)
    async with banco["dueno"].begin() as cx:
        await cx.execute(text(
            "INSERT INTO public.aura_pois_cache (activo_id, pois, computed_at) "
            "VALUES (:id, CAST(:p AS jsonb), now())"), {"id": str(ACTIVO), "p": json.dumps(EN_CACHE)})
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(rutas, "_servicios_propios", _CapaPropia(PROPIO))
    _sin_google(monkeypatch)

    async def _isocronas(db, activo_id, lat, lon):  # fuera del alcance: Valhalla/PostGIS
        return []
    monkeypatch.setattr(assets, "_isocronas_geo_cached", _isocronas)

    async def _db():
        async with banco["Sesion"]() as real:
            yield _SesionHibrida(real)
            await real.commit()
    main.app.dependency_overrides[get_db] = _db
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as c:
            r = await c.get(f"/api/v1/assets/{ACTIVO}/aura")
    finally:
        main.app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d) == {"lat", "lon", "tipo_activo", "pois", "isocronas"}
    assert (d["lat"], d["lon"], d["tipo_activo"], d["isocronas"]) == (LAT, LON, "departamento", [])
    assert d["pois"] == [{"nombre": "Farmacia propia", "lat": -0.181, "lon": -78.468,
                          "distancia_m": 240, "minutos": 3, "cat": "farmacia", "emoji": "💊",
                          "color": "#5EEAD4", "fuente": "propio"}]
    assert await _filas_en_cache(banco) == 1
