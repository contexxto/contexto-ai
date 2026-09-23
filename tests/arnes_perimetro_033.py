# -*- coding: utf-8 -*-
"""PUBLIC-DB-PERIMETER-INCIDENT-R1 · banco aislado para las migraciones 033 y 034.

No es una prueba de pytest: es un arnés que necesita Docker y las dependencias del proyecto
(langgraph-checkpoint-postgres). Se corre a mano:

    python tests/arnes_perimetro_033.py
    PERIM_CONTENEDOR=perim-pg15 PERIM_PUERTO=55451 python tests/arnes_perimetro_033.py

## LO QUE HACE DISTINTO A `arnes_perimetro_032.py`

Aquel banco creaba las tablas del Buyer Store aplicando su propia migración. Aquí no se puede:
**estas cinco tablas no las crea ningún fichero de `migrations/`**, las crea el código en
caliente. Así que el banco usa las mismas dos fuentes que producción, sin copiarlas:

  * `AsyncPostgresSaver.setup()` de LangGraph — el checkpointer de verdad, la misma versión
    que corre en el servidor.
  * `_HANDOFF_DDL`, leído del propio `app/routers/chat.py` por AST. Si alguien cambia esa
    lista, este arnés cambia con ella; copiarla habría creado un doble que deriva en silencio.

Eso convierte el control positivo en algo más fuerte que una reproducción: es una
**demostración causal de la causa raíz**. Se deja que la librería cree sus tablas contra una
base con los privilegios por defecto de Supabase, y salen expuestas sin que su DDL mencione ni
un `GRANT`.

## FIDELIDAD

En producción el backend conecta con un rol llamado `postgres` que **no es superusuario**: es
dueño de las tablas y tiene `rolbypassrls`. El `postgres` de un contenedor limpio sí es
superusuario, y un superusuario se salta todo trivialmente — probar contra él demostraría que
el cambio no rompe nada, pero por la razón equivocada. El banco crea `contexto_owner`
(NOSUPERUSER, BYPASSRLS, dueño) y todo lo productivo corre como él.

## NO SE LEE CONTENIDO

Ni aquí ni en producción. El banco escribe y lee datos SINTÉTICOS suyos; sobre producción, la
única consulta que toca estas tablas es `count(*)`.
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
BANCO = "banco_p0"
URL_OWNER = f"postgresql://contexto_owner:perim@localhost:{PUERTO}/{BANCO}?sslmode=disable"

CINCO = ["checkpoints", "checkpoint_blobs", "checkpoint_writes",
         "handoff_sesion", "handoff_mensaje"]
ROJO, VERDE, GRIS, FIN = "\033[31m", "\033[32m", "\033[90m", "\033[0m"

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# ══ plomería ════════════════════════════════════════════════════════════════════════════
def psql(sql: str, rol: str | None = None, db: str = BANCO, detener: bool = False) -> tuple[int, str]:
    if rol:
        sql = f"SET ROLE {rol};\n{sql}"
    p = subprocess.run(
        ["docker", "exec", "-i", CONTENEDOR, "psql", "-U", "postgres", "-d", db, "-q", "-t", "-A"]
        + (["-v", "ON_ERROR_STOP=1"] if detener else []),
        input=sql, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def sql_texto(texto: str, db: str = BANCO, detener: bool = True, rol: str | None = None):
    if rol:
        texto = "SET ROLE " + rol + ";\n" + texto
    p = subprocess.run(
        ["docker", "exec", "-i", CONTENEDOR, "psql", "-U", "postgres", "-d", db, "-q"]
        + (["-v", "ON_ERROR_STOP=1"] if detener else []),
        input=texto, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def archivo(nombre: str, rol: str | None = "contexto_owner", texto: str | None = None):
    cuerpo = texto if texto is not None else (MIGRACIONES / nombre).read_text(encoding="utf-8")
    return sql_texto(cuerpo, rol=rol)


class Suite:
    def __init__(self, titulo: str):
        self.titulo, self.fallos, self.total = titulo, [], 0

    def afirma(self, nombre: str, cond: bool, detalle: str = "") -> None:
        self.total += 1
        if cond:
            print(f"  {VERDE}PASS{FIN}  {nombre}")
        else:
            self.fallos.append(nombre)
            print(f"  {ROJO}FALLA{FIN} {nombre}" + (f"\n         {GRIS}{detalle}{FIN}" if detalle else ""))

    @property
    def verde(self) -> bool:
        return not self.fallos


def titulo(t: str) -> None:
    print(f"\n{'=' * 80}\n{t}\n{'=' * 80}")


def ve_filas(tabla: str, rol: str) -> int:
    """−1 = permiso denegado (el GRANT lo corta) · 0 = RLS filtró pero el grant sigue."""
    rc, out = psql(f"SELECT count(*) FROM public.{tabla};", rol)
    if "ERROR" in out or "permission denied" in out:
        return -1
    try:
        return int(out.strip().splitlines()[0])
    except (ValueError, IndexError):
        return -2


def puede(op: str, rol: str) -> bool:
    rc, out = psql(op, rol)
    return "permission denied" not in out and "ERROR" not in out


# ══ el DDL REAL del repo, leído por AST ═════════════════════════════════════════════════
def handoff_ddl_del_repo() -> list[str]:
    """Extrae `_HANDOFF_DDL` de app/routers/chat.py sin importar el módulo.

    Por AST y no por copia: una copia sería un doble que deriva en silencio en cuanto alguien
    añada una sentencia. Y sin importar el módulo porque `app.config` exige variables de
    entorno al importarse, y este arnés no las tiene ni las quiere.
    """
    arbol = ast.parse((RAIZ / "app" / "routers" / "chat.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_HANDOFF_DDL" for t in nodo.targets):
            return [ast.literal_eval(e) for e in nodo.value.elts]
    raise SystemExit("no se encontró _HANDOFF_DDL en app/routers/chat.py")


POSTURA = """
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon')           THEN CREATE ROLE anon NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated')  THEN CREATE ROLE authenticated NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role')   THEN CREATE ROLE service_role NOLOGIN BYPASSRLS; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='contexto_owner') THEN
      CREATE ROLE contexto_owner LOGIN PASSWORD 'perim' NOSUPERUSER BYPASSRLS CREATEDB; END IF;
