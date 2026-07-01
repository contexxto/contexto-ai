-- ============================================================
-- Migration 015: Isócronas peatonales por inmueble — isocronas_inmueble
--   Ladrillo #7 del foso (SPEC_Foso_Capa_de_Datos.md, §2.3). Motor: Valhalla
--   auto-hospedado (/isochrone, costing=pedestrian). El inventario es FIJO →
--   se pre-computa UNA isócrona por (inmueble, minutos) y se cachea en PostGIS.
--   Habilita el overlay del Mapa Vivo 2C y la CUÑA de búsqueda por ancla+tiempo
--   (isócrona del ancla → ST_Contains filtra el inventario fijo). Ver §2.4.
-- ============================================================

CREATE TABLE IF NOT EXISTS isocronas_inmueble (
    id          bigserial PRIMARY KEY,
    activo_id   uuid NOT NULL REFERENCES activos_inmutables(id) ON DELETE CASCADE,
    minutos     integer NOT NULL,                      -- 15 | 30
    geom        geometry(MultiPolygon, 4326) NOT NULL,
    generado_en timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS isocronas_inmueble_geom_gix ON isocronas_inmueble USING GIST (geom);
CREATE INDEX IF NOT EXISTS isocronas_inmueble_activo_idx ON isocronas_inmueble (activo_id);

-- UNIQUE nombrada (idempotente), requerida por el upsert ON CONFLICT (activo_id, minutos).
-- Se normaliza el nombre por si una corrida previa la dejó autogenerada (..._key).
ALTER TABLE isocronas_inmueble DROP CONSTRAINT IF EXISTS isocronas_inmueble_activo_id_minutos_key;
ALTER TABLE isocronas_inmueble DROP CONSTRAINT IF EXISTS uq_isocrona_activo_minutos;
ALTER TABLE isocronas_inmueble ADD  CONSTRAINT uq_isocrona_activo_minutos UNIQUE (activo_id, minutos);

-- minutos en un rango sano (peatonal: 5..60). Idempotente vía DROP + ADD.
ALTER TABLE isocronas_inmueble DROP CONSTRAINT IF EXISTS ck_isocrona_minutos;
ALTER TABLE isocronas_inmueble ADD  CONSTRAINT ck_isocrona_minutos
    CHECK (minutos > 0 AND minutos <= 60);

-- Verificación (debe devolver 1)
SELECT count(*) AS tabla_creada
FROM information_schema.tables
WHERE table_name = 'isocronas_inmueble';

-- ============================================================
-- ROLLBACK:  DROP TABLE IF EXISTS isocronas_inmueble;
-- ============================================================
