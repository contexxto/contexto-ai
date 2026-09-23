"""Migración 030 · Inventory Truth fase A · el esquema, y lo que NO puede tocar.

QUÉ CONGELA, y qué NO.

    congela    que la migración añade capacidad estructural y NADA más: sin backfill, sin
               filas de fuente, sin default a inventario real, con procedencia separada para
               propiedad y anuncio, y sin un solo consumidor productivo
    NO congela que el inventario sea real, ni que la procedencia esté poblada. Eso es 030B

## QUÉ PRUEBA ESTE FICHERO Y QUÉ NO PRUEBA

Estos tests leen el SQL como TEXTO. Ninguno abre una conexión, así que NO prueban que
PostgreSQL acepte el fichero ni que aplicarlo produzca el esquema descrito.

Se prueba como texto porque la propiedad que más importa es una AUSENCIA —que nadie lea
estas columnas, que ninguna tabla nueva quede expuesta— y las ausencias no se ven
ejecutando: un SQL perfectamente válido que expusiera la tabla por PostgREST pasaría una
prueba de aplicación y fallaría el propósito.

Que además es válido y hace lo que dice se comprobó APARTE, contra un PostgreSQL local y
desechable, con un arnés que vive en el scratchpad de la sesión —necesita crear y borrar
bases enteras— y cuyo resultado está en el informe de la unidad. Ese arnés no está en el
repositorio, así que esta suite no lo sustituye.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
MIGRACION = RAIZ / "migrations" / "030_inventory_truth_schema.sql"
SQL = MIGRACION.read_text(encoding="utf-8")


def _sin_comentarios(texto: str) -> str:
    """El SQL ejecutable, sin la prosa. Los comentarios de esta migración NOMBRAN los
    canales y los valores prohibidos para explicar por qué no están — un guard que leyera
    el fichero entero se detectaría a sí mismo en su propia justificación. Ya ha pasado
    nueve veces en este repositorio; aquí se evita de entrada."""
    return "\n".join(l.split("--")[0] for l in texto.splitlines())


EJECUTABLE = _sin_comentarios(SQL)


def _check_de(columna: str) -> set[str]:
    """Los valores literales de un CHECK ... IN (...) sobre `columna`."""
    m = re.search(rf"{columna}\s+TEXT\s+NOT\s+NULL\s*\n?\s*CHECK\s*\({columna}\s+IN\s*\(([^)]*)\)",
                  EJECUTABLE, re.IGNORECASE)
    if m is None:
        m = re.search(rf"{columna}\s+TEXT\s+NULL\s*\n?\s*CHECK\s*\({columna}\s+IN\s*\(([^)]*)\)",
                      EJECUTABLE, re.IGNORECASE)
    assert m is not None, f"no se encontró el CHECK de {columna}"
    return set(re.findall(r"'([^']+)'", m.group(1)))


# ══ T1-T4 · LA TABLA DE FUENTES ════════════════════════════════════════════════════


def test_T1_la_tabla_de_fuentes_tiene_las_columnas_exactas():
    assert "CREATE TABLE IF NOT EXISTS inventory_source" in EJECUTABLE
    for col in ("id UUID PRIMARY KEY", "source_type TEXT NOT NULL",
                "internal_name TEXT NOT NULL UNIQUE", "provider_identifier TEXT NULL",
                "usage_permission_status TEXT NOT NULL",
                "permission_effective_at TIMESTAMPTZ NULL",
                "permission_expires_at   TIMESTAMPTZ NULL",
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"):
        assert col in EJECUTABLE, f"falta: {col}"


def test_T2_T3_source_type_lleva_FUENTES_y_ningun_CANAL():
    """La distinción que ordena todo el diseño: un script que llama a un endpoint es un
    cliente sobre un canal, no una fuente."""
    valores = _check_de("source_type")
    assert valores == {"internal_demo", "broker"}, (
        f"la taxonomía de fuentes cambió: {sorted(valores)}")

    for canal in ("csv_supplied", "partner_api", "http_asset", "http_ingest",
                  "direct_db", "sql_seed"):
        assert canal not in valores, f"'{canal}' es un CANAL y está en source_type"


def test_T4_el_permiso_distingue_autoridad_y_no_caducidad():
    """`expired` NO es un estado: se deriva de `permission_expires_at`. Tenerlo como valor
    permitiría que la columna y la fecha se contradijeran. `revoked` sí lo es."""
    valores = _check_de("usage_permission_status")
    assert valores == {"unknown", "internal_demo", "authorized", "restricted", "revoked"}
    assert "expired" not in valores, "la caducidad se deriva de la fecha, no se declara"

    assert "inventory_source_vigencia_coherente" in EJECUTABLE
    assert "permission_expires_at >= permission_effective_at" in EJECUTABLE


# ══ T5-T7 · LA TABLA DE EJECUCIONES ════════════════════════════════════════════════


def test_T5_la_tabla_de_ejecuciones_tiene_las_columnas_exactas():
    assert "CREATE TABLE IF NOT EXISTS inventory_ingestion_event" in EJECUTABLE
    for col in ("id UUID PRIMARY KEY", "source_id UUID NOT NULL",
                "channel TEXT NOT NULL", "started_at   TIMESTAMPTZ NOT NULL",
                "completed_at TIMESTAMPTZ NULL", "external_batch_id TEXT NULL",
                "status TEXT NOT NULL"):
        assert col in EJECUTABLE, f"falta: {col}"


def test_T6_el_canal_lleva_los_CUATRO_canales_medidos():
    valores = _check_de("channel")
    assert valores == {"direct_db", "http_asset", "http_ingest", "sql_seed"}
    for fuente in ("internal_demo", "broker", "partner"):
        assert fuente not in valores, f"'{fuente}' es una FUENTE y está en channel"

    assert _check_de("status") == {"running", "completed", "failed"}


def test_T7_la_ejecucion_apunta_a_su_fuente_y_NUNCA_se_queda_huerfana():
    """`ON DELETE RESTRICT`, jamás `SET NULL`: borrar la fuente no puede borrar la
    procedencia de las filas que trajo."""
    assert re.search(r"source_id UUID NOT NULL\s*\n\s*REFERENCES inventory_source\(id\) "
                     r"ON DELETE RESTRICT", EJECUTABLE)
    assert "ON DELETE SET NULL" not in EJECUTABLE
    assert "ON DELETE CASCADE" not in EJECUTABLE.split("inventory_source")[-1]


# ══ T8-T11 · COLUMNAS DE LA PROPIEDAD ══════════════════════════════════════════════


@pytest.mark.parametrize("columna", [
    "source_id UUID NULL", "ingestion_event_id UUID NULL",
    "inventory_class TEXT NULL", "received_at TIMESTAMPTZ NULL",
    "evidence_exclusion_reason TEXT NULL",
])
def test_T8_las_columnas_de_la_propiedad_nacen_NULLABLE(columna):
    """Nullable y sin default: las 40 filas existentes quedan vacías a propósito."""
    assert f"ADD COLUMN IF NOT EXISTS {columna}" in EJECUTABLE


def test_T9_T10_las_FKs_de_la_propiedad_son_RESTRICT():
    propiedad = EJECUTABLE.split("ALTER TABLE activos_inmutables")[1].split("ALTER TABLE")[0]
    assert propiedad.count("REFERENCES inventory_source(id) ON DELETE RESTRICT") == 1
    assert propiedad.count("REFERENCES inventory_ingestion_event(id) ON DELETE RESTRICT") == 1


def test_T11_inventory_class_usa_EL_VOCABULARIO_DEL_CONTRATO():
    """Sin inventar un segundo enum equivalente: los valores salen de `InventoryClass`."""
    from app.contracts.property_v0 import InventoryClass

    del_contrato = {e.value for e in InventoryClass}
    assert del_contrato == {"live", "demo", "test", "unknown"}

    for tabla in ("activos_inmutables", "transacciones_temporales"):
        bloque = EJECUTABLE.split(f"ALTER TABLE {tabla}")[1].split("ALTER TABLE")[0]
        m = re.search(r"inventory_class IN \(([^)]*)\)", bloque)
        assert m is not None, f"{tabla} no restringe inventory_class"
        assert set(re.findall(r"'([^']+)'", m.group(1))) == del_contrato, tabla


# ══ T12-T14 · COLUMNAS DEL ANUNCIO ═════════════════════════════════════════════════


@pytest.mark.parametrize("columna", [
    "source_id UUID NULL", "ingestion_event_id UUID NULL",
    "inventory_class TEXT NULL", "received_at TIMESTAMPTZ NULL",
])
def test_T12_las_columnas_del_anuncio_nacen_NULLABLE(columna):
    anuncio = EJECUTABLE.split("ALTER TABLE transacciones_temporales")[1]
    assert f"ADD COLUMN IF NOT EXISTS {columna}" in anuncio


def test_T13_el_anuncio_tiene_procedencia_PROPIA_no_heredada():
    """No es previsión: `seed_demo_fase1.sql` hace UPDATE de activos que ya existían e
    INSERT de sus anuncios. Ya hay filas con inmueble de un sitio y anuncio de otro."""
    propiedad = EJECUTABLE.split("ALTER TABLE activos_inmutables")[1].split("ALTER TABLE")[0]
    anuncio = EJECUTABLE.split("ALTER TABLE transacciones_temporales")[1]

    for bloque in (propiedad, anuncio):
        assert "source_id UUID NULL" in bloque
        assert "ingestion_event_id UUID NULL" in bloque

    # El anuncio NO lleva razón de exclusión: los 5 del seed SÍ nacieron demo, así que su
    # clase lo dice — una afirmación más fuerte y más simple.
    assert "evidence_exclusion_reason" not in anuncio


def test_T14_las_FKs_del_anuncio_son_RESTRICT():
    anuncio = EJECUTABLE.split("ALTER TABLE transacciones_temporales")[1]
    assert anuncio.count("ON DELETE RESTRICT") == 2


# ══ T15-T18 · LO QUE NO PUEDE ESTAR ════════════════════════════════════════════════


def test_T15_NINGUNA_columna_nueva_tiene_default():
    """Un `DEFAULT 'live'` habría clasificado 40 filas como inventario real sin que nadie
    lo decidiera. Es exactamente el fallo que esta migración cierra."""
    for linea in EJECUTABLE.splitlines():
        if "ADD COLUMN IF NOT EXISTS" in linea:
            assert "DEFAULT" not in linea.upper(), f"columna con default: {linea.strip()}"
    assert "'live'" not in EJECUTABLE.replace("inventory_class IN ('live'", "")


def test_T16_no_se_añade_last_verified_at():
    """Nadie verifica hoy la disponibilidad de un anuncio. Lo único que se verifica en
    terreno es el ENTORNO. Un timestamp sin productor acabaría relleno con `created_at`."""
    assert "last_verified_at" not in EJECUTABLE


def test_T17_T18_no_entran_datos_personales_ni_payloads():
    for prohibido in ("owner_user_id", "owner_agency_id", "user_id", "buyer",
                      "email", "password", "token", "secret", "credential",
                      "JSONB", "jsonb", "payload", "contacto", "crm"):
        assert prohibido not in EJECUTABLE, f"la migración toca {prohibido}"


# ══ T19-T20 · LA RAZÓN DE EXCLUSIÓN ════════════════════════════════════════════════


def test_T19_la_razon_de_exclusion_admite_demo_contaminated_y_nada_especulativo():
    m = re.search(r"evidence_exclusion_reason IN \(([^)]*)\)", EJECUTABLE)
    assert m is not None
    assert set(re.findall(r"'([^']+)'", m.group(1))) == {"demo_contaminated"}


def test_T20_la_exclusion_NO_afirma_el_origen_de_la_propiedad():
    """Dos hechos distintos, dos columnas distintas.

    Está PROBADO que `seed_demo_fase1.sql` corrió —su nota literal está en la base— y eso
    acredita que cinco activos fueron MODIFICADOS por datos demo. No acredita que nacieran
    demo: el script hace UPDATE, no INSERT. Por eso la razón de exclusión es una columna
    aparte de `inventory_class` y no un valor suyo.
    """
    valores_clase = set(re.findall(
        r"inventory_class IN \(([^)]*)\)", EJECUTABLE)[0].split("'")[1::2])
    assert "demo_contaminated" not in valores_clase, (
        "la contaminación se coló como clase de inventario: afirmaría un origen no probado")

    razon = re.search(r"evidence_exclusion_reason TEXT NULL", EJECUTABLE)
    assert razon is not None, "la razón de exclusión tiene que poder no estar"


# ══ T21-T23 · CERO CONSUMIDORES ════════════════════════════════════════════════════


_COLUMNAS_NUEVAS = ("inventory_class", "ingestion_event_id", "evidence_exclusion_reason",
                    "inventory_source", "inventory_ingestion_event")


_DEFINE_EL_VOCABULARIO = RAIZ / "app" / "contracts" / "property_v0.py"
"""El ÚNICO fichero exento, y no es una excepción cómoda: es donde `InventoryClass` nace.

