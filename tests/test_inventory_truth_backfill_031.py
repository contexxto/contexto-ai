"""Migración 031 · Inventory Truth fase B · qué afirma cada valor escrito, y con qué prueba.

QUÉ CONGELA, y qué NO.

    congela    que 031 escribe procedencia SÓLO donde hay evidencia re-comprobable, que las
               filas se apuntan por clave primaria y no por valores mutables, que las
               precondiciones abortan la migración entera, que repetirla no cambia nada y
               que ni un módulo de la aplicación consume lo que escribe
    NO congela que el inventario sea real. Después de 031 hay CERO propiedades defendibles
               como evidencia de mercado — y ése es el resultado correcto: 031 no arregla
               la ausencia de procedencia, la hace medible

## QUÉ PRUEBA ESTE FICHERO Y QUÉ NO PRUEBA

Estos tests leen el SQL como TEXTO. Comprueban la forma: que el guard existe, que el UPDATE
está acotado, que el literal es el que es. No ejecutan nada, así que NO prueban que
PostgreSQL acepte el fichero ni que las precondiciones aborten de verdad.

Eso se probó aparte, contra un PostgreSQL local y desechable, con la secuencia que exige el
mandato: fixture heredado (40+40) → 030 → 031 → verificar → 031 otra vez → verificar
idéntico, más siete fixtures hostiles. El arnés vive en el scratchpad de la sesión
(`arnes_031_local.py`), no en el repositorio, porque necesita crear y borrar bases enteras.
Su resultado está en el informe de la unidad. Este fichero NO lo sustituye.

Se leen como texto y no contra una base porque las propiedades que más importan son
AUSENCIAS —que nadie consuma estas columnas, que `received_at` no se escriba nunca, que no
haya GRANT— y una ausencia no se observa ejecutando.
"""

from __future__ import annotations

import ast
import pathlib
import re
import uuid

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
MIGRACION = RAIZ / "migrations" / "031_inventory_truth_deterministic_backfill.sql"
SQL = MIGRACION.read_text(encoding="utf-8")
SEED = (RAIZ / "seed_demo_fase1.sql").read_text(encoding="utf-8")


def _sin_comentarios(texto: str) -> str:
    """El SQL ejecutable, sin la prosa.

    Los comentarios de esta migración NOMBRAN a propósito lo que NO hace —`live`, GRANT,
    `received_at`, `acepta_mascotas`— para explicar por qué no está. Un guard que leyera el
    fichero entero se detectaría a sí mismo en su propia justificación. Ha pasado nueve
    veces en este repositorio; aquí se evita de entrada.
    """
    return "\n".join(l.split("--")[0] for l in texto.splitlines())


EJECUTABLE = _sin_comentarios(SQL.split("-- ROLLBACK:")[0])
ROLLBACK = SQL.split("-- ROLLBACK:")[1]

# Los bloques `DO $$ … $$;` llevan `;` dentro, así que se apartan antes de trocear por `;`.
BLOQUES_DO = re.findall(r"DO \$\$(.*?)\$\$;", EJECUTABLE, re.S)
SIN_DO = re.sub(r"DO \$\$.*?\$\$;", " ", EJECUTABLE, flags=re.S)
SENTENCIAS = [s.strip() for s in SIN_DO.split(";") if s.strip()]

UUID_FUENTE = "0c934173-cc6c-54cd-8b98-a3d189809bde"
UUID_EVENTO = "b4079b4f-48f5-5699-bc90-39fd2d4136f4"
INSTANTE = "2026-06-25 15:29:09.874138+00"
NOMBRE_FUENTE = "contexto_datos_demo_internos"


def _lista_de_uuids(texto: str) -> list[str]:
    return re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", texto)


def _sentencias_que_empiezan(verbo: str) -> list[str]:
    return [s for s in SENTENCIAS if s.upper().startswith(verbo)]


def _condicion(sentencia: str) -> str:
    """El WHERE DE LA SENTENCIA, no el de una subconsulta.

    La actualización de los cinco anuncios resuelve la fuente con
    `(SELECT id FROM inventory_source WHERE internal_name = …)`, así que partir por el
    PRIMER `WHERE` devuelve el de la subconsulta: el guard estaría mirando otra cosa y
    pasaría por motivos equivocados. El de la sentencia es siempre el último.
    """
    assert "WHERE" in sentencia, f"sentencia sin WHERE: {sentencia[:60]}"
    return sentencia.rsplit("WHERE", 1)[1]


