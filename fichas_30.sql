-- ============================================================
-- Contexto AI V2 — Fichas tecnicas para 30 activos sin ficha
-- Inferencia geoespacial por sector
-- Pega en Supabase SQL Editor y ejecuta
-- ============================================================

INSERT INTO ficha_tecnica_mantenimiento
  (id, activo_id, tipo_tuberia, "año_construccion", tipo_estructura,
   calidad_acabados, ultimo_mantenimiento_cisterna,
   ultima_impermeabilizacion_techo, ultima_pintura_fachada,
   ultimo_cambio_cableado_electrico, monto_invertido_mejoras)
SELECT
  gen_random_uuid(),
  a.id,
  v.tuberia,
  v.anno::int,
  v.estructura,
  v.acabados,
  v.cisterna::date,
  v.techo::date,
  v.fachada::date,
  v.cableado::date,
  v.monto::numeric
FROM activos_inmutables a
JOIN (VALUES
  ('Av. 6 de Diciembre N36-109 y Bosmediano, La Carolina, Quito', 'Termofusion', '2012', 'Estructura Metalica', 'Porcelanato Estandar', '2025-04-24', '2025-01-15', '2025-08-26', '2020-08-21', 73540),
  ('Calle Portugal E12-76 y 6 de Diciembre, Quito', 'Termofusion', '2021', 'Estructura Metalica', 'Porcelanato Estandar', '2025-11-08', '2025-03-03', '2025-04-29', '2023-02-16', 58118),
  ('Av. Eloy Alfaro N34-451 y Portugal, Quito', 'Termofusion', '2020', 'Hormigon Armado', 'Marmol / Granito', '2024-10-05', '2024-10-24', '2024-09-05', '2021-02-16', 43231),
  ('Calle Catalina Aldaz N34-208 y Portugal, Quito', 'Termofusion', '2014', 'Estructura Metalica', 'Porcelanato Alto Trafico', '2025-02-27', '2024-12-29', '2025-05-02', '2022-07-18', 31698),
  ('Av. De Los Shyris N35-174 y Suecia, Quito', 'Termofusion', '2018', 'Hormigon Armado', 'Porcelanato Alto Trafico', '2024-12-21', '2023-09-27', '2025-03-13', '2024-03-10', 72823),
  ('Av. Gonzalez Suarez N27-160 y Alemania, Quito', 'PVC Presion', '2009', 'Mamposteria Confinada', 'Porcelanato Estandar', '2024-12-27', '2021-05-03', '2023-10-15', '2016-06-30', 33700),
  ('Calle Alemania E12-34 y Gonzalez Suarez, Quito', 'Termofusion', '1998', 'Mamposteria Confinada', 'Ceramica Estandar', '2024-02-26', '2020-02-05', '2023-10-23', '2022-07-16', 25256),
  ('Av. Colon E4-50 y 12 de Octubre, La Mariscal, Quito', 'Cobre/PVC', '2004', 'Hormigon Armado', 'Porcelanato Estandar', '2023-05-21', '2023-07-09', '2023-05-10', '2019-06-13', 23730),
  ('Av. Interoceanica Km 13.5, Urbanizacion El Pilar, Cumbaya', 'PVC Presion', '2022', 'Hormigon Armado', 'Marmol / Granito', '2025-06-16', '2023-12-08', '2025-04-02', '2023-07-08', 55294),
  ('Calle Francisco de Orellana y Av. Pampite, Cumbaya, Quito', 'PVC Presion', '2016', 'Hormigon Armado', 'Marmol / Granito', '2025-01-10', '2025-04-10', '2025-04-18', '2024-04-02', 45673),
  ('Av. Pampite N5-23 y De Los Conquistadores, Cumbaya', 'PVC Presion', '2016', 'Hormigon Armado', 'Porcelanato Estandar', '2025-01-20', '2024-11-01', '2024-07-15', '2022-03-19', 67129),
  ('Calle Chimborazo y Av. Simon Bolivar, Cumbaya, Quito', 'PVC Presion', '2014', 'Estructura Metalica', 'Porcelanato Estandar', '2025-03-31', '2023-11-10', '2025-03-14', '2021-02-25', 53077),
  ('Av. Robles y Francisco de Orellana, El Batan, Cumbaya', 'PVC Presion', '2017', 'Hormigon Armado', 'Porcelanato Estandar', '2024-07-05', '2024-01-18', '2025-09-06', '2024-03-02', 32185),
  ('Av. Diego de Vasquez y Condado Shopping, Norte, Quito', 'PVC Presion', '2013', 'Mamposteria Confinada', 'Porcelanato Estandar', '2022-02-01', '2023-09-20', '2023-04-10', '2019-02-25', 27526),
  ('Calle Antonio Jose de Sucre N78-24, El Condado, Quito', 'Cobre/PVC', '2011', 'Hormigon Armado', 'Ceramica Estandar', '2021-08-13', '2023-02-23', '2021-08-10', '2017-05-30', 32604),
  ('Av. Occidental y De La Prensa, Cotocollao, Quito', 'Cobre/PVC', '2015', 'Hormigon Armado', 'Ceramica Estandar', '2023-10-14', '2019-07-23', '2024-07-18', '2018-05-06', 8106),
  ('Calle Nicolas Arteta y Marchena, Cotocollao, Quito', 'Cobre/PVC', '2011', 'Mamposteria Confinada', 'Ceramica Estandar', '2021-12-04', '2021-01-31', '2021-11-06', '2017-09-27', 27954),
  ('Av. Diego de Vasquez y Mariana de Jesus, Norte, Quito', 'PVC Presion', '2005', 'Hormigon Armado', 'Ceramica Estandar', '2022-05-29', '2018-06-26', '2025-06-05', '2016-09-18', 18621),
  ('Calle Garcia Moreno N2-60 y Sucre, Centro Historico, Quito', 'Cobre/PVC', '1968', 'Mamposteria Simple', 'Mortero / Pintura', '2020-12-25', '2020-09-30', '2025-02-08', '2015-01-12', 52182),
  ('Calle Venezuela y Chile, Centro Historico, Quito', 'Hierro Galvanizado', '1970', 'Mamposteria Confinada', 'Ceramica Estandar', '2018-06-17', '2014-11-05', '2024-09-22', '2017-07-22', 58237),
  ('Av. 24 de Mayo y Cuenca, La Loma, Quito', 'Cobre/PVC', '1985', 'Mamposteria Simple', 'Mortero / Pintura', '2018-07-07', '2016-08-18', '2023-01-22', '2015-09-07', 50343),
  ('Calle Mejia N4-30 y Guayaquil, Centro Historico, Quito', 'Hierro Galvanizado', '1977', 'Mamposteria Confinada', 'Mortero / Pintura', '2019-07-09', '2017-08-18', '2022-11-25', '2017-09-20', 31246),
  ('Calle Benalcazar N2-12 y Bolivar, Quito', 'Hierro Galvanizado', '1970', 'Mamposteria Confinada', 'Ceramica Estandar', '2017-11-01', '2017-03-22', '2024-02-21', '2015-06-30', 15471),
  ('Av. Morona N34-28 y El Camal, Sur, Quito', 'PVC Presion', '2009', 'Mamposteria Confinada', 'Ceramica Estandar', '2024-09-03', '2024-01-30', '2020-08-11', '2019-09-23', 7321),
  ('Calle Manglar Alto y Av. Cardenal de la Torre, Solanda, Quito', 'PVC Presion', '2002', 'Hormigon Armado', 'Ceramica Estandar', '2023-12-13', '2018-01-11', '2022-03-14', '2018-02-17', 12962),
  ('Av. Maldonado S25-80 y Cusubamba, Sur, Quito', 'Cobre/PVC', '2010', 'Hormigon Armado', 'Ceramica Estandar', '2024-05-16', '2023-05-06', '2021-09-26', '2018-08-07', 16609),
  ('Calle Gral Enriquez y Napo, Chimbacalle, Quito', 'Cobre/PVC', '2004', 'Hormigon Armado', 'Ceramica Estandar', '2024-04-29', '2023-10-02', '2023-03-05', '2015-04-08', 16118),
  ('Av. Pedro Vicente Maldonado y Cusubamba, Villa Flora, Quito', 'PVC Presion', '2001', 'Mamposteria Confinada', 'Ceramica Estandar', '2020-05-26', '2022-11-10', '2023-01-24', '2021-05-17', 14127),
  ('Calle Juan Pablo Sainz y Gonzalez Suarez, Quito', 'PVC Presion', '1999', 'Mamposteria Confinada', 'Porcelanato Estandar', '2024-11-18', '2024-02-24', '2025-05-07', '2022-05-21', 25491),
  ('Av. 12 de Octubre N24-593 y Cordero, Quito', 'Cobre/PVC', '2005', 'Hormigon Armado', 'Porcelanato Estandar', '2024-03-26', '2019-08-02', '2023-03-08', '2022-10-10', 20789)
) AS v(dir, tuberia, anno, estructura, acabados, cisterna, techo, fachada, cableado, monto)
ON a.direccion_estandarizada ILIKE '%' || split_part(v.dir, ',', 1) || '%'
WHERE NOT EXISTS (
  SELECT 1 FROM ficha_tecnica_mantenimiento f WHERE f.activo_id = a.id
);

-- Verificacion final
SELECT COUNT(*) AS total_fichas FROM ficha_tecnica_mantenimiento;
SELECT COUNT(*) AS activos_sin_ficha
FROM activos_inmutables a
WHERE NOT EXISTS (SELECT 1 FROM ficha_tecnica_mantenimiento f WHERE f.activo_id = a.id);