# -*- coding: utf-8 -*-
"""PLACE-SOURCE-PERIMETER · banco aislado para la migración 040.

    python tests/arnes_perimetro_040.py                              # perim-pg (PostgreSQL 17)
    PERIM_CONTENEDOR=perim-pg15 python tests/arnes_perimetro_040.py   # PostgreSQL 15
    PERIM_CONTENEDOR=perim-pgis15 python tests/arnes_perimetro_040.py # PostgreSQL 15 + PostGIS

No es una prueba de pytest: necesita Docker y un PostgreSQL limpio, igual que los arneses de la
032, 033, 035, 037 y 039. Producción corre PostgreSQL 17.6 y el CI corre 15: se corre en los dos.

## FIDELIDAD

  · El dueño es `contexto_owner` (NOSUPERUSER + BYPASSRLS), el doble del `postgres` de
    producción, que no es superusuario. Un superusuario se salta todo y demostraría que el
    cambio «no rompe nada» por la razón equivocada.
  · La causa raíz se reproduce: `ALTER DEFAULT PRIVILEGES … GRANT ALL ON TABLES/SEQUENCES TO
    anon, authenticated, service_role`, así el perímetro NACE con la exposición medida.
  · CON PostGIS (`perim-pgis15`): las relaciones las crean las MIGRACIONES REALES 014 → 023, y el
    backend se imita con sus consultas reales: la lectura de entorno y de transporte de
    `app/place/providers/propia.py` (contra `pois_vivos`) y el UPSERT del refresco semanal de
    `scripts/foso_pois_spike.py`, leídos por AST.
  · SIN PostGIS (`perim-pg`, `perim-pg15`): `pois_propios` es un doble de forma (mismas columnas y
    CHECK; `geom` como texto), y `entorno_curacion` y `pois_vivos` salen del DDL REAL
    (`_CURACION_DDL` de `app/entorno_curacion.py` y la vista de la 023).

## CONTROL POSITIVO

Antes de la 040 el banco EXIGE que el defecto se reproduzca: `anon` lee la capa por la vista,
INVENTA un lugar que el backend serviría, RENOMBRA uno real, OCULTA uno real a toda la ciudad con
una curación `cerrado`, mueve la secuencia y borra. Si no, se detiene.

## LO QUE SE PRUEBA DESPUÉS

  · `anon`, `authenticated` y `service_role` sin ningún privilegio (tablas, vista, secuencias y
    columnas) y sin poder leer, insertar, actualizar, borrar, truncar ni mover la secuencia;
  · `PUBLIC` sin nada; GRANT a PUBLIC y por columna posteriores los retira la 040 al reaplicarse;
  · el dueño —el backend y el refresco— lee la vista con la curación aplicada, hace el UPSERT del
    refresco, da de alta y de baja curaciones, y el DDL en runtime (`ensure_curacion_table`)
    sigue funcionando; las filas sobreviven intactas (huella md5 antes y después);
  · RESISTE UN RE-GRANT hostil: SELECT devuelto sobre una tabla → 0 filas (RLS); SELECT devuelto
    sobre la vista → choca con la tabla base (`security_invoker`);
  · reaplicar la 023 (`CREATE OR REPLACE VIEW`) no reabre la lectura;
  · idempotencia; roles ausentes;
  · compuertas fail-closed: política, publicación, vista inesperada (sobre una tabla o sobre la
    propia `pois_vivos`), función, trigger y dueño distinto ABORTAN sin tocar nada;
  · mutaciones: sin ENABLE (cualquiera de las dos), sin REVOKE a los roles, sin REVOKE de
    secuencias, con FORCE, sin REVOKE a PUBLIC (con PUBLIC concedido) o sin `security_invoker`,
    la propia 040 se niega a confirmar; y el ROLLBACK documentado reabre.

Datos sintéticos (`Lugar sintético …`). Sobre producción, nada.
"""
from __future__ import annotations

import ast
import os
import pathlib
import re
import subprocess
import sys

CONTENEDOR = os.environ.get("PERIM_CONTENEDOR", "perim-pg")
RAIZ = pathlib.Path(__file__).resolve().parent.parent
MIGRACIONES = RAIZ / "migrations"
M040 = "040_place_source_perimeter.sql"
BANCO = "banco_040"
POIS, CUR, VISTA = "public.pois_propios", "public.entorno_curacion", "public.pois_vivos"
ACTIVO = "00000000-0000-4000-8000-0000000040a1"
CORREDOR = "00000000-0000-4000-8000-0000000040c1"

