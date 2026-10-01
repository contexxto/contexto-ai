"""PLACE-PROVENANCE-041 · la migración 041, probada sin producción.

  A · sin base: hace SOLO lo que dice (dos columnas jsonb nullable sin default y dos CHECK sobre
      `public.activos_inmutables`), sin DML, sin GRANT/REVOKE/políticas/triggers, sin crear
      `contexto_procedencia`, y con un ROLLBACK comentado que es su inverso exacto.
  B · PostgreSQL real (`TEST_DATABASE_URL`, también en el CI; en local además PG17 y PostGIS):
      `activos_inmutables` con las columnas, los CHECK, el RLS, la política y los grants MEDIDOS
      en producción, y un dueño NOSUPERUSER + BYPASSRLS como `postgres`. Se prueba:
        · esquema pre-041 → PASS; filas legado intactas; ninguna recibe procedencia;
        · segunda aplicación → no-op explícito; estados ajenos → FAIL CLOSED sin tocar nada;
        · el CHECK acepta los documentos REALES del constructor y rechaza los incoherentes;
          UNKNOWN (NULL) sigue siendo válido;
        · el ROLLBACK devuelve el catálogo exacto;
        · la 041 no mueve RLS/ACL/políticas de la tabla, ni debilita la 040;
        · el escritor real (`_recompute_walk_score`) contra el CHECK real;
        · CONTROLES NEGATIVOS: quitar una guarda material pone en rojo la prueba que la vigila.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

RAIZ = Path(__file__).resolve().parents[1]
M041 = RAIZ / "migrations" / "041_place_provenance_evidencia.sql"
M040 = RAIZ / "migrations" / "040_place_source_perimeter.sql"
ROLES = ("anon", "authenticated", "service_role")
DUENO = "p041_owner"
COLS = ("servicios_evidencia", "conectividad_evidencia")


def _sin_comentarios(sql: str) -> str:
    return "\n".join(l.split("--", 1)[0] for l in sql.splitlines())


def _rollback(sql: str) -> str:
    lineas = sql.replace("\r\n", "\n").split("\n")
    i = next(n for n, l in enumerate(lineas) if l.startswith("-- ── ROLLBACK"))
    return "\n".join(l[5:] for l in lineas[i:] if l.startswith("--   ")).strip() + "\n"


# ─────────────────────────────── A · sin base ────────────────────────────────
def test_la_041_hace_solo_lo_que_dice():
    cuerpo = _sin_comentarios(M041.read_text(encoding="utf-8"))
    assert cuerpo.strip().startswith("BEGIN;") and cuerpo.rstrip().endswith("COMMIT;")
    assert "SET LOCAL lock_timeout" in cuerpo
    for col in COLS:
        assert f"ADD COLUMN {col} jsonb;" in cuerpo, col
    assert "ADD CONSTRAINT ck_activos_servicios_evidencia CHECK" in cuerpo
    assert "ADD CONSTRAINT ck_activos_conectividad_evidencia CHECK" in cuerpo
    # Nada de lo que la unidad no autoriza.
    assert not re.search(r"(?i)ADD\s+COLUMN[^;]*\bDEFAULT\b", cuerpo), "ninguna columna nace con DEFAULT"
    assert "coalesce((" in cuerpo, "una clave ausente no puede colarse por un NULL en el CHECK"
    assert not re.search(r"(?i)^\s*(INSERT|UPDATE|DELETE|TRUNCATE)\b", cuerpo, re.M)
    assert not re.search(r"(?i)\b(GRANT|REVOKE)\b", cuerpo)
    assert not re.search(r"(?i)\bCREATE\s+(POLICY|VIEW)\b", cuerpo)
    # UN trigger y UNA función, los de la evidencia desfasada, y nada más (PROD-APPLY-PREFLIGHT).
    assert re.findall(r"(?i)\bCREATE\s+FUNCTION\s+([a-z_.]+)", cuerpo) == \
        ["public.activos_invalida_evidencia_desfasada"]
    assert re.findall(r"(?i)\bCREATE\s+TRIGGER\s+([a-z_]+)", cuerpo) == ["trg_activos_invalida_evidencia_desfasada"]
    assert "BEFORE UPDATE OF servicios_cercanos, conectividad, geom ON public.activos_inmutables" in cuerpo
    assert "SECURITY INVOKER" in cuerpo and "SET search_path = pg_catalog, public" in cuerpo
    assert not re.search(r"(?i)SECURITY\s+DEFINER", cuerpo)
    assert not re.search(r"(?i)\b(ENABLE|DISABLE|FORCE)\s+ROW\s+LEVEL", cuerpo)
    assert not re.search(r"(?i)ADD COLUMN\s+contexto_procedencia", cuerpo)
    assert not re.search(r"(?i)\bSET\s+(servicios_cercanos|conectividad)\b", cuerpo)
    # Solo `activos_inmutables` (y la función de su trigger): ni la 040 ni el respaldo.
    assert set(re.findall(r"public\.([a-z_0-9]+)", cuerpo)) == \
        {"activos_inmutables", "activos_invalida_evidencia_desfasada"}
    for compuerta in ("no existe public.activos_inmutables", "el dueño de activos_inmutables no es",
                      "¿Es la tabla correcta?", "existe contexto_procedencia", "ya aplicada",
                      "estado intermedio o ajeno", "ya existe una restricción",
                      "no quedaron jsonb, nullable, sin default", "los dos CHECK no quedaron",
                      "nacieron con evidencia", "cambió el RLS, el FORCE o el ACL",
                      "cambiaron las políticas o los triggers",
                      "ya existe la función o el trigger de la 041", "el trigger no quedó BEFORE UPDATE",
                      "SECURITY INVOKER con search_path fijo"):
        assert compuerta in cuerpo, compuerta


def test_el_rollback_documentado_es_el_inverso_exacto_y_esta_comentado():
    sql = M041.read_text(encoding="utf-8")
    rb = _rollback(sql)
    assert rb.startswith("BEGIN;") and rb.rstrip().endswith("COMMIT;")
    for c in COLS:
        assert f"DROP COLUMN IF EXISTS {c};" in rb
    for ck in ("ck_activos_servicios_evidencia", "ck_activos_conectividad_evidencia"):
        assert f"DROP CONSTRAINT IF EXISTS {ck};" in rb
    assert "DROP TRIGGER IF EXISTS trg_activos_invalida_evidencia_desfasada ON public.activos_inmutables;" in rb
    assert "DROP FUNCTION IF EXISTS public.activos_invalida_evidencia_desfasada();" in rb
    assert "servicios_cercanos" not in rb and "conectividad;" not in rb, "el texto legado no se toca"
    cola = sql.split("-- ── ROLLBACK", 1)[1]
    assert all(l.startswith("--") or not l.strip() for l in cola.splitlines()[1:])


# ──────────────────────────── B · Postgres real ────────────────────────────
URL = os.getenv("TEST_DATABASE_URL", "")
pg = pytest.mark.skipif(not URL, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas")

# Las columnas y los CHECK de `public.activos_inmutables` MEDIDOS en producción el 2026-09-30
# (evidencia/place_legacy_backfill_preflight_20260930/esquema_prod.json). Sin las FK a
# `inventory_*`, que la 041 no mira. `geom` es PostGIS si el banco lo tiene.
def _ddl_activos(con_postgis: bool) -> str:
    geom = "geometry(Point, 4326)" if con_postgis else "text"
    return f"""
    CREATE TABLE public.activos_inmutables (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        geom {geom} NOT NULL,
        direccion_estandarizada character varying NOT NULL,
        piso_altura integer DEFAULT 1,
        walk_score integer CHECK (walk_score >= 0 AND walk_score <= 100),
        score_ruido_predictivo character varying
            CHECK (score_ruido_predictivo IN ('BAJO', 'MEDIO', 'ALTO')),
        volumen_trafico_historico integer DEFAULT 0,
        densidad_poblacional_pico integer DEFAULT 0,
        porcentaje_cobertura_vegetal numeric,
        created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
        tipo_activo text DEFAULT 'Departamento',
        image_sha256 text, imagen_url text, owner_user_id uuid, owner_agency_id uuid,
        conectividad text, servicios_cercanos text, caracteristicas jsonb, walk_score_fuente text,
        source_id uuid, ingestion_event_id uuid,
        inventory_class text CHECK (inventory_class IN ('live', 'demo', 'test', 'unknown')),
        received_at timestamp with time zone,
        evidence_exclusion_reason text CHECK (evidence_exclusion_reason = 'demo_contaminated'))
    """


LEGADO = [
    ("🌳 Parque Legado a ~300 m · 💊 Farmacia Legada a ~120 m", "🚇 Estación Legada ~500 m (7 min a pie)"),
    ("🛒 Súper Legado (~1.200 m), 🏥 Clínica (~900 m)", None),
    (None, None),
]
COLS_ORIGINALES = ("id, geom::text, direccion_estandarizada, walk_score, conectividad, "
                   "servicios_cercanos, caracteristicas::text, walk_score_fuente")


@pytest.fixture
async def banco(monkeypatch):
    """`activos_inmutables` como en producción, creada por un dueño NOSUPERUSER + BYPASSRLS."""
    from app.config import settings
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
        dueno_actual = (await cx.execute(text(
            "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = to_regclass('public.activos_inmutables')"
        ))).scalar()
        if dueno_actual not in (None, DUENO):
            pytest.fail(f"public.activos_inmutables ya existe y es de {dueno_actual}: no se toca")
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
    try:
        yield {"admin": admin, "motor": motor, "dueno": dueno, "postgis": con_postgis,
               "Sesion": async_sessionmaker(dueno, expire_on_commit=False)}
    finally:
        for m in motores:
            await m.dispose()
        async with admin.begin() as cx:
            await _limpia(cx)
        await admin.dispose()


async def _limpia(cx):
    await cx.execute(text("DROP VIEW IF EXISTS public.pois_vivos CASCADE"))
    await cx.execute(text("DROP TABLE IF EXISTS public.entorno_curacion, public.pois_propios, "
                          "public.pois_propios_backup_20260727, public.activos_inmutables CASCADE"))
    # La función del trigger NO depende de la tabla: sobrevive a su DROP y la 041 abortaría la
    # vez siguiente («la función sin sus columnas»). Es la compuerta haciendo su trabajo.
    await cx.execute(text("DROP FUNCTION IF EXISTS public.activos_invalida_evidencia_desfasada() CASCADE"))


async def _uno(motor, sql, **p):
    async with motor.connect() as cx:
        return (await cx.execute(text(sql), p)).scalar()


async def _aplica(motor, sql_texto=None):
    """Por el aplicador REAL del producto (`app.esquema_requerido.aplicar_migracion`)."""
    from app.esquema_requerido import aplicar_migracion
    from sqlalchemy.ext.asyncio import async_sessionmaker
    ruta = M041
    if sql_texto is not None:
        import tempfile
        ruta = Path(tempfile.gettempdir()) / f"m041_{uuid.uuid4().hex}.sql"
        ruta.write_text(sql_texto, encoding="utf-8")
    try:
        async with async_sessionmaker(motor)() as s:
            await aplicar_migracion(str(ruta), db=s)
    finally:
        if sql_texto is not None:
            ruta.unlink(missing_ok=True)


async def _intenta(motor, sql, **p):
    try:
        async with motor.begin() as cx:
            await cx.execute(text(sql), p)
        return "ok"
    except Exception as e:  # noqa: BLE001
        orig = getattr(e, "orig", e)
        return type(orig).__name__ + ": " + str(orig)[:160]


async def _catalogo(motor) -> dict:
    """Todo lo que la 041 toca o NO debe tocar de `activos_inmutables`, legible y comparable."""
    async with motor.connect() as cx:
        fila = (await cx.execute(text("""
            SELECT relrowsecurity, relforcerowsecurity, coalesce(relacl::text, '') AS acl
            FROM pg_class WHERE oid = 'public.activos_inmutables'::regclass"""))).mappings().one()
        columnas = [tuple(r) for r in (await cx.execute(text("""
            SELECT attname, format_type(atttypid, atttypmod), attnotnull, atthasdef, attacl::text
            FROM pg_attribute WHERE attrelid = 'public.activos_inmutables'::regclass
              AND attnum > 0 AND NOT attisdropped ORDER BY attnum"""))).all()]
        cks = sorted(tuple(r) for r in (await cx.execute(text("""
            SELECT conname, contype::text, convalidated FROM pg_constraint
            WHERE conrelid = 'public.activos_inmutables'::regclass"""))).all())
        pols = sorted(r[0] for r in (await cx.execute(text(
            "SELECT polname FROM pg_policy WHERE polrelid = 'public.activos_inmutables'::regclass"))).all())
        trg = (await cx.execute(text("SELECT count(*) FROM pg_trigger "
                                     "WHERE tgrelid = 'public.activos_inmutables'::regclass "
                                     "AND NOT tgisinternal"))).scalar()
    return {**dict(fila), "columnas": columnas, "constraints": cks, "politicas": pols, "triggers": trg}


async def _huella_legado(motor) -> str:
    return await _uno(motor, f"SELECT md5(string_agg(t::text, '|' ORDER BY t.id)) "
                             f"FROM (SELECT {COLS_ORIGINALES} FROM public.activos_inmutables) t")


def _docs_reales():
    """Los documentos del constructor REAL, con la materia de la suite de dominio."""
    from tests.test_place_provenance_041 import COMPLETA, _docs
    return _docs(COMPLETA)[1]


# ── B1 · aplica sobre el esquema de producción, sin tocar filas ni permisos ─────────
@pg
async def test_041_aplica_sin_tocar_filas_ni_permisos(banco):
    antes, huella = await _catalogo(banco["dueno"]), await _huella_legado(banco["dueno"])
    await _aplica(banco["dueno"])
    despues = await _catalogo(banco["dueno"])
    nuevas = {c[0]: c for c in despues["columnas"] if c[0] in COLS}
    assert set(nuevas) == set(COLS)
    for c in nuevas.values():
        assert c[1] == "jsonb" and c[2] is False and c[3] is False and c[4] is None, c
    assert ("ck_activos_servicios_evidencia", "c", True) in despues["constraints"]
    assert ("ck_activos_conectividad_evidencia", "c", True) in despues["constraints"]
    # Lo que no debía moverse, no se movió.
    assert despues["columnas"][:len(antes["columnas"])] == antes["columnas"]
    for k in ("relrowsecurity", "relforcerowsecurity", "acl", "politicas"):
        assert despues[k] == antes[k], k
    assert despues["triggers"] == antes["triggers"] + 1, "exactamente un trigger más: el de la 041"
    trg = await _uno(banco["dueno"], """
        SELECT t.tgtype::text || ':' || t.tgenabled::text || ':' || t.tgfoid::regprocedure::text || ':' ||
               (SELECT string_agg(a.attname::text, ',' ORDER BY a.attname) FROM pg_attribute a
                 WHERE a.attrelid = t.tgrelid AND a.attnum = ANY (t.tgattr::int2[]))
        FROM pg_trigger t WHERE t.tgrelid = 'public.activos_inmutables'::regclass
          AND t.tgname = 'trg_activos_invalida_evidencia_desfasada'""")
    assert trg == "19:O:activos_invalida_evidencia_desfasada():conectividad,geom,servicios_cercanos", trg
    assert await _huella_legado(banco["dueno"]) == huella, "filas legado intactas"
    assert await _uno(banco["dueno"], "SELECT count(*) FROM public.activos_inmutables "
                      "WHERE servicios_evidencia IS NOT NULL OR conectividad_evidencia IS NOT NULL") == 0
    assert not any(c[0] == "contexto_procedencia" for c in despues["columnas"])


# ── B2 · segunda vez: no-op explícito ────────────────────────────────────────────────
@pg
async def test_041_dos_veces_es_un_no_op_explicito(banco):
    await _aplica(banco["dueno"])
    doc = _docs_reales()["servicios"]
    await _intenta(banco["dueno"], "UPDATE public.activos_inmutables SET servicios_evidencia = "
                   "CAST(:d AS jsonb) WHERE id = :id", d=doc.model_dump_json(), id=str(uuid.UUID(int=1)))
    antes = await _catalogo(banco["dueno"])
    await _aplica(banco["dueno"])    # no revienta: la segunda vez reconoce el estado exacto
    assert await _catalogo(banco["dueno"]) == antes
    assert await _uno(banco["dueno"], "SELECT count(*) FROM public.activos_inmutables "
                      "WHERE servicios_evidencia IS NOT NULL") == 1, "no borra lo ya escrito"


# ── B3 · estados ajenos: FAIL CLOSED sin tocar nada ───────────────────────────────
AJENOS = {
    "columna con DEFAULT": "ALTER TABLE public.activos_inmutables ADD COLUMN servicios_evidencia jsonb "
                           "DEFAULT '{}'::jsonb",
    "solo una de las dos": "ALTER TABLE public.activos_inmutables ADD COLUMN conectividad_evidencia jsonb",
    "tipo equivocado": "ALTER TABLE public.activos_inmutables ADD COLUMN servicios_evidencia text",
    "la etiqueta descartada": "ALTER TABLE public.activos_inmutables ADD COLUMN contexto_procedencia text",
    "nombre de CHECK ocupado": "ALTER TABLE public.activos_inmutables ADD CONSTRAINT "
                               "ck_activos_servicios_evidencia CHECK (true)",
}


@pg
@pytest.mark.parametrize("caso", sorted(AJENOS))
async def test_041_falla_cerrada_ante_un_estado_ajeno(banco, caso):
    await _intenta(banco["dueno"], AJENOS[caso])
    antes = await _catalogo(banco["dueno"])
    with pytest.raises(Exception, match="041 ABORTA"):
        await _aplica(banco["dueno"])
    assert await _catalogo(banco["dueno"]) == antes, "abortar no deja nada a medias"


@pg
async def test_041_la_aplica_solo_el_dueno(banco):
    antes = await _catalogo(banco["dueno"])
    with pytest.raises(Exception, match="041 ABORTA: el dueño"):
        await _aplica(banco["admin"])   # un superusuario que NO es el dueño
    assert await _catalogo(banco["dueno"]) == antes


# ── B4 · el CHECK: documentos reales sí, incoherentes no, NULL siempre ─────────────
@pg
async def test_041_el_check_acepta_los_documentos_reales_y_la_ida_y_vuelta_es_exacta(banco):
    from app.contracts.place_evidence_v0 import NearbyPlacesEvidenceV0, NearestTransitEvidenceV0
    await _aplica(banco["dueno"])
    docs = _docs_reales()
    uid = str(uuid.UUID(int=1))
    r = await _intenta(banco["dueno"], "UPDATE public.activos_inmutables SET "
                       "servicios_evidencia = CAST(:s AS jsonb), conectividad_evidencia = CAST(:c AS jsonb) "
                       "WHERE id = :id", s=docs["servicios"].model_dump_json(),
                       c=docs["conectividad"].model_dump_json(), id=uid)
    assert r == "ok", r
    async with banco["dueno"].connect() as cx:
        s, c = (await cx.execute(text("SELECT servicios_evidencia::text, conectividad_evidencia::text "
                                      "FROM public.activos_inmutables WHERE id = :id"), {"id": uid})).one()
    assert NearbyPlacesEvidenceV0.model_validate_json(s) == docs["servicios"]
    assert NearestTransitEvidenceV0.model_validate_json(c) == docs["conectividad"]
    # insufficient_evidence también es un documento válido.
    from tests.test_place_provenance_041 import _docs, _transporte
    insuf = _docs([_transporte()])[1]["servicios"]
    assert await _intenta(banco["dueno"], "UPDATE public.activos_inmutables SET servicios_evidencia = "
                          "CAST(:s AS jsonb) WHERE id = :id", s=insuf.model_dump_json(), id=uid) == "ok"
    # Y volver a UNKNOWN (NULL) siempre es posible.
    assert await _intenta(banco["dueno"], "UPDATE public.activos_inmutables SET servicios_evidencia = NULL, "
                          "conectividad_evidencia = NULL WHERE id = :id", id=uid) == "ok"


def _mutar(doc_json: str, fn) -> str:
    d = json.loads(doc_json)
    fn(d)
    return json.dumps(d)


INCOHERENTES = {
    "servicios": {
        "no es un objeto": lambda d: None,
        "status unknown": lambda d: d.update(status="unknown", items=[]),
        "available sin elementos": lambda d: d.update(items=[]),
        "available sin evidencia": lambda d: d.update(evidence=[]),
        "insuficiente con elementos": lambda d: d.update(status="insufficient_evidence"),
        "evidencia runtime_only": lambda d: d["evidence"][0].update(persistence_policy="runtime_only"),
        "evidencia de Google": lambda d: d["evidence"][1].update(provider="Google-Places"),
        "recta rotulada como estimación": lambda d: d.update(distance_class="estimated"),
        "otra dimensión": lambda d: d.update(dimension="nearest_transit"),
        "otra versión": lambda d: d.update(contract_version="place-dimension-evidence/v1"),
        "sin fecha de derivación": lambda d: d.pop("derived_at"),
    },
    "conectividad": {
        "recta rotulada como ruta": lambda d: d["walk_duration"].update(value_class="derived"),
        "available sin parada": lambda d: d.update(stop=None),
        "insuficiente con parada": lambda d: d.update(status="insufficient_evidence"),
        "evidencia de Google": lambda d: d["evidence"][0].update(provider="google-routes"),
    },
}


@pg
@pytest.mark.parametrize("dim,caso", [(d, c) for d in INCOHERENTES for c in sorted(INCOHERENTES[d])])
async def test_041_el_check_rechaza_estados_incoherentes(banco, dim, caso):
    await _aplica(banco["dueno"])
    docs = _docs_reales()
    col = f"{dim}_evidencia"
    valor = ('"propio"' if caso == "no es un objeto"
             else _mutar(docs[dim].model_dump_json(), INCOHERENTES[dim][caso]))
    r = await _intenta(banco["dueno"], f"UPDATE public.activos_inmutables SET {col} = CAST(:v AS jsonb) "
                       "WHERE id = :id", v=valor, id=str(uuid.UUID(int=1)))
    assert f"ck_activos_{dim}_evidencia" in r, r


# ── B5 · ROLLBACK: el catálogo exacto de antes ────────────────────────────────────
@pg
async def test_041_rollback_documentado_devuelve_el_catalogo_exacto(banco):
    antes, huella = await _catalogo(banco["dueno"]), await _huella_legado(banco["dueno"])
    await _aplica(banco["dueno"])
    await _intenta(banco["dueno"], "UPDATE public.activos_inmutables SET servicios_evidencia = "
                   "CAST(:d AS jsonb) WHERE id = :id", d=_docs_reales()["servicios"].model_dump_json(),
                   id=str(uuid.UUID(int=1)))
    await _aplica(banco["dueno"], _rollback(M041.read_text(encoding="utf-8")))
    assert await _catalogo(banco["dueno"]) == antes
    assert await _huella_legado(banco["dueno"]) == huella, "el texto legado sigue intacto"
    await _aplica(banco["dueno"])   # y se puede volver a aplicar limpio
    assert len([c for c in (await _catalogo(banco["dueno"]))["columnas"] if c[0] in COLS]) == 2


# ── B6 · la 041 no debilita la 040 ────────────────────────────────────────────────
@pg
async def test_040_sigue_efectiva_despues_de_la_041(banco, monkeypatch):
    import app.entorno_curacion as curacion
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
    from app.esquema_requerido import aplicar_migracion
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

    privs, rls, inv = await _estado_040()
    assert rls and inv and not any(privs.values()), "la 040 quedó aplicada en el banco"
    await _aplica(dueno)
    assert await _estado_040() == (privs, rls, inv), "la 041 no reabre nada de la 040"


# ── B7 · el escritor REAL contra el CHECK real ────────────────────────────────────
@pg
async def test_el_escritor_real_escribe_evidencia_que_la_base_acepta(banco, monkeypatch):
    import app.place.persistible as persistible
    import app.routers.assets as assets
    import app.rutas as rutas
    from tests.test_place_provenance_041 import COMPLETA, LAT, LON, _materia
    monkeypatch.setattr(persistible, "_esquema_041_visto", False)

    async def _fetch(lat, lon, timeout=None):
        return [{"lat": LAT, "lon": LON, "tags": {"amenity": "pharmacy", "name": "Farmacia OSM"}}]

    async def _recolecta(lat, lon):
        return _materia(COMPLETA)

    async def _nada(*a, **k):
        return None
    monkeypatch.setattr(assets, "_fetch_pois", _fetch)
    monkeypatch.setattr(rutas, "_recolectar_zona", _recolecta)
    monkeypatch.setattr(assets, "AsyncSessionLocal", banco["Sesion"])
    # RELEASE-ISOLATION-041: este caso describe la 041 ACTIVADA; el flag va encendido.
    monkeypatch.setattr(assets.settings, "place_provenance_041_write_enabled", True)
    monkeypatch.setattr(assets, "ensure_walk_score_fuente_column", _nada)
    uid = str(uuid.UUID(int=1))

    # Sin la 041: el UPDATE de siempre, sin evidencia (la columna no existe).
    await assets._recompute_walk_score(uid, LAT, LON)
    async with banco["Sesion"]() as s:
        assert not await persistible.esquema_041_presente(s)
    # Con la 041: la misma llamada deja evidencia válida para el CHECK, y el texto sale de ella.
    await _aplica(banco["dueno"])
    await assets._recompute_walk_score(uid, LAT, LON)
    async with banco["dueno"].connect() as cx:
        f = (await cx.execute(text(
            "SELECT servicios_cercanos, conectividad, servicios_evidencia::text AS se, "
            "conectividad_evidencia::text AS ce FROM public.activos_inmutables WHERE id = :id"),
            {"id": uid})).mappings().one()
    lectura = persistible.leer_contexto_persistido(
        {"lat": LAT, "lon": LON, "servicios_evidencia": f["se"], "servicios_cercanos": f["servicios_cercanos"]},
        "servicios")
    assert lectura.estado == "estructurada" and lectura.texto == f["servicios_cercanos"]
    assert json.loads(f["ce"])["walk_duration"]["value_class"] == "estimated"


# ── B7b · la capa REAL (PostGIS, migraciones 014→023): de la vista al CHECK ─────────
@pg
async def test_la_capa_real_proyecta_la_procedencia_y_su_documento_pasa_el_check(banco, monkeypatch):
    """Solo con PostGIS (en local; el Postgres del CI no lo trae). El SQL REAL de `propia.py`
    contra la vista REAL `pois_vivos` → la tubería REAL → el documento → el CHECK real."""
    if not banco["postgis"]:
        pytest.skip("necesita PostGIS para las migraciones reales 014→023 y la vista pois_vivos")
    import app.agent.tools as tools
    import app.place.providers.propia as propia
    import app.rutas as rutas
    from app.contracts.evidence_v0 import SourceType
    from app.esquema_requerido import aplicar_migracion
    from app.place.persistible import documentos_persistibles
    from sqlalchemy.ext.asyncio import async_sessionmaker
    for m in ("014_pois_propios.sql", "019_pois_propios_ciudad.sql", "020_pois_propios_id_origen_unico.sql",
              "021_pois_propios_iglesia_seguridad.sql", "022_osm_id_con_tipo.sql",
              "023_curacion_engancha_poi.sql"):
        async with async_sessionmaker(banco["dueno"])() as s:
            await aplicar_migracion(str(RAIZ / "migrations" / m), db=s)
    lat, lon = -0.1755, -78.4858
    corredor = str(uuid.uuid4())
    async with banco["dueno"].begin() as cx:
        await cx.execute(text("DROP TABLE IF EXISTS pois_propios_backup_20260727"))
        await cx.execute(text(
            "INSERT INTO pois_propios (nombre, categoria, categoria_overture, geom, fuente, overture_id, osm_id, "
            "ciudad, actualizado_en) VALUES "
            "('Parque Real', 'parque', NULL, ST_SetSRID(ST_MakePoint(-78.4855, -0.1752), 4326), 'osm', NULL, "
            " 'node/7001', 'quito', '2026-09-22 14:30:03+00'), "
            "('Farmacia Real', 'farmacia', NULL, ST_SetSRID(ST_MakePoint(-78.4860, -0.1757), 4326), 'overture', "
            " '08f-real-1', NULL, 'quito', '2026-09-22 14:30:03+00'), "
            "('Estación Real', 'transporte', 'metro', ST_SetSRID(ST_MakePoint(-78.4830, -0.1740), 4326), 'osm', "
            " NULL, 'node/7003', 'quito', '2026-09-22 14:30:03+00')"))
        await cx.execute(text(
            "INSERT INTO entorno_curacion (activo_id, accion, nombre, corredor_id, poi_id, creado_en) "
            "SELECT :a, 'confirmado', 'Farmacia Real', :c, id, '2026-09-25 10:00:00+00' "
            "FROM pois_propios WHERE overture_id = '08f-real-1'"),
            {"a": str(uuid.UUID(int=1)), "c": corredor})

    monkeypatch.setattr(propia, "engine", banco["dueno"])
    capa = await propia._servicios_propios(lat, lon)
    assert capa["parque"]["dataset"] == "osm" and capa["parque"]["dataset_id"] == "node/7001"
    assert capa["farmacia"]["dataset"] == "overture" and capa["farmacia"]["dataset_id"] == "08f-real-1"
    assert capa["farmacia"]["verificacion_accion"] == "confirmado"
    assert capa["transporte"]["subtipo"] == "metro" and capa["transporte"]["es_masivo"] is True
    assert capa["parque"]["capa_actualizado_en"].startswith("2026-09-22T14:30:03")

    async def _vacio(*a, **k):
        return {}
    monkeypatch.setattr(tools, "_reverse_geocode", _vacio)
    monkeypatch.setattr(rutas, "walk_score_para", _vacio)
    materia = await rutas._recolectar_zona(lat, lon)
    docs = documentos_persistibles(materia, rutas.ensamblar_place_context(materia))
    s, c = docs["servicios"], docs["conectividad"]
    por_id = {e.evidence_id: e for e in s.evidence}
    farmacia = next(i for i in s.items if i.place.category == "farmacia")
    (vid,) = farmacia.verification_evidence_ids
    assert por_id[vid].source_type is SourceType.OPERATOR_DECLARED
    assert por_id[vid].observed_at.isoformat().startswith("2026-09-25T10:00:00")
    assert c.stop.stop.mode == "masivo" and c.walk_duration.value_class.value == "estimated"

    await _aplica(banco["dueno"])
    r = await _intenta(banco["dueno"], "UPDATE public.activos_inmutables SET "
                       "servicios_evidencia = CAST(:s AS jsonb), conectividad_evidencia = CAST(:c AS jsonb) "
                       "WHERE id = :id", s=s.model_dump_json(), c=c.model_dump_json(), id=str(uuid.UUID(int=1)))
    assert r == "ok", r


# ── B9 · COMPUERTA: ningún escritor deja evidencia vieja junto a un texto nuevo ─────
# El UPDATE EXACTO de los escritores que NO saben de la 041. El primero es byte a byte el de
# `_recompute_walk_score` en `main` = c4668d2 (el backend de producción, 1162936) y el de su rama
# «sin la 041» hoy; el segundo, el de `/publish`; el tercero, el de `PATCH /{id}` al reubicar.
UPDATE_W1_LEGADO = ("UPDATE activos_inmutables SET walk_score = :w, walk_score_fuente = :f, "
                    "conectividad = :c, servicios_cercanos = :s WHERE id = :id")
UPDATE_W2_PUBLISH = ("UPDATE activos_inmutables SET owner_user_id = :u, owner_agency_id = :a, "
                     "conectividad = :c WHERE id = :id")


async def _siembra_evidencia(banco, uid):
    docs = _docs_reales()
    r = await _intenta(banco["dueno"], "UPDATE public.activos_inmutables SET "
                       "servicios_cercanos = :ts, conectividad = :tc, "
                       "servicios_evidencia = CAST(:s AS jsonb), conectividad_evidencia = CAST(:c AS jsonb) "
                       "WHERE id = :id", ts="🌳 Texto viejo a ~254 m", tc="🚇 Estación vieja a ~640 m",
                       s=docs["servicios"].model_dump_json(), c=docs["conectividad"].model_dump_json(), id=uid)
    assert r == "ok", r


async def _fila_entorno(banco, uid):
    async with banco["dueno"].connect() as cx:
        return dict((await cx.execute(text(
            "SELECT servicios_cercanos, conectividad, geom::text AS geom, "
            "servicios_evidencia::text AS se, conectividad_evidencia::text AS ce "
            "FROM public.activos_inmutables WHERE id = :id"), {"id": uid})).mappings().one())


def _sin_evidencia_rancia(antes, despues):
    """La invariante: si cambió el texto de una dimensión (o la ubicación), su evidencia no
    puede ser la de antes. Puede ser NULL o un documento NUEVO, nunca el viejo."""
    fallos = []
    se_movio = despues["geom"] != antes["geom"]
    for txt, ev in (("servicios_cercanos", "se"), ("conectividad", "ce")):
        cambio = despues[txt] != antes[txt] or se_movio
        if cambio and antes[ev] is not None and despues[ev] == antes[ev]:
            fallos.append(f"{txt} cambió{' (y la ubicación)' if se_movio else ''} y {ev} conserva el documento anterior")
    return fallos


ESCRITORES_LEGADOS = ["W1 viejo / rama sin la 041", "W2 /publish", "SQL manual o service_role",
                      "PATCH reubica geom"]


@pg
@pytest.mark.parametrize("escritor", ESCRITORES_LEGADOS)
async def test_legacy_writer_cannot_leave_stale_structured_evidence(banco, escritor):
    """COMPUERTA del PROD-APPLY-PREFLIGHT de la 041. Falla si un escritor cambia el texto (o la
    ubicación) de una fila con evidencia y la evidencia anterior sobrevive."""
    await _aplica(banco["dueno"])
    uid = str(uuid.UUID(int=1))
    await _siembra_evidencia(banco, uid)
    antes = await _fila_entorno(banco, uid)
    if escritor == "W1 viejo / rama sin la 041":
        sql, p = UPDATE_W1_LEGADO, dict(w=77, f="osm", c="🚇 Estación nueva ~700 m (9 min a pie)",
                                        s="🌳 Parque nuevo (~300 m)", id=uid)
    elif escritor == "W2 /publish":
        sql, p = UPDATE_W2_PUBLISH, dict(u=str(uuid.uuid4()), a=None, c="🚇 Metro OSM a ~800 m", id=uid)
    elif escritor == "SQL manual o service_role":
        sql, p = "UPDATE public.activos_inmutables SET servicios_cercanos = :s WHERE id = :id", \
            dict(s="texto editado a mano", id=uid)
    else:
        # El UPDATE de `edit_asset` al reubicar (geom + capa base heurística); sin PostGIS, `geom`
        # es texto en el doble y el punto va como un solo parámetro.
        if banco["postgis"]:
            punto, extra = "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)", dict(lon=-78.50, lat=-0.20)
        else:
            punto, extra = ":g", dict(g="POINT(-78.5 -0.2)")
        sql, p = (f"UPDATE activos_inmutables SET direccion_estandarizada = :dir, geom = {punto}, "
                  "walk_score = :ws, walk_score_fuente = 'heuristico' WHERE id = :id",
                  dict(dir="Otra dirección", ws=60, id=uid, **extra))
    assert await _intenta(banco["dueno"], sql, **p) == "ok"
    despues = await _fila_entorno(banco, uid)
    assert not _sin_evidencia_rancia(antes, despues), _sin_evidencia_rancia(antes, despues)


@pg
@pytest.mark.parametrize("caso", ["capa caída → respaldo OSM", "catálogo ilegible → rama sin la 041"])
async def test_legacy_writer_cannot_leave_stale_structured_evidence_W1_real(banco, monkeypatch, caso):
    """La misma compuerta con el escritor REAL (`_recompute_walk_score` de esta rama)."""
    import app.place.persistible as persistible
    import app.routers.assets as assets
    import app.rutas as rutas
    from tests.test_place_provenance_041 import COMPLETA, LAT, LON, _materia
    monkeypatch.setattr(persistible, "_esquema_041_visto", False)
    await _aplica(banco["dueno"])
    uid = str(uuid.UUID(int=1))
    await _siembra_evidencia(banco, uid)
    antes = await _fila_entorno(banco, uid)

    async def _fetch(lat, lon, timeout=None):
        return [{"lat": LAT, "lon": LON, "tags": {"amenity": "pharmacy", "name": "Farmacia OSM"}},
                {"lat": LAT + 0.004, "lon": LON, "tags": {"railway": "station", "name": "Estación OSM"}}]

    async def _recolecta(lat, lon):
        if caso.startswith("capa caída"):
            raise RuntimeError("capa caída")
        return _materia(COMPLETA)

    async def _nada(*a, **k):
        return None

    async def _sin_041(_s):
        return False
    monkeypatch.setattr(assets, "_fetch_pois", _fetch)
    monkeypatch.setattr(rutas, "_recolectar_zona", _recolecta)
    monkeypatch.setattr(assets, "AsyncSessionLocal", banco["Sesion"])
    # RELEASE-ISOLATION-041: este caso describe la 041 ACTIVADA; el flag va encendido.
    monkeypatch.setattr(assets.settings, "place_provenance_041_write_enabled", True)
    monkeypatch.setattr(assets, "ensure_walk_score_fuente_column", _nada)
    if caso.startswith("catálogo"):
        monkeypatch.setattr(assets, "esquema_041_presente", _sin_041)
    await assets._recompute_walk_score(uid, LAT, LON)
    despues = await _fila_entorno(banco, uid)
    assert despues != antes, "el escritor no escribió: la prueba no mediría nada"
    assert not _sin_evidencia_rancia(antes, despues), _sin_evidencia_rancia(antes, despues)


@pg
async def test_W1_escribe_texto_y_evidencia_de_forma_atomica_y_un_fallo_no_deja_mezcla(banco, monkeypatch):
    """§4 del preflight. El escritor nuevo escribe texto y evidencia en UNA sentencia. Si esa
    sentencia falla —aquí, el CHECK real rechaza la evidencia de una dimensión—, no queda ni el
    texto nuevo ni la evidencia nueva de NINGUNA dimensión: la fila sigue exactamente como estaba."""
    import app.place.persistible as persistible
    import app.routers.assets as assets
    import app.rutas as rutas
    from tests.test_place_provenance_041 import COMPLETA, LAT, LON, _materia
    monkeypatch.setattr(persistible, "_esquema_041_visto", False)
    await _aplica(banco["dueno"])
    uid = str(uuid.UUID(int=1))
    await _siembra_evidencia(banco, uid)
    antes = await _fila_entorno(banco, uid)

    async def _fetch(lat, lon, timeout=None):
        return [{"lat": LAT, "lon": LON, "tags": {"amenity": "pharmacy", "name": "Farmacia OSM"}}]

    async def _recolecta(lat, lon):
        return _materia(COMPLETA)

    async def _nada(*a, **k):
        return None
    real = assets.a_json

    def _a_json_roto(doc):   # la conectividad sale con un documento que el CHECK rechaza
        if doc is not None and doc.dimension == "nearest_transit":
            return json.dumps({"contract_version": "place-dimension-evidence/v0", "status": "unknown"})
        return real(doc)
    monkeypatch.setattr(assets, "_fetch_pois", _fetch)
    monkeypatch.setattr(rutas, "_recolectar_zona", _recolecta)
    monkeypatch.setattr(assets, "AsyncSessionLocal", banco["Sesion"])
    # RELEASE-ISOLATION-041: este caso describe la 041 ACTIVADA; el flag va encendido.
    monkeypatch.setattr(assets.settings, "place_provenance_041_write_enabled", True)
    monkeypatch.setattr(assets, "ensure_walk_score_fuente_column", _nada)
    monkeypatch.setattr(assets, "a_json", _a_json_roto)
    await assets._recompute_walk_score(uid, LAT, LON)     # best-effort: traga el error del CHECK
    assert await _fila_entorno(banco, uid) == antes, "un fallo a mitad dejó texto y evidencia mezclados"
    # Y con el documento bueno, la misma llamada deja texto nuevo con evidencia nueva, juntos.
    monkeypatch.setattr(assets, "a_json", real)
    await assets._recompute_walk_score(uid, LAT, LON)
    despues = await _fila_entorno(banco, uid)
    assert despues["servicios_cercanos"] != antes["servicios_cercanos"] and despues["se"] != antes["se"]
    assert despues["conectividad"] != antes["conectividad"] and despues["ce"] != antes["ce"]
    assert not _sin_evidencia_rancia(antes, despues)


# ── B9b · RELEASE-ISOLATION-041: el escenario de Render, en la base real ─────────────
@pg
async def test_con_la_041_aplicada_y_el_flag_apagado_el_escritor_real_no_escribe_evidencia(banco, monkeypatch):
    """Lo que hará `main` en Render: el esquema 041 EXISTE y `PLACE_PROVENANCE_041_WRITE_ENABLED`
    no. El escritor REAL toma el camino previo a la 041.

    1. Sobre una fila SIN evidencia, no escribe evidencia. Es la parte que muerde si alguien quita
       el gate: con él quitado, el escritor deja aquí un documento nuevo.
    2. Sobre una fila CON evidencia, no la deja rancia junto al texto nuevo. Ojo: la sembrada es el
       mismo documento que produciría el escritor, así que esta parte sola NO distingue el gate
       (el trigger anula un documento que no cambia), y por eso va después de la 1."""
    import app.place.persistible as persistible
    import app.routers.assets as assets
    import app.rutas as rutas
    from tests.test_place_provenance_041 import COMPLETA, LAT, LON, _materia
    monkeypatch.setattr(persistible, "_esquema_041_visto", False)
    await _aplica(banco["dueno"])
    uid = str(uuid.UUID(int=1))
    vacia = await _fila_entorno(banco, uid)
    assert vacia["se"] is None and vacia["ce"] is None

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
    assert assets.settings.place_provenance_041_write_enabled is False, "el valor de fábrica, sin tocar"
    # 1 · fila sin evidencia: el escritor escribe el texto y NO escribe evidencia.
    await assets._recompute_walk_score(uid, LAT, LON)
    tras_1 = await _fila_entorno(banco, uid)
    assert tras_1["servicios_cercanos"] != vacia["servicios_cercanos"], "el escritor no escribió"
    assert tras_1["se"] is None and tras_1["ce"] is None, "con el flag apagado no se escribe evidencia"
    # 2 · fila con evidencia: no queda rancia junto al texto nuevo.
    await _siembra_evidencia(banco, uid)
    antes = await _fila_entorno(banco, uid)
    assert antes["se"] is not None and antes["ce"] is not None
    await assets._recompute_walk_score(uid, LAT, LON)
    despues = await _fila_entorno(banco, uid)
    assert despues["servicios_cercanos"] != antes["servicios_cercanos"], "el escritor no escribió"
    assert despues["se"] is None and despues["ce"] is None
    assert not _sin_evidencia_rancia(antes, despues)
    async with banco["Sesion"]() as s:
        assert await persistible.esquema_041_presente(s), "la prueba exige la 041 aplicada"


# ── B8 · CONTROLES NEGATIVOS: quitar una guarda material pone esto en rojo ─────────
def _mutante(de: str, a: str) -> str:
    sql = M041.read_text(encoding="utf-8")
    assert de in sql, f"la mutación no encuentra su objetivo: {de[:60]}"
    return sql.replace(de, a, 1)


async def _acepta_runtime_only(banco):
    d = _mutar(_docs_reales()["servicios"].model_dump_json(),
               lambda x: x["evidence"][0].update(persistence_policy="runtime_only"))
    return await _intenta(banco["dueno"], "UPDATE public.activos_inmutables SET servicios_evidencia = "
                          "CAST(:v AS jsonb) WHERE id = :id", v=d, id=str(uuid.UUID(int=1))) == "ok"


async def _acepta_unknown(banco):
    d = _mutar(_docs_reales()["servicios"].model_dump_json(), lambda x: x.update(status="unknown", items=[]))
    return await _intenta(banco["dueno"], "UPDATE public.activos_inmutables SET servicios_evidencia = "
                          "CAST(:v AS jsonb) WHERE id = :id", v=d, id=str(uuid.UUID(int=1))) == "ok"


async def _acepta_sin_fecha(banco):
    d = _mutar(_docs_reales()["servicios"].model_dump_json(), lambda x: x.pop("derived_at"))
    return await _intenta(banco["dueno"], "UPDATE public.activos_inmutables SET servicios_evidencia = "
                          "CAST(:v AS jsonb) WHERE id = :id", v=d, id=str(uuid.UUID(int=1))) == "ok"


async def _deja_rancia_al_reubicar(banco):
    uid = str(uuid.UUID(int=1))
    await _siembra_evidencia(banco, uid)
    antes = await _fila_entorno(banco, uid)
    lon = -78.5 - (uuid.uuid4().int % 100000) / 1e7   # un punto NUEVO en cada pasada
    punto = (f"ST_SetSRID(ST_MakePoint({lon}, -0.2), 4326)" if banco["postgis"] else f"'POINT({lon} -0.2)'")
    await _intenta(banco["dueno"], f"UPDATE activos_inmutables SET geom = {punto} WHERE id = :id", id=uid)
    return bool(_sin_evidencia_rancia(antes, await _fila_entorno(banco, uid)))


async def _acepta_recta_como_ruta(banco):
    d = _mutar(_docs_reales()["conectividad"].model_dump_json(),
               lambda x: x["walk_duration"].update(value_class="derived"))
    return await _intenta(banco["dueno"], "UPDATE public.activos_inmutables SET conectividad_evidencia = "
                          "CAST(:v AS jsonb) WHERE id = :id", v=d, id=str(uuid.UUID(int=1))) == "ok"


MUTACIONES = {
    "sin la guarda de persistable": (
        "            AND NOT jsonb_path_exists(servicios_evidencia,\n"
        "                    '$.evidence[*] ? (@.persistence_policy != \"persistable\")')\n", "",
        _acepta_runtime_only, "aplica"),
    "sin el vocabulario de estado": (
        "            AND servicios_evidencia->>'status' IN ('available', 'insufficient_evidence')\n", "",
        _acepta_unknown, "aplica"),
    "sin la regla recta ≠ ruta": (
        "            AND NOT jsonb_path_exists(conectividad_evidencia,\n"
        "                    '$.walk_duration ? (@.method == \"straight_line_at_fixed_pace\" && @.value_class != \"estimated\")')\n",
        "", _acepta_recta_como_ruta, "aplica"),
    "sin el coalesce del CHECK (NULL pasa)": (
        "        ), false));", "        ), true));", _acepta_sin_fecha, "aplica"),
    "el trigger sin la rama de la ubicación": (
        "        IF NEW.geom IS DISTINCT FROM OLD.geom THEN\n"
        "            IF NEW.servicios_evidencia IS NOT DISTINCT FROM OLD.servicios_evidencia THEN\n"
        "                NEW.servicios_evidencia := NULL;\n"
        "            END IF;\n"
        "            IF NEW.conectividad_evidencia IS NOT DISTINCT FROM OLD.conectividad_evidencia THEN\n"
        "                NEW.conectividad_evidencia := NULL;\n"
        "            END IF;\n"
        "        END IF;\n", "", _deja_rancia_al_reubicar, "aplica"),
    "sin el CREATE TRIGGER": (
        "    CREATE TRIGGER trg_activos_invalida_evidencia_desfasada\n"
        "        BEFORE UPDATE OF servicios_cercanos, conectividad, geom ON public.activos_inmutables\n"
        "        FOR EACH ROW EXECUTE FUNCTION public.activos_invalida_evidencia_desfasada();\n", "",
        None, "default"),
    "sin la compuerta de contexto_procedencia": (
        "    IF EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = tabla AND NOT attisdropped\n"
        "                 AND attname = 'contexto_procedencia') THEN", "    IF false THEN",
        None, "etiqueta"),
    "con DEFAULT en una columna": (
        "ADD COLUMN servicios_evidencia jsonb;", "ADD COLUMN servicios_evidencia jsonb DEFAULT '{}'::jsonb;",
        None, "default"),
}


@pg
@pytest.mark.parametrize("nombre", sorted(MUTACIONES))
async def test_quitar_una_guarda_de_la_041_se_detecta(banco, nombre):
    de, a, sonda, tipo = MUTACIONES[nombre]
    if tipo == "aplica":
        # Con la 041 REAL la sonda es rechazada; con la mutante, aceptada → la prueba la ve.
        await _aplica(banco["dueno"])
        assert not await sonda(banco), "control: la 041 real rechaza el estado"
        await _aplica(banco["dueno"], _rollback(M041.read_text(encoding="utf-8")))
        await _aplica(banco["dueno"], _mutante(de, a))
        assert await sonda(banco), f"la mutación «{nombre}» debería dejar pasar el estado"
    elif tipo == "etiqueta":
        await _intenta(banco["dueno"], AJENOS["la etiqueta descartada"])
        await _aplica(banco["dueno"], _mutante(de, a))   # la mutante NO aborta
        cat = await _catalogo(banco["dueno"])
        assert {"contexto_procedencia", *COLS} <= {c[0] for c in cat["columnas"]}
    else:
        # Con DEFAULT, las filas legado nacerían con «evidencia»: la 041 se niega a confirmar
        # (el propio CHECK o su verificación interna) y no deja nada a medias.
        antes = await _catalogo(banco["dueno"])
        with pytest.raises(Exception):
            await _aplica(banco["dueno"], _mutante(de, a))
        assert await _catalogo(banco["dueno"]) == antes
