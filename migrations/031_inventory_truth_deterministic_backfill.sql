-- ============================================================
-- Migration 031: la procedencia que SÍ se puede probar (Inventory Truth · fase B)
--
--   QUÉ ESCRIBE: una fuente, una ejecución de ingesta histórica, y la clasificación de las
--   80 filas heredadas. NADA MÁS. Ni productores, ni consumidores, ni una sola lectura
--   desde la aplicación. Después de aplicarla, búsqueda, tarjetas, ranking, Mapa Vivo,
--   ficha y el carril del comprador se comportan exactamente igual que antes.
--
--   LA REGLA QUE ORDENA EL FICHERO ENTERO: cada valor escrito afirma un hecho, y cada
--   hecho tiene que apoyarse en evidencia que alguien pueda volver a comprobar desde el
--   repositorio. Donde no hay esa evidencia se escribe NULL. No hay procedencia «al mejor
--   esfuerzo»: un valor plausible pero no probado es peor que la ausencia, porque la
--   ausencia se nota y el valor plausible no.
--
--   POR QUÉ 'unknown' EN LAS 80 FILAS Y NO 'live'. Hoy ninguna fila del inventario tiene
--   productor que acredite su origen. `unknown` no es un relleno: es la afirmación —cierta,
--   y medible— de que no sabemos de dónde vino. Marcarlas `live` habría convertido nuestro
--   propio inventario de pruebas en evidencia de mercado sin que nadie lo decidiera.
--
--   LO QUE SÍ ESTÁ PROBADO, y es lo único: `seed_demo_fase1.sql` corrió contra esta base.
--   Lo acreditan tres cosas independientes, todas re-comprobables:
--
--     1. sus cinco ids literales existen, y los cinco llevan la clave `notas` que el
--        script escribe; la nota completa de un activo coincide carácter a carácter
--     2. las cinco triples (activo, operación, precio) del script resuelven 1:1 contra la
--        tabla de anuncios: cero duplicados, cero activos con más de un anuncio
--     3. los cinco anuncios comparten `fecha_publicacion` al microsegundo — que es lo que
--        hace `NOW()` dentro de una transacción— y ese instante no lo comparte ninguna
--        otra fila de la tabla
--
--   POR QUÉ LOS CINCO ANUNCIOS LLEVAN ORIGEN Y LAS CINCO PROPIEDADES NO. Es la misma
--   distinción que motivó columnas separadas en la 030, y aquí se cobra: el script hace
--   `INSERT` de los anuncios y `UPDATE` de los activos. Creó los primeros; los segundos ya
--   existían y sólo fueron MODIFICADOS. Por eso:
--
--     anuncio      inventory_class='demo' + fuente + evento     origen probado
--     propiedad    inventory_class='unknown' + exclusión         contaminación probada,
--                                                                 origen NO
--
--   Apuntar el evento del seed en `activos_inmutables.ingestion_event_id` habría instalado
--   una semántica de «último evento que tocó la fila»: la procedencia se habría convertido
--   en un registro de la última modificación, que es justo lo contrario de lo que es.
--
--   POR QUÉ `received_at` SE QUEDA VACÍO EN LAS 80 FILAS. El instante del seed es cuándo
--   EMPEZÓ ESA EJECUCIÓN, y ya tiene su sitio: `inventory_ingestion_event.started_at`.
--   Copiarlo a `received_at` lo repetiría bajo un nombre que afirma otra cosa —cuándo
--   recibimos el dato— y para las propiedades sería directamente falso, porque ese instante
--   es el de una modificación posterior. La columna la poblarán los productores, hacia
--   adelante y sobre filas nuevas.
--
--   IDEMPOTENTE Y FAIL-CLOSED. Se puede correr dos veces y el estado es idéntico. Y si
--   alguna de las precondiciones no se cumple, ABORTA ENTERA en vez de escribir una
--   procedencia a medias: las dos cosas que no queremos son una historia duplicada y una
--   fila con fuente pero sin evento.
--
--   REQUIERE LA 030 APLICADA. No la recrea; comprueba que está y se planta si no.
--
--   SOBRE RLS: la 030 dejó las dos tablas nuevas con RLS activada y CERO políticas, así que
--   sólo el DUEÑO puede escribir en ellas. Esta migración inserta ahí. Si la aplicara un rol
--   distinto del que creó las tablas, el INSERT fallaría en voz alta —«new row violates
--   row-level security policy»— y no en silencio. 031 no crea políticas ni toca permisos.
-- ============================================================


