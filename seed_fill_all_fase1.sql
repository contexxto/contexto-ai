-- ============================================================
-- Contexto AI — Rellenar TODOS los activos con datos faltantes
-- Pega en Supabase SQL Editor y ejecuta (las 3 partes de una vez).
--
-- Rellena, por tipo de activo, lo que falte en cada inmueble:
--   1) caracteristicas (specs: dorm/baños/m²…) — solo donde es NULL
--   2) imagen_url (foto canónica verificada) — solo donde es NULL
--   3) transaccion (tipo_operacion + precio realista) — solo si no existe
--
-- Todo es DETERMINISTA (hash del id) e IDEMPOTENTE: re-ejecutar no
-- duplica ni sobreescribe. Fotos verificadas visualmente por tipo.
-- ============================================================


-- ─────────────────────────────────────────────────────────────
-- 1) SPECS (caracteristicas) — solo activos sin specs
--    Valores varían por tipo y por hash del id (no quedan idénticos).
-- ─────────────────────────────────────────────────────────────
WITH h AS (
  SELECT
    id,
    COALESCE(tipo_activo, 'Departamento')          AS tipo,
    COALESCE(walk_score, 80)                        AS ws,
    abs(hashtext(id::text || 'a')::bigint)          AS h1,
    abs(hashtext(id::text || 'b')::bigint)          AS h2,
    abs(hashtext(id::text || 'c')::bigint)          AS h3,
    abs(hashtext(id::text || 'd')::bigint)          AS h4,
    abs(hashtext(id::text || 'e')::bigint)          AS h5,
    abs(hashtext(id::text || 'f')::bigint)          AS h6,
    abs(hashtext(id::text || 'g')::bigint)          AS h7
  FROM activos_inmutables
  WHERE caracteristicas IS NULL
)
UPDATE activos_inmutables a
SET caracteristicas = CASE
  WHEN h.tipo = 'Departamento' THEN jsonb_build_object(
    'num_dormitorios', 1 + mod(h.h1, 3),
    'num_banos',       1 + mod(h.h2, 2),
    'area_total_m2',   50 + mod(h.h3, 80),
    'parqueaderos',    mod(h.h4, 3),
    'piso',            1 + mod(h.h5, 12),
    'amoblado',        (mod(h.h6, 2) = 0),
    'notas',           'Departamento con buena distribución, cerca de servicios y transporte.'
  )
  WHEN h.tipo = 'Oficina' THEN jsonb_build_object(
    'area_total_m2',   35 + mod(h.h3, 165),
    'num_banos',       1 + mod(h.h2, 2),
    'parqueaderos',    1 + mod(h.h4, 3),
    'piso',            1 + mod(h.h5, 14),
    'privados',        1 + mod(h.h1, 5),
    'amoblado',        (mod(h.h6, 2) = 0),
    'notas',           'Oficina en edificio corporativo, lista para ocupación inmediata.'
  )
  WHEN h.tipo = 'Local Comercial' THEN jsonb_build_object(
    'area_total_m2',   25 + mod(h.h3, 125),
    'num_banos',       1,
    'frente_calle',    true,
    'planta_baja',     (mod(h.h6, 3) < 2),
    'parqueaderos',    mod(h.h4, 2),
    'notas',           'Local comercial con alto flujo peatonal y excelente visibilidad.'
  )
  ELSE jsonb_build_object(  -- Casa (y cualquier otro tipo)
    'num_dormitorios', 3 + mod(h.h1, 3),
    'num_banos',       2 + mod(h.h2, 3),
    'area_total_m2',   120 + mod(h.h3, 200),
    'area_terreno_m2', 170 + mod(h.h3, 200) + mod(h.h7, 200),
    'parqueaderos',    1 + mod(h.h4, 3),
    'pisos',           2 + mod(h.h5, 2),
    'patio',           true,
    'notas',           'Casa amplia con áreas verdes, ideal para familia.'
  )
END
FROM h
WHERE a.id = h.id;


