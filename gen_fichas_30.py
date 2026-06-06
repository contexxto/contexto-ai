"""
Contexto AI V2 — Generacion de fichas tecnicas para los 30 activos sin ficha.
Logica de inferencia geoespacial por sector:
  - Cumbaya: zona nueva (2015+), buena calidad, bajo trafico → mantenimiento reciente
  - Gonzalez Suarez: zona premium pero antigua (1990s), alto trafico → mantenimiento intermedio
  - Norte Condado: zona popular (2005-2015), calidad media
  - Centro Historico: patrimonio (1970s-1980s), alto riesgo estructural, mantenimiento intensivo
  - Sur El Camal: zona popular consolidada (2000s), calidad basica-media
"""
import random
from datetime import date, timedelta

random.seed(42)  # reproducible

def days_ago(n):
    return (date.today() - timedelta(days=n)).isoformat()

def rand_date(min_days, max_days):
    return days_ago(random.randint(min_days, max_days))

# Perfiles por sector
PERFILES = {
    "Cumbaya": {
        "tuberia": ["Termofusion", "PVC Presion"],
        "anno_range": (2012, 2022),
        "estructura": ["Hormigon Armado", "Estructura Metalica"],
        "acabados": ["Porcelanato Estandar", "Porcelanato Alto Trafico", "Marmol / Granito"],
        "cisterna_days": (180, 730),    # reciente (6m - 2a)
        "techo_days": (365, 1095),      # 1-3 años
        "fachada_days": (180, 730),
        "cableado_days": (730, 2190),   # 2-6 años
        "monto_range": (25000, 75000),
    },
    "Gonzalez Suarez": {
        "tuberia": ["Cobre/PVC", "PVC Presion", "Termofusion"],
        "anno_range": (1992, 2010),
        "estructura": ["Mamposteria Confinada", "Hormigon Armado"],
        "acabados": ["Ceramica Estandar", "Porcelanato Estandar", "Marmol / Granito"],
        "cisterna_days": (365, 1460),   # 1-4 años
        "techo_days": (730, 2555),      # 2-7 años
        "fachada_days": (365, 1460),
        "cableado_days": (1095, 3650),  # 3-10 años
        "monto_range": (10000, 55000),
    },
    "Norte Condado": {
        "tuberia": ["PVC Presion", "Cobre/PVC"],
        "anno_range": (2003, 2016),
        "estructura": ["Mamposteria Confinada", "Hormigon Armado"],
        "acabados": ["Ceramica Estandar", "Porcelanato Estandar"],
        "cisterna_days": (365, 1825),   # 1-5 años
        "techo_days": (730, 2920),      # 2-8 años
        "fachada_days": (365, 1825),
        "cableado_days": (1095, 4015),  # 3-11 años
        "monto_range": (8000, 35000),
    },
    "Centro Historico": {
        "tuberia": ["Hierro Galvanizado", "Cobre/PVC"],
        "anno_range": (1968, 1988),
        "estructura": ["Mamposteria Simple", "Mamposteria Confinada"],
        "acabados": ["Ceramica Estandar", "Mortero / Pintura"],
        "cisterna_days": (730, 3650),   # 2-10 años (mantenimiento irregular)
        "techo_days": (1095, 4380),     # 3-12 años
        "fachada_days": (365, 2190),
        "cableado_days": (2190, 6570),  # 6-18 años (riesgo real)
        "monto_range": (15000, 60000),  # restauracion patrimonio es cara
    },
    "Sur El Camal": {
        "tuberia": ["PVC Presion", "Cobre/PVC"],
        "anno_range": (1998, 2012),
        "estructura": ["Mamposteria Confinada", "Hormigon Armado"],
        "acabados": ["Ceramica Estandar", "Mortero / Pintura"],
        "cisterna_days": (365, 2555),   # 1-7 años
        "techo_days": (730, 3285),      # 2-9 años
        "fachada_days": (365, 2190),
        "cableado_days": (1095, 4380),  # 3-12 años
        "monto_range": (5000, 25000),
    },
}

