# -*- coding: utf-8 -*-
"""BUYER-STORE-PROD-PERIMETER-R1 · FASE 2 · banco aislado para la migración 032.

No es una prueba de la suite de pytest: es un arnés que necesita Docker y un PostgreSQL 17
limpio. Se corre a mano, y por eso lleva su propio runner:

    python tests/arnes_perimetro_032.py

## POR QUÉ UN BANCO Y NO PRODUCCIÓN

Porque la pregunta que hay que contestar antes de tocar producción es «¿esto rompe al
backend?», y la única forma honesta de contestarla es romperlo a propósito en un sitio donde
no importe.

## LA FIDELIDAD ES LO QUE HACE QUE VALGA ALGO

En producción el backend conecta con un rol llamado `postgres` que **no es superusuario**:
es DUEÑO de las tablas y tiene `rolbypassrls`. El `postgres` de un contenedor limpio sí es
superusuario, y un superusuario se salta todo trivialmente — probar contra él demostraría que
el cambio no rompe nada, pero por la razón equivocada. Por eso el banco crea
`contexto_owner` (NOSUPERUSER, BYPASSRLS, dueño) y aplica las migraciones como él.

Y reproduce la causa raíz: `ALTER DEFAULT PRIVILEGES ... GRANT ALL ON TABLES TO anon,
authenticated, service_role`. Sin esa línea las tablas no nacerían expuestas, el control
positivo no fallaría, y toda la prueba sería vacía.

## CONTROL POSITIVO

Antes de aplicar la 032, el banco EXIGE que el defecto se reproduzca: que `anon` pueda leer y
truncar. Si no se reprodujera, el arnés se detiene — una prueba que pasa porque el defecto no
estaba no prueba nada.

## MUTACIONES

Al final se aplican cuatro mutaciones. Una prueba que sigue verde cuando rompes lo que
defiende no defiende nada.

  M1   se quita ENABLE ROW LEVEL SECURITY  -> la propia 032 se niega a confirmar
  M2a  se neutraliza el REVOKE             -> la propia 032 se niega a confirmar
  M2b  RLS sola, el enfoque de la 030      -> MIDE que queda abierto: `anon` sigue
                                              pudiendo TRUNCAR y `service_role` sigue
                                              leyendolo todo. Es el argumento entero
                                              a favor del REVOKE, en una linea
  M3   se aplica la 032 y luego su ROLLBACK -> `anon` vuelve a leer
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

# El contenedor se puede cambiar desde fuera, porque hay DOS versiones que importan:
# produccion corre PostgreSQL 17.6 y el CI corre 15. La 032 tiene que valer en las dos, y
# la diferencia no es teorica: el privilegio MAINTAIN no existe en 15.
#     PERIM_CONTENEDOR=perim-pg15 python tests/arnes_perimetro_032.py
CONTENEDOR = os.environ.get("PERIM_CONTENEDOR", "perim-pg")
RAIZ = pathlib.Path(__file__).resolve().parent.parent
MIGRACIONES = RAIZ / "migrations"
BANCO = "banco_032"

ROJO, VERDE, GRIS, FIN = "\033[31m", "\033[32m", "\033[90m", "\033[0m"


# ══ plomería ════════════════════════════════════════════════════════════════════════════
def psql(sql: str, rol: str | None = None, db: str = BANCO) -> tuple[int, str]:
    """Ejecuta SQL. Devuelve (código, salida+errores). `rol` usa SET ROLE, como PostgREST."""
    if rol:
        sql = f"SET ROLE {rol};\n{sql}"
    p = subprocess.run(
        ["docker", "exec", "-i", CONTENEDOR, "psql", "-U", "postgres", "-d", db, "-q", "-t", "-A"],
        input=sql, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def archivo(ruta: pathlib.Path, db: str = BANCO, detener: bool = True,
            rol: str | None = "contexto_owner") -> tuple[int, str]:
    """Aplica un fichero .sql. Por defecto COMO EL DUENO, que es la fidelidad que importa:
    en produccion quien aplica la migracion es `postgres`, que es el propietario de las dos
    tablas y el concedente de los privilegios que se van a revocar."""
    return sql_texto(ruta.read_text(encoding="utf-8"), db, detener, rol)


def sql_texto(texto: str, db: str = BANCO, detener: bool = True,
              rol: str | None = None) -> tuple[int, str]:
    if rol:
        texto = "SET ROLE " + rol + ";\n" + texto
    p = subprocess.run(
        ["docker", "exec", "-i", CONTENEDOR, "psql", "-U", "postgres", "-d", db, "-q"]
        + (["-v", "ON_ERROR_STOP=1"] if detener else []),
        input=texto, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def escalar(sql: str, rol: str | None = None) -> str:
    return psql(sql, rol)[1].strip().splitlines()[0].strip() if psql(sql, rol)[1].strip() else ""


class Suite:
    def __init__(self, titulo: str):
        self.titulo, self.fallos, self.total = titulo, [], 0

    def afirma(self, nombre: str, condicion: bool, detalle: str = "") -> None:
        self.total += 1
        if condicion:
            print(f"  {VERDE}PASS{FIN}  {nombre}")
        else:
            self.fallos.append(nombre)
            print(f"  {ROJO}FALLA{FIN} {nombre}" + (f"\n         {GRIS}{detalle}{FIN}" if detalle else ""))

    @property
    def verde(self) -> bool:
        return not self.fallos


def titulo(t: str) -> None:
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}")


# ══ el banco ════════════════════════════════════════════════════════════════════════════
POSTURA = """
DROP DATABASE IF EXISTS banco_032;
CREATE DATABASE banco_032;
"""

SUPABASE = """
-- Roles como en Supabase. `service_role` con BYPASSRLS: el atributo que RLS no detiene.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon')          THEN CREATE ROLE anon NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role')  THEN CREATE ROLE service_role NOLOGIN BYPASSRLS; END IF;
  -- El doble del `postgres` de produccion: NOSUPERUSER, BYPASSRLS, y sera dueno.
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='contexto_owner') THEN
      CREATE ROLE contexto_owner LOGIN PASSWORD 'perim' NOSUPERUSER BYPASSRLS;
  END IF;