ROJO, VERDE, GRIS, FIN = "\033[31m", "\033[32m", "\033[90m", "\033[0m"
ROLES = ("anon", "authenticated", "service_role")
PRIVS = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
PRIVS_SEQ = ("USAGE", "SELECT", "UPDATE")
CON_POSTGIS = False  # lo decide monta_banco()


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


def aplica_040(rol="contexto_owner", texto=None):
    cuerpo = texto if texto is not None else (MIGRACIONES / M040).read_text(encoding="utf-8")
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


def estado_rls(rel):
    return uno(f"SELECT relrowsecurity::text || '|' || relforcerowsecurity::text FROM pg_class "
               f"WHERE oid = '{rel}'::regclass;")


def opciones_vista():
    return uno(f"SELECT coalesce(array_to_string(reloptions, ','), '') FROM pg_class WHERE oid = '{VISTA}'::regclass;")


SECS = ("SELECT string_agg(d.objid::regclass::text, ',' ORDER BY d.objid::regclass::text) "
        "FROM pg_depend d JOIN pg_class s ON s.oid = d.objid AND s.relkind = 'S' "
        f"WHERE d.classid = 'pg_class'::regclass AND d.refobjid IN ('{POIS}'::regclass, '{CUR}'::regclass)")


def secuencias():
    return [s for s in (uno(SECS + ";") or "").split(",") if s]


def acl_externo():
    """Grantees externos en el ACL de tablas, vista, secuencias y columnas (PUBLIC incluido)."""
    return uno(f"""
      SELECT coalesce(string_agg(DISTINCT x.q, ','), '') FROM (
        SELECT c.oid::regclass::text || ':' ||
               CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS q,
               CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS quien
          FROM pg_class c, aclexplode(c.relacl) a
         WHERE c.oid IN ('{POIS}'::regclass, '{CUR}'::regclass, '{VISTA}'::regclass)
            OR c.oid IN (SELECT d.objid FROM pg_depend d JOIN pg_class s ON s.oid = d.objid AND s.relkind = 'S'
                          WHERE d.classid = 'pg_class'::regclass AND d.refobjid IN ('{POIS}'::regclass, '{CUR}'::regclass))
        UNION ALL
        SELECT att.attrelid::regclass::text || '.' || att.attname || ':' ||
               CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
               CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END
          FROM pg_attribute att, aclexplode(att.attacl) a
         WHERE att.attrelid IN ('{POIS}'::regclass, '{CUR}'::regclass, '{VISTA}'::regclass) AND att.attnum > 0
      ) x WHERE x.quien IN ('anon','authenticated','service_role','PUBLIC');""") or ""


def huella():
    """md5 del contenido de las dos tablas (como el dueño): las filas sobreviven intactas."""
    return uno(f"""SELECT md5(coalesce((SELECT string_agg(t::text, '|' ORDER BY t.id) FROM {POIS} t), '')) || ':' ||
                          md5(coalesce((SELECT string_agg(t::text, '|' ORDER BY t.id) FROM {CUR} t), ''));""",
               "contexto_owner")


# ══ lo que se lee del repo (por AST: sin importar nada) ═══════════════════════════════════
def _asignaciones(ruta):
    return {t.id: n.value for n in ast.parse(ruta.read_text(encoding="utf-8")).body
            if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}


def curacion_ddl_del_repo():
    return [ast.literal_eval(e) for e in _asignaciones(RAIZ / "app" / "entorno_curacion.py")["_CURACION_DDL"].elts]


def vista_de_la_023():
    """El `CREATE OR REPLACE VIEW pois_vivos` REAL de la migración 023, sin comentarios."""
    sql = "\n".join(l.split("--", 1)[0] for l in (MIGRACIONES / "023_curacion_engancha_poi.sql")
                    .read_text(encoding="utf-8").splitlines())
    m = re.search(r"CREATE OR REPLACE VIEW pois_vivos AS.*?;", sql, re.S)
    assert m, "no se encontró la vista pois_vivos en la 023"
    return m.group(0)


def consultas_de_propia():
    a = _asignaciones(RAIZ / "app" / "place" / "providers" / "propia.py")
    return {k: ast.literal_eval(a[k].args[0]) for k in ("_PROPIOS_ENTORNO_SQL", "_PROPIOS_TRANSPORTE_SQL")}


def upsert_del_refresco():
    a = _asignaciones(RAIZ / "scripts" / "foso_pois_spike.py")
    cols, vals, set_ = (ast.literal_eval(a[k]) for k in ("_COLS", "_VALS", "_SET"))
    return (f"INSERT INTO pois_propios {cols} VALUES {vals} "
            f"ON CONFLICT (osm_id) WHERE osm_id IS NOT NULL DO UPDATE SET {set_}")


