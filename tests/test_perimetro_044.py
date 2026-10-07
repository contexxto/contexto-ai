"""SEC-PERIM-INTENCION-R0 · la 044 cierra el Motor de Intención a los roles externos sin cambiar el producto.

  A · sin base: la migración hace SOLO lo que dice (RLS sin FORCE en las dos tablas, REVOKE a PUBLIC y a los
      tres roles sobre las tablas y la secuencia descubierta, compuertas fail-closed) y nada más: ni políticas,
      ni GRANT, ni DML, ni lecturas de filas, ni otras relaciones, ni privilegios por defecto.
  B · PostgreSQL 15 real (`TEST_DATABASE_URL`, también en el CI): las tablas las crea la migración REAL 018
      como un dueño NO superusuario con BYPASSRLS —el doble del `postgres` de producción— y nacen con la
      exposición medida. La 044 se aplica con el aplicador del producto. Los tres roles y PUBLIC quedan sin
      nada, y el backend sigue funcionando con su código REAL: `registrar_intencion` escribe,
      `ensure_intencion_tables` corre y `metricas_lift` lee la serie. Las filas sobreviven intactas.

El banco completo (control positivo, compuertas, mutaciones, roles ausentes, MAINTAIN, recreación en runtime,
dueño sin BYPASSRLS, PG15 y PG17.6) está en `tests/arnes_perimetro_044.py`, que necesita Docker.
"""
from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy import text

import app.routers.assets as assets
import app.routers.chat as chat

RAIZ = Path(__file__).resolve().parents[1]
M044 = RAIZ / "migrations" / "044_intencion_perimeter.sql"
M018 = RAIZ / "migrations" / "018_intencion_sesion.sql"
ROLES = ("anon", "authenticated", "service_role")
PRIVS = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
TABLAS = ("public.intencion_sesion", "public.intencion_evento")
SEQ = "public.intencion_evento_id_seq"
DUENO = "p044_owner"
ACTIVO = "0cb128c9-0000-4000-8000-0000000044a1"
NO_EXISTE = "0cb128c9-0000-4000-8000-0000000044ff"
DEVICE = "0cb128c9-0000-4000-8000-0000000044d1"
SID = f"qr-{ACTIVO}-{DEVICE}"


# ─────────────────────────────── A · sin base ────────────────────────────────
# La forma de la 044 se prueba con un LEXER, no con expresiones regulares sobre el texto: un `--` dentro de un
# literal, un `/**/`, un identificador entre comillas o `U&"…"` engañan a una regex (la revisión adversarial lo
# demostró con 12 mutantes). Aquí los comentarios desaparecen, los literales son literales y el código de cada
# bloque DO se examina token a token.
_IDENT = re.compile(r"[^\W\d][\w$]*")        # también identificadores no ASCII
_DOLAR = re.compile(r"\$([A-Za-z_][A-Za-z_0-9]*)?\$")


def _lex(sql: str) -> list[tuple[str, str]]:
    """(tipo, texto): 'id' (identificador o palabra clave, en minúsculas), 'str' (literal), 'dolar' (cuerpo
    $…$), 'qid' (identificador entre comillas), 'uesc' (U&…), 'num' o 'p' (puntuación)."""
    out, i, n = [], 0, len(sql)
    while i < n:
        c = sql[i]
        if c.isspace():
            i += 1
        elif sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j
        elif sql.startswith("/*", i):
            prof, i = 1, i + 2
            while prof:
                if i >= n:
                    raise ValueError("comentario /* sin cerrar")
                if sql.startswith("/*", i):
                    prof, i = prof + 1, i + 2
                elif sql.startswith("*/", i):
                    prof, i = prof - 1, i + 2
                else:
                    i += 1
        elif m := _DOLAR.match(sql, i):
            j = sql.find(m.group(0), m.end())
            if j < 0:
                raise ValueError("cuerpo $…$ sin cerrar")
            out.append(("dolar", sql[m.end():j]))
            i = j + len(m.group(0))
        elif c in "uU" and sql.startswith("&", i + 1):
            out.append(("uesc", sql[i:i + 2]))
            i += 2
        elif c == "'" or (c in "eE" and sql.startswith("'", i + 1)):
            escapes = c != "'"
            j, buf = i + (2 if escapes else 1), []
            while True:
                if j >= n:
                    raise ValueError("literal sin cerrar")
                if escapes and sql[j] == "\\":
                    buf.append(sql[j:j + 2])
                    j += 2
                elif sql.startswith("''", j):
                    buf.append("'")
                    j += 2
                elif sql[j] == "'":
                    break
                else:
                    buf.append(sql[j])
                    j += 1
            out.append(("str", "".join(buf)))
            i = j + 1
        elif c == '"':
            j = sql.find('"', i + 1)
            if j < 0:
                raise ValueError("identificador entre comillas sin cerrar")
            out.append(("qid", sql[i + 1:j]))
            i = j + 1
        elif m := _IDENT.match(sql, i):
            out.append(("id", m.group(0).lower()))
            i = m.end()
        elif c.isdigit():
            j = i
            while j < n and (sql[j].isdigit() or sql[j] == "."):
                j += 1
            out.append(("num", sql[i:j]))
            i = j
        else:
            out.append(("p", c))
            i += 1
    return out


