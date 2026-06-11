-- ============================================================================
-- Contexto AI · Migración 012 — Evidencia de la ficha técnica (Fase 2)
-- ----------------------------------------------------------------------------
-- Guarda las URLs de las fotos/evidencia que el corredor levanta en la segunda
-- visita (fotos de tuberías, factura de impermeabilización, etc.). Se almacena
-- como JSON (array de URLs públicas del bucket de Storage "evidencias").
-- También garantiza un único registro de ficha por activo (para upsert).
-- ============================================================================

ALTER TABLE ficha_tecnica_mantenimiento ADD COLUMN IF NOT EXISTS foto_evidencias TEXT;

-- Una ficha por activo (permite ON CONFLICT / upsert limpio).
CREATE UNIQUE INDEX IF NOT EXISTS uq_ficha_activo
    ON ficha_tecnica_mantenimiento (activo_id);