-- ── 1 · LA 030 TIENE QUE ESTAR ──────────────────────────────────────────────────────
--
-- Sin esto, el fallo sería «relation inventory_source does not exist» a mitad del script:
-- correcto pero mudo sobre la causa. Esto dice qué falta y qué hay que aplicar antes.
DO $$
DECLARE faltan TEXT;
BEGIN
    IF to_regclass('public.inventory_source') IS NULL
       OR to_regclass('public.inventory_ingestion_event') IS NULL THEN
        RAISE EXCEPTION '031 requiere la 030: faltan las tablas de procedencia (aplica migrations/030_inventory_truth_schema.sql primero)';
    END IF;

    SELECT string_agg(e.tabla || '.' || e.columna, ', ' ORDER BY e.tabla, e.columna)
      INTO faltan
      FROM (VALUES
              ('activos_inmutables',       'source_id'),
              ('activos_inmutables',       'ingestion_event_id'),
              ('activos_inmutables',       'inventory_class'),
              ('activos_inmutables',       'received_at'),
              ('activos_inmutables',       'evidence_exclusion_reason'),
              ('transacciones_temporales', 'source_id'),
              ('transacciones_temporales', 'ingestion_event_id'),
              ('transacciones_temporales', 'inventory_class'),
              ('transacciones_temporales', 'received_at')
           ) AS e(tabla, columna)
     WHERE NOT EXISTS (SELECT 1 FROM information_schema.columns c
                        WHERE c.table_schema = 'public'
                          AND c.table_name   = e.tabla
                          AND c.column_name  = e.columna);

    IF faltan IS NOT NULL THEN
        RAISE EXCEPTION '031 requiere la 030: faltan columnas: %', faltan;
    END IF;
END $$;


-- ── 2 · LAS FILAS QUE VAMOS A MARCAR TIENEN QUE SEGUIR AHÍ ──────────────────────────
--
-- Los cinco anuncios se identifican por CLAVE PRIMARIA, no por su firma (activo, operación,
-- precio). La firma sirvió para encontrarlos una vez —resolvió 1:1 contra producción el
-- 2026-09-14— pero el precio es estado mutable de un anuncio, no su identidad: una bajada
-- de precio no convierte un anuncio demo en otro.
--
-- Por eso tampoco se exige que el precio siga siendo el mismo. Lo que sí se exige es el
-- EMPAREJAMIENTO anuncio→activo, porque es la relación de la que salió la prueba.
DO $$
DECLARE n INT;
BEGIN
    SELECT count(*) INTO n FROM activos_inmutables
     WHERE id = ANY (ARRAY['53160f0a-95f8-4a3d-a735-c2f82608d1cf',
                           '6c057dd0-8447-4a3b-94be-c38459845e3b',
                           '449acb53-3d7b-4ad6-9a14-3bcb0b645edb',
                           '1ac8d773-29db-496f-b7c5-9b7c3dfd8304',
                           '9e989f59-3da0-462e-a4fe-c34782bb799b']::uuid[]);
    IF n <> 5 THEN
        RAISE EXCEPTION '031: se esperaban las 5 propiedades tocadas por el seed y hay %. No se amplía la coincidencia ni se sustituye por evidencia difusa', n;
    END IF;

    SELECT count(*) INTO n FROM transacciones_temporales
     WHERE id = ANY (ARRAY['0205111d-e81e-4487-97c6-e7dff84467db',
                           'a5f4c87e-393f-43cd-b930-8c51dda52a11',
                           'e73ad64f-78e7-4907-96e4-a2dbdc843a9f',
                           '09e1de1c-1507-43a0-b54a-0638902a16c1',
                           'f7f127c8-7dd7-4d18-b4b8-fbc9848227b3']::uuid[]);
    IF n <> 5 THEN
        RAISE EXCEPTION '031: se esperaban los 5 anuncios creados por el seed y hay %', n;
    END IF;

    SELECT count(*) INTO n
      FROM (VALUES
              ('0205111d-e81e-4487-97c6-e7dff84467db'::uuid, '53160f0a-95f8-4a3d-a735-c2f82608d1cf'::uuid),
              ('a5f4c87e-393f-43cd-b930-8c51dda52a11'::uuid, '6c057dd0-8447-4a3b-94be-c38459845e3b'::uuid),
              ('e73ad64f-78e7-4907-96e4-a2dbdc843a9f'::uuid, '449acb53-3d7b-4ad6-9a14-3bcb0b645edb'::uuid),
              ('09e1de1c-1507-43a0-b54a-0638902a16c1'::uuid, '1ac8d773-29db-496f-b7c5-9b7c3dfd8304'::uuid),
              ('f7f127c8-7dd7-4d18-b4b8-fbc9848227b3'::uuid, '9e989f59-3da0-462e-a4fe-c34782bb799b'::uuid)
           ) AS par(anuncio, activo)
      JOIN transacciones_temporales t ON t.id = par.anuncio AND t.activo_id = par.activo;
    IF n <> 5 THEN
        RAISE EXCEPTION '031: sólo % de los 5 anuncios siguen colgando de su activo esperado. El emparejamiento ES la prueba; sin él no se marca nada', n;
    END IF;
