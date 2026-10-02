-- ============================================================
-- Migration 043: procedencia persistible de la capa de POIs (POI-SOURCE-PROVENANCE, R4)
--
--   QUÉ HACE — SOLO ESQUEMA, SOLO ADITIVO:
--     1. `public.poi_ingestion_run`: el MANIFIESTO de cada obtención de UNA fuente (Overture u
--        OSM) para UNA ciudad en UNA ejecución del refresco: release, esquema observado, lector,
--        endpoint, instantánea declarada por la fuente, código, instantes, contadores y estado
--        (también las corridas CAÍDAS y ROTAS). Nace CERRADA: RLS sin políticas + REVOKE ALL a
--        PUBLIC, anon, authenticated y service_role, sin depender de los privilegios por defecto.
--     2. Seis columnas NULLABLE y SIN DEFAULT en `public.pois_propios` (cambio de catálogo, sin
--        reescritura): la corrida que escribió la fila, la categoría TAL CUAL la da la fuente y el
--        campo del que salió, la versión del registro, el instante que DECLARA el registro fuente y
--        la lista `sources[]` original (con su licencia).
--     3. Las invariantes, en la base y no en la buena fe del escritor (CHECK + FK, sin triggers).
--
--   QUÉ NO HACE, y es la mitad importante:
--     · no escribe ni una fila: las 6 columnas nacen NULL en TODAS las filas existentes, que
--       significa «no se sabe». NO hay backfill (R-2), ni siquiera del release 2026-08-19.0, que
--       solo se reconstruyó COLECTIVAMENTE por huella (OVERTURE-SCHEMA-DRIFT AUDIT 0.1);
--     · no toca `pois_vivos` (las columnas nuevas NO llegan a ningún lector: la vista enumera las
--       suyas desde la 023), ni `categoria`, `categoria_overture`, `actualizado_en`, la 040, la 041,
--       la 042 ni `activos_inmutables`;
--     · no crea funciones, triggers, secuencias ni índices propios, no concede nada a nadie y no
--       toca privilegios por defecto. El escritor (`scripts/foso_pois_spike.py`) no cambia: sigue
--       escribiendo sin conocer las columnas nuevas. El que las llena es otra unidad, que NO se
--       fusiona antes de que esta esté aplicada en producción (R-5).
--
--   TRES AUTORIDADES, QUE NO SE MEZCLAN:
--     OBSERVACIÓN DE LA FUENTE   lo que el proveedor dice de su registro o de su publicación:
--                                fila → source_category, source_record_version, source_updated_at,
--                                source_lineage · corrida → source_release, source_snapshot_at
--     OBSERVACIÓN DE LA INGESTA  lo que Contexto VIO al leer: fila → source_category_namespace,
--                                ingestion_run_id · corrida → reader_contract,
--                                source_schema_fingerprint, source_endpoint, code_sha, instantes,
--                                contadores, estado, error
--     CLASIFICACIÓN DE CONTEXTO  `categoria` (sin cambios). Jamás se escribe en `source_*`.
--   Overture NO declara una versión semántica de su esquema dentro del dato (medido: el Parquet solo
--   trae `geo` 1.1.0 y `ARROW:schema`). Por eso aquí NO existe «places/v2» como dato del proveedor:
--   lo que se conserva es la huella del esquema OBSERVADO y el lector (con su versión) de Contexto.
--
--   LA REGLA CENTRAL — PLACE EVIDENCE v0 ESTÁ CONGELADO: v0 (`app/place/clasificacion.py`) lee
--   `categoria_overture` de una fila de Overture como `overture:categories.primary`, siempre. Una
--   fila escrita leyendo `taxonomy.primary` NO puede dejar ese valor en `categoria_overture`, o v0
--   lo publicaría con el espacio de nombres equivocado. `ck_pois_columna_legada_coherente` lo
--   impide en la base; solo se aplica a filas QUE DECLARAN su espacio (las históricas, sin
--   metadata, no se juzgan retrospectivamente).
--
--   IDEMPOTENCIA EXPLÍCITA (estándar 041/042): si la tabla, sus constraints, las 6 columnas y las
--   constraints de la capa ya existen EXACTAMENTE como las deja esta migración, no hace nada. Si
--   existe cualquier otra cosa —la tabla sin las columnas, una sola columna, otro tipo, un DEFAULT,
--   una constraint con estos nombres— ABORTA sin tocar nada. Nada se "arregla" en caliente.
--
--   BLOQUEOS: el `ALTER TABLE public.pois_propios` pide ACCESS EXCLUSIVE y lo sostiene hasta el
--   COMMIT: mientras dure, las lecturas de `pois_vivos` ESPERAN. Sin reescritura (columnas nullable
--   sin default) y con validaciones sobre columnas recién creadas y NULL. `lock_timeout` corto: si
--   un lector largo lo retiene, la migración FALLA en vez de ponerse en cola delante de todos.
--   Dispara `pgrst_ddl_watch` (recarga del caché de PostgREST, inocua). No aplicarla dentro de la
--   ventana del refresco semanal (lunes 21:30 → martes 02:00 UTC), cuyo DDL T0 también la bloquea.
--
--   QUIÉN LA APLICA: el dueño de `pois_propios` (en producción, `postgres`). NUNCA `supabase_admin`:
--   sus privilegios por defecto en `public` siguen abiertos.
--
--   Diseño, medición y ensayo: RESULTADO_POI_SOURCE_PROVENANCE_SCHEMA_CODE_PREFLIGHT_0.1.md (candidata
--   sha256 b5f8e6a5…). Cambios frente a la candidata, con su porqué y su prueba:
--   RESULTADO_POI_SOURCE_PROVENANCE_MIGRATION_043_CODE_CI_0.1.md §B.
-- ============================================================