# En el código de los bloques DO: ni DML, ni DDL, ni lecturas de contenido, ni caminos alternos.
_PROHIBIDOS = {
    "insert", "update", "delete", "truncate", "merge", "copy", "analyze", "vacuum", "cluster", "reindex", "refresh",
    "lock", "grant", "create", "drop", "alter", "table", "only", "notify", "listen", "call", "nextval", "setval",
    "currval", "lastval", "pg_sequence_last_value", "pg_stats", "pg_stats_ext", "pg_statistic", "pg_read_file",
    "pg_read_binary_file", "lo_import", "lo_export", "dblink", "query_to_xml", "table_to_xml", "schema_to_xml",
    "database_to_xml", "cursor_to_xml", "query_to_xml_and_xmlschema", "table_to_xml_and_xmlschema",
    "pg_get_function_sqlbody",
}
# LISTA BLANCA de lo que puede ir seguido de «(» en el código: funciones de catálogo y de privilegios, y
# palabras clave. Cualquier otra llamada —`ts_stat`, `dblink_exec`, `get_raw_page`, una función de usuario o
# de extensión— es una violación, aunque no esté en la lista negra de arriba.
_LLAMADAS = {"acldefault", "aclexplode", "and", "any", "array", "array_append", "array_length", "array_to_string",
             "coalesce", "count", "current_setting", "exists", "format", "format_type", "from", "has_any_column_privilege",
             "has_function_privilege", "has_sequence_privilege", "has_table_privilege", "if", "in", "medidas", "not", "or",
             "pg_get_constraintdef", "pg_get_expr", "pg_get_userbyid", "pg_has_role", "select", "set_config", "soporte",
             "string_agg", "string_to_array", "to_regclass", "unnest", "values"}
# Las ÚNICAS sentencias dinámicas: los tres REVOKE, con su plantilla exacta y sus argumentos exactos.
_EXECUTE = {("REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM PUBLIC", ("seq",)),
            ("REVOKE ALL PRIVILEGES ON TABLE public.intencion_sesion, public.intencion_evento FROM %I", ("rol",)),
            ("REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM %I", ("seq", "rol"))}
_CATALOGOS = {"pg_class", "pg_depend", "pg_attrdef", "pg_attribute", "pg_policy", "pg_publication_tables",
              "pg_rewrite", "pg_inherits", "pg_constraint", "pg_proc", "pg_namespace", "pg_language", "pg_roles",
              "pg_trigger", "pg_event_trigger", "pg_aggregate", "pg_default_acl", "pg_type", "pg_extension", "unnest", "aclexplode"}


def _execute_exacto(tokens, i):
    """EXECUTE format('<plantilla exacta>', <args exactos>) ; — y nada más."""
    for plantilla, args in _EXECUTE:
        forma = [("id", "format"), ("p", "("), ("str", plantilla)]
        for a in args:
            forma += [("p", ","), ("id", a)]
        forma += [("p", ")"), ("p", ";")]
        if tokens[i + 1:i + 1 + len(forma)] == forma:
            return True
    return False


def _codigo_limpio(tokens, donde, permite_execute=False):
    v = []
    for i, (tipo, txt) in enumerate(tokens):
        if (tipo, txt) == ("qid", "char"):
            continue                          # el tipo interno `"char"` (acldefault lo exige); no es una relación
        if tipo in ("qid", "uesc", "dolar"):
            v.append(f"{donde}: {tipo} {txt[:40]!r} (un nombre o un cuerpo que este examen no vería)")
        if tipo != "id":
            continue
        previo = tokens[i - 1] if i else ("", "")
        sig = tokens[i + 1] if i + 1 < len(tokens) else ("", "")
        if txt in _PROHIBIDOS:
            v.append(f"{donde}: «{txt}»")
        if txt.startswith("intencion_"):
            v.append(f"{donde}: «{txt}» como código (solo puede aparecer dentro de un literal)")
        if txt == "public" and sig == ("p", "."):
            v.append(f"{donde}: referencia calificada public.… como código")
        if txt in ("from", "join") and previo != ("id", "distinct"):
            if not (sig == ("p", "(") or (sig[0] == "id" and sig[1] in _CATALOGOS)):
                v.append(f"{donde}: {txt} {sig[1]!r} (solo catálogos del sistema)")
        if sig == ("p", "(") and txt not in _LLAMADAS:
            v.append(f"{donde}: llamada a «{txt}» fuera de la lista blanca")
        if txt == "set_config":
            arg = tokens[i + 2] if i + 2 < len(tokens) else ("", "")
            if not (arg[0] == "str" and arg[1].startswith("contexto_044.")):
                v.append(f"{donde}: set_config de algo que no es contexto_044.* ({arg[1]!r})")
        if txt == "execute" and not (permite_execute and _execute_exacto(tokens, i)):
            v.append(f"{donde}: EXECUTE que no es uno de los tres REVOKE exactos")
    return v