END $$;
GRANT anon, authenticated, service_role, contexto_owner TO postgres;
ALTER DATABASE banco_p0 OWNER TO contexto_owner;
ALTER SCHEMA public OWNER TO contexto_owner;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
-- LA CAUSA RAIZ, tal cual se midio en produccion el 2026-09-23.
ALTER DEFAULT PRIVILEGES FOR ROLE contexto_owner IN SCHEMA public GRANT ALL ON TABLES    TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE contexto_owner IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
-- Vecinas, para probar que las migraciones no tocan nada mas.
SET ROLE contexto_owner;
CREATE TABLE IF NOT EXISTS public.vecina_sin_rls (id serial PRIMARY KEY, nota text);
INSERT INTO public.vecina_sin_rls (nota) VALUES ('v1'),('v2'),('v3');
CREATE TABLE IF NOT EXISTS public.vecina_con_rls (id serial PRIMARY KEY, nota text);
INSERT INTO public.vecina_con_rls (nota) VALUES ('r1'),('r2');
ALTER TABLE public.vecina_con_rls ENABLE ROW LEVEL SECURITY;
RESET ROLE;
"""

SEMILLA_HANDOFF = """
SET ROLE contexto_owner;
INSERT INTO public.handoff_sesion (session_id, activo_id, estado, lead_email)
VALUES ('s-banco-1', gen_random_uuid(), 'solicitado', 'sintetico@ejemplo.invalid')
ON CONFLICT DO NOTHING;
INSERT INTO public.handoff_mensaje (session_id, autor, texto)
VALUES ('s-banco-1','usuario','mensaje sintetico de banco'),
       ('s-banco-1','corredor','respuesta sintetica de banco');
