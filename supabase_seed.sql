-- ============================================================
-- Contexto AI V2 — Seed Data: 35 activos en 6 sectores de Quito
-- Pega esto en Supabase SQL Editor y ejecuta
-- ============================================================

INSERT INTO activos_inmutables
  (id, geom, direccion_estandarizada, piso_altura, walk_score,
   score_ruido_predictivo, volumen_trafico_historico,
   densidad_poblacional_pico, porcentaje_cobertura_vegetal)
VALUES
  ('53160f0a-95f8-4a3d-a735-c2f82608d1cf', ST_SetSRID(ST_MakePoint(-78.482,-0.181),4326), 'Av. Republica del Salvador N34-183, La Carolina, Quito', 8, 95, 'BAJO', 1200, 8500, 42.3),
  ('6c057dd0-8447-4a3b-94be-c38459845e3b', ST_SetSRID(ST_MakePoint(-78.4865,-0.1845),4326), 'Av. Amazonas N35-17 y Atahualpa, La Carolina, Quito', 12, 88, 'ALTO', 18400, 12000, 14.7),
  ('449acb53-3d7b-4ad6-9a14-3bcb0b645edb', ST_SetSRID(ST_MakePoint(-78.485,-0.1798),4326), 'Calle Los Shyris N35-61 y Portugal, Quito', 5, 91, 'MEDIO', 6300, 7200, 28.1),
  ('0cb128c9-177d-44a5-81d0-0c5667d88641', ST_SetSRID(ST_MakePoint(-78.4802,-0.1835),4326), 'Av. Naciones Unidas E10-44 y Amazonas, Quito', 15, 93, 'MEDIO', 9100, 11500, 22.5),
  ('8b040ab7-cdb2-4da1-ada7-0769e4142b74', ST_SetSRID(ST_MakePoint(-78.483,-0.1778),4326), 'Calle Isla Fernandina N44-28 y Los Shyris, Quito', 4, 87, 'BAJO', 980, 4800, 51.0),
  ('1ac8d773-29db-496f-b7c5-9b7c3dfd8304', ST_SetSRID(ST_MakePoint(-78.4825,-0.1795),4326), 'Av. 6 de Diciembre N36-109 y Bosmediano, La Carolina, Quito', 10, 92, 'MEDIO', 7800, 9200, 31.5),
  ('2c80ad8d-d19a-4ab4-bb2b-ea35009cb092', ST_SetSRID(ST_MakePoint(-78.4835,-0.1815),4326), 'Calle Portugal E12-76 y 6 de Diciembre, Quito', 6, 89, 'MEDIO', 5400, 7800, 26.8),
  ('5e15ff0e-ed4c-4b82-9f0e-c0bc78b6364a', ST_SetSRID(ST_MakePoint(-78.4855,-0.1855),4326), 'Av. Eloy Alfaro N34-451 y Portugal, Quito', 14, 90, 'ALTO', 14200, 10500, 18.2),
  ('dab0167f-b596-46ea-b91a-0e23cb749c09', ST_SetSRID(ST_MakePoint(-78.486,-0.18),4326), 'Calle Catalina Aldaz N34-208 y Portugal, Quito', 4, 86, 'BAJO', 1450, 5600, 39.4),
  ('9e989f59-3da0-462e-a4fe-c34782bb799b', ST_SetSRID(ST_MakePoint(-78.4872,-0.1822),4326), 'Av. De Los Shyris N35-174 y Suecia, Quito', 8, 94, 'MEDIO', 9100, 11200, 24.7),
  ('b1810dd2-3e8c-4bc3-a27d-f80efde43cb7', ST_SetSRID(ST_MakePoint(-78.4892,-0.2045),4326), 'Av. Gonzalez Suarez N27-160 y Alemania, Quito', 18, 78, 'ALTO', 22000, 13000, 8.5),
  ('ee9ff315-5947-40bc-be09-632ace6b7991', ST_SetSRID(ST_MakePoint(-78.488,-0.2052),4326), 'Calle Alemania E12-34 y Gonzalez Suarez, Quito', 12, 75, 'MEDIO', 6800, 9800, 15.3),
  ('c99175a0-a2f7-4e1d-970f-382f840d4383', ST_SetSRID(ST_MakePoint(-78.494,-0.2101),4326), 'Av. Colon E4-50 y 12 de Octubre, La Mariscal, Quito', 7, 96, 'ALTO', 19500, 14500, 12.0),
  ('8d279afe-6bb1-40de-afb2-b15453b0d7e1', ST_SetSRID(ST_MakePoint(-78.432,-0.198),4326), 'Av. Interoceánica Km 13.5, Urbanizacion El Pilar, Cumbaya', 2, 45, 'BAJO', 3200, 2800, 65.0),
  ('cc9d3069-ceed-495b-988a-896ffb9ac03a', ST_SetSRID(ST_MakePoint(-78.434,-0.1975),4326), 'Calle Francisco de Orellana y Av. Pampite, Cumbaya, Quito', 3, 52, 'BAJO', 2400, 3200, 58.5),
  ('55638d22-1286-4a84-bbe7-4464011689bc', ST_SetSRID(ST_MakePoint(-78.4355,-0.1965),4326), 'Av. Pampite N5-23 y De Los Conquistadores, Cumbaya', 4, 58, 'MEDIO', 5600, 4500, 47.2),
  ('f5704d0a-6324-4286-901e-ba64500b2e3a', ST_SetSRID(ST_MakePoint(-78.428,-0.201),4326), 'Calle Chimborazo y Av. Simon Bolivar, Cumbaya, Quito', 2, 38, 'BAJO', 1800, 2100, 72.0),
  ('17b38047-377d-4b2e-bc6e-995218e85523', ST_SetSRID(ST_MakePoint(-78.43,-0.199),4326), 'Av. Robles y Francisco de Orellana, El Batan, Cumbaya', 6, 61, 'MEDIO', 4900, 5800, 39.8),
  ('283b6ec4-3345-46c4-bd33-6455dd013ae9', ST_SetSRID(ST_MakePoint(-78.501,-0.1022),4326), 'Av. Diego de Vasquez y Condado Shopping, Norte, Quito', 5, 70, 'MEDIO', 8900, 6800, 22.3),
  ('f9f1e79b-1950-4238-a298-7e2844393502', ST_SetSRID(ST_MakePoint(-78.5025,-0.1035),4326), 'Calle Antonio Jose de Sucre N78-24, El Condado, Quito', 3, 65, 'BAJO', 2100, 4200, 35.6),
  ('24b16bb1-5d3f-477f-b26d-c463cee17479', ST_SetSRID(ST_MakePoint(-78.508,-0.1105),4326), 'Av. Occidental y De La Prensa, Cotocollao, Quito', 4, 68, 'ALTO', 15600, 8900, 16.4),
  ('ae79a615-59b6-444b-b185-423d6c17f811', ST_SetSRID(ST_MakePoint(-78.5055,-0.1092),4326), 'Calle Nicolas Arteta y Marchena, Cotocollao, Quito', 2, 62, 'BAJO', 1350, 3600, 41.2),
  ('d87ff968-f621-4218-ac69-157fea30df1d', ST_SetSRID(ST_MakePoint(-78.504,-0.1045),4326), 'Av. Diego de Vasquez y Mariana de Jesus, Norte, Quito', 8, 74, 'MEDIO', 7200, 7100, 28.9),
  ('69287b92-9aaa-4309-a2c5-3616f3f9b316', ST_SetSRID(ST_MakePoint(-78.512,-0.2201),4326), 'Calle Garcia Moreno N2-60 y Sucre, Centro Historico, Quito', 3, 98, 'ALTO', 21000, 18000, 5.2),
  ('c25d2116-c7b0-481b-b1d8-96a3dc28a580', ST_SetSRID(ST_MakePoint(-78.5135,-0.2215),4326), 'Calle Venezuela y Chile, Centro Historico, Quito', 4, 97, 'ALTO', 19500, 17200, 6.8),
  ('f232b3cf-637d-49b0-ba95-c82fba94a1da', ST_SetSRID(ST_MakePoint(-78.515,-0.224),4326), 'Av. 24 de Mayo y Cuenca, La Loma, Quito', 2, 92, 'MEDIO', 9800, 14500, 11.0),
  ('789c1b16-d66c-45d9-8943-0f03402a7256', ST_SetSRID(ST_MakePoint(-78.5108,-0.2195),4326), 'Calle Mejia N4-30 y Guayaquil, Centro Historico, Quito', 5, 96, 'ALTO', 18200, 16800, 4.5),
  ('65e9af33-9074-48c9-9697-5d9b0fc93499', ST_SetSRID(ST_MakePoint(-78.5125,-0.2208),4326), 'Calle Benalcazar N2-12 y Bolivar, Quito', 3, 95, 'MEDIO', 11000, 15200, 7.3),
  ('77dfff9b-1e7a-4226-8770-c13515676c5f', ST_SetSRID(ST_MakePoint(-78.5205,-0.265),4326), 'Av. Morona N34-28 y El Camal, Sur, Quito', 3, 72, 'MEDIO', 7400, 9800, 14.2),
  ('c931b78e-fe79-4cb7-b7b8-f2ccf7c75a45', ST_SetSRID(ST_MakePoint(-78.528,-0.272),4326), 'Calle Manglar Alto y Av. Cardenal de la Torre, Solanda, Quito', 2, 68, 'BAJO', 2800, 7500, 19.6),
  ('c750a2b9-6f2f-4f0d-87e4-dd8369a30ded', ST_SetSRID(ST_MakePoint(-78.5245,-0.269),4326), 'Av. Maldonado S25-80 y Cusubamba, Sur, Quito', 4, 75, 'ALTO', 16800, 12200, 9.8),
  ('b1fe3dc0-2dc4-48ab-8cc5-964e34b244be', ST_SetSRID(ST_MakePoint(-78.5185,-0.2445),4326), 'Calle Gral Enriquez y Napo, Chimbacalle, Quito', 3, 80, 'MEDIO', 6200, 10400, 16.8),
  ('25a41327-18c4-4271-bde5-13a70075f6eb', ST_SetSRID(ST_MakePoint(-78.522,-0.2608),4326), 'Av. Pedro Vicente Maldonado y Cusubamba, Villa Flora, Quito', 5, 78, 'MEDIO', 8100, 11000, 13.5),
  ('8d12a906-0ba2-46cc-acfc-5b772393fe03', ST_SetSRID(ST_MakePoint(-78.4905,-0.2038),4326), 'Calle Juan Pablo Sainz y Gonzalez Suarez, Quito', 5, 72, 'BAJO', 1100, 5200, 44.0),
  ('7887ff3e-9e5e-4921-b652-f9a61ecee0b2', ST_SetSRID(ST_MakePoint(-78.492,-0.2115),4326), 'Av. 12 de Octubre N24-593 y Cordero, Quito', 9, 88, 'MEDIO', 8300, 10200, 20.5);

