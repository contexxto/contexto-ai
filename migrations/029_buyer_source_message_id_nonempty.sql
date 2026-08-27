-- ============================================================
-- Migration 029: `source_message_id` tampoco puede ser una cadena vacía (E3.2 · 1C)
--
--   POR QUÉ EXISTE: la 028 declaró `source_message_id TEXT NOT NULL`, y eso impide `NULL`
--   pero **no** impide `""`. En la revisión de E3.1b se comprobó que la cadena vacía
--   atravesaba la validación del store y llegaba hasta la base.
--
--   No era explotable —la garantía vivía aguas arriba, en
--   `IdentifiedUserMessage(message_id, min_length=1)`, y el store no tenía consumidor
--   productivo— pero la garantía estaba en un solo sitio y atribuida al sitio equivocado:
--   se creía del esquema, y el esquema no la daba.
--
--   DEFENSA EN PROFUNDIDAD, y cada capa responde por lo suyo:
--
--     upstream   IdentifiedUserMessage      el mensaje nace con identidad o no nace
--     Python     anexar_revision()          falla antes de tocar la base
--     esquema    este CHECK                 ninguna otra vía puede colarla
--
--   La tercera capa importa porque las dos primeras protegen UN camino. Un backfill, una
--   migración de datos o un segundo escritor futuro no pasan por `anexar_revision`.
--
--   `btrim` y no solo `<> ''`: un identificador de espacios no identifica nada, y sería
--   peor que la cadena vacía porque parece un valor.
--
--   NO SE EDITA LA 028. Está en `main` y podría estar aplicada en algún entorno; reescribir
--   una migración ya publicada rompe el supuesto de que el historial es inmutable.
--
--   NO SE APLICA EN PRODUCCIÓN EN ESTA UNIDAD — ni la 028 ni ésta. El store sigue sin
--   consumidor productivo y el gate de esquema lo mantiene apagado.
--
--   Idempotente: se puede correr varias veces.
-- ============================================================

-- `ADD CONSTRAINT` no admite `IF NOT EXISTS` en PostgreSQL, así que la idempotencia se
-- consigue comprobando el catálogo. El bloque completo es un no-op en la segunda pasada.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_buyer_revisions_message_id_no_vacio'
          -- Acotado A LA TABLA: `conname` no es unico por base de datos. Otra tabla con una
          -- restriccion del mismo nombre haria creer que esta migracion ya se aplico, y
          -- `buyer_context_revisions` se quedaria SIN el CHECK — en silencio.
          AND conrelid = 'buyer_context_revisions'::regclass
    ) THEN
        ALTER TABLE buyer_context_revisions
            ADD CONSTRAINT ck_buyer_revisions_message_id_no_vacio
            CHECK (length(btrim(source_message_id)) > 0);
    END IF;
END $$;

COMMENT ON CONSTRAINT ck_buyer_revisions_message_id_no_vacio ON buyer_context_revisions IS
    'NOT NULL impide NULL, no la cadena vacía. Un source_message_id vacío o de solo '
    'espacios no identifica ningún mensaje, y sin identidad no hay idempotencia posible.';

-- Verificación (debe devolver 1)
SELECT count(*) AS restriccion_creada
FROM pg_constraint
WHERE conname = 'ck_buyer_revisions_message_id_no_vacio'
  AND conrelid = 'buyer_context_revisions'::regclass;

-- ROLLBACK:
--   ALTER TABLE buyer_context_revisions
--     DROP CONSTRAINT IF EXISTS ck_buyer_revisions_message_id_no_vacio;
--   Revertir solo devuelve la laguna: `NOT NULL` seguiría dejando pasar `""`.
