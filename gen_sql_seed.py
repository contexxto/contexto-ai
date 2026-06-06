"""Genera SQL INSERT para poblar Supabase desde local"""
import uuid

assets = [
    ("A", -0.1810, -78.4820, "Av. Republica del Salvador N34-183, La Carolina, Quito", 8, 95, "BAJO", 1200, 8500, 42.3),
    ("B", -0.1845, -78.4865, "Av. Amazonas N35-17 y Atahualpa, La Carolina, Quito", 12, 88, "ALTO", 18400, 12000, 14.7),
    ("C", -0.1798, -78.4850, "Calle Los Shyris N35-61 y Portugal, Quito", 5, 91, "MEDIO", 6300, 7200, 28.1),
    ("D", -0.1835, -78.4802, "Av. Naciones Unidas E10-44 y Amazonas, Quito", 15, 93, "MEDIO", 9100, 11500, 22.5),
    ("E", -0.1778, -78.4830, "Calle Isla Fernandina N44-28 y Los Shyris, Quito", 4, 87, "BAJO", 980, 4800, 51.0),
]

SEED_EXTRA = [
    ("La Carolina", -0.1795, -78.4825, "Av. 6 de Diciembre N36-109 y Bosmediano, La Carolina, Quito", 10, 92, "MEDIO", 7800, 9200, 31.5),
    ("La Carolina", -0.1815, -78.4835, "Calle Portugal E12-76 y 6 de Diciembre, Quito", 6, 89, "MEDIO", 5400, 7800, 26.8),
    ("La Carolina", -0.1855, -78.4855, "Av. Eloy Alfaro N34-451 y Portugal, Quito", 14, 90, "ALTO", 14200, 10500, 18.2),
    ("La Carolina", -0.1800, -78.4860, "Calle Catalina Aldaz N34-208 y Portugal, Quito", 4, 86, "BAJO", 1450, 5600, 39.4),
    ("La Carolina", -0.1822, -78.4872, "Av. De Los Shyris N35-174 y Suecia, Quito", 8, 94, "MEDIO", 9100, 11200, 24.7),
    ("Gonzalez Suarez", -0.2045, -78.4892, "Av. Gonzalez Suarez N27-160 y Alemania, Quito", 18, 78, "ALTO", 22000, 13000, 8.5),
    ("Gonzalez Suarez", -0.2052, -78.4880, "Calle Alemania E12-34 y Gonzalez Suarez, Quito", 12, 75, "MEDIO", 6800, 9800, 15.3),
    ("Gonzalez Suarez", -0.2101, -78.4940, "Av. Colon E4-50 y 12 de Octubre, La Mariscal, Quito", 7, 96, "ALTO", 19500, 14500, 12.0),
    ("Cumbaya", -0.1980, -78.4320, "Av. Interoceánica Km 13.5, Urbanizacion El Pilar, Cumbaya", 2, 45, "BAJO", 3200, 2800, 65.0),
    ("Cumbaya", -0.1975, -78.4340, "Calle Francisco de Orellana y Av. Pampite, Cumbaya, Quito", 3, 52, "BAJO", 2400, 3200, 58.5),
    ("Cumbaya", -0.1965, -78.4355, "Av. Pampite N5-23 y De Los Conquistadores, Cumbaya", 4, 58, "MEDIO", 5600, 4500, 47.2),
    ("Cumbaya", -0.2010, -78.4280, "Calle Chimborazo y Av. Simon Bolivar, Cumbaya, Quito", 2, 38, "BAJO", 1800, 2100, 72.0),
    ("Cumbaya", -0.1990, -78.4300, "Av. Robles y Francisco de Orellana, El Batan, Cumbaya", 6, 61, "MEDIO", 4900, 5800, 39.8),
    ("Norte Condado", -0.1022, -78.5010, "Av. Diego de Vasquez y Condado Shopping, Norte, Quito", 5, 70, "MEDIO", 8900, 6800, 22.3),
    ("Norte Condado", -0.1035, -78.5025, "Calle Antonio Jose de Sucre N78-24, El Condado, Quito", 3, 65, "BAJO", 2100, 4200, 35.6),
    ("Norte Condado", -0.1105, -78.5080, "Av. Occidental y De La Prensa, Cotocollao, Quito", 4, 68, "ALTO", 15600, 8900, 16.4),
    ("Norte Condado", -0.1092, -78.5055, "Calle Nicolas Arteta y Marchena, Cotocollao, Quito", 2, 62, "BAJO", 1350, 3600, 41.2),
    ("Norte Condado", -0.1045, -78.5040, "Av. Diego de Vasquez y Mariana de Jesus, Norte, Quito", 8, 74, "MEDIO", 7200, 7100, 28.9),
    ("Centro Historico", -0.2201, -78.5120, "Calle Garcia Moreno N2-60 y Sucre, Centro Historico, Quito", 3, 98, "ALTO", 21000, 18000, 5.2),
    ("Centro Historico", -0.2215, -78.5135, "Calle Venezuela y Chile, Centro Historico, Quito", 4, 97, "ALTO", 19500, 17200, 6.8),
    ("Centro Historico", -0.2240, -78.5150, "Av. 24 de Mayo y Cuenca, La Loma, Quito", 2, 92, "MEDIO", 9800, 14500, 11.0),
    ("Centro Historico", -0.2195, -78.5108, "Calle Mejia N4-30 y Guayaquil, Centro Historico, Quito", 5, 96, "ALTO", 18200, 16800, 4.5),
    ("Centro Historico", -0.2208, -78.5125, "Calle Benalcazar N2-12 y Bolivar, Quito", 3, 95, "MEDIO", 11000, 15200, 7.3),
    ("Sur El Camal", -0.2650, -78.5205, "Av. Morona N34-28 y El Camal, Sur, Quito", 3, 72, "MEDIO", 7400, 9800, 14.2),
    ("Sur El Camal", -0.2720, -78.5280, "Calle Manglar Alto y Av. Cardenal de la Torre, Solanda, Quito", 2, 68, "BAJO", 2800, 7500, 19.6),
    ("Sur El Camal", -0.2690, -78.5245, "Av. Maldonado S25-80 y Cusubamba, Sur, Quito", 4, 75, "ALTO", 16800, 12200, 9.8),
    ("Sur El Camal", -0.2445, -78.5185, "Calle Gral Enriquez y Napo, Chimbacalle, Quito", 3, 80, "MEDIO", 6200, 10400, 16.8),
    ("Sur El Camal", -0.2608, -78.5220, "Av. Pedro Vicente Maldonado y Cusubamba, Villa Flora, Quito", 5, 78, "MEDIO", 8100, 11000, 13.5),
    ("Gonzalez Suarez", -0.2038, -78.4905, "Calle Juan Pablo Sainz y Gonzalez Suarez, Quito", 5, 72, "BAJO", 1100, 5200, 44.0),
    ("Gonzalez Suarez", -0.2115, -78.4920, "Av. 12 de Octubre N24-593 y Cordero, Quito", 9, 88, "MEDIO", 8300, 10200, 20.5),
]

