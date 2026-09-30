# -*- coding: utf-8 -*-
"""AURA-CACHE-PERIMETER · banco aislado para la migración 039.

    python tests/arnes_perimetro_039.py
    PERIM_CONTENEDOR=perim-pg15 python tests/arnes_perimetro_039.py

No es una prueba de pytest: necesita Docker y un PostgreSQL limpio, igual que los arneses de la
032, 033, 035 y 037. Producción corre PostgreSQL 17.6 y el CI corre 15: se corre en los dos.

## FIDELIDAD

  · El dueño es `contexto_owner` (NOSUPERUSER + BYPASSRLS), el doble del `postgres` de
    producción, que no es superusuario. Un superusuario se salta todo y demostraría que el
    cambio «no rompe nada» por la razón equivocada.
  · La causa raíz se reproduce: `ALTER DEFAULT PRIVILEGES … GRANT ALL ON TABLES TO anon,
    authenticated, service_role`, así la tabla NACE con la exposición medida en producción.
  · La tabla la crea el `_AURA_CACHE_DDL` REAL de `app/routers/assets.py`, leído por AST.
  · El backend se imita con sus sentencias reales: la LECTURA de `_pois_geo_cached` (TTL de
    30 días) y el UPSERT con `CAST(:pois AS jsonb)` (PR #171). Desde MAP-SOURCE-BOUNDARY
    (2026-09-30) ninguna de las dos existe en el producto —/aura sale de la capa propia—; se
    conservan aquí como el patrón de acceso que la 039 tenía que seguir permitiendo al dueño.

## CONTROL POSITIVO

Antes de la 039 el banco EXIGE que el defecto se reproduzca: `anon` lee la caché, ENVENENA la
de un inmueble ajeno (una fila «fresca» que la lectura del backend serviría) y borra y trunca. Si
no, se detiene: una prueba que pasa porque el defecto no estaba no prueba nada.

## LO QUE SE PRUEBA DESPUÉS

  · `anon`, `authenticated` y `service_role` sin ningún privilegio (tabla y columnas) y sin poder
    leer, insertar, actualizar, borrar ni truncar;
  · `PUBLIC` sin nada, y un GRANT a PUBLIC posterior lo retira la 039 al reaplicarse;
  · un GRANT por columna previo desaparece con la 039;
  · el dueño —el backend— lee, hace el UPSERT de la caché, actualiza y borra, y el DDL en runtime
    (`ensure_aura_cache_table`) sigue funcionando;
  · RESISTE UN RE-GRANT: aunque alguien devuelva SELECT a anon, ve 0 filas (lo que aporta RLS);
  · idempotencia;
  · compuertas fail-closed: política, publicación, vista dependiente, función que la mencione y
    dueño distinto ABORTAN sin tocar nada;
  · mutaciones: sin ENABLE, sin REVOKE, con FORCE, o sin el REVOKE a PUBLIC (con PUBLIC
    concedido), la propia 039 se niega a confirmar; y el ROLLBACK documentado reabre.

Datos sintéticos (`Lugar sintético …`). Sobre producción, nada.
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
M039 = "039_aura_pois_cache_perimeter.sql"
BANCO = "banco_039"
T = "public.aura_pois_cache"
A1, A2, A3 = ("00000000-0000-4000-8000-0000000000a1", "00000000-0000-4000-8000-0000000000a2",
              "00000000-0000-4000-8000-0000000000a3")
INTRUSO = "00000000-0000-4000-8000-00000000bad0"

ROJO, VERDE, GRIS, FIN = "\033[31m", "\033[32m", "\033[90m", "\033[0m"
ROLES = ("anon", "authenticated", "service_role")
PRIVS = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")

# La lectura y el UPSERT del backend, con los binds ya resueltos (lo que Postgres recibe).
LECTURA_BACKEND = (f"SELECT pois FROM {T} WHERE activo_id = '{A1}' "
                   "AND computed_at > now() - (30 * interval '1 day');")
UPSERT_BACKEND = (f"INSERT INTO {T} (activo_id, pois, computed_at) "
                  f"VALUES ('{A1}', CAST('[{{\"nombre\":\"Lugar sintético renovado\"}}]' AS jsonb), now()) "
                  "ON CONFLICT (activo_id) DO UPDATE SET pois = EXCLUDED.pois, computed_at = now();")


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


def aplica_039(rol="contexto_owner", texto=None):
    cuerpo = texto if texto is not None else (MIGRACIONES / M039).read_text(encoding="utf-8")
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
    rc, out = psql(f"SELECT count(*) FROM {T};", rol)
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
    return psql(f"SELECT relrowsecurity::text || '|' || relforcerowsecurity::text FROM pg_class "
                f"WHERE oid = '{T}'::regclass;")[1].strip()


def acl_externo():
    """Grantees externos en el ACL de la tabla y de sus columnas (PUBLIC incluido)."""
    return psql(f"""
      SELECT coalesce(string_agg(DISTINCT x.q, ','), '') FROM (
        SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS q
          FROM pg_class c, aclexplode(c.relacl) a WHERE c.oid = '{T}'::regclass
        UNION ALL
        SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END
          FROM pg_attribute att, aclexplode(att.attacl) a
         WHERE att.attrelid = '{T}'::regclass AND att.attnum > 0
      ) x WHERE x.q IN ('anon','authenticated','service_role','PUBLIC');""")[1].strip()


def aura_ddl_del_repo():
    """`_AURA_CACHE_DDL` de app/routers/assets.py, por AST y sin importar el módulo."""
    arbol = ast.parse((RAIZ / "app" / "routers" / "assets.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_AURA_CACHE_DDL" for t in nodo.targets):
            return [ast.literal_eval(e) for e in nodo.value.elts]
    raise SystemExit("no se encontró _AURA_CACHE_DDL en app/routers/assets.py")


# ══ el banco ════════════════════════════════════════════════════════════════════════════
POSTURA = f"""
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
ALTER DATABASE {BANCO} OWNER TO contexto_owner;
ALTER SCHEMA public OWNER TO contexto_owner;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
-- LA CAUSA RAÍZ: toda tabla que cree el dueño nace con DML para los tres roles.
ALTER DEFAULT PRIVILEGES FOR ROLE contexto_owner IN SCHEMA public
    GRANT ALL ON TABLES TO anon, authenticated, service_role;
