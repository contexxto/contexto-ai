"""PLACE-EVIDENCE-TARGET-AUTHORITY · la 042 cierra la autoridad directa sobre el destino de la
evidencia (`public.activos_inmutables`), probada sin producción.

  A · sin base:
      · la migración hace SOLO lo que dice (REVOKE a PUBLIC y a los tres roles sobre ESA tabla,
        compuertas fail-closed, verificación del privilegio efectivo) y nada más: ni GRANT, ni
        políticas, ni RLS/FORCE, ni DML, ni otras tablas, ni Storage/Auth, ni privilegios por
        defecto, ni el EXECUTE de la función de la 041;
      · el ROLLBACK documentado es el inverso exacto, está comentado y se declara como reversión
        de emergencia a un estado INSEGURO;
      · GUARDA ESTRUCTURAL (§14): falla si el repo reabre el destino —una SECURITY DEFINER que lo
        nombre o con SQL dinámico, un GRANT o una política para un rol público, un consumidor
        PostgREST o un cliente Supabase en el backend—, con su propio control de que no es vacua.
  B · PostgreSQL real (`TEST_DATABASE_URL`, también en el CI; en local además PG17 y PostGIS):
      `activos_inmutables` con las columnas, el RLS, la política y los grants MEDIDOS en
      producción, la 041 real aplicada, un dueño NOSUPERUSER + BYPASSRLS como `postgres` y
      `service_role` con BYPASSRLS como en producción. Con ROLES REALES (`SET ROLE`), sin mocks:
        · CONTROL POSITIVO antes de la 042: `service_role` lee, inserta, fabrica evidencia, borra,
          trunca, engancha un trigger; `anon`/`authenticated` chocan con el RLS en DML pero
          TRUNCATE, TRIGGER, REFERENCES y LOCK lo sortean;
        · después: todo `permission denied`; `contexto_audit_ro` sigue leyendo por su política y no
          muta; el dueño conserva TODA su autoridad y el trigger de la 041 sigue anulando;
        · la función de la 041 no es invocable directamente, y sin TRIGGER no se engancha;
        · filas intactas (huellas con TODAS las columnas explícitas), 041 y 040 intactas;
        · idempotencia; estados ajenos → FAIL CLOSED sin tocar nada; estados permitidos;
        · el ROLLBACK devuelve los privilegios EFECTIVOS medidos;
        · el escritor nuevo (`_recompute_walk_score`, con la 041) escribe como dueño tras la 042;
        · MUTACIONES: quitar una guarda material de la 042 pone en rojo la prueba que la vigila.
El backend VIEJO de producción (1162936) contra 041 + 042 se prueba fuera del repo (su código no
convive con este en el mismo proceso): ver el informe.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.test_migracion_041 import (LEGADO, M040, M041, _ddl_activos, _docs_reales, _limpia,
                                      _rollback, _sin_comentarios, _uno)

RAIZ = Path(__file__).resolve().parents[1]
M042 = RAIZ / "migrations" / "042_place_evidence_target_authority.sql"
ROLES = ("anon", "authenticated", "service_role")
DUENO = "p042_owner"
VERBOS = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
COLUMNAS = ("id, geom::text, direccion_estandarizada, piso_altura, walk_score, score_ruido_predictivo, "
            "volumen_trafico_historico, densidad_poblacional_pico, porcentaje_cobertura_vegetal, created_at, "
            "tipo_activo, image_sha256, imagen_url, owner_user_id, owner_agency_id, conectividad, "
            "servicios_cercanos, caracteristicas, walk_score_fuente, source_id, ingestion_event_id, "
            "inventory_class, received_at, evidence_exclusion_reason, servicios_evidencia, conectividad_evidencia")


# ─────────────────────────────── A · sin base ────────────────────────────────
def test_la_042_hace_solo_lo_que_dice():
    cuerpo = _sin_comentarios(M042.read_text(encoding="utf-8"))
    assert cuerpo.strip().startswith("BEGIN;") and cuerpo.rstrip().endswith("COMMIT;")
    assert "SET LOCAL lock_timeout" in cuerpo
    assert "REVOKE ALL PRIVILEGES ON TABLE public.activos_inmutables FROM PUBLIC;" in cuerpo
    assert "REVOKE ALL PRIVILEGES ON TABLE public.activos_inmutables FROM %I" in cuerpo
    assert "ARRAY['anon', 'authenticated', 'service_role']" in cuerpo
    assert "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol)" in cuerpo, "guarda de rol inexistente"
    # Nada de lo que la unidad no autoriza.
    assert not re.search(r"(?i)\bGRANT\b", cuerpo), "ningún GRANT (el del ROLLBACK va comentado)"
    assert not re.search(r"(?i)\bCREATE\s+(POLICY|VIEW|FUNCTION|TRIGGER|TABLE|ROLE)\b", cuerpo)
    assert not re.search(r"(?i)\bALTER\s+(TABLE|ROLE|FUNCTION|DEFAULT\s+PRIVILEGES|POLICY)\b", cuerpo)
    assert not re.search(r"(?i)\b(ENABLE|DISABLE|FORCE)\s+ROW\s+LEVEL", cuerpo)
    assert not re.search(r"(?i)^\s*(INSERT|UPDATE|DELETE|TRUNCATE)\b", cuerpo, re.M)
    assert not re.search(r"(?i)\bOWNER\s+TO\b|\bSEQUENCE\b|\bON\s+FUNCTION\b|\bstorage\.|\bauth\.", cuerpo)
    # Una sola tabla y, en las compuertas, la función de la 041 (sin tocar su EXECUTE).
    assert set(re.findall(r"public\.([a-z_0-9]+)", cuerpo)) == \
        {"activos_inmutables", "activos_invalida_evidencia_desfasada"}
    assert not re.search(r"(?i)REVOKE[^;]*activos_invalida_evidencia_desfasada", cuerpo)
    for compuerta in ("no existe public.activos_inmutables", "el dueño de activos_inmutables no es quien aplica",
                      "RLS está desactivado", "tiene FORCE activado", "las políticas de activos_inmutables no son",
                      "la 041 no está aplicada", "faltan los CHECK validados de la 041",
                      "dejó de ser SECURITY INVOKER", "no son el de la 041 exacto",
                      "concedidos por otro rol o con opción de concesión", "destinatarios no medidos",
                      "no tiene exactamente SELECT", "estado intermedio o ajeno", "hay ACL de columna",
                      "la autoridad sigue abierta", "hay vistas que dependen", "hay reglas",
                      "herencia o particiones", "publicación de replicación", "funciones que nombran",
                      "SECURITY DEFINER con SQL dinámico",
                      "042 FALLA: quedan privilegios de tabla", "042 FALLA: quedan privilegios de columna",
                      "conserva % efectivo", "contexto_audit_ro perdió SELECT", "el dueño % perdió",
                      "cambió el RLS o el FORCE", "cambiaron las políticas", "la 041 (trigger o CHECK)"):
        assert compuerta in cuerpo, compuerta


def test_el_rollback_documentado_es_el_inverso_exacto_y_se_declara_inseguro():
    sql = M042.read_text(encoding="utf-8")
    rb = _rollback(sql)
    assert rb == ("BEGIN;\nGRANT ALL PRIVILEGES ON TABLE public.activos_inmutables TO anon, authenticated, "
                  "service_role;\nCOMMIT;\n"), rb
    cola = sql.split("-- ── ROLLBACK", 1)[1]
    assert all(l.startswith("--") or not l.strip() for l in cola.splitlines()[1:]), "el ROLLBACK va comentado"
    assert "EMERGENCY REVERSAL TO PRIOR KNOWN-INSECURE AUTHORITY STATE" in cola
    assert "PUBLIC" in cola and "no recibe nada" in cola


# ── §14 · GUARDA ESTRUCTURAL: nadie reabre el destino ─────────────────────────────
ROL_PUBLICO = r"\b(PUBLIC|anon|authenticated|service_role)\b"


def _puentes_sql(sql: str) -> list[str]:
    """Lo que en SQL reabriría `activos_inmutables` a un rol público, directa o indirectamente."""
    cuerpo = _sin_comentarios(sql)
    hallazgos = []
    for m in re.finditer(r"(?i)\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\b", cuerpo):
        # La sentencia entera: hasta el `;` que sigue al cierre de su cuerpo `$tag$ … $tag$`
        # (los atributos pueden ir antes o después del cuerpo).
        resto = cuerpo[m.start():]
        d = re.search(r"\$[A-Za-z_]*\$", resto)
        cierre = resto.find(d.group(0), d.end()) if d else -1
        fin = resto.find(";", cierre + len(d.group(0))) if cierre >= 0 else resto.find(";")
        trozo = resto[: fin + 1 if fin >= 0 else len(resto)]
        if re.search(r"(?i)SECURITY\s+DEFINER", trozo) and (
                "activos_inmutables" in trozo or re.search(r"(?i)\bEXECUTE\s+(format|'|\$|[a-z_]+\s*(;|\|\|))", trozo)
                or re.search(r"(?i)query_to_xml|dblink", trozo)):
            hallazgos.append("SECURITY DEFINER que nombra el destino o ejecuta SQL dinámico: "
                             + trozo.strip().splitlines()[0][:90])
    for m in re.finditer(r"(?is)\bGRANT\b[^;]*?\bON\b[^;]*?\bactivos_inmutables\b[^;]*?\bTO\b[^;]*?;", cuerpo):
        if re.search(ROL_PUBLICO, m.group(0).split(" TO ", 1)[-1], re.I):
            hallazgos.append("GRANT del destino a un rol público: " + " ".join(m.group(0).split())[:90])
    for m in re.finditer(r"(?is)\bGRANT\b[^;]*?\bON\s+ALL\s+TABLES\s+IN\s+SCHEMA\s+public\b[^;]*?;", cuerpo):
        if re.search(ROL_PUBLICO, m.group(0).split(" TO ", 1)[-1], re.I):
            hallazgos.append("GRANT de TODAS las tablas de public a un rol público: " + " ".join(m.group(0).split())[:90])
    for m in re.finditer(r"(?is)\bCREATE\s+POLICY\b[^;]*?\bON\b\s+(public\.)?activos_inmutables\b[^;]*?;", cuerpo):
        if re.search(r"(?i)\bTO\b[^;]*" + ROL_PUBLICO, m.group(0)):
            hallazgos.append("política del destino para un rol público: " + " ".join(m.group(0).split())[:90])
    return hallazgos


def _puentes_codigo(ruta: str, codigo: str) -> list[str]:
    """Un consumidor PostgREST del destino, o un cliente Supabase dentro del backend."""
    hallazgos = []
    if re.search(r"rest/v1/activos_inmutables|\.from\(\s*['\"`]activos_inmutables['\"`]", codigo):
        hallazgos.append(f"{ruta}: consumidor PostgREST de activos_inmutables")
    if ruta.startswith("app/") and re.search(r"(?m)^\s*(from\s+supabase\b|import\s+supabase\b)", codigo):
        hallazgos.append(f"{ruta}: cliente Supabase en el backend")
    return hallazgos


def test_la_guarda_estructural_no_es_vacua():
    malo_secdef = ("CREATE OR REPLACE FUNCTION public.rpc_mala(q text) RETURNS void LANGUAGE plpgsql\n"
                   "SECURITY DEFINER AS $$ BEGIN EXECUTE q; END $$;\n")
    malo_nombre = ("CREATE FUNCTION public.rpc_nombra() RETURNS void LANGUAGE sql SECURITY DEFINER AS\n"
                   "$$ UPDATE public.activos_inmutables SET servicios_evidencia = NULL $$;\n")
    assert _puentes_sql(malo_secdef) and _puentes_sql(malo_nombre)
    assert _puentes_sql("GRANT UPDATE ON TABLE public.activos_inmutables TO service_role;")
    assert _puentes_sql("GRANT SELECT ON ALL TABLES IN SCHEMA public TO anon;")
    assert _puentes_sql("CREATE POLICY p ON public.activos_inmutables FOR ALL TO authenticated USING (true);")
    assert not _puentes_sql("GRANT SELECT ON TABLE public.activos_inmutables TO contexto_audit_ro;")
    assert not _puentes_sql("-- GRANT ALL PRIVILEGES ON TABLE public.activos_inmutables TO anon;")
    assert _puentes_codigo("frontend/src/x.js", "supabase.from('activos_inmutables').update({})")
    assert _puentes_codigo("app/x.py", "from supabase import create_client")
    assert not _puentes_codigo("frontend/src/x.js", "supabase.storage.from('evidencias').upload(p, f)")


def test_nadie_en_el_repo_reabre_el_destino():
    ajenas = {"node_modules", ".venv", "venv", "site-packages", ".git"}
    hallazgos = []
    for f in sorted(RAIZ.rglob("*.sql")):
        if ajenas & set(f.parts):
            continue
        hallazgos += [f"{f.relative_to(RAIZ).as_posix()}: {h}"
                      for h in _puentes_sql(f.read_text(encoding="utf-8", errors="replace"))]
    for carpeta, patron in (("app", "*.py"), ("scripts", "*.py"), ("frontend/src", "*.js"), ("frontend/src", "*.jsx")):
        for f in sorted((RAIZ / carpeta).rglob(patron)):
            if ajenas & set(f.parts):
                continue
            rel = f.relative_to(RAIZ).as_posix()
            hallazgos += _puentes_codigo(rel, f.read_text(encoding="utf-8", errors="replace"))
    assert not hallazgos, hallazgos


# ──────────────────────────── B · Postgres real ────────────────────────────
URL = os.getenv("TEST_DATABASE_URL", "")
pg = pytest.mark.skipif(not URL, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas")
EXTRAS = ("public.f042_nombra()", "public.f042_rpc(text)", "public.f042_trg()")


async def _limpia042(cx):
    await cx.execute(text("DROP SCHEMA IF EXISTS s042_andamio CASCADE"))
    await cx.execute(text("DROP PUBLICATION IF EXISTS p042_pub"))
    await cx.execute(text("DROP VIEW IF EXISTS public.v042_activos"))
    await cx.execute(text("DROP TABLE IF EXISTS public.activos_hijo042"))
    for f in EXTRAS:
        await cx.execute(text(f"DROP FUNCTION IF EXISTS {f} CASCADE"))
    await _limpia(cx)
    await cx.execute(text("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='p042_intruso') "
                          "THEN DROP ROLE p042_intruso; END IF; END $$;"))


@pytest.fixture
async def banco():
    """`activos_inmutables` como en producción, con la 041 real aplicada por un dueño NOSUPERUSER +
    BYPASSRLS, `service_role` con BYPASSRLS (como en producción; se restaura al final)."""
    from app.config import settings
    from app.esquema_requerido import aplicar_migracion
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    if settings.database_url and URL.split("@")[-1] in settings.database_url:
        pytest.fail("TEST_DATABASE_URL apunta a la base del producto. Abortado.")
    admin = create_async_engine(URL, poolclass=NullPool)
    async with admin.begin() as cx:
        for rol in (*ROLES, "contexto_audit_ro"):
            await cx.execute(text(
                f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{rol}') "
                f"THEN CREATE ROLE {rol} NOLOGIN; END IF; END $$;"))
        await cx.execute(text(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{DUENO}') "
            f"THEN CREATE ROLE {DUENO} NOLOGIN NOSUPERUSER BYPASSRLS; END IF; END $$;"))
        await cx.execute(text(f"GRANT USAGE, CREATE ON SCHEMA public TO {DUENO}"))
        await cx.execute(text("GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role, contexto_audit_ro"))
        sr_bypass = (await cx.execute(text("SELECT rolbypassrls FROM pg_roles WHERE rolname='service_role'"))).scalar()
        await cx.execute(text("ALTER ROLE service_role BYPASSRLS"))
        dueno_actual = (await cx.execute(text(
            "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = to_regclass('public.activos_inmutables')"
        ))).scalar()
        if dueno_actual not in (None, DUENO, "p041_owner"):
            pytest.fail(f"public.activos_inmutables ya existe y es de {dueno_actual}: no se toca")
        await _limpia042(cx)
        # ANDAMIO del banco (no existe en producción): un esquema donde los roles pueden crear una
        # tabla, para medir REFERENCES con una FK real (una tabla temporal no puede referenciar una
        # permanente). En producción ningún rol público tiene CREATE en `public` (medido).
        await cx.execute(text("CREATE SCHEMA s042_andamio"))
        await cx.execute(text(f"GRANT USAGE, CREATE ON SCHEMA s042_andamio TO anon, authenticated, service_role, "
                              f"contexto_audit_ro, {DUENO}"))
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
    punto = "ST_SetSRID(ST_MakePoint(-78.4858, -0.1755), 4326)" if con_postgis else "'POINT(-78.4858 -0.1755)'"
    async with dueno.begin() as cx:
        await cx.execute(text(_ddl_activos(con_postgis)))
        await cx.execute(text("ALTER TABLE public.activos_inmutables ENABLE ROW LEVEL SECURITY"))
        await cx.execute(text("CREATE POLICY audit_ro_select_activos ON public.activos_inmutables "
                              "FOR SELECT TO contexto_audit_ro USING (true)"))
        await cx.execute(text("GRANT ALL PRIVILEGES ON TABLE public.activos_inmutables "
                              "TO anon, authenticated, service_role"))
        await cx.execute(text("GRANT SELECT ON TABLE public.activos_inmutables TO contexto_audit_ro"))
        for i, (serv, conect) in enumerate(LEGADO):
            await cx.execute(text(
                f"INSERT INTO public.activos_inmutables (id, geom, direccion_estandarizada, walk_score, "
                f"servicios_cercanos, conectividad, inventory_class) VALUES "
                f"(:id, {punto}, :dir, 80, :s, :c, 'unknown')"),
                {"id": str(uuid.UUID(int=i + 1)), "dir": f"Dirección sintética {i}", "s": serv, "c": conect})
    async with async_sessionmaker(dueno)() as s:
        await aplicar_migracion(str(M041), db=s)
    try:
        yield {"admin": admin, "motor": motor, "dueno": dueno, "postgis": con_postgis, "punto": punto,
               "Sesion": async_sessionmaker(dueno, expire_on_commit=False)}
    finally:
        for m in motores:
            await m.dispose()
        async with admin.begin() as cx:
            await _limpia042(cx)
            if not sr_bypass:
                await cx.execute(text("ALTER ROLE service_role NOBYPASSRLS"))
        await admin.dispose()


async def _aplica(motor, sql_texto=None, ruta=M042):
    """Por el aplicador REAL del producto (`app.esquema_requerido.aplicar_migracion`)."""
    import tempfile

    from app.esquema_requerido import aplicar_migracion
    from sqlalchemy.ext.asyncio import async_sessionmaker
    if sql_texto is not None:
        ruta = Path(tempfile.gettempdir()) / f"m042_{uuid.uuid4().hex}.sql"
        ruta.write_text(sql_texto, encoding="utf-8")
    try:
        async with async_sessionmaker(motor)() as s:
            await aplicar_migracion(str(ruta), db=s)
    finally:
        if sql_texto is not None:
            ruta.unlink(missing_ok=True)


async def _intenta_aplicar(motor, sql_texto=None) -> str:
    try:
        await _aplica(motor, sql_texto)
        return "ok"
    except Exception as e:  # noqa: BLE001
        return str(getattr(e, "orig", e))[:300]


async def _prueba(motor, sql, simple=False, **p):
    """Ejecuta y SIEMPRE revierte: mide qué puede hacer un rol sin dejar rastro. `simple` usa el
    protocolo simple del driver (una función `RETURNS trigger` no se deja preparar)."""
    async with motor.connect() as cx:
        tx = await cx.begin()
        try:
            if simple:
                cruda = await cx.get_raw_connection()
                return ("ok", await cruda.driver_connection.execute(sql))
            r = await cx.execute(text(sql), p)
            filas = len(r.fetchall()) if r.returns_rows else r.rowcount
            return ("ok", filas)
        except Exception as e:  # noqa: BLE001
            # La excepción REAL del driver (SQLAlchemy la envuelve en ProgrammingError & co.).
            orig = getattr(e, "orig", e)
            real = orig.__cause__ if isinstance(orig.__cause__, Exception) else orig
            return (type(real).__name__, str(real).splitlines()[0][:140])
        finally:
            await tx.rollback()


async def _verbos(motor) -> tuple[str, ...]:
    v = int(await _uno(motor, "SHOW server_version_num"))
    return VERBOS + (("MAINTAIN",) if v >= 170000 else ())


async def _efectivo(motor) -> dict:
    verbos = await _verbos(motor)
    r = {}
    async with motor.connect() as cx:
        for rol in ("public", *ROLES, "contexto_audit_ro", DUENO):
            for p in verbos:
                r[f"{rol}:{p}"] = (await cx.execute(text(
                    "SELECT has_table_privilege(:r, 'public.activos_inmutables', :p)"), {"r": rol, "p": p})).scalar()
            for p in ("SELECT", "INSERT", "UPDATE", "REFERENCES"):
                r[f"{rol}:col:{p}"] = (await cx.execute(text(
                    "SELECT has_any_column_privilege(:r, 'public.activos_inmutables', :p)"),
                    {"r": rol, "p": p})).scalar()
    return r


async def _catalogo(motor) -> dict:
    """Todo lo que la 042 NO debe mover, más el ACL como CONJUNTO (el orden textual no importa)."""
    async with motor.connect() as cx:
        async def q(sql):
            return [tuple(x) for x in (await cx.execute(text(sql))).all()]
        return {
            "rls_force": await q("SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                                 "WHERE oid = 'public.activos_inmutables'::regclass"),
            "acl": sorted(await q("""
                SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
                       a.privilege_type, a.is_grantable, pg_get_userbyid(a.grantor)
                FROM pg_class c, aclexplode(c.relacl) a WHERE c.oid = 'public.activos_inmutables'::regclass""")),
            "columnas": await q("""
                SELECT attname, format_type(atttypid, atttypmod), attnotnull, atthasdef, attacl::text
                FROM pg_attribute WHERE attrelid = 'public.activos_inmutables'::regclass
                  AND attnum > 0 AND NOT attisdropped ORDER BY attnum"""),
            "constraints": sorted(await q("""
                SELECT conname, contype::text, convalidated, pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conrelid = 'public.activos_inmutables'::regclass""")),
            "politicas": sorted(await q("""
                SELECT policyname, cmd, roles::text, permissive, qual, with_check FROM pg_policies
                WHERE schemaname = 'public' AND tablename = 'activos_inmutables'""")),
            "triggers": sorted(await q("""
                SELECT tgname, tgenabled::text, pg_get_triggerdef(oid) FROM pg_trigger
                WHERE tgrelid = 'public.activos_inmutables'::regclass AND NOT tgisinternal""")),
            "funcion_041": await q("""
                SELECT prosecdef, proconfig::text, md5(prosrc), proacl::text FROM pg_proc
                WHERE oid = to_regprocedure('public.activos_invalida_evidencia_desfasada()')"""),
        }


async def _huellas(motor) -> dict:
    async with motor.connect() as cx:
        f = (await cx.execute(text(f"""
            SELECT count(*) AS filas,
                   md5(string_agg(md5(row({COLUMNAS})::text), '' ORDER BY id)) AS contenido,
                   md5(string_agg(md5(coalesce(servicios_cercanos, '<NULL>')), '' ORDER BY id)) AS servicios,
                   md5(string_agg(md5(coalesce(conectividad, '<NULL>')), '' ORDER BY id)) AS conectividad,
                   md5(string_agg(md5(geom::text), '' ORDER BY id)) AS geom,
                   count(servicios_evidencia) + count(conectividad_evidencia) AS con_evidencia
            FROM public.activos_inmutables"""))).mappings().one()
    return dict(f)


def _operaciones(banco) -> dict:
    """Lo que un rol intentaría sobre el destino. Cada una se ejecuta y se REVIERTE."""
    doc = _docs_reales()["servicios"].model_dump_json()
    otro = "ST_SetSRID(ST_MakePoint(-78.50, -0.20), 4326)" if banco["postgis"] else "'POINT(-78.5 -0.2)'"
    return {
        "SELECT": ("SELECT id FROM public.activos_inmutables", {}),
        "INSERT": (f"INSERT INTO public.activos_inmutables (geom, direccion_estandarizada) "
                   f"VALUES ({banco['punto']}, 'Dirección intrusa')", {}),
        "UPDATE evidencia": ("UPDATE public.activos_inmutables SET servicios_evidencia = CAST(:d AS jsonb)", {"d": doc}),
        "UPDATE texto": ("UPDATE public.activos_inmutables SET servicios_cercanos = 'texto fabricado'", {}),
        "UPDATE geom": (f"UPDATE public.activos_inmutables SET geom = {otro}", {}),
        "DELETE": ("DELETE FROM public.activos_inmutables", {}),
        "TRUNCATE": ("TRUNCATE public.activos_inmutables", {}),
        "CREATE TRIGGER": ("CREATE TRIGGER t042_intruso BEFORE UPDATE ON public.activos_inmutables "
                           "FOR EACH ROW EXECUTE FUNCTION public.activos_invalida_evidencia_desfasada()", {}),
        "REFERENCES": ("CREATE TABLE s042_andamio.ancla (a uuid REFERENCES public.activos_inmutables (id))", {}),
        "LOCK exclusivo": ("LOCK TABLE public.activos_inmutables IN ACCESS EXCLUSIVE MODE", {}),
    }


async def _matriz(banco, roles) -> dict:
    ops = _operaciones(banco)
    return {(rol, op): await _prueba(banco["motor"](rol), sql, **p) for rol in roles for op, (sql, p) in ops.items()}


def _denegado(res) -> bool:
    return res[0] == "InsufficientPrivilegeError" and "permission denied" in res[1] \
        and "row-level security" not in res[1]


# ── B1 · la 042 cierra la autoridad directa sin tocar filas ni nada más ───────────
@pg
async def test_042_cierra_la_autoridad_directa_sin_tocar_filas_ni_lo_demas(banco):
    verbos = await _verbos(banco["admin"])
    antes_ef, antes_cat, antes_h = await _efectivo(banco["admin"]), await _catalogo(banco["dueno"]), \
        await _huellas(banco["dueno"])
    assert all(antes_ef[f"{r}:{p}"] for r in ROLES for p in verbos), "el banco nace con la exposición medida"
    await _aplica(banco["dueno"])
    ef = await _efectivo(banco["admin"])
    for rol in ("public", *ROLES):
        fuga = [k for k, v in ef.items() if k.startswith(f"{rol}:") and v]
        assert not fuga, fuga
    assert [k for k, v in ef.items() if k.startswith("contexto_audit_ro:") and v] == \
        ["contexto_audit_ro:SELECT", "contexto_audit_ro:col:SELECT"]
    assert all(ef[f"{DUENO}:{p}"] for p in verbos), "el dueño conserva toda su autoridad"
    cat = await _catalogo(banco["dueno"])
    for k in ("rls_force", "columnas", "constraints", "politicas", "triggers", "funcion_041"):
        assert cat[k] == antes_cat[k], k
    assert {(g, p) for g, p, _, _ in cat["acl"]} == \
        {(DUENO, p) for p in verbos} | {("contexto_audit_ro", "SELECT")}
    assert await _huellas(banco["dueno"]) == antes_h, "cero cambios de filas"
    assert antes_h["con_evidencia"] == 0


@pg
async def test_042_dos_veces_es_un_no_op(banco):
    await _aplica(banco["dueno"])
    cat, ef = await _catalogo(banco["dueno"]), await _efectivo(banco["admin"])
    await _aplica(banco["dueno"])
    assert await _catalogo(banco["dueno"]) == cat and await _efectivo(banco["admin"]) == ef


# ── B2 · CONTROLES con roles REALES: antes (positivo) y después (negativo) ──────────
@pg
async def test_controles_con_roles_reales_antes_y_despues(banco):
    h0 = await _huellas(banco["dueno"])
    antes = await _matriz(banco, ROLES)
    # CONTROL POSITIVO: el defecto existe. service_role (BYPASSRLS) lo hace TODO; anon y
    # authenticated chocan con el RLS en DML, pero TRUNCATE, TRIGGER, REFERENCES y LOCK lo sortean.
    for op in _operaciones(banco):
        assert antes[("service_role", op)][0] == "ok", (op, antes[("service_role", op)])
    assert antes[("service_role", "SELECT")] == ("ok", 3) and antes[("service_role", "UPDATE evidencia")] == ("ok", 3)
    for rol in ("anon", "authenticated"):
        assert antes[(rol, "SELECT")] == ("ok", 0) and antes[(rol, "UPDATE evidencia")] == ("ok", 0)
        assert "row-level security" in antes[(rol, "INSERT")][1]
        for op in ("TRUNCATE", "CREATE TRIGGER", "REFERENCES", "LOCK exclusivo"):
            assert antes[(rol, op)][0] == "ok", (rol, op, antes[(rol, op)])
    await _aplica(banco["dueno"])
    despues = await _matriz(banco, ROLES)
    abiertos = {k: v for k, v in despues.items() if not _denegado(v)}
    assert not abiertos, abiertos
    assert await _huellas(banco["dueno"]) == h0, "cada intento se revirtió: las filas no se movieron"


@pg
async def test_contexto_audit_ro_sigue_leyendo_y_no_muta(banco):
    await _aplica(banco["dueno"])
    m = await _matriz(banco, ["contexto_audit_ro"])
    assert m[("contexto_audit_ro", "SELECT")] == ("ok", 3), "lee todas las filas por su política"
    for op, res in m.items():
        if op[1] != "SELECT":
            assert _denegado(res), (op, res)


@pg
async def test_el_dueno_conserva_su_autoridad_y_el_trigger_de_la_041_sigue_anulando(banco):
    await _aplica(banco["dueno"])
    m = await _matriz(banco, [DUENO])
    assert all(r[0] == "ok" for r in m.values()), m
    # Escritura real (confirmada) del dueño: evidencia, y luego una reubicación sin evidencia nueva.
    uid, doc = str(uuid.UUID(int=1)), _docs_reales()["servicios"].model_dump_json()
    otro = "ST_SetSRID(ST_MakePoint(-78.50, -0.20), 4326)" if banco["postgis"] else "'POINT(-78.5 -0.2)'"
    async with banco["dueno"].begin() as cx:
        await cx.execute(text("UPDATE public.activos_inmutables SET servicios_evidencia = CAST(:d AS jsonb) "
                              "WHERE id = :id"), {"d": doc, "id": uid})
    assert await _uno(banco["dueno"], "SELECT servicios_evidencia IS NOT NULL FROM public.activos_inmutables "
                                      "WHERE id = :id", id=uid) is True
    async with banco["dueno"].begin() as cx:
        await cx.execute(text(f"UPDATE public.activos_inmutables SET geom = {otro} WHERE id = :id"), {"id": uid})
    assert await _uno(banco["dueno"], "SELECT servicios_evidencia IS NULL FROM public.activos_inmutables "
                                      "WHERE id = :id", id=uid) is True, "el trigger de la 041 sigue vivo"


@pg
async def test_la_funcion_de_la_041_no_es_un_vector(banco):
    """Su EXECUTE (privilegios por defecto) no se toca: no es invocable directamente, ningún rol
    público puede crear objetos en `public`, y sin TRIGGER no se engancha a la tabla."""
    llamada = "SELECT public.activos_invalida_evidencia_desfasada()"
    for rol in ROLES:
        r = await _prueba(banco["motor"](rol), llamada, simple=True)
        assert r[0] == "FeatureNotSupportedError" and "trigger" in r[1], (rol, r)
        assert await _uno(banco["admin"], f"SELECT has_schema_privilege('{rol}', 'public', 'CREATE')") is False
    await _aplica(banco["dueno"])
    for rol in ROLES:
        r = await _prueba(banco["motor"](rol), llamada, simple=True)
        assert r[0] == "FeatureNotSupportedError", (rol, r)
        sql, p = _operaciones(banco)["CREATE TRIGGER"]
        assert _denegado(await _prueba(banco["motor"](rol), sql, **p)), rol


# ── B3 · estados ajenos: FAIL CLOSED sin tocar nada ───────────────────────────────
AJENOS = {
    "sin la 041": None,   # se prepara con el ROLLBACK documentado de la 041
    "RLS apagado": "ALTER TABLE public.activos_inmutables DISABLE ROW LEVEL SECURITY",
    "FORCE": "ALTER TABLE public.activos_inmutables FORCE ROW LEVEL SECURITY",
    "política extra para anon": "CREATE POLICY p042_anon ON public.activos_inmutables FOR SELECT TO anon USING (true)",
    "PUBLIC con privilegio": "GRANT SELECT ON TABLE public.activos_inmutables TO PUBLIC",
    "destinatario no medido": "GRANT SELECT ON TABLE public.activos_inmutables TO p042_intruso",
    "subconjunto (anon sin TRUNCATE)": "REVOKE TRUNCATE ON TABLE public.activos_inmutables FROM anon",
    "auditor con más que SELECT": "GRANT INSERT ON TABLE public.activos_inmutables TO contexto_audit_ro",
    "ACL de columna": "GRANT UPDATE (servicios_evidencia) ON TABLE public.activos_inmutables TO contexto_audit_ro",
    "opción de concesión": "GRANT SELECT ON TABLE public.activos_inmutables TO authenticated WITH GRANT OPTION",
    "evidencia bajo autoridad abierta": "EVIDENCIA",
    "vista dependiente": "CREATE VIEW public.v042_activos AS SELECT id FROM public.activos_inmutables",
    "regla": "CREATE RULE r042 AS ON INSERT TO public.activos_inmutables DO ALSO NOTIFY r042",
    "herencia": "CREATE TABLE public.activos_hijo042 () INHERITS (public.activos_inmutables)",
    "publicación": "ADMIN:CREATE PUBLICATION p042_pub FOR TABLE public.activos_inmutables",
    "función que la nombra": ("CREATE FUNCTION public.f042_nombra() RETURNS bigint LANGUAGE sql "
                              "AS 'SELECT count(*) FROM public.activos_inmutables'"),
    "SECURITY DEFINER dinámica": ("CREATE FUNCTION public.f042_rpc(q text) RETURNS void LANGUAGE plpgsql "
                                  "SECURITY DEFINER AS $f$ BEGIN EXECUTE q; END $f$"),
    "trigger extra": ("CREATE FUNCTION public.f042_trg() RETURNS trigger LANGUAGE plpgsql AS "
                      "$f$ BEGIN RETURN NEW; END $f$; CREATE TRIGGER t042_extra BEFORE INSERT ON "
                      "public.activos_inmutables FOR EACH ROW EXECUTE FUNCTION public.f042_trg()"),
}


async def _prepara(banco, caso):
    accion = AJENOS[caso]
    if caso == "destinatario no medido":
        async with banco["admin"].begin() as cx:
            await cx.execute(text("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='p042_intruso') "
                                  "THEN CREATE ROLE p042_intruso NOLOGIN; END IF; END $$;"))
    if accion is None:
        async with banco["dueno"].connect() as cx:
            cruda = await cx.get_raw_connection()
            await cruda.driver_connection.execute(_rollback(M041.read_text(encoding="utf-8")))
        return
    if accion == "EVIDENCIA":
        doc = _docs_reales()["servicios"].model_dump_json()
        async with banco["dueno"].begin() as cx:
            await cx.execute(text("UPDATE public.activos_inmutables SET servicios_evidencia = CAST(:d AS jsonb) "
                                  "WHERE id = :id"), {"d": doc, "id": str(uuid.UUID(int=1))})
        return
    motor = banco["admin"] if accion.startswith("ADMIN:") else banco["dueno"]
    async with motor.connect() as cx:
        cruda = await cx.get_raw_connection()
        await cruda.driver_connection.execute(accion.removeprefix("ADMIN:"))


@pg
@pytest.mark.parametrize("caso", sorted(AJENOS))
async def test_042_falla_cerrada_ante_un_estado_ajeno(banco, caso):
    await _prepara(banco, caso)
    antes = await _catalogo(banco["dueno"]), await _efectivo(banco["admin"])
    r = await _intenta_aplicar(banco["dueno"])
    assert "042 ABORTA" in r, r
    assert (await _catalogo(banco["dueno"]), await _efectivo(banco["admin"])) == antes, "no tocó nada"


@pg
async def test_042_la_aplica_solo_el_dueno(banco):
    r = await _intenta_aplicar(banco["admin"])   # superusuario, pero NO el dueño
    assert "042 ABORTA: el dueño de activos_inmutables no es quien aplica" in r, r


# ── B4 · estados PERMITIDOS ─────────────────────────────────────────────────────────
@pg
async def test_042_acepta_service_role_ya_revocado_a_mano(banco):
    async with banco["dueno"].begin() as cx:
        await cx.execute(text("REVOKE ALL PRIVILEGES ON TABLE public.activos_inmutables FROM service_role"))
    assert await _intenta_aplicar(banco["dueno"]) == "ok"
    ef = await _efectivo(banco["admin"])
    assert not any(v for k, v in ef.items() if k.split(":")[0] in ("public", *ROLES))


@pg
async def test_042_ya_cerrada_con_evidencia_nueva_es_no_op(banco):
    """Con la autoridad YA cerrada, la evidencia que escriba el dueño es legítima: reaplicar no aborta."""
    await _aplica(banco["dueno"])
    await _prepara(banco, "evidencia bajo autoridad abierta")
    cat, h = await _catalogo(banco["dueno"]), await _huellas(banco["dueno"])
    assert h["con_evidencia"] == 1
    assert await _intenta_aplicar(banco["dueno"]) == "ok"
    assert await _catalogo(banco["dueno"]) == cat and await _huellas(banco["dueno"]) == h


# ── B5 · ROLLBACK: reversión de emergencia al estado medido (inseguro) ───────────────
@pg
async def test_rollback_devuelve_los_privilegios_efectivos_medidos(banco):
    antes_ef, antes_acl = await _efectivo(banco["admin"]), (await _catalogo(banco["dueno"]))["acl"]
    await _aplica(banco["dueno"])
    async with banco["dueno"].connect() as cx:
        cruda = await cx.get_raw_connection()
        await cruda.driver_connection.execute(_rollback(M042.read_text(encoding="utf-8")))
    assert await _efectivo(banco["admin"]) == antes_ef
    assert set((await _catalogo(banco["dueno"]))["acl"]) == set(antes_acl), "mismo ACL como conjunto"
    assert await _intenta_aplicar(banco["dueno"]) == "ok", "y la 042 vuelve a cerrar"


# ── B6 · regresión: la 040 y la 041 siguen enteras ───────────────────────────────────
@pg
async def test_la_040_sigue_efectiva_despues_de_la_042(banco, monkeypatch):
    import app.entorno_curacion as curacion
    from app.esquema_requerido import aplicar_migracion
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from tests.test_perimetro_040 import DOBLE_POIS, _vista_de_la_023
    dueno = banco["dueno"]
    async with dueno.begin() as cx:
        await cx.execute(text(DOBLE_POIS))
    monkeypatch.setattr(curacion, "_curacion_ready", False)
    async with async_sessionmaker(dueno)() as s:
        await curacion.ensure_curacion_table(s)
    async with dueno.begin() as cx:
        await cx.execute(text(_vista_de_la_023()))
        await cx.execute(text("GRANT ALL PRIVILEGES ON TABLE public.pois_propios, public.entorno_curacion, "
                              "public.pois_vivos TO anon, authenticated, service_role"))
    async with async_sessionmaker(dueno)() as s:
        await aplicar_migracion(str(M040), db=s)

    async def _estado_040():
        rels = ("public.pois_propios", "public.entorno_curacion", "public.pois_vivos")
        privs = {(r, rel, p): await _uno(banco["admin"], f"SELECT has_table_privilege('{r}', '{rel}', '{p}')")
                 for r in ROLES for rel in rels for p in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")}
        rls = await _uno(banco["admin"], "SELECT bool_and(relrowsecurity) FROM pg_class WHERE oid IN "
                         "('public.pois_propios'::regclass, 'public.entorno_curacion'::regclass)")
        inv = await _uno(banco["admin"], "SELECT 'security_invoker=true' = ANY(reloptions) FROM pg_class "
                         "WHERE oid = 'public.pois_vivos'::regclass")
        return privs, rls, inv

    antes = await _estado_040()
    assert antes[1] and antes[2] and not any(antes[0].values()), "la 040 quedó aplicada en el banco"
    await _aplica(dueno)
    assert await _estado_040() == antes, "la 042 no reabre ni mueve nada de la 040"


@pg
async def test_la_041_sigue_entera_despues_de_la_042(banco):
    from app.esquema_requerido import aplicar_migracion
    from sqlalchemy.ext.asyncio import async_sessionmaker
    await _aplica(banco["dueno"])
    cat = await _catalogo(banco["dueno"])
    async with async_sessionmaker(banco["dueno"])() as s:
        await aplicar_migracion(str(M041), db=s)          # la 041 se reconoce ya aplicada: no-op
    assert await _catalogo(banco["dueno"]) == cat
    r = await _prueba(banco["dueno"], "UPDATE public.activos_inmutables SET servicios_evidencia = "
                      "'{\"contract_version\": \"place-dimension-evidence/v0\", \"status\": \"available\"}'::jsonb")
    assert r[0] == "CheckViolationError", "el CHECK de la 041 sigue rechazando lo incoherente"


# ── B7 · el escritor NUEVO (con la 041) sigue escribiendo como dueño ────────────────
@pg
async def test_el_escritor_nuevo_escribe_texto_y_evidencia_como_dueno_tras_la_042(banco, monkeypatch):
    import app.place.persistible as persistible
    import app.routers.assets as assets
    import app.rutas as rutas
    from app.models import ActivoInmutable
    from sqlalchemy import select
    from tests.test_place_provenance_041 import COMPLETA, LAT, LON, _materia
    monkeypatch.setattr(persistible, "_esquema_041_visto", False)
    await _aplica(banco["dueno"])

    async def _fetch(lat, lon, timeout=None):
        return [{"lat": LAT, "lon": LON, "tags": {"amenity": "pharmacy", "name": "Farmacia OSM"}}]

    async def _recolecta(lat, lon):
        return _materia(COMPLETA)

    async def _nada(*a, **k):
        return None
    monkeypatch.setattr(assets, "_fetch_pois", _fetch)
    monkeypatch.setattr(rutas, "_recolectar_zona", _recolecta)
    monkeypatch.setattr(assets, "AsyncSessionLocal", banco["Sesion"])
    monkeypatch.setattr(assets, "ensure_walk_score_fuente_column", _nada)
    uid = str(uuid.UUID(int=1))
    async with banco["Sesion"]() as s:
        assert await persistible.esquema_041_presente(s), "detecta la 041"
        if banco["postgis"]:   # el modelo lee `geom` con ST_AsEWKB: solo con PostGIS
            assert (await s.execute(select(ActivoInmutable).where(ActivoInmutable.id == uid))).scalar_one()
    await assets._recompute_walk_score(uid, LAT, LON)
    async with banco["dueno"].connect() as cx:
        f = (await cx.execute(text(
            "SELECT servicios_cercanos, servicios_evidencia::text AS se, conectividad_evidencia::text AS ce "
            "FROM public.activos_inmutables WHERE id = :id"), {"id": uid})).mappings().one()
    assert f["se"] and f["ce"], "texto y evidencia escritos juntos"
    lectura = persistible.leer_contexto_persistido(
        {"lat": LAT, "lon": LON, "servicios_evidencia": f["se"], "servicios_cercanos": f["servicios_cercanos"]},
        "servicios")
    assert lectura.estado == "estructurada" and lectura.texto == f["servicios_cercanos"]
    assert json.loads(f["ce"])["walk_duration"]["value_class"] == "estimated"


# ── B8 · MUTACIONES: quitar una guarda material de la 042 se detecta ────────────────
def _mutante(de: str, a: str) -> str:
    sql = M042.read_text(encoding="utf-8")
    assert de in sql, f"la mutación no encuentra su objetivo: {de[:60]}"
    return sql.replace(de, a, 1)


REVOKE_ROL = "EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.activos_inmutables FROM %I', rol);"
REVOKE_PUBLIC = "REVOKE ALL PRIVILEGES ON TABLE public.activos_inmutables FROM PUBLIC;"
MUTACIONES = {
    # (texto original, texto mutante, estado previo del banco o None, qué debe pasar)
    "sin REVOKE a los tres roles": (REVOKE_ROL, "NULL;", None, "042 FALLA"),
    "REVOKE solo de DML": (REVOKE_ROL, REVOKE_ROL.replace("ALL PRIVILEGES", "INSERT, UPDATE, DELETE"), None,
                           "042 FALLA"),
    "revoca también al auditor": (REVOKE_PUBLIC, REVOKE_PUBLIC + "\nREVOKE ALL PRIVILEGES ON TABLE "
                                  "public.activos_inmutables FROM contexto_audit_ro;", None,
                                  "042 FALLA: contexto_audit_ro perdió SELECT"),
    "añade FORCE": (REVOKE_PUBLIC, REVOKE_PUBLIC + "\nALTER TABLE public.activos_inmutables FORCE ROW LEVEL "
                    "SECURITY;", None, "042 FALLA: cambió el RLS o el FORCE"),
    "sin compuerta de evidencia": ("IF abierta AND n > 0 THEN", "IF false THEN",
                                   "evidencia bajo autoridad abierta", "ok"),
    "sin compuerta SECURITY DEFINER": ("AND (p.prosrc ~* '\\mexecute\\M'", "AND false AND (p.prosrc ~* '\\mexecute\\M'",
                                       "SECURITY DEFINER dinámica", "ok"),
    "sin compuerta de subconjunto": ("IF privs_r IS NOT NULL AND privs_r IS DISTINCT FROM privs_d THEN",
                                     "IF false THEN", "subconjunto (anon sin TRUNCATE)", "ok"),
    # Defensa en profundidad: sin la compuerta, la verificación final lo atrapa igual.
    "sin compuerta de destinatario": ("IF lista IS NOT NULL THEN\n        RAISE EXCEPTION '042 ABORTA: el ACL de",
                                      "IF false THEN\n        RAISE EXCEPTION '042 ABORTA: el ACL de",
                                      "destinatario no medido", "042 FALLA: quedan privilegios de tabla en pie"),
}


@pg
@pytest.mark.parametrize("nombre", sorted(MUTACIONES))
async def test_quitar_una_guarda_de_la_042_se_detecta(banco, nombre):
    de, a, estado, esperado = MUTACIONES[nombre]
    if estado:
        # Sin la mutación, ese estado ABORTA (lo prueba B3); con ella, pasa: la guarda era lo único.
        await _prepara(banco, estado)
    r = await _intenta_aplicar(banco["dueno"], _mutante(de, a))
    if esperado == "ok":
        assert r == "ok", f"la guarda quitada no era la que frenaba este estado: {r}"
    else:
        assert esperado in r, r
