-- ============================================================
-- Migration 041: evidencia estructurada del entorno, por dimensión (PLACE-PROVENANCE-041)
--
--   QUÉ HACE: añade a `public.activos_inmutables` dos columnas `jsonb` NULLABLE y SIN DEFAULT,
--   una por dimensión, con un CHECK cada una:
--
--     servicios_evidencia     ← `NearbyPlacesEvidenceV0`   (app/contracts/place_evidence_v0.py)
--     conectividad_evidencia  ← `NearestTransitEvidenceV0`
--
--   Cada documento guarda, por ELEMENTO, sus tres ejes de procedencia por separado:
--     SOURCE        el registro del dataset abierto (Overture / OSM)   → EvidenceRefV0 PUBLIC_DATASET
--     METHOD        cómo Contexto calculó la distancia                  → EvidenceRefV0 OWN_MEASUREMENT
--     VERIFICATION  si un corredor lo comprobó en terreno               → EvidenceRefV0 OPERATOR_DECLARED
--   y la clase de cada valor (Plan 1.1 §E4.5): la distancia en línea recta es `derived`, los
--   minutos por paso fijo son `estimated`. La prosa histórica (`servicios_cercanos`,
--   `conectividad`) se RENDERIZA desde el documento; el texto no es la fuente.
--
--   QUÉ NO HACE, y es la mitad importante:
--     · no escribe ni una fila: las columnas nacen en NULL, que significa UNKNOWN. Ninguna fila
--       histórica adquiere procedencia por defecto, ni se infiere de su texto;
--     · no toca `servicios_cercanos` ni `conectividad`, ni borra el texto legado;
--     · no crea `contexto_procedencia` —la etiqueta única que esta unidad descartó— y ABORTA si
--       alguien la creó: la frontera de lectura (`app/place/legado.py`) abriría por ella;
--     · no añade trigger: con evidencia presente, el texto deja de ser autoridad (la lectura
--       renderiza desde el documento y comprueba su origen), así que un escritor que solo toque
--       el texto no puede lavar procedencia. Ver RESULTADO_PLACE_PROVENANCE_041_CODE_0.1 §K;
--     · ni GRANT, ni REVOKE, ni políticas, ni RLS. Las columnas heredan la autoridad de la tabla;
--       lo que la tabla tenga de más es el residual R2 de `activos_inmutables`, fuera de aquí;
--     · no toca el perímetro de la 040 (`pois_propios`, `entorno_curacion`, `pois_vivos`).
--
--   IDEMPOTENCIA EXPLÍCITA: si las dos columnas ya existen EXACTAMENTE como las deja esta
--   migración (jsonb, nullable, sin default, con sus dos CHECK validados), no hace nada. Si
--   existe cualquier otra cosa —una sola de las dos, otro tipo, un DEFAULT, sin el CHECK—,
--   ABORTA sin tocar nada. Nada se "arregla" en caliente.
--
--   QUIÉN LA APLICA: el dueño de `activos_inmutables` (en producción, `postgres`).
-- ============================================================

BEGIN;

-- `ADD COLUMN` sin default y `ADD CONSTRAINT` piden un ACCESS EXCLUSIVE breve.
SET LOCAL lock_timeout = '3s';

DO $$
DECLARE
    tabla         CONSTANT regclass := to_regclass('public.activos_inmutables');
    cols          CONSTANT text[] := ARRAY['servicios_evidencia', 'conectividad_evidencia'];
    cks           CONSTANT text[] := ARRAY['ck_activos_servicios_evidencia',
                                           'ck_activos_conectividad_evidencia'];
    presentes     integer;
    exactas       integer;
    ck_validos    integer;
    rls_antes     boolean;
    force_antes   boolean;
    acl_antes     text;
    pol_antes     integer;
    trg_antes     integer;
    no_nulas      bigint;