def _asignaciones(sentencia: str) -> str:
    """Lo que hay entre `SET` y el WHERE de la sentencia: exactamente lo que se escribe."""
    return sentencia.split("SET", 1)[1].rsplit("WHERE", 1)[0]


# ══ T1-T2 · SITIO Y PRERREQUISITO ══════════════════════════════════════════════════


def test_T1_el_fichero_es_el_031_y_no_pisa_ningun_numero():
    assert MIGRACION.exists(), "la migración no está donde dice el mandato"

    otros = [p.name for p in (RAIZ / "migrations").glob("031*.sql")
             if p.name != MIGRACION.name]
    assert not otros, f"hay otra migración con el número 031: {otros}"

    # Y es EL SIGUIENTE número, no uno saltado: 030 tiene que existir y 032 no.
    assert (RAIZ / "migrations" / "030_inventory_truth_schema.sql").exists()
    assert not list((RAIZ / "migrations").glob("032*.sql"))


def test_T2_la_031_EXIGE_la_030_y_lo_dice_claro():
    """Sin esto el fallo sería «relation inventory_source does not exist» a mitad del
    script: correcto, pero mudo sobre qué hay que aplicar antes."""
    assert "to_regclass('public.inventory_source')" in EJECUTABLE
    assert "to_regclass('public.inventory_ingestion_event')" in EJECUTABLE
    assert "031 requiere la 030" in EJECUTABLE

    # Las NUEVE columnas de la 030 se comprueban una a una: que existan las tablas no
    # prueba que la 030 llegara entera. Se leen los pares del VALUES, sin depender de
    # cuántos espacios lleve el alineado.
    bloque = next(b for b in BLOQUES_DO if "information_schema.columns" in b)
    declarados = set(re.findall(r"\('([a-z_]+)',\s*'([a-z_]+)'\)", bloque))
    assert declarados == {
        ("activos_inmutables", "source_id"),
        ("activos_inmutables", "ingestion_event_id"),
        ("activos_inmutables", "inventory_class"),
        ("activos_inmutables", "received_at"),
        ("activos_inmutables", "evidence_exclusion_reason"),
        ("transacciones_temporales", "source_id"),
        ("transacciones_temporales", "ingestion_event_id"),
        ("transacciones_temporales", "inventory_class"),
        ("transacciones_temporales", "received_at"),
    }, f"el prerrequisito no cubre las 9 columnas de la 030: {sorted(declarados)}"


def test_031_NO_recrea_el_esquema_de_la_030():
    """Es un backfill. Si además creara tablas, aplicar 030 dejaría de ser obligatorio y la
    verificación intermedia entre las dos se volvería opcional en la práctica."""
    for ddl in ("CREATE TABLE", "ADD COLUMN", "CREATE INDEX", "ALTER TABLE"):
        assert ddl not in EJECUTABLE.upper(), f"031 hace DDL: {ddl}"


# ══ T3-T4 · LA FUENTE ══════════════════════════════════════════════════════════════


def test_T3_la_fuente_demo_se_inserta_UNA_vez_con_semantica_exacta():
    inserciones = [s for s in _sentencias_que_empiezan("INSERT")
                   if "inventory_source" in s and "inventory_ingestion_event" not in s]
    assert len(inserciones) == 1, f"se esperaba UNA inserción de fuente, hay {len(inserciones)}"

    ins = inserciones[0]
    assert f"'{UUID_FUENTE}'::uuid" in ins, "la fuente no lleva el UUID fijo"
    assert "'internal_demo', 'contexto_datos_demo_internos', NULL" in ins
    assert "'internal_demo', NULL, NULL" in ins, \
        "permiso o fechas de vigencia distintos de lo acordado"
    assert "ON CONFLICT (internal_name) DO NOTHING" in ins, \
        "la idempotencia va por la clave natural, no por el id: si alguien ya creó la "
    assert "'authorized'" not in ins, \
        "no nos concedemos un permiso: a nuestros propios datos la pregunta no aplica"


