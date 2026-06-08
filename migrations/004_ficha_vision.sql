-- ============================================================
-- Migration 004: campos de gobernanza para extracción por visión (Fase B1)
-- Marca el origen del dato, la confianza y el estado de revisión.
-- Aditivo y reversible.
-- ============================================================

ALTER TABLE ficha_tecnica_mantenimiento
    ADD COLUMN IF NOT EXISTS fuente TEXT NOT NULL DEFAULT 'manual'
        CHECK (fuente IN ('manual', 'vision_ia')),
    ADD COLUMN IF NOT EXISTS confianza_extraccion NUMERIC(3,2),
    ADD COLUMN IF NOT EXISTS estado_revision TEXT NOT NULL DEFAULT 'publicado'
        CHECK (estado_revision IN ('publicado', 'pendiente_revision'));

-- Verificación
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'ficha_tecnica_mantenimiento'
  AND column_name IN ('fuente', 'confianza_extraccion', 'estado_revision')
ORDER BY column_name;

-- ============================================================
-- ROLLBACK:
--   ALTER TABLE ficha_tecnica_mantenimiento
--     DROP COLUMN IF EXISTS fuente,
--     DROP COLUMN IF EXISTS confianza_extraccion,
--     DROP COLUMN IF EXISTS estado_revision;
-- ============================================================