BEGIN;

-- `CREATE TABLE`, `ADD COLUMN` sin default y `ADD CONSTRAINT` piden bloqueos breves.
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '60s';

DO $$
DECLARE
    capa        CONSTANT regclass := to_regclass('public.pois_propios');
    vista       CONSTANT regclass := to_regclass('public.pois_vivos');
    corrida              regclass := to_regclass('public.poi_ingestion_run');
    cols        CONSTANT text[] := ARRAY['ingestion_run_id', 'source_category', 'source_category_namespace',
                                         'source_record_version', 'source_updated_at', 'source_lineage'];
    -- nombre:tipo:not_null:con_default, en el orden en que quedan
    firma_cols  CONSTANT text := 'ingestion_run_id:uuid:f:f,source_category:text:f:f,'
                                 'source_category_namespace:text:f:f,source_record_version:text:f:f,'
                                 'source_updated_at:timestamp with time zone:f:f,source_lineage:jsonb:f:f';
    firma_run   CONSTANT text := 'id:uuid:t:t,source_provider:text:t:f,ciudad:text:t:f,status:text:t:f,'
                                 'reader_contract:text:t:f,source_release:text:f:f,'
                                 'source_schema_fingerprint:text:f:f,source_snapshot_at:timestamp with time zone:f:f,'
                                 'source_endpoint:text:f:f,code_sha:text:t:f,invocation_ref:text:f:f,'
                                 'started_at:timestamp with time zone:t:f,fetched_at:timestamp with time zone:f:f,'
                                 'completed_at:timestamp with time zone:t:f,rows_fetched:integer:f:f,'
                                 'rows_valid:integer:f:f,rows_written:integer:f:f,rows_closed:integer:f:f,'
                                 'error_class:text:f:f,error_phase:text:f:f';
    cks_capa    CONSTANT text[] := ARRAY['ck_pois_categoria_fuente_con_espacio', 'ck_pois_espacio_vocabulario',
                                         'ck_pois_espacio_de_su_fuente', 'ck_pois_columna_legada_coherente',
                                         'ck_pois_corrida_exige_espacio', 'ck_pois_procedencia_exige_corrida',
                                         'ck_pois_linaje_forma'];
    cks_run     CONSTANT text[] := ARRAY['ck_pir_proveedor', 'ck_pir_ciudad', 'ck_pir_estado', 'ck_pir_lector',
                                         'ck_pir_huella', 'ck_pir_sha', 'ck_pir_fetched', 'ck_pir_valid',
                                         'ck_pir_written', 'ck_pir_closed', 'ck_pir_tiempos', 'ck_pir_ok_completa',
                                         'ck_pir_fallo', 'ck_pir_fase', 'ck_pir_release'];
    fk          CONSTANT text := 'fk_pois_ingestion_run';
    roles_pub   CONSTANT text[] := ARRAY['public', 'anon', 'authenticated', 'service_role', 'contexto_audit_ro'];
    verbos               text[] := ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'];
    presentes   integer;
    nombres     integer;
    exacto      boolean;
    filas_antes bigint;
    filas_desp  bigint;
    nulas       bigint;
    acl_capa    text;
    acl_vista   text;
    def_vista   text;
    opc_vista   text;
    rol         text;
    verbo       text;
