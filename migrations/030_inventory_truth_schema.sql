-- ============================================================
-- Migration 030: el inventario puede decir de dónde vino (Inventory Truth · fase A)
--
--   QUÉ AÑADE: dos tablas de procedencia y nueve columnas nullable. NADA MÁS. Ni backfill,
--   ni filas de fuente, ni productores, ni consumidores. Después de aplicarla, los 40
--   activos y los 40 anuncios se comportan exactamente igual que antes: ninguna búsqueda,
--   ranking, tarjeta, mapa ni el Buyer Harness lee una sola de estas columnas.
--
--   POR QUÉ EXISTE. Hoy no se puede responder «¿de dónde salió este inmueble?». Las filas
--   actuales mezclan al menos tres linajes —seeds demo, piloto de corredor, ingesta por
--   visión— y `activos_inmutables` no guarda ninguna señal de origen. Sin eso, cualquier
--   medición de mercado mide también nuestros propios datos de prueba sin saberlo.
--
--   POR QUÉ FUENTE Y CANAL SON COSAS DISTINTAS, y es la decisión que ordena todo el fichero:
--
--     FUENTE   quién AFIRMA el hecho en el mundo real   (un corredor, nosotros mismos)
--     CANAL    por dónde entró el dato al sistema       (HTTP, CSV por ORM, un .sql)
--
--   Un script que llama a un endpoint no es una fuente: es un cliente sobre un canal.
--   Confundirlos habría llenado el registro de entradas que no representan a nadie.
--
--   POR QUÉ PROPIEDAD Y ANUNCIO LLEVAN PROCEDENCIA SEPARADA. No es previsión: ya pasa.
--   `seed_demo_fase1.sql` hace UPDATE de activos que ya existían e INSERT de sus anuncios,
--   así que hay filas cuyo inmueble vino de un sitio y cuyo anuncio vino de otro. Una sola
--   referencia representaría dos hechos distintos como si fueran uno.
--
--   TODO NULLABLE, Y SIN DEFAULT. Un `DEFAULT 'live'` habría clasificado 40 filas como
--   inventario real sin que nadie lo decidiera — exactamente el fallo que esto viene a
--   cerrar. Las columnas nacen vacías y se llenan con evidencia, en 030B.
--
--   Aditiva, idempotente y reversible.
-- ============================================================

-- ── FUENTES ─────────────────────────────────────────────────────────────────────────
--
-- Quién afirma. No guarda credenciales, ni contactos, ni nada que se parezca a un CRM:
-- es un registro de autoría y permiso, no una agenda de proveedores.
CREATE TABLE IF NOT EXISTS inventory_source (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Sólo FUENTES. `sql_seed`, `http_asset`, `http_ingest` y `direct_db` NO van aquí:
    -- son canales y viven en `inventory_ingestion_event.channel`.
    --
    -- Dos valores, y son los dos casos que existen hoy: los seeds que escribimos nosotros
    -- y el piloto con corredor. `partner` no está porque todavía no hay ninguno, y añadir
    -- un valor es una migración de una línea — más barato que arrastrar una categoría que
    -- nadie usa y que alguien acabaría rellenando por parecido.
    source_type TEXT NOT NULL
        CHECK (source_type IN ('internal_demo', 'broker')),

    -- Identidad operativa nuestra. Siempre existe, a diferencia del identificador del
    -- proveedor. Es mutable (renombrar no crea una fuente nueva: el UUID manda).
    internal_name TEXT NOT NULL UNIQUE,

    -- El id que usa el proveedor, si lo tiene. La mayoría no.
    provider_identifier TEXT NULL,

    -- AUTORIDAD, no caducidad. `expired` no es un estado: se deriva de
    -- `permission_expires_at`, y tenerlo como valor permitiría que la columna y la fecha
    -- se contradijeran. `revoked` SÍ es un estado: nos lo retiraron, y eso no lo dice
    -- ninguna fecha.
    usage_permission_status TEXT NOT NULL
        CHECK (usage_permission_status IN
               ('unknown', 'internal_demo', 'authorized', 'restricted', 'revoked')),

    permission_effective_at TIMESTAMPTZ NULL,
    permission_expires_at   TIMESTAMPTZ NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Un permiso que caduca antes de empezar no es un permiso.
    CONSTRAINT inventory_source_vigencia_coherente
        CHECK (permission_expires_at IS NULL
               OR permission_effective_at IS NULL
               OR permission_expires_at >= permission_effective_at)
);

-- Unicidad PARCIAL: dos fuentes del mismo tipo no pueden compartir identificador de
-- proveedor, pero muchas no tienen ninguno y `NULL` no colisiona consigo mismo.
CREATE UNIQUE INDEX IF NOT EXISTS ux_inventory_source_proveedor
    ON inventory_source (source_type, provider_identifier)
    WHERE provider_identifier IS NOT NULL;