def resolver_binds(sql, valores):
    for k in sorted(valores, key=len, reverse=True):
        sql = sql.replace(f":{k}", valores[k])
    return sql


# ══ el banco ════════════════════════════════════════════════════════════════════════════
def postura(con_roles=True):
    roles = """
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon')           THEN CREATE ROLE anon NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated')  THEN CREATE ROLE authenticated NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role')   THEN CREATE ROLE service_role NOLOGIN BYPASSRLS; END IF;
""" if con_roles else ""
    base = f"""
DO $$ BEGIN{roles}
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='contexto_owner') THEN
      CREATE ROLE contexto_owner LOGIN PASSWORD 'perim' NOSUPERUSER BYPASSRLS CREATEDB; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='otro_rol') THEN
      CREATE ROLE otro_rol NOLOGIN NOSUPERUSER; END IF;
END $$;
GRANT contexto_owner, otro_rol TO postgres;
ALTER DATABASE {BANCO} OWNER TO contexto_owner;
ALTER SCHEMA public OWNER TO contexto_owner;
"""
    if not con_roles:
        return base
    return base + """
GRANT anon, authenticated, service_role TO postgres;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
-- LA CAUSA RAÍZ: toda tabla y secuencia que cree el dueño nace con DML para los tres roles.
ALTER DEFAULT PRIVILEGES FOR ROLE contexto_owner IN SCHEMA public
    GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE contexto_owner IN SCHEMA public
    GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
"""


DOBLE_POIS = """
CREATE TABLE IF NOT EXISTS pois_propios (
    id                 bigserial PRIMARY KEY,
    nombre             text,
    categoria          text NOT NULL,
    categoria_overture text,
    geom               text NOT NULL,           -- doble de forma: geometry(Point,4326) en producción
    fuente             text NOT NULL DEFAULT 'overture',
    confianza          real,
    overture_id        text,
    osm_id             text,
    marca              text,
    direccion          text,
    operativo          boolean DEFAULT true,
    actualizado_en     timestamptz NOT NULL DEFAULT now(),
    ciudad             text NOT NULL DEFAULT 'quito',
    CONSTRAINT ck_pois_categoria CHECK (categoria IN ('salud','farmacia','supermercado','educacion',
        'parque','centro_comercial','transporte','iglesia','seguridad')),
    CONSTRAINT ck_pois_fuente CHECK (fuente IN ('overture','osm'))
);
CREATE UNIQUE INDEX IF NOT EXISTS pois_propios_osm_uidx ON pois_propios (osm_id) WHERE osm_id IS NOT NULL;
"""


def geom(lon, lat):
    return f"ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)" if CON_POSTGIS else f"'POINT({lon} {lat})'"


def semilla():
    return f"""
SET ROLE contexto_owner;
INSERT INTO {POIS} (nombre, categoria, categoria_overture, geom, fuente, osm_id) VALUES
  ('Parque sintético 1',    'parque',     NULL,     {geom(-78.481, -0.181)}, 'osm',      'node/401'),
  ('Farmacia sintética 2',  'farmacia',   NULL,     {geom(-78.482, -0.182)}, 'overture', NULL),
  ('Estación sintética 3',  'transporte', 'metro',  {geom(-78.483, -0.183)}, 'osm',      'node/403'),
  ('Súper sintético 4',     'supermercado', NULL,   {geom(-78.484, -0.184)}, 'osm',      'node/404');
INSERT INTO {CUR} (activo_id, accion, nombre, categoria, corredor_id, poi_id) VALUES
  ('{ACTIVO}', 'agregado', 'Lugar sintético del corredor', 'Supermercado', '{CORREDOR}', NULL),
  ('{ACTIVO}', 'cerrado',  'Súper sintético 4',            'supermercado', '{CORREDOR}',
     (SELECT id FROM {POIS} WHERE osm_id = 'node/404'));
RESET ROLE;
"""


def monta_banco(con_roles=True):
    global CON_POSTGIS
    sql_texto(f"DROP DATABASE IF EXISTS {BANCO};", db="postgres")
    sql_texto(f"CREATE DATABASE {BANCO};", db="postgres")
    CON_POSTGIS = sql_texto("CREATE EXTENSION IF NOT EXISTS postgis;")[0] == 0
    rc, out = sql_texto(postura(con_roles))
    assert rc == 0, out
    if CON_POSTGIS:
        for m in ("014_pois_propios.sql", "019_pois_propios_ciudad.sql", "020_pois_propios_id_origen_unico.sql",
                  "021_pois_propios_iglesia_seguridad.sql", "022_osm_id_con_tipo.sql", "023_curacion_engancha_poi.sql"):
            rc, out = sql_texto((MIGRACIONES / m).read_text(encoding="utf-8"), rol="contexto_owner")
            assert rc == 0, f"la migración real {m} falló:\n{out[-400:]}"
        # la 020 crea un respaldo que NO es del perímetro: fuera del banco para no confundir.
        sql_texto("DROP TABLE IF EXISTS pois_propios_backup_20260727;", rol="contexto_owner")
    else:
        rc, out = sql_texto(DOBLE_POIS + ";\n".join(curacion_ddl_del_repo()) + ";\n" + vista_de_la_023(),
                            rol="contexto_owner")
        assert rc == 0, f"el DDL real (curación / vista 023) falló:\n{out[-400:]}"
    rc, out = sql_texto(semilla())
    assert rc == 0, out


