# -*- coding: utf-8 -*-
"""Plan 1.1 · TR-5 · banco aislado para la migración 038 (`consent_grant`).

    python tests/arnes_perimetro_038.py
    PERIM_CONTENEDOR=perim-pg15 python tests/arnes_perimetro_038.py

No es una prueba de pytest: necesita Docker y un PostgreSQL limpio, igual que el de la 037.
Producción corre PostgreSQL 17 y el CI corre 15: se corre en los dos.

## FIDELIDAD

  · El dueño es `contexto_owner` (NOSUPERUSER + BYPASSRLS), el doble del `postgres` de
    producción. Un superusuario se salta todo y probaría el cierre por la razón equivocada.
  · La causa raíz se reproduce: `ALTER DEFAULT PRIVILEGES … GRANT ALL ON TABLES TO anon,
    authenticated, service_role`. Toda tabla que cree el dueño NACE expuesta, salvo que la 038
    la cierre en su misma transacción.

## CONTROL POSITIVO

Antes de aplicar la 038 el banco EXIGE ver la exposición: una tabla sonda creada por el dueño
tiene los 7 privilegios para anon y anon la lee. Si no, se detiene.

## LO QUE SE PRUEBA DESPUÉS

  · RLS ON, sin FORCE, 0 políticas; en el ACL sólo queda el dueño;
  · anon, authenticated y service_role: 0 de 7 privilegios, y ninguno lee, inserta, actualiza,
    borra ni trunca; el dueño —el backend— lee y escribe;
  · RESISTE UN RE-GRANT (RLS aporta algo por encima del REVOKE);
  · sin secuencias; idempotencia;
  · compuertas fail-closed (política, publicación, vista, función, dueño distinto) que abortan
    sin tocar nada; y mutaciones que la propia 038 se niega a confirmar.

Datos sintéticos (`qr-sintetico-*`). Sobre producción, nada.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

CONTENEDOR = os.environ.get("PERIM_CONTENEDOR", "perim-pg")
RAIZ = pathlib.Path(__file__).resolve().parent.parent
M038 = RAIZ / "migrations" / "038_consent_grant_reenganche.sql"
BANCO = "banco_038"

ROJO, VERDE, GRIS, FIN = "\033[31m", "\033[32m", "\033[90m", "\033[0m"
ROLES = ("anon", "authenticated", "service_role")
PRIVS = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
T = "public.consent_grant"


def sql_texto(texto, db=BANCO, rol=None, detener=True):
    if rol:
        texto = "SET ROLE " + rol + ";\n" + texto
    p = subprocess.run(
        ["docker", "exec", "-i", CONTENEDOR, "psql", "-U", "postgres", "-d", db, "-q"]
        + (["-v", "ON_ERROR_STOP=1"] if detener else []),
        input=texto, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def psql(sql, rol=None, db=BANCO):
    if rol:
        sql = f"SET ROLE {rol};\n{sql}"
    p = subprocess.run(
        ["docker", "exec", "-i", CONTENEDOR, "psql", "-U", "postgres", "-d", db, "-q", "-t", "-A"],
        input=sql, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def aplica_038(rol="contexto_owner", texto=None):
    return sql_texto(texto if texto is not None else M038.read_text(encoding="utf-8"), rol=rol)


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


def ve_filas(rol, tabla=T):
    rc, out = psql(f"SELECT count(*) FROM {tabla};", rol)
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
    rc, out = psql(f"SELECT relrowsecurity::text || '|' || relforcerowsecurity::text FROM pg_class "
                   f"WHERE oid = to_regclass('{T}');")
    return out.strip() or "sin tabla"


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
ALTER DATABASE banco_038 OWNER TO contexto_owner;
ALTER SCHEMA public OWNER TO contexto_owner;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
-- LA CAUSA RAÍZ: toda tabla que cree el dueño nace con DML para los tres roles.
ALTER DEFAULT PRIVILEGES FOR ROLE contexto_owner IN SCHEMA public
    GRANT ALL ON TABLES TO anon, authenticated, service_role;
"""

FILA = ("INSERT INTO public.consent_grant (contract_version, session_id, principal_kind, "
        "principal_session_id, proof_basis, audience, purpose, action, channel, mode, expires_at, "
        "provenance) VALUES ('consent_grant_v0', '{sid}', 'PSEUDONYMOUS_SESSION_PRINCIPAL', '{sid}', "
        "'RESUME_SECRET_POSSESSION', 'PRINCIPAL_SELF', 'REENGAGEMENT', 'NOTIFY_VERIFIED_UPDATE', "
        "'PUSH', 'once', now() + interval '30 days', '{{\"surface\":\"P5\"}}');")


def monta_banco():
    sql_texto("DROP DATABASE IF EXISTS banco_038;", db="postgres")
    sql_texto("CREATE DATABASE banco_038;", db="postgres")
    rc, out = sql_texto(POSTURA)
    assert rc == 0, out