def test_el_UUID_de_la_fuente_es_DERIVADO_y_recomputable():
    """Un UUID al azar en un fichero versionado se ve igual que uno derivado, pero no se
    puede verificar. Éste sale de una cadena que el propio fichero documenta."""
    esperado = uuid.uuid5(uuid.NAMESPACE_URL,
                          f"contexto:inventory_source:{NOMBRE_FUENTE}")
    assert str(esperado) == UUID_FUENTE
    assert UUID_FUENTE in EJECUTABLE
    assert f"contexto:inventory_source:{NOMBRE_FUENTE}" in SQL, \
        "la derivación tiene que estar escrita en el fichero, o no es verificable"


def test_T4_una_fuente_del_mismo_nombre_con_otra_semantica_ABORTA():
    """`DO NOTHING` es idempotencia, no consentimiento: si la fila que hay no es la que
    creemos, adjudicaríamos inventario a una autoridad equivocada."""
    bloque = next(b for b in BLOQUES_DO if "inventory_source%ROWTYPE" in b)
    assert "fila.source_type <> 'internal_demo'" in bloque
    assert "fila.usage_permission_status <> 'internal_demo'" in bloque
    assert "RAISE EXCEPTION" in bloque
    assert "No se sobrescribe" in bloque

    # Y ninguna sentencia PISA la fila existente.
    assert "DO UPDATE" not in EJECUTABLE.upper(), \
        "un ON CONFLICT DO UPDATE sobrescribiría la fuente que ya estaba"


# ══ T5-T6 · EL EVENTO HISTÓRICO ════════════════════════════════════════════════════


def test_T5_el_evento_historico_se_inserta_UNA_vez_con_el_instante_MEDIDO():
    inserciones = [s for s in _sentencias_que_empiezan("INSERT")
                   if "inventory_ingestion_event" in s]
    assert len(inserciones) == 1, "se esperaba UNA inserción de evento"

    ins = inserciones[0]
    assert f"'{UUID_EVENTO}'::uuid" in ins
    assert "'sql_seed'" in ins, "el canal es el del script .sql, no una fuente"
    assert f"TIMESTAMPTZ '{INSTANTE}'" in ins, \
        "el instante tiene que llevar zona explícita: la columna de origen es naive"
    assert "'completed'" in ins
    assert "ON CONFLICT (id) DO NOTHING" in ins

    # La fuente se resuelve por NOMBRE, no por el UUID literal: si ya existía con otro id
    # —caso que T3/T4 aceptan— el evento tiene que colgar de la que hay.
    assert f"WHERE s.internal_name = '{NOMBRE_FUENTE}'" in ins


def test_completed_at_se_queda_NULL_porque_nadie_lo_midio():
    """Que las filas existan prueba que la ejecución terminó. No dice cuándo. Un
    `completed_at = started_at` habría sido una duración inventada de cero."""
    ins = next(s for s in _sentencias_que_empiezan("INSERT")
               if "inventory_ingestion_event" in s)
    # El orden de columnas de la inserción, con `completed_at` y `external_batch_id` a NULL.
    assert "completed_at" in ins and "external_batch_id" in ins
    assert re.search(r"TIMESTAMPTZ '[^']+',\s*\n\s*NULL,\s*\n\s*NULL,\s*\n\s*'completed'",
                     ins), "completed_at o external_batch_id no están a NULL"

    bloque = next(b for b in BLOQUES_DO if "fila.completed_at" in b)
    assert "fila.completed_at IS NOT NULL" in bloque, \
        "nada comprueba que el evento canónico siga sin fecha de fin"


def test_el_UUID_del_evento_es_DERIVADO_y_recomputable():
    clave = ("contexto:inventory_ingestion_event:sql_seed:seed_demo_fase1:"
             "2026-06-25T15:29:09.874138")
    assert str(uuid.uuid5(uuid.NAMESPACE_URL, clave)) == UUID_EVENTO
    assert clave in SQL, "la derivación del evento no está escrita en el fichero"