END $$;


-- ── 3 · LA FUENTE: NUESTRA PROPIA AUTORIDAD ─────────────────────────────────────────
--
-- Una sola fila, y representa QUIÉN AFIRMA los datos demo: nosotros. No representa el
-- script (eso es un cliente), ni el canal (eso es `sql_seed`, y vive en el evento), ni una
-- ejecución concreta (eso es el evento).
--
-- El UUID es fijo y DERIVADO, no inventado: uuid5 sobre NAMESPACE_URL de la cadena
--   'contexto:inventory_source:contexto_datos_demo_internos'
-- Cualquiera puede recomputarlo y comprobar que es éste. Un UUID al azar en un fichero
-- versionado se ve igual pero no se puede verificar.
--
-- `usage_permission_status='internal_demo'` y no 'authorized': no nos concedimos un permiso,
-- es que la pregunta del permiso no aplica a nuestros propios datos sintéticos. Fechas de
-- vigencia NULL por lo mismo — un permiso que no existe no caduca.
INSERT INTO inventory_source (id, source_type, internal_name, provider_identifier,
                              usage_permission_status,
                              permission_effective_at, permission_expires_at)
VALUES ('0c934173-cc6c-54cd-8b98-a3d189809bde'::uuid,
        'internal_demo', 'contexto_datos_demo_internos', NULL,
        'internal_demo', NULL, NULL)
ON CONFLICT (internal_name) DO NOTHING;

-- `DO NOTHING` es idempotencia, no consentimiento. Si ya existe una fila con ese nombre
-- pero con otra semántica, no se pisa y no se sigue: sería adjudicar filas reales a una
-- autoridad que no es la que creemos.
DO $$
DECLARE fila inventory_source%ROWTYPE;
BEGIN
    SELECT * INTO fila FROM inventory_source
     WHERE internal_name = 'contexto_datos_demo_internos';

    IF NOT FOUND THEN
        RAISE EXCEPTION '031: la fuente demo interna no quedó creada';
    END IF;

    IF fila.source_type <> 'internal_demo'
       OR fila.usage_permission_status <> 'internal_demo' THEN
        RAISE EXCEPTION '031: ya existe una fuente llamada contexto_datos_demo_internos con otra semántica (source_type=%, permiso=%). No se sobrescribe', fila.source_type, fila.usage_permission_status;
    END IF;
END $$;


-- ── 4 · LA EJECUCIÓN HISTÓRICA ──────────────────────────────────────────────────────
--
-- `started_at` NO se estima: se lee. Los cinco anuncios del seed comparten
-- `fecha_publicacion` al microsegundo porque el script escribe `NOW()`, que en PostgreSQL
-- es el instante de INICIO DE LA TRANSACCIÓN — cinco INSERT en una ejecución dan el mismo
-- valor. Y ese instante no lo comparte ninguna otra fila de la tabla, así que identifica
-- esa ejecución y no otra.
--
-- LA ZONA, que es donde esto se podía torcer en silencio: `fecha_publicacion` es
-- `timestamp without time zone` y `started_at` es `timestamptz`. El valor guardado se
-- convirtió usando el `TimeZone` de la sesión que corrió el script. Comprobado el
-- 2026-09-14 contra la base: el servidor lo fija en UTC desde su fichero de configuración
-- (`reset_val=UTC`) y NINGUNA base ni rol lo sobrescribe en `pg_db_role_setting`; el script
-- versionado no hace `SET TimeZone`. De ahí el `+00` explícito: así el literal significa lo
-- mismo lo aplique quien lo aplique, en vez de depender de la sesión del aplicador.
--
-- `completed_at` SE QUEDA NULL. Que las filas estén ahí prueba que la ejecución terminó;
-- no dice cuándo. Un `completed_at = started_at` habría sido una duración inventada de cero.
--
-- UUID derivado igual que la fuente, de
--   'contexto:inventory_ingestion_event:sql_seed:seed_demo_fase1:2026-06-25T15:29:09.874138'

