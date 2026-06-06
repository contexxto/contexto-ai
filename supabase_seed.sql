-- ============================================================
-- Contexto AI V2 — Seed Data: 35 activos en 6 sectores de Quito
-- Pega esto en Supabase SQL Editor y ejecuta
-- ============================================================

INSERT INTO activos_inmutables
  (id, geom, direccion_estandarizada, piso_altura, walk_score,
   score_ruido_predictivo, volumen_trafico_historico,
   densidad_poblacional_pico, porcentaje_cobertura_vegetal)
VALUES
  ('c3fec2e3-d934-40d4-8b75-af9d271380c8', ST_SetSRID(ST_MakePoint(-78.482,-0.181),4326), 'Av. Republica del Salvador N34-183, La Carolina, Quito', 8, 95, 'BAJO', 1200, 8500, 42.3),
  ('7984b682-6b6e-4b4a-b190-caeb6c0314cc', ST_SetSRID(ST_MakePoint(-78.4865,-0.1845),4326), 'Av. Amazonas N35-17 y Atahualpa, La Carolina, Quito', 12, 88, 'ALTO', 18400, 12000, 14.7),
  ('dde6f993-6df4-4f2b-9b86-101297602a40', ST_SetSRID(ST_MakePoint(-78.485,-0.1798),4326), 'Calle Los Shyris N35-61 y Portugal, Quito', 5, 91, 'MEDIO', 6300, 7200, 28.1),
  ('aca9a335-4ef8-4f8e-8594-d3d13938c6c3', ST_SetSRID(ST_MakePoint(-78.4802,-0.1835),4326), 'Av. Naciones Unidas E10-44 y Amazonas, Quito', 15, 93, 'MEDIO', 9100, 11500, 22.5),
  ('5fda4990-c2c2-4d35-8dee-d9c03a930da4', ST_SetSRID(ST_MakePoint(-78.483,-0.1778),4326), 'Calle Isla Fernandina N44-28 y Los Shyris, Quito', 4, 87, 'BAJO', 980, 4800, 51.0),
  ('bbc4517c-64dc-4290-a3b6-e388a7edc699', ST_SetSRID(ST_MakePoint(-78.4825,-0.1795),4326), 'Av. 6 de Diciembre N36-109 y Bosmediano, La Carolina, Quito', 10, 92, 'MEDIO', 7800, 9200, 31.5),
  ('3aa1063b-f882-45c2-9edc-d5e83af4a4d3', ST_SetSRID(ST_MakePoint(-78.4835,-0.1815),4326), 'Calle Portugal E12-76 y 6 de Diciembre, Quito', 6, 89, 'MEDIO', 5400, 7800, 26.8),
  ('bd73d2b4-9fcc-4f43-9fb2-43c37e3760ee', ST_SetSRID(ST_MakePoint(-78.4855,-0.1855),4326), 'Av. Eloy Alfaro N34-451 y Portugal, Quito', 14, 90, 'ALTO', 14200, 10500, 18.2),
  ('29b02f46-636d-4e45-a02c-b0d816671c2c', ST_SetSRID(ST_MakePoint(-78.486,-0.18),4326), 'Calle Catalina Aldaz N34-208 y Portugal, Quito', 4, 86, 'BAJO', 1450, 5600, 39.4),
  ('a0984bc3-9ea5-4ea4-8928-04b252977ea3', ST_SetSRID(ST_MakePoint(-78.4872,-0.1822),4326), 'Av. De Los Shyris N35-174 y Suecia, Quito', 8, 94, 'MEDIO', 9100, 11200, 24.7),
  ('51665ea2-28f4-4b73-8c5c-46a39898fbbc', ST_SetSRID(ST_MakePoint(-78.4892,-0.2045),4326), 'Av. Gonzalez Suarez N27-160 y Alemania, Quito', 18, 78, 'ALTO', 22000, 13000, 8.5),
  ('dcc85214-9907-4e57-b670-e7b63cd98b98', ST_SetSRID(ST_MakePoint(-78.488,-0.2052),4326), 'Calle Alemania E12-34 y Gonzalez Suarez, Quito', 12, 75, 'MEDIO', 6800, 9800, 15.3),
  ('2de1dc70-35f5-4a22-a562-db76398b1619', ST_SetSRID(ST_MakePoint(-78.494,-0.2101),4326), 'Av. Colon E4-50 y 12 de Octubre, La Mariscal, Quito', 7, 96, 'ALTO', 19500, 14500, 12.0),
  ('68cf6149-8c35-4f71-a049-d10aeffcf784', ST_SetSRID(ST_MakePoint(-78.432,-0.198),4326), 'Av. Interoceánica Km 13.5, Urbanizacion El Pilar, Cumbaya', 2, 45, 'BAJO', 3200, 2800, 65.0),
  ('15d37236-abbc-44db-a33b-f670add9d328', ST_SetSRID(ST_MakePoint(-78.434,-0.1975),4326), 'Calle Francisco de Orellana y Av. Pampite, Cumbaya, Quito', 3, 52, 'BAJO', 2400, 3200, 58.5),
  ('40e0c117-b5f4-4d92-b96a-e1a8bc1e31c7', ST_SetSRID(ST_MakePoint(-78.4355,-0.1965),4326), 'Av. Pampite N5-23 y De Los Conquistadores, Cumbaya', 4, 58, 'MEDIO', 5600, 4500, 47.2),
  ('acee2163-0781-4087-8ca2-97735b268c28', ST_SetSRID(ST_MakePoint(-78.428,-0.201),4326), 'Calle Chimborazo y Av. Simon Bolivar, Cumbaya, Quito', 2, 38, 'BAJO', 1800, 2100, 72.0),
  ('27647d6d-c0a2-4b8e-bc49-cf1ed9ef271a', ST_SetSRID(ST_MakePoint(-78.43,-0.199),4326), 'Av. Robles y Francisco de Orellana, El Batan, Cumbaya', 6, 61, 'MEDIO', 4900, 5800, 39.8),
  ('1ccab297-6ee0-420e-a011-fec71506c7b9', ST_SetSRID(ST_MakePoint(-78.501,-0.1022),4326), 'Av. Diego de Vasquez y Condado Shopping, Norte, Quito', 5, 70, 'MEDIO', 8900, 6800, 22.3),
  ('4288a480-a5ed-4d14-830a-6b536e28f883', ST_SetSRID(ST_MakePoint(-78.5025,-0.1035),4326), 'Calle Antonio Jose de Sucre N78-24, El Condado, Quito', 3, 65, 'BAJO', 2100, 4200, 35.6),
  ('a05bd78d-2df9-40d8-afc0-9c4c82d511bd', ST_SetSRID(ST_MakePoint(-78.508,-0.1105),4326), 'Av. Occidental y De La Prensa, Cotocollao, Quito', 4, 68, 'ALTO', 15600, 8900, 16.4),
  ('dff6ea78-1e78-487a-ad3e-4100e03d0093', ST_SetSRID(ST_MakePoint(-78.5055,-0.1092),4326), 'Calle Nicolas Arteta y Marchena, Cotocollao, Quito', 2, 62, 'BAJO', 1350, 3600, 41.2),
  ('4e33a8d1-f94e-4990-bcd2-1f59decb6d1c', ST_SetSRID(ST_MakePoint(-78.504,-0.1045),4326), 'Av. Diego de Vasquez y Mariana de Jesus, Norte, Quito', 8, 74, 'MEDIO', 7200, 7100, 28.9),
  ('9d0c1fcd-f8d3-4d8a-b722-1a4cac1f2699', ST_SetSRID(ST_MakePoint(-78.512,-0.2201),4326), 'Calle Garcia Moreno N2-60 y Sucre, Centro Historico, Quito', 3, 98, 'ALTO', 21000, 18000, 5.2),
  ('2ff0b14d-a16c-4592-b0cb-d59501748157', ST_SetSRID(ST_MakePoint(-78.5135,-0.2215),4326), 'Calle Venezuela y Chile, Centro Historico, Quito', 4, 97, 'ALTO', 19500, 17200, 6.8),
  ('50eb6460-2a66-4f31-a5fc-0c47d7f370b8', ST_SetSRID(ST_MakePoint(-78.515,-0.224),4326), 'Av. 24 de Mayo y Cuenca, La Loma, Quito', 2, 92, 'MEDIO', 9800, 14500, 11.0),
  ('b2d43296-a3e1-41a9-b5c4-b58fdcb51f23', ST_SetSRID(ST_MakePoint(-78.5108,-0.2195),4326), 'Calle Mejia N4-30 y Guayaquil, Centro Historico, Quito', 5, 96, 'ALTO', 18200, 16800, 4.5),
  ('539b7580-b1e8-4866-9be5-929aa04c9bcb', ST_SetSRID(ST_MakePoint(-78.5125,-0.2208),4326), 'Calle Benalcazar N2-12 y Bolivar, Quito', 3, 95, 'MEDIO', 11000, 15200, 7.3),
  ('9beb4370-0468-4438-8b10-7023b1f17402', ST_SetSRID(ST_MakePoint(-78.5205,-0.265),4326), 'Av. Morona N34-28 y El Camal, Sur, Quito', 3, 72, 'MEDIO', 7400, 9800, 14.2),
  ('98366989-99fb-489e-9dc2-9172e11bbd8c', ST_SetSRID(ST_MakePoint(-78.528,-0.272),4326), 'Calle Manglar Alto y Av. Cardenal de la Torre, Solanda, Quito', 2, 68, 'BAJO', 2800, 7500, 19.6),
  ('e1b4b891-8a52-42c7-8765-e023c1fcab27', ST_SetSRID(ST_MakePoint(-78.5245,-0.269),4326), 'Av. Maldonado S25-80 y Cusubamba, Sur, Quito', 4, 75, 'ALTO', 16800, 12200, 9.8),
  ('c8b13c28-9c14-49b8-a1d7-1e193c11a13b', ST_SetSRID(ST_MakePoint(-78.5185,-0.2445),4326), 'Calle Gral Enriquez y Napo, Chimbacalle, Quito', 3, 80, 'MEDIO', 6200, 10400, 16.8),
  ('e3a18b06-8362-412b-8748-766b413958b3', ST_SetSRID(ST_MakePoint(-78.522,-0.2608),4326), 'Av. Pedro Vicente Maldonado y Cusubamba, Villa Flora, Quito', 5, 78, 'MEDIO', 8100, 11000, 13.5),
  ('373afe4b-49db-44a0-93ef-58cee5cca098', ST_SetSRID(ST_MakePoint(-78.4905,-0.2038),4326), 'Calle Juan Pablo Sainz y Gonzalez Suarez, Quito', 5, 72, 'BAJO', 1100, 5200, 44.0),
  ('797ae517-983f-47dc-985f-bcbb8ad75fd7', ST_SetSRID(ST_MakePoint(-78.492,-0.2115),4326), 'Av. 12 de Octubre N24-593 y Cordero, Quito', 9, 88, 'MEDIO', 8300, 10200, 20.5);