# Direcciones de los 30 activos extra (mismo orden que SEED_EXTRA en gen_sql_seed.py)
ACTIVOS_EXTRA = [
    ("La Carolina",     "Av. 6 de Diciembre N36-109 y Bosmediano, La Carolina, Quito"),
    ("La Carolina",     "Calle Portugal E12-76 y 6 de Diciembre, Quito"),
    ("La Carolina",     "Av. Eloy Alfaro N34-451 y Portugal, Quito"),
    ("La Carolina",     "Calle Catalina Aldaz N34-208 y Portugal, Quito"),
    ("La Carolina",     "Av. De Los Shyris N35-174 y Suecia, Quito"),
    ("Gonzalez Suarez", "Av. Gonzalez Suarez N27-160 y Alemania, Quito"),
    ("Gonzalez Suarez", "Calle Alemania E12-34 y Gonzalez Suarez, Quito"),
    ("Gonzalez Suarez", "Av. Colon E4-50 y 12 de Octubre, La Mariscal, Quito"),
    ("Cumbaya",         "Av. Interoceanica Km 13.5, Urbanizacion El Pilar, Cumbaya"),
    ("Cumbaya",         "Calle Francisco de Orellana y Av. Pampite, Cumbaya, Quito"),
    ("Cumbaya",         "Av. Pampite N5-23 y De Los Conquistadores, Cumbaya"),
    ("Cumbaya",         "Calle Chimborazo y Av. Simon Bolivar, Cumbaya, Quito"),
    ("Cumbaya",         "Av. Robles y Francisco de Orellana, El Batan, Cumbaya"),
    ("Norte Condado",   "Av. Diego de Vasquez y Condado Shopping, Norte, Quito"),
    ("Norte Condado",   "Calle Antonio Jose de Sucre N78-24, El Condado, Quito"),
    ("Norte Condado",   "Av. Occidental y De La Prensa, Cotocollao, Quito"),
    ("Norte Condado",   "Calle Nicolas Arteta y Marchena, Cotocollao, Quito"),
    ("Norte Condado",   "Av. Diego de Vasquez y Mariana de Jesus, Norte, Quito"),
    ("Centro Historico","Calle Garcia Moreno N2-60 y Sucre, Centro Historico, Quito"),
    ("Centro Historico","Calle Venezuela y Chile, Centro Historico, Quito"),
    ("Centro Historico","Av. 24 de Mayo y Cuenca, La Loma, Quito"),
    ("Centro Historico","Calle Mejia N4-30 y Guayaquil, Centro Historico, Quito"),
    ("Centro Historico","Calle Benalcazar N2-12 y Bolivar, Quito"),
    ("Sur El Camal",    "Av. Morona N34-28 y El Camal, Sur, Quito"),
    ("Sur El Camal",    "Calle Manglar Alto y Av. Cardenal de la Torre, Solanda, Quito"),
    ("Sur El Camal",    "Av. Maldonado S25-80 y Cusubamba, Sur, Quito"),
    ("Sur El Camal",    "Calle Gral Enriquez y Napo, Chimbacalle, Quito"),
    ("Sur El Camal",    "Av. Pedro Vicente Maldonado y Cusubamba, Villa Flora, Quito"),
    ("Gonzalez Suarez", "Calle Juan Pablo Sainz y Gonzalez Suarez, Quito"),
    ("Gonzalez Suarez", "Av. 12 de Octubre N24-593 y Cordero, Quito"),
]

def perfil_para_sector(sector):
    # La Carolina usa perfil Cumbaya (zona moderna-premium)
    if sector == "La Carolina":
        return PERFILES["Cumbaya"]
    return PERFILES[sector]

lines = []
lines.append("-- ============================================================")
lines.append("-- Contexto AI V2 — Fichas tecnicas para 30 activos sin ficha")
lines.append("-- Inferencia geoespacial por sector")
lines.append("-- Pega en Supabase SQL Editor y ejecuta")
lines.append("-- ============================================================")
lines.append("")
lines.append("INSERT INTO ficha_tecnica_mantenimiento")
lines.append("  (id, activo_id, tipo_tuberia, \"año_construccion\", tipo_estructura,")
lines.append("   calidad_acabados, ultimo_mantenimiento_cisterna,")
lines.append("   ultima_impermeabilizacion_techo, ultima_pintura_fachada,")
lines.append("   ultimo_cambio_cableado_electrico, monto_invertido_mejoras)")
lines.append("SELECT")
lines.append("  gen_random_uuid(),")
lines.append("  a.id,")
lines.append("  v.tuberia,")
lines.append("  v.anno::int,")
lines.append("  v.estructura,")
lines.append("  v.acabados,")
lines.append("  v.cisterna::date,")
lines.append("  v.techo::date,")
lines.append("  v.fachada::date,")
lines.append("  v.cableado::date,")
lines.append("  v.monto::numeric")
lines.append("FROM activos_inmutables a")
lines.append("JOIN (VALUES")

rows = []
for sector, direccion in ACTIVOS_EXTRA:
    p = perfil_para_sector(sector)
    tuberia   = random.choice(p["tuberia"])
    anno      = random.randint(*p["anno_range"])
    estructura= random.choice(p["estructura"])
    acabados  = random.choice(p["acabados"])
    cisterna  = rand_date(*p["cisterna_days"])
    techo     = rand_date(*p["techo_days"])
    fachada   = rand_date(*p["fachada_days"])
    cableado  = rand_date(*p["cableado_days"])
    monto     = random.randint(*p["monto_range"])

    # Escapar apostrofes en direccion (por si acaso)
    dir_esc = direccion.replace("'", "''")
    rows.append(
        f"  ('{dir_esc}', '{tuberia}', '{anno}', '{estructura}', "
        f"'{acabados}', '{cisterna}', '{techo}', '{fachada}', '{cableado}', {monto})"
    )

lines.append(",\n".join(rows))
lines.append(") AS v(dir, tuberia, anno, estructura, acabados, cisterna, techo, fachada, cableado, monto)")
lines.append("ON a.direccion_estandarizada ILIKE '%' || split_part(v.dir, ',', 1) || '%'")
lines.append("WHERE NOT EXISTS (")
lines.append("  SELECT 1 FROM ficha_tecnica_mantenimiento f WHERE f.activo_id = a.id")
lines.append(");")
lines.append("")
lines.append("-- Verificacion final")
lines.append("SELECT COUNT(*) AS total_fichas FROM ficha_tecnica_mantenimiento;")
lines.append("SELECT COUNT(*) AS activos_sin_ficha")
lines.append("FROM activos_inmutables a")
lines.append("WHERE NOT EXISTS (SELECT 1 FROM ficha_tecnica_mantenimiento f WHERE f.activo_id = a.id);")

output = "\n".join(lines)

with open("fichas_30.sql", "w", encoding="utf-8") as f:
    f.write(output)

print(f"[OK] fichas_30.sql generado: {len(ACTIVOS_EXTRA)} fichas")
print(f"     {len(output)} caracteres")