-- ─────────────────────────────────────────────────────────────
-- 2) FOTO (imagen_url) — solo activos sin foto
--    Pool curado y VERIFICADO VISUALMENTE por tipo. Sin fotos
--    erróneas (nada de comida, salas residenciales ni cabañas).
-- ─────────────────────────────────────────────────────────────
WITH tipo_pools(tipo, pool) AS (
  VALUES
   ('Departamento', ARRAY[
      'photo-1502672260266-1c1ef2d93688','photo-1522708323590-d24dbb6b0267',
      'photo-1560448204-e02f11c3d0e2','photo-1493809842364-78817add7ffb',
      'photo-1484154218962-a197022b5858','photo-1554995207-c18c203602cb',
      'photo-1545324418-cc1a3fa10c00','photo-1556912173-3bb406ef7e77',
      'photo-1505691938895-1758d7feb511','photo-1586023492125-27b2c045efd7']::text[]),
   ('Oficina', ARRAY[
      'photo-1497366754035-f200968a6e72','photo-1524758631624-e2822e304c36',
      'photo-1497215728101-856f4ea42174','photo-1604328698692-f76ea9498e76',
      'photo-1431540015161-0bf868a2d407','photo-1497366811353-6870744d04b2',
      'photo-1462826303086-329426d1aef5']::text[]),
   ('Local Comercial', ARRAY[
      'photo-1441986300917-64674bd600d8','photo-1604719312566-8912e9227c6a',
      'photo-1567521464027-f127ff144326','photo-1604335399105-a0c585fd81a1',
      'photo-1534723452862-4c874018d66d','photo-1542838132-92c53300491e',
      'photo-1578916171728-46686eac8d58']::text[]),
   ('Casa', ARRAY[
      'photo-1564013799919-ab600027ffc6','photo-1570129477492-45c003edd2be',
      'photo-1572120360610-d971b9d7767c','photo-1605276374104-dee2a0ed3cd6',
      'photo-1583608205776-bfd35f0d9f83','photo-1576941089067-2de3c901e126',
      'photo-1599809275671-b5942cabc7a2','photo-1600585154340-be6161a56a0c',
      'photo-1600596542815-ffad4c1539a9']::text[])
)
UPDATE activos_inmutables a
SET imagen_url =
      'https://images.unsplash.com/'
   || tp.pool[ (1 + mod( abs(hashtext(a.id::text || 'img')::bigint), array_length(tp.pool, 1) ))::int ]
   || '?auto=format&fit=crop&w=600&q=80'
FROM tipo_pools tp
WHERE a.imagen_url IS NULL
  AND tp.tipo = CASE WHEN a.tipo_activo IN ('Departamento','Oficina','Local Comercial','Casa')
                     THEN a.tipo_activo ELSE 'Departamento' END;


-- ─────────────────────────────────────────────────────────────
-- 3) TRANSACCIÓN (precio + operación) — solo activos sin transacción
--    Precio = área (de specs) × $/m² por tipo × jitter × premium walk.
--    VENTA redondeada a centenas; ARRIENDO ≈ venta/165, a decenas.
-- ─────────────────────────────────────────────────────────────
INSERT INTO transacciones_temporales (activo_id, tipo_operacion, precio, estado_anuncio, fecha_publicacion)
SELECT a.id, calc.tipo, calc.precio, 'ACTIVO', NOW()
FROM activos_inmutables a
CROSS JOIN LATERAL (
  SELECT
    COALESCE((a.caracteristicas->>'area_total_m2')::numeric, 70)        AS area,
    CASE COALESCE(a.tipo_activo,'Departamento')
      WHEN 'Departamento'    THEN 1400
      WHEN 'Oficina'         THEN 1300
      WHEN 'Local Comercial' THEN 1700
      ELSE 1150 END                                                     AS ppm2,
    CASE WHEN mod(abs(hashtext(a.id::text || 'op')::bigint), 100) <
              CASE COALESCE(a.tipo_activo,'Departamento')
                WHEN 'Departamento'    THEN 60
                WHEN 'Oficina'         THEN 50
                WHEN 'Local Comercial' THEN 55
                ELSE 30 END
         THEN 'ARRIENDO' ELSE 'VENTA' END                              AS tipo,
    0.85 + mod(abs(hashtext(a.id::text || 'jit')::bigint), 30) / 100.0  AS jit,
    1 + (COALESCE(a.walk_score,80) - 80) * 0.004                        AS wf
) base
CROSS JOIN LATERAL (
  SELECT
    base.tipo,
    CASE WHEN base.tipo = 'VENTA'
      THEN round( base.area * base.ppm2 * base.jit * base.wf, -2)
      ELSE round( (base.area * base.ppm2 * base.jit * base.wf) / 165.0 / 10.0) * 10
    END AS precio
) calc
WHERE NOT EXISTS (
  SELECT 1 FROM transacciones_temporales t WHERE t.activo_id = a.id
);


-- ─────────────────────────────────────────────────────────────
-- 4) VERIFICACIÓN — debe devolver 0 filas (no quedan datos faltantes)
-- ─────────────────────────────────────────────────────────────
SELECT
  a.id,
  a.direccion_estandarizada AS direccion,
  a.tipo_activo,
  a.walk_score,
  CASE WHEN a.imagen_url IS NULL THEN '❌' ELSE '✅' END     AS foto,
  CASE WHEN a.caracteristicas IS NULL THEN '❌' ELSE '✅' END AS specs,
  CASE WHEN EXISTS (SELECT 1 FROM transacciones_temporales t WHERE t.activo_id = a.id)
       THEN '✅' ELSE '❌' END                                AS transaccion
FROM activos_inmutables a
WHERE a.imagen_url IS NULL
   OR a.caracteristicas IS NULL
   OR NOT EXISTS (SELECT 1 FROM transacciones_temporales t WHERE t.activo_id = a.id);