BEGIN
    -- ── 0 · COMPUERTAS, FAIL-CLOSED ──────────────────────────────────────────────
    IF tabla IS NULL THEN
        RAISE EXCEPTION '041 ABORTA: no existe public.activos_inmutables. ¿Base equivocada?';
    END IF;
    IF (SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = tabla) <> current_user THEN
        RAISE EXCEPTION '041 ABORTA: el dueño de activos_inmutables no es quien aplica (%).', current_user;
    END IF;
    IF (SELECT count(*) FROM pg_attribute WHERE attrelid = tabla AND NOT attisdropped
          AND attname IN ('servicios_cercanos', 'conectividad')) <> 2 THEN
        RAISE EXCEPTION '041 ABORTA: activos_inmutables no tiene servicios_cercanos y conectividad. '
                        '¿Es la tabla correcta?';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = tabla AND NOT attisdropped
                 AND attname = 'contexto_procedencia') THEN
        RAISE EXCEPTION '041 ABORTA: existe contexto_procedencia, la etiqueta única que esta unidad '
                        'descartó. La frontera de lectura abriría por ella: caracterízala antes.';
    END IF;

    SELECT count(*) INTO presentes
      FROM pg_attribute WHERE attrelid = tabla AND NOT attisdropped AND attname = ANY (cols);
    SELECT count(*) INTO exactas
      FROM pg_attribute WHERE attrelid = tabla AND NOT attisdropped AND attname = ANY (cols)
       AND atttypid = 'jsonb'::regtype AND NOT attnotnull AND NOT atthasdef;
    SELECT count(*) INTO ck_validos
      FROM pg_constraint WHERE conrelid = tabla AND contype = 'c' AND convalidated AND conname = ANY (cks);

    IF presentes = 2 AND exactas = 2 AND ck_validos = 2 THEN
        RAISE NOTICE '041: ya aplicada (dos columnas jsonb nullable, sin default, con sus CHECK). Nada que hacer.';
        RETURN;
    END IF;
    IF presentes <> 0 THEN
        RAISE EXCEPTION '041 ABORTA: estado intermedio o ajeno (% de 2 columnas presentes, % exactas, '
                        '% de 2 CHECK). No se arregla en caliente: caracterízalo antes.',
                        presentes, exactas, ck_validos;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = tabla AND conname = ANY (cks)) THEN
        RAISE EXCEPTION '041 ABORTA: ya existe una restricción con el nombre de las de la 041.';
    END IF;

    -- Lo que la 041 NO debe mover, medido antes.
    SELECT relrowsecurity, relforcerowsecurity, coalesce(relacl::text, '')
      INTO rls_antes, force_antes, acl_antes FROM pg_class WHERE oid = tabla;
    SELECT count(*) INTO pol_antes FROM pg_policy WHERE polrelid = tabla;
    SELECT count(*) INTO trg_antes FROM pg_trigger WHERE tgrelid = tabla AND NOT tgisinternal;

    -- ── 1 · LAS DOS COLUMNAS: NULLABLE, SIN DEFAULT (NULL = UNKNOWN) ────────────────
    ALTER TABLE public.activos_inmutables ADD COLUMN servicios_evidencia jsonb;
    ALTER TABLE public.activos_inmutables ADD COLUMN conectividad_evidencia jsonb;

    -- ── 2 · CHECK: la forma mínima que la base garantiza por sí misma ───────────────
    -- El contrato Pydantic valida todo (enlaces por eje, tipos de evidencia, ids). Aquí se
    -- repite lo que ninguna escritura, venga de donde venga, puede saltarse:
    --   · un objeto de la versión y la dimensión correctas;
    --   · estado available | insufficient_evidence (UNKNOWN es NULL, no un documento);
    --   · available exige elementos y evidencia; insufficient_evidence no admite elementos;
    --   · toda evidencia es persistable (Plan 1.1 §E4.6) y ninguna es de Google;
    --   · la línea recta es `derived`, y una duración por paso fijo es `estimated`.
    ALTER TABLE public.activos_inmutables ADD CONSTRAINT ck_activos_servicios_evidencia CHECK (
        -- coalesce(…, false): una clave AUSENTE da NULL, y un CHECK con NULL PASA. Sin esto,
        -- un documento sin `status` o sin `derived_at` se colaría.
        servicios_evidencia IS NULL OR coalesce((
            jsonb_typeof(servicios_evidencia) = 'object'
            AND servicios_evidencia->>'contract_version' = 'place-dimension-evidence/v0'
            AND servicios_evidencia->>'dimension' = 'nearby_places'
            AND servicios_evidencia->>'status' IN ('available', 'insufficient_evidence')
            AND servicios_evidencia->>'derived_at' ~ '^\d{4}-\d{2}-\d{2}T'
            AND jsonb_typeof(servicios_evidencia->'origin') = 'object'
            AND jsonb_typeof(servicios_evidencia->'items') = 'array'
            AND jsonb_typeof(servicios_evidencia->'evidence') = 'array'
            AND (servicios_evidencia->>'status' <> 'available'
                 OR (jsonb_array_length(servicios_evidencia->'items') > 0
                     AND jsonb_array_length(servicios_evidencia->'evidence') > 0))
            AND (servicios_evidencia->>'status' <> 'insufficient_evidence'
                 OR jsonb_array_length(servicios_evidencia->'items') = 0)
            AND NOT jsonb_path_exists(servicios_evidencia,
                    '$.evidence[*] ? (@.persistence_policy != "persistable")')
            AND NOT jsonb_path_exists(servicios_evidencia,
                    '$.evidence[*].provider ? (@ like_regex "^google" flag "i")')
            AND NOT (servicios_evidencia->>'distance_method' = 'straight_line_geodesic'
                     AND servicios_evidencia->>'distance_class' IS DISTINCT FROM 'derived')
        ), false));

    ALTER TABLE public.activos_inmutables ADD CONSTRAINT ck_activos_conectividad_evidencia CHECK (
        -- coalesce(…, false): una clave AUSENTE da NULL, y un CHECK con NULL PASA. Sin esto,
        -- un documento sin `status` o sin `derived_at` se colaría.
        conectividad_evidencia IS NULL OR coalesce((
            jsonb_typeof(conectividad_evidencia) = 'object'
            AND conectividad_evidencia->>'contract_version' = 'place-dimension-evidence/v0'
            AND conectividad_evidencia->>'dimension' = 'nearest_transit'
            AND conectividad_evidencia->>'status' IN ('available', 'insufficient_evidence')
            AND conectividad_evidencia->>'derived_at' ~ '^\d{4}-\d{2}-\d{2}T'
            AND jsonb_typeof(conectividad_evidencia->'origin') = 'object'
            AND jsonb_typeof(conectividad_evidencia->'evidence') = 'array'
            AND (conectividad_evidencia->>'status' <> 'available'
                 OR (jsonb_typeof(conectividad_evidencia->'stop') = 'object'
                     AND jsonb_array_length(conectividad_evidencia->'evidence') > 0))
            AND (conectividad_evidencia->>'status' <> 'insufficient_evidence'
                 OR jsonb_typeof(conectividad_evidencia->'stop') IS DISTINCT FROM 'object')
            AND NOT jsonb_path_exists(conectividad_evidencia,
                    '$.evidence[*] ? (@.persistence_policy != "persistable")')
            AND NOT jsonb_path_exists(conectividad_evidencia,
                    '$.evidence[*].provider ? (@ like_regex "^google" flag "i")')
            AND NOT (conectividad_evidencia->>'distance_method' = 'straight_line_geodesic'
                     AND conectividad_evidencia->>'distance_class' IS DISTINCT FROM 'derived')
            AND NOT jsonb_path_exists(conectividad_evidencia,
                    '$.walk_duration ? (@.method == "straight_line_at_fixed_pace" && @.value_class != "estimated")')
        ), false));

    COMMENT ON COLUMN public.activos_inmutables.servicios_evidencia IS
        'PLACE-PROVENANCE-041. NearbyPlacesEvidenceV0 (place-dimension-evidence/v0): servicios más '
        'cercanos por categoría en la capa propia, con SOURCE/METHOD/VERIFICATION por elemento. '
        'NULL = UNKNOWN. servicios_cercanos se renderiza desde aquí; el texto no es la fuente.';
    COMMENT ON COLUMN public.activos_inmutables.conectividad_evidencia IS
        'PLACE-PROVENANCE-041. NearestTransitEvidenceV0 (place-dimension-evidence/v0): parada más '
        'cercana (masiva primero) en la capa propia. Los minutos son estimated (recta / 80 m/min), '
        'nunca tiempo de ruta. NULL = UNKNOWN. conectividad se renderiza desde aquí.';

    -- ── 3 · VERIFICACIÓN FAIL-CLOSED (mide el efecto; no lo declara) ────────────────
    IF (SELECT count(*) FROM pg_attribute WHERE attrelid = tabla AND NOT attisdropped
          AND attname = ANY (cols) AND atttypid = 'jsonb'::regtype AND NOT attnotnull
          AND NOT atthasdef AND attacl IS NULL) <> 2 THEN
        RAISE EXCEPTION '041 FALLA: las columnas no quedaron jsonb, nullable, sin default y sin ACL propia';
    END IF;
    IF (SELECT count(*) FROM pg_constraint WHERE conrelid = tabla AND contype = 'c'
          AND convalidated AND conname = ANY (cks)) <> 2 THEN
        RAISE EXCEPTION '041 FALLA: los dos CHECK no quedaron validados';
    END IF;
    SELECT count(*) INTO no_nulas FROM public.activos_inmutables
     WHERE servicios_evidencia IS NOT NULL OR conectividad_evidencia IS NOT NULL;
    IF no_nulas <> 0 THEN
        RAISE EXCEPTION '041 FALLA: % fila(s) nacieron con evidencia; ninguna debe tenerla', no_nulas;
    END IF;
    IF (SELECT relrowsecurity FROM pg_class WHERE oid = tabla) IS DISTINCT FROM rls_antes
       OR (SELECT relforcerowsecurity FROM pg_class WHERE oid = tabla) IS DISTINCT FROM force_antes
       OR (SELECT coalesce(relacl::text, '') FROM pg_class WHERE oid = tabla) IS DISTINCT FROM acl_antes THEN
        RAISE EXCEPTION '041 FALLA: cambió el RLS, el FORCE o el ACL de activos_inmutables';
    END IF;
    IF (SELECT count(*) FROM pg_policy WHERE polrelid = tabla) <> pol_antes
       OR (SELECT count(*) FROM pg_trigger WHERE tgrelid = tabla AND NOT tgisinternal) <> trg_antes THEN
        RAISE EXCEPTION '041 FALLA: cambiaron las políticas o los triggers de activos_inmutables';
    END IF;

    RAISE NOTICE '041 OK: 2 columnas jsonb nullable sin default, 2 CHECK validados, 0 filas con '
                 'evidencia, RLS/ACL/políticas/triggers de activos_inmutables intactos';