def _violaciones(sql: str) -> list[str]:
    """Todo lo que la 044 hace distinto de su forma autorizada. Lista vacía = conforme."""
    sentencias, actual = [], []
    for t in _lex(sql):
        if t == ("p", ";"):
            sentencias.append(actual)
            actual = []
        else:
            actual.append(t)
    if actual:
        return ["texto ejecutable tras el último ;"]
    primeras = [s[0][1] if s else "" for s in sentencias]
    if primeras != ["begin", "set", "set", "do", "alter", "alter", "revoke", "do", "do", "select", "commit"]:
        return [f"sentencias de primer nivel inesperadas: {primeras}"]
    if sentencias[0] != [("id", "begin")] or sentencias[10] != [("id", "commit")]:
        return ["BEGIN o COMMIT con algo más"]

    def plano(s):
        return " ".join(t[1] if t[0] in ("id", "p", "num") else f"<{t[0]}:{t[1]}>" for t in s)

    v = []
    for k, esperada in {1: "set local lock_timeout = <str:3s>",
                        2: "set local search_path = pg_catalog , pg_temp",
                        4: "alter table public . intencion_sesion enable row level security",
                        5: "alter table public . intencion_evento enable row level security",
                        6: "revoke all privileges on table public . intencion_sesion , public . intencion_evento "
                           "from public"}.items():
        if plano(sentencias[k]) != esperada:
            v.append(f"sentencia {k}: {plano(sentencias[k])!r}")
    v += _codigo_limpio(sentencias[9], "SELECT final")
    for k in (3, 7, 8):
        s = sentencias[k]
        if len(s) != 2 or s[1][0] != "dolar":
            v.append(f"bloque DO {k} con forma inesperada")
            continue
        v += _codigo_limpio(_lex(s[1][1]), f"DO {k}", permite_execute=(k == 7))
    return v


def test_la_044_tiene_exactamente_la_forma_autorizada():
    sql = M044.read_text(encoding="utf-8")
    assert _violaciones(sql) == []
    # El REVOKE dinámico es, exactamente, a los tres roles y a PUBLIC sobre las tablas y la secuencia.
    literales = [t[1] for t in _lex(sql.split("-- ── 2 · REVOKE", 1)[1].split("-- ── 3 ·", 1)[0])
                 if t[0] == "dolar"]
    codigo = _lex(literales[0])
    revokes = sorted(t[1] for t in codigo if t[0] == "str" and t[1].startswith("REVOKE"))
    assert revokes == ["REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM %I", "REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM PUBLIC",
                       "REVOKE ALL PRIVILEGES ON TABLE public.intencion_sesion, public.intencion_evento FROM %I"]
    assert ("str", "anon") in codigo and ("str", "authenticated") in codigo and ("str", "service_role") in codigo
    # La secuencia se descubre por dependencia y DEFAULT; MAINTAIN se mide donde existe.
    cuerpo = " ".join(t[1] for t in _lex(sql))
    assert "pg_attrdef" in cuerpo and "server_version_num" in cuerpo and "MAINTAIN" in cuerpo
    # Las compuertas fail-closed (mandato 1-11 y las de la revisión adversarial) y la verificación posterior.
    for compuerta in ("no existe", "no es una tabla ordinaria", "las secuencias de las tablas no son las medidas",
                      "DEFAULT que usan secuencias o funciones no medidas", "el dueño no es quien aplica",
                      "ya existen", "FORCE ROW LEVEL SECURITY ya activado", "publicación de replicación",
                      "vistas que dependen", "reglas sobre", "herencia o particiones", "FK entrantes",
                      "funciones que nombran", "SECURITY DEFINER alcanzables por un rol externo", "triggers sobre",
                      "concedidos por otro rol", "destinatarios no medidos", "ACL de columna", "miembro del dueño",
                      "privilegios por defecto",
                      "cambió el conjunto de secuencias", "RLS no quedó activado", "apareció FORCE",
                      "aparecieron", "quedan privilegios en pie", "quedan privilegios de columna",
                      "conserva % efectivo sobre alguna columna", "sobre la secuencia", "perdió",
                      "apareció un puente", "con autoridad", "cambió la estructura"):
        assert compuerta in sql, compuerta


