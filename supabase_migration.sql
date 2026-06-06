-- ============================================================
-- Contexto AI V2 — Migración a Supabase
-- Pega esto en: Supabase Dashboard → SQL Editor → New Query
-- ============================================================

-- Supabase ya tiene PostGIS activo. Solo necesitamos pgcrypto:
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Activo Físico Perpetuo
CREATE TABLE IF NOT EXISTS activos_inmutables (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    geom                        GEOMETRY(Point, 4326) NOT NULL,
    direccion_estandarizada     VARCHAR(255) NOT NULL,
    piso_altura                 INT DEFAULT 1,
    walk_score                  INT CHECK (walk_score BETWEEN 0 AND 100),
    score_ruido_predictivo      VARCHAR(10) CHECK (score_ruido_predictivo IN ('BAJO', 'MEDIO', 'ALTO')),
    volumen_trafico_historico   INT DEFAULT 0,
    densidad_poblacional_pico   INT DEFAULT 0,
    porcentaje_cobertura_vegetal NUMERIC(5,2),
    created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_activos_geom ON activos_inmutables USING GIST(geom);

-- 2. Transacciones Temporales
CREATE TABLE IF NOT EXISTS transacciones_temporales (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activo_id           UUID REFERENCES activos_inmutables(id) ON DELETE CASCADE,
    tipo_operacion      VARCHAR(20) CHECK (tipo_operacion IN ('ARRIENDO', 'VENTA', 'MONITOREO_PASIVO')),
    precio              NUMERIC(12,2),
    estado_anuncio      VARCHAR(15) CHECK (estado_anuncio IN ('ACTIVO', 'COMPLETADO', 'PAUSADO')),
    fecha_publicacion   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_cierre        TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_transacciones_activo_id ON transacciones_temporales(activo_id);

-- 3. Historial Eventos Urbanos
CREATE TABLE IF NOT EXISTS historial_eventos_urbanos (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    geom_evento                 GEOMETRY(Point, 4326) NOT NULL,
    tipo_evento                 VARCHAR(50),
    descripcion                 TEXT,
    restriccion_altura_pisos    INT DEFAULT NULL,
    fecha_inicio                DATE,
    fecha_fin                   DATE,
    impacto_plusvalia_estimado  NUMERIC(4,2)
);
CREATE INDEX IF NOT EXISTS idx_eventos_geom ON historial_eventos_urbanos USING GIST(geom_evento);

-- 4. Ficha Técnica de Mantenimiento
CREATE TABLE IF NOT EXISTS ficha_tecnica_mantenimiento (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activo_id                       UUID REFERENCES activos_inmutables(id) ON DELETE CASCADE,
    tipo_tuberia                    VARCHAR(50),
    año_construccion                INT,
    tipo_estructura                 VARCHAR(50),
    calidad_acabados                VARCHAR(30),
    ultimo_mantenimiento_cisterna       DATE,
    ultima_impermeabilizacion_techo     DATE,
    ultima_pintura_fachada              DATE,
    ultimo_cambio_cableado_electrico    DATE,
    monto_invertido_mejoras         NUMERIC(12,2) DEFAULT 0.00,
    descripcion_mejoras             TEXT,
    updated_at                      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ficha_activo ON ficha_tecnica_mantenimiento(activo_id);

-- Verificación
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'activos_inmutables','transacciones_temporales',
    'historial_eventos_urbanos','ficha_tecnica_mantenimiento'
  );