RESET ROLE;
"""


async def checkpointer_escribe(hilo: str, n: int = 3) -> dict:
    """Usa el AsyncPostgresSaver REAL: setup, varios put, get y list."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.checkpoint.base import empty_checkpoint, create_checkpoint

    res = {}
    async with AsyncPostgresSaver.from_conn_string(URL_OWNER) as cp:
        await cp.setup()
        cfg = {"configurable": {"thread_id": hilo, "checkpoint_ns": ""}}
        ckpt = empty_checkpoint()
        for i in range(n):
            # Los BLOBS sólo se escriben si el checkpoint trae valores de canal Y se declaran
            # sus versiones nuevas. Un `empty_checkpoint()` puesto tal cual llena `checkpoints`
            # y `checkpoint_writes` pero deja `checkpoint_blobs` VACÍA — y entonces el control
            # positivo no reproduce nada sobre la tabla más grande de las tres. Lo detectó el
            # propio arnés al ponerse rojo, que es justamente para lo que está.
            version = f"{i + 1:032d}.0"
            ckpt = {**ckpt,
                    "channel_values": {"mensajes": [f"dato sintetico de banco {i}"]},
                    "channel_versions": {**ckpt.get("channel_versions", {}), "mensajes": version}}
            cfg = await cp.aput(cfg, ckpt, {"source": "banco", "step": i, "writes": {}},
                                {"mensajes": version})
            await cp.aput_writes(cfg, [("canal", {"i": i})], f"tarea-{i}")
            ckpt = create_checkpoint(ckpt, {}, i)
        res["puestos"] = n
        tupla = await cp.aget_tuple({"configurable": {"thread_id": hilo, "checkpoint_ns": ""}})
        res["lectura"] = tupla is not None
        res["listados"] = len([c async for c in cp.alist({"configurable": {"thread_id": hilo}})])
    return res


def monta_banco(con_handoff: bool = True) -> None:
    sql_texto("DROP DATABASE IF EXISTS banco_p0;", db="postgres")
    sql_texto("CREATE DATABASE banco_p0;", db="postgres")
    rc, out = sql_texto(POSTURA)
    assert rc == 0, f"no se pudo montar la postura:\n{out}"
    asyncio.run(checkpointer_escribe("hilo-semilla", 3))       # crea checkpoint_* de verdad
    if con_handoff:
        rc, out = sql_texto("SET ROLE contexto_owner;\n" +
                            ";\n".join(handoff_ddl_del_repo()) + ";", detener=True)
        assert rc == 0, f"el _HANDOFF_DDL real falló:\n{out}"
        rc, out = sql_texto(SEMILLA_HANDOFF)
        assert rc == 0, out


# ══ 1 · CONTROL POSITIVO ════════════════════════════════════════════════════════════════
def control_positivo() -> Suite:
    titulo("1 · CONTROL POSITIVO — el banco tiene que REPRODUCIR la exposición")
    print("  Y con las fuentes reales: el checkpointer de LangGraph y el _HANDOFF_DDL del repo.")
    print("  Si esto no falla, el banco no mide nada y el resto es decorado.\n")
    s = Suite("control positivo")
    for t in CINCO:
        s.afirma(f"anon LEE {t}", ve_filas(t, "anon") > 0, f"vio {ve_filas(t, 'anon')}")
    s.afirma("anon puede TRUNCAR handoff_mensaje",
             puede("TRUNCATE public.handoff_mensaje CASCADE;", "anon"))
    s.afirma("anon puede mover la SECUENCIA de handoff_mensaje",
             puede("SELECT setval('public.handoff_mensaje_id_seq', 1, false);", "anon"))
    s.afirma("una tabla NUEVA nace expuesta (la causa raíz)",
             _nace_expuesta(), "si esto es False, el default privilege no está reproducido")
    return s


