"""AURA-POIS-CACHE FIX 0.1 — la caché de POIs de AURA-SINGLE nunca escribió.

CAUSA. `VALUES (:id, :pois::jsonb, now())` dentro de `text()`: el `::` del cast se come el
bindparam. SQLAlchemy registra `poi` (no `pois`) y el SQL viaja con `:pois::jsonb` LITERAL →
Postgres responde «syntax error at or near ":"» → el `except` best-effort lo tragaba con un
warning. Desde e545d1b (2026-06-29) la tabla no tiene ni una fila y cada /aura recomputa
contra Google. Mismo cepo que ya documentaba `app/place/providers/propia.py` («CAST(... AS
text[]) y NO `:subtipos::text[]`»).

  A · sin base: la sentencia REAL que ejecuta `_pois_geo_cached` (capturada en su call site,
      no copiada aquí) declara exactamente los binds que recibe; y una guarda sobre TODO
      `text()` literal de `app/` para que el cepo no vuelva.
  B · PostgreSQL 15 real (`TEST_DATABASE_URL`): INSERT jsonb real, ON CONFLICT, miss →
      persistencia, hit sin Google, `[]` no se cachea, un fallo real degrada sin romper, y el
      contrato HTTP de GET /{id}/aura.
  C · hallazgo adyacente con la MISMA causa: `save_ficha` (`:cisterna::date` …). Test rojo
      marcado xfail ESTRICTO hasta que Carlos decida si entra en este PR.

Sin `TEST_DATABASE_URL` los bloques B y C se SALTAN: un skip aquí es «esta evidencia no se
recogió», no un verde.
"""
from __future__ import annotations

import ast
import copy
import json
import logging
import os
import re
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import asyncpg as dialecto_asyncpg

import app.routers.assets as assets

RAIZ = Path(__file__).resolve().parents[1]
ACTIVO = uuid.UUID("0cb128c9-0000-4000-8000-00000000a0a0")
LAT, LON = -0.1807, -78.4678
POIS = [
    {"nombre": "Parque La Carolina", "categoria": "parque", "lat": -0.1795, "lon": -78.4851, "distancia_m": 420},
    {"nombre": "Farmacia Ñandú «24 h»", "categoria": "farmacia", "lat": -0.1812, "lon": -78.4671, "distancia_m": 95},
]

# Un `:nombre` que SQLAlchemy debería convertir en bind. El lookbehind replica el de
# SQLAlchemy (ni `::`, ni palabra, ni barra invertida delante); sin su lookahead `(?!:)`,
# que es justo lo que hace que `:pois::jsonb` se registre como `poi`.
_BIND_EN_FUENTE = re.compile(r"(?<![:\w\\]):([A-Za-z_]\w*)")


def _binds_sin_convertir(sql_compilado: str) -> list[str]:
    return _BIND_EN_FUENTE.findall(sql_compilado)


# ─────────────────────────────── A · sin base ────────────────────────────────
class _SinFila:
    def mappings(self):
        return self

    def first(self):
        return None


class _Espia:
    """AsyncSession mínima: registra cada (sentencia, parámetros) y devuelve «sin fila»."""

    def __init__(self):
        self.sentencias: list[tuple] = []

    async def execute(self, stmt, params=None):
        self.sentencias.append((stmt, dict(params or {})))
        return _SinFila()

    async def commit(self):
        pass

    async def rollback(self):
        pass


class _Google:
    """Doble de `_pois_geo` (Google Places): cuenta llamadas."""

    def __init__(self, respuesta):
        self.respuesta = respuesta
        self.llamadas = 0

    async def __call__(self, lat, lon):
        self.llamadas += 1
        return copy.deepcopy(self.respuesta)


