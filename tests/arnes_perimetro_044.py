# -*- coding: utf-8 -*-
"""SEC-PERIM-INTENCION-R0 · banco aislado para la migración 044.

    python tests/arnes_perimetro_044.py                                # perim-pg176 (PostgreSQL 17.6, = producción)
    PERIM_CONTENEDOR=perim-pg15 python tests/arnes_perimetro_044.py    # PostgreSQL 15 (= el CI)

No es una prueba de pytest: necesita Docker y un PostgreSQL limpio, igual que los arneses de la 032 … 040.
Producción corre PostgreSQL 17.6 (MAINTAIN existe) y el CI corre 15: se corre en los dos.

## FIDELIDAD

  · El dueño es `contexto_owner` (NOSUPERUSER + BYPASSRLS), el doble del `postgres` de producción, que no es
    superusuario. Un superusuario se salta todo y demostraría que el cambio «no rompe nada» por la razón
    equivocada. Una suite repite el cierre con un dueño SIN BYPASSRLS (`contexto_owner_nb`).
  · Se reproduce la HISTORIA de producción: la causa raíz (`ALTER DEFAULT PRIVILEGES … GRANT ALL ON
    TABLES/SEQUENCES TO anon, authenticated, service_role`), la migración REAL 018 —las tablas nacen con
    `arwdDxtm` para los tres roles y la secuencia con `rwU`—, filas escritas con el SQL REAL de
    `registrar_intencion`, y después las migraciones REALES 034 y 036 —los privilegios por defecto del dueño
    quedan cerrados, como en producción—. El destino de la FK es un doble de forma (`id uuid PRIMARY KEY`).
  · El backend se imita con su SQL REAL, leído por AST sin importar nada: el upsert y el evento de
    `registrar_intencion`, la lectura directa de la serie (la forma que tenía el lift hasta SEC-X2-R0c, que
    se la retiró: RETIRAR UN CONSUMIDOR ≠ ROMPER LA COMPATIBILIDAD DEL DUEÑO) y el `_INTENCION_DDL` en runtime.

## LO QUE SE PRUEBA

  1 · CONTROL POSITIVO: antes de la 044 `anon` lee el resumen y las señales, inventa y borra filas, falsea la
      serie, trunca, mueve la secuencia, usa la FK como oráculo y lee valores por `pg_stats`; `MAINTAIN` en 17.
  2 · DESPUÉS: RLS sin FORCE, 0 políticas, ningún privilegio externo (tabla, columnas, secuencia; PUBLIC
      incluido), cada operación denegada a los tres roles, el oráculo cerrado, `pg_stats` mudo; las filas y la
      estructura (FK incluida) intactas; el backend REAL funciona como dueño; un re-GRANT hostil choca con RLS
      (salvo `service_role`, que tiene BYPASSRLS: por eso el REVOKE); una RPC INVOKER posterior no abre nada.
  2b–2h · idempotencia; dueño sin BYPASSRLS; el estado del botón del panel (RLS sin REVOKE); PUBLIC concedido;
      la semántica del REVOKE de columnas (lente E); la recreación en runtime con defaults cerrados y abiertos
      (lente F); `lock_timeout` con un escritor vivo (lente G).
  3 · COMPUERTAS: cada precondición rota (tabla ausente o que no es tabla, secuencia inesperada o ausente,
      dueño distinto o aplica otro rol, política, FORCE, publicación, vista, materializada, vista sobre la
      secuencia, regla, herencia, función por texto, por cuerpo SQL estándar y por tipo fila, SECURITY DEFINER
      dinámica, trigger, ACL de columna, concedente ajeno, destinatario no medido, rol externo miembro del dueño,
      defaults abiertos en `public` y globales) ABORTA sin tocar nada.
  4 · MUTACIONES: la propia 044 se niega a confirmar si le falta un efecto o se le cuela uno; el ROLLBACK
      documentado reabre.
  5 · ROLES AUSENTES (como el CI): aplica, avisa y sigue cerrando lo que puede; idempotente.

Datos sintéticos (`Resumen sintético …`). Sobre producción, nada.
"""
from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys
import time

CONTENEDOR = os.environ.get("PERIM_CONTENEDOR", "perim-pg176")
RAIZ = pathlib.Path(__file__).resolve().parent.parent
MIGRACIONES = RAIZ / "migrations"
M044 = "044_intencion_perimeter.sql"
BANCO = "banco_044"
SES, EVE, SEQ = "public.intencion_sesion", "public.intencion_evento", "public.intencion_evento_id_seq"
ACTIVO = "00000000-0000-4000-8000-0000000044a1"
NO_EXISTE = "00000000-0000-4000-8000-0000000044ff"
SID1 = f"qr-{ACTIVO}-00000000-0000-4000-8000-0000000044d1"
SID2 = "crm-sintetico-044"

ROJO, VERDE, GRIS, FIN = "\033[31m", "\033[32m", "\033[90m", "\033[0m"
ROLES = ("anon", "authenticated", "service_role")
PRIVS = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
PRIVS_SEQ = ("USAGE", "SELECT", "UPDATE")
DUENO = "contexto_owner"           # lo cambia monta_banco()
ES17 = False                       # lo decide main()
VERBOS = PRIVS


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


def aplica_044(rol=None, texto=None):
    cuerpo = texto if texto is not None else (MIGRACIONES / M044).read_text(encoding="utf-8")
    return sql_texto(cuerpo, rol=rol or DUENO)


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


def uno(sql, rol=None):
    """Primer valor de la consulta, o None si hubo error."""
    rc, out = psql(sql, rol)
    if "ERROR" in out or "permission denied" in out:
        return None
    lineas = [x for x in out.strip().splitlines() if x.strip()]
    return lineas[0].strip() if lineas else ""


def ve_filas(rel, rol):
    v = uno(f"SELECT count(*) FROM {rel};", rol)
    return -1 if v is None else int(v)


def puede(op, rol):
    rc, out = psql(op, rol)
    return "permission denied" not in out and "ERROR" not in out


def error_de(op, rol):
    return psql(op, rol)[1].strip()


def denegado(op, rol):
    return "permission denied" in error_de(op, rol)


def estado_rls(rel):
    return uno(f"SELECT relrowsecurity::text || '|' || relforcerowsecurity::text FROM pg_class "
               f"WHERE oid = '{rel}'::regclass;")


def foto():
    """RLS, FORCE, políticas y ACL (tabla y columnas) de todo lo que se llame intencion*: lo que una compuerta
    que aborta NO puede haber cambiado."""
    return uno("""SELECT string_agg(c.relname || ':' || c.relkind || ':' || c.relrowsecurity || ':' || c.relforcerowsecurity
                   || ':' || (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) || ':' || coalesce(c.relacl::text, '-')
                   || ':' || coalesce((SELECT string_agg(a.attname || '=' || a.attacl::text, ',' ORDER BY a.attnum)
                                         FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attacl IS NOT NULL), ''),
                   ' | ' ORDER BY c.relname)
                  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'public' AND c.relname LIKE 'intencion%';""")


def acl_externo():
    """Destinatarios distintos del dueño en el ACL de las tablas, la secuencia y las columnas (PUBLIC incluido)."""
    return uno(f"""
      SELECT coalesce(string_agg(DISTINCT x.q, ','), '') FROM (
        SELECT c.relname || ':' || CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS q
          FROM pg_class c, aclexplode(c.relacl) a
         WHERE c.oid IN ('{SES}'::regclass, '{EVE}'::regclass, '{SEQ}'::regclass) AND a.grantee <> c.relowner
        UNION ALL
        SELECT att.attrelid::regclass::text || '.' || att.attname || ':' ||
               CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END
          FROM pg_attribute att, aclexplode(att.attacl) a
         WHERE att.attrelid IN ('{SES}'::regclass, '{EVE}'::regclass) AND att.attnum > 0
      ) x;""") or ""


def efectivos(rol, rel):
    return [p for p in VERBOS if uno(f"SELECT has_table_privilege('{rol}','{rel}','{p}');") == "t"]


