-- ============================================================
-- Contexto AI V2 — Migration: columna tipo_activo
-- Clasificacion por logica de sector + caracteristicas del activo
-- ============================================================

-- 1. Añadir columna
ALTER TABLE activos_inmutables
ADD COLUMN IF NOT EXISTS tipo_activo TEXT DEFAULT 'Departamento';

-- 2. Clasificar por sector y caracteristicas
-- Centro Historico: patrimonio → uso mixto (residencial/comercial)
UPDATE activos_inmutables SET tipo_activo = 'Local Comercial'
WHERE direccion_estandarizada ILIKE '%Centro Historico%'
   OR direccion_estandarizada ILIKE '%Garcia Moreno%'
   OR direccion_estandarizada ILIKE '%Venezuela%'
   OR direccion_estandarizada ILIKE '%Mejia%'
   OR direccion_estandarizada ILIKE '%Benalcazar%'
   OR direccion_estandarizada ILIKE '%24 de Mayo%';

-- Cumbaya baja densidad → Quintas / Casas
UPDATE activos_inmutables SET tipo_activo = 'Quinta'
WHERE direccion_estandarizada ILIKE '%Interocean%'
   OR direccion_estandarizada ILIKE '%Chimborazo%Bolivar%'
   OR direccion_estandarizada ILIKE '%El Pilar%';

UPDATE activos_inmutables SET tipo_activo = 'Casa'
WHERE direccion_estandarizada ILIKE '%Pampite%'
   OR direccion_estandarizada ILIKE '%El Batan%'
   OR direccion_estandarizada ILIKE '%Francisco de Orellana%Pampite%';

-- Norte Condado: casas populares
UPDATE activos_inmutables SET tipo_activo = 'Casa'
WHERE direccion_estandarizada ILIKE '%Condado%'
   OR direccion_estandarizada ILIKE '%Cotocollao%'
   OR direccion_estandarizada ILIKE '%Nicolas Arteta%'
   OR direccion_estandarizada ILIKE '%Antonio Jose de Sucre%';

-- Sur: uso mixto residencial
UPDATE activos_inmutables SET tipo_activo = 'Casa'
WHERE direccion_estandarizada ILIKE '%Solanda%'
   OR direccion_estandarizada ILIKE '%Villa Flora%'
   OR direccion_estandarizada ILIKE '%Chimbacalle%';

UPDATE activos_inmutables SET tipo_activo = 'Local Comercial'
WHERE direccion_estandarizada ILIKE '%El Camal%'
   OR direccion_estandarizada ILIKE '%Maldonado%Cusubamba%';

-- Gonzalez Suarez / Mariscal: oficinas y departamentos premium
UPDATE activos_inmutables SET tipo_activo = 'Oficina'
WHERE direccion_estandarizada ILIKE '%Colon%12 de Octubre%'
   OR direccion_estandarizada ILIKE '%12 de Octubre%Cordero%'
   OR direccion_estandarizada ILIKE '%Gonzalez Suarez%Alemania%'
   OR direccion_estandarizada ILIKE '%Juan Pablo Sainz%';

-- La Carolina y resto: Departamento (default ya aplicado, pero explicitamos)
UPDATE activos_inmutables SET tipo_activo = 'Departamento'
WHERE tipo_activo = 'Departamento';  -- no-op, confirma el default

-- 3. Verificacion
SELECT tipo_activo, COUNT(*) AS cantidad
FROM activos_inmutables
GROUP BY tipo_activo
ORDER BY cantidad DESC;