END $$;

-- Verificación legible.
SELECT a.attname AS columna, format_type(a.atttypid, a.atttypmod) AS tipo,
       NOT a.attnotnull AS nullable, a.atthasdef AS con_default
  FROM pg_attribute a
 WHERE a.attrelid = 'public.activos_inmutables'::regclass
   AND a.attname IN ('servicios_evidencia', 'conectividad_evidencia')
 ORDER BY a.attname;

COMMIT;

-- ── ROLLBACK ────────────────────────────────────────────────────────────────────────
--
-- Deshace exactamente lo de arriba. Sólo con autorización explícita. Las columnas se llevan
-- la evidencia que los escritores hayan guardado (re-derivable desde la capa propia); el texto
-- legado NO se toca. El código de esta unidad funciona sin las columnas (escribe solo el texto),
-- así que el orden da igual.
--
--   BEGIN;
--   ALTER TABLE public.activos_inmutables DROP CONSTRAINT IF EXISTS ck_activos_conectividad_evidencia;
--   ALTER TABLE public.activos_inmutables DROP CONSTRAINT IF EXISTS ck_activos_servicios_evidencia;
--   ALTER TABLE public.activos_inmutables DROP COLUMN IF EXISTS conectividad_evidencia;
--   ALTER TABLE public.activos_inmutables DROP COLUMN IF EXISTS servicios_evidencia;
--   COMMIT;