# ══ 1 · CONTROL POSITIVO ════════════════════════════════════════════════════════════════
def control_positivo():
    titulo("1 · CONTROL POSITIVO — el banco tiene que REPRODUCIR la exposición de producción")
    s = Suite("control positivo")
    for rel in (POIS, CUR):
        s.afirma(f"{rel}: RLS desactivado, como en producción", estado_rls(rel) == "false|false", estado_rls(rel))
    s.afirma("pois_vivos SIN security_invoker, como en producción", opciones_vista() == "", opciones_vista())
    s.afirma("dos secuencias en el perímetro", len(secuencias()) == 2, secuencias())
    for rol in ROLES:
        for rel in (POIS, CUR, VISTA):
            todos = all(uno(f"SELECT has_table_privilege('{rol}','{rel}','{p}');") == "t" for p in PRIVS)
            s.afirma(f"{rol} tiene los 7 privilegios sobre {rel}", todos)
        s.afirma(f"{rol} puede mover las secuencias", all(
            uno(f"SELECT has_sequence_privilege('{rol}','{q}','UPDATE');") == "t" for q in secuencias()))
    s.afirma("anon LEE la capa por la vista (3 vivos: el cerrado no sale)", ve_filas(VISTA, "anon") == 3,
             f"vio {ve_filas(VISTA, 'anon')}")
    s.afirma("anon INVENTA un lugar", puede(
        f"INSERT INTO {POIS} (nombre, categoria, geom, fuente, osm_id) "
        f"VALUES ('Lugar INVENTADO', 'parque', {geom(-78.49, -0.19)}, 'osm', 'node/666');", "anon"))
    s.afirma("…y el BACKEND lo serviría (lectura de pois_vivos como dueño)",
             uno(f"SELECT count(*) FROM {VISTA} WHERE nombre = 'Lugar INVENTADO';", "contexto_owner") == "1")
    s.afirma("anon RENOMBRA un lugar real", puede(
        f"UPDATE {POIS} SET nombre = 'Nombre CAMBIADO' WHERE osm_id = 'node/401';", "anon"))
    s.afirma("anon OCULTA un lugar real a toda la ciudad con una curación `cerrado`", puede(
        f"INSERT INTO {CUR} (activo_id, accion, nombre, poi_id) VALUES ('{ACTIVO}', 'cerrado', 'x', "
        f"(SELECT id FROM {POIS} WHERE osm_id = 'node/403'));", "anon")
             and uno(f"SELECT count(*) FROM {VISTA} WHERE osm_id = 'node/403';", "contexto_owner") == "0")
    q = secuencias()[0]
    s.afirma("anon MUEVE una secuencia (setval)", puede(f"SELECT setval('{q}', 1000000);", "anon"))
    s.afirma("anon BORRA", puede(f"DELETE FROM {CUR} WHERE nombre = 'x';", "anon"))
    return s