La migración reutiliza ese vocabulario a propósito —T11 lo exige— en vez de inventar un
segundo enum equivalente. Definir el término no es consumir el esquema: `property_v0.py` no
sabe que existe una tabla, no importa nada de base de datos y no lee una columna. Exentar
todo `app/contracts/` habría sido más laxo de lo necesario; se exenta un fichero."""


def _modulos_de_app():
    return [p for p in sorted((RAIZ / "app").rglob("*.py"))
            if "__pycache__" not in str(p) and p != _DEFINE_EL_VOCABULARIO]


def test_T21_ningun_modulo_de_la_APLICACION_conoce_el_esquema_nuevo():
    """La propiedad central de 030A: capacidad estructural con cero consumo."""
    culpables = []
    for py in _modulos_de_app():
        texto = py.read_text(encoding="utf-8", errors="ignore")
        for nombre in _COLUMNAS_NUEVAS:
            if nombre in texto:
                culpables.append(f"{py.relative_to(RAIZ).as_posix()} → {nombre}")
    assert not culpables, f"alguien ya consume el esquema nuevo: {culpables}"


def test_T22_ninguna_consulta_de_BUSQUEDA_o_PANEL_menciona_las_columnas_nuevas():
    """Por AST sobre las cadenas SQL, no sobre el fichero entero: un comentario que
    explique por qué NO se usan no puede poner el guard rojo."""
    for rel in ("app/agent/tools.py", "app/decision/assembler.py", "app/rutas.py",
                "app/routers/assets.py", "app/routers/chat.py"):
        arbol = ast.parse((RAIZ / rel).read_text(encoding="utf-8"))
        literales = [n.value for n in ast.walk(arbol)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        for cadena in literales:
            for nombre in _COLUMNAS_NUEVAS:
                assert nombre not in cadena, f"{rel} consulta {nombre}"


def test_T23_el_carril_del_comprador_no_conoce_el_esquema_nuevo():
    for py in sorted((RAIZ / "app" / "buyer").rglob("*.py")):
        if "__pycache__" in str(py):
            continue
        texto = py.read_text(encoding="utf-8", errors="ignore")
        for nombre in _COLUMNAS_NUEVAS:
            assert nombre not in texto, f"{py.name} conoce {nombre}"


def test_T21b_el_detector_de_consumidores_NO_es_inerte():
    """LA MITAD NEGATIVA. Sin esto, T21-T23 podrían estar recorriendo ficheros donde esos
    nombres nunca aparecerían de todos modos."""
    sintetico = "SELECT inventory_class FROM activos_inmutables"
    assert any(n in sintetico for n in _COLUMNAS_NUEVAS)

    arbol = ast.parse('q = "SELECT a.inventory_class FROM activos_inmutables a"\n')
    literales = [n.value for n in ast.walk(arbol)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert any("inventory_class" in c for c in literales), \
        "el detector por AST no ve la columna dentro de una cadena SQL"


# ══ T24-T25 · IDEMPOTENCIA, ROLLBACK Y NO-BACKFILL ═════════════════════════════════


def test_T24_la_migracion_es_IDEMPOTENTE_segun_la_convencion_del_repo():
    for sentencia in re.findall(r"CREATE TABLE\s+(\S+)", EJECUTABLE):
        assert sentencia == "IF", f"CREATE TABLE sin IF NOT EXISTS: {sentencia}"
    for sentencia in re.findall(r"CREATE (?:UNIQUE )?INDEX\s+(\S+)", EJECUTABLE):
        assert sentencia == "IF", f"CREATE INDEX sin IF NOT EXISTS: {sentencia}"
    assert EJECUTABLE.count("ADD COLUMN IF NOT EXISTS") == 9, \
        "toda columna nueva tiene que ser idempotente"


def test_T25_hay_bloque_de_ROLLBACK_y_deshace_TODO():
    rollback = SQL.split("-- ROLLBACK:")[1]
    for objeto in ("inventory_ingestion_event", "inventory_source", "source_id",
                   "ingestion_event_id", "inventory_class", "received_at",
                   "evidence_exclusion_reason"):
        assert objeto in rollback, f"el rollback no deshace {objeto}"


def test_030A_NO_escribe_ni_una_fila():
    """Ni backfill, ni filas de fuente, ni ejecuciones sembradas."""
    for escritura in ("INSERT INTO", "UPDATE ", "DELETE FROM", "COPY "):
        assert escritura not in EJECUTABLE.upper().replace("ON UPDATE", ""), \
            f"la migración escribe: {escritura}"


def test_las_tablas_nuevas_NO_quedan_expuestas():
    """Crear una tabla en `public` bajo Supabase puede exponerla por PostgREST.

    LO QUE RLS SIN POLÍTICAS HACE, Y LO QUE NO: deja sin acceso a los roles SUJETOS a RLS,
    tengan el GRANT que tengan. NO alcanza al dueño de la tabla —aquí se usa ENABLE, no
    FORCE— ni a los roles con BYPASSRLS, para los que manda el GRANT. Y la migración no
    revoca los permisos que el entorno conceda por su cuenta.

    Lo que este test comprueba, por tanto, es acotado y es lo que la migración sí controla:
    que RLS quede activada en las dos tablas y que el fichero no conceda nada ni cree
    ninguna política."""
    for tabla in ("inventory_source", "inventory_ingestion_event"):
        assert f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY" in \
            re.sub(r"\s+", " ", EJECUTABLE), f"{tabla} sin RLS"

    assert "CREATE POLICY" not in EJECUTABLE, \
        "una política aquí sería conceder acceso que 030A no autoriza"
    assert "GRANT" not in EJECUTABLE, "030A no concede nada a nadie"


def test_el_fichero_EXENTO_no_puede_tocar_la_base():
    """La exención de T21 sólo vale si `property_v0.py` de verdad no accede a nada.

    Si algún día importara SQLAlchemy o el módulo de base, dejaría de ser el sitio donde se
    define un vocabulario y pasaría a ser un consumidor — y la exención habría que quitarla.
    """
    arbol = ast.parse(_DEFINE_EL_VOCABULARIO.read_text(encoding="utf-8"))
    modulos = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.ImportFrom) and n.module:
            modulos.add(n.module)
        elif isinstance(n, ast.Import):
            modulos.update(a.name for a in n.names)

    for prohibido in ("sqlalchemy", "asyncpg", "app.database", "app.models"):
        assert not any(m.startswith(prohibido) for m in modulos),             f"el contrato importa {prohibido}: ya no es sólo una definición"