INSERT INTO ficha_tecnica_mantenimiento
  (id, activo_id, tipo_tuberia, "año_construccion", tipo_estructura,
   calidad_acabados, ultimo_mantenimiento_cisterna,
   ultima_impermeabilizacion_techo, ultima_pintura_fachada,
   ultimo_cambio_cableado_electrico, monto_invertido_mejoras)
VALUES
  ('268545e8-89f3-4fb9-889e-edc1702d3d7f', '53160f0a-95f8-4a3d-a735-c2f82608d1cf', 'Termofusion', 2021, 'Hormigon Armado', 'Porcelanato Alto Trafico', '2024-11-15', '2025-03-10', '2024-06-20', '2023-08-05', 45000),
  ('b033f672-0c95-4fc0-9666-cb96801fb3da', '6c057dd0-8447-4a3b-94be-c38459845e3b', 'Cobre/PVC', 1998, 'Mamposteria Confinada', 'Ceramica Estandar', '2019-04-22', '2017-05-14', '2020-09-03', '2016-02-11', 12000),
  ('e6cdc822-a233-444d-8507-fe882b895070', '449acb53-3d7b-4ad6-9a14-3bcb0b645edb', 'PVC Presion', 2015, 'Hormigon Armado', 'Porcelanato Estandar', '2023-07-18', '2022-11-30', '2023-03-14', '2021-05-20', 28500),
  ('95c83277-d6e2-4fc9-837c-d9129a270a78', '0cb128c9-177d-44a5-81d0-0c5667d88641', 'Termofusion', 2019, 'Estructura Metalica', 'Marmol / Granito', '2025-01-08', '2024-08-22', '2024-04-11', '2022-10-15', 67000),
  ('a06a2690-373c-435e-9b7b-f067625a44f5', '8b040ab7-cdb2-4da1-ada7-0769e4142b74', 'PVC Presion', 2010, 'Hormigon Armado', 'Porcelanato Estandar', '2024-02-05', '2023-06-17', '2022-10-28', '2020-03-09', 19500);

-- Verificacion
SELECT COUNT(*) AS total_activos FROM activos_inmutables;
SELECT COUNT(*) AS fichas FROM ficha_tecnica_mantenimiento;