-- ── EJECUCIONES DE INGESTA ──────────────────────────────────────────────────────────
--
-- Qué ejecución concreta trajo estas filas. Es lo que convierte «deshacer la carga del
-- martes» en una operación determinista en vez de un `WHERE created_at BETWEEN …`, que es
-- justo la heurística que no queremos usar para clasificar nada.
CREATE TABLE IF NOT EXISTS inventory_ingestion_event (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- RESTRICT y nunca SET NULL: borrar una fuente no puede dejar huérfana la procedencia
    -- de las filas que trajo. Si estorba borrar, es que la procedencia sigue viva.
    source_id UUID NOT NULL
        REFERENCES inventory_source(id) ON DELETE RESTRICT,

    -- Sólo CANALES. Los cuatro que existen hoy, medidos en el código:
    --   direct_db   import_assets.py escribe por ORM contra la base
    --   http_asset  POST /api/v1/assets/        (lo usa el piloto del corredor)
    --   http_ingest POST /api/v1/assets/ingest  (geocodificación + visión)
    --   sql_seed    ejecución de un .sql del repositorio
    channel TEXT NOT NULL
        CHECK (channel IN ('direct_db', 'http_asset', 'http_ingest', 'sql_seed')),

    started_at   TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NULL,

    -- El identificador del lote del proveedor, cuando lo dé. No es nuestro.
    external_batch_id TEXT NULL,

    status TEXT NOT NULL
        CHECK (status IN ('running', 'completed', 'failed')),

    CONSTRAINT inventory_ingestion_event_fin_coherente
        CHECK (completed_at IS NULL OR completed_at >= started_at)
);

