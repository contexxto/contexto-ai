-- ============================================================
-- Migration 021: `iglesia` y `seguridad` entran a la capa propia
--
--   POR QUÉ: eran las dos únicas categorías que el branch "ruta a X" seguía mandando
--   a Google, y son justo las que Google responde PEOR en Quito. Verificado en vivo
--   2026-07-27 con clave real: "iglesia más cercana" devolvió *"Wilson Maldonado"* y
--   "UPC más cercano" devolvió *"ABOGADOS EN LINES"*. Basura en ambos casos.
--
--   OSM sí las tiene (medido en el bbox de Quito, 2026-07-27):
--     amenity=place_of_worship  291 (274 con nombre)
--     amenity=police            144 (127 con nombre)
--
--   Con esto el branch "ruta a X" deja de llamar a Google POR COMPLETO.
--
--   NOTA FAIR HOUSING (canon Contexto): `seguridad` es el PUESTO DE POLICÍA como
--   servicio físico —igual que un hospital o un colegio—, NO una medida de qué tan
--   seguro es un barrio. El canon prohíbe crime maps y "seguridad social del barrio";
--   un POI de UPC con su dirección es un hecho verificable, no un juicio sobre la zona
--   ni sobre quien vive en ella. El rótulo se ajustó en el mismo commit para que
--   nombre el SERVICIO ("UPC") y no la cualidad ("seguridad"), porque con dato bueno
--   la lectura ambigua deja de ser inofensiva.
-- ============================================================

ALTER TABLE pois_propios DROP CONSTRAINT IF EXISTS ck_pois_categoria;
ALTER TABLE pois_propios ADD  CONSTRAINT ck_pois_categoria
    CHECK (categoria IN ('salud','farmacia','supermercado','educacion',
                         'parque','centro_comercial','transporte',
                         'iglesia','seguridad'));

-- Verificación (debe listar las 9 y, tras la ingesta, incluir iglesia y seguridad)
SELECT categoria, count(*) FROM pois_propios GROUP BY 1 ORDER BY 2 DESC;

-- ============================================================
-- ROLLBACK (solo posible si NO hay filas de esas dos categorías):
--   DELETE FROM pois_propios WHERE categoria IN ('iglesia','seguridad');
--   ALTER TABLE pois_propios DROP CONSTRAINT IF EXISTS ck_pois_categoria;
--   ALTER TABLE pois_propios ADD  CONSTRAINT ck_pois_categoria
--       CHECK (categoria IN ('salud','farmacia','supermercado','educacion',
--                            'parque','centro_comercial','transporte'));
-- ============================================================