# ══ 2 · DESPUÉS DE LA 040 ═══════════════════════════════════════════════════════════════
def suite_cerrada(huella_antes, vivos_antes):
    titulo("2 · DESPUÉS DE LA 040")
    s = Suite("perímetro cerrado")
    for rel in (POIS, CUR):
        s.afirma(f"{rel}: RLS activado, SIN FORCE", estado_rls(rel) == "true|false", estado_rls(rel))
        s.afirma(f"{rel}: cero políticas", uno(
            f"SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='{rel.split('.')[1]}';") == "0")
    s.afirma("pois_vivos con security_invoker = true", opciones_vista() == "security_invoker=true", opciones_vista())
    s.afirma("ningún grantee externo (tablas, vista, secuencias y columnas; PUBLIC incluido)",
             acl_externo() == "", f"quedan: {acl_externo()!r}")
    for rol in ROLES:
        for rel in (POIS, CUR, VISTA):
            efectivos = [p for p in PRIVS if uno(f"SELECT has_table_privilege('{rol}','{rel}','{p}');") == "t"]
            s.afirma(f"{rol}: 0 privilegios efectivos sobre {rel}", not efectivos, f"conserva {efectivos}")
            s.afirma(f"{rol} NO lee {rel}", ve_filas(rel, rol) == -1)
        for q in secuencias():
            efs = [p for p in PRIVS_SEQ if uno(f"SELECT has_sequence_privilege('{rol}','{q}','{p}');") == "t"]
            s.afirma(f"{rol}: 0 privilegios sobre la secuencia {q}", not efs, f"conserva {efs}")
            s.afirma(f"{rol} NO mueve {q} (setval)", not puede(f"SELECT setval('{q}', 1);", rol))
        s.afirma(f"{rol} NO inventa (INSERT pois_propios)", not puede(
            f"INSERT INTO {POIS} (nombre, categoria, geom) VALUES ('x', 'parque', {geom(0, 0)});", rol))
        s.afirma(f"{rol} NO renombra (UPDATE)", not puede(f"UPDATE {POIS} SET nombre = 'x';", rol))
        s.afirma(f"{rol} NO oculta (INSERT curación)", not puede(
            f"INSERT INTO {CUR} (activo_id, accion, nombre) VALUES ('{ACTIVO}', 'cerrado', 'x');", rol))
        s.afirma(f"{rol} NO borra", not puede(f"DELETE FROM {CUR};", rol))
        s.afirma(f"{rol} NO trunca (lo que RLS sola no cubre)", not puede(f"TRUNCATE {CUR};", rol))

    # — el backend (el dueño) sigue trabajando —
    s.afirma("las filas sobreviven INTACTAS (huella md5 idéntica)", huella() == huella_antes,
             f"{huella_antes} → {huella()}")
    s.afirma("el DUEÑO lee pois_vivos con la curación aplicada (mismos vivos que antes)",
             ve_filas(VISTA, "contexto_owner") == vivos_antes, f"{ve_filas(VISTA, 'contexto_owner')} vs {vivos_antes}")
    s.afirma("…y el `cerrado` sigue ocultando su POI",
             uno(f"SELECT count(*) FROM {VISTA} WHERE osm_id = 'node/404';", "contexto_owner") == "0")
    s.afirma("el DUEÑO da de alta, edita y borra una curación (como POST/DELETE /entorno)", puede(
        f"""INSERT INTO {CUR} (activo_id, accion, nombre, corredor_id) VALUES ('{ACTIVO}', 'agregado', 'Nuevo', '{CORREDOR}');
            UPDATE {CUR} SET categoria = 'Parque' WHERE nombre = 'Nuevo';
            DELETE FROM {CUR} WHERE nombre = 'Nuevo';""", "contexto_owner"))
    s.afirma("el DUEÑO inserta, edita y borra un POI", puede(
        f"""INSERT INTO {POIS} (nombre, categoria, geom, fuente, osm_id) VALUES ('Temporal', 'salud', {geom(-78.5, -0.2)}, 'osm', 'node/900');
            UPDATE {POIS} SET operativo = false WHERE osm_id = 'node/900';
            DELETE FROM {POIS} WHERE osm_id = 'node/900';""", "contexto_owner"))
    rc, out = sql_texto("SET ROLE contexto_owner;\n" + ";\n".join(curacion_ddl_del_repo()) + ";")
    s.afirma("el DDL en runtime (ensure_curacion_table) sigue funcionando", rc == 0, out[-300:])
    if CON_POSTGIS:
        binds = {"lat": "-0.181", "lon": "-78.481", "max_m": "5000", "cats":
                 "ARRAY['salud','farmacia','supermercado','educacion','parque','centro_comercial']",
                 "masivo": "ARRAY['metro','estacion_tren','terminal_bus','estacion']"}
        for nombre, sql in consultas_de_propia().items():
            rc, out = psql(resolver_binds(sql, binds) + ";", "contexto_owner")
            s.afirma(f"la lectura REAL {nombre} (propia.py) funciona como el dueño",
                     "ERROR" not in out and out.strip() != "", out.strip()[-200:])
        up = resolver_binds(upsert_del_refresco(), {
            "nombre": "'Parque sintético 1 (refrescado)'", "categoria": "'parque'", "cat_leaf": "NULL",
            "lon": "-78.481", "lat": "-0.181", "fuente": "'osm'", "confidence": "NULL", "overture_id": "NULL",
            "osm_id": "'node/401'", "marca": "NULL", "direccion": "NULL", "operativo": "true", "ciudad": "'quito'"})
        s.afirma("el UPSERT REAL del refresco semanal (foso_pois_spike.py) funciona como el dueño",
                 puede(up + ";", "contexto_owner")
                 and uno(f"SELECT nombre FROM {POIS} WHERE osm_id = 'node/401';", "contexto_owner")
                 == "Parque sintético 1 (refrescado)")

    # — lo que aportan RLS y security_invoker por encima del REVOKE —
    psql(f"GRANT SELECT ON {POIS} TO anon;", "contexto_owner")
    s.afirma("RESISTE UN RE-GRANT sobre la tabla: con SELECT devuelto a anon, ve 0 filas",
             ve_filas(POIS, "anon") == 0, f"vio {ve_filas(POIS, 'anon')}")
    psql(f"REVOKE ALL PRIVILEGES ON {POIS} FROM anon;", "contexto_owner")
    psql(f"GRANT SELECT ON {VISTA} TO anon;", "contexto_owner")
    e = error_de(f"SELECT count(*) FROM {VISTA};", "anon")
    s.afirma("RESISTE UN RE-GRANT sobre la VISTA: choca con la tabla base (security_invoker)",
             "permission denied for table" in e, e[-160:])
    psql(f"GRANT SELECT ON {POIS}, {CUR} TO anon;", "contexto_owner")
    s.afirma("…y con SELECT también en las tablas base, ve 0 filas (RLS)", ve_filas(VISTA, "anon") == 0,
             f"vio {ve_filas(VISTA, 'anon')}")
    psql(f"REVOKE ALL PRIVILEGES ON {POIS}, {CUR}, {VISTA} FROM anon;", "contexto_owner")

    # — reaplicar la 023 (CREATE OR REPLACE VIEW) —
    rc, out = sql_texto(vista_de_la_023(), rol="contexto_owner")
    tras = opciones_vista()
    s.afirma("reaplicar la vista de la 023 NO reabre la lectura (el ACL sobrevive)",
             rc == 0 and ve_filas(VISTA, "anon") == -1 and acl_externo() == "", f"rc={rc} acl={acl_externo()!r}")
    print(f"  {GRIS}(dato: tras reaplicar la 023, reloptions de pois_vivos = {tras!r}){FIN}")
    if tras != "security_invoker=true":
        sql_texto(f"ALTER VIEW {VISTA} SET (security_invoker = true);", rol="contexto_owner")
    return s


