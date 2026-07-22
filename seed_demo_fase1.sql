-- ============================================================
-- Contexto AI — Seed Demo Fase 1: Carrusel de tarjetas rico
-- Pega esto en Supabase SQL Editor y ejecuta.
-- Enriquece 5 activos existentes en La Carolina / Shyris con:
--   · caracteristicas (dormitorios, baños, m², foto)
--   · imagen_url (foto canónica)
--   · transaccion (precio + tipo operación)
-- ============================================================

-- ─────────────────────────────────────────────────────────────
-- 1. Av. República del Salvador — 2 dorm · 1 baño · 68 m² · walk 95
-- ─────────────────────────────────────────────────────────────
UPDATE activos_inmutables
SET
  tipo_activo = 'Departamento',
  imagen_url  = 'https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=600&q=80',
  caracteristicas = '{
    "num_dormitorios": 2,
    "num_banos": 1,
    "area_total_m2": 68,
    "amoblado": false,
    "parqueaderos": 1,
    "piso": 3,
    "notas": "Departamento luminoso frente al Parque La Carolina. Cocina equipada, cuarto de lavado."
  }'::jsonb
WHERE id = '53160f0a-95f8-4a3d-a735-c2f82608d1cf';

INSERT INTO transacciones_temporales (activo_id, tipo_operacion, precio, estado_anuncio, fecha_publicacion)
VALUES ('53160f0a-95f8-4a3d-a735-c2f82608d1cf', 'ARRIENDO', 380.00, 'ACTIVO', NOW())
ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────
-- 2. Av. Amazonas y Atahualpa — 3 dorm · 2 baños · 120 m² · walk 88
-- ─────────────────────────────────────────────────────────────
UPDATE activos_inmutables
SET
  tipo_activo = 'Departamento',
  imagen_url  = 'https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=600&q=80',
  caracteristicas = '{
    "num_dormitorios": 3,
    "num_banos": 2,
    "area_total_m2": 120,
    "amoblado": false,
    "parqueaderos": 2,
    "piso": 8,
    "alicuota_mensual": 85,
    "notas": "Suite master con vestidor. Vista despejada. Edificio con guardianía 24h y sala comunal."
  }'::jsonb
WHERE id = '6c057dd0-8447-4a3b-94be-c38459845e3b';

INSERT INTO transacciones_temporales (activo_id, tipo_operacion, precio, estado_anuncio, fecha_publicacion)
VALUES ('6c057dd0-8447-4a3b-94be-c38459845e3b', 'VENTA', 148000.00, 'ACTIVO', NOW())
ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────
-- 3. Calle Los Shyris y Portugal — 1 dorm · 1 baño · 52 m² · walk 91
-- ─────────────────────────────────────────────────────────────
UPDATE activos_inmutables
SET
  tipo_activo = 'Departamento',
  imagen_url  = 'https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=600&q=80',
  caracteristicas = '{
    "num_dormitorios": 1,
    "num_banos": 1,
    "area_total_m2": 52,
    "amoblado": true,
    "parqueaderos": 0,
    "piso": 2,
    "notas": "Estudio amoblado, ideal para profesionales. A 3 min caminando del CC Iñaquito y Metro."
  }'::jsonb
WHERE id = '449acb53-3d7b-4ad6-9a14-3bcb0b645edb';

INSERT INTO transacciones_temporales (activo_id, tipo_operacion, precio, estado_anuncio, fecha_publicacion)
VALUES ('449acb53-3d7b-4ad6-9a14-3bcb0b645edb', 'ARRIENDO', 290.00, 'ACTIVO', NOW())
ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────
-- 4. Av. 6 de Diciembre y Bosmediano — 2 dorm · 2 baños · 95 m² · walk 92
-- ─────────────────────────────────────────────────────────────
UPDATE activos_inmutables
SET
  tipo_activo = 'Departamento',
  imagen_url  = 'https://images.unsplash.com/photo-1512917774080-9991f1c4c750?auto=format&fit=crop&w=600&q=80',
  caracteristicas = '{
    "num_dormitorios": 2,
    "num_banos": 2,
    "area_total_m2": 95,
    "amoblado": false,
    "parqueaderos": 1,
    "piso": 5,
    "alicuota_mensual": 60,
    "notas": "Amplio balcón con vista a la montaña. Dos parqueaderos opcionales. Cerca de colegios internacionales."
  }'::jsonb
WHERE id = '1ac8d773-29db-496f-b7c5-9b7c3dfd8304';

INSERT INTO transacciones_temporales (activo_id, tipo_operacion, precio, estado_anuncio, fecha_publicacion)
VALUES ('1ac8d773-29db-496f-b7c5-9b7c3dfd8304', 'VENTA', 185000.00, 'ACTIVO', NOW())
ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────
-- 5. Av. De Los Shyris y Suecia — 3 dorm · 2 baños · 110 m² · walk 94
-- ─────────────────────────────────────────────────────────────
UPDATE activos_inmutables
SET
  tipo_activo = 'Departamento',
  imagen_url  = 'https://images.unsplash.com/photo-1493809842364-78817add7ffb?auto=format&fit=crop&w=600&q=80',
  caracteristicas = '{
    "num_dormitorios": 3,
    "num_banos": 2,
    "area_total_m2": 110,
    "amoblado": false,
    "parqueaderos": 1,
    "piso": 4,
    "acepta_mascotas": true,
    "notas": "A pasos del Parque La Carolina. Edificio boutique de 6 pisos. Acepta mascotas medianas."
  }'::jsonb
WHERE id = '9e989f59-3da0-462e-a4fe-c34782bb799b';

INSERT INTO transacciones_temporales (activo_id, tipo_operacion, precio, estado_anuncio, fecha_publicacion)
VALUES ('9e989f59-3da0-462e-a4fe-c34782bb799b', 'ARRIENDO', 550.00, 'ACTIVO', NOW())
ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────
-- Verificación rápida
-- ─────────────────────────────────────────────────────────────
SELECT
  a.direccion_estandarizada,
  a.walk_score,
  a.tipo_activo,
  (a.caracteristicas->>'num_dormitorios')::int AS dorm,
  (a.caracteristicas->>'num_banos')::int       AS banos,
  (a.caracteristicas->>'area_total_m2')::int   AS m2,
  t.tipo_operacion,
  t.precio
FROM activos_inmutables a
LEFT JOIN LATERAL (
  SELECT tipo_operacion, precio
  FROM transacciones_temporales tt
  WHERE tt.activo_id = a.id
  ORDER BY tt.fecha_publicacion DESC LIMIT 1
) t ON true
WHERE a.id IN (
  '53160f0a-95f8-4a3d-a735-c2f82608d1cf',
  '6c057dd0-8447-4a3b-94be-c38459845e3b',
  '449acb53-3d7b-4ad6-9a14-3bcb0b645edb',
  '1ac8d773-29db-496f-b7c5-9b7c3dfd8304',
  '9e989f59-3da0-462e-a4fe-c34782bb799b'
)
ORDER BY a.walk_score DESC;