BEGIN
    -- MAINTAIN existe desde 17 (producción es 17.6; el CI es 15). `array_append` y no `||`: en
    -- PL/pgSQL de 17, `text[] || 'MAINTAIN'` se lee como un literal de array malformado.
    IF current_setting('server_version_num')::int >= 170000 THEN
        verbos := array_append(verbos, 'MAINTAIN');
    END IF;

    -- ── 0 · COMPUERTAS, FAIL-CLOSED ──────────────────────────────────────────────
    IF capa IS NULL OR vista IS NULL THEN
        RAISE EXCEPTION '043 ABORTA: no existe public.pois_propios o public.pois_vivos. ¿Base equivocada?';
    END IF;
    IF (SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = capa) <> current_user THEN
        RAISE EXCEPTION '043 ABORTA: el dueño de pois_propios no es quien aplica (%).', current_user;
    END IF;
    -- Las columnas que nombran las invariantes, con el tipo que se mide en producción.
    IF (SELECT count(*) FROM pg_attribute WHERE attrelid = capa AND NOT attisdropped
          AND ((attname IN ('fuente', 'ciudad') AND atttypid = 'text'::regtype AND attnotnull)
               OR (attname = 'categoria_overture' AND atttypid = 'text'::regtype AND NOT attnotnull))) <> 3 THEN
        RAISE EXCEPTION '043 ABORTA: pois_propios no tiene fuente/ciudad (text NOT NULL) y categoria_overture '
                        '(text nullable). ¿Es la tabla correcta?';
    END IF;
    -- El perímetro de la 040 tiene que estar en pie: si no, cerrar la tabla nueva sería en falso.
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = capa) THEN
        RAISE EXCEPTION '043 ABORTA: pois_propios sin RLS. El perímetro de la 040 no está como se midió.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_class WHERE oid = vista
                    AND 'security_invoker=true' = ANY (coalesce(reloptions, '{}'))) THEN
        RAISE EXCEPTION '043 ABORTA: pois_vivos sin security_invoker. El perímetro de la 040 no está como se midió.';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_class c, aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a
                WHERE c.oid IN (capa, vista) AND a.grantee <> c.relowner) THEN
        RAISE EXCEPTION '043 ABORTA: pois_propios o pois_vivos tienen destinatarios externos en su ACL (PUBLIC '
                        'incluido). El perímetro de la 040 no está como se midió.';
    END IF;

    -- ── IDEMPOTENCIA: exacto → no-op; cualquier otra cosa → aborta ──────────────────
    SELECT count(*) INTO presentes FROM pg_attribute WHERE attrelid = capa AND NOT attisdropped AND attname = ANY (cols);
    SELECT count(*) INTO nombres FROM pg_constraint WHERE conrelid = capa AND conname = ANY (array_append(cks_capa, fk));
    IF corrida IS NOT NULL OR presentes > 0 OR nombres > 0 THEN
        exacto := corrida IS NOT NULL AND presentes = 6
            AND (SELECT string_agg(attname || ':' || format_type(atttypid, atttypmod) || ':' ||
                                   CASE WHEN attnotnull THEN 't' ELSE 'f' END || ':' || CASE WHEN atthasdef THEN 't' ELSE 'f' END,
                                   ',' ORDER BY attnum)
                   FROM pg_attribute WHERE attrelid = capa AND NOT attisdropped AND attname = ANY (cols)) = firma_cols
            AND (SELECT string_agg(attname || ':' || format_type(atttypid, atttypmod) || ':' ||
                                   CASE WHEN attnotnull THEN 't' ELSE 'f' END || ':' || CASE WHEN atthasdef THEN 't' ELSE 'f' END,
                                   ',' ORDER BY attnum)
                   FROM pg_attribute WHERE attrelid = corrida AND attnum > 0 AND NOT attisdropped) = firma_run
            AND (SELECT count(*) FROM pg_constraint WHERE conrelid = capa AND contype = 'c' AND convalidated
                   AND conname = ANY (cks_capa)) = 7
            AND (SELECT count(*) FROM pg_constraint WHERE conrelid = corrida AND contype = 'c' AND convalidated
                   AND conname = ANY (cks_run)) = 15
            AND EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = capa AND conname = fk AND contype = 'f'
                          AND confrelid = corrida AND condeferrable AND condeferred AND confdeltype = 'r' AND convalidated)
            AND (SELECT relrowsecurity AND NOT relforcerowsecurity FROM pg_class WHERE oid = corrida)
            AND NOT EXISTS (SELECT 1 FROM pg_policy WHERE polrelid = corrida)
            AND NOT EXISTS (SELECT 1 FROM pg_class c, aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a
                             WHERE c.oid = corrida AND a.grantee <> c.relowner);
        IF exacto THEN
            RAISE NOTICE '043: ya aplicada (poi_ingestion_run cerrada y las 6 columnas de procedencia con sus '
                         'invariantes, exactas). Nada que hacer.';
            RETURN;
        END IF;
        RAISE EXCEPTION '043 ABORTA: estado intermedio o ajeno (tabla de corridas: %, % de 6 columnas, % '
                        'constraints con los nombres de la 043). No se arregla en caliente: caracterízalo antes.',
                        CASE WHEN corrida IS NULL THEN 'ausente' ELSE 'presente' END, presentes, nombres;
    END IF;

    -- Lo que la 043 NO debe mover, medido antes.
    SELECT count(*) INTO filas_antes FROM public.pois_propios;
    SELECT coalesce(relacl::text, '') INTO acl_capa FROM pg_class WHERE oid = capa;
    SELECT coalesce(relacl::text, ''), coalesce(reloptions::text, '') INTO acl_vista, opc_vista
      FROM pg_class WHERE oid = vista;
    def_vista := pg_get_viewdef(vista);

    -- ── 1 · EL MANIFIESTO DE CORRIDAS ────────────────────────────────────────────
    -- Una fila por (fuente × ciudad × ejecución). La inserta el escritor AL FINAL de la transacción
    -- de su fuente, con los contadores ya conocidos: la FK de `pois_propios` es DIFERIDA y se
    -- comprueba en el COMMIT. Una fuente CAÍDA o ROTA deja su fila sin filas de POIs enlazadas.
    -- `id` es uuid: sin secuencia (nada que cerrar aparte).
    CREATE TABLE public.poi_ingestion_run (
        id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        source_provider           text NOT NULL
            CONSTRAINT ck_pir_proveedor CHECK (source_provider IN ('overture', 'osm')),
        ciudad                    text NOT NULL
            CONSTRAINT ck_pir_ciudad CHECK (ciudad = lower(btrim(ciudad)) AND ciudad <> '' AND ciudad !~ '\s'),
        status                    text NOT NULL
            CONSTRAINT ck_pir_estado CHECK (status IN ('ok', 'caida', 'rota')),
        reader_contract           text NOT NULL
            CONSTRAINT ck_pir_lector CHECK (reader_contract ~ '^[a-z0-9_]+_v[0-9]+$'),
        source_release            text NULL,
        source_schema_fingerprint text NULL
            CONSTRAINT ck_pir_huella CHECK (source_schema_fingerprint ~ '^[0-9a-f]{64}$'),
        source_snapshot_at        timestamptz NULL,
        source_endpoint           text NULL,
        code_sha                  text NOT NULL
            CONSTRAINT ck_pir_sha CHECK (code_sha ~ '^[0-9a-f]{40}$'),
        invocation_ref            text NULL,
        started_at                timestamptz NOT NULL,
        fetched_at                timestamptz NULL,
        completed_at              timestamptz NOT NULL,
        rows_fetched              integer NULL CONSTRAINT ck_pir_fetched CHECK (rows_fetched >= 0),
        rows_valid                integer NULL CONSTRAINT ck_pir_valid CHECK (rows_valid >= 0),
        rows_written              integer NULL CONSTRAINT ck_pir_written CHECK (rows_written >= 0),
        rows_closed               integer NULL CONSTRAINT ck_pir_closed CHECK (rows_closed >= 0),
        error_class               text NULL,
        error_phase               text NULL,
        CONSTRAINT ck_pir_tiempos CHECK (
            completed_at >= started_at
            AND (fetched_at IS NULL OR (fetched_at >= started_at AND fetched_at <= completed_at))),
        -- OK = se obtuvo, se validó y se escribió: todo conocido, sin error.
        CONSTRAINT ck_pir_ok_completa CHECK (status <> 'ok' OR (
            fetched_at IS NOT NULL AND rows_fetched IS NOT NULL AND rows_valid IS NOT NULL
            AND rows_written IS NOT NULL AND rows_closed IS NOT NULL
            AND error_class IS NULL AND error_phase IS NULL)),
        -- CAÍDA/ROTA: con la CLASE del error y la FASE (nunca su texto: arrastra SQL, host o
        -- parámetros) y sin escritura confirmada.
        CONSTRAINT ck_pir_fallo CHECK (status = 'ok' OR (
            error_class IS NOT NULL AND error_phase IS NOT NULL AND rows_written IS NULL AND rows_closed IS NULL)),
        -- Las fases de `ResultadoFuente` (#189). Una fuente CAÍDA es la que no respondió: solo al obtener.
        CONSTRAINT ck_pir_fase CHECK (
            (error_phase IS NULL OR error_phase IN ('obtencion', 'validacion', 'escritura'))
            AND (status <> 'caida' OR error_phase = 'obtencion')),
        -- Overture se publica por releases; OSM no (Overpass es continuo y declara su instantánea).
        CONSTRAINT ck_pir_release CHECK (
            (source_provider = 'osm' AND source_release IS NULL AND source_schema_fingerprint IS NULL)
            OR (source_provider = 'overture' AND source_snapshot_at IS NULL
                AND (status <> 'ok' OR (source_release IS NOT NULL AND source_schema_fingerprint IS NOT NULL)))),
        -- Destino de la FK compuesta de `pois_propios`: una fila solo puede colgar de una corrida de
        -- SU fuente y SU ciudad.
        CONSTRAINT uq_pir_id_proveedor_ciudad UNIQUE (id, source_provider, ciudad)
    );

    COMMENT ON TABLE public.poi_ingestion_run IS
        '043 · Manifiesto de cada obtención de UNA fuente de POIs para UNA ciudad en UNA ejecución del refresco. '
        'Solo filas OBSERVADAS por el escritor en tiempo de ejecución: nunca reconstrucciones a posteriori.';
    COMMENT ON COLUMN public.poi_ingestion_run.source_release IS
        'FUENTE · Overture: nombre exacto del release leído (p. ej. 2026-09-23.1). OSM: NULL (no hay releases).';
    COMMENT ON COLUMN public.poi_ingestion_run.source_snapshot_at IS
        'FUENTE · OSM: osm3s.timestamp_osm_base que DECLARA Overpass en su respuesta. Overture: NULL.';
    COMMENT ON COLUMN public.poi_ingestion_run.source_schema_fingerprint IS
        'INGESTA · sha256 del esquema (columnas y tipos de primer nivel) que Contexto OBSERVÓ al leer el release. '
        'No es una versión declarada por Overture: el dato no la trae.';
    COMMENT ON COLUMN public.poi_ingestion_run.reader_contract IS
        'INGESTA · el lector de Contexto que interpretó la fuente, con su versión (p. ej. '
        'overture_places_categories_v1, osm_overpass_nwr_body_center_v1). Declaración de Contexto, no de la fuente.';
    COMMENT ON COLUMN public.poi_ingestion_run.fetched_at IS
        'INGESTA · cuándo Contexto terminó de recuperar la respuesta de la fuente: el «recuperado en» de cada fila enlazada.';
    COMMENT ON COLUMN public.poi_ingestion_run.error_class IS
        'INGESTA · solo la CLASE de la excepción (nunca su texto). NULL si status = ok.';

    ALTER TABLE public.poi_ingestion_run ENABLE ROW LEVEL SECURITY;
    REVOKE ALL PRIVILEGES ON TABLE public.poi_ingestion_run FROM PUBLIC;
    FOREACH rol IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol) THEN
            EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.poi_ingestion_run FROM %I', rol);
        END IF;
    END LOOP;

    -- ── 2 · LA PROCEDENCIA POR FILA ──────────────────────────────────────────────
    -- Nullable y sin DEFAULT: SOLO catálogo (sin reescritura). NULL = «no se sabe».
    ALTER TABLE public.pois_propios
        ADD COLUMN ingestion_run_id          uuid,
        ADD COLUMN source_category           text,
        ADD COLUMN source_category_namespace text,
        ADD COLUMN source_record_version     text,
        ADD COLUMN source_updated_at         timestamptz,
        ADD COLUMN source_lineage            jsonb,
        -- FK compuesta: la corrida existe, es de la MISMA fuente y de la MISMA ciudad. Diferida (el
        -- escritor inserta la corrida al final de su transacción) y RESTRICT (una corrida con filas
        -- no se borra). MATCH SIMPLE: una fila sin corrida (histórica) no se comprueba.
        ADD CONSTRAINT fk_pois_ingestion_run FOREIGN KEY (ingestion_run_id, fuente, ciudad)
            REFERENCES public.poi_ingestion_run (id, source_provider, ciudad)
            ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
        -- I1 · una categoría de la fuente SIN el campo del que salió no se guarda.
        ADD CONSTRAINT ck_pois_categoria_fuente_con_espacio
            CHECK (source_category IS NULL OR source_category_namespace IS NOT NULL),
        -- I2 · vocabulario CERRADO de campos de origen. Ampliarlo es una migración explícita.
        ADD CONSTRAINT ck_pois_espacio_vocabulario
            CHECK (source_category_namespace IS NULL OR source_category_namespace IN (
                'overture:categories.primary', 'overture:taxonomy.primary',
                'osm:amenity', 'osm:shop', 'osm:leisure', 'osm:railway', 'osm:highway',
                'osm:public_transport', 'osm:station')),
        -- I3 · el campo de origen es del MISMO dataset que la fila.
        ADD CONSTRAINT ck_pois_espacio_de_su_fuente
            CHECK (source_category_namespace IS NULL OR split_part(source_category_namespace, ':', 1) = fuente),
        -- I4 · LA REGLA CENTRAL (protege a v0): una fila de Overture que declara un campo distinto de
        --      `categories.primary` (p. ej. `taxonomy.primary`) deja `categoria_overture` en NULL, y una
        --      que declara `categories.primary` lleva EXACTAMENTE el mismo valor. Las filas sin campo
        --      declarado (históricas) no se juzgan.
        ADD CONSTRAINT ck_pois_columna_legada_coherente
            CHECK (fuente <> 'overture' OR source_category_namespace IS NULL
                   OR (source_category_namespace = 'overture:categories.primary'
                       AND categoria_overture IS NOT DISTINCT FROM source_category)
                   OR (source_category_namespace <> 'overture:categories.primary' AND categoria_overture IS NULL)),
        -- I5 · una fila enlazada a una corrida declara SIEMPRE de qué campo leyó su categoría.
        ADD CONSTRAINT ck_pois_corrida_exige_espacio
            CHECK (ingestion_run_id IS NULL OR source_category_namespace IS NOT NULL),
        -- I7 · ningún dato de procedencia sin la corrida que lo observó: ni procedencia parcial
        --      suelta ni relleno a mano. Lo histórico queda NULL entero.
        ADD CONSTRAINT ck_pois_procedencia_exige_corrida
            CHECK (ingestion_run_id IS NOT NULL
                   OR (source_category IS NULL AND source_category_namespace IS NULL
                       AND source_record_version IS NULL AND source_updated_at IS NULL AND source_lineage IS NULL)),
        -- I6 · el linaje es la lista `sources[]` de Overture, verbatim: una lista de objetos, y solo en
        --      filas de Overture (la consulta de OSM no recibe nada equivalente).
        ADD CONSTRAINT ck_pois_linaje_forma
            CHECK (source_lineage IS NULL OR (
                fuente = 'overture' AND jsonb_typeof(source_lineage) = 'array'
                AND NOT jsonb_path_exists(source_lineage, '$[*] ? (@.type() != "object")')));

    COMMENT ON COLUMN public.pois_propios.ingestion_run_id IS
        '043 · INGESTA · la corrida (poi_ingestion_run) cuyo upsert escribió por última vez los campos de origen de '
        'esta fila. El cierre (operativo=false) NO la cambia. NULL = desconocida (toda fila anterior a la 043).';
    COMMENT ON COLUMN public.pois_propios.source_category IS
        '043 · FUENTE · la categoría TAL CUAL la da la fuente en el campo que nombra source_category_namespace. '
        'Nunca la categoría de Contexto (esa es `categoria`).';
    COMMENT ON COLUMN public.pois_propios.source_category_namespace IS
        '043 · INGESTA · el campo de la fuente del que Contexto LEYÓ source_category (overture:categories.primary, '
        'overture:taxonomy.primary, osm:<clave de la etiqueta que casó>).';
    COMMENT ON COLUMN public.pois_propios.source_record_version IS
        '043 · FUENTE · la versión del registro que declara la fuente (Overture: `version` del GERS id). NULL si no la da.';
    COMMENT ON COLUMN public.pois_propios.source_updated_at IS
        '043 · FUENTE · el instante que DECLARA el registro fuente. NO es una observación del lugar ni la hora de '
        'ingesta. NULL si no se puede derivar de manera inequívoca (sin zona horaria, varias raíces…).';
    COMMENT ON COLUMN public.pois_propios.source_lineage IS
        '043 · FUENTE · Overture: la lista sources[] del registro, verbatim (contribuyente, licencia, record_id, '
        'update_time). Conserva la evidencia original aunque el escalar quede NULL. OSM: NULL.';

    -- ── 3 · VERIFICACIÓN FAIL-CLOSED (mide el efecto; no lo declara) ────────────────
    corrida := to_regclass('public.poi_ingestion_run');
    IF NOT (SELECT relrowsecurity AND NOT relforcerowsecurity FROM pg_class WHERE oid = corrida)
       OR EXISTS (SELECT 1 FROM pg_policy WHERE polrelid = corrida) THEN
        RAISE EXCEPTION '043 FALLA: poi_ingestion_run no quedó con RLS, sin FORCE y sin políticas';
    END IF;
    -- El ACL y el privilegio EFECTIVO, verbo a verbo: no basta con mirar el texto del ACL.
    IF EXISTS (SELECT 1 FROM pg_class c, aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a
                WHERE c.oid IN (corrida, capa, vista) AND a.grantee <> c.relowner) THEN
        RAISE EXCEPTION '043 FALLA: hay destinatarios externos (PUBLIC incluido) en la tabla nueva, la capa o la vista';
    END IF;
    FOREACH rol IN ARRAY roles_pub LOOP
        IF rol = 'public' OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol) THEN
            FOREACH verbo IN ARRAY verbos LOOP
                IF has_table_privilege(rol, corrida, verbo) THEN
                    RAISE EXCEPTION '043 FALLA: % conserva % sobre poi_ingestion_run', rol, verbo;
                END IF;
            END LOOP;
        END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid IN (corrida, capa) AND attacl IS NOT NULL) THEN
        RAISE EXCEPTION '043 FALLA: hay ACL de columna';
    END IF;
    IF (SELECT string_agg(attname || ':' || format_type(atttypid, atttypmod) || ':' ||
                          CASE WHEN attnotnull THEN 't' ELSE 'f' END || ':' || CASE WHEN atthasdef THEN 't' ELSE 'f' END,
                          ',' ORDER BY attnum)
          FROM pg_attribute WHERE attrelid = capa AND NOT attisdropped AND attname = ANY (cols)) IS DISTINCT FROM firma_cols
       OR (SELECT string_agg(attname || ':' || format_type(atttypid, atttypmod) || ':' ||
                             CASE WHEN attnotnull THEN 't' ELSE 'f' END || ':' || CASE WHEN atthasdef THEN 't' ELSE 'f' END,
                             ',' ORDER BY attnum)
             FROM pg_attribute WHERE attrelid = corrida AND attnum > 0 AND NOT attisdropped) IS DISTINCT FROM firma_run THEN
        RAISE EXCEPTION '043 FALLA: las columnas no quedaron con la forma declarada (nullable, sin default, tipos)';
    END IF;
    SELECT count(*), count(*) FILTER (WHERE ingestion_run_id IS NULL AND source_category IS NULL
                                        AND source_category_namespace IS NULL AND source_record_version IS NULL
                                        AND source_updated_at IS NULL AND source_lineage IS NULL)
      INTO filas_desp, nulas FROM public.pois_propios;
    IF filas_desp <> filas_antes OR nulas <> filas_desp THEN
        RAISE EXCEPTION '043 FALLA: % filas antes, % después, % con procedencia NULL (deben ser todas)',
                        filas_antes, filas_desp, nulas;
    END IF;
    IF coalesce((SELECT relacl::text FROM pg_class WHERE oid = capa), '') <> acl_capa
       OR coalesce((SELECT relacl::text FROM pg_class WHERE oid = vista), '') <> acl_vista
       OR coalesce((SELECT reloptions::text FROM pg_class WHERE oid = vista), '') <> opc_vista
       OR pg_get_viewdef(vista) <> def_vista THEN
        RAISE EXCEPTION '043 FALLA: cambió el ACL de la capa, o el ACL, las opciones o la definición de pois_vivos';
    END IF;

    RAISE NOTICE '043 OK: poi_ingestion_run cerrada (RLS sin políticas, 0 privilegios externos), 6 columnas de '
                 'procedencia NULL en % filas, 8 invariantes, pois_vivos intacta', filas_desp;
