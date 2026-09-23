# -*- coding: utf-8 -*-
"""PUBLIC-DB-P0-CLOSEOUT-R1 · banco aislado para las migraciones 035 y 036.

    python tests/arnes_perimetro_035.py
    PERIM_CONTENEDOR=perim-pg15 PERIM_PUERTO=55451 python tests/arnes_perimetro_035.py

## LA PRUEBA QUE JUSTIFICA LA 035

No es «anon puede leer una tabla de versiones». Es esto, y se ejecuta de verdad:

    B) se vacia `checkpoint_migrations` ANTES de la 035
       -> AsyncPostgresSaver.setup() recorre las migraciones desde 0
       -> la 9 es `ALTER TABLE checkpoint_writes ADD COLUMN task_path ...` SIN `IF NOT EXISTS`
       -> ERROR: column "task_path" ... already exists
       -> y como setup() corre en el `lifespan`, el backend NO ARRANCA

    C) con la 035 aplicada, `anon` ya no puede vaciarla -> setup() PASS

El control destructivo (B) **solo se ejecuta en este banco**. Nunca contra produccion.

## FIDELIDAD

Igual que el arnes de la 033: el dueno es `contexto_owner` (NOSUPERUSER + BYPASSRLS), no el
superusuario del contenedor, porque un superusuario se salta todo trivialmente. Y las tablas las
crea el `AsyncPostgresSaver` REAL de la version pineada, no un doble.

## NO SE LEE CONTENIDO

El banco escribe y lee datos sinteticos suyos. Sobre produccion, nada.
"""
from __future__ import annotations

import ast
import asyncio
import os
import pathlib
import subprocess
import sys

CONTENEDOR = os.environ.get("PERIM_CONTENEDOR", "perim-pg")
PUERTO = os.environ.get("PERIM_PUERTO", "55450")
RAIZ = pathlib.Path(__file__).resolve().parent.parent
MIGRACIONES = RAIZ / "migrations"
BANCO = "banco_p0c"
URL = f"postgresql://contexto_owner:perim@localhost:{PUERTO}/{BANCO}?sslmode=disable"

