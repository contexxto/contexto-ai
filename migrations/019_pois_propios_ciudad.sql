-- ============================================================
-- Migration 019: pois_propios gana columna `ciudad` (multi-ciudad seguro)
--
--   PROBLEMA QUE ARREGLA (detectado 2026-07-27):
--   `scripts/foso_pois_spike.py` hacía `TRUNCATE pois_propios` antes de insertar.
--   Correrlo con el bbox de una segunda ciudad BORRABA Quito entero. La tabla no
--   tenía forma de saber a qué mercado pertenecía cada POI, así que no había manera
--   de recargar una ciudad sin tocar las demás.
--
--   SOLUCIÓN: una columna `ciudad` + índice, para que la recarga sea
--   `DELETE ... WHERE ciudad = :ciudad` en vez de `TRUNCATE`.
--
--   NOTA sobre las queries de lectura: NO cambian. `_PROPIOS_ENTORNO_SQL` y
--   `_PROPIOS_TRANSPORTE_SQL` (app/rutas.py) filtran por proximidad geográfica
--   (ST_DWithin), y un POI de otra ciudad jamás cae dentro del radio de un inmueble
--   de Quito. La columna es para el CICLO DE CARGA, no para el de consulta.
--   (Supuesto explícito: los mercados objetivo están a cientos de km entre sí.
--   Si alguna vez se cargan dos ciudades conurbadas, revisar este supuesto.)
-- ============================================================

-- 1) Columna nullable primero (no bloquea; la tabla ya tiene datos en prod)
ALTER TABLE pois_propios ADD COLUMN IF NOT EXISTS ciudad text;

-- 2) Backfill: todo lo que existe hoy es Quito (carga del 2026-07-01, bbox
--    xmin=-78.60 xmax=-78.40 ymin=-0.35 ymax=-0.05). Verificado 2026-07-27: 4.898 POIs.
UPDATE pois_propios SET ciudad = 'quito' WHERE ciudad IS NULL;

-- 3) Recién ahora NOT NULL + default, con la tabla ya consistente
ALTER TABLE pois_propios ALTER COLUMN ciudad SET DEFAULT 'quito';
ALTER TABLE pois_propios ALTER COLUMN ciudad SET NOT NULL;

-- 4) Índice para el DELETE acotado por ciudad (el que reemplaza al TRUNCATE)
CREATE INDEX IF NOT EXISTS pois_propios_ciudad_idx ON pois_propios (ciudad);

-- 5) Slug limpio: minúsculas, sin espacios (evita 'Quito' vs 'quito' vs 'quito ')
ALTER TABLE pois_propios DROP CONSTRAINT IF EXISTS ck_pois_ciudad;
ALTER TABLE pois_propios ADD  CONSTRAINT ck_pois_ciudad
    CHECK (ciudad = lower(btrim(ciudad)) AND ciudad <> '' AND ciudad !~ '\s');

-- Verificación (debe devolver 0 filas sin ciudad, y el desglose por mercado)
SELECT ciudad, count(*) AS pois FROM pois_propios GROUP BY ciudad ORDER BY 2 DESC;

-- ============================================================
-- ROLLBACK:
--   DROP INDEX IF EXISTS pois_propios_ciudad_idx;
--   ALTER TABLE pois_propios DROP CONSTRAINT IF EXISTS ck_pois_ciudad;
--   ALTER TABLE pois_propios DROP COLUMN IF EXISTS ciudad;
-- ============================================================