def efectivos_seq(rol):
    return [p for p in PRIVS_SEQ if uno(f"SELECT has_sequence_privilege('{rol}','{SEQ}','{p}');") == "t"]


def huella():
    """md5 del contenido de las dos tablas (como el dueño): las filas sobreviven intactas."""
    return uno(f"""SELECT md5(coalesce((SELECT string_agg(t::text, '|' ORDER BY t.session_id) FROM {SES} t), '')) || ':' ||
                          md5(coalesce((SELECT string_agg(t::text, '|' ORDER BY t.id) FROM {EVE} t), ''));""", DUENO)


def estructura():
    """Columnas, restricciones (la FK incluida) e índices de las dos tablas."""
    return uno(f"""SELECT md5(string_agg(x, '|' ORDER BY x)) FROM (
        SELECT 'col ' || attrelid::regclass || ' ' || attnum || ' ' || attname || ' ' || format_type(atttypid, atttypmod) AS x
          FROM pg_attribute WHERE attrelid IN ('{SES}'::regclass, '{EVE}'::regclass) AND attnum > 0 AND NOT attisdropped
        UNION ALL SELECT 'con ' || conrelid::regclass || ' ' || conname || ' ' || pg_get_constraintdef(oid)
          FROM pg_constraint WHERE conrelid IN ('{SES}'::regclass, '{EVE}'::regclass)
        UNION ALL SELECT 'idx ' || pg_get_indexdef(indexrelid)
          FROM pg_index WHERE indrelid IN ('{SES}'::regclass, '{EVE}'::regclass)) s;""")


def contadores():
    """Lo que una lectura o escritura de filas habría movido: `pg_stat_user_tables` de las dos tablas y el estado
    de la secuencia. Cada backend vuelca sus contadores al terminar: se lee hasta que dos lecturas coinciden."""
    q = ("SELECT string_agg(concat_ws(',', s.relname, s.seq_scan, s.seq_tup_read, coalesce(s.idx_scan, 0), "
         "coalesce(s.idx_tup_fetch, 0), s.n_tup_ins, s.n_tup_upd, s.n_tup_del, s.n_tup_hot_upd, s.analyze_count, "
         "s.vacuum_count, coalesce(io.heap_blks_read, 0), coalesce(io.heap_blks_hit, 0), "
         "coalesce(io.idx_blks_read, 0), coalesce(io.idx_blks_hit, 0)), ' | ' ORDER BY s.relname) "
         "FROM pg_stat_user_tables s JOIN pg_statio_user_tables io USING (relid) "
         f"WHERE s.relid IN ('{SES}'::regclass, '{EVE}'::regclass);")
    previo = None
    for _ in range(25):
        ahora = (uno(q), uno(f"SELECT last_value || ',' || is_called FROM {SEQ};", DUENO))
        if ahora == previo:
            return ahora
        previo = ahora
        time.sleep(0.4)
    raise AssertionError(f"los contadores no se estabilizan: {previo}")


def fk():
    return uno(f"SELECT string_agg(conname || ' ' || pg_get_constraintdef(oid), ' | ') FROM pg_constraint "
               f"WHERE contype = 'f' AND conrelid = '{SES}'::regclass;")


# ══ lo que se lee del repo (por AST: sin importar nada) ═══════════════════════════════════
def _textos_en(funcion, ruta):
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    f = next(n for n in ast.walk(arbol)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == funcion)
    return [ast.literal_eval(c.args[0]) for c in ast.walk(f)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "text"]


def sql_de_registrar_intencion():
    t = _textos_en("registrar_intencion", RAIZ / "app" / "routers" / "chat.py")
    return (next(x for x in t if x.startswith("SELECT estado FROM intencion_sesion")),
            next(x for x in t if x.startswith("INSERT INTO intencion_sesion")),
            next(x for x in t if x.startswith("INSERT INTO intencion_evento")))


# La lectura de la serie que hacía `metricas_lift` hasta SEC-X2-R0c (congelada de main d94c6f1). R0c la retiró
# del lift; el banco la usa como lectura DIRECTA del dueño. `lift_sin_lectura_de_la_serie` fija que el lift
# siga sin leerla.
_LECTURA_SERIE = "SELECT session_id, estado FROM intencion_evento WHERE session_id = ANY(:ids)"


def sql_del_lift():
    return _LECTURA_SERIE


def lift_sin_lectura_de_la_serie():
    return not any("intencion_evento" in x
                   for x in _textos_en("metricas_lift", RAIZ / "app" / "routers" / "assets.py"))


def intencion_ddl_del_repo():
    arbol = ast.parse((RAIZ / "app" / "routers" / "chat.py").read_text(encoding="utf-8"))
    nodo = next(n.value for n in arbol.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "_INTENCION_DDL" for t in n.targets))
    return [ast.literal_eval(e) for e in nodo.elts]


def resolver_binds(sql, valores):
    for k in sorted(valores, key=len, reverse=True):
        sql = sql.replace(f":{k}", valores[k])
    return sql


def turno(sid, activo, estado, nivel, score, handoff, turnos, resumen):
    """Un turno de `registrar_intencion` con su SQL REAL: upsert del estado y evento si cambió."""
    _sel, ups, ev = sql_de_registrar_intencion()
    binds = {"s": f"'{sid}'", "a": f"'{activo}'" if activo else "NULL", "e": f"'{estado}'", "n": f"'{nivel}'",
             "sc": str(score), "h": "true" if handoff else "false", "t": str(turnos),
             "r": "'[\"Resumen sintético: razón\"]'", "se": "'{\"zona\": \"sintética\"}'", "re": f"'{resumen}'"}
    return resolver_binds(ups, binds) + ";\n" + resolver_binds(ev, binds) + ";"


# ══ el banco ════════════════════════════════════════════════════════════════════════════
def postura(dueno, con_roles=True, defaults_abiertos=True):
    roles = """
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon')           THEN CREATE ROLE anon NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated')  THEN CREATE ROLE authenticated NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role')   THEN CREATE ROLE service_role NOLOGIN BYPASSRLS; END IF;
""" if con_roles else ""
    base = f"""
DO $$ BEGIN{roles}
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='contexto_owner') THEN
      CREATE ROLE contexto_owner LOGIN PASSWORD 'perim' NOSUPERUSER BYPASSRLS; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='contexto_owner_nb') THEN
      CREATE ROLE contexto_owner_nb LOGIN PASSWORD 'perim' NOSUPERUSER NOBYPASSRLS; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='otro_rol') THEN CREATE ROLE otro_rol NOLOGIN NOSUPERUSER; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lector044') THEN
      CREATE ROLE lector044 NOLOGIN NOSUPERUSER BYPASSRLS; END IF;
END $$;
GRANT pg_read_all_data TO lector044;
ALTER DATABASE {BANCO} OWNER TO {dueno};
ALTER SCHEMA public OWNER TO {dueno};
"""
    if not con_roles:
        return base
    return base + f"""
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
-- Como en Supabase: PostgREST entra con `authenticator` (NOINHERIT), miembro de los tres.
DO $a$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticator') THEN
    CREATE ROLE authenticator NOLOGIN NOINHERIT; END IF; END $a$;
GRANT anon, authenticated, service_role TO authenticator;
""" + (f"""
-- LA CAUSA RAÍZ: toda tabla y secuencia que cree el dueño nace con todo para los tres roles.
ALTER DEFAULT PRIVILEGES FOR ROLE {dueno} IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE {dueno} IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
""" if defaults_abiertos else "")