def test_T6_un_evento_gemelo_bajo_otro_id_ABORTA():
    """Dos filas para la misma ejecución serían dos historias del mismo hecho, y nada en el
    esquema diría cuál es la buena. §5 del mandato: fallar antes que crear dos historias."""
    gemelos = [b for b in BLOQUES_DO if "gemelos" in b]
    assert len(gemelos) >= 2, "la comprobación de gemelos tiene que ir ANTES y DESPUÉS"

    for bloque in gemelos:
        assert "e.channel       = 'sql_seed'" in bloque or "channel = 'sql_seed'" in bloque
        assert INSTANTE in bloque
        assert f"<> '{UUID_EVENTO}'::uuid" in bloque, \
            "la comprobación no excluye el id canónico, así que se detectaría a sí misma"
        assert "RAISE EXCEPTION" in bloque

    # §5: sin restricción UNIQUE nueva. La unicidad se defiende con la comprobación, no
    # añadiendo esquema en una migración que es de datos.
    assert "UNIQUE" not in EJECUTABLE.upper(), "031 no añade restricciones de esquema"


# ══ T7-T11 · LAS PROPIEDADES ═══════════════════════════════════════════════════════


def test_T7_todas_las_propiedades_heredadas_quedan_UNKNOWN():
    ups = [s for s in _sentencias_que_empiezan("UPDATE")
           if "activos_inmutables" in s and "inventory_class" in s]
    assert len(ups) == 1
    up = ups[0]
    assert "SET inventory_class = 'unknown'" in up
    assert "WHERE inventory_class IS NULL" in up
    assert not _lista_de_uuids(up), \
        "el relleno general no puede estar acotado a unos ids: es para TODAS"


def test_T8_exactamente_las_cinco_propiedades_del_seed_quedan_CONTAMINADAS():
    up = next(s for s in _sentencias_que_empiezan("UPDATE")
              if "evidence_exclusion_reason" in s)
    assert "SET evidence_exclusion_reason = 'demo_contaminated'" in up
    ids = _lista_de_uuids(up)
    assert len(ids) == 5 and len(set(ids)) == 5, f"se esperaban 5 ids, hay {len(ids)}"


def test_los_cinco_ids_son_LOS_DEL_SCRIPT_versionado():
    """La prueba no es que yo los escribiera bien: es que son los mismos que están en
    `seed_demo_fase1.sql`, que está en el repositorio y no lo edita esta unidad."""
    del_seed = set(re.findall(
        r"WHERE id = '([0-9a-f-]{36})'", SEED))
    assert len(del_seed) == 5, f"el seed no tiene 5 activos: {len(del_seed)}"

    up = next(s for s in _sentencias_que_empiezan("UPDATE")
              if "evidence_exclusion_reason" in s)
    assert set(_lista_de_uuids(up)) == del_seed, \
        "los ids marcados como contaminados no son los que el script toca"


def test_T9_T10_T11_las_propiedades_NO_reciben_origen():
    """El script hace UPDATE sobre activos que ya existían. Está probado que los tocó; no
    está probado que los creara. Apuntarles el evento habría convertido la procedencia en
    un registro de la última modificación."""
    for up in _sentencias_que_empiezan("UPDATE"):
        if "activos_inmutables" not in up:
            continue
        asignaciones = _asignaciones(up)
        for prohibida in ("source_id", "ingestion_event_id", "received_at"):
            assert prohibida not in asignaciones, \
                f"031 escribe {prohibida} en una propiedad: afirmaría un origen no probado"


# ══ T12-T16 · LOS ANUNCIOS ═════════════════════════════════════════════════════════


def test_T12_el_resto_de_anuncios_queda_UNKNOWN():
    ups = [s for s in _sentencias_que_empiezan("UPDATE")
           if "transacciones_temporales" in s and "'unknown'" in s]
    assert len(ups) == 1
    assert "WHERE inventory_class IS NULL" in ups[0]
    assert not _lista_de_uuids(ups[0])