def _nace_expuesta() -> bool:
    psql("DROP TABLE IF EXISTS public.sonda_nacimiento;", "contexto_owner")
    psql("CREATE TABLE public.sonda_nacimiento (x int);", "contexto_owner")
    rc, out = psql("""SELECT coalesce(string_agg(DISTINCT pg_get_userbyid(a.grantee), ','),'')
                        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace, aclexplode(c.relacl) a
                       WHERE n.nspname='public' AND c.relname='sonda_nacimiento'
                         AND pg_get_userbyid(a.grantee) IN ('anon','authenticated','service_role');""")
    psql("DROP TABLE IF EXISTS public.sonda_nacimiento;", "contexto_owner")
    return bool(out.strip())


# ══ 2 · DESPUÉS DE LA 033 ═══════════════════════════════════════════════════════════════
def suite_cerrada() -> Suite:
    titulo("2 · DESPUÉS DE LA 033 — el perímetro de las cinco")
    s = Suite("perímetro P0")
    for rol in ("anon", "authenticated", "service_role"):
        for t in CINCO:
            n = ve_filas(t, rol)
            s.afirma(f"{rol} NO lee {t}", n == -1,
                     f"devolvió {n} (−1 = permiso denegado, 0 = RLS filtró pero el grant sigue)")
        s.afirma(f"{rol} NO puede truncar handoff_mensaje",
                 not puede("TRUNCATE public.handoff_mensaje CASCADE;", rol))
        s.afirma(f"{rol} NO puede tocar la SECUENCIA (la DoS del contador)",
                 not puede("SELECT setval('public.handoff_mensaje_id_seq', 1, false);", rol))
        # OJO: la funcion del trigger tiene que ser una funcion de trigger DE VERDAD.
        # Con `pg_notify` esta comprobacion pasaba EN VACIO: el CREATE TRIGGER fallaba por
        # tipo de funcion, no por permiso, asi que habria seguido "verde" aunque el
        # privilegio TRIGGER estuviera concedido. `suppress_redundant_updates_trigger` es
        # una funcion de trigger integrada y ejecutable por PUBLIC, asi que lo unico que
        # puede impedir el CREATE es el privilegio.
        s.afirma(f"{rol} NO puede colgar un TRIGGER",
                 not puede("CREATE TRIGGER t_mal BEFORE UPDATE ON public.handoff_mensaje "
                           "FOR EACH ROW EXECUTE FUNCTION suppress_redundant_updates_trigger();",
                           rol))

    rc, out = psql("""SELECT count(*) FILTER (WHERE relrowsecurity), count(*) FILTER (WHERE relforcerowsecurity)
                        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                       WHERE n.nspname='public' AND c.relname = ANY(ARRAY['checkpoints','checkpoint_blobs',
                             'checkpoint_writes','handoff_sesion','handoff_mensaje']);""")
    s.afirma("RLS en las 5, FORCE en ninguna", out.strip().startswith("5|0"), out.strip())
    rc, out = psql("""SELECT count(*) FROM pg_policies WHERE schemaname='public'
                       AND tablename = ANY(ARRAY['checkpoints','checkpoint_blobs','checkpoint_writes',
                            'handoff_sesion','handoff_mensaje']);""")
    s.afirma("cero políticas", out.strip() == "0", out.strip())

    # vecinas intactas
    s.afirma("la vecina SIN rls sigue legible por anon", ve_filas("vecina_sin_rls", "anon") == 3)
    s.afirma("la vecina CON rls sigue en 0 sin error", ve_filas("vecina_con_rls", "anon") == 0)
    s.afirma("checkpoint_migrations NO se tocó (queda para la 2ª ola)",
             ve_filas("checkpoint_migrations", "anon") >= 0)
    return s


