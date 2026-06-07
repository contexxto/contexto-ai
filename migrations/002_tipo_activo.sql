-- ============================================================
-- Migration 002: columna tipo_activo en activos_inmutables
-- Aplicada: 2026-06-07 (produccion Supabase)
-- ============================================================

-- 1. Añadir columna con default
ALTER TABLE activos_inmutables
ADD COLUMN IF NOT EXISTS tipo_activo TEXT NOT NULL DEFAULT 'Departamento';

-- 2. Constraint de validacion
ALTER TABLE activos_inmutables
DROP CONSTRAINT IF EXISTS ck_tipo_activo;

ALTER TABLE activos_inmutables
ADD CONSTRAINT ck_tipo_activo
CHECK (tipo_activo IN ('Departamento', 'Casa', 'Local Comercial', 'Oficina', 'Quinta'));

-- 3. Clasificacion por sector (idempotente)
UPDATE activos_inmutables SET tipo_activo = 'Local Comercial'
WHERE direccion_estandarizada ILIKE ANY(ARRAY[
    '%Centro Historico%','%Garcia Moreno%','%Venezuela%Chile%',
    '%Mejia%Guayaquil%','%Benalcazar%','%24 de Mayo%',
    '%El Camal%','%Maldonado%Cusubamba%'
]) AND tipo_activo = 'Departamento';

UPDATE activos_inmutables SET tipo_activo = 'Quinta'
WHERE direccion_estandarizada ILIKE ANY(ARRAY[
    '%Interocean%','%Chimborazo%Bolivar%','%El Pilar%'
]) AND tipo_activo = 'Departamento';

UPDATE activos_inmutables SET tipo_activo = 'Casa'
WHERE direccion_estandarizada ILIKE ANY(ARRAY[
    '%Pampite%','%El Batan%','%Condado%','%Cotocollao%',
    '%Nicolas Arteta%','%Antonio Jose de Sucre%',
    '%Solanda%','%Villa Flora%','%Chimbacalle%'
]) AND tipo_activo = 'Departamento';

UPDATE activos_inmutables SET tipo_activo = 'Oficina'
WHERE direccion_estandarizada ILIKE ANY(ARRAY[
    '%Colon%12 de Octubre%','%12 de Octubre%Cordero%',
    '%Gonzalez Suarez%Alemania%','%Juan Pablo Sainz%'
]) AND tipo_activo = 'Departamento';

-- 4. Verificacion
SELECT tipo_activo, COUNT(*) AS cantidad
FROM activos_inmutables
GROUP BY tipo_activo ORDER BY cantidad DESC;