# ══ 2c · PUBLIC Y COLUMNAS ══════════════════════════════════════════════════════════════
def publico_y_columnas():
    titulo("2c · PUBLIC Y GRANTS DE COLUMNA — lo que un REVOKE a tres roles no cubriría")
    s = Suite("PUBLIC y columnas")
    monta_banco()
    rc, out = sql_texto(f"GRANT SELECT ON {POIS}, {VISTA} TO PUBLIC; GRANT SELECT (nombre), UPDATE (nombre) "
                        f"ON {POIS} TO anon; GRANT SELECT (accion) ON {CUR} TO authenticated; "
                        f"GRANT USAGE ON SEQUENCE {secuencias()[0]} TO PUBLIC;", rol="contexto_owner")
    assert rc == 0, out
    antes = acl_externo()
    s.afirma("preparado: PUBLIC (tabla, vista y secuencia) y GRANTs de columna",
             "PUBLIC" in antes and "nombre:anon" in antes and "accion:authenticated" in antes, antes)
    rc, out = aplica_040()
    s.afirma("la 040 aplica", rc == 0, out[-300:])
    s.afirma("PUBLIC y los GRANT de columna desaparecen", acl_externo() == "", f"quedan: {acl_externo()!r}")
    s.afirma("anon ya no lee ni la columna", ve_filas(POIS, "anon") == -1)
    return s


# ══ 2d · ROLES AUSENTES ═════════════════════════════════════════════════════════════════
def roles_ausentes():
    titulo("2d · ROLES AUSENTES — el PostgreSQL del CI no tiene anon/authenticated/service_role")
    s = Suite("roles ausentes")
    # Los roles son del CLÚSTER y otros bancos del contenedor dependen de ellos: no se pueden
    # borrar. Se RENOMBRAN mientras dura la prueba (para la 040, no existen) y se restauran.
    renombrados = []
    try:
        for rol in ROLES:
            rc, out = psql(f"ALTER ROLE {rol} RENAME TO {rol}_ausente_040;", db="postgres")
            if rc == 0 and "ERROR" not in out:
                renombrados.append(rol)
        s.afirma("preparado: ninguno de los tres roles existe en el clúster", all(
            uno(f"SELECT count(*) FROM pg_roles WHERE rolname = '{r}';") in ("0", None) for r in ROLES)
            and len(renombrados) == 3, f"renombrados {renombrados}")
        monta_banco(con_roles=False)
        rc, out = aplica_040()
        s.afirma("la 040 aplica sin los roles (avisa y sigue)", rc == 0 and "no existe aquí" in out, out[-300:])
        s.afirma("y aun así deja RLS activado y la vista con security_invoker",
                 estado_rls(POIS) == "true|false" and estado_rls(CUR) == "true|false"
                 and opciones_vista() == "security_invoker=true")
        rc, out = aplica_040()
        s.afirma("idempotente también sin roles", rc == 0, out[-200:])
    finally:
        for rol in renombrados:
            psql(f"ALTER ROLE {rol}_ausente_040 RENAME TO {rol};", db="postgres")
    return s


