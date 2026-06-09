-- ============================================================================
-- Contexto AI · Migración 007 — Caché de embeddings de texto
-- ----------------------------------------------------------------------------
-- POR QUÉ
--   Voyage (plan free) limita a 3 RPM. Consultas de texto idénticas (búsquedas
--   repetidas en demos/pruebas, /match y /similar) re-gastaban llamadas. Esta
--   tabla cachea el vector por (hash del texto, input_type, modelo) para no
--   volver a llamar a Voyage por el mismo texto.
--
-- NOTA
--   - Solo cachea TEXTO. Las imágenes ya tienen caché a nivel de activo
--     (image_sha256, migración 005).
--   - La app degrada con elegancia: si esta tabla no existe, embed_text_cached
--     simplemente llama a Voyage sin cachear (envuelto en SAVEPOINT).
-- ============================================================================

CREATE TABLE IF NOT EXISTS embedding_cache (
    content_sha256  TEXT         NOT NULL,           -- sha256(modelo|input_type|texto)
    input_type      TEXT         NOT NULL,           -- 'query' | 'document'
    model           TEXT         NOT NULL,           -- p.ej. voyage-multimodal-3
    embedding       vector(1024) NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (content_sha256, input_type, model)
);

COMMENT ON TABLE embedding_cache IS
  'Caché de embeddings de texto por hash, para no re-llamar a Voyage por el mismo texto.';