# ══ 3 · EL CHECKPOINTER SIGUE FUNCIONANDO ═══════════════════════════════════════════════
def checkpointer_funciona(s: Suite) -> None:
    titulo("3 · CHECKPOINTER REAL con el perímetro cerrado (PASO 5 del mandato)")
    print("  No se asume por BYPASSRLS: se ejecuta la librería de verdad.\n")
    antes = {t: ve_filas(t, "contexto_owner") for t in CINCO[:3]}
    try:
        r = asyncio.run(checkpointer_escribe("hilo-tras-033", 4))
        s.afirma("setup() + 4 aput + aput_writes con RLS activo", r["puestos"] == 4)
        s.afirma("aget_tuple recupera el checkpoint", r["lectura"])
        s.afirma("alist enumera el historial", r["listados"] >= 4, f"listó {r['listados']}")
    except Exception as e:
        s.afirma("el checkpointer real funciona tras la 033", False, f"{type(e).__name__}: {e}")
        return
    despues = {t: ve_filas(t, "contexto_owner") for t in CINCO[:3]}
    s.afirma("el checkpointer ESCRIBIÓ de verdad",
             all(despues[t] > antes[t] for t in antes), f"{antes} -> {despues}")

    rc, out = psql("""SELECT count(*) FILTER (WHERE relrowsecurity) FROM pg_class c
                        JOIN pg_namespace n ON n.oid=c.relnamespace
                       WHERE n.nspname='public'
                         AND c.relname = ANY(ARRAY['checkpoints','checkpoint_blobs','checkpoint_writes']);""")
    s.afirma("el setup() del checkpointer NO se llevó el RLS por delante", out.strip() == "3", out.strip())
    s.afirma("y `anon` sigue fuera después de que el checkpointer escribiera",
             ve_filas("checkpoint_blobs", "anon") == -1)
    # borrado de hilo, que es la operación menos obvia
    s.afirma("el dueño puede BORRAR un hilo (limpieza)",
             puede("DELETE FROM public.checkpoint_writes WHERE thread_id='hilo-semilla';", "contexto_owner"))


# ══ 4 · EL HANDOFF SIGUE FUNCIONANDO ════════════════════════════════════════════════════
def handoff_funciona(s: Suite) -> None:
    titulo("4 · HANDOFF REAL con el perímetro cerrado (PASO 6 del mandato)")
    print("  Se vuelve a correr el _HANDOFF_DDL del repo: es DDL en caliente, una vez por")
    print("  proceso, así que ocurrirá en producción tras el próximo despliegue.\n")
    rc, out = sql_texto("SET ROLE contexto_owner;\n" + ";\n".join(handoff_ddl_del_repo()) + ";",
                        detener=True)
    s.afirma("ensure_handoff_tables() (el DDL real) corre sin error tras la 033", rc == 0,
             out.strip()[-260:])
    rc, out = psql("""SELECT count(*) FILTER (WHERE relrowsecurity) FROM pg_class c
                        JOIN pg_namespace n ON n.oid=c.relnamespace
                       WHERE n.nspname='public' AND c.relname IN ('handoff_sesion','handoff_mensaje');""")
    s.afirma("ese DDL NO se llevó el RLS por delante", out.strip() == "2", out.strip())
    rc, out = psql("""SELECT coalesce(string_agg(DISTINCT pg_get_userbyid(a.grantee),','),'(ninguno)')
                        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace, aclexplode(c.relacl) a
                       WHERE n.nspname='public' AND c.relname IN ('handoff_sesion','handoff_mensaje')
                         AND pg_get_userbyid(a.grantee) IN ('anon','authenticated','service_role');""")
    s.afirma("ni devolvió privilegios a los roles externos", out.strip() == "(ninguno)", out.strip())

    antes = ve_filas("handoff_mensaje", "contexto_owner")
    s.afirma("el backend INSERTA un mensaje de corredor",
             puede("INSERT INTO public.handoff_mensaje (session_id, autor, texto) "
                   "VALUES ('s-banco-1','corredor','otra respuesta sintetica');", "contexto_owner"))
    s.afirma("y la fila está", ve_filas("handoff_mensaje", "contexto_owner") == antes + 1)
    s.afirma("el backend LEE el hilo (SELECT autor, texto ... como crm_tools)",
             puede("SELECT autor, texto FROM public.handoff_mensaje WHERE session_id='s-banco-1' "
                   "ORDER BY id ASC;", "contexto_owner"))
    s.afirma("el backend ACTUALIZA el estado de la sesión",
             puede("UPDATE public.handoff_sesion SET estado='atendido' WHERE session_id='s-banco-1';",
                   "contexto_owner"))
    s.afirma("el backend lee lead_email (rescate de avisos)",
             puede("SELECT lead_email FROM public.handoff_sesion WHERE session_id='s-banco-1';",
                   "contexto_owner"))