END $$;

-- Verificación legible.
SELECT a.attname AS columna, format_type(a.atttypid, a.atttypmod) AS tipo,
       NOT a.attnotnull AS nullable, a.atthasdef AS con_default
  FROM pg_attribute a
 WHERE a.attrelid = 'public.pois_propios'::regclass
   AND a.attname IN ('ingestion_run_id', 'source_category', 'source_category_namespace',
                     'source_record_version', 'source_updated_at', 'source_lineage')
 ORDER BY a.attnum;

COMMIT;

-- ── ROLLBACK ────────────────────────────────────────────────────────────────────────
--
-- Deshace exactamente lo de arriba. Sólo con autorización explícita y DESPUÉS de revertir el
-- escritor que exija la 043 (si ya se fusionó). Descarta la procedencia que se haya escrito; no
-- toca ningún otro dato. Exacto en lo LÓGICO, no en lo físico: DROP COLUMN deja 6 atributos
-- `attisdropped` hasta la próxima reescritura de la tabla.
--
--   BEGIN;
--   SET LOCAL lock_timeout = '3s';
--   ALTER TABLE public.pois_propios
--       DROP CONSTRAINT IF EXISTS ck_pois_linaje_forma,
--       DROP CONSTRAINT IF EXISTS ck_pois_procedencia_exige_corrida,
--       DROP CONSTRAINT IF EXISTS ck_pois_corrida_exige_espacio,
--       DROP CONSTRAINT IF EXISTS ck_pois_columna_legada_coherente,
--       DROP CONSTRAINT IF EXISTS ck_pois_espacio_de_su_fuente,
--       DROP CONSTRAINT IF EXISTS ck_pois_espacio_vocabulario,
--       DROP CONSTRAINT IF EXISTS ck_pois_categoria_fuente_con_espacio,
--       DROP CONSTRAINT IF EXISTS fk_pois_ingestion_run,
--       DROP COLUMN IF EXISTS source_lineage,
--       DROP COLUMN IF EXISTS source_updated_at,
--       DROP COLUMN IF EXISTS source_record_version,
--       DROP COLUMN IF EXISTS source_category_namespace,
--       DROP COLUMN IF EXISTS source_category,
--       DROP COLUMN IF EXISTS ingestion_run_id;
--   DROP TABLE IF EXISTS public.poi_ingestion_run;
--   COMMIT;