async def test_upsert_de_la_cache_declara_exactamente_los_binds_que_recibe(monkeypatch):
    """La sentencia que de verdad ejecuta `_pois_geo_cached` al escribir. Con el defecto:
    binds {id, poi} frente a parámetros {id, pois}, y `:pois::jsonb` viaja literal."""
    monkeypatch.setattr(assets, "_aura_cache_ready", True)
    monkeypatch.setattr(assets, "_pois_geo", _Google(POIS))
    espia = _Espia()

    assert await assets._pois_geo_cached(espia, ACTIVO, LAT, LON) == POIS

    inserts = [(s, p) for s, p in espia.sentencias if "INSERT INTO aura_pois_cache" in str(s)]
    assert len(inserts) == 1, "el miss con POIs no vacíos debe intentar escribir la caché"
    stmt, params = inserts[0]
    assert set(stmt._bindparams) == {"id", "pois"} == set(params)
    compilado = stmt.compile(dialect=dialecto_asyncpg.dialect()).string
    assert _binds_sin_convertir(compilado) == [], compilado
    # Toda sentencia del camino (lectura incluida) cumple lo mismo.
    for s, p in espia.sentencias:
        assert set(s._bindparams) == set(p), str(s)


# Excepciones CONOCIDAS de la guarda, cada una con su motivo. Vacía = ningún `text()` de `app/`
# pierde un bind. No añadir entradas sin un test rojo que las describa.
_EXCEPCIONES_CONOCIDAS = {
    # SAME-ROOT-CAUSE · save_ficha (POST /{id}/ficha): `:cisterna::date` y hermanos. Test rojo
    # `test_save_ficha_persiste_las_fechas` (xfail estricto) hasta la decisión de Carlos.
    ("app/routers/assets.py", frozenset({"cisterna", "techo", "fachada", "cableado"})),
}


def _literal(nodo) -> str | None:
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Add):
        a, b = _literal(nodo.left), _literal(nodo.right)
        return a + b if a is not None and b is not None else None
    return None  # f-strings y construcciones dinámicas: fuera del alcance de esta guarda


def _textos_literales():
    for ruta in sorted((RAIZ / "app").rglob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call) or not nodo.args:
                continue
            f = nodo.func
            nombre = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if nombre != "text":
                continue
            sql = _literal(nodo.args[0])
            if sql is not None:
                yield ruta.relative_to(RAIZ).as_posix(), nodo.lineno, sql


def test_ningun_text_literal_de_app_pierde_un_bind_por_un_cast():
    """Guarda del cepo: para cada `text("…")` literal de `app/`, todo `:nombre` del fuente
    queda registrado como bind. `:x::tipo` lo rompe; `CAST(:x AS tipo)` no."""
    vistos, fallos = 0, []
    for ruta, linea, sql in _textos_literales():
        vistos += 1
        en_fuente = set(_BIND_EN_FUENTE.findall(sql))
        registrados = set(text(sql)._bindparams)
        perdidos = en_fuente - registrados
        if perdidos and (ruta, frozenset(perdidos)) not in _EXCEPCIONES_CONOCIDAS:
            fallos.append(f"{ruta}:{linea} pierde {sorted(perdidos)}")
    assert vistos > 100, f"la guarda no está viendo el código ({vistos} text() literales)"
    assert fallos == [], "\n".join(fallos)


def test_las_excepciones_conocidas_siguen_existiendo():
    """Si alguien arregla el caso conocido, la excepción debe salir de la lista (no se
    acumulan permisos muertos)."""
    perdidos_por_ruta = {}
    for ruta, _, sql in _textos_literales():
        perdidos = set(_BIND_EN_FUENTE.findall(sql)) - set(text(sql)._bindparams)
        if perdidos:
            perdidos_por_ruta.setdefault(ruta, []).append(frozenset(perdidos))
    for ruta, conjunto in _EXCEPCIONES_CONOCIDAS:
        assert conjunto in perdidos_por_ruta.get(ruta, []), f"excepción muerta: {ruta} {sorted(conjunto)}"