# ══ 5 · LA 034 ══════════════════════════════════════════════════════════════════════════
def suite_034() -> Suite:
    titulo("5 · DESPUÉS DE LA 034 — la causa raíz")
    s = Suite("causa raíz")
    acl_previa = psql("""SELECT relacl::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                          WHERE n.nspname='public' AND c.relname='vecina_sin_rls';""")[1].strip()
    rc, out = archivo("034_default_privileges_no_exponen.sql")
    s.afirma("la 034 aplica", rc == 0, out.strip()[-300:])
    s.afirma("una tabla NUEVA ya NO nace expuesta", not _nace_expuesta())
    acl_post = psql("""SELECT relacl::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                        WHERE n.nspname='public' AND c.relname='vecina_sin_rls';""")[1].strip()
    s.afirma("y NO cambió el acl de una tabla que ya existía", acl_previa == acl_post,
             f"{acl_previa}  ->  {acl_post}")
    s.afirma("las vecinas siguen con las mismas filas", ve_filas("vecina_sin_rls", "anon") == 3)
    rc2, _ = archivo("034_default_privileges_no_exponen.sql")
    s.afirma("la 034 es idempotente", rc2 == 0)
    return s


# ══ 6 · MUTACIONES ══════════════════════════════════════════════════════════════════════
def mutaciones() -> Suite:
    titulo("6 · MUTACIONES — la prueba tiene que ponerse ROJA (PASO 7 del mandato)")
    s = Suite("mutaciones")
    original = (MIGRACIONES / "033_conversaciones_y_handoff_perimetro.sql").read_text(encoding="utf-8")

    def prepara():
        monta_banco()

    # M1 · sin REVOKE
    print(f"\n{GRIS}  M1 · se neutraliza el REVOKE de las tablas{FIN}")
    prepara()
    mut = original.replace(
        "'REVOKE ALL PRIVILEGES ON TABLE public.checkpoints, public.checkpoint_blobs, '",
        "'SELECT 1 /* M1 */ -- '")
    assert mut != original, "M1 no encontró el REVOKE: el arnés mentiría"
    rc, out = archivo("", texto=mut)
    s.afirma("M1 · sin REVOKE la 033 ABORTA en su verificación",
             rc != 0 and "quedan privilegios en pie" in out, out.strip()[-200:])

    # M2 · sin RLS
    print(f"\n{GRIS}  M2 · se quita ENABLE ROW LEVEL SECURITY{FIN}")
    prepara()
    mut = original
    for t in CINCO:
        for pad in ("        ", "       ", "      ", "     ", "    ", "   ", "  ", " "):
            mut = mut.replace(f"ALTER TABLE public.{t}{pad}ENABLE ROW LEVEL SECURITY;\n", "")
    assert mut != original, "M2 no encontró los ENABLE RLS"
    rc, out = archivo("", texto=mut)
    s.afirma("M2 · sin RLS la 033 ABORTA en su verificación",
             rc != 0 and "RLS no quedó activado" in out, out.strip()[-200:])

    # M3..M8 parten de una 033 bien aplicada
    prepara()
    rc, out = archivo("033_conversaciones_y_handoff_perimetro.sql")
    assert rc == 0, out

    print(f"\n{GRIS}  M3 · se devuelve TRUNCATE a anon{FIN}")
    psql("GRANT TRUNCATE ON public.handoff_mensaje TO anon;", "contexto_owner")
    s.afirma("M3 · con TRUNCATE devuelto, anon vuelve a poder vaciar la tabla",
             puede("TRUNCATE public.handoff_mensaje CASCADE;", "anon"))
    psql("REVOKE ALL ON public.handoff_mensaje FROM anon;", "contexto_owner")

    print(f"\n{GRIS}  M4 · se devuelve TRIGGER a anon{FIN}")
    psql("GRANT TRIGGER ON public.handoff_mensaje TO anon;", "contexto_owner")
    s.afirma("M4 · con TRIGGER devuelto, anon vuelve a poder colgar código en la tabla",
             puede("CREATE TRIGGER t_m4 BEFORE UPDATE ON public.handoff_mensaje "
                   "FOR EACH ROW EXECUTE FUNCTION suppress_redundant_updates_trigger();", "anon"))
    psql("DROP TRIGGER IF EXISTS t_m4 ON public.handoff_mensaje;", "contexto_owner")
    psql("REVOKE ALL ON public.handoff_mensaje FROM anon;", "contexto_owner")

    print(f"\n{GRIS}  M5 · se deja el DEFAULT PRIVILEGE peligroso (no se aplica la 034){FIN}")
    s.afirma("M5 · sin la 034, una tabla nueva sigue naciendo expuesta", _nace_expuesta())

    print(f"\n{GRIS}  M6 · se bloquea a `postgres` por accidente{FIN}")
    psql("REVOKE ALL ON public.handoff_mensaje FROM contexto_owner;", "contexto_owner")
    rota = not puede("SELECT count(*) FROM public.handoff_mensaje;", "contexto_owner")
    s.afirma("M6 · revocar al DUEÑO rompe al backend — por eso la 033 nunca lo nombra",
             rota or _dueno_sigue_por_ser_dueno(),
             "el dueño conserva acceso por propiedad aunque se revoque el grant; "
             "la mutación documenta ese matiz")
    psql("GRANT ALL ON public.handoff_mensaje TO contexto_owner;", "contexto_owner")

    print(f"\n{GRIS}  M7 · se introduce una política permisiva{GRIS}{FIN}")
    psql("CREATE POLICY p_m7 ON public.handoff_mensaje FOR SELECT TO anon USING (true);",
         "contexto_owner")
    rc, out = psql("""SELECT count(*) FROM pg_policies WHERE schemaname='public'
                       AND tablename='handoff_mensaje';""")
    s.afirma("M7 · una política permisiva rompe la afirmación de «cero políticas»",
             out.strip() != "0", out.strip())
    rc, out = archivo("033_conversaciones_y_handoff_perimetro.sql")
    s.afirma("M7b · y la 033 se niega a re-aplicarse con una política presente",
             rc != 0 and "ya existen" in out, out.strip()[-200:])
    psql("DROP POLICY IF EXISTS p_m7 ON public.handoff_mensaje;", "contexto_owner")

    print(f"\n{GRIS}  M8 · se devuelve el acceso a service_role sin justificación{FIN}")
    psql("GRANT SELECT ON public.handoff_mensaje TO service_role;", "contexto_owner")
    s.afirma("M8 · service_role (BYPASSRLS) vuelve a leerlo todo si se le devuelve el grant",
             ve_filas("handoff_mensaje", "service_role") >= 0,
             "RLS no lo detiene: sólo el REVOKE")
    psql("REVOKE ALL ON public.handoff_mensaje FROM service_role;", "contexto_owner")

    # M9 · LA TRAMPA DEL CATALOGO. `pg_default_acl.defaclnamespace` vale 0 cuando la concesion
    #      se hizo SIN `IN SCHEMA`, y esa fila no empareja con `pg_namespace`. La version de la
    #      034 que usaba INNER JOIN daba VERDE con el agujero abierto. Aqui se comprueba que la
    #      version corregida lo ve — y que la vieja no lo veria.
    print(f"\n{GRIS}  M9 · una concesión GLOBAL (sin IN SCHEMA) que el INNER JOIN perdía{FIN}")
    monta_banco()
    rc, out = archivo("034_default_privileges_no_exponen.sql")
    assert rc == 0, out
    psql("ALTER DEFAULT PRIVILEGES GRANT ALL ON TABLES TO anon;", "contexto_owner")
    vieja = psql("""SELECT count(*) FROM pg_default_acl d
                      JOIN pg_namespace n ON n.oid=d.defaclnamespace, aclexplode(d.defaclacl) a
                     WHERE n.nspname='public' AND d.defaclobjtype='r'
                       AND pg_get_userbyid(a.grantee)='anon';""")[1].strip()
    nueva = psql("""SELECT count(*) FROM pg_default_acl d
                      LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace, aclexplode(d.defaclacl) a
                     WHERE (d.defaclnamespace = 0 OR n.nspname='public') AND d.defaclobjtype='r'
                       AND pg_get_userbyid(a.grantee)='anon';""")[1].strip()
    s.afirma("M9 · con la concesion global viva, una tabla nueva SI nace expuesta",
             _nace_expuesta(), "si no, el escenario no esta reproducido")
    s.afirma("M9a · la consulta VIEJA (INNER JOIN) no la ve -> era fail-OPEN",
             vieja == "0", f"vio {vieja}")
    s.afirma("M9b · la consulta de la 034 (LEFT JOIN) SI la ve", nueva != "0", f"vio {nueva}")
    rc, out = archivo("034_default_privileges_no_exponen.sql")
    s.afirma("M9c · y la 034 re-aplicada ABORTA en vez de dar verde",
             rc != 0 and ("todavía concede" in out or "SIGUE naciendo" in out),
             out.strip()[-240:])
    return s