-- Antes de insertar: que no haya YA otro evento lógicamente idéntico bajo otro id. Dos
-- filas para la misma ejecución serían dos historias del mismo hecho, y nada en el esquema
-- diría cuál es la buena.
DO $$
DECLARE gemelos INT;
BEGIN
    SELECT count(*) INTO gemelos
      FROM inventory_ingestion_event e
      JOIN inventory_source s ON s.id = e.source_id
     WHERE s.internal_name = 'contexto_datos_demo_internos'
       AND e.channel       = 'sql_seed'
       AND e.started_at    = TIMESTAMPTZ '2026-06-25 15:29:09.874138+00'
       AND e.id           <> 'b4079b4f-48f5-5699-bc90-39fd2d4136f4'::uuid;
    IF gemelos > 0 THEN
        RAISE EXCEPTION '031: ya hay % evento(s) para la misma ejecución del seed bajo otro id. Antes que crear dos historias, se aborta', gemelos;
    END IF;
END $$;

INSERT INTO inventory_ingestion_event (id, source_id, channel, started_at, completed_at,
                                       external_batch_id, status)
SELECT 'b4079b4f-48f5-5699-bc90-39fd2d4136f4'::uuid,
       s.id,
       'sql_seed',
       TIMESTAMPTZ '2026-06-25 15:29:09.874138+00',
       NULL,
       NULL,
       'completed'
  FROM inventory_source s
 WHERE s.internal_name = 'contexto_datos_demo_internos'
ON CONFLICT (id) DO NOTHING;

-- Después de insertar: el evento canónico existe, cuelga de la fuente correcta y sigue
-- siendo el único para esa ejecución.
DO $$
DECLARE fila inventory_ingestion_event%ROWTYPE;
        fuente_demo UUID;
        gemelos INT;
BEGIN
    SELECT id INTO fuente_demo FROM inventory_source
     WHERE internal_name = 'contexto_datos_demo_internos';

    SELECT * INTO fila FROM inventory_ingestion_event
     WHERE id = 'b4079b4f-48f5-5699-bc90-39fd2d4136f4'::uuid;

    IF NOT FOUND THEN
        RAISE EXCEPTION '031: el evento histórico del seed no quedó creado';
    END IF;

    IF fila.source_id <> fuente_demo
       OR fila.channel <> 'sql_seed'
       OR fila.status  <> 'completed'
       OR fila.started_at <> TIMESTAMPTZ '2026-06-25 15:29:09.874138+00'
       OR fila.completed_at IS NOT NULL THEN
        RAISE EXCEPTION '031: el evento con el id canónico existe pero describe otra cosa (canal=%, estado=%, inicio=%)', fila.channel, fila.status, fila.started_at;
    END IF;

    SELECT count(*) INTO gemelos FROM inventory_ingestion_event
     WHERE source_id = fuente_demo AND channel = 'sql_seed'
       AND started_at = TIMESTAMPTZ '2026-06-25 15:29:09.874138+00'
       AND id <> 'b4079b4f-48f5-5699-bc90-39fd2d4136f4'::uuid;
    IF gemelos > 0 THEN
        RAISE EXCEPTION '031: quedaron % eventos duplicados para la ejecución del seed', gemelos;
    END IF;
END $$;


-- ── 5 · LOS CINCO ANUNCIOS NO PUEDEN TRAER YA OTRA PROCEDENCIA ──────────────────────
--
-- Si alguien los reclasificó con evidencia mejor, 031 no es quién para revertirlo — pero
-- tampoco puede escribir la mitad y dejar la clase de uno y la fuente de otro. Se aborta.
DO $$
DECLARE conflicto INT;
        fuente_demo UUID;