def test_T13_T14_T15_los_cinco_anuncios_llevan_clase_fuente_y_evento():
    up = next(s for s in _sentencias_que_empiezan("UPDATE")
              if "transacciones_temporales" in s and "'demo'" in s)
    assert "inventory_class    = 'demo'" in up
    assert f"internal_name = '{NOMBRE_FUENTE}'" in up, \
        "la fuente se resuelve por nombre, para apuntar a la que exista"
    assert f"ingestion_event_id = '{UUID_EVENTO}'::uuid" in up

    ids = _lista_de_uuids(_condicion(up))
    assert len(set(ids)) == 5, f"se esperaban 5 anuncios, hay {len(set(ids))}"


def test_los_anuncios_se_apuntan_por_CLAVE_PRIMARIA_y_no_por_su_firma():
    """§8: nada de precio, operación o activo. El precio es estado mutable de un anuncio;
    una bajada de precio no convierte un anuncio demo en otro."""
    up = next(s for s in _sentencias_que_empiezan("UPDATE")
              if "transacciones_temporales" in s and "'demo'" in s)
    condicion = _condicion(up)
    assert condicion.strip().startswith("id = ANY"), \
        "la selección no empieza por la clave primaria"
    for prohibido in ("precio", "tipo_operacion", "activo_id", "fecha_publicacion",
                      "estado_anuncio"):
        assert prohibido not in condicion, f"la selección usa {prohibido}, que es mutable"


def test_T16_received_at_NO_SE_ESCRIBE_EN_NINGUN_SITIO():
    """§10. El instante del seed ya tiene su sitio —`inventory_ingestion_event.started_at`—
    y copiarlo aquí lo repetiría bajo un nombre que afirma otra cosa."""
    for up in _sentencias_que_empiezan("UPDATE"):
        assert "received_at" not in _asignaciones(up), \
            "031 escribe received_at, y no hay medición que lo respalde"
    for ins in _sentencias_que_empiezan("INSERT"):
        assert "received_at" not in ins


def test_la_lista_de_anuncios_es_LA_MISMA_en_todos_los_sitios():
    """Los cinco ids aparecen en cuatro sitios —precondición, emparejamiento, comprobación
    de conflicto y UPDATE—. Repetir un literal es una oportunidad de equivocarse; esto
    convierte la repetición en un invariante comprobado."""
    apariciones = re.findall(
        r"ARRAY\['0205111d[^\]]*\]::uuid\[\]", EJECUTABLE, re.S)
    assert len(apariciones) >= 3, f"se esperaban al menos 3 listas de anuncios, hay {len(apariciones)}"
    conjuntos = {frozenset(_lista_de_uuids(a)) for a in apariciones}
    assert len(conjuntos) == 1, "las listas de anuncios no coinciden entre sí"
    assert len(next(iter(conjuntos))) == 5

    propiedades = re.findall(r"ARRAY\['53160f0a[^\]]*\]::uuid\[\]", EJECUTABLE, re.S)
    assert len(propiedades) >= 2
    conj_p = {frozenset(_lista_de_uuids(p)) for p in propiedades}
    assert len(conj_p) == 1, "las listas de propiedades no coinciden entre sí"

    # Y anuncios y propiedades son conjuntos DISJUNTOS: son entidades distintas.
    assert not (next(iter(conjuntos)) & next(iter(conj_p)))


def test_TAMBIEN_las_comprobaciones_direccionan_por_CLAVE_PRIMARIA():
    """No basta con que el UPDATE apunte bien. Si una precondición contara por `activo_id`,
    seguiría dando 5 en el caso feliz y estaría midiendo otra cosa: la comprobación pasaría
    por casualidad el día que dejara de ser cierta.

    Lo encontró el arnés de mutación: cambiar `id` por `activo_id` en el bloque de
    precondición no ponía rojo ningún test.
    """
    for bloque in BLOQUES_DO:
        if "FROM transacciones_temporales" not in bloque:
            continue
        for linea in bloque.splitlines():
            if "ANY (ARRAY[" in linea:
                assert re.search(r"WHERE id = ANY \(ARRAY\[", linea), \
                    f"una comprobación direcciona anuncios por otra columna: {linea.strip()[:70]}"

    for bloque in BLOQUES_DO:
        if "FROM activos_inmutables" not in bloque:
            continue
        for linea in bloque.splitlines():
            if "ANY (ARRAY[" in linea:
                assert re.search(r"WHERE id = ANY \(ARRAY\[", linea), \
                    f"una comprobación direcciona propiedades por otra columna: {linea.strip()[:70]}"


