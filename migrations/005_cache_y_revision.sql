-- ============================================================
-- Migration 005: Caché por hash de imagen + Cola de revisión asistida
--   1. activos_inmutables: image_sha256 (dedup/caché) + imagen_url (foto canónica)
--   2. ficha_tecnica_mantenimiento: ficha_vision_raw (extracción IA completa, JSONB)
--      + estado_revision ahora admite 'rechazado'
--   3. correcciones_ficha: bitácora de correcciones humanas (ground-truth)
-- Reversible: ver bloque de rollback al final.
-- ============================================================

-- 1. Caché por hash + foto canónica en el activo ----------------
ALTER TABLE activos_inmutables
    ADD COLUMN IF NOT EXISTS image_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS imagen_url   TEXT;

-- Lookup rápido para el caché (no único: filas antiguas tienen NULL).
CREATE INDEX IF NOT EXISTS idx_activos_img_hash
    ON activos_inmutables(image_sha256);

-- 2. Extracción IA completa para poder revisar/corregir ---------
ALTER TABLE ficha_tecnica_mantenimiento
    ADD COLUMN IF NOT EXISTS ficha_vision_raw JSONB;

-- Ampliar estados de revisión para permitir 'rechazado'.
-- (La migración 004 creó un CHECK inline con nombre autogenerado;
--  lo eliminamos de forma robusta sin depender del nombre exacto.)
DO $$
DECLARE c text;
BEGIN
    FOR c IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'ficha_tecnica_mantenimiento'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%estado_revision%'
    LOOP
        EXECUTE format('ALTER TABLE ficha_tecnica_mantenimiento DROP CONSTRAINT %I', c);
    END LOOP;
END $$;

ALTER TABLE ficha_tecnica_mantenimiento
    ADD CONSTRAINT ck_ficha_estado_revision
    CHECK (estado_revision IN ('publicado', 'pendiente_revision', 'rechazado'));

-- 3. Bitácora de correcciones humanas (la "fábrica de ground-truth")
CREATE TABLE IF NOT EXISTS correcciones_ficha (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activo_id     UUID NOT NULL REFERENCES activos_inmutables(id) ON DELETE CASCADE,
    campo         TEXT NOT NULL,
    valor_ia      TEXT,
    valor_humano  TEXT,
    revisor       TEXT,
    created_at    TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_correcciones_activo
    ON correcciones_ficha(activo_id);

-- 4. Verificación
SELECT
    (SELECT count(*) FROM information_schema.columns
        WHERE table_name='activos_inmutables' AND column_name='image_sha256')      AS col_hash,
    (SELECT count(*) FROM information_schema.columns
        WHERE table_name='activos_inmutables' AND column_name='imagen_url')        AS col_img_url,
    (SELECT count(*) FROM information_schema.columns
        WHERE table_name='ficha_tecnica_mantenimiento' AND column_name='ficha_vision_raw') AS col_raw,
    (SELECT count(*) FROM information_schema.tables
        WHERE table_name='correcciones_ficha')                                     AS tabla_correcciones;

-- ============================================================
-- ROLLBACK:
--   DROP TABLE IF EXISTS correcciones_ficha;
--   ALTER TABLE ficha_tecnica_mantenimiento DROP COLUMN IF EXISTS ficha_vision_raw;
--   ALTER TABLE ficha_tecnica_mantenimiento DROP CONSTRAINT IF EXISTS ck_ficha_estado_revision;
--   ALTER TABLE ficha_tecnica_mantenimiento ADD CONSTRAINT ck_ficha_estado_revision
--       CHECK (estado_revision IN ('publicado','pendiente_revision'));
--   DROP INDEX IF EXISTS idx_activos_img_hash;
--   ALTER TABLE activos_inmutables DROP COLUMN IF EXISTS image_sha256;
--   ALTER TABLE activos_inmutables DROP COLUMN IF EXISTS imagen_url;
-- ============================================================