BEGIN
    SELECT id INTO fuente_demo FROM inventory_source
     WHERE internal_name = 'contexto_datos_demo_internos';

    SELECT count(*) INTO conflicto FROM transacciones_temporales
     WHERE id = ANY (ARRAY['0205111d-e81e-4487-97c6-e7dff84467db',
                           'a5f4c87e-393f-43cd-b930-8c51dda52a11',
                           'e73ad64f-78e7-4907-96e4-a2dbdc843a9f',
                           '09e1de1c-1507-43a0-b54a-0638902a16c1',
                           'f7f127c8-7dd7-4d18-b4b8-fbc9848227b3']::uuid[])
       AND (   (inventory_class    IS NOT NULL AND inventory_class    <> 'demo')
            OR (source_id          IS NOT NULL AND source_id          <> fuente_demo)
            OR (ingestion_event_id IS NOT NULL
                AND ingestion_event_id <> 'b4079b4f-48f5-5699-bc90-39fd2d4136f4'::uuid));
    IF conflicto > 0 THEN
        RAISE EXCEPTION '031: % de los 5 anuncios del seed ya llevan otra clase o procedencia. No se pisa una clasificación posterior', conflicto;
    END IF;
END $$;


-- ── 6 · PROCEDENCIA DE LOS CINCO ANUNCIOS ───────────────────────────────────────────
--
-- Va PRIMERO, antes del relleno general: así los cinco nunca llegan a escribirse como
-- `unknown` para corregirse acto seguido. Un estado intermedio que nadie ve sigue siendo
-- un estado que el WAL registra.
--
-- Por clave primaria. NO por precio, NO por operación, NO por activo: un activo podría
-- tener otro anuncio mañana y la actualización lo habría alcanzado.
--
-- `source_id` se resuelve por NOMBRE y no por el UUID literal: si la fuente ya existía con
-- otro id —caso que el paso 3 acepta mientras la semántica coincida— las filas tienen que
-- apuntar a la que hay, no a la que quisimos crear.
UPDATE transacciones_temporales
   SET inventory_class    = 'demo',
       source_id          = (SELECT id FROM inventory_source
                              WHERE internal_name = 'contexto_datos_demo_internos'),
       ingestion_event_id = 'b4079b4f-48f5-5699-bc90-39fd2d4136f4'::uuid
 WHERE id = ANY (ARRAY['0205111d-e81e-4487-97c6-e7dff84467db',
                       'a5f4c87e-393f-43cd-b930-8c51dda52a11',
                       'e73ad64f-78e7-4907-96e4-a2dbdc843a9f',
                       '09e1de1c-1507-43a0-b54a-0638902a16c1',
                       'f7f127c8-7dd7-4d18-b4b8-fbc9848227b3']::uuid[])
   AND (inventory_class IS NULL OR inventory_class = 'demo');


-- ── 7 · EL RESTO DEL INVENTARIO: NO SABEMOS ─────────────────────────────────────────
--
-- `WHERE inventory_class IS NULL` no es una optimización: es lo que impide que una segunda
-- pasada degrade a `unknown` una fila que alguien ya clasificó con evidencia. La migración
-- rellena huecos; no reescribe respuestas.
UPDATE transacciones_temporales
   SET inventory_class = 'unknown'
 WHERE inventory_class IS NULL;

UPDATE activos_inmutables
   SET inventory_class = 'unknown'
 WHERE inventory_class IS NULL;


-- ── 8 · LAS CINCO PROPIEDADES CONTAMINADAS ──────────────────────────────────────────
--
-- Siguen siendo `unknown` —el paso anterior ya las marcó— y además quedan excluidas de
-- cualquier medición de mercado. Son dos hechos distintos y por eso son dos columnas:
-- de dónde vinieron (no se sabe) y por qué no sirven para medir (las pisaron datos demo).
--
-- ESTO ES LO QUE EVITA EL FALLO SILENCIOSO. El día que llegue inventario con procedencia
-- real, `unknown` se vaciará; si estas cinco sólo fueran `unknown`, se irían vaciando con
-- el resto y acabarían promovidas a evidencia sin que nadie lo decidiera. La razón de
-- exclusión no se vacía sola.
--
-- Fuente, evento y `received_at` se quedan NULL A PROPÓSITO: el script hizo `UPDATE` sobre
-- activos que ya existían. Está probado que los tocó; no está probado que los creara.
UPDATE activos_inmutables
   SET evidence_exclusion_reason = 'demo_contaminated'
 WHERE id = ANY (ARRAY['53160f0a-95f8-4a3d-a735-c2f82608d1cf',
                       '6c057dd0-8447-4a3b-94be-c38459845e3b',
                       '449acb53-3d7b-4ad6-9a14-3bcb0b645edb',
                       '1ac8d773-29db-496f-b7c5-9b7c3dfd8304',
                       '9e989f59-3da0-462e-a4fe-c34782bb799b']::uuid[])
   AND evidence_exclusion_reason IS NULL;