def _dueno_sigue_por_ser_dueno() -> bool:
    return ve_filas("handoff_mensaje", "contexto_owner") >= 0


def main() -> int:
    for m in ("033_conversaciones_y_handoff_perimetro.sql", "034_default_privileges_no_exponen.sql"):
        if not (MIGRACIONES / m).exists():
            print(f"{ROJO}falta {m}{FIN}")
            return 2

    titulo(f"0 · BANCO — {CONTENEDOR}:{PUERTO}, postura de Supabase reproducida")
    monta_banco()
    rc, out = psql("SELECT version();")
    print(f"  {out.strip()[:70]}")
    print(f"  tablas creadas por el checkpointer REAL y por el _HANDOFF_DDL REAL del repo")
    print(f"  ({len(handoff_ddl_del_repo())} sentencias leídas de app/routers/chat.py por AST)")

    s1 = control_positivo()
    if not s1.verde:
        print(f"\n{ROJO}EL CONTROL POSITIVO NO SE REPRODUJO.{FIN} El banco no mide lo que dice medir.")
        return 1

    titulo("· se aplica la 033 ·")
    rc, out = archivo("033_conversaciones_y_handoff_perimetro.sql")
    print(out.strip()[-600:])
    if rc != 0:
        print(f"{ROJO}la 033 no aplicó{FIN}")
        return 1

    s2 = suite_cerrada()
    checkpointer_funciona(s2)
    handoff_funciona(s2)
    rc2, _ = archivo("033_conversaciones_y_handoff_perimetro.sql")
    s2.afirma("la 033 es idempotente", rc2 == 0)

    s3 = suite_034()
    s4 = mutaciones()

    titulo("RESUMEN")
    for s in (s1, s2, s3, s4):
        marca = f"{VERDE}VERDE{FIN}" if s.verde else f"{ROJO}ROJA ({len(s.fallos)}){FIN}"
        print(f"  {s.titulo:22} {s.total:3} comprobaciones  {marca}")
        for f in s.fallos:
            print(f"        - {f}")
    return 0 if all(s.verde for s in (s1, s2, s3, s4)) else 1


if __name__ == "__main__":
    sys.exit(main())