END $$;
GRANT anon, authenticated, service_role, contexto_owner TO postgres;

CREATE SCHEMA IF NOT EXISTS auth;
ALTER SCHEMA public OWNER TO contexto_owner;
ALTER SCHEMA auth   OWNER TO contexto_owner;
GRANT USAGE ON SCHEMA public, auth TO anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS auth.users (id UUID PRIMARY KEY, email TEXT);
ALTER TABLE auth.users OWNER TO contexto_owner;

-- LA CAUSA RAIZ, reproducida: toda tabla que cree el dueno nace con DML para los tres roles.
ALTER DEFAULT PRIVILEGES FOR ROLE contexto_owner IN SCHEMA public
    GRANT ALL ON TABLES TO anon, authenticated, service_role;

-- Vecina sin RLS: prueba que la 032 no toca nada mas.
SET ROLE contexto_owner;
CREATE TABLE public.tabla_vecina (id SERIAL PRIMARY KEY, nota TEXT NOT NULL);
INSERT INTO public.tabla_vecina (nota) VALUES ('v1'),('v2'),('v3');
-- Vecina con RLS, imitando a la 030: RLS puesto, grants intactos.
CREATE TABLE public.vecina_con_rls (id SERIAL PRIMARY KEY, nota TEXT NOT NULL);
INSERT INTO public.vecina_con_rls (nota) VALUES ('r1'),('r2');
ALTER TABLE public.vecina_con_rls ENABLE ROW LEVEL SECURITY;
RESET ROLE;
"""

SEMILLA = """
SET ROLE contexto_owner;
INSERT INTO auth.users (id, email) VALUES
    ('11111111-1111-1111-1111-111111111111', 'sintetico-1@ejemplo.invalid'),
    ('22222222-2222-2222-2222-222222222222', 'sintetico-2@ejemplo.invalid');
INSERT INTO public.buyer_context_heads (buyer_id, current_revision) VALUES
    ('11111111-1111-1111-1111-111111111111', 0),
    ('22222222-2222-2222-2222-222222222222', 1);
INSERT INTO public.buyer_context_revisions
    (buyer_id, context_revision, source_message_id, context_json) VALUES
    ('11111111-1111-1111-1111-111111111111', 0, 'msg-sintetico-a', '{"nota":"dato de banco, nadie real"}'),
    ('22222222-2222-2222-2222-222222222222', 0, 'msg-sintetico-b', '{"nota":"dato de banco, nadie real"}'),
    ('22222222-2222-2222-2222-222222222222', 1, 'msg-sintetico-c', '{"nota":"dato de banco, nadie real"}');