# Los 12 disfraces de la revisión adversarial (y algunos más): el examen tiene que verlos TODOS.
_ANCLA = "    -- 1 · Las dos tablas existen y son tablas ordinarias."
_MUTANTES = {
    "literal con --": "    PERFORM '--', count(*) FROM public.intencion_sesion;\n",
    "-- y luego UPDATE": "    PERFORM '--'; UPDATE public.intencion_sesion SET score = score;\n",
    "MERGE": "    MERGE INTO public.intencion_evento e USING (SELECT 1 AS x) s ON false WHEN MATCHED THEN UPDATE SET score = 0;\n",
    "FROM ONLY": "    PERFORM count(*) FROM ONLY public.intencion_sesion;\n",
    "TABLE": "    PERFORM * FROM (TABLE public.intencion_sesion) t;\n",
    "unión por coma": "    PERFORM count(*) FROM pg_class c, public.intencion_sesion s;\n",
    "identificador entre comillas": '    PERFORM count(*) FROM public."intencion_sesion";\n',
    "FROM/**/": "    PERFORM count(*) FROM/**/public.intencion_sesion;\n",
    "table_to_xml": "    PERFORM table_to_xml(tablas[1]::regclass, true, false, '');\n",
    "EXECUTE de lectura": "    EXECUTE format('SELECT count(*) FROM %s', tablas[1]::regclass);\n",
    "ANALYZE y pg_stats": "    ANALYZE public.intencion_sesion; PERFORM count(*) FROM pg_stats;\n",
    "nextval": "    PERFORM nextval('public.intencion_evento_id_seq');\n",
    "U& escapado": '    PERFORM count(*) FROM U&"intencion\\005fsesion";\n',
    "EXECUTE arbitrario": "    EXECUTE 'SELECT 1';\n",
    "lectura por nombre de catálogo de usuario": "    PERFORM count(*) FROM intencion_evento;\n",
    # 2.ª ronda: funciones que ejecutan texto, set_config y EXECUTE fuera de su sitio.
    "ts_stat": "    PERFORM * FROM ts_stat('SELECT to_tsvector(resumen) FROM public.intencion_sesion');\n",
    "dblink_exec": "    PERFORM dblink_exec('dbname=x', 'TRUNCATE public.intencion_evento');\n",
    "get_raw_page": "    PERFORM get_raw_page('public.intencion_sesion', 0);\n",
    "llamada calificada": "    PERFORM pg_catalog.pg_read_file('base/1/1');\n",
    "set_config del search_path": "    PERFORM set_config('search_path', 'sombra, pg_catalog', true);\n",
    "EXECUTE de un REVOKE válido fuera de su bloque": "    EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM PUBLIC', seq);\n",
    "lectura por ctid": "    PERFORM resumen FROM pg_class c, public.intencion_sesion s WHERE s.ctid = '(0,1)'::tid;\n",
}


@pytest.mark.parametrize("nombre", sorted(_MUTANTES))
def test_el_examen_de_forma_ve_cada_disfraz(nombre):
    sql = M044.read_text(encoding="utf-8")
    assert sql.count(_ANCLA) == 1
    assert _violaciones(sql.replace(_ANCLA, _MUTANTES[nombre] + _ANCLA)), nombre


@pytest.mark.parametrize("viejo, nuevo", [
    # Plantilla del REVOKE con una segunda sentencia: EXECUTE sin INTO acepta varias.
    ("EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM PUBLIC', seq);",
     "EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM PUBLIC; SELECT count(*) FROM public.intencion_sesion', seq);"),
    # Argumento distinto del esperado.
    ("EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM %I', seq, rol);",
     "EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM %I', seq, current_setting('x'));"),
])
def test_el_examen_de_forma_ve_un_execute_alterado_en_el_bloque_del_revoke(viejo, nuevo):
    sql = M044.read_text(encoding="utf-8")
    assert sql.count(viejo) == 1
    assert _violaciones(sql.replace(viejo, nuevo))


def test_el_examen_de_forma_ve_una_sentencia_de_primer_nivel_colada():
    sql = M044.read_text(encoding="utf-8")
    assert _violaciones(sql.replace("\nCOMMIT;", "\nSELECT count(*) FROM public.intencion_sesion;\nCOMMIT;", 1))
    assert _violaciones(sql.replace("SET LOCAL lock_timeout = '3s';",
                                    "SET LOCAL lock_timeout = '3s';\nTRUNCATE public.intencion_evento;", 1))
    assert _violaciones(sql.replace("\nBEGIN;", "\nBEGIN ISOLATION LEVEL READ UNCOMMITTED;", 1))


def test_el_rollback_documentado_es_el_inverso_exacto_y_esta_comentado():
    sql = M044.read_text(encoding="utf-8")
    rollback = sql.split("-- ── ROLLBACK", 1)[1]
    for linea in ("ALTER TABLE public.intencion_sesion DISABLE ROW LEVEL SECURITY;",
                  "ALTER TABLE public.intencion_evento DISABLE ROW LEVEL SECURITY;",
                  "GRANT ALL PRIVILEGES ON TABLE public.intencion_sesion, public.intencion_evento "
                  "TO anon, authenticated, service_role;",
                  "GRANT ALL PRIVILEGES ON SEQUENCE public.intencion_evento_id_seq TO anon, authenticated, service_role;"):
        assert linea in rollback, linea
    # Todo el ROLLBACK está comentado: aplicar la 044 nunca lo ejecuta.
    assert all(l.startswith("--") or not l.strip() for l in rollback.splitlines()[1:])