-- ── 9 · LO QUE 031 DEJA EN PIE ──────────────────────────────────────────────────────
--
-- No se tocan `caracteristicas` ni ningún valor de producto: `acepta_mascotas` sigue donde
-- estaba, en las mismas filas y con el mismo valor. 031 añade metadatos de procedencia
-- ALREDEDOR del inventario, no dentro de él.
--
-- No se rellenan `last_verified_at` (no existe, y por buenas razones), identificadores de
-- proveedor, lotes externos, fechas de permiso ni procedencia por campo. Nada de eso tiene
-- hoy un hecho detrás.


-- Verificación (todas las cifras deben cuadrar con el estado esperado)
SELECT
    (SELECT count(*) FROM inventory_source
      WHERE internal_name = 'contexto_datos_demo_internos')            AS fuente_demo,
    (SELECT count(*) FROM inventory_ingestion_event
      WHERE id = 'b4079b4f-48f5-5699-bc90-39fd2d4136f4'::uuid)         AS evento_seed,
    (SELECT count(*) FROM activos_inmutables
      WHERE inventory_class IS NULL)                                   AS propiedades_sin_clase,
    (SELECT count(*) FROM activos_inmutables
      WHERE evidence_exclusion_reason = 'demo_contaminated')           AS propiedades_excluidas,
    (SELECT count(*) FROM activos_inmutables
      WHERE source_id IS NOT NULL OR ingestion_event_id IS NOT NULL
         OR received_at IS NOT NULL)                                   AS propiedades_con_origen,
    (SELECT count(*) FROM transacciones_temporales
      WHERE inventory_class = 'demo')                                  AS anuncios_demo,
    (SELECT count(*) FROM transacciones_temporales
      WHERE inventory_class IS NULL)                                   AS anuncios_sin_clase,
    (SELECT count(*) FROM transacciones_temporales
      WHERE received_at IS NOT NULL)                                   AS anuncios_con_recepcion;

-- ROLLBACK:
--   UPDATE transacciones_temporales
--      SET inventory_class = NULL, source_id = NULL, ingestion_event_id = NULL
--    WHERE ingestion_event_id = 'b4079b4f-48f5-5699-bc90-39fd2d4136f4'::uuid
--       OR inventory_class = 'unknown';
--   UPDATE activos_inmutables
--      SET inventory_class = NULL, evidence_exclusion_reason = NULL
--    WHERE inventory_class = 'unknown' OR evidence_exclusion_reason = 'demo_contaminated';
--   DELETE FROM inventory_ingestion_event
--    WHERE id = 'b4079b4f-48f5-5699-bc90-39fd2d4136f4'::uuid;
--   DELETE FROM inventory_source
--    WHERE internal_name = 'contexto_datos_demo_internos';
--
--   ADVERTENCIA, y es distinta de la de la 030. Revertir la 030 no perdía nada porque las
--   columnas nacían vacías. Revertir la 031 SÍ borra procedencia, y hay una parte que no se
--   puede volver a deducir: el instante del seed se lee hoy de `fecha_publicacion` porque
--   ninguna otra fila lo comparte, pero en cuanto otra ejecución escriba en esa tabla, ese
--   instante puede dejar de ser único. La evidencia que hace posible esta migración es
--   perecedera; el rollback la devuelve a un estado que quizá ya no se pueda reconstruir.
--
--   El rollback tampoco distingue un `unknown` escrito por 031 de uno escrito después por
--   otra vía: los borra los dos. Es aceptable mientras 031 sea lo único que escribe estas
--   columnas — que es exactamente el estado en el que se aplica.
