"""
Spike #18 del FOSO — capa de POIs propia (Overture + OSM transporte -> pois_propios -> validar).

Prueba end-to-end el primer ladrillo del stack propio (ver docs/SPEC_Foso_Capa_de_Datos.md):
  1. Baja Overture Places del bbox de Quito via DuckDB (S3 anonimo) — 6 categorias.
  2. Baja TRANSPORTE de OSM via Overpass (Overture Places es debil en paradas) — 7a categoria.
  3. Mapea/normaliza y carga a la tabla pois_propios en Supabase (PostGIS).
  4. Valida: POI mas cercano POR categoria para inmuebles de prueba, lado a lado con el
     servicios_cercanos que dejo Google (comparacion honesta sin gastar la API de Google).

Corre:  ./.venv/Scripts/python.exe scripts/foso_pois_spike.py
Lee DATABASE_URL_OVERRIDE del .env (patron de scripts/asignar_corredor.py).

NOTA: TODO SINCRONO (DuckDB + asyncio crashea el GIL en Windows). requests con verify=False
para Overpass (inspeccion SSL corporativa local, mismo criterio que SSL_VERIFY=false).
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

DB_URL = os.getenv("DATABASE_URL_OVERRIDE", "").strip()
if not DB_URL:
    print("❌ DATABASE_URL_OVERRIDE no está en el .env."); sys.exit(1)
SYNC_URL = DB_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://")
if "sslmode" not in SYNC_URL:
    SYNC_URL += ("&" if "?" in SYNC_URL else "?") + "sslmode=require"

import duckdb
import requests
import urllib3
from sqlalchemy import create_engine, text

urllib3.disable_warnings()  # verify=False para Overpass (SSL corporativo local)

OVERTURE = "s3://overturemaps-us-west-2/release/2026-06-17.0/theme=places/type=place/*"
BBOX = dict(xmin=-78.60, xmax=-78.40, ymin=-0.35, ymax=-0.05)  # Quito
# Umbral de confianza POR categoría. La confianza mezcla "¿es real?" con "¿categoría
# correcta?": el ruido (oficinas/negocios mal etiquetados) se concentra en parque y
# centro_comercial → exigente ahí (0.70). Salud/farmacia/super/educación son fiables a
# menor confianza (cadenas de barrio reales) → permisivo (0.55) para no perder cobertura
# en la periferia. Un umbral plano de 0.7 limpiaba el ruido pero mataba recall real.
CONF_MIN = {
    "salud":            0.55,
    "farmacia":         0.55,
    "supermercado":     0.55,
    "educacion":        0.55,
    "parque":           0.70,
    "centro_comercial": 0.70,
}
CONF_FLOOR = min(CONF_MIN.values())  # piso para el pull; el resto se filtra por categoría

CAT_LEAF = {
    "salud":            ["hospital", "doctor", "medical_center", "urgent_care_clinic"],
    "farmacia":         ["pharmacy", "drugstore"],
    "supermercado":     ["supermarket", "grocery_store"],
    "educacion":        ["school", "college_university", "preschool"],
    "parque":           ["park", "playground"],
    "centro_comercial": ["shopping_center", "department_store"],
}
LEAF_TO_CAT = {leaf: cat for cat, leafs in CAT_LEAF.items() for leaf in leafs}

# Claves comunes a TODO POI (Overture y OSM) — el executemany exige el mismo shape.
_KEYS = ("nombre", "categoria", "cat_leaf", "lon", "lat", "confidence",
         "overture_id", "osm_id", "marca", "direccion", "operativo", "fuente")


def _normalizar(p: dict) -> dict:
    return {k: p.get(k) for k in _KEYS}


def pull_overture() -> list[dict]:
    """Places del bbox de Quito en nuestras 6 categorías, confianza ≥ CONF_MIN."""
    leaf_list = "', '".join(LEAF_TO_CAT.keys())
    con = duckdb.connect()
    try:
        con.execute("INSTALL spatial; INSTALL httpfs; LOAD spatial; LOAD httpfs; SET s3_region='us-west-2';")
        q = f"""
            SELECT id AS overture_id, names.primary AS nombre, categories.primary AS cat_leaf,
                   confidence, ST_Y(geometry) AS lat, ST_X(geometry) AS lon,
                   addresses[1].freeform AS direccion, brand.names.primary AS marca, operating_status
            FROM read_parquet('{OVERTURE}')
            WHERE bbox.xmin BETWEEN {BBOX['xmin']} AND {BBOX['xmax']}
              AND bbox.ymin BETWEEN {BBOX['ymin']} AND {BBOX['ymax']}
              AND confidence > {CONF_FLOOR}
              AND categories.primary IN ('{leaf_list}')
        """
        cols = ["overture_id", "nombre", "cat_leaf", "confidence", "lat", "lon",
                "direccion", "marca", "operating_status"]
        raw = [dict(zip(cols, r)) for r in con.execute(q).fetchall()]
    finally:
        con.close()
    out = []
    for r in raw:
        cat = LEAF_TO_CAT.get(r["cat_leaf"])
        if r["confidence"] is None or r["confidence"] < CONF_MIN[cat]:
            continue  # umbral por categoría (parque/centro_comercial más exigentes)
        r["categoria"] = cat
        r["operativo"] = (r.get("operating_status") != "closed")
        r["osm_id"] = None
        r["fuente"] = "overture"
        out.append(_normalizar(r))
    return out


_OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",  # mirror de respaldo
]


def pull_osm_transporte() -> list[dict]:
    """Transporte público de OSM (Overture Places no lo cubre bien). Overpass, sin auth."""
    s, w, n, e = BBOX["ymin"], BBOX["xmin"], BBOX["ymax"], BBOX["xmax"]
    query = f"""
    [out:json][timeout:90];
    (
      node["highway"="bus_stop"]({s},{w},{n},{e});
      node["amenity"="bus_station"]({s},{w},{n},{e});
      node["railway"="station"]({s},{w},{n},{e});
      node["railway"="subway_entrance"]({s},{w},{n},{e});
      node["public_transport"="station"]({s},{w},{n},{e});
    );
    out body;
    """
    headers = {"User-Agent": "whaber-foso-spike/1.0 (contacto: dev@whaber.local)"}
    elems = None
    for url in _OVERPASS_ENDPOINTS:
        try:
            r = requests.post(url, data={"data": query}, headers=headers,
                              timeout=120, verify=False)
            r.raise_for_status()
            elems = r.json().get("elements", [])
            break
        except Exception as ex:  # rate-limit / caído → probar siguiente mirror
            print(f"   ⚠️ Overpass {url.split('/')[2]} falló ({str(ex)[:60]})")
    if elems is None:  # todos los mirrors fallaron → degradar sin romper el spike
        print("   ⚠️ ningún endpoint de Overpass respondió — sigo sin transporte")
        return []
    out = []
    for el in elems:
        tags = el.get("tags", {}) or {}
        if el.get("lat") is None or el.get("lon") is None:
            continue
        # Subtipo → distingue el hub MASIVO (Metro/terminal, héroe de plusvalía) de la
        # simple parada de bus. Se guarda en categoria_overture (:cat_leaf) para que la
        # capa de producción priorice el masivo igual que _mejor_transporte con Google.
        if tags.get("railway") == "subway_entrance" or tags.get("station") == "subway":
            subtipo, nombre = "metro", tags.get("name") or "Estación de Metro"
        elif tags.get("railway") == "station":
            subtipo, nombre = "estacion_tren", tags.get("name") or "Estación de tren"
        elif tags.get("amenity") == "bus_station":
            subtipo, nombre = "terminal_bus", tags.get("name") or "Terminal de bus"
        elif tags.get("public_transport") == "station":
            subtipo, nombre = "estacion", tags.get("name") or "Estación"
        else:
            subtipo, nombre = "parada_bus", tags.get("name") or "Parada de bus"
        out.append(_normalizar({
            "nombre": nombre, "categoria": "transporte", "cat_leaf": subtipo,
            "lat": el["lat"], "lon": el["lon"], "confidence": None,
            "overture_id": None, "osm_id": str(el["id"]), "marca": None,
            "direccion": None, "operativo": True, "fuente": "osm",
        }))
    return out


# Subtipos de transporte considerados "masivos" (Metro/tren/terminal) — héroes de plusvalía.
TRANSPORTE_MASIVO = ("metro", "estacion_tren", "terminal_bus", "estacion")


DDL = """
CREATE TABLE IF NOT EXISTS pois_propios (
    id             bigserial PRIMARY KEY,
    nombre         text,
    categoria      text NOT NULL,
    categoria_overture text,
    geom           geometry(Point, 4326) NOT NULL,
    fuente         text NOT NULL DEFAULT 'overture',
    confianza      real,
    overture_id    text,
    osm_id         text,
    marca          text,
    direccion      text,
    operativo      boolean DEFAULT true,
    actualizado_en timestamptz NOT NULL DEFAULT now()
);
-- idempotente: si la tabla ya existía de una corrida previa, agrega columnas nuevas
ALTER TABLE pois_propios ADD COLUMN IF NOT EXISTS osm_id text;
ALTER TABLE pois_propios ADD COLUMN IF NOT EXISTS fuente text NOT NULL DEFAULT 'overture';
CREATE INDEX IF NOT EXISTS pois_propios_geom_gix ON pois_propios USING GIST (geom);
CREATE INDEX IF NOT EXISTS pois_propios_cat_idx  ON pois_propios (categoria);
"""

INSERT_SQL = text("""
    INSERT INTO pois_propios
        (nombre, categoria, categoria_overture, geom, fuente, confianza, overture_id, osm_id, marca, direccion, operativo)
    VALUES
        (:nombre, :categoria, :cat_leaf, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
         :fuente, :confidence, :overture_id, :osm_id, :marca, :direccion, :operativo)
