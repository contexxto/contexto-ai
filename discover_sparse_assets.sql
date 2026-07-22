-- ============================================================
-- Contexto AI — Descubrimiento de activos con datos faltantes
-- Ejecuta en Supabase SQL Editor y comparte el resultado.
-- ============================================================

SELECT
  a.id,
  a.direccion_estandarizada                                  AS direccion,
  a.walk_score,
  COALESCE(a.tipo_activo, '❌ sin tipo')                     AS tipo,
  CASE WHEN a.imagen_url IS NULL THEN '❌' ELSE '✅' END     AS foto,
  CASE WHEN a.caracteristicas IS NULL THEN '❌' ELSE '✅' END AS specs,
  COALESCE(
    (SELECT tipo_operacion::text
     FROM transacciones_temporales tt
     WHERE tt.activo_id = a.id
     ORDER BY fecha_publicacion DESC LIMIT 1),
    '❌ sin precio'
  )                                                          AS transaccion,
  (SELECT precio::text
   FROM transacciones_temporales tt
   WHERE tt.activo_id = a.id
   ORDER BY fecha_publicacion DESC LIMIT 1)                  AS precio
FROM activos_inmutables a
WHERE
  a.imagen_url IS NULL
  OR a.caracteristicas IS NULL
  OR NOT EXISTS (
      SELECT 1 FROM transacciones_temporales tt
      WHERE tt.activo_id = a.id
  )
ORDER BY a.walk_score DESC NULLS LAST;