def monta_banco(dueno="contexto_owner", con_roles=True, defaults_cerrados=True):
    """La historia de producción: causa raíz → 018 REAL → filas → 034 y 036 REALES."""
    global DUENO
    DUENO = dueno
    sql_texto(f"DROP DATABASE IF EXISTS {BANCO};", db="postgres")
    sql_texto(f"CREATE DATABASE {BANCO};", db="postgres")
    rc, out = sql_texto(postura(dueno, con_roles))
    assert rc == 0, out
    rc, out = sql_texto(f"CREATE TABLE public.activos_inmutables (id uuid PRIMARY KEY);"
                        f"INSERT INTO public.activos_inmutables VALUES ('{ACTIVO}');", rol=dueno)
    assert rc == 0, out
    rc, out = sql_texto((MIGRACIONES / "018_intencion_sesion.sql").read_text(encoding="utf-8"), rol=dueno)
    assert rc == 0, f"la migración real 018 falló:\n{out[-400:]}"
    rc, out = sql_texto(turno(SID1, ACTIVO, "identificado", "frio", 10, False, 1, "Resumen sintético uno")
                        + turno(SID2, None, "enganchado", "tibio", 40, False, 3, "Resumen sintético dos"), rol=dueno)
    assert rc == 0, f"el SQL real de registrar_intencion falló:\n{out[-400:]}"
    if con_roles and defaults_cerrados:
        for m in ("034_default_privileges_no_exponen.sql", "036_default_privileges_secuencias.sql"):
            rc, out = sql_texto((MIGRACIONES / m).read_text(encoding="utf-8"), rol=dueno)
            assert rc == 0, f"la migración real {m} falló:\n{out[-400:]}"


# ══ 1 · CONTROL POSITIVO ════════════════════════════════════════════════════════════════
def control_positivo():
    titulo("1 · CONTROL POSITIVO — el banco tiene que REPRODUCIR la exposición de producción")
    s = Suite("control positivo")
    for rel in (SES, EVE):
        s.afirma(f"{rel}: RLS desactivado, como en producción", estado_rls(rel) == "false|false", estado_rls(rel))
    s.afirma("los privilegios por defecto del dueño ya están cerrados (034/036), como en producción", uno(
        "SELECT count(*) FROM pg_default_acl d, aclexplode(d.defaclacl) a WHERE d.defaclrole = "
        f"'{DUENO}'::regrole AND a.grantee <> d.defaclrole;") == "0")
    for rol in ROLES:
        for rel in (SES, EVE):
            s.afirma(f"{rol} tiene los {len(VERBOS)} privilegios sobre {rel}", efectivos(rol, rel) == list(VERBOS),
                     efectivos(rol, rel))
        s.afirma(f"{rol} tiene USAGE/SELECT/UPDATE sobre la secuencia", efectivos_seq(rol) == list(PRIVS_SEQ))
    s.afirma("anon LEE el resumen y las señales de intención", uno(
        f"SELECT resumen || ' / ' || senales::text FROM {SES} WHERE session_id = '{SID1}';", "anon")
             == 'Resumen sintético uno / {"zona": "sintética"}')
    s.afirma("anon FALSEA la serie del lift (inserta un evento)", puede(
        f"INSERT INTO {EVE} (session_id, estado, nivel) VALUES ('{SID1}', 'confirmado', 'caliente');", "anon"))
    s.afirma("…y la lectura directa de la serie lo contaría como el pico de esa sesión", uno(
        "SELECT count(*) FROM (" + resolver_binds(sql_del_lift(), {"ids": f"ARRAY['{SID1}']"}) + ") x "
        "WHERE x.estado = 'confirmado';", DUENO) == "1")
    s.afirma("anon EDITA el estado de una sesión", puede(f"UPDATE {SES} SET score = 100 WHERE session_id = '{SID2}';", "anon"))
    s.afirma("ORÁCULO: un id existente entra…", puede(
        f"INSERT INTO {SES} (session_id, activo_id, estado, nivel) VALUES ('sonda-1', '{ACTIVO}', 'anonimo', 'frio');",
        "anon"))
    e = error_de(f"INSERT INTO {SES} (session_id, activo_id, estado, nivel) VALUES ('sonda-2', '{NO_EXISTE}', "
                 f"'anonimo', 'frio');", "anon")
    s.afirma("…y uno inexistente choca con la FK: la respuesta DISTINGUE la existencia", "foreign key" in e, e[-160:])
    s.afirma("anon BORRA", puede(f"DELETE FROM {SES} WHERE session_id = 'sonda-1';", "anon"))
    s.afirma("anon MUEVE la secuencia (setval)", puede(f"SELECT setval('{SEQ}', 1, false);", "anon"))
    rc, out = sql_texto(turno("qr-tras-setval", None, "identificado", "frio", 10, False, 1, "x"), rol=DUENO, detener=True)
    s.afirma("…y el siguiente INSERT del BACKEND choca con la clave primaria", rc != 0 and "duplicate key" in out,
             out[-160:])
    psql(f"ANALYZE {SES};", DUENO)
    s.afirma("anon LEE VALORES por pg_stats (lado oscuro del SELECT)", (uno(
        f"SELECT count(*) FROM pg_stats WHERE schemaname = 'public' AND tablename = 'intencion_sesion';", "anon") or "0")
        != "0")
    if ES17:
        rc, out = psql(f"ANALYZE {SES};", "anon")
        s.afirma("PG17 · anon tiene MAINTAIN: ANALYZE sin aviso", "skipping" not in out and "denied" not in out, out)
    s.afirma("service_role LEE (además tiene BYPASSRLS)", ve_filas(SES, "service_role") >= 2)
    s.afirma("anon TRUNCA (lo que RLS sola no cubre)", puede(f"TRUNCATE {EVE};", "anon"))
    return s


# ══ 2 · DESPUÉS DE LA 044 ═══════════════════════════════════════════════════════════════
OPS = {
    "SELECT sesión": f"SELECT count(*) FROM {SES};",
    "SELECT resumen": f"SELECT resumen FROM {SES};",
    "SELECT evento": f"SELECT count(*) FROM {EVE};",
    "INSERT sesión (id existente)": f"INSERT INTO {SES} (session_id, activo_id, estado, nivel) "
                                    f"VALUES ('x1', '{ACTIVO}', 'anonimo', 'frio');",
    "INSERT sesión (id inexistente)": f"INSERT INTO {SES} (session_id, activo_id, estado, nivel) "
                                      f"VALUES ('x2', '{NO_EXISTE}', 'anonimo', 'frio');",
    "INSERT evento": f"INSERT INTO {EVE} (session_id, estado, nivel) VALUES ('x', 'confirmado', 'caliente');",
    "UPDATE sesión": f"UPDATE {SES} SET score = 100;",
    "DELETE evento": f"DELETE FROM {EVE};",
    "TRUNCATE sesión": f"TRUNCATE {SES};",
    "TRUNCATE evento": f"TRUNCATE {EVE};",
    "LOCK TABLE": f"BEGIN; LOCK TABLE {SES} IN ACCESS SHARE MODE; COMMIT;",
    "nextval": f"SELECT nextval('{SEQ}');",
    "setval": f"SELECT setval('{SEQ}', 1);",
    "last_value": f"SELECT last_value FROM {SEQ};",
    "COPY TO": f"COPY {SES} TO STDOUT;",
}