INSERT INTO ficha_tecnica_mantenimiento
  (id, activo_id, tipo_tuberia, anno_construccion, tipo_estructura,
   calidad_acabados, ultimo_mantenimiento_cisterna,
   ultima_impermeabilizacion_techo, ultima_pintura_fachada,
   ultimo_cambio_cableado_electrico, monto_invertido_mejoras)
VALUES
  ('c2b8fb23-8692-44d3-a523-c365dd43fe53', 'c3fec2e3-d934-40d4-8b75-af9d271380c8', 'Termofusion', 2021, 'Hormigon Armado', 'Porcelanato Alto Trafico', '2024-11-15', '2025-03-10', '2024-06-20', '2023-08-05', 45000),
  ('4fff49a4-af3a-4b96-8e66-c754ccbc8aea', '7984b682-6b6e-4b4a-b190-caeb6c0314cc', 'Cobre/PVC', 1998, 'Mamposteria Confinada', 'Ceramica Estandar', '2019-04-22', '2017-05-14', '2020-09-03', '2016-02-11', 12000),
  ('fac8cd9e-f2dd-40fa-8b97-03fd37410731', 'dde6f993-6df4-4f2b-9b86-101297602a40', 'PVC Presion', 2015, 'Hormigon Armado', 'Porcelanato Estandar', '2023-07-18', '2022-11-30', '2023-03-14', '2021-05-20', 28500),
  ('011091fc-a6c9-4af9-a223-94be6557d500', 'aca9a335-4ef8-4f8e-8594-d3d13938c6c3', 'Termofusion', 2019, 'Estructura Metalica', 'Marmol / Granito', '2025-01-08', '2024-08-22', '2024-04-11', '2022-10-15', 67000),
  ('3bf0cac8-f164-4238-9203-4461d82241da', '5fda4990-c2c2-4d35-8dee-d9c03a930da4', 'PVC Presion', 2010, 'Hormigon Armado', 'Porcelanato Estandar', '2024-02-05', '2023-06-17', '2022-10-28', '2020-03-09', 19500);

-- Verificacion
SELECT COUNT(*) AS total_activos FROM activos_inmutables;
SELECT COUNT(*) AS fichas FROM ficha_tecnica_mantenimiento;