all_assets = []
ids_map = {}

# Base 5
for a in assets:
    aid = str(uuid.uuid4())
    ids_map[a[0]] = aid
    all_assets.append((aid, a[1], a[2], a[3], a[4], a[5], a[6], a[7], a[8], a[9]))

# Extra 30
for a in SEED_EXTRA:
    aid = str(uuid.uuid4())
    all_assets.append((aid, a[1], a[2], a[3], a[4], a[5], a[6], a[7], a[8], a[9]))

sql_lines = []
sql_lines.append("-- ============================================================")
sql_lines.append("-- Contexto AI V2 — Seed Data: 35 activos en 6 sectores de Quito")
sql_lines.append("-- Pega esto en Supabase SQL Editor y ejecuta")
sql_lines.append("-- ============================================================")
sql_lines.append("")

# Activos en lotes de 10
sql_lines.append("INSERT INTO activos_inmutables")
sql_lines.append("  (id, geom, direccion_estandarizada, piso_altura, walk_score,")
sql_lines.append("   score_ruido_predictivo, volumen_trafico_historico,")
sql_lines.append("   densidad_poblacional_pico, porcentaje_cobertura_vegetal)")
sql_lines.append("VALUES")

rows = []
for a in all_assets:
    aid, lat, lon, dir_, piso, walk, ruido, traf, dens, veg = a
    rows.append(
        f"  ('{aid}', ST_SetSRID(ST_MakePoint({lon},{lat}),4326), "
        f"'{dir_}', {piso}, {walk}, '{ruido}', {traf}, {dens}, {veg})"
    )
sql_lines.append(",\n".join(rows) + ";")
sql_lines.append("")

# Fichas para los 5 base
fichas = [
    (ids_map["A"], "Termofusion", 2021, "Hormigon Armado", "Porcelanato Alto Trafico", "2024-11-15","2025-03-10","2024-06-20","2023-08-05", 45000),
    (ids_map["B"], "Cobre/PVC", 1998, "Mamposteria Confinada", "Ceramica Estandar", "2019-04-22","2017-05-14","2020-09-03","2016-02-11", 12000),
    (ids_map["C"], "PVC Presion", 2015, "Hormigon Armado", "Porcelanato Estandar", "2023-07-18","2022-11-30","2023-03-14","2021-05-20", 28500),
    (ids_map["D"], "Termofusion", 2019, "Estructura Metalica", "Marmol / Granito", "2025-01-08","2024-08-22","2024-04-11","2022-10-15", 67000),
    (ids_map["E"], "PVC Presion", 2010, "Hormigon Armado", "Porcelanato Estandar", "2024-02-05","2023-06-17","2022-10-28","2020-03-09", 19500),
]

sql_lines.append("INSERT INTO ficha_tecnica_mantenimiento")
sql_lines.append("  (id, activo_id, tipo_tuberia, anno_construccion, tipo_estructura,")
sql_lines.append("   calidad_acabados, ultimo_mantenimiento_cisterna,")
sql_lines.append("   ultima_impermeabilizacion_techo, ultima_pintura_fachada,")
sql_lines.append("   ultimo_cambio_cableado_electrico, monto_invertido_mejoras)")
sql_lines.append("VALUES")

frows = []
for f in fichas:
    fid = str(uuid.uuid4())
    frows.append(
        f"  ('{fid}', '{f[0]}', '{f[1]}', {f[2]}, '{f[3]}', '{f[4]}', "
        f"'{f[5]}', '{f[6]}', '{f[7]}', '{f[8]}', {f[9]})"
    )
sql_lines.append(",\n".join(frows) + ";")
sql_lines.append("")
sql_lines.append("-- Verificacion")
sql_lines.append("SELECT COUNT(*) AS total_activos FROM activos_inmutables;")
sql_lines.append("SELECT COUNT(*) AS fichas FROM ficha_tecnica_mantenimiento;")

output = "\n".join(sql_lines)

with open("supabase_seed.sql", "w", encoding="utf-8") as f:
    f.write(output)

print(f"[OK] supabase_seed.sql generado: {len(all_assets)} activos")
print(f"     {len(output)} caracteres")