def suite_cerrada(huella_antes, estructura_antes, fk_antes):
    titulo("2 · DESPUÉS DE LA 044")
    s = Suite("perímetro cerrado")
    for rel in (SES, EVE):
        s.afirma(f"{rel}: RLS activado, SIN FORCE", estado_rls(rel) == "true|false", estado_rls(rel))
        s.afirma(f"{rel}: cero políticas", uno(f"SELECT count(*) FROM pg_policy WHERE polrelid = '{rel}'::regclass;") == "0")
    s.afirma("ningún destinatario fuera del dueño (tablas, secuencia y columnas; PUBLIC incluido)",
             acl_externo() == "", f"quedan: {acl_externo()!r}")
    for rol in ("public", *ROLES):
        for rel in (SES, EVE):
            s.afirma(f"{rol}: 0 privilegios efectivos sobre {rel} ({len(VERBOS)} verbos)", not efectivos(rol, rel),
                     f"conserva {efectivos(rol, rel)}")
            cols = [p for p in ("SELECT", "INSERT", "UPDATE", "REFERENCES")
                    if uno(f"SELECT has_any_column_privilege('{rol}','{rel}','{p}');") == "t"]
            s.afirma(f"{rol}: 0 privilegios de columna sobre {rel}", not cols, f"conserva {cols}")
        s.afirma(f"{rol}: 0 privilegios sobre la secuencia", not efectivos_seq(rol), f"conserva {efectivos_seq(rol)}")
    for rol in ROLES:
        negadas = [op for op, sql in OPS.items() if not denegado(sql, rol)]
        s.afirma(f"{rol}: las {len(OPS)} operaciones reciben «permission denied»", not negadas, f"pasan: {negadas}")
    e1 = error_de(OPS["INSERT sesión (id existente)"], "anon")
    e2 = error_de(OPS["INSERT sesión (id inexistente)"], "anon")
    s.afirma("el ORÁCULO de la FK desapareció: existente o no, la misma respuesta",
             e1 == e2 and "permission denied for table intencion_sesion" in e1, f"{e1!r} / {e2!r}")
    s.afirma("pg_stats ya no le enseña a anon ningún valor", uno(
        "SELECT count(*) FROM pg_stats WHERE schemaname = 'public' AND tablename LIKE 'intencion%';", "anon") == "0")
    rc, out = psql(f"ANALYZE {SES}; VACUUM {EVE};", "anon")
    s.afirma("anon ya no puede ANALYZE ni VACUUM (MAINTAIN en 17; dueño en 15)", out.count("skipping") == 2, out)

    # — las filas y la estructura —
    s.afirma("las filas sobreviven INTACTAS (huella md5 idéntica)", huella() == huella_antes,
             f"{huella_antes} → {huella()}")
    s.afirma("columnas, restricciones e índices idénticos", estructura() == estructura_antes)
    s.afirma("la FK saliente sigue, idéntica", fk() == fk_antes and "REFERENCES activos_inmutables(id)" in (fk() or ""),
             fk())

    # — el backend (el dueño) sigue trabajando, con su SQL REAL —
    sel, _ups, _ev = sql_de_registrar_intencion()
    s.afirma("registrar_intencion · lee el estado previo", uno(resolver_binds(sel, {"s": f"'{SID1}'"}) + ";", DUENO)
             == "identificado")
    s.afirma("registrar_intencion · upsert + evento (cambio de estado)", puede(
        turno(SID1, ACTIVO, "intencion", "caliente", 100, True, 2, "Resumen sintético uno, segundo turno"), DUENO))
    s.afirma("…y quedó escrito", uno(f"SELECT estado || '|' || handoff_sugerido FROM {SES} WHERE session_id = '{SID1}';",
                                     DUENO) == "intencion|true")
    s.afirma("el lift ya no lee la serie (SEC-X2-R0c): consumidor retirado", lift_sin_lectura_de_la_serie())
    s.afirma("el dueño conserva la lectura directa de la serie", uno(
        "SELECT count(*) FROM (" + resolver_binds(sql_del_lift(), {"ids": f"ARRAY['{SID1}', '{SID2}']"}) + ") x;",
        DUENO) == "3")
    rc, out = sql_texto(";\n".join(intencion_ddl_del_repo()) + ";", rol=DUENO)
    s.afirma("el DDL en runtime (_INTENCION_DDL) sigue funcionando y no reabre nada",
             rc == 0 and acl_externo() == "" and estado_rls(SES) == "true|false", out[-200:])
    s.afirma("el DUEÑO hace CRUD y usa la secuencia", puede(
        f"""INSERT INTO {EVE} (session_id, estado, nivel) VALUES ('d', 'anonimo', 'frio');
            UPDATE {EVE} SET score = 1 WHERE session_id = 'd'; DELETE FROM {EVE} WHERE session_id = 'd';""", DUENO))

    # — lo que aporta RLS por encima del REVOKE, y dónde NO alcanza —
    psql(f"GRANT SELECT ON {SES} TO anon;", DUENO)
    s.afirma("RESISTE UN RE-GRANT: con SELECT devuelto a anon, RLS sin políticas → 0 filas",
             ve_filas(SES, "anon") == 0, f"vio {ve_filas(SES, 'anon')}")
    psql(f"REVOKE ALL PRIVILEGES ON {SES} FROM anon;", DUENO)
    psql(f"GRANT SELECT ON {SES} TO service_role;", DUENO)
    s.afirma("…pero NO frente a service_role (BYPASSRLS): con SELECT devuelto ve todo. Solo el REVOKE lo cierra",
             ve_filas(SES, "service_role") >= 2)
    psql(f"REVOKE ALL PRIVILEGES ON {SES} FROM service_role;", DUENO)
    rc, out = sql_texto(f"CREATE FUNCTION public.rpc_invoker_044() RETURNS bigint LANGUAGE sql AS "
                        f"$$ SELECT count(*) FROM {SES} $$; GRANT EXECUTE ON FUNCTION public.rpc_invoker_044() TO anon;",
                        rol=DUENO)
    s.afirma("una RPC SECURITY INVOKER posterior no abre nada (corre como anon → denegada)",
             rc == 0 and denegado("SELECT public.rpc_invoker_044();", "anon"))
    psql("DROP FUNCTION public.rpc_invoker_044();", DUENO)
    s.afirma("y todo vuelve a quedar sin destinatarios externos", acl_externo() == "")
    return s


# ══ 2c · DUEÑO SIN BYPASSRLS ════════════════════════════════════════════════════════════
def dueno_sin_bypass():
    titulo("2c · DUEÑO SIN BYPASSRLS — ENABLE sin FORCE no sujeta al dueño, por sí solo")
    s = Suite("dueño sin BYPASSRLS")
    monta_banco(dueno="contexto_owner_nb")
    rc, out = aplica_044()
    s.afirma("la 044 aplica como un dueño sin BYPASSRLS", rc == 0, out[-300:])
    s.afirma("el dueño sigue viendo sus filas", ve_filas(SES, DUENO) == 2, f"vio {ve_filas(SES, DUENO)}")
    s.afirma("registrar_intencion (SQL real) escribe", puede(
        turno(SID2, None, "intencion", "caliente", 90, True, 4, "Resumen sintético dos, otro turno"), DUENO))
    s.afirma("la lectura directa de la serie funciona", uno(
        "SELECT count(*) FROM (" + resolver_binds(sql_del_lift(), {"ids": f"ARRAY['{SID2}']"}) + ") x;", DUENO) == "2")
    s.afirma("anon sigue cerrado", denegado(OPS["SELECT sesión"], "anon"))
    monta_banco()
    return s


# ══ 2d · EL BOTÓN DEL PANEL ═════════════════════════════════════════════════════════════
def estado_del_panel():
    titulo("2d · EL ESTADO DEL PANEL — RLS encendido sin REVOKE no cierra; la 044 sí")
    s = Suite("panel")
    monta_banco()
    sql_texto(f"ALTER TABLE {SES} ENABLE ROW LEVEL SECURITY; ALTER TABLE {EVE} ENABLE ROW LEVEL SECURITY;", rol=DUENO)
    s.afirma("con RLS encendido y sin REVOKE, anon ve 0 filas…", ve_filas(SES, "anon") == 0)
    s.afirma("…pero sigue pudiendo TRUNCAR y mover la secuencia (verde falso)",
             puede(f"SELECT setval('{SEQ}', 5);", "anon") and puede(f"TRUNCATE {EVE};", "anon"))
    rc, out = aplica_044()
    s.afirma("la 044 lo admite (RLS ya activado) y aplica", rc == 0, out[-300:])
    s.afirma("y ahora sí: nada externo", acl_externo() == "" and denegado(OPS["TRUNCATE sesión"], "anon"))
    return s