# ══ 3 · COMPUERTAS FAIL-CLOSED ══════════════════════════════════════════════════════════
def compuertas():
    titulo("3 · COMPUERTAS FAIL-CLOSED — cada precondición rota aborta SIN tocar nada")
    s = Suite("compuertas")
    casos = [
        ("política en pois_propios", f"CREATE POLICY p_sonda ON {POIS} FOR SELECT USING (true);",
         "contexto_owner", "ya existen"),
        ("política en entorno_curacion", f"CREATE POLICY p_sonda ON {CUR} FOR SELECT USING (true);",
         "contexto_owner", "ya existen"),
        ("publicación de replicación", f"CREATE PUBLICATION supabase_realtime FOR TABLE {CUR};",
         None, "publicación de replicación"),
        ("vista inesperada sobre una tabla", f"CREATE VIEW public.v_sonda AS SELECT id, nombre FROM {POIS};",
         "contexto_owner", "además de pois_vivos"),
        ("vista inesperada sobre pois_vivos", f"CREATE VIEW public.v_sonda AS SELECT id FROM {VISTA};",
         "contexto_owner", "además de pois_vivos"),
        ("función que menciona el perímetro",
         "CREATE FUNCTION public.f_sonda() RETURNS bigint LANGUAGE sql AS "
         f"$$ SELECT count(*) FROM {CUR} $$;", "contexto_owner", "funciones que mencionan"),
        ("trigger en el perímetro",
         "CREATE FUNCTION public.t_sonda() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$; "
         f"CREATE TRIGGER t_sonda BEFORE INSERT ON {CUR} FOR EACH ROW EXECUTE FUNCTION public.t_sonda();",
         "contexto_owner", "triggers en el perímetro"),
    ]
    for nombre, prepara, rol, mensaje in casos:
        monta_banco()
        rc, out = sql_texto(prepara, rol=rol)
        assert rc == 0, f"no se pudo preparar «{nombre}»:\n{out}"
        acl_antes = uno(f"SELECT relacl::text FROM pg_class WHERE oid='{POIS}'::regclass;")
        rc, out = aplica_040()
        acl_despues = uno(f"SELECT relacl::text FROM pg_class WHERE oid='{POIS}'::regclass;")
        s.afirma(f"{nombre} → ABORTA", rc != 0 and mensaje in out, out.strip()[-220:])
        s.afirma(f"{nombre} → nada cambió (RLS off, vista intacta, ACL idéntico)",
                 estado_rls(POIS) == "false|false" and estado_rls(CUR) == "false|false"
                 and opciones_vista() == "" and acl_antes == acl_despues,
                 f"{estado_rls(POIS)} {estado_rls(CUR)} {opciones_vista()!r}")
        psql("DROP PUBLICATION IF EXISTS supabase_realtime;")

    for nombre, sql in (("dueño distinto de la tabla", f"ALTER TABLE {CUR} OWNER TO otro_rol;"),
                        ("dueño distinto de la vista", f"ALTER VIEW {VISTA} OWNER TO otro_rol;")):
        monta_banco()
        rc, out = sql_texto(sql)
        assert rc == 0, out
        rc, out = aplica_040()
        s.afirma(f"{nombre} → ABORTA", rc != 0 and "el dueño no es quien aplica" in out, out.strip()[-220:])
        s.afirma(f"{nombre} → nada cambió", estado_rls(POIS) == "false|false" and opciones_vista() == "")
    return s