-- ── PROCEDENCIA DE LA PROPIEDAD ─────────────────────────────────────────────────────
--
-- `source_id` NULL significa FUENTE DESCONOCIDA. No se crea una fila «fuente UNKNOWN»:
-- habría dos formas de decir lo mismo y alguien acabaría tratándolas distinto.
--
-- `inventory_class` es un eje INDEPENDIENTE de la fuente: se puede saber quién trajo una
-- fila y no saber para qué sirve, y al revés. Sus valores son los de `InventoryClass` del
-- contrato `PropertyContextV0`, sin inventar un segundo vocabulario equivalente.
ALTER TABLE activos_inmutables
    ADD COLUMN IF NOT EXISTS source_id UUID NULL
        REFERENCES inventory_source(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS ingestion_event_id UUID NULL
        REFERENCES inventory_ingestion_event(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS inventory_class TEXT NULL
        CHECK (inventory_class IN ('live', 'demo', 'test', 'unknown')),
    ADD COLUMN IF NOT EXISTS received_at TIMESTAMPTZ NULL,
    -- POR QUÉ ESTA COLUMNA EXISTE Y NO BASTA CON `inventory_class`. Son dos hechos
    -- distintos: de dónde vino la fila, y por qué no sirve para medir el mercado. Está
    -- probado que `seed_demo_fase1.sql` corrió —su nota literal está en la base— y eso
    -- acredita que cinco activos fueron MODIFICADOS por datos demo. No acredita que
    -- nacieran demo: el script hace UPDATE, no INSERT. Decir `inventory_class='demo'`
    -- afirmaría un origen que nadie ha probado.
    ADD COLUMN IF NOT EXISTS evidence_exclusion_reason TEXT NULL
        CHECK (evidence_exclusion_reason IN ('demo_contaminated'));

-- NO se añade `last_verified_at`. Nadie verifica hoy la disponibilidad de un anuncio —lo
-- único que se verifica en terreno es el ENTORNO, y se hereda entre inmuebles que comparten
-- un POI—. Un timestamp sin proceso que lo produzca acabaría relleno con `created_at`, que
-- es precisamente la mentira que `last_updated_at` del contrato documenta haber cerrado.

-- ── PROCEDENCIA DEL ANUNCIO ─────────────────────────────────────────────────────────
--
-- Columnas propias, no heredadas del inmueble. Ver la cabecera: ya existen filas donde el
-- inmueble y su anuncio vinieron de productores distintos.
--
-- Sin `evidence_exclusion_reason`: no hay ningún caso demostrado de un anuncio que haya que
-- excluir sin poder clasificarlo. Los cinco anuncios del seed SÍ nacieron demo, así que su
-- `inventory_class` lo dirá — que es una afirmación más fuerte y más simple.
ALTER TABLE transacciones_temporales
    ADD COLUMN IF NOT EXISTS source_id UUID NULL
        REFERENCES inventory_source(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS ingestion_event_id UUID NULL
        REFERENCES inventory_ingestion_event(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS inventory_class TEXT NULL
        CHECK (inventory_class IN ('live', 'demo', 'test', 'unknown')),
    ADD COLUMN IF NOT EXISTS received_at TIMESTAMPTZ NULL;

-- ── ÍNDICES ─────────────────────────────────────────────────────────────────────────
--
-- Las dos tablas tienen 40 filas y 96 kB de heap entre las dos (medido con el rol de
-- auditoría el 2026-09-14), así que crearlos dentro del migrador no bloquea nada: por eso
-- no hace falta `CONCURRENTLY`, que además no puede correr en la transacción del aplicador.
--
-- `inventory_ingestion_event.source_id` NO lleva índice todavía: no hay consulta que lo
-- recorra. Se añadirá cuando exista.
CREATE INDEX IF NOT EXISTS ix_activos_source           ON activos_inmutables (source_id);
CREATE INDEX IF NOT EXISTS ix_activos_ingestion_event  ON activos_inmutables (ingestion_event_id);
CREATE INDEX IF NOT EXISTS ix_activos_inventory_class  ON activos_inmutables (inventory_class);
CREATE INDEX IF NOT EXISTS ix_transacciones_source          ON transacciones_temporales (source_id);
CREATE INDEX IF NOT EXISTS ix_transacciones_ingestion_event ON transacciones_temporales (ingestion_event_id);
CREATE INDEX IF NOT EXISTS ix_transacciones_inventory_class ON transacciones_temporales (inventory_class);

-- ── EXPOSICIÓN ──────────────────────────────────────────────────────────────────────
--
-- Crear una tabla en `public` bajo Supabase puede exponerla por PostgREST si existen grants
-- por defecto. Estas dos no son una API nueva y no deben ser legibles por nadie todavía.
--
-- Se activa RLS SIN crear ninguna política. QUÉ SIGNIFICA ESO EXACTAMENTE, porque la
-- versión corta —«RLS sin políticas deniega a todo el mundo»— es falsa, y es justo la frase
-- sobre la que se apoyaría quien venga después:
--
--   roles SUJETOS a RLS    sin política no hay ninguna fila que puedan leer ni escribir.
--                          Acceso cero, tengan el GRANT que tengan
--   el DUEÑO de la tabla   NO queda sujeto: aquí se usa ENABLE y no FORCE ROW LEVEL
--                          SECURITY. Es deliberado — la 031 escribe estas dos tablas, y lo
--                          hace como dueño
--   roles con BYPASSRLS    RLS no les aplica en absoluto. Para ellos manda el GRANT y nada
--                          más
--
-- Y ESTA MIGRACIÓN NO REVOCA NADA. Los permisos que el entorno conceda por su cuenta
-- —`ALTER DEFAULT PRIVILEGES` sobre el esquema, si los hay— siguen intactos después de
-- aplicarla. RLS los neutraliza para quien está sujeto a RLS; para el resto, no.
--
-- Medido en producción el 2026-09-15: los permisos por defecto dan DML completo a `anon`,
-- `authenticated` y `service_role`, y `service_role` tiene BYPASSRLS. Ahí RLS detiene a los
-- dos primeros y NO al tercero. No es una excepción de estas dos tablas: es la postura de
-- las 31 que ya existen, y éstas no guardan ningún dato personal.
--
-- Deliberadamente NO se hace REVOKE sobre `anon`/`authenticated`: el aplicador corre con el
-- rol de la aplicación, que puede no tener permiso para revocar, y un REVOKE fallido tumbaría
-- la migración entera. RLS cubre a quien está sujeto a RLS; lo que quede fuera es decisión
-- de otra unidad, con su propia autorización.
--
-- CERO políticas se crean aquí. El rol de auditoría TAMPOCO recibe SELECT: la superficie de
-- evidencia será una VIEW, en otra unidad.
ALTER TABLE inventory_source          ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_ingestion_event ENABLE ROW LEVEL SECURITY;

-- Verificación (debe devolver 2)
SELECT count(*) AS tablas_creadas
FROM information_schema.tables
WHERE table_name IN ('inventory_source', 'inventory_ingestion_event');

-- ROLLBACK:
--   ALTER TABLE transacciones_temporales
--       DROP COLUMN IF EXISTS source_id,
--       DROP COLUMN IF EXISTS ingestion_event_id,
--       DROP COLUMN IF EXISTS inventory_class,
--       DROP COLUMN IF EXISTS received_at;
--   ALTER TABLE activos_inmutables
--       DROP COLUMN IF EXISTS source_id,
--       DROP COLUMN IF EXISTS ingestion_event_id,
--       DROP COLUMN IF EXISTS inventory_class,
--       DROP COLUMN IF EXISTS received_at,
--       DROP COLUMN IF EXISTS evidence_exclusion_reason;
--   DROP TABLE IF EXISTS inventory_ingestion_event;
--   DROP TABLE IF EXISTS inventory_source;
--
--   Revertir 030A no pierde nada: las columnas nacen vacías y esta fase no escribe una sola
--   fila. En cuanto 030B haga el backfill, revertir SÍ borraría procedencia — y parte de ella
--   (qué ejecución trajo qué) no se puede reconstruir después.
