# -*- coding: utf-8 -*-
"""SEC-PERIM-LEAD-ACTIVIDAD-APPLY · banco aislado para la migración 037.

    python tests/arnes_perimetro_037.py
    PERIM_CONTENEDOR=perim-pg15 python tests/arnes_perimetro_037.py

No es una prueba de pytest: necesita Docker y un PostgreSQL limpio, igual que los arneses de la
032, 033 y 035. Producción corre PostgreSQL 17.6 y el CI corre 15: se corre en los dos.

## FIDELIDAD

  · El dueño es `contexto_owner` (NOSUPERUSER + BYPASSRLS), el doble del `postgres` de
    producción, que no es superusuario. Un superusuario se salta todo y demostraría que el
    cambio «no rompe nada» por la razón equivocada.
  · La causa raíz se reproduce: `ALTER DEFAULT PRIVILEGES … GRANT ALL ON TABLES TO anon,
    authenticated, service_role`, así la tabla NACE con la exposición medida en producción.
  · La tabla la crea el `_LEAD_ACTIVIDAD_DDL` REAL de `app/routers/chat.py`, leído por AST: una
    copia sería un doble que deriva en silencio.

## CONTROL POSITIVO

Antes de la 037 el banco EXIGE que el defecto se reproduzca: `anon` lee los correos, escribe el
consentimiento y el contacto, borra y trunca. Si no, se detiene: una prueba que pasa porque el
defecto no estaba no prueba nada.

## LO QUE SE PRUEBA DESPUÉS

  · los tres roles sin ningún privilegio (leer, insertar, actualizar, borrar, truncar);
  · el dueño —el backend— lee, inserta, actualiza y borra;
  · el DDL en runtime (`ensure_lead_actividad`) sigue funcionando, y la columna de TR-2
    (`reenganche_cerrado_en`) se puede añadir y nace cerrada;
  · RESISTE UN RE-GRANT: aunque alguien devuelva SELECT a anon, ve 0 filas (lo que aporta RLS);
  · idempotencia;
  · compuertas fail-closed: política existente, publicación, vista dependiente, función que la
    mencione y dueño distinto ABORTAN sin tocar nada;
  · mutaciones: sin ENABLE, sin REVOKE o con FORCE, la propia 037 se niega a confirmar.

## NO SE LEE CONTENIDO REAL

El banco escribe y lee datos sintéticos suyos (`@ejemplo.invalid`). Sobre producción, nada.
"""
from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys

CONTENEDOR = os.environ.get("PERIM_CONTENEDOR", "perim-pg")
RAIZ = pathlib.Path(__file__).resolve().parent.parent
MIGRACIONES = RAIZ / "migrations"
M037 = "037_lead_actividad_perimetro.sql"
BANCO = "banco_037"

ROJO, VERDE, GRIS, FIN = "\033[31m", "\033[32m", "\033[90m", "\033[0m"
ROLES = ("anon", "authenticated", "service_role")
PRIVS = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")


# ══ plomería ════════════════════════════════════════════════════════════════════════════
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


def aplica_037(rol="contexto_owner", texto=None):
    cuerpo = texto if texto is not None else (MIGRACIONES / M037).read_text(encoding="utf-8")
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


def ve_filas(rol):
    rc, out = psql("SELECT count(*) FROM public.lead_actividad;", rol)
    if "ERROR" in out or "permission denied" in out:
        return -1
    try:
        return int(out.strip().splitlines()[0])
    except (ValueError, IndexError):
        return -2


def puede(op, rol):
    rc, out = psql(op, rol)
    return "permission denied" not in out and "ERROR" not in out


def estado_rls():
    return psql("SELECT relrowsecurity::text || '|' || relforcerowsecurity::text FROM pg_class "
                "WHERE oid = 'public.lead_actividad'::regclass;")[1].strip()