RESET ROLE;
"""


def monta_banco() -> None:
    sql_texto(POSTURA, db="postgres")
    rc, out = sql_texto(SUPABASE)
    assert rc == 0, f"no se pudo montar la postura de Supabase:\n{out}"
    for nombre in ("028_buyer_context_store.sql", "029_buyer_source_message_id_nonempty.sql"):
        # Como DUENO, para que el relacl salga con el mismo concedente que produccion.
        cuerpo = "SET ROLE contexto_owner;\n" + (MIGRACIONES / nombre).read_text(encoding="utf-8")
        rc, out = sql_texto(cuerpo)
        assert rc == 0, f"falló {nombre}:\n{out}"
    rc, out = sql_texto(SEMILLA)
    assert rc == 0, f"falló la semilla:\n{out}"


def puede(operacion: str, rol: str) -> bool:
    """¿Consigue `rol` ejecutar `operacion`? True = lo logró (o leyó filas)."""
    rc, out = psql(operacion, rol)
    return "permission denied" not in out and "ERROR" not in out


def ve_filas(tabla: str, rol: str) -> int:
    rc, out = psql(f"SELECT count(*) FROM public.{tabla};", rol)
    if "ERROR" in out or "permission denied" in out:
        return -1  # bloqueado por privilegio, que es distinto de ver cero
    try:
        return int(out.strip().splitlines()[0])
    except (ValueError, IndexError):
        return -2


TABLAS = ("buyer_context_heads", "buyer_context_revisions")


# ══ 1 · CONTROL POSITIVO ════════════════════════════════════════════════════════════════
def control_positivo() -> Suite:
    titulo("1 · CONTROL POSITIVO — el banco tiene que REPRODUCIR la exposición")
    print("  Si esto no falla, el banco no está midiendo nada y el resto es decorado.\n")
    s = Suite("control positivo")
    s.afirma("anon LEE buyer_context_heads (2 filas)", ve_filas("buyer_context_heads", "anon") == 2)
    s.afirma("anon LEE buyer_context_revisions (3 filas)", ve_filas("buyer_context_revisions", "anon") == 3)
    s.afirma("authenticated LEE buyer_context_revisions", ve_filas("buyer_context_revisions", "authenticated") == 3)
    s.afirma("service_role LEE buyer_context_revisions", ve_filas("buyer_context_revisions", "service_role") == 3)
    s.afirma("anon PUEDE truncar (sin RLS)",
             puede("TRUNCATE public.buyer_context_revisions CASCADE;", "anon"))
    # `anon` acaba de vaciar la tabla en el control positivo; se rehace para lo que viene.
    sql_texto("""SET ROLE contexto_owner;
        INSERT INTO public.buyer_context_revisions (buyer_id, context_revision, source_message_id, context_json)
        VALUES ('11111111-1111-1111-1111-111111111111',0,'msg-sintetico-a','{"n":1}'),
               ('22222222-2222-2222-2222-222222222222',0,'msg-sintetico-b','{"n":1}'),
               ('22222222-2222-2222-2222-222222222222',1,'msg-sintetico-c','{"n":1}');
        RESET ROLE;""")
    return s


# ══ 2 · DESPUÉS DE LA 032 ═══════════════════════════════════════════════════════════════
def suite_cerrada(etiqueta: str = "2 · DESPUÉS DE LA 032") -> Suite:
    titulo(etiqueta)
    s = Suite("perímetro cerrado")

    # — el backend sigue trabajando —
    s.afirma("el DUEÑO sigue leyendo heads (2)", ve_filas("buyer_context_heads", "contexto_owner") == 2)
    s.afirma("el DUEÑO sigue leyendo revisions (3)", ve_filas("buyer_context_revisions", "contexto_owner") == 3)
    s.afirma("el DUEÑO sigue escribiendo",
             puede("""INSERT INTO public.buyer_context_revisions
                        (buyer_id, context_revision, source_message_id, context_json)
                      VALUES ('11111111-1111-1111-1111-111111111111', 9, 'msg-prueba-escritura', '{"x":1}');
                      DELETE FROM public.buyer_context_revisions WHERE context_revision = 9;""",
                   "contexto_owner"))

    # — los de fuera, cortados —
    for rol in ("anon", "authenticated", "service_role"):
        for tabla in TABLAS:
            s.afirma(f"{rol} NO lee {tabla}", ve_filas(tabla, rol) == -1,
                     f"devolvió {ve_filas(tabla, rol)} (−1 = permiso denegado, 0 = RLS filtró pero el grant sigue)")
        s.afirma(f"{rol} NO puede truncar (la que RLS sola NO cubre)",
                 not puede("TRUNCATE public.buyer_context_revisions CASCADE;", rol))
        s.afirma(f"{rol} NO puede insertar",
                 not puede("""INSERT INTO public.buyer_context_heads (buyer_id, current_revision)
                              VALUES ('33333333-3333-3333-3333-333333333333', 0);""", rol))

    # — estado del catálogo —
    rc, out = psql("""SELECT count(*) FILTER (WHERE relrowsecurity), count(*) FILTER (WHERE relforcerowsecurity)
                        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                       WHERE n.nspname='public' AND c.relname IN ('buyer_context_heads','buyer_context_revisions');""")
    s.afirma("RLS activado en las 2, FORCE en ninguna", out.strip().startswith("2|0"), out.strip())
    s.afirma("cero políticas",
             psql("""SELECT count(*) FROM pg_policies WHERE schemaname='public'
                      AND tablename IN ('buyer_context_heads','buyer_context_revisions');""")[1].strip() == "0")
    rc, out = psql("""SELECT coalesce(string_agg(DISTINCT pg_get_userbyid(a.grantee), ','), '')
                        FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace, aclexplode(t.relacl) a
                       WHERE n.nspname='public' AND t.relname IN ('buyer_context_heads','buyer_context_revisions');""")
    s.afirma("en el ACL sólo queda el dueño", out.strip() in ("contexto_owner", ""), f"ACL: {out.strip()!r}")

    # — nada más cambió —
    s.afirma("la vecina SIN rls sigue igual (anon la lee)", ve_filas("tabla_vecina", "anon") == 3)
    s.afirma("la vecina CON rls sigue igual (anon ve 0, sin error)", ve_filas("vecina_con_rls", "anon") == 0)
    rc, out = psql("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                   "WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity;")
    s.afirma("sólo 3 tablas con RLS en todo public (vecina + las 2)", out.strip() == "3", out.strip())

    # — las filas siguen ahí —
    s.afirma("heads conserva 2 filas", ve_filas("buyer_context_heads", "contexto_owner") == 2)
    s.afirma("revisions conserva 3 filas", ve_filas("buyer_context_revisions", "contexto_owner") == 3)

    # — la cascada desde auth.users sigue funcionando con RLS puesto —
    # Los triggers de integridad referencial corren con los privilegios del dueño, así que
    # con ENABLE (no FORCE) deberían eludir RLS. «Deberían» no basta: se mide.
    psql("""SET ROLE contexto_owner;
            INSERT INTO auth.users (id, email) VALUES
                ('44444444-4444-4444-4444-444444444444','cascada@ejemplo.invalid');
            INSERT INTO public.buyer_context_heads (buyer_id, current_revision)
                VALUES ('44444444-4444-4444-4444-444444444444', 0);
            INSERT INTO public.buyer_context_revisions
                (buyer_id, context_revision, source_message_id, context_json)
                VALUES ('44444444-4444-4444-4444-444444444444',0,'msg-cascada','{"n":1}');""")
    antes = ve_filas("buyer_context_revisions", "contexto_owner")
    psql("DELETE FROM auth.users WHERE id='44444444-4444-4444-4444-444444444444';",
         "contexto_owner")
    s.afirma("el borrado en cascada desde auth.users sigue funcionando con RLS activo",
             antes == 4 and ve_filas("buyer_context_revisions", "contexto_owner") == 3,
             f"antes={antes} despues={ve_filas('buyer_context_revisions', 'contexto_owner')}")

    # — la propiedad que justifica ENABLE RLS y no sólo el REVOKE —
    psql("GRANT SELECT ON public.buyer_context_revisions TO anon;", "contexto_owner")
    s.afirma("RESISTE UN RE-GRANT: aunque alguien devuelva SELECT a anon, sigue viendo 0 filas",
             ve_filas("buyer_context_revisions", "anon") == 0,
             "esto es lo que aporta RLS por encima del REVOKE")
    psql("REVOKE ALL PRIVILEGES ON public.buyer_context_revisions FROM anon;", "contexto_owner")
    return s


# ══ 3 · MUTACIONES ══════════════════════════════════════════════════════════════════════
def mutaciones(m032: pathlib.Path) -> Suite:
    titulo("3 · MUTACIONES — la prueba tiene que ponerse ROJA")
    s = Suite("mutaciones")
    original = m032.read_text(encoding="utf-8")

    # M1 · sin ENABLE ROW LEVEL SECURITY
    print(f"\n{GRIS}  M1 · se quita ENABLE ROW LEVEL SECURITY{FIN}")
    monta_banco()
    mut = original
    for tabla in ("buyer_context_heads    ", "buyer_context_revisions"):
        mut = mut.replace("ALTER TABLE public." + tabla + " ENABLE ROW LEVEL SECURITY;\n", "")
    assert mut != original, "la mutación M1 no encontró el ENABLE RLS: el arnés mentiría"
    rc, out = sql_texto(mut, detener=True, rol="contexto_owner")
    s.afirma("M1 · la propia 032 se niega a aplicarse (su verificación muerde)",
             rc != 0 and "RLS no quedó activado" in out,
             out.strip()[-200:])

    # M2a · sin el REVOKE, la verificación de la propia 032 tiene que negarse
    print(f"\n{GRIS}  M2a · se neutraliza el REVOKE; la 032 debe negarse a confirmar{FIN}")
    monta_banco()
    sin_revoke = original.replace(
        "'REVOKE ALL PRIVILEGES ON TABLE public.buyer_context_heads, public.buyer_context_revisions FROM %I',",
        "'SELECT 1 /* REVOKE neutralizado por la mutacion M2 */ -- %I',")
    assert sin_revoke != original, "la mutación M2 no encontró el REVOKE: el arnés mentiría"
    rc, out = sql_texto(sin_revoke, detener=True, rol="contexto_owner")
    s.afirma("M2a · sin REVOKE la 032 ABORTA en su propia verificación",
             rc != 0 and "quedan privilegios en pie" in out, out.strip()[-220:])

    # M2b · y si además se silenciara la verificación —es decir, el enfoque de la 030: RLS y
    #       nada más— hay que MEDIR qué queda abierto. Esto es lo que hace que el REVOKE no
    #       sea opcional, y si alguna vez deja de ser cierto, esta prueba lo dirá.
    print(f"\n{GRIS}  M2b · RLS sola (el enfoque de la 030): ¿qué sigue abierto?{FIN}")
    monta_banco()
    rc, out = sql_texto("""SET ROLE contexto_owner;
        ALTER TABLE public.buyer_context_heads     ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.buyer_context_revisions ENABLE ROW LEVEL SECURITY;""", detener=True)
    assert rc == 0, out
    lee_anon = ve_filas("buyer_context_revisions", "anon")
    lee_service = ve_filas("buyer_context_revisions", "service_role")
    truncable = puede("TRUNCATE public.buyer_context_revisions CASCADE;", "anon")
    print(f"       {GRIS}con RLS sola -> anon lee={lee_anon} (0 = filtrado, NO bloqueado) · "
          f"service_role lee={lee_service} · anon truncó={truncable}{FIN}")
    s.afirma("M2b · con RLS SOLA, `anon` todavía puede TRUNCAR la tabla", truncable,
             "si esto fuera False, el REVOKE sobraría y la 032 estaría sobredimensionada")
    s.afirma("M2b · con RLS SOLA, `service_role` (BYPASSRLS) sigue leyéndolo todo",
             lee_service == 3, f"vio {lee_service}")

    # M3 · se aplica la 032 y luego se deshace (el rollback documentado)
    print(f"\n{GRIS}  M3 · se aplica la 032 y luego se ejecuta su ROLLBACK{FIN}")
    monta_banco()
    rc, out = archivo(m032)
    assert rc == 0, f"la 032 no aplicó en M3:\n{out}"
    sql_texto("""ALTER TABLE public.buyer_context_heads     DISABLE ROW LEVEL SECURITY;
                 ALTER TABLE public.buyer_context_revisions DISABLE ROW LEVEL SECURITY;
                 GRANT ALL PRIVILEGES ON TABLE public.buyer_context_heads,
                     public.buyer_context_revisions TO anon, authenticated, service_role;""")
    s.afirma("M3 · tras deshacerlo, anon vuelve a leer (la prueba se pone roja)",
             ve_filas("buyer_context_revisions", "anon") == 3,
             f"vio {ve_filas('buyer_context_revisions', 'anon')}")
    return s


def sin_los_roles(m032: pathlib.Path) -> Suite:
    """El caso del CI: un PostgreSQL de servicio donde `anon`, `authenticated` y
    `service_role` NO existen.

    Importa porque `REVOKE ... FROM rol_inexistente` es un ERROR, y como la 032 va en una
    transacción, ese error se llevaría por delante el ENABLE RLS de arriba — dejando la tabla
    ABIERTA y la migración en rojo. La guarda `IF EXISTS (SELECT 1 FROM pg_roles ...)` existe
    por esto, y aquí se comprueba que de verdad sirve."""
    titulo("2c · SIN LOS ROLES DE SUPABASE — el PostgreSQL del CI")
    s = Suite("sin roles")
    sql_texto("DROP DATABASE IF EXISTS banco_032_ci;", db="postgres")
    sql_texto("CREATE DATABASE banco_032_ci;", db="postgres")
    base = "banco_032_ci"
    sql_texto("""CREATE SCHEMA IF NOT EXISTS auth;
                 CREATE TABLE auth.users (id UUID PRIMARY KEY, email TEXT);""", db=base)
    for nombre in ("028_buyer_context_store.sql", "029_buyer_source_message_id_nonempty.sql"):
        rc, out = sql_texto((MIGRACIONES / nombre).read_text(encoding="utf-8"), db=base)
        assert rc == 0, out
    rc, out = sql_texto(m032.read_text(encoding="utf-8"), db=base, detener=True)
    s.afirma("la 032 aplica sin los roles de Supabase", rc == 0, out.strip()[-260:])
    p = subprocess.run(
        ["docker", "exec", "-i", CONTENEDOR, "psql", "-U", "postgres", "-d", base, "-q", "-t", "-A"],
        input="""SELECT count(*) FILTER (WHERE relrowsecurity) FROM pg_class c
                   JOIN pg_namespace n ON n.oid=c.relnamespace
                  WHERE n.nspname='public'
                    AND c.relname IN ('buyer_context_heads','buyer_context_revisions');""",
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    s.afirma("y aun así deja RLS activado en las 2 (el REVOKE no se llevó el ENABLE)",
             p.stdout.strip() == "2", f"quedaron {p.stdout.strip()!r} con RLS")
    return s


def main() -> int:
    m032 = MIGRACIONES / "032_buyer_store_prod_perimeter.sql"
    if not m032.exists():
        print(f"{ROJO}no existe {m032}{FIN}")
        return 2

    titulo("0 · BANCO — PostgreSQL 17 aislado, con la postura de Supabase reproducida")
    monta_banco()
    print("  banco montado: roles, auth.users, default privileges, 028, 029 y semilla sintética")

    s1 = control_positivo()
    if not s1.verde:
        print(f"\n{ROJO}EL CONTROL POSITIVO NO SE REPRODUJO.{FIN} El banco no mide lo que dice medir.")
        return 1

    titulo("· se aplica la 032 ·")
    rc, out = archivo(m032)
    print(out.strip()[-500:])
    if rc != 0:
        print(f"{ROJO}la 032 no aplicó{FIN}")
        return 1

    s2 = suite_cerrada()

    titulo("2b · IDEMPOTENCIA — aplicarla dos veces")
    rc2, out2 = archivo(m032)
    s2.afirma("la 032 es idempotente", rc2 == 0, out2.strip()[-200:])

    s2c = sin_los_roles(m032)
    s3 = mutaciones(m032)

    titulo("RESUMEN")
    for s in (s1, s2, s2c, s3):
        marca = f"{VERDE}VERDE{FIN}" if s.verde else f"{ROJO}ROJA ({len(s.fallos)}){FIN}"
        print(f"  {s.titulo:24} {s.total:3} comprobaciones  {marca}")
        for f in s.fallos:
            print(f"        - {f}")
    return 0 if all(s.verde for s in (s1, s2, s2c, s3)) else 1


if __name__ == "__main__":
    sys.exit(main())
