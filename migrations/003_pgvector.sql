-- ============================================================
-- Migration 003: pgvector — búsqueda por similitud (Fase A)
-- Activa la extensión vector y crea la tabla de embeddings.
-- NO genera embeddings (eso es Fase B con Voyage). Puro esquema.
-- Totalmente reversible: ver bloque de rollback al final.
-- ============================================================

-- 1. Activar extensión pgvector (nativa en Supabase)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Tabla de embeddings — SEPARADA de activos_inmutables
--    para no afectar el rendimiento de las consultas geoespaciales.
CREATE TABLE IF NOT EXISTS activo_embeddings (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activo_id   UUID NOT NULL REFERENCES activos_inmutables(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('imagen', 'ficha_texto')),
    embedding   VECTOR(1024) NOT NULL,            -- voyage-multimodal-3 → 1024 dims
    source_url  TEXT,                             -- url de la foto o hash del texto
    model       TEXT NOT NULL DEFAULT 'voyage-multimodal-3',
    created_at  TIMESTAMP DEFAULT now()
);

-- 3. Índice HNSW para búsqueda por distancia coseno (rápido < 1M filas)
CREATE INDEX IF NOT EXISTS idx_activo_emb_hnsw
    ON activo_embeddings
    USING hnsw (embedding vector_cosine_ops);

-- 4. Índice para joins por activo
CREATE INDEX IF NOT EXISTS idx_activo_emb_activo
    ON activo_embeddings(activo_id);

-- 5. Verificación
SELECT
    (SELECT count(*) FROM pg_extension WHERE extname = 'vector')      AS vector_ext,
    (SELECT count(*) FROM information_schema.tables
        WHERE table_name = 'activo_embeddings')                        AS tabla_creada,
    (SELECT count(*) FROM activo_embeddings)                           AS filas_actuales;

-- ============================================================
-- ROLLBACK (si fuese necesario revertir):
--   DROP TABLE IF EXISTS activo_embeddings;
--   -- DROP EXTENSION IF EXISTS vector;  (solo si nada más lo usa)
-- ============================================================