def control_positivo():
    titulo("1 · CONTROL POSITIVO — una tabla nueva del dueño NACE expuesta en este banco")
    s = Suite("control positivo")
    rc, out = sql_texto("CREATE TABLE public.sonda (x int); INSERT INTO public.sonda VALUES (1),(2);",
                        rol="contexto_owner")
    assert rc == 0, out
    for rol in ROLES:
        todos = all(psql(f"SELECT has_table_privilege('{rol}','public.sonda','{p}');")[1].strip() == "t"
                    for p in PRIVS)
        s.afirma(f"{rol} hereda los 7 privilegios sobre una tabla nueva", todos)
    s.afirma("anon LEE la sonda", ve_filas("anon", "public.sonda") == 2)
    s.afirma("anon ESCRIBE en la sonda", puede("INSERT INTO public.sonda VALUES (3);", "anon"))
    sql_texto("DROP TABLE public.sonda;", rol="contexto_owner")
    return s


def suite_cerrada():
    titulo("2 · DESPUÉS DE LA 038")
    s = Suite("perímetro cerrado")
    s.afirma("RLS activado, SIN FORCE", estado_rls() == "true|false", estado_rls())
    s.afirma("cero políticas", psql(
        "SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='consent_grant';"
    )[1].strip() == "0")
    rc, out = psql(f"""SELECT coalesce(string_agg(DISTINCT CASE WHEN a.grantee = 0 THEN 'PUBLIC'
                              ELSE pg_get_userbyid(a.grantee) END, ','), '')
                        FROM pg_class t, aclexplode(t.relacl) a WHERE t.oid = '{T}'::regclass;""")
    s.afirma("en el ACL sólo queda el dueño", out.strip() in ("contexto_owner", ""), f"ACL: {out.strip()!r}")

    rc, out = sql_texto(FILA.format(sid="qr-sintetico-1") + FILA.format(sid="qr-sintetico-2"),
                        rol="contexto_owner")
    s.afirma("el DUEÑO inserta grants", rc == 0, out[-300:])
    for rol in ROLES:
        efectivos = [p for p in PRIVS if psql(
            f"SELECT has_table_privilege('{rol}','{T}','{p}');")[1].strip() == "t"]
        s.afirma(f"{rol}: 0 de 7 privilegios efectivos", not efectivos, f"conserva {efectivos}")
        s.afirma(f"{rol} NO lee", ve_filas(rol) == -1, f"devolvió {ve_filas(rol)}")
        s.afirma(f"{rol} NO fabrica un grant", not puede(FILA.format(sid="qr-intruso"), rol))
        s.afirma(f"{rol} NO reactiva un grant (revoked_at → NULL)", not puede(
            f"UPDATE {T} SET revoked_at = NULL, used_at = NULL;", rol))
        s.afirma(f"{rol} NO borra", not puede(f"DELETE FROM {T};", rol))
        s.afirma(f"{rol} NO trunca (lo que RLS sola no cubre)", not puede(f"TRUNCATE {T};", rol))

    s.afirma("el DUEÑO lee sus 2 grants", ve_filas("contexto_owner") == 2)
    s.afirma("el DUEÑO consume, revoca y borra", puede(
        f"""UPDATE {T} SET used_at = now() WHERE session_id = 'qr-sintetico-1';
            UPDATE {T} SET revoked_at = now() WHERE session_id = 'qr-sintetico-2';
            DELETE FROM {T} WHERE session_id = 'qr-sintetico-2';""", "contexto_owner"))
    s.afirma("sin secuencias", psql(
        f"SELECT count(*) FROM pg_class s JOIN pg_depend d ON d.objid = s.oid "
        f"WHERE s.relkind = 'S' AND d.refobjid = '{T}'::regclass;")[1].strip() == "0")

    psql(f"GRANT SELECT ON {T} TO anon;", "contexto_owner")
    s.afirma("RESISTE UN RE-GRANT: con SELECT devuelto a anon, ve 0 filas", ve_filas("anon") == 0,
             f"vio {ve_filas('anon')}")
    psql(f"REVOKE ALL PRIVILEGES ON {T} FROM anon;", "contexto_owner")
    return s