def test_ningun_consumidor_del_producto_usa_los_roles_externos_sobre_estas_tablas():
    """El frontend solo usa auth y Storage; nadie llama a PostgREST; el backend escribe y lee como dueño."""
    for ruta in (RAIZ / "frontend" / "src").rglob("*"):
        if ruta.suffix in (".js", ".jsx", ".ts", ".tsx") and ruta.is_file():
            codigo = ruta.read_text(encoding="utf-8", errors="replace")
            assert not re.search(r"intencion_(sesion|evento)", codigo), ruta
    for ruta in [*(RAIZ / "app").rglob("*.py"), *(RAIZ / "scripts").rglob("*.py")]:
        codigo = ruta.read_text(encoding="utf-8", errors="replace")
        if re.search(r"intencion_(sesion|evento)", codigo):
            assert "rest/v1" not in codigo and "service_role" not in codigo, ruta


# ──────────────────────────── B · Postgres 15 real ────────────────────────────
URL = os.getenv("TEST_DATABASE_URL", "")
pg = pytest.mark.skipif(not URL, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas")


async def _limpia(cx):
    await cx.execute(text("DROP TABLE IF EXISTS public.hija044"))
    await cx.execute(text("DROP FUNCTION IF EXISTS public.f044_definer(text)"))
    await cx.execute(text("DO $$ BEGIN IF pg_has_role('anon', 'pg_read_all_data', 'MEMBER') THEN "
                          "REVOKE pg_read_all_data FROM anon; END IF; END $$;"))
    await cx.execute(text("DROP TABLE IF EXISTS public.intencion_evento, public.intencion_sesion CASCADE"))
    await cx.execute(text(
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_class WHERE oid = to_regclass('public.activos_inmutables') "
        f"AND pg_get_userbyid(relowner) = '{DUENO}') THEN DROP TABLE public.activos_inmutables CASCADE; END IF; END $$;"))
    await cx.execute(text(f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{DUENO}') THEN "
                          f"ALTER DEFAULT PRIVILEGES FOR ROLE {DUENO} IN SCHEMA public REVOKE ALL ON TABLES FROM anon; "
                          f"END IF; END $$;"))


@pytest.fixture
async def banco(monkeypatch):
    """Las dos tablas creadas por la migración REAL 018 como un dueño NOSUPERUSER + BYPASSRLS, con la
    exposición medida en producción (los tres roles con todo, la secuencia abierta) y con filas escritas
    por el `registrar_intencion` REAL."""
    from app.config import settings
    from app.esquema_requerido import aplicar_migracion
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    if settings.database_url and URL.split("@")[-1] in settings.database_url:
        pytest.fail("TEST_DATABASE_URL apunta a la base del producto. Abortado.")
    admin = create_async_engine(URL, poolclass=NullPool)
    async with admin.begin() as cx:
        for rol in ROLES:
            await cx.execute(text(
                f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{rol}') "
                f"THEN CREATE ROLE {rol} NOLOGIN; END IF; END $$;"))
        await cx.execute(text(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{DUENO}') "
            f"THEN CREATE ROLE {DUENO} NOLOGIN NOSUPERUSER BYPASSRLS; END IF; END $$;"))
        await cx.execute(text(f"GRANT USAGE, CREATE ON SCHEMA public TO {DUENO}"))
        await cx.execute(text("GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role"))
        sr_bypass = (await cx.execute(text("SELECT rolbypassrls FROM pg_roles WHERE rolname='service_role'"))).scalar()
        await cx.execute(text("ALTER ROLE service_role BYPASSRLS"))   # como en producción
        for rel in ("public.activos_inmutables", *TABLAS):
            dueno_actual = (await cx.execute(text(
                f"SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = to_regclass('{rel}')"))).scalar()
            if dueno_actual not in (None, DUENO):
                pytest.fail(f"{rel} ya existe y es de {dueno_actual}: no se toca")
        await _limpia(cx)

    motores = []

    def motor(rol):
        m = create_async_engine(URL, poolclass=NullPool, connect_args={
            "server_settings": {"role": rol, "search_path": "public"}})
        motores.append(m)
        return m

    dueno = motor(DUENO)
    Sesion = async_sessionmaker(dueno, expire_on_commit=False)
    async with dueno.begin() as cx:
        # Doble de forma del destino de la FK (la 018 la declara); la tabla real no es de esta unidad.
        await cx.execute(text("CREATE TABLE public.activos_inmutables (id uuid PRIMARY KEY)"))
        await cx.execute(text(f"INSERT INTO public.activos_inmutables (id) VALUES ('{ACTIVO}')"))
    async with Sesion() as s:
        await aplicar_migracion(str(M018), db=s)          # la migración REAL 018
    async with dueno.begin() as cx:                       # la exposición medida en producción
        await cx.execute(text("GRANT ALL PRIVILEGES ON TABLE public.intencion_sesion, public.intencion_evento "
                              "TO anon, authenticated, service_role"))
        await cx.execute(text(f"GRANT ALL PRIVILEGES ON SEQUENCE {SEQ} TO anon, authenticated, service_role"))
    monkeypatch.setattr(chat, "AsyncSessionLocal", Sesion)
    monkeypatch.setattr(chat, "_intencion_ready", False)
    await chat.registrar_intencion(SID, [HumanMessage(content="Hola")])          # estado `identificado`
    try:
        yield SimpleNamespace(admin=admin, motor=motor, dueno=dueno, Sesion=Sesion)
    finally:
        for m in motores:
            await m.dispose()
        async with admin.begin() as cx:
            await _limpia(cx)
            if not sr_bypass:
                await cx.execute(text("ALTER ROLE service_role NOBYPASSRLS"))
        await admin.dispose()


async def _uno(motor, sql):
    async with motor.connect() as cx:
        return (await cx.execute(text(sql))).scalar()


async def _intenta(motor, sql):
    try:
        async with motor.begin() as cx:
            await cx.execute(text(sql))
        return "ok"
    except Exception as e:  # noqa: BLE001
        return type(getattr(e, "orig", e)).__name__ + ": " + str(getattr(e, "orig", e))[:110]


async def _efectivos(admin, rol, rel):
    return [p for p in PRIVS if await _uno(admin, f"SELECT has_table_privilege('{rol}', '{rel}', '{p}')")]


async def _huella(b):
    return await _uno(b.dueno,
                      "SELECT md5(coalesce((SELECT string_agg(t::text, '|' ORDER BY t.session_id) "
                      "FROM public.intencion_sesion t), '')) || ':' || "
                      "md5(coalesce((SELECT string_agg(t::text, '|' ORDER BY t.id) FROM public.intencion_evento t), ''))")


async def _fk(admin):
    return await _uno(admin, "SELECT string_agg(conname || ' ' || pg_get_constraintdef(oid), ' | ' ORDER BY conname) "
                             "FROM pg_constraint WHERE contype = 'f' AND conrelid IN "
                             "('public.intencion_sesion'::regclass, 'public.intencion_evento'::regclass)")


async def _contadores(b):
    """Lo que una lectura o una escritura de la migración habría movido: los contadores de `pg_stat_user_tables`
    de las dos tablas y el estado de la secuencia. Cada backend vuelca sus contadores al terminar: se lee hasta
    que dos lecturas seguidas coinciden."""
    q = ("SELECT string_agg(concat_ws(',', s.relname, s.seq_scan, s.seq_tup_read, coalesce(s.idx_scan, 0), "
         "coalesce(s.idx_tup_fetch, 0), s.n_tup_ins, s.n_tup_upd, s.n_tup_del, s.n_tup_hot_upd, s.analyze_count, "
         "s.vacuum_count, coalesce(io.heap_blks_read, 0), coalesce(io.heap_blks_hit, 0), "
         "coalesce(io.idx_blks_read, 0), coalesce(io.idx_blks_hit, 0)), ' | ' ORDER BY s.relname) "
         "FROM pg_stat_user_tables s JOIN pg_statio_user_tables io USING (relid) "
         "WHERE s.relid IN ('public.intencion_sesion'::regclass, 'public.intencion_evento'::regclass)")
    previo = None
    for _ in range(25):
        async with b.admin.connect() as cx:
            await cx.execute(text("SELECT pg_stat_clear_snapshot()"))
            ahora = ((await cx.execute(text(q))).scalar(),
                     (await cx.execute(text(f"SELECT last_value || ',' || is_called FROM {SEQ}"))).scalar())
        if ahora == previo:
            return ahora
        previo = ahora
        await asyncio.sleep(0.4)
    pytest.fail(f"los contadores no se estabilizaron: {previo}")


async def _aplica_044(b, rol=None):
    from app.esquema_requerido import aplicar_migracion
    from sqlalchemy.ext.asyncio import async_sessionmaker
    Sesion = b.Sesion if rol is None else async_sessionmaker(b.motor(rol), expire_on_commit=False)
    async with Sesion() as s:
        await aplicar_migracion(str(M044), db=s)


async def _lift_como(b, rol, monkeypatch):
    """La lectura REAL del lift (`metricas_lift`), ejecutada con la sesión de `rol`. Un fallo de lectura de
    `intencion_evento` lo traga el propio endpoint: se ve como 0 transiciones registradas."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async def leads(db, *_a, **_k):
        return [{"session_id": SID, "estado": "anonimo", "handoff_estado": None}]

    async def sin_lead_actividad(db):
        raise RuntimeError("lead_actividad fuera de esta prueba")

    monkeypatch.setattr(assets, "_leads_del_corredor", leads)
    monkeypatch.setattr(chat, "ensure_lead_actividad", sin_lead_actividad)
    usuario = SimpleNamespace(rol="corredor", user_id="u-044", agency_id=None)
    async with async_sessionmaker(b.motor(rol), expire_on_commit=False)() as db:
        return await assets.metricas_lift.__wrapped__(request=None, user=usuario, db=db)


@pg
async def test_044_cierra_tablas_y_secuencia_y_el_backend_real_sigue(banco, monkeypatch):
    b = banco
    admin, motor = b.admin, b.motor
    # ── CONTROL POSITIVO: la exposición de producción está reproducida ──
    for rel in TABLAS:
        assert await _uno(admin, f"SELECT relrowsecurity FROM pg_class WHERE oid = '{rel}'::regclass") is False
    for rol in ROLES:
        for rel in TABLAS:
            assert await _efectivos(admin, rol, rel) == list(PRIVS), (rol, rel)
        assert await _uno(admin, f"SELECT has_sequence_privilege('{rol}', '{SEQ}', 'UPDATE')")
    anon = motor("anon")
    assert await _uno(anon, "SELECT count(*) FROM public.intencion_sesion") == 1
    assert await _uno(anon, "SELECT resumen IS NOT NULL FROM public.intencion_sesion") is True
    assert await _intenta(anon, "INSERT INTO public.intencion_evento (session_id, estado, nivel) "
                                "VALUES ('falsa', 'confirmado', 'caliente')") == "ok"      # falsea el lift
    # El ORÁCULO de la FK: un id existente entra; uno inexistente choca con la FK. Distinguibles.
    assert await _intenta(anon, "INSERT INTO public.intencion_sesion (session_id, activo_id, estado, nivel) "
                                f"VALUES ('sonda-1', '{ACTIVO}', 'anonimo', 'frio')") == "ok"
    r = await _intenta(anon, "INSERT INTO public.intencion_sesion (session_id, activo_id, estado, nivel) "
                             f"VALUES ('sonda-2', '{NO_EXISTE}', 'anonimo', 'frio')")
    assert "ForeignKeyViolation" in r, r
    assert await _intenta(anon, f"SELECT setval('{SEQ}', (SELECT last_value FROM {SEQ}))") == "ok"
    assert (await _lift_como(b, "anon", monkeypatch))["_transiciones_registradas"] == 1   # anon lee la serie
    async with b.dueno.begin() as cx:
        await cx.execute(text("DELETE FROM public.intencion_evento WHERE session_id = 'falsa'"))
        await cx.execute(text("DELETE FROM public.intencion_sesion WHERE session_id = 'sonda-1'"))
    huella, fk = await _huella(b), await _fk(admin)
    assert "activos_inmutables" in fk
    contadores = await _contadores(b)

    await _aplica_044(b)

    # ── LA MIGRACIÓN NO LEYÓ NI ESCRIBIÓ FILAS: ni un escaneo, ni una tupla, ni un ANALYZE, ni la secuencia ──
    assert await _contadores(b) == contadores

    # ── EL PERÍMETRO QUEDÓ CERRADO ──
    for rel in TABLAS:
        estado = await _uno(admin, "SELECT relrowsecurity::text || '|' || relforcerowsecurity::text "
                                   f"FROM pg_class WHERE oid = '{rel}'::regclass")
        assert estado == "true|false", (rel, estado)
    assert await _uno(admin, "SELECT count(*) FROM pg_policy WHERE polrelid IN "
                             "('public.intencion_sesion'::regclass, 'public.intencion_evento'::regclass)") == 0
    for rol in ("public", *ROLES):
        for rel in TABLAS:
            assert await _efectivos(admin, rol, rel) == [], (rol, rel)
            for p in ("SELECT", "INSERT", "UPDATE", "REFERENCES"):
                assert not await _uno(admin, f"SELECT has_any_column_privilege('{rol}', '{rel}', '{p}')"), (rol, rel, p)
        for p in ("USAGE", "SELECT", "UPDATE"):
            assert not await _uno(admin, f"SELECT has_sequence_privilege('{rol}', '{SEQ}', '{p}')"), (rol, p)
    externos = await _uno(admin, "SELECT count(*) FROM pg_class c, aclexplode(c.relacl) a WHERE a.grantee <> c.relowner "
                                 "AND c.oid IN ('public.intencion_sesion'::regclass, 'public.intencion_evento'::regclass, "
                                 f"'{SEQ}'::regclass)")
    assert externos == 0
    for rol in ROLES:
        m = motor(rol)
        for sql in ("SELECT count(*) FROM public.intencion_sesion",
                    "SELECT resumen FROM public.intencion_sesion",
                    "SELECT count(*) FROM public.intencion_evento",
                    "INSERT INTO public.intencion_evento (session_id, estado, nivel) VALUES ('x', 'confirmado', 'caliente')",
                    f"INSERT INTO public.intencion_sesion (session_id, activo_id, estado, nivel) "
                    f"VALUES ('x', '{ACTIVO}', 'anonimo', 'frio')",
                    f"INSERT INTO public.intencion_sesion (session_id, activo_id, estado, nivel) "
                    f"VALUES ('y', '{NO_EXISTE}', 'anonimo', 'frio')",
                    "UPDATE public.intencion_sesion SET score = 100",
                    "DELETE FROM public.intencion_evento",
                    "TRUNCATE public.intencion_sesion",
                    "TRUNCATE public.intencion_evento",
                    f"SELECT nextval('{SEQ}')",
                    f"SELECT setval('{SEQ}', 1)",
                    f"SELECT last_value FROM {SEQ}"):
            r = await _intenta(m, sql)
            # El oráculo de la FK desaparece: existente o no, el mismo «permission denied».
            assert "InsufficientPrivilege" in r and "permission denied" in r, (rol, sql, r)

    # ── LAS FILAS Y LA ESTRUCTURA, INTACTAS ──
    assert await _huella(b) == huella
    assert await _fk(admin) == fk

    # ── EL BACKEND REAL, COMO DUEÑO, SIGUE FUNCIONANDO ──
    monkeypatch.setattr(chat, "_intencion_ready", False)          # fuerza el DDL en runtime
    await chat.registrar_intencion(SID, [
        HumanMessage(content="Hola"),
        AIMessage(content="", tool_calls=[{"name": "solicitar_handoff", "args": {}, "id": "t1"}]),
        ToolMessage(content="ok", name="solicitar_handoff", tool_call_id="t1"),
        HumanMessage(content="Quiero agendar una visita este sábado, ¿me pasas con el corredor?"),
    ])
    assert chat._intencion_ready is True
    # `identificado` → `intencion` con handoff: upsert del estado y un evento nuevo en la serie.
    assert await _uno(b.dueno, f"SELECT count(*) FROM public.intencion_evento WHERE session_id = '{SID}'") == 2
    assert await _uno(b.dueno, "SELECT estado || '|' || handoff_sugerido::text FROM public.intencion_sesion "
                               f"WHERE session_id = '{SID}'") == "intencion|true"
    # El lift, por el endpoint REAL: el dueño lee la serie; anon ya no (0 transiciones).
    assert (await _lift_como(b, DUENO, monkeypatch))["_transiciones_registradas"] == 1
    assert (await _lift_como(b, "anon", monkeypatch))["_transiciones_registradas"] == 0
    # CRUD del dueño, secuencia incluida.
    for sql in ("INSERT INTO public.intencion_evento (session_id, estado, nivel) VALUES ('d', 'anonimo', 'frio')",
                "UPDATE public.intencion_evento SET score = 1 WHERE session_id = 'd'",
                "DELETE FROM public.intencion_evento WHERE session_id = 'd'"):
        assert await _intenta(b.dueno, sql) == "ok", sql

    # ── IDEMPOTENTE ──
    acl = await _uno(admin, "SELECT string_agg(relacl::text, ' ' ORDER BY relname) FROM pg_class WHERE relname IN "
                            "('intencion_sesion', 'intencion_evento', 'intencion_evento_id_seq')")
    await _aplica_044(b)
    assert await _uno(admin, "SELECT string_agg(relacl::text, ' ' ORDER BY relname) FROM pg_class WHERE relname IN "
                             "('intencion_sesion', 'intencion_evento', 'intencion_evento_id_seq')") == acl


async def _sin_cambios(b, acl_antes):
    for rel in TABLAS:
        assert await _uno(b.admin, f"SELECT relrowsecurity FROM pg_class WHERE oid = '{rel}'::regclass") is False
    assert await _uno(b.admin, "SELECT string_agg(coalesce(relacl::text, ''), ' ' ORDER BY relname) FROM pg_class "
                               "WHERE relname IN ('intencion_sesion', 'intencion_evento', 'intencion_evento_id_seq')"
                      ) == acl_antes


@pg
@pytest.mark.parametrize("prepara, mensaje, como", [
    ("CREATE POLICY p044 ON public.intencion_sesion FOR SELECT USING (true)", "ya existen", "dueno"),
    (f"ALTER DEFAULT PRIVILEGES FOR ROLE {DUENO} IN SCHEMA public GRANT SELECT ON TABLES TO anon",
     "privilegios por defecto", "dueno"),
    ("GRANT SELECT (resumen) ON public.intencion_sesion TO anon", "ACL de columna", "dueno"),
    # Revisión adversarial: una columna de SISTEMA también tiene ACL propio.
    ("GRANT SELECT (xmin) ON public.intencion_sesion TO anon", "ACL de columna", "dueno"),
    # …una SECURITY DEFINER con cuerpo SQL estándar y SQL dinámico que no nombra nada (prosrc vacío):
    ("CREATE FUNCTION public.f044_definer(q text) RETURNS xml LANGUAGE sql SECURITY DEFINER "
     "BEGIN ATOMIC SELECT query_to_xml(q, true, false, ''); END", "SECURITY DEFINER alcanzables", "dueno"),
    # …una FK entrante (oráculo de existencia que el REVOKE no retira):
    ("CREATE TABLE public.hija044 (s text REFERENCES public.intencion_sesion (session_id))", "FK entrantes", "dueno"),
    # …y un rol externo miembro de un rol predefinido de datos.
    ("GRANT pg_read_all_data TO anon", "miembro", "admin"),
])
async def test_044_aborta_sin_tocar_nada_si_una_precondicion_no_es_la_medida(banco, prepara, mensaje, como):
    async with (banco.dueno if como == "dueno" else banco.admin).begin() as cx:
        await cx.execute(text(prepara))
    acl = await _uno(banco.admin, "SELECT string_agg(coalesce(relacl::text, ''), ' ' ORDER BY relname) FROM pg_class "
                                  "WHERE relname IN ('intencion_sesion', 'intencion_evento', 'intencion_evento_id_seq')")
    with pytest.raises(Exception, match=mensaje):
        await _aplica_044(banco)
    await _sin_cambios(banco, acl)
    async with banco.dueno.begin() as cx:
        await cx.execute(text("DROP POLICY IF EXISTS p044 ON public.intencion_sesion"))