# ══ 2e · PUBLIC ═════════════════════════════════════════════════════════════════════════
def publico():
    titulo("2e · PUBLIC — un privilegio a PUBLIC no lo quita un REVOKE a tres roles")
    s = Suite("PUBLIC")
    monta_banco()
    rc, out = sql_texto(f"GRANT SELECT ON {SES}, {EVE} TO PUBLIC; GRANT USAGE ON SEQUENCE {SEQ} TO PUBLIC;", rol=DUENO)
    assert rc == 0, out
    s.afirma("preparado: PUBLIC en las dos tablas y en la secuencia", "PUBLIC" in acl_externo(), acl_externo())
    rc, out = aplica_044()
    s.afirma("la 044 aplica", rc == 0, out[-300:])
    s.afirma("PUBLIC desaparece de tablas y secuencia", acl_externo() == "", acl_externo())
    s.afirma("y su privilegio efectivo es nulo", not efectivos("public", SES) and not efectivos_seq("public"))
    return s


# ══ 2f · LENTE E · COLUMNAS ═════════════════════════════════════════════════════════════
def lente_columnas():
    titulo("2f · LENTE E — ¿sobrevive un GRANT de columna a un REVOKE de tabla?")
    s = Suite("columnas")
    monta_banco()
    rc, out = sql_texto("CREATE TABLE public.sonda_col (a int, b int); GRANT SELECT (a), UPDATE (b) ON public.sonda_col "
                        "TO anon;", rol=DUENO)
    assert rc == 0, out
    antes = uno("SELECT count(*) FROM pg_attribute WHERE attrelid = 'public.sonda_col'::regclass AND attacl IS NOT NULL;")
    psql("REVOKE ALL PRIVILEGES ON TABLE public.sonda_col FROM anon;", DUENO)
    despues = uno("SELECT count(*) FROM pg_attribute WHERE attrelid = 'public.sonda_col'::regclass AND attacl IS NOT NULL "
                  "AND attacl::text LIKE '%anon%';")
    s.afirma("medido: un REVOKE ALL de TABLA también retira los GRANT de columna de ese rol",
             antes == "2" and despues == "0" and denegado("SELECT a FROM public.sonda_col;", "anon"),
             f"antes {antes}, después {despues}")
    psql("DROP TABLE public.sonda_col;", DUENO)
    sql_texto(f"GRANT SELECT (resumen) ON {SES} TO anon;", rol=DUENO)
    f = foto()
    rc, out = aplica_044()
    s.afirma("aun así, la 044 NO lo da por bueno: un ACL de columna no medido ABORTA (compuerta 10)",
             rc != 0 and "ACL de columna" in out and foto() == f, out.strip()[-200:])
    return s


# ══ 2g · LENTE F · RECREACIÓN EN RUNTIME ════════════════════════════════════════════════
def lente_runtime():
    titulo("2g · LENTE F — ¿una recreación en runtime (`_INTENCION_DDL`) reabre las tablas?")
    s = Suite("runtime")
    monta_banco()
    assert aplica_044()[0] == 0
    sql_texto(f"DROP TABLE {EVE}, {SES};", rol=DUENO)
    rc, out = sql_texto(";\n".join(intencion_ddl_del_repo()) + ";", rol=DUENO)
    s.afirma("con los defaults cerrados (034/036, como producción), la recreación nace SIN privilegios externos",
             rc == 0 and acl_externo() == "" and denegado(OPS["SELECT sesión"], "anon")
             and denegado(OPS["setval"], "anon"), f"{out[-200:]} acl={acl_externo()!r}")
    s.afirma("RESIDUAL declarado: nace sin RLS y sin la FK (el DDL en runtime no los crea)",
             estado_rls(SES) == "false|false" and not fk())

    monta_banco(defaults_cerrados=False)
    f = foto()
    rc, out = aplica_044()
    s.afirma("con los defaults ABIERTOS (antes de 034/036), la 044 ABORTA (compuerta 11)",
             rc != 0 and "privilegios por defecto" in out and foto() == f, out.strip()[-200:])
    sql_texto(f"DROP TABLE {EVE}, {SES};", rol=DUENO)
    sql_texto(";\n".join(intencion_ddl_del_repo()) + ";", rol=DUENO)
    s.afirma("…porque en ese estado la recreación en runtime nacería ABIERTA (por eso es compuerta)",
             ve_filas(SES, "anon") == 0 and puede(f"SELECT setval('{SEQ}', 1);", "anon"))
    monta_banco()
    return s


