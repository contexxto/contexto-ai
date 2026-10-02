"""POI-SOURCE-PROVENANCE · la 043 añade la procedencia persistible de la capa de POIs SIN cambiar el
producto: solo esquema, sin backfill, sin tocar el escritor ni Place Evidence v0.

  A · sin base (CI):
      · la migración hace SOLO lo que dice: una tabla nueva cerrada (RLS + REVOKE explícito), seis
        columnas nullable sin default, CHECK + FK y nada más (ni DML, ni GRANT, ni funciones,
        triggers, secuencias, vistas o privilegios por defecto); el ROLLBACK está comentado;
      · el vocabulario de campos de origen CONTIENE el de v0 y v0 NO aprende `taxonomy.primary`;
      · ningún lector productivo de la capa hace `SELECT *` ni nombra una columna nueva.
  B · PostgreSQL real (`TEST_DATABASE_URL`; en el CI, 15 sin PostGIS; en local, además 17.6 y PostGIS):
      `pois_propios` como la mide producción (mismo orden de columnas, CHECK e índices), la 023 y la
      040 REALES aplicadas por el aplicador del producto con un dueño NOSUPERUSER + BYPASSRLS —el
      doble del `postgres` de producción— y los privilegios POR DEFECTO de ese dueño ABIERTOS a
      propósito (el peor caso: la 043 tiene que cerrarse sola). Filas sintéticas de las dos
      fuentes, abiertas y cerradas, con curación; o la foto REAL de la capa si `POIS_CAPA_FOTO`
      apunta a ella (solo en local: datos públicos de POIs que no viven en el repo).
        · filas, columnas, vista, ACL y RLS intactos; las 6 columnas NULL en todo lo histórico;
        · la tabla de corridas nace cerrada aunque el default esté abierto (control positivo);
        · invariantes: la regla central (taxonomy.primary ⇒ categoria_overture NULL), procedencia
          parcial, forma del linaje, FK compuesta diferida, manifiesto;
        · rollback lógico exacto, reaplicación = no-op, estados ajenos = FAIL CLOSED;
        · el escritor PRE-R4 (`f8614e1d`, el de producción hasta R4 y el de su rollback) sigue escribiendo
          sin conocer las columnas (con PostGIS, el `main()` real: Overture sigue ROTA por D-4 y OSM se
          refresca);
        · lectores (/aura, chat, mapa) y Place Evidence v0 devuelven EXACTAMENTE lo mismo.
`MIGRACION_043_RUTA` existe SOLO para el control por mutación (evidencia del informe): apunta las
pruebas a una copia mutada de la 043 para comprobar que la prueba que vigila cada regla se pone roja.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.test_poi_refresh_source_isolation import (_carga, _corre, _estado, _fuentes, _osm, _parquet,  # noqa: F401
                                                     duckdb_spatial, foso)

RAIZ = Path(__file__).resolve().parents[1]
M043 = Path(os.getenv("MIGRACION_043_RUTA") or RAIZ / "migrations" / "043_poi_source_provenance.sql")
M023 = RAIZ / "migrations" / "023_curacion_engancha_poi.sql"
M040 = RAIZ / "migrations" / "040_place_source_perimeter.sql"
NUEVAS = ("ingestion_run_id", "source_category", "source_category_namespace", "source_record_version",
          "source_updated_at", "source_lineage")
CKS_CAPA = ("ck_pois_categoria_fuente_con_espacio", "ck_pois_espacio_vocabulario", "ck_pois_espacio_de_su_fuente",
            "ck_pois_columna_legada_coherente", "ck_pois_corrida_exige_espacio", "ck_pois_procedencia_exige_corrida",
            "ck_pois_linaje_forma")
ROLES_PUB = ("anon", "authenticated", "service_role", "contexto_audit_ro")
DUENO = "p043_owner"
SHA = "47a0ef61f0535bba535aad21c58522140fd7b3a1"
HUELLA = "a" * 64
# Las 14 columnas de producción (orden medido) y las 17 de `pois_vivos` (la 023), EXPLÍCITAS: una huella
# con `t::text` cambiaría al añadir columnas aunque sean NULL.
COLS14 = ("id, nombre, categoria, categoria_overture, geom::text, fuente, confianza, overture_id, marca, direccion, "
          "operativo, actualizado_en, osm_id, ciudad")
COLS17 = ("id, nombre, categoria, categoria_overture, geom::text, fuente, confianza, overture_id, osm_id, marca, "
          "direccion, operativo, ciudad, actualizado_en, verificado_en, verificado_por, verificacion_accion")


def _sin_comentarios(sql: str) -> str:
    return "\n".join(l.split("--", 1)[0] for l in sql.splitlines())


def _cuerpo() -> str:
    return _sin_comentarios(M043.read_text(encoding="utf-8").split("-- ── ROLLBACK", 1)[0])


# ─────────────────────────────── A · sin base ────────────────────────────────
def test_A_la_043_hace_solo_lo_que_dice():
    cuerpo = _cuerpo()
    assert cuerpo.strip().startswith("BEGIN;") and cuerpo.rstrip().endswith("COMMIT;")
    assert "SET LOCAL lock_timeout = '3s';" in cuerpo
    assert "CREATE TABLE public.poi_ingestion_run (" in cuerpo
    assert "ALTER TABLE public.poi_ingestion_run ENABLE ROW LEVEL SECURITY;" in cuerpo
    assert "REVOKE ALL PRIVILEGES ON TABLE public.poi_ingestion_run FROM PUBLIC;" in cuerpo
    assert "ARRAY['anon', 'authenticated', 'service_role']" in cuerpo
    assert "REVOKE ALL PRIVILEGES ON TABLE public.poi_ingestion_run FROM %I" in cuerpo
    # Seis columnas, nullable y SIN default (catálogo, sin reescritura). NULL = «no se sabe».
    columnas_nuevas = re.findall(r"ADD COLUMN\s+(\w+)\s+([^,\n]+),", cuerpo)
    assert [a for a, _ in columnas_nuevas] == list(NUEVAS)
    assert all(not re.search(r"(?i)\b(DEFAULT|NOT\s+NULL)\b", tipo) for _, tipo in columnas_nuevas), columnas_nuevas
    for ck in (*CKS_CAPA, "fk_pois_ingestion_run", "ck_pir_fase", "ck_pir_release", "uq_pir_id_proveedor_ciudad"):
        assert f"CONSTRAINT {ck}" in cuerpo, ck
    assert "DEFERRABLE INITIALLY DEFERRED" in cuerpo and "ON DELETE RESTRICT" in cuerpo
    # Nada de lo que la unidad no autoriza: ni DML (backfill), ni GRANT, ni objetos ejecutables, ni
    # tocar la vista, ni privilegios por defecto, ni FORCE.
    assert not re.search(r"(?im)^\s*(INSERT|UPDATE|DELETE|TRUNCATE|MERGE)\b", cuerpo)
    assert not re.search(r"(?i)\bGRANT\b", cuerpo)
    assert not re.search(r"(?i)\bCREATE\s+(OR\s+REPLACE\s+)?(FUNCTION|TRIGGER|SEQUENCE|INDEX|VIEW|POLICY|RULE)\b", cuerpo)
    assert not re.search(r"(?i)\bALTER\s+(VIEW|DEFAULT\s+PRIVILEGES)\b", cuerpo)
    assert not re.search(r"(?i)\bFORCE\s+ROW\s+LEVEL", cuerpo)
    assert not re.search(r"(?i)\bDROP\b", cuerpo)
    assert set(re.findall(r"public\.([a-z_0-9]+)", cuerpo)) == {"pois_propios", "pois_vivos", "poi_ingestion_run"}
    # Las compuertas fail-closed, todas.
    for compuerta in ("¿Base equivocada?", "el dueño de pois_propios no es quien aplica", "¿Es la tabla correcta?",
                      "pois_propios sin RLS", "pois_vivos sin security_invoker", "destinatarios externos en su ACL",
                      "ya aplicada", "estado intermedio o ajeno", "no quedó con RLS", "conserva % sobre poi_ingestion_run",
                      "hay ACL de columna", "la forma declarada", "con procedencia NULL (deben ser todas)",
                      "la definición de pois_vivos"):
        assert compuerta in cuerpo, compuerta


def test_A_el_rollback_documentado_esta_comentado_y_deshace_todo():
    rollback = M043.read_text(encoding="utf-8").split("-- ── ROLLBACK", 1)[1]
    assert all(l.startswith("--") or not l.strip() for l in rollback.splitlines()[1:])
    for nombre in (*CKS_CAPA, "fk_pois_ingestion_run"):
        assert f"DROP CONSTRAINT IF EXISTS {nombre}" in rollback, nombre
    for col in NUEVAS:
        assert f"DROP COLUMN IF EXISTS {col}" in rollback, col
    assert "DROP TABLE IF EXISTS public.poi_ingestion_run;" in rollback


def test_A_el_vocabulario_contiene_el_de_v0_y_v0_no_aprende_taxonomy():
    from app.contracts.place_evidence_v0 import SourceCategoryNamespace
    from app.place import clasificacion

    lista = re.search(r"source_category_namespace IN \((.*?)\)\)", _cuerpo(), re.S)
    vocabulario = set(re.findall(r"'([^']+)'", lista.group(1)))
    v0 = {ns.value for ns in SourceCategoryNamespace}
    assert v0 <= vocabulario, v0 - vocabulario
    assert {"overture:taxonomy.primary", "osm:station"} <= vocabulario
    # v0 sigue congelado: ni aprende el espacio nuevo, ni deja de rotular `categoria_overture` de
    # Overture como `categories.primary` (la suposición que protege `ck_pois_columna_legada_coherente`).
    assert "overture:taxonomy.primary" not in v0
    valor, ns, _ = clasificacion._categoria_de_la_fuente("overture", "grocery_store")
    assert (valor, ns) == ("grocery_store", SourceCategoryNamespace.OVERTURE_CATEGORIES_PRIMARY)


_SELECT_ESTRELLA = re.compile(r"(?i)\bSELECT\s+(DISTINCT\s+(ON\s*\([^)]*\)\s*)?)?\*|\b[a-z_]+\.\*")


def _sql_de_la_capa(raiz: Path):
    """Cada literal de SQL del producto que nombra la capa, con su fichero."""
    for carpeta in ("app", "scripts"):
        for f in sorted((raiz / carpeta).rglob("*.py")):
            src = f.read_text(encoding="utf-8", errors="replace")
            for lit in re.findall(r'"""(.*?)"""|"((?:[^"\\\n]|\\.)*)"', src, re.S):
                s = lit[0] or lit[1]
                if re.search(r"(?is)\bSELECT\b.*\b(FROM|JOIN)\s+(public\.)?pois_(propios|vivos)\b", s):
                    yield f.relative_to(raiz).as_posix(), s


def test_A_ningun_lector_productivo_hace_select_estrella_ni_nombra_las_columnas_nuevas():
    hallazgos, vistos = [], 0
    for fichero, sql in _sql_de_la_capa(RAIZ):
        vistos += 1
        if _SELECT_ESTRELLA.search(sql.replace("count(*)", "")):
            hallazgos.append((fichero, "SELECT *", sql[:80]))
        for col in NUEVAS:
            if re.search(rf"\b{col}\b", sql):
                hallazgos.append((fichero, col, sql[:80]))
    assert vistos >= 10, f"la guarda no encontró los lectores de la capa ({vistos}): sería vacua"
    assert not hallazgos, hallazgos
    # La vista de la 023 enumera sus columnas: lo nuevo de `pois_propios` no llega a ningún lector.
    vista = re.search(r"CREATE OR REPLACE VIEW pois_vivos AS(.*?)FROM pois_propios p", M023.read_text(encoding="utf-8"), re.S)
    assert vista and not _SELECT_ESTRELLA.search(_sin_comentarios(vista.group(1)))


def test_A_la_guarda_de_select_estrella_no_es_vacua():
    assert _SELECT_ESTRELLA.search("SELECT * FROM pois_vivos")
    assert _SELECT_ESTRELLA.search("SELECT p.* FROM pois_propios p")
    assert not _SELECT_ESTRELLA.search("SELECT categoria, count(*)::int AS n FROM pois_vivos".replace("count(*)", ""))


# ──────────────────────────── B · Postgres real ────────────────────────────
URL = os.getenv("TEST_DATABASE_URL", "")
pg = pytest.mark.skipif(not URL, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas")
FOTO = os.getenv("POIS_CAPA_FOTO", "")
VIEJO = "2026-09-22 14:30:03+00"
CERRADO = "2026-08-25 00:34:04+00"
SINTETICAS = [  # (id, nombre, categoria, categoria_overture, lon, lat, fuente, confianza, overture_id, osm_id, operativo, actualizado_en)
    (1, "Súper Overture", "supermercado", "grocery_store", -78.4800, -0.1800, "overture", 0.6, "ov-a", None, True, VIEJO),
    (2, "Clínica Overture", "salud", "medical_center", -78.4810, -0.1810, "overture", 0.7, "ov-b", None, True, VIEJO),
    (3, "Parque Overture cerrado", "parque", "park", -78.4820, -0.1790, "overture", 0.8, "ov-c", None, False, CERRADO),
    (4, "Farmacia OSM", "farmacia", "pharmacy", -78.4805, -0.1805, "osm", None, None, "node/1", True, VIEJO),
    (5, "Parque OSM", "parque", "park", -78.4795, -0.1795, "osm", None, None, "way/2", True, VIEJO),
    (6, "Estación OSM", "transporte", "metro", -78.4790, -0.1810, "osm", None, None, "node/3", True, VIEJO),
    (7, "Parada OSM", "transporte", "parada_bus", -78.4800, -0.1812, "osm", None, None, "node/4", True, VIEJO),
    (8, "Minimarket OSM cerrado", "supermercado", "minimarket", -78.4802, -0.1802, "osm", None, None, "node/5", False, CERRADO),
]


def _doble_pois(con_postgis: bool) -> str:
    """`pois_propios` como la mide producción (esquema_pois_ro_PRE.json, 2026-10-02): orden de columnas,
    defaults, CHECK e índices. `geom` es PostGIS si el banco lo tiene; si no, un doble de forma."""
    geom = "geometry(Point, 4326)" if con_postgis else "text"
    gist = "CREATE INDEX pois_propios_geom_gix ON public.pois_propios USING gist (geom);" if con_postgis else ""
    return f"""
    CREATE TABLE public.pois_propios (
        id bigserial PRIMARY KEY, nombre text, categoria text NOT NULL, categoria_overture text,
        geom {geom} NOT NULL, fuente text NOT NULL DEFAULT 'overture', confianza real, overture_id text,
        marca text, direccion text, operativo boolean DEFAULT true,
        actualizado_en timestamptz NOT NULL DEFAULT now(), osm_id text, ciudad text NOT NULL DEFAULT 'quito',
        CONSTRAINT ck_pois_categoria CHECK (categoria IN ('salud','farmacia','supermercado','educacion','parque',
            'centro_comercial','transporte','iglesia','seguridad')),
        CONSTRAINT ck_pois_ciudad CHECK (ciudad = lower(btrim(ciudad)) AND ciudad <> '' AND ciudad !~ '\\s'),
        CONSTRAINT ck_pois_fuente CHECK (fuente IN ('overture','osm')));
    CREATE INDEX pois_propios_cat_idx ON public.pois_propios (categoria);
    CREATE INDEX pois_propios_ciudad_idx ON public.pois_propios (ciudad);
    CREATE UNIQUE INDEX pois_propios_osm_uidx ON public.pois_propios (osm_id) WHERE osm_id IS NOT NULL;
    CREATE UNIQUE INDEX pois_propios_overture_uidx ON public.pois_propios (overture_id) WHERE overture_id IS NOT NULL;
    {gist}
    """


async def _limpia(cx):
    await cx.execute(text("DROP VIEW IF EXISTS public.pois_vivos CASCADE"))
    await cx.execute(text("DROP TABLE IF EXISTS public.entorno_curacion, public.pois_propios, public.poi_ingestion_run, "
                          "public.control043 CASCADE"))


async def _aplica(banco, ruta: Path | None = None, sql: str | None = None, motor=None) -> list[str]:
    """Por el aplicador REAL del producto (`app.esquema_requerido.aplicar_migracion`). Devuelve los avisos."""
    from app.esquema_requerido import aplicar_migracion
    from sqlalchemy.ext.asyncio import async_sessionmaker
    tmp = None
    if sql is not None:
        tmp = Path(tempfile.gettempdir()) / f"m043_{uuid.uuid4().hex}.sql"
        tmp.write_text(sql, encoding="utf-8")
    avisos: list[str] = []
    try:
        async with async_sessionmaker(motor or banco["dueno"])() as s:
            cruda = await (await s.connection()).get_raw_connection()
            cruda.driver_connection.add_log_listener(lambda _c, m: avisos.append(m.message))
            await aplicar_migracion(str(tmp or ruta or M043), db=s)
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)
    return avisos


async def _intenta_aplicar(banco, **k) -> str:
    try:
        await _aplica(banco, **k)
        return "ok"
    except Exception as e:  # noqa: BLE001
        return str(getattr(e, "orig", e))[:300]


def _causa(e: BaseException):
    orig = getattr(e, "orig", e)
    return getattr(orig, "__cause__", None) or orig


async def _intenta(motor, *sentencias) -> str:
    """Una transacción con varias sentencias (la FK diferida se comprueba en el COMMIT)."""
    try:
        async with motor.begin() as cx:
            for s, p in sentencias:
                await cx.execute(text(s), p)
        return "ok"
    except Exception as e:  # noqa: BLE001
        c = _causa(e)
        return f"{type(c).__name__}:{getattr(c, 'constraint_name', None) or str(c)[:120]}"


async def _uno(motor, sql, **p):
    async with motor.connect() as cx:
        return (await cx.execute(text(sql), p)).scalar()


async def _lista(motor, sql, **p) -> list:
    async with motor.connect() as cx:
        return list((await cx.execute(text(sql), p)).scalars())


@pytest.fixture
async def banco():
    from app.config import settings
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    if settings.database_url and URL.split("@")[-1] in settings.database_url:
        pytest.fail("TEST_DATABASE_URL apunta a la base del producto. Abortado.")
    admin = create_async_engine(URL, poolclass=NullPool)
    async with admin.begin() as cx:
        for rol in ROLES_PUB:
            await cx.execute(text(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{rol}') "
                                  f"THEN CREATE ROLE {rol} NOLOGIN; END IF; END $$;"))
        await cx.execute(text(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{DUENO}') "
                              f"THEN CREATE ROLE {DUENO} NOLOGIN NOSUPERUSER BYPASSRLS; END IF; END $$;"))
        await cx.execute(text(f"GRANT USAGE, CREATE ON SCHEMA public TO {DUENO}"))
        await cx.execute(text("GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role, contexto_audit_ro"))
        dueno_actual = (await cx.execute(text(
            "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = to_regclass('public.pois_propios')"))).scalar()
        if dueno_actual not in (None, DUENO, "p040_owner"):
            pytest.fail(f"public.pois_propios ya existe y es de {dueno_actual}: no se toca")
        await _limpia(cx)
        try:
            async with cx.begin_nested():
                await cx.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            con_postgis = True
        except Exception:  # noqa: BLE001 — el Postgres del CI no trae PostGIS
            con_postgis = False

    motores = []

    def motor(rol=None):
        args = {"server_settings": {"role": rol, "search_path": "public"}} if rol else {}
        m = create_async_engine(URL, poolclass=NullPool, connect_args=args)
        motores.append(m)
        return m

    dueno = motor(DUENO)
    b = {"admin": admin, "motor": motor, "dueno": dueno, "postgis": con_postgis,
         "Sesion": async_sessionmaker(dueno, expire_on_commit=False)}
    try:
        async with dueno.begin() as cx:
            for s in _doble_pois(con_postgis).split(";"):
                if s.strip():
                    await cx.execute(text(s))
        await _aplica(b, ruta=M023)                    # la curación y la vista REALES de la 023
        async with dueno.begin() as cx:
            # La exposición de antes de la 040 (medida en producción), para que la 040 real la cierre.
            await cx.execute(text("GRANT ALL PRIVILEGES ON TABLE public.pois_propios, public.entorno_curacion, "
                                  "public.pois_vivos TO anon, authenticated, service_role"))
            if FOTO:
                g = "ST_GeomFromEWKB(decode(:g, 'hex'))" if con_postgis else ":g"
                filas = json.loads(Path(FOTO).read_text(encoding="utf-8"))
                await cx.execute(text(
                    f"INSERT INTO public.pois_propios (id, nombre, categoria, categoria_overture, geom, fuente, confianza, "
                    f"overture_id, osm_id, marca, direccion, operativo, ciudad, actualizado_en) VALUES (:id, :nombre, "
                    f":categoria, :categoria_overture, {g}, :fuente, :confianza, :overture_id, :osm_id, :marca, :direccion, "
                    f":operativo, :ciudad, CAST(CAST(:actualizado_en AS text) AS timestamptz))"),
                    [{**{k: f[k] for k in ("id", "nombre", "categoria", "categoria_overture", "fuente", "confianza",
                                           "overture_id", "osm_id", "marca", "direccion", "operativo", "ciudad",
                                           "actualizado_en")}, "g": f["geom_ewkb"]} for f in filas])
            else:
                g = "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)" if con_postgis else ":wkt"
                await cx.execute(text(
                    f"INSERT INTO public.pois_propios (id, nombre, categoria, categoria_overture, geom, fuente, confianza, "
                    f"overture_id, osm_id, marca, direccion, operativo, ciudad, actualizado_en) VALUES (:id, :n, :c, :co, "
                    f"{g}, :f, :conf, :ov, :osm, :marca, :dir, :op, 'quito', CAST(CAST(:t AS text) AS timestamptz))"),
                    [dict(id=i, n=n, c=c, co=co, f=f, conf=conf, ov=ov, osm=osm, op=op, t=t,
                          **({"lon": lon, "lat": lat} if con_postgis else {"wkt": f"POINT({lon} {lat})"}),
                          marca="Marca" if f == "overture" else None, dir="Calle sintética" if f == "overture" else None)
                     for i, n, c, co, lon, lat, f, conf, ov, osm, op, t in SINTETICAS])
            await cx.execute(text("SELECT setval('public.pois_propios_id_seq', (SELECT max(id) FROM public.pois_propios))"))
            # Curación: un «cerrado» sobre un POI operativo y un «confirmado» que resucita uno cerrado.
            await cx.execute(text(
                "INSERT INTO public.entorno_curacion (activo_id, accion, nombre, poi_id, creado_en) VALUES "
                "(gen_random_uuid(), 'cerrado', 'x', (SELECT min(id) FROM public.pois_propios WHERE fuente='osm' AND operativo "
                " AND categoria_overture='parada_bus'), '2026-09-01'), "
                "(gen_random_uuid(), 'confirmado', 'y', (SELECT min(id) FROM public.pois_propios WHERE fuente='overture' "
                " AND NOT operativo), '2026-09-02')"))
        await _aplica(b, ruta=M040)                    # el perímetro REAL de la 040
        async with admin.begin() as cx:
            # El PEOR caso: lo que cree el dueño nace abierto a los tres roles (el mundo de antes de la 034;
            # en producción sigue así para `supabase_admin`). La 043 no puede depender del default.
            await cx.execute(text(f"ALTER DEFAULT PRIVILEGES FOR ROLE {DUENO} IN SCHEMA public "
                                  "GRANT ALL ON TABLES TO anon, authenticated, service_role"))
        yield b
    finally:
        for m in motores:
            await m.dispose()
        async with admin.begin() as cx:
            await cx.execute(text(f"ALTER DEFAULT PRIVILEGES FOR ROLE {DUENO} IN SCHEMA public "
                                  "REVOKE ALL ON TABLES FROM anon, authenticated, service_role"))
            await _limpia(cx)
        await admin.dispose()


async def _foto(motor) -> dict:
    """Lo que la 043 NO debe mover (columnas EXPLÍCITAS) y el catálogo que sí."""
    async with motor.connect() as cx:
        q = lambda s: cx.execute(text(s))  # noqa: E731
        f = {
            "datos": (await q(f"SELECT md5(string_agg(md5(row({COLS14})::text), ',' ORDER BY id)) || ':' || count(*) "
                              f"FROM public.pois_propios")).scalar(),
            "vista": (await q(f"SELECT md5(string_agg(md5(row({COLS17})::text), ',' ORDER BY id)) || ':' || count(*) "
                              f"FROM public.pois_vivos")).scalar(),
            "vista_def": (await q("SELECT pg_get_viewdef('public.pois_vivos'::regclass)")).scalar(),
            "vista_opciones": (await q("SELECT reloptions::text FROM pg_class WHERE oid='public.pois_vivos'::regclass")).scalar(),
            "vista_columnas": [r[0] for r in await q("SELECT attname FROM pg_attribute WHERE attrelid='public.pois_vivos'::regclass "
                                                     "AND attnum > 0 AND NOT attisdropped ORDER BY attnum")],
            "acl": (await q("SELECT string_agg(relname || '=' || coalesce(relacl::text, '-'), ' ' ORDER BY relname) "
                            "FROM pg_class WHERE oid IN ('public.pois_propios'::regclass, 'public.pois_vivos'::regclass, "
                            "'public.entorno_curacion'::regclass, 'public.pois_propios_id_seq'::regclass)")).scalar(),
            "rls": (await q("SELECT relrowsecurity::text || relforcerowsecurity::text FROM pg_class "
                            "WHERE oid='public.pois_propios'::regclass")).scalar(),
            "columnas": [r[0] for r in await q("SELECT attname FROM pg_attribute WHERE attrelid='public.pois_propios'::regclass "
                                               "AND attnum > 0 AND NOT attisdropped ORDER BY attnum")],
            "constraints": sorted(r[0] for r in await q("SELECT conname FROM pg_constraint "
                                                        "WHERE conrelid='public.pois_propios'::regclass")),
            "borradas": (await q("SELECT count(*) FROM pg_attribute WHERE attrelid='public.pois_propios'::regclass "
                                 "AND attnum > 0 AND attisdropped")).scalar(),
            "corridas": (await q("SELECT to_regclass('public.poi_ingestion_run')::text")).scalar(),
        }
        if "source_lineage" in f["columnas"]:
            f["con_procedencia"] = (await q("SELECT count(*) FROM public.pois_propios WHERE "
                                            + " OR ".join(f"{c} IS NOT NULL" for c in NUEVAS))).scalar()
    return f


@pg
async def test_B_la_043_sobre_la_copia_del_esquema_conserva_filas_vista_acl_y_deja_lo_historico_null(banco):
    antes = await _foto(banco["dueno"])
    avisos = await _aplica(banco)
    despues = await _foto(banco["dueno"])
    assert any(a.startswith("043 OK:") for a in avisos), avisos
    for k in ("datos", "vista", "vista_def", "vista_opciones", "vista_columnas", "acl", "rls", "borradas"):
        assert despues[k] == antes[k], k
    assert len(antes["vista_columnas"]) == 17
    assert despues["columnas"] == antes["columnas"] + list(NUEVAS)
    assert despues["con_procedencia"] == 0, "lo histórico queda NULL entero: no hay backfill"
    assert set(despues["constraints"]) - set(antes["constraints"]) == {*CKS_CAPA, "fk_pois_ingestion_run"}
    assert despues["corridas"] == "poi_ingestion_run"
    if FOTO:
        assert antes["datos"].endswith(":9082"), antes["datos"]


VERBOS = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")


@pg
async def test_B_la_tabla_de_corridas_nace_cerrada_aunque_el_default_este_abierto_y_con_rls(banco):
    admin, dueno, motor = banco["admin"], banco["dueno"], banco["motor"]
    # CONTROL POSITIVO: en este banco, una tabla nueva del dueño SIN REVOKE nace abierta.
    async with dueno.begin() as cx:
        await cx.execute(text("CREATE TABLE public.control043 (x int)"))
    acl_control = await _uno(admin, "SELECT relacl::text FROM pg_class WHERE oid='public.control043'::regclass")
    assert all(f"{r}=" in acl_control for r in ("anon", "authenticated", "service_role")), acl_control
    async with dueno.begin() as cx:
        await cx.execute(text("DROP TABLE public.control043"))

    await _aplica(banco)
    v17 = int(await _uno(admin, "SHOW server_version_num")) >= 170000
    verbos = VERBOS + (("MAINTAIN",) if v17 else ())
    assert await _uno(admin, "SELECT relacl::text FROM pg_class WHERE oid='public.poi_ingestion_run'::regclass") \
        == (f"{{{DUENO}=arwdDxtm/{DUENO}}}" if v17 else f"{{{DUENO}=arwdDxt/{DUENO}}}")
    for rol in ("public", *ROLES_PUB):
        for rel in ("public.poi_ingestion_run", "public.pois_propios", "public.pois_vivos"):
            efectivos = [v for v in verbos if await _uno(admin, f"SELECT has_table_privilege('{rol}', '{rel}', '{v}')")]
            assert efectivos == [], (rol, rel, efectivos)
    for rol in ROLES_PUB:
        for sql in ("SELECT count(*) FROM public.poi_ingestion_run",
                    "INSERT INTO public.poi_ingestion_run (source_provider, ciudad, status, reader_contract, code_sha, "
                    "started_at, completed_at, error_class, error_phase) VALUES ('osm','quito','caida','x_v1', "
                    f"'{SHA}', now(), now(), 'X', 'obtencion')",
                    "SELECT source_lineage FROM public.pois_propios"):
            r = await _intenta(motor(rol), (sql, {}))
            assert r.startswith("InsufficientPrivilegeError"), (rol, sql, r)
    # RLS sin FORCE y sin políticas (el dueño, BYPASSRLS como `postgres`, escribe y lee).
    assert await _uno(admin, "SELECT relrowsecurity AND NOT relforcerowsecurity FROM pg_class "
                             "WHERE oid='public.poi_ingestion_run'::regclass") is True
    assert await _uno(admin, "SELECT count(*) FROM pg_policy WHERE polrelid='public.poi_ingestion_run'::regclass") == 0
    caida = _run(provider="osm", status="caida", fetched_at=None, rows_fetched=None, rows_valid=None, rows_written=None,
                 rows_closed=None, error_class="ConnectionError", error_phase="obtencion")
    assert await _intenta(dueno, (_RUN_SQL, caida)) == "ok"
    assert await _uno(dueno, "SELECT count(*) FROM public.poi_ingestion_run") == 1
    assert await _uno(admin, "SELECT count(*) FROM pg_attribute WHERE attrelid IN "
                             "('public.poi_ingestion_run'::regclass, 'public.pois_propios'::regclass) AND attacl IS NOT NULL") == 0


_RUN_COLS = ("id", "source_provider", "ciudad", "status", "reader_contract", "source_release", "source_schema_fingerprint",
             "source_snapshot_at", "source_endpoint", "code_sha", "invocation_ref", "started_at", "fetched_at", "completed_at",
             "rows_fetched", "rows_valid", "rows_written", "rows_closed", "error_class", "error_phase")
_RUN_SQL = (f"INSERT INTO public.poi_ingestion_run ({', '.join(_RUN_COLS)}) VALUES ("
            + ", ".join(f"CAST(CAST(:{c} AS text) AS timestamptz)" if c.endswith("_at") else f":{c}" for c in _RUN_COLS)
            + ")")


def _run(provider="overture", **cambios) -> dict:
    """Una corrida VÁLIDA (OK) de la fuente; los cambios la vuelven el caso de cada prueba."""
    base = {"id": str(uuid.uuid4()), "source_provider": provider, "ciudad": "quito", "status": "ok",
            "reader_contract": "overture_places_categories_v1" if provider == "overture" else "osm_overpass_nwr_body_center_v1",
            "source_release": "2026-08-19.0" if provider == "overture" else None,
            "source_schema_fingerprint": HUELLA if provider == "overture" else None,
            "source_snapshot_at": None if provider == "overture" else "2026-10-02T04:37:05Z",
            "source_endpoint": "s3://x" if provider == "overture" else "https://overpass-api.de/api/interpreter",
            "code_sha": SHA, "invocation_ref": "github-actions:1/1", "started_at": "2026-10-02T04:20:00Z",
            "fetched_at": "2026-10-02T04:20:30Z", "completed_at": "2026-10-02T04:21:00Z", "rows_fetched": 3,
            "rows_valid": 3, "rows_written": 3, "rows_closed": 0, "error_class": None, "error_phase": None}
    base.update(cambios)
    return base


_LINAJE = json.dumps([{"property": "", "dataset": "meta", "license": "CDLA-Permissive-2.0", "record_id": "1264674866906410",
                       "update_time": "2026-08-10T00:00:00.000Z", "version": "2026-08-10"},
                      {"property": "/properties/confidence", "dataset": "Overture", "license": "CDLA-Permissive-2.0",
                       "record_id": None, "update_time": "2026-08-14T19:46:07Z"}])
_PROC = ("UPDATE public.pois_propios SET ingestion_run_id = :rid, source_category = :cat, source_category_namespace = :ns, "
         "source_record_version = :ver, source_updated_at = CAST(CAST(:upd AS text) AS timestamptz), source_lineage = CAST(:lin AS jsonb), "
         "categoria_overture = CASE WHEN :legado THEN categoria_overture ELSE NULL END WHERE id = :id")


def _fila(**k) -> dict:
    base = {"rid": None, "cat": None, "ns": None, "ver": None, "upd": None, "lin": None, "legado": True, "id": None}
    base.update(k)
    return base


async def _ids(banco) -> dict:
    """La fila de Overture con `grocery_store`, la del metro de OSM y una histórica de cada fuente."""
    d = banco["dueno"]
    return {"ov": await _uno(d, "SELECT min(id) FROM public.pois_propios WHERE fuente='overture' AND operativo "
                                "AND categoria_overture='grocery_store'"),
            "metro": await _uno(d, "SELECT min(id) FROM public.pois_propios WHERE fuente='osm' AND categoria_overture='metro'"),
            "osm": await _uno(d, "SELECT min(id) FROM public.pois_propios WHERE fuente='osm' AND operativo")}


@pg
async def test_B_procedencia_valida_con_categories_primary_y_con_taxonomy_y_osm_exacto(banco):
    await _aplica(banco)
    ids, d = await _ids(banco), banco["dueno"]
    run_v1, run_v2 = _run(), _run(reader_contract="overture_places_taxonomy_v2", source_release="2026-09-23.1")
    run_osm = _run("osm")
    # F · categories.primary: la columna legada lleva EXACTAMENTE el mismo valor (v0 lo sigue leyendo bien).
    assert await _intenta(d, (_PROC, _fila(rid=run_v1["id"], cat="grocery_store", ns="overture:categories.primary",
                                           ver="9", upd="2026-08-10T00:00:00Z", lin=_LINAJE, id=ids["ov"])),
                          (_RUN_SQL, run_v1)) == "ok"
    # H · taxonomy.primary con `categoria_overture` NULL: aceptado. La corrida va AL FINAL (FK diferida).
    assert await _intenta(d, (_PROC, _fila(rid=run_v2["id"], cat="grocery_store", ns="overture:taxonomy.primary",
                                           ver="10", lin=_LINAJE, legado=False, id=ids["ov"])),
                          (_RUN_SQL, run_v2)) == "ok"
    assert await _uno(d, "SELECT categoria_overture IS NULL FROM public.pois_propios WHERE id = :i", i=ids["ov"]) is True
    # OSM: el metro EXACTO (`station=subway`), que v0 hoy declara desconocido.
    assert await _intenta(d, (_PROC, _fila(rid=run_osm["id"], cat="subway", ns="osm:station", id=ids["metro"])),
                          (_RUN_SQL, run_osm)) == "ok"
    # Las históricas siguen escribiéndose sin procedencia.
    assert await _intenta(d, ("UPDATE public.pois_propios SET nombre = nombre || ' (ed.)', actualizado_en = now() "
                              "WHERE ingestion_run_id IS NULL", {})) == "ok"


@pg
async def test_B_LA_REGLA_CENTRAL_taxonomy_primary_con_valor_en_categoria_overture_se_rechaza(banco):
    await _aplica(banco)
    ids, d, run = await _ids(banco), banco["dueno"], _run(reader_contract="overture_places_taxonomy_v2")
    r = await _intenta(d, (_RUN_SQL, run), (_PROC, _fila(rid=run["id"], cat="grocery_store",
                                                         ns="overture:taxonomy.primary", legado=True, id=ids["ov"])))
    assert r == "CheckViolationError:ck_pois_columna_legada_coherente", r
    assert await _uno(d, "SELECT categoria_overture FROM public.pois_propios WHERE id = :i", i=ids["ov"]) == "grocery_store"


@pytest.mark.parametrize("caso, fila, restriccion", [
    ("categoría sin campo de origen", dict(cat="grocery_store"), "ck_pois_categoria_fuente_con_espacio"),
    ("campo fuera del vocabulario", dict(cat="x", ns="overture:basic_category", legado=False), "ck_pois_espacio_vocabulario"),
    ("campo de OSM en una fila de Overture", dict(cat="x", ns="osm:shop", legado=False), "ck_pois_espacio_de_su_fuente"),
    ("categories.primary con otro valor que la columna legada", dict(cat="supermarket", ns="overture:categories.primary"),
     "ck_pois_columna_legada_coherente"),
    ("corrida sin campo de origen", dict(), "ck_pois_corrida_exige_espacio"),
    ("linaje que es un objeto", dict(cat="grocery_store", ns="overture:categories.primary", lin='{"a": 1}'),
     "ck_pois_linaje_forma"),
    ("linaje con un elemento que no es objeto", dict(cat="grocery_store", ns="overture:categories.primary", lin='[1, {"a": 1}]'),
     "ck_pois_linaje_forma"),
])
@pg
async def test_B_metadata_incoherente_se_rechaza(banco, caso, fila, restriccion):
    await _aplica(banco)
    ids, run = await _ids(banco), _run()
    r = await _intenta(banco["dueno"], (_RUN_SQL, run), (_PROC, _fila(rid=run["id"], id=ids["ov"], **fila)))
    assert r == f"CheckViolationError:{restriccion}", (caso, r)


@pytest.mark.parametrize("fila", [dict(upd="2026-08-10T00:00:00Z"), dict(lin=_LINAJE), dict(ver="9"),
                                  dict(cat="grocery_store", ns="overture:categories.primary")])
@pg
async def test_B_procedencia_parcial_sin_corrida_se_rechaza(banco, fila):
    await _aplica(banco)
    ids = await _ids(banco)
    r = await _intenta(banco["dueno"], (_PROC, _fila(id=ids["ov"], **fila)))
    assert r == "CheckViolationError:ck_pois_procedencia_exige_corrida", r


@pg
async def test_B_el_linaje_es_solo_de_overture(banco):
    await _aplica(banco)
    ids, run = await _ids(banco), _run("osm")
    r = await _intenta(banco["dueno"], (_RUN_SQL, run),
                       (_PROC, _fila(rid=run["id"], cat="subway", ns="osm:station", lin='[{"dataset": "x"}]', id=ids["metro"])))
    assert r == "CheckViolationError:ck_pois_linaje_forma", r


@pg
async def test_B_la_fk_compuesta_diferida_exige_una_corrida_real_de_su_fuente_y_su_ciudad(banco):
    await _aplica(banco)
    ids, d = await _ids(banco), banco["dueno"]
    v1 = dict(cat="grocery_store", ns="overture:categories.primary", id=ids["ov"])
    # Sin corrida: se rechaza en el COMMIT.
    r = await _intenta(d, (_PROC, _fila(rid=str(uuid.uuid4()), **v1)))
    assert r == "ForeignKeyViolationError:fk_pois_ingestion_run", r
    # Una corrida de OTRA fuente o de OTRA ciudad no vale.
    for otra in (_run("osm"), _run(ciudad="mazatlan")):
        r = await _intenta(d, (_RUN_SQL, otra), (_PROC, _fila(rid=otra["id"], **v1)))
        assert r == "ForeignKeyViolationError:fk_pois_ingestion_run", (otra["source_provider"], otra["ciudad"], r)
    # La buena, insertada AL FINAL de la transacción.
    buena = _run()
    assert await _intenta(d, (_PROC, _fila(rid=buena["id"], **v1)), (_RUN_SQL, buena)) == "ok"
    # Una corrida con filas no se borra (RESTRICT, inmediato).
    r = await _intenta(d, ("DELETE FROM public.poi_ingestion_run WHERE id = :i", {"i": buena["id"]}))
    assert r == "ForeignKeyViolationError:fk_pois_ingestion_run", r


@pytest.mark.parametrize("cambios, restriccion", [
    (dict(fetched_at=None, rows_fetched=None, rows_valid=None, rows_written=None, rows_closed=None), "ck_pir_ok_completa"),
    (dict(error_class="X", error_phase="escritura"), "ck_pir_ok_completa"),
    (dict(provider="osm", source_release="2026-09-23.1"), "ck_pir_release"),
    (dict(source_schema_fingerprint=None), "ck_pir_release"),
    (dict(source_snapshot_at="2026-10-02T04:37:05Z"), "ck_pir_release"),
    (dict(status="caida", rows_written=None, rows_closed=None, error_phase="obtencion"), "ck_pir_fallo"),
    (dict(status="rota", error_class="X", error_phase="escritura"), "ck_pir_fallo"),
    (dict(status="caida", rows_written=None, rows_closed=None, error_class="X", error_phase="escritura"), "ck_pir_fase"),
    (dict(status="rota", rows_written=None, rows_closed=None, error_class="X", error_phase="otra"), "ck_pir_fase"),
    (dict(reader_contract="places/v2"), "ck_pir_lector"),
    (dict(code_sha="abc"), "ck_pir_sha"),
    (dict(source_schema_fingerprint="xyz"), "ck_pir_huella"),
    (dict(completed_at="2026-10-02T04:00:00Z"), "ck_pir_tiempos"),
    (dict(provider="google"), "ck_pir_proveedor"),
    (dict(ciudad="Quito "), "ck_pir_ciudad"),
    (dict(status="parcial"), "ck_pir_estado"),
    (dict(rows_fetched=-1), "ck_pir_fetched"),
])
@pg
async def test_B_el_manifiesto_rechaza_corridas_incoherentes(banco, cambios, restriccion):
    await _aplica(banco)
    provider = cambios.pop("provider", "overture")
    r = await _intenta(banco["dueno"], (_RUN_SQL, _run(provider, **cambios)))
    assert r == f"CheckViolationError:{restriccion}", (cambios, r)


@pg
async def test_B_el_manifiesto_acepta_las_corridas_reales(banco):
    await _aplica(banco)
    for run in (_run(), _run("osm"),
                _run(status="rota", fetched_at=None, rows_fetched=None, rows_valid=None, rows_written=None, rows_closed=None,
                     source_schema_fingerprint=None, error_class="BinderException", error_phase="obtencion",
                     source_release="2026-09-23.1"),
                _run("osm", status="caida", fetched_at=None, rows_fetched=None, rows_valid=None, rows_written=None,
                     rows_closed=None, error_class="ConnectionError", error_phase="obtencion"),
                _run("osm", status="rota", rows_written=None, rows_closed=None, error_class="OperationalError",
                     error_phase="escritura")):
        assert await _intenta(banco["dueno"], (_RUN_SQL, run)) == "ok", run


@pg
async def test_B_sin_procedencia_se_sigue_insertando_actualizando_y_cerrando_como_hoy(banco, foso):
    """El escritor ACTUAL no conoce las columnas: sus sentencias (las reales del cierre) siguen pasando."""
    await _aplica(banco)
    d = banco["dueno"]
    g = "ST_SetSRID(ST_MakePoint(-78.48, -0.18), 4326)" if banco["postgis"] else "'POINT(-78.48 -0.18)'"
    vivas = await _lista(d, "SELECT osm_id FROM public.pois_propios WHERE fuente='osm' AND operativo ORDER BY osm_id")
    assert await _intenta(d,
                          (f"INSERT INTO public.pois_propios (nombre, categoria, categoria_overture, geom, fuente, confianza, "
                           f"overture_id, osm_id, marca, direccion, operativo, ciudad) VALUES ('Nueva', 'farmacia', 'pharmacy', "
                           f"{g}, 'osm', NULL, NULL, 'node/77', NULL, NULL, true, 'quito')", {}),
                          ("UPDATE public.pois_propios SET nombre = nombre, categoria_overture = categoria_overture, "
                           "operativo = true, actualizado_en = now() WHERE fuente = 'overture'", {}),
                          (str(foso.CERRAR_OSM), {"ciudad": "quito", "ids": vivas[1:] + ["node/77"]})) == "ok"
    assert await _uno(d, "SELECT count(*) FROM public.pois_propios WHERE " + " OR ".join(f"{c} IS NOT NULL" for c in NUEVAS)) == 0
    assert await _uno(d, "SELECT count(*) FROM public.poi_ingestion_run") == 0


def _rollback_sql() -> str:
    bloque = M043.read_text(encoding="utf-8").split("-- ── ROLLBACK", 1)[1]
    return "\n".join(l[5:] for l in bloque.splitlines() if l.startswith("--   "))


@pg
async def test_B_el_rollback_documentado_deja_el_esquema_logico_y_los_datos_como_antes(banco):
    antes = await _foto(banco["dueno"])
    await _aplica(banco)
    await _aplica(banco, sql=_rollback_sql())
    tras = await _foto(banco["dueno"])
    for k in ("datos", "vista", "vista_def", "vista_opciones", "vista_columnas", "acl", "rls", "columnas", "constraints"):
        assert tras[k] == antes[k], k
    assert tras["corridas"] is None
    assert tras["borradas"] == antes["borradas"] + 6, "lógico exacto, no físico: 6 atributos attisdropped"
    # Y se puede volver a aplicar.
    assert any(a.startswith("043 OK:") for a in await _aplica(banco))


@pg
async def test_B_reaplicar_no_hace_nada_y_los_estados_ajenos_fallan_cerrados(banco):
    d, admin = banco["dueno"], banco["admin"]
    await _aplica(banco)
    aplicada = await _foto(d)
    avisos = await _aplica(banco)
    assert any(a.startswith("043: ya aplicada") for a in avisos), avisos
    assert await _foto(d) == aplicada
    # Una pieza de menos tras aplicar: aborta, no la "arregla".
    async with d.begin() as cx:
        await cx.execute(text("ALTER TABLE public.pois_propios DROP CONSTRAINT ck_pois_linaje_forma"))
    assert "estado intermedio o ajeno" in await _intenta_aplicar(banco)
    await _aplica(banco, sql=_rollback_sql())
    limpia = await _foto(d)

    def sin_borradas(f):
        return {k: v for k, v in f.items() if k != "borradas"}

    async def ajeno(preparar, deshacer, esperado):
        async with d.begin() as cx:
            for s in preparar:
                await cx.execute(text(s))
        r = await _intenta_aplicar(banco)
        assert esperado in r, (preparar, r)
        async with d.begin() as cx:
            for s in deshacer:
                await cx.execute(text(s))
        assert sin_borradas(await _foto(d)) == sin_borradas(limpia), preparar

    await ajeno(["CREATE TABLE public.poi_ingestion_run (id uuid PRIMARY KEY)"],
                ["DROP TABLE public.poi_ingestion_run"], "estado intermedio o ajeno")
    await ajeno(["ALTER TABLE public.pois_propios ADD COLUMN source_lineage jsonb"],
                ["ALTER TABLE public.pois_propios DROP COLUMN source_lineage"], "estado intermedio o ajeno")
    await ajeno(["ALTER TABLE public.pois_propios ADD CONSTRAINT ck_pois_linaje_forma CHECK (true)"],
                ["ALTER TABLE public.pois_propios DROP CONSTRAINT ck_pois_linaje_forma"], "estado intermedio o ajeno")
    await ajeno(["ALTER VIEW public.pois_vivos RESET (security_invoker)"],
                ["ALTER VIEW public.pois_vivos SET (security_invoker = true)"], "sin security_invoker")
    await ajeno(["GRANT SELECT ON public.pois_propios TO anon"], ["REVOKE SELECT ON public.pois_propios FROM anon"],
                "destinatarios externos")
    await ajeno(["ALTER TABLE public.pois_propios DISABLE ROW LEVEL SECURITY"],
                ["ALTER TABLE public.pois_propios ENABLE ROW LEVEL SECURITY"], "sin RLS")
    # Quien no es el dueño (aunque sea superusuario) no la aplica.
    assert "no es quien aplica" in await _intenta_aplicar_como(banco, admin)
    assert (await _foto(d))["corridas"] is None


async def _intenta_aplicar_como(banco, motor) -> str:
    try:
        await _aplica(banco, motor=motor)
        return "ok"
    except Exception as e:  # noqa: BLE001
        return str(getattr(e, "orig", e))[:300]


def _plano(o):
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return {f.name: _plano(getattr(o, f.name)) for f in dataclasses.fields(o)}
    if hasattr(o, "model_dump"):
        return o.model_dump(mode="json")
    if isinstance(o, dict):
        return {str(k): _plano(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plano(v) for v in o]
    return o if isinstance(o, (str, int, float, bool, type(None))) else str(o)


@pg
async def test_B_lectores_aura_chat_mapa_y_place_evidence_v0_devuelven_exactamente_lo_mismo(banco, monkeypatch):
    if not banco["postgis"]:
        pytest.skip("los lectores usan PostGIS (ST_DWithin…): el Postgres del CI no lo trae")
    import app.place.providers.propia as propia
    import app.rutas as rutas
    from app.routers import assets

    eng = banco["motor"](DUENO)
    monkeypatch.setattr(propia, "engine", eng)
    monkeypatch.setattr(rutas, "engine", eng)

    class _Reloj(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 2, 5, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(rutas, "datetime", _Reloj)
    puntos = ([(-0.1807, -78.4678), (-0.2950, -78.5400), (-0.1100, -78.4900)] if FOTO
              else [(-0.1805, -78.4805), (-0.1790, -78.4790)])

    async def lecturas() -> dict:
        out = {}
        for i, (lat, lon) in enumerate(puntos):
            area = json.dumps({"type": "Polygon", "coordinates": [[[lon - .01, lat - .01], [lon + .01, lat - .01],
                                                                  [lon + .01, lat + .01], [lon - .01, lat + .01],
                                                                  [lon - .01, lat - .01]]]})
            out[i] = json.dumps(_plano({
                "servicios_propios": await propia._servicios_propios(lat, lon),
                "ruta_super": await propia._nearest_propio(lat, lon, "supermercado"),
                "ruta_metro": await propia._nearest_propio(lat, lon, "transporte", ["metro", "estacion_tren", "estacion"]),
                "aura_pines": await assets._pois_geo(lat, lon),
                "panorama": await rutas._panorama_transporte(lat, lon),
                "isocrona": await rutas._contenido_isocrona(json.loads(area)),
                "place_evidence_v0": await rutas.evidencia_de_capa_propia(lat, lon),
            }), sort_keys=True, ensure_ascii=False)
        return out

    antes = await lecturas()
    await _aplica(banco)
    despues = await lecturas()
    assert despues == antes
    todo = "".join(despues.values())
    # No vacua: la capa respondió, con procedencia v0 y documentos persistibles.
    assert '"poi_id"' in todo and '"dataset": "overture"' in todo and '"available"' in todo, todo[:400]
    # Los nombres que SOLO existen por la 043 no llegan a ningún lector (`source_category` y
    # `source_category_namespace` sí aparecen: son campos de la clasificación de v0, anteriores).
    for col in ("ingestion_run_id", "source_record_version", "source_updated_at", "source_lineage", "poi_ingestion_run"):
        assert col not in todo, col
    assert "taxonomy" not in todo


PRE_R4 = "f8614e1d761409541483aec881f7b39c62db8c02"   # main con la 043 aplicada y el escritor que aún no la conoce


@pg
async def test_B_el_escritor_pre_r4_corre_sobre_la_043_overture_sigue_rota_y_osm_se_refresca(
        banco, foso, duckdb_spatial, monkeypatch, tmp_path):
    """El escritor PRE-R4 EXACTO (`f8614e1d`): el que corre hoy en producción sobre la 043 y el que volvería con un
    rollback de R4. Desde R4 el escritor de la rama ya no es este (su contrato lo prueba
    `tests/test_poi_source_provenance_writer.py`), así que se toma de la historia de git."""
    if not banco["postgis"]:
        pytest.skip("el upsert real del escritor usa PostGIS: el Postgres del CI no lo trae")
    pytest.importorskip("psycopg")
    import subprocess
    p = subprocess.run(["git", "show", f"{PRE_R4}:scripts/foso_pois_spike.py"], cwd=RAIZ, capture_output=True)
    if p.returncode != 0:
        pytest.skip("sin historia git (clon superficial): no hay escritor PRE-R4 que cargar")
    ruta = tmp_path / "foso_pre_r4.py"
    ruta.write_bytes(p.stdout)
    pre = _carga(ruta, "foso_pre_r4")
    for nombre in ("overture_release", "avisar_ops"):
        monkeypatch.setattr(pre, nombre, getattr(foso, nombre))
    pre.avisos = foso.avisos
    await _aplica(banco)
    d = banco["dueno"]
    huella_overture = ("SELECT md5(string_agg(md5(row(" + COLS14 + ")::text), ',' ORDER BY id)) FROM public.pois_propios "
                       "WHERE fuente = 'overture'")
    ov_antes = await _uno(d, huella_overture)
    operativas_antes = set(await _lista(d, "SELECT osm_id FROM public.pois_propios WHERE fuente='osm' AND operativo"))
    url = (URL.replace("postgresql+asyncpg://", "postgresql+psycopg://") + ("&" if "?" in URL else "?")
           + f"options=-c%20role%3D{DUENO}%20-c%20search_path%3Dpublic")
    monkeypatch.setattr(pre, "SYNC_URL", url)
    v2 = _parquet(duckdb_spatial, tmp_path / "v2.parquet", con_categories=False)   # Overture 2026-09-23.x (D-4)
    monkeypatch.setattr(pre, "overture_glob", lambda rel: v2)
    # Las filas con la forma del escritor PRE-R4 (sin las claves de procedencia que entrega el lector R4).
    lote = [pre._normalizar(_osm(foso, oid)) for oid in sorted(operativas_antes)[1:]] + [
        pre._normalizar(_osm(foso, "node/9001"))]
    lote[0]["nombre"] = "OSM refrescado sobre la 043"
    monkeypatch.setattr(pre, "pull_osm_transporte", lambda: lote)

    assert _corre(pre) == 1                                      # alguna fuente ROTA: Overture (D-4), igual que hoy
    f = _fuentes(_estado(tmp_path))
    assert (f["overture"]["estado"], f["overture"]["fase"]) == ("rota", "obtencion")
    assert "categories" in f["overture"]["error"]
    assert (f["osm"]["estado"], f["osm"]["escritas"]) == ("ok", len(lote))
    assert await _uno(d, huella_overture) == ov_antes, "Overture: 0 escrituras"
    assert await _uno(d, "SELECT nombre FROM public.pois_propios WHERE osm_id = :o", o=lote[0]["osm_id"]) == lote[0]["nombre"]
    assert await _uno(d, "SELECT operativo FROM public.pois_propios WHERE osm_id = 'node/9001'") is True
    cerradas = await _uno(d, "SELECT count(*) FROM public.pois_propios WHERE fuente='osm' AND NOT operativo "
                             "AND osm_id = ANY(:i)", i=sorted(operativas_antes))
    assert cerradas == f["osm"]["cerradas"]
    # Sin conocer la 043: ni una columna de procedencia escrita, ni una corrida registrada.
    assert await _uno(d, "SELECT count(*) FROM public.pois_propios WHERE " + " OR ".join(f"{c} IS NOT NULL" for c in NUEVAS)) == 0
    assert await _uno(d, "SELECT count(*) FROM public.poi_ingestion_run") == 0