""")

NEAREST_SQL = text("""
    SELECT DISTINCT ON (categoria)
           categoria, nombre, marca, confianza, fuente,
           ROUND(ST_Distance(geom::geography,
                 ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography))::int AS distancia_m
    FROM pois_propios
    WHERE operativo
      AND ST_DWithin(geom::geography,
                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :max_m)
    ORDER BY categoria, geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
""")


def main():
    print("── 1) Overture Places (6 categorías, umbral de conf por categoría) ──", flush=True)
    t0 = time.time()
    pois = pull_overture()
    print(f"   {len(pois)} POIs Overture ({time.time()-t0:.0f}s)")
    print("── 2) OSM transporte (Overpass) ──", flush=True)
    t0 = time.time()
    transp = pull_osm_transporte()
    print(f"   {len(transp)} paradas/estaciones de transporte ({time.time()-t0:.0f}s)")
    pois += transp

    por_cat: dict[str, int] = {}
    for p in pois:
        por_cat[p["categoria"]] = por_cat.get(p["categoria"], 0) + 1
    for cat, n in sorted(por_cat.items(), key=lambda x: -x[1]):
        print(f"     {cat:16} {n}")

    eng = create_engine(SYNC_URL, echo=False)
    with eng.begin() as db:
        print("── 3) Cargando a pois_propios ──", flush=True)
        for stmt in DDL.strip().split(";"):
            if stmt.strip():
                db.execute(text(stmt))
        db.execute(text("TRUNCATE pois_propios RESTART IDENTITY"))
        db.execute(INSERT_SQL, pois)
        n = db.execute(text("SELECT count(*) FROM pois_propios")).scalar()
        print(f"   cargados {n} POIs ✅")

    with eng.connect() as db:
        print("\n── 4) Validación: nuestra capa vs Google (servicios_cercanos guardado) ──", flush=True)
        # Prioriza inmuebles que SÍ tengan servicios guardados (para un vs-Google real).
        inmuebles = db.execute(text("""
            SELECT id::text AS id, direccion_estandarizada AS dir,
                   ST_Y(geom) AS lat, ST_X(geom) AS lon, servicios_cercanos
            FROM activos_inmutables WHERE geom IS NOT NULL
            ORDER BY (servicios_cercanos IS NOT NULL AND btrim(servicios_cercanos) <> '') DESC,
                     created_at
            LIMIT 4
        """)).mappings().all()

        for a in inmuebles:
            print(f"\n📍 {a['dir']}")
            props = db.execute(NEAREST_SQL,
                    {"lat": a["lat"], "lon": a["lon"], "max_m": 1500}).mappings().all()
            print("   NUESTRA capa:")
            if not props:
                print("     (sin POIs a ≤1.5 km)")
            for p in props:
                marca = f" [{p['marca']}]" if p["marca"] else ""
                conf = f"conf {p['confianza']:.2f}" if p["confianza"] is not None else "—"
                print(f"     {p['categoria']:16} {p['nombre']}{marca} · {p['distancia_m']} m · {conf} · {p['fuente']}")
            sc = (a["servicios_cercanos"] or "").strip().replace("\n", " ")
            print(f"   GOOGLE: {sc[:260] or '(vacío)'}")

    eng.dispose()
    print("\n✅ Spike #18 completo. pois_propios (Overture + OSM transporte) cargada y consultable.")


if __name__ == "__main__":
    main()
