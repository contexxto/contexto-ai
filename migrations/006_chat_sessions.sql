-- ============================================================
-- Migration 006: Metadatos de conversaciones (sidebar tipo LLM)
--   El checkpointer (tabla 'checkpoints') guarda los MENSAJES, pero no
--   títulos personalizados, pines ni archivado. Esta tabla añade esa capa.
-- ============================================================

CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id  TEXT PRIMARY KEY,           -- = thread_id del checkpointer
    titulo      TEXT,                        -- título personalizado (renombrar)
    pinned      BOOLEAN NOT NULL DEFAULT false,
    archived    BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMP DEFAULT now(),
    updated_at  TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_pinned
    ON chat_sessions(pinned) WHERE pinned = true;

-- Verificación (debe devolver 1)
SELECT count(*) AS tabla_creada
FROM information_schema.tables
WHERE table_name = 'chat_sessions';

-- ============================================================
-- ROLLBACK:  DROP TABLE IF EXISTS chat_sessions;
-- ============================================================
