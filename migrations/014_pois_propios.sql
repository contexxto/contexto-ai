-- ============================================================
-- Migration 014: Capa propia de POIs (el foso) — pois_propios
--   Primer ladrillo del stack de datos propio (SPEC_Foso_Capa_de_Datos.md,
--   Ladrillo #18): Overture Places (6 categorías) + OSM transporte (Overpass),
--   conflados y almacenables (licencias CDLA/ODbL, sin share-alike sobre POIs).
--   La tabla ya existía (creada por scripts/foso_pois_spike.py); esta migración
--   la formaliza como esquema canónico versionado, con índices y constraints.
--   La consume app/rutas.py (_servicios_propios) como fuente PRIMARIA del entorno,
--   con Google solo de fallback por hueco.
-- ============================================================

CREATE TABLE IF NOT EXISTS pois_propios (
    id                 bigserial PRIMARY KEY,
    nombre             text,
    categoria          text NOT NULL,
    categoria_overture text,
    geom               geometry(Point, 4326) NOT NULL,
    fuente             text NOT NULL DEFAULT 'overture',
    confianza          real,
    overture_id        text,
    osm_id             text,
    marca              text,
    direccion          text,
    operativo          boolean DEFAULT true,
    actualizado_en     timestamptz NOT NULL DEFAULT now()
);

-- Columnas agregadas si la tabla venía de una corrida previa del spike sin ellas
ALTER TABLE pois_propios ADD COLUMN IF NOT EXISTS osm_id text;
ALTER TABLE pois_propios ADD COLUMN IF NOT EXISTS fuente text NOT NULL DEFAULT 'overture';

CREATE INDEX IF NOT EXISTS pois_propios_geom_gix ON pois_propios USING GIST (geom);
CREATE INDEX IF NOT EXISTS pois_propios_cat_idx  ON pois_propios (categoria);

-- Constraints de integridad. Postgres NO soporta ADD CONSTRAINT IF NOT EXISTS →
-- se hace idempotente con DROP IF EXISTS + ADD.
ALTER TABLE pois_propios DROP CONSTRAINT IF EXISTS ck_pois_categoria;
ALTER TABLE pois_propios ADD  CONSTRAINT ck_pois_categoria
    CHECK (categoria IN ('salud','farmacia','supermercado','educacion',
                         'parque','centro_comercial','transporte'));

ALTER TABLE pois_propios DROP CONSTRAINT IF EXISTS ck_pois_fuente;
ALTER TABLE pois_propios ADD  CONSTRAINT ck_pois_fuente
    CHECK (fuente IN ('overture','osm'));

-- Verificación (debe devolver 1)
SELECT count(*) AS tabla_creada
FROM information_schema.tables
WHERE table_name = 'pois_propios';

-- ============================================================
-- ROLLBACK:  DROP TABLE IF EXISTS pois_propios;
-- ============================================================