"""

SEMILLA = f"""
SET ROLE contexto_owner;
INSERT INTO {T} (activo_id, pois, computed_at) VALUES
  ('{A1}', '[{{"nombre":"Lugar sintético 1","lat":-0.18,"lon":-78.48}}]', now()),
  ('{A2}', '[{{"nombre":"Lugar sintético 2","lat":-0.19,"lon":-78.47}}]', now()),
  ('{A3}', '[{{"nombre":"Lugar sintético 3","lat":-0.20,"lon":-78.46}}]', now() - interval '40 days');
RESET ROLE;
"""


def monta_banco():
    sql_texto(f"DROP DATABASE IF EXISTS {BANCO};", db="postgres")
    sql_texto(f"CREATE DATABASE {BANCO};", db="postgres")
    rc, out = sql_texto(POSTURA)
    assert rc == 0, out
    # La tabla la crea el DDL REAL del backend, como dueño —igual que en producción—.
    rc, out = sql_texto("SET ROLE contexto_owner;\n" + ";\n".join(aura_ddl_del_repo()) + ";")
    assert rc == 0, f"el _AURA_CACHE_DDL real falló:\n{out[-400:]}"
    rc, out = sql_texto(SEMILLA)
    assert rc == 0, out


# ══ 1 · CONTROL POSITIVO ════════════════════════════════════════════════════════════════
def control_positivo():
    titulo("1 · CONTROL POSITIVO — el banco tiene que REPRODUCIR la exposición de producción")
    s = Suite("control positivo")
    s.afirma("RLS desactivado, como en producción", estado_rls() == "false|false", estado_rls())
    for rol in ROLES:
        todos = all(psql(f"SELECT has_table_privilege('{rol}','{T}','{p}');")[1].strip() == "t" for p in PRIVS)
        s.afirma(f"{rol} tiene los 7 privilegios (igual que producción)", todos)
    s.afirma("anon LEE las 3 entradas", ve_filas("anon") == 3)
    s.afirma("anon ENVENENA la caché de un inmueble (fila fresca con un «lugar» inventado)", puede(
        f"INSERT INTO {T} (activo_id, pois, computed_at) VALUES "
        f"('{INTRUSO}', '[{{\"nombre\":\"Lugar INVENTADO\",\"lat\":0,\"lon\":0}}]', now());", "anon"))
    s.afirma("y la LECTURA del backend lo serviría (TTL de 30 días)",
             "Lugar INVENTADO" in psql(f"SELECT pois FROM {T} WHERE activo_id = '{INTRUSO}' "
                                       "AND computed_at > now() - (30 * interval '1 day');", "contexto_owner")[1])
    s.afirma("anon REESCRIBE la entrada de otro inmueble", puede(
        f"UPDATE {T} SET pois = '[{{\"nombre\":\"Otro INVENTADO\"}}]' WHERE activo_id = '{A2}';", "anon"))
    s.afirma("anon BORRA entradas", puede(f"DELETE FROM {T} WHERE activo_id = '{INTRUSO}';", "anon"))
    return s


# ══ 2 · DESPUÉS DE LA 039 ═══════════════════════════════════════════════════════════════
def suite_cerrada():
    titulo("2 · DESPUÉS DE LA 039")
    s = Suite("perímetro cerrado")
    s.afirma("RLS activado, SIN FORCE", estado_rls() == "true|false", estado_rls())
    s.afirma("cero políticas", psql(
        "SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='aura_pois_cache';")[1].strip() == "0")
    s.afirma("ningún grantee externo en el ACL (tabla ni columnas; PUBLIC incluido)", acl_externo() == "",
             f"quedan: {acl_externo()!r}")
    for rol in ROLES:
        efectivos = [p for p in PRIVS if psql(f"SELECT has_table_privilege('{rol}','{T}','{p}');")[1].strip() == "t"]
        s.afirma(f"{rol}: 0 de 7 privilegios efectivos", not efectivos, f"conserva {efectivos}")
        s.afirma(f"{rol}: 0 privilegios de columna", psql(
            f"SELECT has_any_column_privilege('{rol}','{T}','SELECT,INSERT,UPDATE,REFERENCES');")[1].strip() == "f")
        s.afirma(f"{rol} NO lee", ve_filas(rol) == -1, f"devolvió {ve_filas(rol)}")
        s.afirma(f"{rol} NO envenena (INSERT)", not puede(
            f"INSERT INTO {T} (activo_id, pois) VALUES ('{INTRUSO}', '[]');", rol))
        s.afirma(f"{rol} NO reescribe (UPDATE)", not puede(f"UPDATE {T} SET pois = '[]';", rol))
        s.afirma(f"{rol} NO borra", not puede(f"DELETE FROM {T};", rol))
        s.afirma(f"{rol} NO trunca (lo que RLS sola no cubre)", not puede(f"TRUNCATE {T};", rol))

    # — el backend (el dueño) sigue trabajando: /aura por el backend —
    s.afirma("el DUEÑO ve sus 3 entradas", ve_filas("contexto_owner") == 3)
    rc, out = psql(LECTURA_BACKEND, "contexto_owner")
    s.afirma("la LECTURA real de _pois_geo_cached (TTL 30 d) sirve la entrada fresca",
             "Lugar sintético 1" in out, out[-200:])
    rc, out = psql(f"SELECT count(*) FROM {T} WHERE activo_id = '{A3}' "
                   "AND computed_at > now() - (30 * interval '1 day');", "contexto_owner")
    s.afirma("y NO sirve la caducada (40 días)", out.strip() == "0", out)
    s.afirma("el UPSERT del backend (CAST AS jsonb, PR #171) escribe y actualiza", puede(UPSERT_BACKEND, "contexto_owner")
             and "renovado" in psql(LECTURA_BACKEND, "contexto_owner")[1])
    s.afirma("el DUEÑO inserta, actualiza y borra", puede(
        f"""INSERT INTO {T} (activo_id, pois) VALUES ('{INTRUSO}', '[]');
            UPDATE {T} SET computed_at = now() WHERE activo_id = '{INTRUSO}';
            DELETE FROM {T} WHERE activo_id = '{INTRUSO}';""", "contexto_owner"))
    rc, out = sql_texto("SET ROLE contexto_owner;\n" + ";\n".join(aura_ddl_del_repo()) + ";")
    s.afirma("el DDL en runtime (ensure_aura_cache_table) sigue funcionando", rc == 0, out[-300:])

    # — RLS aporta algo por encima del REVOKE —
    psql(f"GRANT SELECT ON {T} TO anon;", "contexto_owner")
    s.afirma("RESISTE UN RE-GRANT: con SELECT devuelto a anon, ve 0 filas", ve_filas("anon") == 0,
             f"vio {ve_filas('anon')}")
    psql(f"REVOKE ALL PRIVILEGES ON {T} FROM anon;", "contexto_owner")
    return s


# ══ 2c · PUBLIC Y COLUMNAS ══════════════════════════════════════════════════════════════
def publico_y_columnas():
    titulo("2c · PUBLIC Y GRANTS DE COLUMNA — lo que un REVOKE a tres roles no cubriría")
    s = Suite("PUBLIC y columnas")
    monta_banco()
    rc, out = sql_texto(f"GRANT SELECT ON {T} TO PUBLIC; GRANT SELECT (pois), UPDATE (pois) ON {T} TO anon;",
                        rol="contexto_owner")
    assert rc == 0, out
    s.afirma("preparado: PUBLIC y un GRANT de columna a anon", "PUBLIC" in acl_externo() and "anon" in acl_externo(),
             acl_externo())
    rc, out = aplica_039()
    s.afirma("la 039 aplica", rc == 0, out[-300:])
    s.afirma("PUBLIC y el GRANT de columna desaparecen", acl_externo() == "", f"quedan: {acl_externo()!r}")
    s.afirma("anon ya no lee ni la columna", ve_filas("anon") == -1)
    return s


# ══ 3 · COMPUERTAS FAIL-CLOSED ══════════════════════════════════════════════════════════
def compuertas():
    titulo("3 · COMPUERTAS FAIL-CLOSED — cada precondición rota aborta SIN tocar nada")
    s = Suite("compuertas")
    casos = [
        ("política existente", f"CREATE POLICY p_sonda ON {T} FOR SELECT USING (true);",
         "contexto_owner", "ya existen"),
        ("publicación de replicación", f"CREATE PUBLICATION supabase_realtime FOR TABLE {T};",
         None, "publicación de replicación"),
        ("vista dependiente", f"CREATE VIEW public.v_sonda AS SELECT activo_id FROM {T};",
         "contexto_owner", "vistas que dependen"),
        ("función que la menciona",
         "CREATE FUNCTION public.f_sonda() RETURNS bigint LANGUAGE sql AS "
         f"$$ SELECT count(*) FROM {T} $$;", "contexto_owner", "funciones que mencionan"),
    ]
    for nombre, prepara, rol, mensaje in casos:
        monta_banco()
        rc, out = sql_texto(prepara, rol=rol)
        assert rc == 0, f"no se pudo preparar «{nombre}»:\n{out}"
        acl_antes = psql(f"SELECT relacl::text FROM pg_class WHERE oid='{T}'::regclass;")[1].strip()
        rc, out = aplica_039()
        acl_despues = psql(f"SELECT relacl::text FROM pg_class WHERE oid='{T}'::regclass;")[1].strip()
        s.afirma(f"{nombre} → ABORTA", rc != 0 and mensaje in out, out.strip()[-220:])
        s.afirma(f"{nombre} → nada cambió (RLS off, ACL idéntico)",
                 estado_rls() == "false|false" and acl_antes == acl_despues, f"{estado_rls()} · {acl_despues}")
        psql("DROP PUBLICATION IF EXISTS supabase_realtime;")

    monta_banco()
    rc, out = sql_texto(f"ALTER TABLE {T} OWNER TO otro_rol;")
    assert rc == 0, out
    rc, out = aplica_039()
    s.afirma("dueño distinto de quien aplica → ABORTA", rc != 0 and "el dueño es" in out, out.strip()[-220:])
    s.afirma("dueño distinto → nada cambió", estado_rls() == "false|false", estado_rls())
    return s


# ══ 4 · MUTACIONES ══════════════════════════════════════════════════════════════════════
def mutaciones():
    titulo("4 · MUTACIONES — la propia 039 tiene que negarse a confirmar")
    s = Suite("mutaciones")
    original = (MIGRACIONES / M039).read_text(encoding="utf-8")

    monta_banco()
    mut = original.replace(f"ALTER TABLE {T} ENABLE ROW LEVEL SECURITY;\n", "")
    assert mut != original, "M1 no encontró el ENABLE"
    rc, out = aplica_039(texto=mut)
    s.afirma("M1 · sin ENABLE RLS la 039 ABORTA", rc != 0 and "RLS no quedó activado" in out, out[-200:])
    s.afirma("M1 · y no deja nada a medias (RLS off)", estado_rls() == "false|false")

    monta_banco()
    mut = original.replace(f"'REVOKE ALL PRIVILEGES ON TABLE {T} FROM %I'", "'SELECT 1 /* M2 */ -- %I'")
    assert mut != original, "M2 no encontró el REVOKE"
    rc, out = aplica_039(texto=mut)
    s.afirma("M2 · sin REVOKE a los roles la 039 ABORTA", rc != 0 and "quedan privilegios en pie" in out, out[-200:])
    s.afirma("M2 · y el ENABLE también se deshace (transacción única)", estado_rls() == "false|false")

    monta_banco()
    mut = original.replace(f"ALTER TABLE {T} ENABLE ROW LEVEL SECURITY;\n",
                           f"ALTER TABLE {T} ENABLE ROW LEVEL SECURITY;\n"
                           f"ALTER TABLE {T} FORCE ROW LEVEL SECURITY;\n")
    rc, out = aplica_039(texto=mut)
    s.afirma("M3 · con FORCE la 039 ABORTA", rc != 0 and "apareció FORCE" in out, out[-200:])

    monta_banco()
    sql_texto(f"GRANT SELECT ON {T} TO PUBLIC;", rol="contexto_owner")
    mut = original.replace(f"REVOKE ALL PRIVILEGES ON TABLE {T} FROM PUBLIC;\n", "")
    assert mut != original, "M5 no encontró el REVOKE a PUBLIC"
    rc, out = aplica_039(texto=mut)
    s.afirma("M5 · sin el REVOKE a PUBLIC (y PUBLIC concedido) la 039 ABORTA",
             rc != 0 and "PUBLIC(SELECT)" in out, out[-200:])

    monta_banco()
    assert aplica_039()[0] == 0
    sql_texto(f"""ALTER TABLE {T} DISABLE ROW LEVEL SECURITY;
                  GRANT ALL PRIVILEGES ON TABLE {T} TO anon, authenticated, service_role;""")
    s.afirma("M4 · el ROLLBACK documentado reabre la exposición (anon vuelve a leer)",
             ve_filas("anon") == 3, f"vio {ve_filas('anon')}")
    return s


def main():
    if not (MIGRACIONES / M039).exists():
        print(f"{ROJO}falta {M039}{FIN}")
        return 2
    titulo(f"0 · BANCO — {CONTENEDOR}")
    monta_banco()
    print("  " + psql("SELECT version();")[1].strip()[:70])

    s1 = control_positivo()
    if not s1.verde:
        print(f"\n{ROJO}EL CONTROL POSITIVO NO SE REPRODUJO.{FIN} El banco no mide lo que dice medir.")
        return 1

    monta_banco()
    titulo("· se aplica la 039 ·")
    rc, out = aplica_039()
    print(out.strip()[-400:])
    if rc != 0:
        print(f"{ROJO}la 039 no aplicó{FIN}")
        return 1
    s2 = suite_cerrada()

    titulo("2b · IDEMPOTENCIA")
    rc2, out2 = aplica_039()
    s2.afirma("la 039 es idempotente", rc2 == 0, out2.strip()[-200:])
    s2.afirma("y sigue cerrada", estado_rls() == "true|false" and ve_filas("anon") == -1)

    s2c = publico_y_columnas()
    s3 = compuertas()
    s4 = mutaciones()

    titulo("RESUMEN")
    for s in (s1, s2, s2c, s3, s4):
        marca = f"{VERDE}VERDE{FIN}" if s.verde else f"{ROJO}ROJA ({len(s.fallos)}){FIN}"
        print(f"  {s.titulo:20} {s.total:3} comprobaciones  {marca}")
        for f in s.fallos:
            print(f"        - {f}")
    return 0 if all(s.verde for s in (s1, s2, s2c, s3, s4)) else 1


if __name__ == "__main__":
    sys.exit(main())