def test_el_emparejamiento_anuncio_activo_cubre_los_cinco():
    """§9: la relación anuncio→activo ES la prueba. Sin ella, cinco claves primarias son
    cinco números."""
    bloque = next(b for b in BLOQUES_DO if "par(anuncio, activo)" in b)
    pares = re.findall(r"\('([0-9a-f-]{36})'::uuid, '([0-9a-f-]{36})'::uuid\)", bloque)
    assert len(pares) == 5, f"se esperaban 5 pares, hay {len(pares)}"

    anuncios = {a for a, _ in pares}
    activos = {p for _, p in pares}
    assert len(anuncios) == 5 and len(activos) == 5
    assert activos == set(re.findall(r"WHERE id = '([0-9a-f-]{36})'", SEED)), \
        "los activos del emparejamiento no son los del script versionado"
    assert "emparejamiento" in bloque and "RAISE EXCEPTION" in bloque


# ══ T17-T18 · LO QUE NO PUEDE TOCAR ════════════════════════════════════════════════


def test_T17_031_NO_toca_un_solo_valor_de_producto():
    """Metadatos ALREDEDOR del inventario, nunca dentro. `acepta_mascotas` sigue donde
    estaba, en las mismas filas y con el mismo valor."""
    for campo in ("acepta_mascotas", "caracteristicas", "imagen_url", "tipo_activo",
                  "direccion_estandarizada", "walk_score", "precio", "estado_anuncio"):
        for up in _sentencias_que_empiezan("UPDATE"):
            asignaciones = _asignaciones(up)
            assert campo not in asignaciones, f"031 modifica {campo}"


def test_T18_la_exclusion_NO_alcanza_a_ninguna_otra_fila():
    escrituras = [s for s in _sentencias_que_empiezan("UPDATE")
                  if "evidence_exclusion_reason" in _asignaciones(s)]
    assert len(escrituras) == 1, "hay más de una escritura de exclusión"

    condicion = _condicion(escrituras[0])
    assert condicion.strip().startswith("id = ANY"), \
        "la exclusión no está acotada por clave primaria"
    assert "evidence_exclusion_reason IS NULL" in condicion

    # `transacciones_temporales` no tiene esa columna, y 031 no la inventa. Sólo se miran
    # las ESCRITURAS: la verificación final es un SELECT que nombra las dos tablas a la vez
    # para imprimir sus conteos, y no escribe nada.
    for s in _sentencias_que_empiezan("UPDATE") + _sentencias_que_empiezan("INSERT"):
        if "transacciones_temporales" in s:
            assert "evidence_exclusion_reason" not in s


# ══ T19-T20 · IDEMPOTENCIA Y NO-DEGRADACIÓN ════════════════════════════════════════


def test_T19_ninguna_escritura_queda_sin_guardia():
    """Repetir 031 tiene que dejar el estado idéntico. Cada escritura lo consigue por su
    cuenta: no se confía en que «total, se aplica una vez»."""
    for ins in _sentencias_que_empiezan("INSERT"):
        assert "ON CONFLICT" in ins, f"inserción sin guardia: {ins[:60]}"

    for up in _sentencias_que_empiezan("UPDATE"):
        assert "WHERE" in up, f"UPDATE sin WHERE: {up[:60]}"
        condicion = _condicion(up)
        assert "IS NULL" in condicion, \
            f"UPDATE sin condición de hueco, así que una segunda pasada reescribe: {up[:60]}"


def test_T20_el_relleno_general_NO_degrada_una_clasificacion_posterior():
    """`WHERE inventory_class IS NULL` no es una optimización: es lo que impide que una
    segunda pasada rebaje a `unknown` una fila que alguien ya clasificó con evidencia."""
    for up in _sentencias_que_empiezan("UPDATE"):
        if "'unknown'" not in up:
            continue
        assert _condicion(up).strip().startswith("inventory_class IS NULL"), \
            "el relleno a unknown no está limitado a filas sin clase"

    # Y los cinco anuncios sólo se escriben si están vacíos o ya son 'demo'.
    up = next(s for s in _sentencias_que_empiezan("UPDATE") if "'demo'" in s)
    assert "(inventory_class IS NULL OR inventory_class = 'demo')" in up

    bloque = next(b for b in BLOQUES_DO if "conflicto" in b)
    assert "inventory_class    <> 'demo'" in bloque or "inventory_class <> 'demo'" in bloque
    assert "No se pisa una clasificación posterior" in bloque


