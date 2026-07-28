-- ============================================================
-- Migration 020: unicidad sobre el identificador de ORIGEN de cada POI
--
--   POR QUÉ (Fase 3, punto 1 del PLAN_Migracion_MapChat):
--   Hoy la única clave es `id` (bigserial), que se regenera en cada carga. Por eso
--   el refresco solo puede ser borrar-y-recargar: cada POI recibe id nuevo, se pierde
--   su antigüedad, y nada puede colgar de él de forma estable.
--
--   Con unicidad sobre el id de origen, el refresco pasa a ser un UPSERT: actualiza
--   lo que cambió, marca operativo=false lo que desapareció, inserta lo nuevo —
--   CONSERVANDO la fila y lo que tenga enganchado (la curación del corredor, cuando
--   se construya: Fase 3 punto 3).
--
--   Los identificadores ya son aptos (verificado en prod 2026-07-27):
--     - overture_id (GERS): 2.851 distintos de 2.851 no nulos. Estable ENTRE
--       RELEASES por diseño de Overture — la SPEC §1.3 ya lo anotó "para dedupe futuro".
--     - osm_id: estable por definición en OSM.
--
--   Índices PARCIALES (WHERE ... IS NOT NULL) porque las dos columnas son mutuamente
--   excluyentes: un POI viene de Overture o de OSM, nunca de ambas. Un UNIQUE normal
--   colapsaría con los múltiples NULL (en Postgres los NULL no colisionan entre sí,
--   pero el índice parcial además es más pequeño y expresa la intención).
--
--   NO resuelve la conflación Overture↔OSM (mismo lugar en las dos fuentes = dos
--   filas). Eso es otro problema y tiene su receta en la SPEC §1.6 (≤60 m + nombre
--   similar por trigram). Esta migración solo hace posible el upsert POR FUENTE.
-- ============================================================

-- Red de seguridad antes de tocar nada (primera recarga real de la tabla).
CREATE TABLE IF NOT EXISTS pois_propios_backup_20260727 AS
    SELECT * FROM pois_propios;

-- Verificación previa: si estas consultas devuelven algo, hay duplicados y el índice
-- fallaría. Se dejan como documentación del estado que se validó antes de crear.
--   SELECT overture_id, count(*) FROM pois_propios WHERE overture_id IS NOT NULL
--     GROUP BY 1 HAVING count(*) > 1;
--   SELECT osm_id, count(*) FROM pois_propios WHERE osm_id IS NOT NULL
--     GROUP BY 1 HAVING count(*) > 1;

CREATE UNIQUE INDEX IF NOT EXISTS pois_propios_overture_uidx
    ON pois_propios (overture_id) WHERE overture_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS pois_propios_osm_uidx
    ON pois_propios (osm_id) WHERE osm_id IS NOT NULL;

-- Verificación (ambos deben aparecer)
SELECT indexname FROM pg_indexes
WHERE tablename = 'pois_propios' AND indexname LIKE '%_uidx';

-- ============================================================
-- ROLLBACK:
--   DROP INDEX IF EXISTS pois_propios_overture_uidx;
--   DROP INDEX IF EXISTS pois_propios_osm_uidx;
--   -- el backup se conserva a propósito; borrarlo es decisión aparte:
--   -- DROP TABLE IF EXISTS pois_propios_backup_20260727;
-- ============================================================