def lead_ddl_del_repo():
    """`_LEAD_ACTIVIDAD_DDL` de app/routers/chat.py, por AST y sin importar el módulo."""
    arbol = ast.parse((RAIZ / "app" / "routers" / "chat.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_LEAD_ACTIVIDAD_DDL" for t in nodo.targets):
            return [ast.literal_eval(e) for e in nodo.value.elts]
    raise SystemExit("no se encontró _LEAD_ACTIVIDAD_DDL en app/routers/chat.py")


# ══ el banco ════════════════════════════════════════════════════════════════════════════
POSTURA = """
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon')           THEN CREATE ROLE anon NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated')  THEN CREATE ROLE authenticated NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role')   THEN CREATE ROLE service_role NOLOGIN BYPASSRLS; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='contexto_owner') THEN
      CREATE ROLE contexto_owner LOGIN PASSWORD 'perim' NOSUPERUSER BYPASSRLS CREATEDB; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='otro_rol') THEN
      CREATE ROLE otro_rol NOLOGIN NOSUPERUSER; END IF;
END $$;
GRANT anon, authenticated, service_role, contexto_owner, otro_rol TO postgres;
ALTER DATABASE banco_037 OWNER TO contexto_owner;
ALTER SCHEMA public OWNER TO contexto_owner;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
-- LA CAUSA RAÍZ: toda tabla que cree el dueño nace con DML para los tres roles.
ALTER DEFAULT PRIVILEGES FOR ROLE contexto_owner IN SCHEMA public
    GRANT ALL ON TABLES TO anon, authenticated, service_role;
"""

SEMILLA = """
SET ROLE contexto_owner;
INSERT INTO public.lead_actividad (session_id, lead_email, lead_push, consent_reenganche_at) VALUES
  ('qr-sintetico-1', 'sintetico-1@ejemplo.invalid', '{"endpoint":"https://push.ejemplo.invalid/1"}', now()),
  ('qr-sintetico-2', NULL, NULL, NULL),
  ('qr-sintetico-3', 'sintetico-3@ejemplo.invalid', NULL, NULL);
RESET ROLE;
"""


def monta_banco():
    sql_texto("DROP DATABASE IF EXISTS banco_037;", db="postgres")
    sql_texto("CREATE DATABASE banco_037;", db="postgres")
    rc, out = sql_texto(POSTURA)
    assert rc == 0, out
    # La tabla la crea el DDL REAL del backend, como dueño —igual que en producción—.
    rc, out = sql_texto("SET ROLE contexto_owner;\n" + ";\n".join(lead_ddl_del_repo()) + ";")
    assert rc == 0, f"el _LEAD_ACTIVIDAD_DDL real falló:\n{out[-400:]}"
    rc, out = sql_texto(SEMILLA)
    assert rc == 0, out


# ══ 1 · CONTROL POSITIVO ════════════════════════════════════════════════════════════════
def control_positivo():
    titulo("1 · CONTROL POSITIVO — el banco tiene que REPRODUCIR la exposición de producción")
    s = Suite("control positivo")
    s.afirma("RLS desactivado, como en producción", estado_rls() == "false|false", estado_rls())
    for rol in ("anon", "authenticated"):
        todos = all(psql(f"SELECT has_table_privilege('{rol}','public.lead_actividad','{p}');")[1].strip() == "t"
                    for p in PRIVS)
        s.afirma(f"{rol} tiene los 7 privilegios (igual que producción)", todos)
    s.afirma("anon LEE las 3 filas (correos incluidos)", ve_filas("anon") == 3)
    s.afirma("anon LEE un correo concreto",
             "sintetico-1@ejemplo.invalid" in psql(
                 "SELECT lead_email FROM public.lead_actividad WHERE session_id='qr-sintetico-1';", "anon")[1])
    s.afirma("anon ESCRIBE consentimiento + correo de un tercero (el ataque medido)",
             puede("UPDATE public.lead_actividad SET consent_reenganche_at = now(), "
                   "lead_email = 'tercero@ejemplo.invalid' WHERE session_id = 'qr-sintetico-2';", "anon"))
    s.afirma("anon INSERTA una fila", puede(
        "INSERT INTO public.lead_actividad (session_id) VALUES ('qr-intrusa');", "anon"))
    s.afirma("anon BORRA filas", puede(
        "DELETE FROM public.lead_actividad WHERE session_id = 'qr-intrusa';", "anon"))
    return s


# ══ 2 · DESPUÉS DE LA 037 ═══════════════════════════════════════════════════════════════
def suite_cerrada():
    titulo("2 · DESPUÉS DE LA 037")
    s = Suite("perímetro cerrado")
    s.afirma("RLS activado, SIN FORCE", estado_rls() == "true|false", estado_rls())
    s.afirma("cero políticas", psql(
        "SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='lead_actividad';")[1].strip() == "0")
    rc, out = psql("""SELECT coalesce(string_agg(DISTINCT pg_get_userbyid(a.grantee), ','), '')
                        FROM pg_class t, aclexplode(t.relacl) a
                       WHERE t.oid = 'public.lead_actividad'::regclass;""")
    s.afirma("en el ACL sólo queda el dueño", out.strip() in ("contexto_owner", ""), f"ACL: {out.strip()!r}")

    for rol in ROLES:
        efectivos = [p for p in PRIVS if psql(
            f"SELECT has_table_privilege('{rol}','public.lead_actividad','{p}');")[1].strip() == "t"]
        s.afirma(f"{rol}: 0 de 7 privilegios efectivos", not efectivos, f"conserva {efectivos}")
        s.afirma(f"{rol} NO lee", ve_filas(rol) == -1, f"devolvió {ve_filas(rol)}")
        s.afirma(f"{rol} NO actualiza el consentimiento", not puede(
            "UPDATE public.lead_actividad SET consent_reenganche_at = now() WHERE session_id='qr-sintetico-3';", rol))
        s.afirma(f"{rol} NO inserta", not puede(
            "INSERT INTO public.lead_actividad (session_id) VALUES ('qr-intrusa-2');", rol))
        s.afirma(f"{rol} NO borra", not puede("DELETE FROM public.lead_actividad;", rol))
        s.afirma(f"{rol} NO trunca (lo que RLS sola no cubre)",
                 not puede("TRUNCATE public.lead_actividad;", rol))

    # — el backend (el dueño) sigue trabajando —
    s.afirma("el DUEÑO lee sus 3 filas", ve_filas("contexto_owner") == 3)
    s.afirma("el DUEÑO inserta, actualiza y borra", puede(
        """INSERT INTO public.lead_actividad (session_id) VALUES ('qr-dueno');
           UPDATE public.lead_actividad SET ultima_actividad = now() WHERE session_id = 'qr-dueno';
           DELETE FROM public.lead_actividad WHERE session_id = 'qr-dueno';""", "contexto_owner"))
    rc, out = sql_texto("SET ROLE contexto_owner;\n" + ";\n".join(lead_ddl_del_repo()) + ";")
    s.afirma("el DDL en runtime (ensure_lead_actividad) sigue funcionando", rc == 0, out[-300:])
    rc, out = sql_texto("SET ROLE contexto_owner;\nALTER TABLE public.lead_actividad "
                        "ADD COLUMN IF NOT EXISTS reenganche_cerrado_en timestamptz;")
    s.afirma("se puede añadir la columna de TR-2 (reenganche_cerrado_en)", rc == 0, out[-300:])
    s.afirma("y nace cerrada para anon", psql(
        "SELECT has_column_privilege('anon','public.lead_actividad','reenganche_cerrado_en','SELECT');"
    )[1].strip() == "f")

    # — RLS aporta algo por encima del REVOKE —
    psql("GRANT SELECT ON public.lead_actividad TO anon;", "contexto_owner")
    s.afirma("RESISTE UN RE-GRANT: con SELECT devuelto a anon, ve 0 filas", ve_filas("anon") == 0,
             f"vio {ve_filas('anon')}")
    psql("REVOKE ALL PRIVILEGES ON public.lead_actividad FROM anon;", "contexto_owner")
    return s


# ══ 3 · COMPUERTAS FAIL-CLOSED ══════════════════════════════════════════════════════════
def compuertas():
    titulo("3 · COMPUERTAS FAIL-CLOSED — cada precondición rota aborta SIN tocar nada")
    s = Suite("compuertas")
    casos = [
        ("política existente", "CREATE POLICY p_sonda ON public.lead_actividad FOR SELECT USING (true);",
         "contexto_owner", "ya existen"),
        ("publicación de replicación", "CREATE PUBLICATION supabase_realtime FOR TABLE public.lead_actividad;",
         None, "publicación de replicación"),
        ("vista dependiente", "CREATE VIEW public.v_sonda AS SELECT session_id FROM public.lead_actividad;",
         "contexto_owner", "vistas que dependen"),
        ("función que la menciona",
         "CREATE FUNCTION public.f_sonda() RETURNS bigint LANGUAGE sql AS "
         "$$ SELECT count(*) FROM public.lead_actividad $$;", "contexto_owner", "funciones que mencionan"),
    ]
    for nombre, prepara, rol, mensaje in casos:
        monta_banco()
        rc, out = sql_texto(prepara, rol=rol)
        assert rc == 0, f"no se pudo preparar «{nombre}»:\n{out}"
        acl_antes = psql("SELECT relacl::text FROM pg_class WHERE oid='public.lead_actividad'::regclass;")[1].strip()
        rc, out = aplica_037()
        acl_despues = psql("SELECT relacl::text FROM pg_class WHERE oid='public.lead_actividad'::regclass;")[1].strip()
        s.afirma(f"{nombre} → ABORTA", rc != 0 and mensaje in out, out.strip()[-220:])
        s.afirma(f"{nombre} → nada cambió (RLS off, ACL idéntico)",
                 estado_rls() == "false|false" and acl_antes == acl_despues, f"{estado_rls()} · {acl_despues}")
        psql("DROP PUBLICATION IF EXISTS supabase_realtime;")

    # Dueño distinto: la tabla es de `otro_rol` y la aplica `contexto_owner`.
    monta_banco()
    rc, out = sql_texto("ALTER TABLE public.lead_actividad OWNER TO otro_rol;")
    assert rc == 0, out
    rc, out = aplica_037()
    s.afirma("dueño distinto de quien aplica → ABORTA", rc != 0 and "el dueño es" in out, out.strip()[-220:])
    s.afirma("dueño distinto → nada cambió", estado_rls() == "false|false", estado_rls())
    return s


# ══ 4 · MUTACIONES ══════════════════════════════════════════════════════════════════════
def mutaciones():
    titulo("4 · MUTACIONES — la propia 037 tiene que negarse a confirmar")
    s = Suite("mutaciones")
    original = (MIGRACIONES / M037).read_text(encoding="utf-8")

    monta_banco()
    mut = original.replace("ALTER TABLE public.lead_actividad ENABLE ROW LEVEL SECURITY;\n", "")
    assert mut != original, "M1 no encontró el ENABLE"
    rc, out = aplica_037(texto=mut)
    s.afirma("M1 · sin ENABLE RLS la 037 ABORTA", rc != 0 and "RLS no quedó activado" in out, out[-200:])
    s.afirma("M1 · y no deja nada a medias (RLS off)", estado_rls() == "false|false")

    monta_banco()
    mut = original.replace("'REVOKE ALL PRIVILEGES ON TABLE public.lead_actividad FROM %I'",
                           "'SELECT 1 /* M2 */ -- %I'")
    assert mut != original, "M2 no encontró el REVOKE"
    rc, out = aplica_037(texto=mut)
    s.afirma("M2 · sin REVOKE la 037 ABORTA", rc != 0 and "quedan privilegios en pie" in out, out[-200:])
    s.afirma("M2 · y el ENABLE también se deshace (transacción única)", estado_rls() == "false|false")

    monta_banco()
    mut = original.replace("ALTER TABLE public.lead_actividad ENABLE ROW LEVEL SECURITY;\n",
                           "ALTER TABLE public.lead_actividad ENABLE ROW LEVEL SECURITY;\n"
                           "ALTER TABLE public.lead_actividad FORCE ROW LEVEL SECURITY;\n")
    rc, out = aplica_037(texto=mut)
    s.afirma("M3 · con FORCE la 037 ABORTA", rc != 0 and "apareció FORCE" in out, out[-200:])

    monta_banco()
    assert aplica_037()[0] == 0
    sql_texto("""ALTER TABLE public.lead_actividad DISABLE ROW LEVEL SECURITY;
                 GRANT ALL PRIVILEGES ON TABLE public.lead_actividad TO anon, authenticated, service_role;""")
    s.afirma("M4 · el ROLLBACK documentado reabre la exposición (anon vuelve a leer)",
             ve_filas("anon") == 3, f"vio {ve_filas('anon')}")
    return s


def main():
    if not (MIGRACIONES / M037).exists():
        print(f"{ROJO}falta {M037}{FIN}")
        return 2
    titulo(f"0 · BANCO — {CONTENEDOR}")
    monta_banco()
    print("  " + psql("SELECT version();")[1].strip()[:70])

    s1 = control_positivo()
    if not s1.verde:
        print(f"\n{ROJO}EL CONTROL POSITIVO NO SE REPRODUJO.{FIN} El banco no mide lo que dice medir.")
        return 1

    monta_banco()
    titulo("· se aplica la 037 ·")
    rc, out = aplica_037()
    print(out.strip()[-400:])
    if rc != 0:
        print(f"{ROJO}la 037 no aplicó{FIN}")
        return 1
    s2 = suite_cerrada()

    titulo("2b · IDEMPOTENCIA")
    rc2, out2 = aplica_037()
    s2.afirma("la 037 es idempotente", rc2 == 0, out2.strip()[-200:])
    s2.afirma("y sigue cerrada", estado_rls() == "true|false" and ve_filas("anon") == -1)

    s3 = compuertas()
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