# ══ T21-T22 · FAIL-CLOSED ══════════════════════════════════════════════════════════


@pytest.mark.parametrize("tabla,mensaje", [
    ("activos_inmutables", "5 propiedades"),
    ("transacciones_temporales", "5 anuncios"),
])
def test_T21_T22_si_falta_una_fila_objetivo_la_migracion_ABORTA(tabla, mensaje):
    """§7 y §9: no se amplía la coincidencia ni se sustituye por evidencia difusa. Si el
    mundo cambió, se para y se vuelve a mirar."""
    bloque = next(b for b in BLOQUES_DO if mensaje in b)
    assert f"FROM {tabla}" in bloque
    assert "n <> 5" in bloque
    assert "RAISE EXCEPTION" in bloque


def test_todas_las_precondiciones_usan_RAISE_y_ninguna_avisa_y_sigue():
    """Un `RAISE NOTICE` habría dejado la migración continuar, y con ella una procedencia a
    medias. En un backfill eso es peor que no haberlo corrido."""
    for nivel in ("RAISE NOTICE", "RAISE WARNING", "RAISE INFO", "RAISE LOG"):
        assert nivel not in EJECUTABLE, f"hay un {nivel}: avisa y sigue"
    assert EJECUTABLE.count("RAISE EXCEPTION") >= 8, \
        "faltan guardas: se esperaban al menos ocho abortos distintos"


def test_los_guards_de_este_fichero_NO_son_inertes():
    """LA MITAD NEGATIVA. Sin esto, los tests de arriba podrían estar comprobando patrones
    que nunca aparecerían de todos modos."""
    falso = _sin_comentarios(
        "UPDATE activos_inmutables SET received_at = now(), inventory_class = 'live';\n")
    sentencias = [s.strip() for s in falso.split(";") if s.strip()]
    assert sentencias and sentencias[0].upper().startswith("UPDATE")
    asignaciones = sentencias[0].split("SET", 1)[1]
    assert "received_at" in asignaciones, "el detector de received_at no ve una escritura real"
    assert "WHERE" not in sentencias[0], "el detector de UPDATE sin WHERE no distingue"

    # Y el troceo por `;` no se traga las sentencias de verdad.
    assert len(SENTENCIAS) == 7, (
        f"se esperaban 2 INSERT + 4 UPDATE + 1 SELECT, hay {len(SENTENCIAS)}")
    assert len(_sentencias_que_empiezan("UPDATE")) == 4
    assert len(_sentencias_que_empiezan("INSERT")) == 2
    assert len(BLOQUES_DO) == 6, f"se esperaban 6 bloques de comprobación, hay {len(BLOQUES_DO)}"


# ══ T23 · CERO CONSUMIDORES ════════════════════════════════════════════════════════


_HUELLAS_DE_031 = (NOMBRE_FUENTE, UUID_FUENTE, UUID_EVENTO, "demo_contaminated",
                   "inventory_ingestion_event", "inventory_source")


def _modulos_de_app():
    exento = RAIZ / "app" / "contracts" / "property_v0.py"
    return [p for p in sorted((RAIZ / "app").rglob("*.py"))
            if "__pycache__" not in str(p) and p != exento]


def test_T23_ningun_modulo_de_la_aplicacion_conoce_lo_que_031_escribe():
    """La propiedad central: 031 deja el producto EXACTAMENTE igual. Búsqueda, tarjetas,
    ranking, Mapa Vivo, ficha y el carril del comprador no saben que esto existe."""
    culpables = []
    for py in _modulos_de_app():
        texto = py.read_text(encoding="utf-8", errors="ignore")
        for huella in _HUELLAS_DE_031:
            if huella in texto:
                culpables.append(f"{py.relative_to(RAIZ).as_posix()} → {huella}")
    assert not culpables, f"alguien ya consume lo que escribe 031: {culpables}"