ROJO, VERDE, GRIS, FIN = "\033[31m", "\033[32m", "\033[90m", "\033[0m"

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def psql(sql, rol=None, db=BANCO):
    if rol:
        sql = f"SET ROLE {rol};\n{sql}"
    p = subprocess.run(
        ["docker", "exec", "-i", CONTENEDOR, "psql", "-U", "postgres", "-d", db, "-q", "-t", "-A"],
        input=sql, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def sql_texto(texto, db=BANCO, detener=True, rol=None):
    if rol:
        texto = "SET ROLE " + rol + ";\n" + texto
    p = subprocess.run(
        ["docker", "exec", "-i", CONTENEDOR, "psql", "-U", "postgres", "-d", db, "-q"]
        + (["-v", "ON_ERROR_STOP=1"] if detener else []),
        input=texto, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def archivo(nombre, rol="contexto_owner", texto=None):
    cuerpo = texto if texto is not None else (MIGRACIONES / nombre).read_text(encoding="utf-8")
    return sql_texto(cuerpo, rol=rol)


class Suite:
    def __init__(self, t):
        self.titulo, self.fallos, self.total = t, [], 0

    def afirma(self, nombre, cond, detalle=""):
        self.total += 1
        if cond:
            print(f"  {VERDE}PASS{FIN}  {nombre}")
        else:
            self.fallos.append(nombre)
            print(f"  {ROJO}FALLA{FIN} {nombre}" + (f"\n         {GRIS}{detalle}{FIN}" if detalle else ""))

    @property
    def verde(self):
        return not self.fallos


def titulo(t):
    print(f"\n{'=' * 80}\n{t}\n{'=' * 80}")


def ve_filas(tabla, rol):
    rc, out = psql(f"SELECT count(*) FROM public.{tabla};", rol)
    if "ERROR" in out or "permission denied" in out:
        return -1
    try:
        return int(out.strip().splitlines()[0])
    except (ValueError, IndexError):
        return -2


def puede(op, rol):
    rc, out = psql(op, rol)
    return "permission denied" not in out and "ERROR" not in out


def handoff_ddl_del_repo():
    """Lee `_HANDOFF_DDL` de app/routers/chat.py por AST, sin importar el modulo.

    Por AST y no por copia: una copia seria un doble que deriva en silencio en cuanto alguien
    anada una sentencia. Sin importar, porque `app.config` exige variables de entorno al
    importarse y este arnes no las tiene ni las quiere.
    """
    arbol = ast.parse((RAIZ / "app" / "routers" / "chat.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_HANDOFF_DDL" for t in nodo.targets):
            return [ast.literal_eval(e) for e in nodo.value.elts]
    raise SystemExit("no se encontro _HANDOFF_DDL en app/routers/chat.py")


POSTURA = """
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon')           THEN CREATE ROLE anon NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated')  THEN CREATE ROLE authenticated NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role')   THEN CREATE ROLE service_role NOLOGIN BYPASSRLS; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='contexto_owner') THEN
      CREATE ROLE contexto_owner LOGIN PASSWORD 'perim' NOSUPERUSER BYPASSRLS CREATEDB; END IF;
END $$;
GRANT anon, authenticated, service_role, contexto_owner TO postgres;
ALTER DATABASE banco_p0c OWNER TO contexto_owner;
ALTER SCHEMA public OWNER TO contexto_owner;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
-- LA CAUSA RAIZ, las dos mitades: tablas (ya cerrada por la 034) y SECUENCIAS (esta unidad).
ALTER DEFAULT PRIVILEGES FOR ROLE contexto_owner IN SCHEMA public GRANT ALL ON TABLES    TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE contexto_owner IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
SET ROLE contexto_owner;
CREATE TABLE IF NOT EXISTS public.vecina (id serial PRIMARY KEY, nota text);
INSERT INTO public.vecina (nota) VALUES ('v1'),('v2');
RESET ROLE;
"""


async def escribe(hilo, n=3):
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.checkpoint.base import empty_checkpoint, create_checkpoint
    async with AsyncPostgresSaver.from_conn_string(URL) as cp:
        await cp.setup()
        cfg = {"configurable": {"thread_id": hilo, "checkpoint_ns": ""}}
        ck = empty_checkpoint()
        for i in range(n):
            v = f"{i + 1:032d}.0"
            ck = {**ck, "channel_values": {"m": [f"sintetico {i}"]},
                  "channel_versions": {**ck.get("channel_versions", {}), "m": v}}
            cfg = await cp.aput(cfg, ck, {"source": "banco", "step": i, "writes": {}}, {"m": v})
            await cp.aput_writes(cfg, [("c", {"i": i})], f"t-{i}")
            ck = create_checkpoint(ck, {}, i)
    return n


async def solo_setup():
    """Lo que hace el lifespan al arrancar. Devuelve (ok, mensaje)."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    try:
        async with AsyncPostgresSaver.from_conn_string(URL) as cp:
            await cp.setup()
        return True, "setup() OK"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e).splitlines()[0][:120]}"


def monta_banco(con_033=True):
    sql_texto("DROP DATABASE IF EXISTS banco_p0c;", db="postgres")
    sql_texto("CREATE DATABASE banco_p0c;", db="postgres")
    rc, out = sql_texto(POSTURA)
    assert rc == 0, out
    asyncio.run(escribe("hilo-semilla", 3))
    # Las tablas de handoff las crea el codigo en caliente, no un fichero de migrations/.
    # Se usan las sentencias REALES del repo para que el banco no sea un doble.
    rc, out = sql_texto("SET ROLE contexto_owner;\n" + ";\n".join(handoff_ddl_del_repo()) + ";")
    assert rc == 0, f"el _HANDOFF_DDL real fallo:\n{out[-400:]}"
    if con_033:
        # El estado de produccion HOY: la 033 ya esta aplicada sobre las cinco.
        rc, out = archivo("033_conversaciones_y_handoff_perimetro.sql")
        assert rc == 0, f"la 033 no aplico en el banco (¿faltan las tablas de handoff?):\n{out[-400:]}"


def nace_expuesta_secuencia():
    psql("DROP SEQUENCE IF EXISTS public.sonda_seq;", "contexto_owner")
    psql("CREATE SEQUENCE public.sonda_seq;", "contexto_owner")
    rc, out = psql("""SELECT coalesce(string_agg(DISTINCT pg_get_userbyid(a.grantee),','),'')
                        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace, aclexplode(c.relacl) a
                       WHERE n.nspname='public' AND c.relname='sonda_seq'
                         AND pg_get_userbyid(a.grantee) IN ('anon','authenticated','service_role');""")
    expuesta = bool(out.strip())
    psql("DROP SEQUENCE IF EXISTS public.sonda_seq;", "contexto_owner")
    return expuesta


# ══ 1 · CONTROL POSITIVO ════════════════════════════════════════════════════════════════
def control_positivo():
    titulo("1 · CONTROL POSITIVO — el banco tiene que reproducir lo que falta por cerrar")
    s = Suite("control positivo")
    s.afirma("anon LEE checkpoint_migrations", ve_filas("checkpoint_migrations", "anon") > 0)
    s.afirma("anon puede VACIAR checkpoint_migrations",
             puede("DELETE FROM public.checkpoint_migrations;", "anon"))
    # se repone para lo que viene
    sql_texto("SET ROLE contexto_owner;\nINSERT INTO public.checkpoint_migrations (v) "
              "SELECT generate_series(0,9) ON CONFLICT DO NOTHING;")
    s.afirma("una SECUENCIA nueva nace expuesta (la causa raiz que queda)",
             nace_expuesta_secuencia())
    s.afirma("y las cinco de la 033 siguen cerradas (el banco parte del estado de hoy)",
             ve_filas("checkpoint_blobs", "anon") == -1)
    return s


# ══ 2 · LA PRUEBA DECISIVA ══════════════════════════════════════════════════════════════
def prueba_decisiva(s):
    titulo("2 · PRUEBA DECISIVA — ¿de verdad tumba el arranque?")
    print("  Control destructivo. SOLO en este banco, jamas contra produccion.\n")

    ok, msg = asyncio.run(solo_setup())
    s.afirma("A · setup() con la tabla intacta y la version vigente -> PASS", ok, msg)

    print(f"\n{GRIS}  B · se vacia checkpoint_migrations ANTES de la 035{FIN}")
    monta_banco()
    n = ve_filas("checkpoint_migrations", "contexto_owner")
    borro = puede("DELETE FROM public.checkpoint_migrations;", "anon")
    ok, msg = asyncio.run(solo_setup())
    s.afirma("B · `anon` la vacia y setup() FALLA — el backend no arrancaria",
             borro and not ok and "already exists" in msg,
             f"borro={borro} setup_ok={ok} -> {msg}")
    print(f"       {GRIS}(tenia {n} filas · el fallo reproducido es: {msg}){FIN}")

    print(f"\n{GRIS}  C · con la 035 aplicada, ese vaciado ya no puede ocurrir{FIN}")
    monta_banco()
    rc, out = archivo("035_checkpoint_migrations_perimetro.sql")
    assert rc == 0, out[-400:]
    borro = puede("DELETE FROM public.checkpoint_migrations;", "anon")
    trunco = puede("TRUNCATE public.checkpoint_migrations;", "anon")
    s.afirma("C · `anon` ya no puede vaciarla (ni DELETE ni TRUNCATE)", not borro and not trunco,
             f"delete={borro} truncate={trunco}")
    ok, msg = asyncio.run(solo_setup())
    s.afirma("C · y setup() sigue PASS con RLS activo", ok, msg)


# ══ 3 · DESPUES DE LA 035 ═══════════════════════════════════════════════════════════════
def suite_035():
    titulo("3 · DESPUES DE LA 035")
    s = Suite("perimetro 035")
    for rol in ("anon", "authenticated", "service_role"):
        s.afirma(f"{rol} NO lee checkpoint_migrations",
                 ve_filas("checkpoint_migrations", rol) == -1,
                 f"devolvio {ve_filas('checkpoint_migrations', rol)}")
        s.afirma(f"{rol} NO puede truncarla",
                 not puede("TRUNCATE public.checkpoint_migrations;", rol))
        s.afirma(f"{rol} NO puede insertar una version falsa",
                 not puede("INSERT INTO public.checkpoint_migrations (v) VALUES (99);", rol))
    rc, out = psql("""SELECT relrowsecurity, relforcerowsecurity,
                             (SELECT count(*) FROM pg_policies WHERE schemaname='public'
                               AND tablename='checkpoint_migrations')
                        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                       WHERE n.nspname='public' AND c.relname='checkpoint_migrations';""")
    s.afirma("rls=true, force=false, politicas=0", out.strip().startswith("t|f|0"), out.strip())
    s.afirma("el DUENO sigue leyendola", ve_filas("checkpoint_migrations", "contexto_owner") > 0)
    s.afirma("la vecina no se toco", ve_filas("vecina", "anon") == 2)
    s.afirma("la 035 es idempotente", archivo("035_checkpoint_migrations_perimetro.sql")[0] == 0)
    return s


# ══ 4 · LA 036 ══════════════════════════════════════════════════════════════════════════
def suite_036():
    titulo("4 · DESPUES DE LA 036 — el default de SECUENCIAS")
    s = Suite("causa raiz 036")
    acl_previa = psql("SELECT relacl::text FROM pg_class WHERE relname='vecina_id_seq';")[1].strip()
    rc, out = archivo("036_default_privileges_secuencias.sql")
    s.afirma("la 036 aplica", rc == 0, out.strip()[-320:])
    s.afirma("una SECUENCIA nueva ya NO nace expuesta", not nace_expuesta_secuencia())

    # la sonda viva, por fuera de la migracion
    psql("CREATE SEQUENCE public.sonda_viva;", "contexto_owner")
    for op, sql in (("last_value", "SELECT last_value FROM public.sonda_viva;"),
                    ("setval", "SELECT setval('public.sonda_viva', 99, false);"),
                    ("nextval", "SELECT nextval('public.sonda_viva');")):
        s.afirma(f"anon recibe permission denied en {op}", not puede(sql, "anon"))
    s.afirma("el DUENO sigue pudiendo nextval", puede("SELECT nextval('public.sonda_viva');", "contexto_owner"))
    psql("DROP SEQUENCE public.sonda_viva;", "contexto_owner")

    acl_post = psql("SELECT relacl::text FROM pg_class WHERE relname='vecina_id_seq';")[1].strip()
    s.afirma("NO cambio el acl de una secuencia que ya existia", acl_previa == acl_post,
             f"{acl_previa} -> {acl_post}")
    s.afirma("la 036 es idempotente", archivo("036_default_privileges_secuencias.sql")[0] == 0)
    s.afirma("no quedan objetos de la sonda", psql(
        "SELECT count(*) FROM pg_class WHERE relname LIKE '_036_sonda%';")[1].strip() == "0")
    return s


# ══ 5 · MUTACIONES ══════════════════════════════════════════════════════════════════════
def mutaciones():
    titulo("5 · MUTACIONES — la prueba tiene que ponerse ROJA")
    s = Suite("mutaciones")
    m035 = (MIGRACIONES / "035_checkpoint_migrations_perimetro.sql").read_text(encoding="utf-8")
    m036 = (MIGRACIONES / "036_default_privileges_secuencias.sql").read_text(encoding="utf-8")

    print(f"\n{GRIS}  M1 · se quita ENABLE ROW LEVEL SECURITY de la 035{FIN}")
    monta_banco()
    mut = m035.replace("ALTER TABLE public.checkpoint_migrations ENABLE ROW LEVEL SECURITY;\n", "")
    assert mut != m035, "M1 no encontro el ENABLE RLS"
    rc, out = archivo("", texto=mut)
    s.afirma("M1 · sin RLS la 035 ABORTA", rc != 0 and "RLS no quedó activado" in out, out[-200:])

    print(f"\n{GRIS}  M2 · se neutraliza el REVOKE de la 035{FIN}")
    monta_banco()
    mut = m035.replace("'REVOKE ALL PRIVILEGES ON TABLE public.checkpoint_migrations FROM %I'",
                       "'SELECT 1 /* M2 */ -- %I'")
    assert mut != m035, "M2 no encontro el REVOKE"
    rc, out = archivo("", texto=mut)
    s.afirma("M2 · sin REVOKE la 035 ABORTA", rc != 0 and "quedan privilegios en pie" in out, out[-200:])

    print(f"\n{GRIS}  M3 · se devuelve TRUNCATE a anon tras la 035{FIN}")
    monta_banco()
    assert archivo("035_checkpoint_migrations_perimetro.sql")[0] == 0
    psql("GRANT TRUNCATE ON public.checkpoint_migrations TO anon;", "contexto_owner")
    s.afirma("M3 · con TRUNCATE devuelto, anon vuelve a poder vaciarla",
             puede("TRUNCATE public.checkpoint_migrations;", "anon"))

    print(f"\n{GRIS}  M4 · el control destructivo, otra vez, como mutacion explicita{FIN}")
    monta_banco()
    psql("DELETE FROM public.checkpoint_migrations;", "contexto_owner")
    ok, msg = asyncio.run(solo_setup())
    s.afirma("M4 · con la tabla vacia, setup() falla y reproduce el fallo medido",
             not ok and "already exists" in msg, msg)

    print(f"\n{GRIS}  M5 · se deja el default GLOBAL de secuencias{FIN}")
    monta_banco()
    mut = m036.replace(
        "'ALTER DEFAULT PRIVILEGES REVOKE ALL ON SEQUENCES FROM %I'",
        "'SELECT 1 /* M5: se omite el global */ -- %I'")
    assert mut != m036, "M5 no encontro el REVOKE global"
    psql("ALTER DEFAULT PRIVILEGES GRANT ALL ON SEQUENCES TO anon;", "contexto_owner")
    rc, out = archivo("", texto=mut)
    s.afirma("M5 · sin el REVOKE global, la 036 ABORTA (o la secuencia nace abierta)",
             rc != 0 and ("todavía concede" in out or "SIGUE naciendo" in out or "pudo tocar" in out),
             out[-260:])

    print(f"\n{GRIS}  M6 · se deja el default de PUBLIC{FIN}")
    monta_banco()
    mut = m036.replace(
        "'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I'",
        "'SELECT 1 /* M6: se omite el de public */ -- %I'")
    assert mut != m036, "M6 no encontro el REVOKE de public"
    rc, out = archivo("", texto=mut)
    s.afirma("M6 · sin el REVOKE de public, la 036 ABORTA",
             rc != 0 and ("todavía concede" in out or "SIGUE naciendo" in out or "pudo tocar" in out),
             out[-260:])

    print(f"\n{GRIS}  M7 · se permite setval a anon tras la 036{FIN}")
    monta_banco()
    assert archivo("036_default_privileges_secuencias.sql")[0] == 0
    psql("CREATE SEQUENCE public.m7_seq;", "contexto_owner")
    antes = puede("SELECT setval('public.m7_seq', 5, false);", "anon")
    psql("GRANT ALL ON SEQUENCE public.m7_seq TO anon;", "contexto_owner")
    despues = puede("SELECT setval('public.m7_seq', 5, false);", "anon")
    s.afirma("M7 · devolver el grant a anon reabre el setval", (not antes) and despues,
             f"antes={antes} despues={despues}")
    psql("DROP SEQUENCE public.m7_seq;", "contexto_owner")

    print(f"\n{GRIS}  M8 · la verificacion con INNER JOIN pierde defaclnamespace=0{FIN}")
    monta_banco()
    assert archivo("036_default_privileges_secuencias.sql")[0] == 0
    psql("ALTER DEFAULT PRIVILEGES GRANT ALL ON SEQUENCES TO anon;", "contexto_owner")
    vieja = psql("""SELECT count(*) FROM pg_default_acl d
                      JOIN pg_namespace n ON n.oid=d.defaclnamespace, aclexplode(d.defaclacl) a
                     WHERE n.nspname='public' AND d.defaclobjtype='S'
                       AND pg_get_userbyid(a.grantee)='anon';""")[1].strip()
    nueva = psql("""SELECT count(*) FROM pg_default_acl d
                      LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace, aclexplode(d.defaclacl) a
                     WHERE (d.defaclnamespace=0 OR n.nspname='public') AND d.defaclobjtype='S'
                       AND pg_get_userbyid(a.grantee)='anon';""")[1].strip()
    s.afirma("M8 · con el default global vivo, una secuencia nueva SI nace expuesta",
             nace_expuesta_secuencia())
    s.afirma("M8a · la consulta VIEJA (INNER JOIN) no lo ve -> seria fail-OPEN", vieja == "0", vieja)
    s.afirma("M8b · la consulta de la 036 (LEFT JOIN) SI lo ve", nueva != "0", nueva)
    rc, out = archivo("036_default_privileges_secuencias.sql")
    s.afirma("M8c · y la 036 re-aplicada lo limpia o ABORTA, nunca da verde en falso",
             rc == 0 and not nace_expuesta_secuencia(), out[-200:])
    return s


def main():
    for m in ("035_checkpoint_migrations_perimetro.sql", "036_default_privileges_secuencias.sql"):
        if not (MIGRACIONES / m).exists():
            print(f"{ROJO}falta {m}{FIN}")
            return 2

    titulo(f"0 · BANCO — {CONTENEDOR}:{PUERTO}, partiendo del estado de produccion (033 aplicada)")
    monta_banco()
    print("  " + psql("SELECT version();")[1].strip()[:70])

    s1 = control_positivo()
    if not s1.verde:
        print(f"\n{ROJO}EL CONTROL POSITIVO NO SE REPRODUJO.{FIN}")
        return 1
    prueba_decisiva(s1)

    monta_banco()
    titulo("· se aplica la 035 ·")
    rc, out = archivo("035_checkpoint_migrations_perimetro.sql")
    print(out.strip()[-360:])
    if rc != 0:
        return 1
    s2 = suite_035()

    ok, msg = asyncio.run(solo_setup())
    s2.afirma("el checkpointer real sigue arrancando tras la 035", ok, msg)
    n = asyncio.run(escribe("hilo-tras-035", 3))
    s2.afirma("y sigue escribiendo", n == 3)

    s3 = suite_036()
    s4 = mutaciones()

    titulo("RESUMEN")
    for s in (s1, s2, s3, s4):
        marca = f"{VERDE}VERDE{FIN}" if s.verde else f"{ROJO}ROJA ({len(s.fallos)}){FIN}"
        print(f"  {s.titulo:20} {s.total:3} comprobaciones  {marca}")
        for f in s.fallos:
            print(f"        - {f}")
    return 0 if all(s.verde for s in (s1, s2, s3, s4)) else 1


if __name__ == "__main__":
    sys.exit(main())