def compuertas():
    titulo("3 · COMPUERTAS FAIL-CLOSED — cada precondición rota aborta SIN tocar nada")
    s = Suite("compuertas")
    casos = [
        ("política existente", f"CREATE POLICY p_sonda ON {T} FOR SELECT USING (true);",
         "contexto_owner", "ya existen"),
        ("publicación de replicación", f"CREATE PUBLICATION supabase_realtime FOR TABLE {T};",
         None, "publicación de replicación"),
        ("vista dependiente", f"CREATE VIEW public.v_sonda AS SELECT grant_id FROM {T};",
         "contexto_owner", "vistas que dependen"),
    ]
    for nombre, prepara, rol, mensaje in casos:
        monta_banco()
        assert aplica_038()[0] == 0
        rc, out = sql_texto(prepara, rol=rol)
        assert rc == 0, f"no se pudo preparar «{nombre}»:\n{out}"
        acl_antes = psql(f"SELECT relacl::text FROM pg_class WHERE oid='{T}'::regclass;")[1].strip()
        rc, out = aplica_038()
        acl_despues = psql(f"SELECT relacl::text FROM pg_class WHERE oid='{T}'::regclass;")[1].strip()
        s.afirma(f"{nombre} → ABORTA", rc != 0 and mensaje in out, out.strip()[-220:])
        s.afirma(f"{nombre} → nada cambió (ACL idéntico)", acl_antes == acl_despues, acl_despues)
        psql("DROP PUBLICATION IF EXISTS supabase_realtime;")

    monta_banco()
    rc, out = sql_texto("CREATE FUNCTION public.f_sonda() RETURNS bigint LANGUAGE sql AS "
                        "$$ SELECT 1 /* consent_grant */ $$;", rol="contexto_owner")
    assert rc == 0, out
    rc, out = aplica_038()
    s.afirma("función que la menciona → ABORTA (antes de crear nada)",
             rc != 0 and "funciones que mencionan" in out, out.strip()[-220:])
    s.afirma("función que la menciona → la tabla NO se creó", estado_rls() == "sin tabla", estado_rls())

    monta_banco()
    assert aplica_038()[0] == 0
    rc, out = sql_texto(f"ALTER TABLE {T} OWNER TO otro_rol;")
    assert rc == 0, out
    rc, out = aplica_038()
    s.afirma("dueño distinto de quien aplica → ABORTA", rc != 0 and "el dueño es" in out, out.strip()[-220:])
    return s


def mutaciones():
    titulo("4 · MUTACIONES — la propia 038 tiene que negarse a confirmar")
    s = Suite("mutaciones")
    original = M038.read_text(encoding="utf-8")

    monta_banco()
    mut = original.replace("ALTER TABLE public.consent_grant ENABLE ROW LEVEL SECURITY;\n", "")
    assert mut != original, "M1 no encontró el ENABLE"
    rc, out = aplica_038(texto=mut)
    s.afirma("M1 · sin ENABLE RLS la 038 ABORTA", rc != 0 and "RLS no quedó activado" in out, out[-200:])
    s.afirma("M1 · y la tabla NO queda creada (transacción única)", estado_rls() == "sin tabla", estado_rls())

    monta_banco()
    mut = original.replace("'REVOKE ALL PRIVILEGES ON TABLE public.consent_grant FROM %I'",
                           "'SELECT 1 /* M2 */ -- %I'")
    assert mut != original, "M2 no encontró el REVOKE"
    rc, out = aplica_038(texto=mut)
    s.afirma("M2 · sin REVOKE la 038 ABORTA", rc != 0 and "quedan privilegios en pie" in out, out[-200:])
    s.afirma("M2 · y no queda una tabla expuesta a medias", estado_rls() == "sin tabla", estado_rls())

    monta_banco()
    mut = original.replace("ALTER TABLE public.consent_grant ENABLE ROW LEVEL SECURITY;\n",
                           "ALTER TABLE public.consent_grant ENABLE ROW LEVEL SECURITY;\n"
                           "ALTER TABLE public.consent_grant FORCE ROW LEVEL SECURITY;\n")
    rc, out = aplica_038(texto=mut)
    s.afirma("M3 · con FORCE la 038 ABORTA", rc != 0 and "apareció FORCE" in out, out[-200:])

    monta_banco()
    mut = original.replace("    REVOKE ALL PRIVILEGES ON TABLE public.consent_grant FROM PUBLIC;\n",
                           "    GRANT SELECT ON TABLE public.consent_grant TO PUBLIC;\n")
    assert mut != original, "M4 no encontró el REVOKE de PUBLIC"
    rc, out = aplica_038(texto=mut)
    s.afirma("M4 · con SELECT a PUBLIC la 038 ABORTA", rc != 0 and "PUBLIC" in out, out[-200:])
    return s


def main():
    if not M038.exists():
        print(f"{ROJO}falta {M038.name}{FIN}")
        return 2
    titulo(f"0 · BANCO — {CONTENEDOR}")
    monta_banco()
    print("  " + psql("SELECT version();")[1].strip()[:70])

    s1 = control_positivo()
    if not s1.verde:
        print(f"\n{ROJO}EL CONTROL POSITIVO NO SE REPRODUJO.{FIN} El banco no mide lo que dice medir.")
        return 1

    monta_banco()
    titulo("· se aplica la 038 ·")
    rc, out = aplica_038()
    print(out.strip()[-400:])
    if rc != 0:
        print(f"{ROJO}la 038 no aplicó{FIN}")
        return 1
    s2 = suite_cerrada()

    titulo("2b · IDEMPOTENCIA")
    rc2, out2 = aplica_038()
    s2.afirma("la 038 es idempotente", rc2 == 0, out2.strip()[-200:])
    s2.afirma("y sigue cerrada", estado_rls() == "true|false" and ve_filas("anon") == -1)
    s2.afirma("y no tocó los grants que había", ve_filas("contexto_owner") == 1)

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