def test_las_consultas_del_producto_no_filtran_por_clase_de_inventario():
    """Por AST sobre las cadenas SQL. §15: que después de 031 haya cero propiedades
    defendibles como mercado es una CONCLUSIÓN de evidencia, no una regla de elegibilidad.
    En cuanto una consulta filtrara por `inventory_class`, dejaría de serlo."""
    for rel in ("app/agent/tools.py", "app/decision/assembler.py", "app/rutas.py",
                "app/routers/assets.py", "app/routers/chat.py"):
        arbol = ast.parse((RAIZ / rel).read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
                for huella in ("inventory_class", "evidence_exclusion_reason",
                               "ingestion_event_id"):
                    assert huella not in nodo.value, f"{rel} filtra por {huella}"


def test_el_detector_de_consumidores_NO_es_inerte():
    arbol = ast.parse('q = "SELECT * FROM a WHERE inventory_class = \'live\'"\n')
    literales = [n.value for n in ast.walk(arbol)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert any("inventory_class" in c for c in literales)
    assert any(h in f"... {NOMBRE_FUENTE} ..." for h in _HUELLAS_DE_031)


# ══ T24-T25 · SEGURIDAD Y DATOS PERSONALES ═════════════════════════════════════════


def test_T24_031_no_toca_permisos_ni_RLS_ni_roles():
    """La 030 es la dueña de la seguridad del esquema; la vista de evidencia, futura, será
    la dueña de la exposición a auditoría. 031 no es dueña de nada de eso."""
    for prohibido in ("GRANT", "REVOKE", "CREATE POLICY", "DROP POLICY", "ALTER POLICY",
                      "ROW LEVEL SECURITY", "ALTER ROLE", "CREATE ROLE", "ALTER DEFAULT",
                      "SECURITY DEFINER", "CREATE VIEW", "SET ROLE"):
        assert prohibido not in EJECUTABLE.upper(), f"031 toca seguridad: {prohibido}"


def test_T25_no_entra_ni_una_columna_personal():
    """§6 del gate de evidencia, que sigue vigente: nada de usuarios, contactos,
    propietarios ni conversación."""
    for personal in ("user_id", "owner_user_id", "email", "telefono", "password",
                     "contacto", "propietario", "buyer_context", "chat_sessions",
                     "checkpoints", "jwt", "auth."):
        assert personal not in EJECUTABLE.lower(), f"031 menciona {personal}"

    # Las únicas tablas que toca son las cuatro esperadas.
    tocadas = set(re.findall(
        r"(?:INSERT INTO|UPDATE)\s+([a-z_]+)", EJECUTABLE))
    assert tocadas == {"inventory_source", "inventory_ingestion_event",
                       "activos_inmutables", "transacciones_temporales"}, \
        f"031 escribe en tablas inesperadas: {sorted(tocadas)}"


def test_no_hay_borrados():
    """Un backfill añade procedencia. Si además borrara, revertirlo dejaría de ser posible."""
    for destructivo in ("DELETE FROM", "TRUNCATE", "DROP "):
        assert destructivo not in EJECUTABLE.upper(), f"031 destruye: {destructivo}"


# ══ ROLLBACK ═══════════════════════════════════════════════════════════════════════


def test_hay_bloque_de_ROLLBACK_y_deshace_las_cuatro_escrituras():
    for objeto in ("transacciones_temporales", "activos_inmutables",
                   "inventory_ingestion_event", "inventory_source",
                   "inventory_class", "evidence_exclusion_reason", UUID_EVENTO):
        assert objeto in ROLLBACK, f"el rollback no deshace {objeto}"


def test_el_rollback_advierte_que_la_evidencia_es_PERECEDERA():
    """Revertir la 030 no perdía nada. Revertir la 031 sí: el instante del seed se lee hoy
    de `fecha_publicacion` porque ninguna otra fila lo comparte, y eso deja de ser cierto en
    cuanto otra ejecución escriba en esa tabla."""
    assert "perecedera" in ROLLBACK.lower()
    assert "fecha_publicacion" in ROLLBACK