# ══ 4 · MUTACIONES ══════════════════════════════════════════════════════════════════════
def mutaciones():
    titulo("4 · MUTACIONES — la propia 040 tiene que negarse a confirmar")
    s = Suite("mutaciones")
    original = (MIGRACIONES / M040).read_text(encoding="utf-8")

    def mutante(etiqueta, viejo, nuevo, esperado, preparar=None):
        monta_banco()
        if preparar:
            rc, out = sql_texto(preparar, rol="contexto_owner")
            assert rc == 0, out
        mut = original.replace(viejo, nuevo)
        assert mut != original, f"{etiqueta} no encontró su objetivo"
        rc, out = aplica_040(texto=mut)
        s.afirma(f"{etiqueta} → la 040 ABORTA", rc != 0 and esperado in out, out.strip()[-220:])
        s.afirma(f"{etiqueta} → y no deja nada a medias", estado_rls(POIS) == "false|false"
                 and estado_rls(CUR) == "false|false" and opciones_vista() == "")

    mutante("M1 · sin ENABLE en pois_propios", f"ALTER TABLE {POIS} ENABLE ROW LEVEL SECURITY;\n", "",
            "RLS no quedó activado en pois_propios")
    mutante("M1b · sin ENABLE en entorno_curacion", f"ALTER TABLE {CUR} ENABLE ROW LEVEL SECURITY;\n", "",
            "RLS no quedó activado en entorno_curacion")
    mutante("M2 · sin REVOKE de tablas y vista a los roles",
            "EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.pois_propios, public.entorno_curacion, '\n"
            "                       'public.pois_vivos FROM %I', rol);",
            "PERFORM 1;  -- M2", "quedan privilegios en pie")
    mutante("M2b · sin REVOKE de secuencias a los roles",
            "EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM %I', seq, rol);",
            "PERFORM 1;  -- M2b", "quedan privilegios en pie")
    mutante("M3 · con FORCE", f"ALTER TABLE {POIS} ENABLE ROW LEVEL SECURITY;\n",
            f"ALTER TABLE {POIS} ENABLE ROW LEVEL SECURITY;\nALTER TABLE {POIS} FORCE ROW LEVEL SECURITY;\n",
            "apareció FORCE")
    mutante("M5 · sin el REVOKE a PUBLIC (con PUBLIC concedido)",
            f"REVOKE ALL PRIVILEGES ON TABLE {POIS}, {CUR}, {VISTA} FROM PUBLIC;\n", "",
            "PUBLIC(SELECT)", preparar=f"GRANT SELECT ON {VISTA} TO PUBLIC;")
    mutante("M6 · sin security_invoker en la vista", f"ALTER VIEW {VISTA} SET (security_invoker = true);\n", "",
            "security_invoker")

    monta_banco()
    assert aplica_040()[0] == 0
    rollback = "\n".join(l[4:] if l.startswith("--  ") else "" for l in
                         original.split("-- ── ROLLBACK", 1)[1].splitlines())
    rc, out = sql_texto(rollback)
    s.afirma("M4 · el ROLLBACK documentado reabre la exposición (anon vuelve a leer por la vista)",
             rc == 0 and ve_filas(VISTA, "anon") == 3, f"rc={rc} vio {ve_filas(VISTA, 'anon')} {out[-200:]}")
    return s


def main():
    if not (MIGRACIONES / M040).exists():
        print(f"{ROJO}falta {M040}{FIN}")
        return 2
    titulo(f"0 · BANCO — {CONTENEDOR}")
    monta_banco()
    print("  " + (uno("SELECT version();") or "")[:70])
    print(f"  modo: {'PostGIS + migraciones reales 014→023' if CON_POSTGIS else 'doble de forma (sin PostGIS) + DDL real de curación y vista'}")

    s1 = control_positivo()
    if not s1.verde:
        print(f"\n{ROJO}EL CONTROL POSITIVO NO SE REPRODUJO.{FIN} El banco no mide lo que dice medir.")
        return 1

    monta_banco()
    antes, vivos = huella(), ve_filas(VISTA, "contexto_owner")
    titulo("· se aplica la 040 ·")
    rc, out = aplica_040()
    print(out.strip()[-500:])
    if rc != 0:
        print(f"{ROJO}la 040 no aplicó{FIN}")
        return 1
    s2 = suite_cerrada(antes, vivos)

    titulo("2b · IDEMPOTENCIA")
    rc2, out2 = aplica_040()
    s2.afirma("la 040 es idempotente", rc2 == 0, out2.strip()[-200:])
    s2.afirma("y sigue cerrada", estado_rls(POIS) == "true|false" and ve_filas(VISTA, "anon") == -1)

    s2c = publico_y_columnas()
    s3 = compuertas()
    s4 = mutaciones()
    s2d = roles_ausentes()   # al final: renombra y restaura los roles del contenedor

    titulo("RESUMEN")
    todas = (s1, s2, s2c, s3, s4, s2d)
    for s in todas:
        marca = f"{VERDE}VERDE{FIN}" if s.verde else f"{ROJO}ROJA ({len(s.fallos)}){FIN}"
        print(f"  {s.titulo:20} {s.total:3} comprobaciones  {marca}")
        for f in s.fallos:
            print(f"        - {f}")
    return 0 if all(s.verde for s in todas) else 1


if __name__ == "__main__":
    sys.exit(main())