# ──────────────────────────── B · Postgres 15 real ────────────────────────────
URL = os.getenv("TEST_DATABASE_URL", "")
pg = pytest.mark.skipif(not URL, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas")


@pytest.fixture
async def base(monkeypatch):
    """Esquema propio y efímero; la tabla la crea el `_AURA_CACHE_DDL` REAL."""
    from app.config import settings
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    if settings.database_url and URL.split("@")[-1] in settings.database_url:
        pytest.fail("TEST_DATABASE_URL apunta a la base del producto. Abortado.")
    esquema = "aura_" + uuid.uuid4().hex[:10]
    admin = create_async_engine(URL, poolclass=NullPool)
    async with admin.begin() as cx:
        await cx.execute(text(f"CREATE SCHEMA {esquema}"))
    motor = create_async_engine(URL, poolclass=NullPool,
                                connect_args={"server_settings": {"search_path": esquema}})
    Sesion = async_sessionmaker(motor, expire_on_commit=False)
    monkeypatch.setattr(assets, "_aura_cache_ready", False)
    try:
        yield Sesion
    finally:
        await motor.dispose()
        async with admin.begin() as cx:
            await cx.execute(text(f"DROP SCHEMA {esquema} CASCADE"))
        await admin.dispose()


async def _filas(Sesion):
    async with Sesion() as db:
        r = (await db.execute(text(
            "SELECT activo_id::text AS activo_id, jsonb_typeof(pois) AS tipo, pois, "
            "       computed_at > now() - interval '1 minute' AS fresca "
            "FROM aura_pois_cache ORDER BY activo_id"))).mappings().all()
    out = []
    for f in r:
        d = dict(f)
        d["pois"] = json.loads(d["pois"]) if isinstance(d["pois"], str) else d["pois"]
        out.append(d)
    return out


def _warnings(caplog, trozo):
    return [r for r in caplog.records if r.levelno >= logging.WARNING and trozo in r.getMessage()]


@pg
async def test_miss_persiste_jsonb_real_y_el_hit_no_llama_a_google(base, monkeypatch, caplog):
    google = _Google(POIS)
    monkeypatch.setattr(assets, "_pois_geo", google)

    async with base() as db:
        assert await assets._pois_geo_cached(db, ACTIVO, LAT, LON) == POIS
    assert google.llamadas == 1
    assert _warnings(caplog, "aura cache") == [], [r.getMessage() for r in caplog.records]
    filas = await _filas(base)
    assert filas == [{"activo_id": str(ACTIVO), "tipo": "array", "pois": POIS, "fresca": True}]

    # HIT: otra sesión, sin Google.
    async with base() as db:
        assert await assets._pois_geo_cached(db, ACTIVO, LAT, LON) == POIS
    assert google.llamadas == 1


@pg
async def test_on_conflict_actualiza_una_entrada_caducada(base, monkeypatch, caplog):
    async with base() as db:
        await assets.ensure_aura_cache_table(db)
        await db.execute(text(
            "INSERT INTO aura_pois_cache (activo_id, pois, computed_at) "
            "VALUES (:id, CAST(:p AS jsonb), now() - interval '40 days')"),
            {"id": str(ACTIVO), "p": json.dumps([{"nombre": "viejo"}])})
        await db.commit()
    google = _Google(POIS)
    monkeypatch.setattr(assets, "_pois_geo", google)

    async with base() as db:
        assert await assets._pois_geo_cached(db, ACTIVO, LAT, LON) == POIS
    assert google.llamadas == 1, "una entrada caducada (> TTL) no se sirve"
    assert _warnings(caplog, "aura cache") == []
    assert await _filas(base) == [{"activo_id": str(ACTIVO), "tipo": "array", "pois": POIS, "fresca": True}]


@pg
async def test_una_lista_vacia_no_se_cachea(base, monkeypatch):
    google = _Google([])
    monkeypatch.setattr(assets, "_pois_geo", google)
    for _ in range(2):
        async with base() as db:
            assert await assets._pois_geo_cached(db, ACTIVO, LAT, LON) == []
    assert google.llamadas == 2, "un [] transitorio no se congela: cada vista vuelve a preguntar"
    assert await _filas(base) == []


@pg
async def test_un_fallo_real_de_la_cache_degrada_sin_romper(base, monkeypatch, caplog):
    """Sin la tabla (DDL saltado a propósito): la lectura Y la escritura fallan de verdad en
    Postgres; /aura igual recibe los POIs y la sesión queda usable (sin PendingRollback)."""
    monkeypatch.setattr(assets, "_aura_cache_ready", True)
    google = _Google(POIS)
    monkeypatch.setattr(assets, "_pois_geo", google)

    async with base() as db:
        assert await assets._pois_geo_cached(db, ACTIVO, LAT, LON) == POIS
        assert (await db.execute(text("SELECT 1"))).scalar() == 1
        await db.commit()
    assert google.llamadas == 1
    assert len(_warnings(caplog, "aura cache: lectura falló")) == 1
    assert len(_warnings(caplog, "aura cache: escritura falló")) == 1


class _FilaUnica:
    def __init__(self, fila):
        self.fila = fila

    def mappings(self):
        return self

    def first(self):
        return self.fila


class _SesionHibrida:
    """El test de Postgres no tiene PostGIS: SOLO la búsqueda del inmueble (`ST_Y(geom)`) se
    responde en memoria. Todo lo demás —la caché entera— va a la base real."""

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
async def test_contrato_http_de_aura_sin_cambios_y_la_segunda_vista_sale_de_la_cache(base, monkeypatch):
    import main
    from app.database import get_db
    from app.limiter import limiter

    monkeypatch.setattr(limiter, "enabled", False)
    google = _Google(POIS)
    monkeypatch.setattr(assets, "_pois_geo", google)
    isocronas = [{"minutos": 15, "geometry": {"type": "Polygon", "coordinates": []}}]

    async def _isocronas(db, activo_id, lat, lon):  # fuera del alcance: Valhalla/PostGIS
        return isocronas
    monkeypatch.setattr(assets, "_isocronas_geo_cached", _isocronas)

    async def _db():
        async with base() as real:
            yield _SesionHibrida(real)
            await real.commit()
    main.app.dependency_overrides[get_db] = _db
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as c:
            respuestas = [await c.get(f"/api/v1/assets/{ACTIVO}/aura") for _ in range(2)]
    finally:
        main.app.dependency_overrides.pop(get_db, None)

    for r in respuestas:
        assert r.status_code == 200, r.text
        assert r.json() == {"lat": LAT, "lon": LON, "tipo_activo": "departamento",
                            "pois": POIS, "isocronas": isocronas}
    assert google.llamadas == 1, "la segunda vista debe salir de la caché"
    assert [f["activo_id"] for f in await _filas(base)] == [str(ACTIVO)]


# ─────────────── C · hallazgo adyacente con la MISMA causa (save_ficha) ───────────────
@pg
@pytest.mark.xfail(strict=True, reason=(
    "SAME-ROOT-CAUSE · save_ficha usa `:cisterna::date`, `:techo::date`, `:fachada::date`, "
    "`:cableado::date` (assets.py): el cast se come el bind y el INSERT no llega a Postgres "
    "válido. Pendiente de decisión: ¿entra en este PR?"))
async def test_save_ficha_persiste_las_fechas(base, monkeypatch):
    """POST /{id}/ficha tal como lo llama FichaTecnica.jsx: las fechas llegan como TEXTO."""
    async with base() as db:
        await db.execute(text(
            'CREATE TABLE ficha_tecnica_mantenimiento (id uuid PRIMARY KEY, activo_id uuid UNIQUE, '
            'tipo_tuberia varchar, "año_construccion" int, tipo_estructura varchar, '
            'calidad_acabados varchar, ultimo_mantenimiento_cisterna date, '
            'ultima_impermeabilizacion_techo date, ultima_pintura_fachada date, '
            'ultimo_cambio_cableado_electrico date, monto_invertido_mejoras numeric, '
            'descripcion_mejoras text, foto_evidencias text, estado_revision text, '
            'updated_at timestamp)'))
        await db.commit()

    async def _dueno(db, activo_id, user):
        return None
    monkeypatch.setattr(assets, "_assert_owner", _dueno)
    payload = assets.FichaRequest(
        tipo_tuberia="cobre", anio_construccion=2012, ultimo_mantenimiento_cisterna="2026-05-01",
        ultima_impermeabilizacion_techo="2025-11-15", ultima_pintura_fachada=None,
        ultimo_cambio_cableado_electrico="2024-02-29", monto_invertido_mejoras=1200.5)

    async with base() as db:
        assert (await assets.save_ficha(ACTIVO, payload, user=None, db=db))["ok"] is True
    async with base() as db:
        f = (await db.execute(text(
            "SELECT ultimo_mantenimiento_cisterna::text AS c, ultima_impermeabilizacion_techo::text AS t, "
            "ultima_pintura_fachada AS p, ultimo_cambio_cableado_electrico::text AS e "
            "FROM ficha_tecnica_mantenimiento WHERE activo_id = :id"), {"id": str(ACTIVO)})).mappings().first()
    assert dict(f) == {"c": "2026-05-01", "t": "2025-11-15", "p": None, "e": "2024-02-29"}