# ══ 2h · LENTE G · BLOQUEO ══════════════════════════════════════════════════════════════
def lente_bloqueo():
    titulo("2h · LENTE G — con un escritor vivo, la 044 no se queda en cola: aborta a los 3 s sin tocar nada")
    s = Suite("bloqueo")
    monta_banco()
    escritor = subprocess.Popen(
        ["docker", "exec", "-i", CONTENEDOR, "psql", "-U", "postgres", "-d", BANCO, "-q"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    escritor.stdin.write(f"SET ROLE {DUENO}; BEGIN; UPDATE {SES} SET turnos = turnos WHERE session_id = '{SID1}'; "
                         "SELECT pg_sleep(8); COMMIT;\n")
    escritor.stdin.close()
    time.sleep(1.5)
    f = foto()
    t0 = time.time()
    rc, out = aplica_044()
    dt = time.time() - t0
    escritor.wait(timeout=30)
    s.afirma("la 044 aborta por lock_timeout", rc != 0 and "lock timeout" in out, out.strip()[-200:])
    s.afirma(f"…en ~3 s, no en la duración del escritor ({dt:.1f} s)", dt < 7)
    s.afirma("…y no deja nada a medias", foto() == f)
    rc, out = aplica_044()
    s.afirma("terminado el escritor, la 044 aplica", rc == 0, out[-200:])
    return s


# ══ 3 · COMPUERTAS FAIL-CLOSED ══════════════════════════════════════════════════════════
def compuertas():
    titulo("3 · COMPUERTAS FAIL-CLOSED — cada precondición rota aborta SIN tocar nada")
    s = Suite("compuertas")
    D = "{dueno}"
    casos = [
        # (nombre, sql de preparación, rol que la prepara (None = superusuario), mensaje, rol que aplica)
        ("1 · tabla ausente", f"DROP TABLE {EVE};", D, "no existe public.intencion_evento", None),
        ("1 · no es una tabla ordinaria", f"DROP TABLE {EVE}; CREATE VIEW {EVE} AS SELECT 1 AS id;", D,
         "no es una tabla ordinaria", None),
        ("3 · secuencia inesperada (otro DEFAULT nextval)",
         f"CREATE SEQUENCE public.extra_044; ALTER TABLE {SES} ALTER COLUMN turnos SET DEFAULT nextval('public.extra_044');",
         D, "no son las medidas", None),
        ("3 · secuencia ausente", f"ALTER TABLE {EVE} ALTER COLUMN id DROP DEFAULT; DROP SEQUENCE {SEQ};", D,
         "no son las medidas", None),
        ("2 · dueño distinto de una tabla", f"ALTER TABLE {SES} OWNER TO otro_rol;", None, "el dueño no es quien aplica",
         None),
        ("2 · aplica un rol que no es el dueño", "SELECT 1;", None, "el dueño no es quien aplica", "otro_rol"),
        ("4 · política en intencion_sesion", f"CREATE POLICY p044 ON {SES} FOR SELECT USING (true);", D, "ya existen",
         None),
        ("4 · política restrictiva en intencion_evento",
         f"CREATE POLICY p044 ON {EVE} AS RESTRICTIVE FOR ALL USING (false);", D, "ya existen", None),
        ("4 · FORCE", f"ALTER TABLE {EVE} FORCE ROW LEVEL SECURITY;", D, "FORCE ROW LEVEL SECURITY ya activado", None),
        ("5 · publicación de replicación", f"CREATE PUBLICATION p044 FOR TABLE {EVE};", None,
         "publicación de replicación", None),
        ("6 · vista", f"CREATE VIEW public.v044 AS SELECT session_id, resumen FROM {SES};", D, "vistas que dependen", None),
        ("6 · materializada", f"CREATE MATERIALIZED VIEW public.mv044 AS SELECT estado FROM {EVE};", D,
         "vistas que dependen", None),
        ("6 · vista sobre la secuencia", f"CREATE VIEW public.v044 AS SELECT last_value FROM {SEQ};", D,
         "vistas que dependen", None),
        ("6 · regla", f"CREATE RULE r044 AS ON INSERT TO {EVE} DO ALSO NOTHING;", D, "reglas sobre", None),
        ("6 · herencia", f"CREATE TABLE public.hija044 () INHERITS ({EVE});", D, "herencia o particiones", None),
        ("7 · función por texto (plpgsql)",
         "CREATE FUNCTION public.f044() RETURNS bigint LANGUAGE plpgsql AS "
         "$$ BEGIN RETURN (SELECT count(*) FROM intencion_evento); END $$;", D, "funciones que nombran", None),
        ("7 · función con cuerpo SQL estándar (solo pg_depend: prosrc vacío)",
         f"CREATE FUNCTION public.f044() RETURNS bigint LANGUAGE sql BEGIN ATOMIC SELECT count(*) FROM {SES}; END;", D,
         "funciones que nombran", None),
        ("7 · función por tipo fila (sin nombrar la tabla en el cuerpo)",
         "CREATE FUNCTION public.f044(r public.intencion_sesion) RETURNS int LANGUAGE sql AS 'SELECT 1';", D,
         "funciones que nombran", None),
        ("8 · SECURITY DEFINER con SQL dinámico ejecutable por PUBLIC (sin nombrar nada)",
         "CREATE FUNCTION public.f044(q text) RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS "
         "$$ BEGIN EXECUTE q; END $$;", D, "SECURITY DEFINER alcanzables", None),
        ("9 · trigger",
         "CREATE FUNCTION public.t044() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$; "
         f"CREATE TRIGGER t044 BEFORE INSERT ON {SES} FOR EACH ROW EXECUTE FUNCTION public.t044();", D,
         "triggers sobre", None),
        ("10 · ACL de columna", f"GRANT SELECT (resumen) ON {SES} TO anon;", D, "ACL de columna", None),
        ("10 · concedido por otro rol",
         f"GRANT SELECT ON {SES} TO otro_rol WITH GRANT OPTION; SET ROLE otro_rol; GRANT SELECT ON {SES} TO anon;", D,
         "concedidos por otro rol", None),
        ("10 · destinatario no medido", f"GRANT SELECT ON {SES} TO otro_rol;", D, "destinatarios no medidos", None),
        ("10 · rol externo miembro del dueño", "GRANT {dueno} TO anon;", None, "miembro del dueño", None),
        ("11 · defaults abiertos de TABLAS en public",
         "ALTER DEFAULT PRIVILEGES FOR ROLE {dueno} IN SCHEMA public GRANT SELECT ON TABLES TO anon;", None,
         "privilegios por defecto", None),
        ("11 · defaults GLOBALES de SECUENCIAS (defaclnamespace = 0)",
         "ALTER DEFAULT PRIVILEGES FOR ROLE {dueno} GRANT USAGE ON SEQUENCES TO anon;", None,
         "privilegios por defecto", None),
        # ── las que pidió la revisión adversarial (falsos verdes de la primera versión) ──
        ("8 · DEFINER con cuerpo SQL estándar y query_to_xml (prosrc vacío)",
         "CREATE FUNCTION public.f044(q text) RETURNS xml LANGUAGE sql SECURITY DEFINER "
         "BEGIN ATOMIC SELECT query_to_xml(q, true, false, ''); END;", D, "SECURITY DEFINER alcanzables", None),
        ("8 · DEFINER con table_to_xml (familia *_to_xml)",
         "CREATE FUNCTION public.f044(t regclass) RETURNS xml LANGUAGE sql SECURITY DEFINER "
         "AS $f$ SELECT table_to_xml(t, true, false, '') $f$;", D, "SECURITY DEFINER alcanzables", None),
        ("8 · DEFINER que delega en una INVOKER dinámica",
         "CREATE FUNCTION public.ayuda044(q text) RETURNS SETOF text LANGUAGE plpgsql "
         "AS $f$ BEGIN RETURN QUERY EXECUTE q; END $f$; "
         "CREATE FUNCTION public.f044(q text) RETURNS SETOF text LANGUAGE sql SECURITY DEFINER "
         "AS $f$ SELECT * FROM public.ayuda044(q) $f$;", D, "SECURITY DEFINER alcanzables", None),
        ("8 · DEFINER con el nombre escapado (U&)",
         "CREATE FUNCTION public.f044() RETURNS text LANGUAGE sql SECURITY DEFINER "
         "AS $f$ SELECT string_agg(resumen, ',') FROM public.U&\"intencion\\005fsesion\" $f$;", D,
         "SECURITY DEFINER alcanzables", None),
        ("8 · DEFINER que mueve la secuencia sin nombrarla",
         "CREATE FUNCTION public.f044(s regclass, v bigint) RETURNS bigint LANGUAGE sql SECURITY DEFINER "
         "AS $f$ SELECT setval(s, v, false) $f$;", D, "SECURITY DEFINER alcanzables", None),
        ("8 · trigger DEFINER en otra tabla que anon escribe (EXECUTE revocado)",
         "CREATE TABLE public.buzon044 (q text, r text); "
         "CREATE FUNCTION public.t044() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER "
         "AS $f$ BEGIN EXECUTE NEW.q INTO NEW.r; RETURN NEW; END $f$; "
         "REVOKE ALL ON FUNCTION public.t044() FROM PUBLIC; "
         "CREATE TRIGGER t044 BEFORE INSERT ON public.buzon044 FOR EACH ROW EXECUTE FUNCTION public.t044(); "
         "GRANT SELECT, INSERT ON public.buzon044 TO anon;", D, "SECURITY DEFINER alcanzables", None),
        ("6 · FK entrante desde otra tabla (oráculo)",
         f"CREATE TABLE public.hija044 (s text REFERENCES {SES} (session_id)); GRANT INSERT ON public.hija044 TO anon;",
         D, "FK entrantes", None),
        ("10 · ACL de una columna de SISTEMA concedido por otro (no lo retira el REVOKE del dueño)",
         f"GRANT SELECT (xmin, ctid) ON {SES} TO otro_rol WITH GRANT OPTION; SET ROLE otro_rol; "
         f"GRANT SELECT (xmin, ctid) ON {SES} TO anon, service_role;", D, "ACL de columna", None),
        ("10 · ACL de columna de la SECUENCIA concedido por otro",
         f"GRANT SELECT (last_value) ON {SEQ} TO otro_rol WITH GRANT OPTION; SET ROLE otro_rol; "
         f"GRANT SELECT (last_value) ON {SEQ} TO anon;", D, "ACL de columna", None),
        ("10 · anon miembro de pg_write_all_data", "GRANT pg_write_all_data TO anon;", None, "miembro", None),
        ("10 · service_role miembro de pg_execute_server_program",
         "GRANT pg_execute_server_program TO service_role;", None, "miembro", None),
        ("10 · authenticator miembro del dueño", "GRANT {dueno} TO authenticator;", None, "miembro del dueño", None),
        ("3 · DEFAULT con una secuencia por nombre (enlace tardío, sin dependencia)",
         "CREATE SEQUENCE public.extra_044; "
         f"ALTER TABLE {SES} ALTER COLUMN turnos SET DEFAULT nextval('public.extra_044'::text);",
         D, "DEFAULT que usan secuencias", None),
        ("8 · DEFINER cuyo dueño es miembro de pg_read_all_data con BYPASSRLS",
         "GRANT CREATE ON SCHEMA public TO lector044; SET ROLE lector044; "
         "CREATE FUNCTION public.f044() RETURNS text LANGUAGE sql SECURITY DEFINER "
         "AS $f$ SELECT 'x' $f$;", None, "SECURITY DEFINER alcanzables", None),
        ("8 · DEFINER en lenguaje internal de un superusuario (C/internal ya no tienen excepción genérica)",
         "CREATE FUNCTION public.f044(text) RETURNS text LANGUAGE internal STRICT IMMUTABLE SECURITY DEFINER "
         "AS 'upper';", None, "SECURITY DEFINER alcanzables", None),
        ("8 · agregado cuyo soporte es DEFINER (EXECUTE revocado en el soporte, nombre partido)",
         "CREATE FUNCTION public.sf044(acc text, x text) RETURNS text LANGUAGE plpgsql SECURITY DEFINER AS $f$ "
         "DECLARE r text; t text := 'public.intencion' || '_sesion'; "
         "BEGIN EXECUTE format('SELECT string_agg(resumen, %L) FROM %s', ',', t) INTO r; RETURN r; END $f$; "
         "REVOKE ALL ON FUNCTION public.sf044(text, text) FROM PUBLIC; "
         "CREATE AGGREGATE public.agg044(text) (SFUNC = public.sf044, STYPE = text); "
         "GRANT EXECUTE ON FUNCTION public.agg044(text) TO anon;", D, "SECURITY DEFINER alcanzables", None),
        ("8 · event trigger con función DEFINER",
         "CREATE FUNCTION public.ev044() RETURNS event_trigger LANGUAGE plpgsql SECURITY DEFINER "
         "AS $f$ BEGIN END $f$; CREATE EVENT TRIGGER ev044 ON ddl_command_end EXECUTE FUNCTION public.ev044();",
         None, "SECURITY DEFINER alcanzables", None),
        ("3 · DEFAULT con una expresión no medida (sin secuencia ni función de usuario a la vista)",
         f"ALTER TABLE {SES} ALTER COLUMN turnos SET DEFAULT length(query_to_xml('select 1', true, false, '')::text);",
         D, "DEFAULT que usan secuencias", None),
        ("3 · DEFAULT que llama a una función de usuario",
         "CREATE FUNCTION public.sig044() RETURNS int LANGUAGE sql AS 'SELECT 1'; "
         f"ALTER TABLE {SES} ALTER COLUMN turnos SET DEFAULT public.sig044();", D, "DEFAULT que usan secuencias", None),
    ]
    for nombre, prepara, rol, mensaje, aplica in casos:
        monta_banco()
        rol_prep = DUENO if rol == D else None
        rc, out = sql_texto(prepara.replace("{dueno}", DUENO), rol=rol_prep)
        assert rc == 0, f"no se pudo preparar «{nombre}»:\n{out}"
        f = foto()
        rc, out = aplica_044(rol=aplica)
        s.afirma(f"{nombre} → ABORTA", rc != 0 and mensaje in out, out.strip()[-220:])
        s.afirma(f"{nombre} → nada cambió", foto() == f, f"{f}\n         → {foto()}")
        psql("DROP PUBLICATION IF EXISTS p044;")
        for limpieza in (f"REVOKE {DUENO} FROM anon;", f"REVOKE {DUENO} FROM authenticator;",
                         "REVOKE pg_write_all_data FROM anon;", "REVOKE pg_execute_server_program FROM service_role;"):
            psql(limpieza, db="postgres")
        psql("DROP EVENT TRIGGER IF EXISTS ev044;")

    # El search_path de quien aplica no puede tapar un catálogo (la 044 fija el suyo).
    monta_banco()
    sql_texto(f"CREATE PUBLICATION p044 FOR TABLE {EVE};")
    sql_texto("CREATE SCHEMA sombra; CREATE VIEW sombra.pg_publication_tables AS SELECT NULL::name AS pubname, "
              "NULL::name AS schemaname, NULL::name AS tablename WHERE false; GRANT USAGE ON SCHEMA sombra TO PUBLIC; "
              "GRANT SELECT ON sombra.pg_publication_tables TO PUBLIC;")
    f = foto()
    rc, out = aplica_044(texto="SET search_path = sombra, pg_catalog, public;\n"
                         + (MIGRACIONES / M044).read_text(encoding="utf-8"))
    s.afirma("un catálogo tapado en el search_path de quien aplica no da verde (sigue viendo la publicación)",
             rc != 0 and "publicación de replicación" in out and foto() == f, out.strip()[-200:])
    psql("DROP PUBLICATION IF EXISTS p044;")
    return s


# ══ 4 · MUTACIONES ══════════════════════════════════════════════════════════════════════
def mutaciones():
    titulo("4 · MUTACIONES — la propia 044 tiene que negarse a confirmar")
    s = Suite("mutaciones")
    original = (MIGRACIONES / M044).read_text(encoding="utf-8")
    ancla = "-- ── 3 · VERIFICACIÓN FAIL-CLOSED"
    assert original.count(ancla) == 1

    def mutante(etiqueta, viejo, nuevo, esperado, preparar=None):
        monta_banco()
        if preparar:
            rc, out = sql_texto(preparar, rol=DUENO)
            assert rc == 0, out
        f = foto()
        mut = original.replace(viejo, nuevo)
        assert mut != original, f"{etiqueta} no encontró su objetivo"
        rc, out = aplica_044(texto=mut)
        s.afirma(f"{etiqueta} → la 044 ABORTA", rc != 0 and esperado in out, out.strip()[-220:])
        s.afirma(f"{etiqueta} → y no deja nada a medias", foto() == f)

    def colado(etiqueta, sql, esperado):
        mutante(etiqueta, ancla, sql + "\n" + ancla, esperado)

    mutante("M1 · sin ENABLE en intencion_sesion", f"ALTER TABLE {SES} ENABLE ROW LEVEL SECURITY;\n", "",
            "RLS no quedó activado en public.intencion_sesion")
    mutante("M1b · sin ENABLE en intencion_evento", f"ALTER TABLE {EVE} ENABLE ROW LEVEL SECURITY;\n", "",
            "RLS no quedó activado en public.intencion_evento")
    mutante("M2 · sin REVOKE de tablas a los roles",
            "EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.intencion_sesion, public.intencion_evento FROM %I', rol);",
            "PERFORM 1;", "quedan privilegios en pie")
    mutante("M2b · sin REVOKE de la secuencia a los roles",
            "EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM %I', seq, rol);", "PERFORM 1;",
            "quedan privilegios en pie")
    mutante("M3 · con FORCE", f"ALTER TABLE {EVE} ENABLE ROW LEVEL SECURITY;\n",
            f"ALTER TABLE {EVE} ENABLE ROW LEVEL SECURITY;\nALTER TABLE {EVE} FORCE ROW LEVEL SECURITY;\n",
            "apareció FORCE")
    mutante("M5 · sin el REVOKE de tablas a PUBLIC (con PUBLIC concedido)",
            "REVOKE ALL PRIVILEGES ON TABLE public.intencion_sesion, public.intencion_evento FROM PUBLIC;\n", "",
            "PUBLIC(SELECT)", preparar=f"GRANT SELECT ON {SES} TO PUBLIC;")
    mutante("M5b · sin el REVOKE de la secuencia a PUBLIC (con PUBLIC concedido)",
            "EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM PUBLIC', seq);", "PERFORM 1;",
            "PUBLIC(USAGE)", preparar=f"GRANT USAGE ON SEQUENCE {SEQ} TO PUBLIC;")
    colado("M6 · un GRANT colado tras el REVOKE", f"GRANT SELECT ON {EVE} TO authenticated;", "quedan privilegios en pie")
    colado("M7 · una política colada", f"CREATE POLICY m7 ON {SES} FOR SELECT TO anon USING (true);", "aparecieron")
    colado("M8 · la FK borrada", f"ALTER TABLE {SES} DROP CONSTRAINT intencion_sesion_activo_id_fkey;",
           "cambió la estructura")
    colado("M9 · un GRANT de columna colado", f"GRANT SELECT (resumen) ON {SES} TO anon;", "quedan privilegios de columna")
    colado("M10 · una vista colada", f"CREATE VIEW public.v_m10 AS SELECT session_id FROM {SES};", "apareció un puente")
    colado("M11 · una columna añadida", f"ALTER TABLE {EVE} ADD COLUMN m11 text;", "cambió la estructura")
    colado("M12 · una SECURITY DEFINER colada", "CREATE FUNCTION public.m12() RETURNS int LANGUAGE sql SECURITY DEFINER "
           "AS 'SELECT 1';", "SECURITY DEFINER alcanzables")
    colado("M13 · una FK entrante colada", f"CREATE TABLE public.m13 (s text REFERENCES {SES} (session_id));",
           "apareció un puente")
    colado("M14 · ACL de columna de sistema colado", f"GRANT SELECT (xmin) ON {SES} TO anon;",
           "quedan privilegios de columna")
    colado("M15 · ACL de columna de la secuencia colado", f"GRANT SELECT (last_value) ON {SEQ} TO anon;",
           "quedan privilegios de columna")
    colado("M16 · un DEFAULT cambiado", f"ALTER TABLE {SES} ALTER COLUMN turnos SET DEFAULT 1;", "cambió la estructura")
    colado("M18 · un agregado con soporte DEFINER colado",
           "CREATE FUNCTION public.sf18(a int, b int) RETURNS int LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'; "
           "REVOKE ALL ON FUNCTION public.sf18(int, int) FROM PUBLIC; "
           "CREATE AGGREGATE public.agg18(int) (SFUNC = public.sf18, STYPE = int);", "SECURITY DEFINER alcanzables")
    colado("M17 · una membresía colada", f"RESET ROLE; GRANT pg_read_all_data TO anon; SET ROLE {DUENO};", "044 FALLA")

    monta_banco()
    assert aplica_044()[0] == 0
    rollback = "\n".join(l[4:] if l.startswith("--  ") else "" for l in
                         original.split("-- ── ROLLBACK", 1)[1].splitlines())
    rc, out = sql_texto(rollback)
    s.afirma("M4 · el ROLLBACK documentado reabre la exposición (anon vuelve a leer y a mover la secuencia)",
             rc == 0 and ve_filas(SES, "anon") == 2 and puede(f"SELECT setval('{SEQ}', 1000);", "anon"),
             f"rc={rc} vio {ve_filas(SES, 'anon')} {out[-200:]}")
    return s


# ══ 5 · ROLES AUSENTES ══════════════════════════════════════════════════════════════════
def roles_ausentes():
    titulo("5 · ROLES AUSENTES — el PostgreSQL del CI no tiene anon/authenticated/service_role")
    s = Suite("roles ausentes")
    # Los roles son del CLÚSTER y otros bancos del contenedor dependen de ellos: no se pueden borrar. Se
    # RENOMBRAN mientras dura la prueba (para la 044 no existen) y se restauran.
    renombrados = []
    try:
        for rol in ROLES:
            rc, out = psql(f"ALTER ROLE {rol} RENAME TO {rol}_ausente_044;", db="postgres")
            if rc == 0 and "ERROR" not in out:
                renombrados.append(rol)
        s.afirma("preparado: ninguno de los tres roles existe en el clúster", all(
            uno(f"SELECT count(*) FROM pg_roles WHERE rolname = '{r}';") in ("0", None) for r in ROLES)
            and len(renombrados) == 3, f"renombrados {renombrados}")
        monta_banco(con_roles=False)
        sql_texto(f"GRANT SELECT ON {SES} TO PUBLIC;", rol=DUENO)
        rc, out = aplica_044()
        s.afirma("la 044 aplica sin los roles (avisa y sigue)", rc == 0 and "no existe aquí" in out, out[-300:])
        s.afirma("y aun así deja RLS activado y PUBLIC sin nada",
                 estado_rls(SES) == "true|false" and estado_rls(EVE) == "true|false" and acl_externo() == "")
        rc, out = aplica_044()
        s.afirma("idempotente también sin roles", rc == 0, out[-200:])
    finally:
        for rol in renombrados:
            psql(f"ALTER ROLE {rol}_ausente_044 RENAME TO {rol};", db="postgres")
    return s


def detector():
    titulo("2i · CONTROL DEL DETECTOR — una 044 que lee una fila tiene que delatarse en los contadores")
    s = Suite("detector")
    monta_banco()
    c0 = contadores()
    mut = (MIGRACIONES / M044).read_text(encoding="utf-8").replace(
        "    -- 1 · Las dos tablas existen y son tablas ordinarias.",
        "    PERFORM count(*) FROM public.intencion_sesion;\n    -- 1 · Las dos tablas existen y son tablas ordinarias.", 1)
    rc, out = aplica_044(texto=mut)
    s.afirma("la 044 con una lectura colada aplica (sus compuertas no la ven)…", rc == 0, out[-200:])
    c1 = contadores()
    s.afirma("…pero el detector sí: seq_scan cambió", c0 != c1, f"{c0} → {c1}")
    # La lectura más sigilosa: una fila por su ctid (no mueve seq_scan ni idx_scan, medido).
    monta_banco()
    c0 = contadores()
    mut = (MIGRACIONES / M044).read_text(encoding="utf-8").replace(
        "    -- 1 · Las dos tablas existen y son tablas ordinarias.",
        "    PERFORM resumen FROM public.intencion_sesion WHERE ctid = '(0,1)'::tid;\n"
        "    -- 1 · Las dos tablas existen y son tablas ordinarias.", 1)
    rc, out = aplica_044(texto=mut)
    c1 = contadores()
    s.afirma("una lectura por ctid también se delata (bloques de pg_statio)", rc == 0 and c0 != c1, f"{c0} → {c1}")
    return s


def main():
    global ES17, VERBOS
    if not (MIGRACIONES / M044).exists():
        print(f"{ROJO}falta {M044}{FIN}")
        return 2
    titulo(f"0 · BANCO — {CONTENEDOR}")
    monta_banco()
    print("  " + (uno("SELECT version();") or "")[:70])
    ES17 = int(uno("SELECT current_setting('server_version_num');") or 0) >= 170000
    VERBOS = PRIVS + (("MAINTAIN",) if ES17 else ())
    print(f"  verbos medidos: {', '.join(VERBOS)}")

    s1 = control_positivo()
    if not s1.verde:
        print(f"\n{ROJO}EL CONTROL POSITIVO NO SE REPRODUJO.{FIN} El banco no mide lo que dice medir.")
        return 1

    monta_banco()
    antes, est, fk_antes = huella(), estructura(), fk()
    c_antes = contadores()
    titulo("· se aplica la 044 ·")
    rc, out = aplica_044()
    print(out.strip()[-700:])
    if rc != 0:
        print(f"{ROJO}la 044 no aplicó{FIN}")
        return 1
    c_despues = contadores()
    s2 = suite_cerrada(antes, est, fk_antes)
    s2.afirma("la 044 NO leyó ni escribió filas: pg_stat_user_tables y la secuencia, idénticos",
              c_antes == c_despues, f"{c_antes} → {c_despues}")

    titulo("2b · IDEMPOTENCIA")
    f = foto()
    rc2, out2 = aplica_044()
    s2.afirma("la 044 es idempotente", rc2 == 0, out2.strip()[-200:])
    s2.afirma("y deja exactamente el mismo estado", foto() == f)

    otras = [dueno_sin_bypass(), estado_del_panel(), publico(), lente_columnas(), lente_runtime(), lente_bloqueo(),
             detector(), compuertas(), mutaciones()]
    s5 = roles_ausentes()   # al final: renombra y restaura los roles del contenedor

    titulo("RESUMEN")
    todas = (s1, s2, *otras, s5)
    for s in todas:
        marca = f"{VERDE}VERDE{FIN}" if s.verde else f"{ROJO}ROJA ({len(s.fallos)}){FIN}"
        print(f"  {s.titulo:20} {s.total:3} comprobaciones  {marca}")
        for x in s.fallos:
            print(f"        - {x}")
    print(f"  TOTAL {sum(s.total for s in todas)} comprobaciones, "
          f"{sum(len(s.fallos) for s in todas)} fallos — {CONTENEDOR}")
    return 0 if all(s.verde for s in todas) else 1


if __name__ == "__main__":
    sys.exit(main())
