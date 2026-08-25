"""
Spike #18 del FOSO — capa de POIs propia (Overture + OSM transporte -> pois_propios -> validar).

Prueba end-to-end el primer ladrillo del stack propio (ver docs/SPEC_Foso_Capa_de_Datos.md):
  1. Baja Overture Places del bbox de Quito via DuckDB (S3 anonimo) — 6 categorias.
  2. Baja TRANSPORTE de OSM via Overpass (Overture Places es debil en paradas) — 7a categoria.
  3. Mapea/normaliza y carga a la tabla pois_propios en Supabase (PostGIS).
  4. Valida: POI mas cercano POR categoria para inmuebles de prueba, lado a lado con el
     servicios_cercanos que dejo Google (comparacion honesta sin gastar la API de Google).

Corre:  ./.venv/Scripts/python.exe scripts/foso_pois_spike.py [ciudad]
        (sin argumento = 'quito'. Ciudades registradas en el dict CIUDADES.)

MULTI-CIUDAD (desde 2026-07-27, migracion 019): la recarga es POR CIUDAD
(`DELETE ... WHERE ciudad = :c`), no un TRUNCATE de la tabla. Correr este script para
un mercado NO toca los demas. Antes de la 019, abrir la segunda ciudad habria borrado
Quito entero.

Lee DATABASE_URL_OVERRIDE del .env (patron de scripts/asignar_corredor.py).

NOTA: TODO SINCRONO (DuckDB + asyncio crashea el GIL en Windows). requests con verify=False
para Overpass (inspeccion SSL corporativa local, mismo criterio que SSL_VERIFY=false).
"""
import os
import re
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


def _a_sincrona(url: str) -> str:
    """psycopg en vez de asyncpg (este script es sincrono) y TLS obligatorio."""
    sync = url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    if "sslmode" not in sync:
        sync += ("&" if "?" in sync else "?") + "sslmode=require"
    return sync


SYNC_URL = _a_sincrona(DB_URL) if DB_URL else ""


def exigir_credencial_de_base() -> None:
    """Corta antes de tocar nada si no hay credencial. Al CORRER, no al importar.

    Hasta el 2026-08-24 este corte vivia en el cuerpo del modulo, asi que importar el
    archivo mataba al interprete. En el portatil del fundador no se notaba —el .env
    tiene la variable—, pero en CI no hay .env: las ocho pruebas de
    tests/test_overture_release.py, que solo miran que release se elige y no abren
    ninguna conexion, ni siquiera llegaban a recolectarse. Lo cazo la primera corrida
    del gate de pruebas (PR #119, E0.5 del Trust Gate).

    Efecto secundario del arreglo, y es el que importa: --solo-avisar ya no necesita
    la credencial. Antes, si el refresco fallaba PORQUE faltaba DATABASE_URL_OVERRIDE,
    el aviso moria por la misma causa que intentaba reportar.
    """
    if not DB_URL:
        print("❌ DATABASE_URL_OVERRIDE no está en el .env.")
        sys.exit(1)

import duckdb
import requests
import urllib3
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

urllib3.disable_warnings()  # verify=False para Overpass (SSL corporativo local)

OVERTURE_BUCKET = "overturemaps-us-west-2"
OVERTURE_LIST_URL = f"https://{OVERTURE_BUCKET}.s3.amazonaws.com/"

# Release de respaldo. Solo se usa si el descubrimiento falla por red, y es probable
# que para entonces ya no exista: ver la advertencia de abajo.
OVERTURE_RELEASE_FALLBACK = "2026-08-19.0"


def _releases_disponibles() -> list[str]:
    """Los releases que Overture tiene publicados AHORA, de más viejo a más nuevo.

    Se listan por la API de S3 (un GET con delimiter, no una descarga) en vez de por
    glob de DuckDB: glob no enumera prefijos y devuelve cero filas.
    """
    resp = requests.get(
        OVERTURE_LIST_URL,
        params={"list-type": "2", "prefix": "release/", "delimiter": "/"},
        timeout=30,
        verify=False,  # mismo criterio que Overpass: inspección SSL corporativa local
    )
    resp.raise_for_status()
    hallados = re.findall(r"<Prefix>release/([^<]+?)/</Prefix>", resp.text)
    return sorted(r for r in hallados if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.\d+", r))


def overture_release() -> str:
    """El release vigente. OVERTURE_RELEASE en el entorno lo fija a mano si hace falta.

    POR QUÉ SE DESCUBRE Y NO SE FIJA (2026-08-24, E0.2 del Trust Gate): hasta hoy esta
    ruta tenía escrito 'release/2026-06-17.0'. Overture NO conserva los releases
    viejos —el 2026-08-24 el bucket solo ofrecía 2026-07-22.0 y 2026-08-19.0—, así que
    el que estaba fijado había dejado de existir y la consulta leía un prefijo vacío.
    La tubería no estaba desactualizada: estaba rota, y en silencio, porque cero filas
    no es un error para DuckDB.

    Fijar un release es por eso una bomba de tiempo con la mecha ya encendida: funciona
    hasta que Overture rota, y entonces falla sin ruido. Preferimos preguntar.
    """
    fijado = os.getenv("OVERTURE_RELEASE", "").strip()
    if fijado:
        return fijado
    try:
        disponibles = _releases_disponibles()
    except Exception as exc:  # noqa: BLE001 — red caída: seguimos con el respaldo
        print(f"⚠️  No se pudo listar los releases de Overture ({type(exc).__name__}: {exc}).")
        print(f"    Se intentará con el respaldo {OVERTURE_RELEASE_FALLBACK}, que puede haber sido rotado.")
        return OVERTURE_RELEASE_FALLBACK
    if not disponibles:
        raise RuntimeError(
            "Overture no publicó ningún release con formato de fecha en "
            f"{OVERTURE_LIST_URL}release/. Puede haber cambiado la disposición del bucket."
        )
    # max() y no [-1]: elegir el más nuevo no puede depender de que el listado llegue
    # ordenado. Como los nombres son YYYY-MM-DD.N, el orden lexicográfico es el cronológico.
    return max(disponibles)


def overture_glob(release: str) -> str:
    return f"s3://{OVERTURE_BUCKET}/release/{release}/theme=places/type=place/*"

# ── Registro de mercados ────────────────────────────────────────────────────────
# Cada entrada ata el SLUG de ciudad a su bbox. Van juntos a propósito: así es
# imposible cargar el bbox de una ciudad etiquetado con el nombre de otra.
#
# Para abrir un mercado nuevo: agrega su entrada aquí y corre
#   python scripts/foso_pois_spike.py <slug>
# El script borra y recarga SOLO ese slug (`DELETE ... WHERE ciudad=`), nunca la
# tabla entera. Antes de la migración 019 esto era un TRUNCATE y abrir la segunda
# ciudad habría borrado Quito.
#
# El slug debe cumplir el CHECK de la migración 019: minúsculas, sin espacios.
# NO inventes el bbox: sácalo de un visor real (bboxfinder / OSM export) y déjalo
# anotado con la fecha en que lo mediste.
CIUDADES = {
    # slug: (xmin=oeste, xmax=este, ymin=sur, ymax=norte)   ← lon, lon, lat, lat
    "quito": dict(xmin=-78.60, xmax=-78.40, ymin=-0.35, ymax=-0.05),
    # "puebla":  dict(xmin=..., xmax=..., ymin=..., ymax=...),   # pendiente de medir
    # "mazatlan": dict(xmin=..., xmax=..., ymin=..., ymax=...),  # pendiente de medir
}
CIUDAD_DEFAULT = "quito"

# Se fijan en main() según la ciudad pedida por CLI.
CIUDAD = CIUDAD_DEFAULT
BBOX = CIUDADES[CIUDAD_DEFAULT]
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
         "overture_id", "osm_id", "marca", "direccion", "operativo", "fuente", "ciudad")


def _normalizar(p: dict) -> dict:
    d = {k: p.get(k) for k in _KEYS}
    d["ciudad"] = CIUDAD  # el slug del mercado en curso; nunca se toma del POI
    return d


def pull_overture() -> list[dict]:
    """Places del bbox de Quito en nuestras 6 categorías, confianza ≥ CONF_MIN."""
    release = overture_release()
    print(f"   Overture release: {release}")
    leaf_list = "', '".join(LEAF_TO_CAT.keys())
    con = duckdb.connect()
    try:
        con.execute("INSTALL spatial; INSTALL httpfs; LOAD spatial; LOAD httpfs; SET s3_region='us-west-2';")
        q = f"""
            SELECT id AS overture_id, names.primary AS nombre, categories.primary AS cat_leaf,
                   confidence, ST_Y(geometry) AS lat, ST_X(geometry) AS lon,
                   addresses[1].freeform AS direccion, brand.names.primary AS marca, operating_status
            FROM read_parquet('{overture_glob(release)}')
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

    # Cero filas de Overture NO es un resultado válido: el bbox de un mercado activo
    # siempre tiene comercios. Si esto pasa, o el release se rotó bajo nuestros pies o
    # cambió el esquema — y sin este corte el script seguiría hasta el cierre de POIs
    # dando la corrida por buena, que es exactamente como el fallo pasó desapercibido.
    if not raw:
        raise RuntimeError(
            f"Overture devolvió 0 filas para el release {release} y el bbox de {CIUDAD}. "
            "No se continúa: una recarga con cero POIs cerraría los existentes por ausencia."
        )
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
    "https://overpass.kumi.systems/api/interpreter",   # mirror de respaldo
    "https://overpass.private.coffee/api/interpreter",  # 3er mirror: los dos de arriba
    # cayeron JUNTOS dos veces el 27-28/07/2026 (504); un tercero independiente
    # baja la probabilidad de corrida incompleta del refresco semanal.
]


def pull_osm_transporte() -> list[dict]:
    """POIs de OSM: transporte + el comercio de barrio que Overture no ve. Overpass, sin auth.

    Overture es débil en dos frentes y OSM los cubre (mismo criterio, dos aplicaciones):
      - transporte: Overture Places no mapea paradas (su theme de transporte son calles).
      - comercio de barrio: medido 2026-07-27 en el bbox de Quito — OSM tiene 1.078
        `shop=convenience` (la tienda de esquina, que NO existía en nuestra capa),
        601 farmacias vs 466 de Overture y 341 supermercados vs 311. Esa era la brecha
        de paridad contra Google (+84 m en farmacia, +24 m en supermercado).
    En salud NO se suma OSM: Overture tiene 858 contra 498 de OSM (clinic+doctors).

    OSM es ODbL → almacenable CON atribución (a diferencia del contenido de Google
    Places, que los términos de esa plataforma no permiten guardar).
    """
    s, w, n, e = BBOX["ymin"], BBOX["xmin"], BBOX["ymax"], BBOX["xmax"]
    # `nwr` (node+way+relation), no `node`: gran parte del mundo real está mapeado como
    # POLÍGONO (el edificio de la iglesia, el perímetro del parque, el local de la
    # farmacia). Solo-nodos nos dejó ciegos a 1.198 parques, 315 iglesias, 171 farmacias
    # y 95 UPCs en Quito — destapado en el test en vivo del 2026-07-28, cuando "ruta al
    # parque" respondió Plaza Quitumbe a 28 min con el Parque Lineal Calicanto al lado.
    # `out body center` añade a ways/relations su centroide (center.lat/center.lon).
    query = f"""
    [out:json][timeout:120];
    (
      nwr["highway"="bus_stop"]({s},{w},{n},{e});
      nwr["amenity"="bus_station"]({s},{w},{n},{e});
      nwr["railway"="station"]({s},{w},{n},{e});
      nwr["railway"="subway_entrance"]({s},{w},{n},{e});
      nwr["public_transport"="station"]({s},{w},{n},{e});
      nwr["amenity"="pharmacy"]({s},{w},{n},{e});
      nwr["shop"="supermarket"]({s},{w},{n},{e});
      nwr["shop"="convenience"]({s},{w},{n},{e});
      nwr["amenity"="place_of_worship"]({s},{w},{n},{e});
      nwr["amenity"="police"]({s},{w},{n},{e});
      nwr["leisure"~"^(park|garden)$"]({s},{w},{n},{e});
    );
    out body center;
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
    if elems is None:  # todos los mirrors fallaron
        # Devuelve None (≠ lista vacía) para que el llamador NO confunda "Overpass caído"
        # con "OSM ya no tiene estos POIs" y no cierre nada. Ver incidente en CERRAR_*.
        print("   ⚠️ ningún endpoint de Overpass respondió — NO se cerrará ningún POI de OSM")
        return None
    out = []
    for el in elems:
        tags = el.get("tags", {}) or {}
        # Nodos traen lat/lon directo; ways/relations traen su centroide en `center`
        # (pedido con `out body center`).
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        # Subtipo → distingue el hub MASIVO (Metro/terminal, héroe de plusvalía) de la
        # simple parada de bus. Se guarda en categoria_overture (:cat_leaf) para que la
        # capa de producción priorice el masivo igual que _mejor_transporte con Google.
        # ── comercio (categorías nuevas 2026-07-27) ──────────────────────────
        # Sin nombre NO entra: "Encontré Farmacia a 200 m" es peor experiencia que
        # caer a Google. En transporte sí entra sin nombre (una parada anónima sigue
        # sirviendo). Medido: descarta ~40 farmacias y ~78 tiendas de 1.679.
        if tags.get("amenity") == "pharmacy":
            if not tags.get("name"):
                continue
            categoria, subtipo, nombre = "farmacia", "pharmacy", tags["name"]
        elif tags.get("shop") in ("supermarket", "convenience"):
            if not tags.get("name"):
                continue
            categoria = "supermercado"
            # El minimarket queda distinguible del supermercado grande en
            # categoria_overture, igual que parada_bus se distingue de metro. Hoy no
            # se prioriza uno sobre otro (gana el más cercano, y la preferencia de
            # marca ya favorece cadenas reconocibles); el subtipo deja la puerta
            # abierta a priorizar sin recargar.
            subtipo = "supermercado" if tags["shop"] == "supermarket" else "minimarket"
            nombre = tags["name"]
        elif tags.get("amenity") == "place_of_worship":
            if not tags.get("name"):
                continue
            categoria, subtipo, nombre = "iglesia", "place_of_worship", tags["name"]
        elif tags.get("amenity") == "police":
            # El PUESTO DE POLICÍA como servicio físico (igual que un hospital), NO una
            # medida de qué tan seguro es el barrio. El canon prohíbe lo segundo; esto
            # es un hecho con dirección. Ver migración 021 y el rótulo en _CAT_LABEL.
            if not tags.get("name"):
                continue
            categoria, subtipo, nombre = "seguridad", "police", tags["name"]
        elif tags.get("leisure") in ("park", "garden"):
            # Refuerzo a la categoría más flaca (Overture: 109 en todo Quito por su
            # umbral de confianza; OSM tiene 357 parques CON NOMBRE). Solo con nombre,
            # mismo criterio que el comercio: "ruta al parque" → "Parque" a secas no
            # aporta; los 800+ sin nombre son mayormente verde residual de barrio.
            if not tags.get("name"):
                continue
            categoria, subtipo, nombre = "parque", tags["leisure"], tags["name"]
        # ── transporte ───────────────────────────────────────────────────────
        elif tags.get("railway") == "subway_entrance" or tags.get("station") == "subway":
            categoria, subtipo, nombre = "transporte", "metro", tags.get("name") or "Estación de Metro"
        elif tags.get("railway") == "station":
            categoria, subtipo, nombre = "transporte", "estacion_tren", tags.get("name") or "Estación de tren"
        elif tags.get("amenity") == "bus_station":
            categoria, subtipo, nombre = "transporte", "terminal_bus", tags.get("name") or "Terminal de bus"
        elif tags.get("public_transport") == "station":
            categoria, subtipo, nombre = "transporte", "estacion", tags.get("name") or "Estación"
        elif tags.get("highway") == "bus_stop":
            categoria, subtipo, nombre = "transporte", "parada_bus", tags.get("name") or "Parada de bus"
        else:
            continue
        out.append(_normalizar({
            "nombre": nombre, "categoria": categoria, "cat_leaf": subtipo,
            "lat": lat, "lon": lon, "confidence": None,
            # "type/id" (formato estándar OSM): con `nwr`, el node 123 y el way 123 son
            # objetos DISTINTOS con el mismo número — sin prefijo, el índice único los
            # colapsaría en una fila. Migración 022 prefijó las filas previas (nodos).
            "overture_id": None, "osm_id": f"{el['type']}/{el['id']}", "marca": None,
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
    ciudad         text NOT NULL DEFAULT 'quito',
    actualizado_en timestamptz NOT NULL DEFAULT now()
);
-- idempotente: si la tabla ya existía de una corrida previa, agrega columnas nuevas
ALTER TABLE pois_propios ADD COLUMN IF NOT EXISTS osm_id text;
ALTER TABLE pois_propios ADD COLUMN IF NOT EXISTS fuente text NOT NULL DEFAULT 'overture';
ALTER TABLE pois_propios ADD COLUMN IF NOT EXISTS ciudad text NOT NULL DEFAULT 'quito';
CREATE INDEX IF NOT EXISTS pois_propios_geom_gix   ON pois_propios USING GIST (geom);
CREATE INDEX IF NOT EXISTS pois_propios_cat_idx    ON pois_propios (categoria);
CREATE INDEX IF NOT EXISTS pois_propios_ciudad_idx ON pois_propios (ciudad);
"""

# UPSERT por identificador de ORIGEN (migración 020). Reemplaza el DELETE+INSERT:
# la fila SOBREVIVE al refresco con su `id`, y con ella lo que le cuelgue (la curación
# del corredor, cuando exista). `actualizado_en` marca el último contacto con el origen.
# El WHERE del ON CONFLICT repite el predicado del índice parcial — Postgres lo exige
# para saber a qué índice apuntar.
_SET = """
        nombre = EXCLUDED.nombre,
        categoria = EXCLUDED.categoria,
        categoria_overture = EXCLUDED.categoria_overture,
        geom = EXCLUDED.geom,
        confianza = EXCLUDED.confianza,
        marca = EXCLUDED.marca,
        direccion = EXCLUDED.direccion,
        operativo = EXCLUDED.operativo,
        ciudad = EXCLUDED.ciudad,
        actualizado_en = now()
"""
_COLS = """(nombre, categoria, categoria_overture, geom, fuente, confianza,
            overture_id, osm_id, marca, direccion, operativo, ciudad)"""
_VALS = """(:nombre, :categoria, :cat_leaf, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
            :fuente, :confidence, :overture_id, :osm_id, :marca, :direccion, :operativo, :ciudad)"""

UPSERT_OVERTURE = text(f"""
    INSERT INTO pois_propios {_COLS} VALUES {_VALS}
    ON CONFLICT (overture_id) WHERE overture_id IS NOT NULL DO UPDATE SET {_SET}
""")
UPSERT_OSM = text(f"""
    INSERT INTO pois_propios {_COLS} VALUES {_VALS}
    ON CONFLICT (osm_id) WHERE osm_id IS NOT NULL DO UPDATE SET {_SET}
""")

# Lo que sigue en la tabla pero YA NO viene del origen: se marca cerrado, NO se borra.
# Un POI que desaparece de Overture/OSM puede ser un cierre real o un borrado erróneo
# del mapa; conservar la fila permite revertir y deja el historial.
#
# ⚠️ POR FUENTE, y NUNCA si la fuente falló. Incidente 2026-07-27: Overpass devolvió 504
# en sus dos endpoints, `pull_osm` degradó a lista vacía, y la versión anterior de esta
# sentencia —que miraba las dos fuentes juntas— marcó 3.924 POIs de OSM como cerrados.
# La guarda de "0 POIs cosechados" no saltó porque Overture SÍ había traído 2.851.
# Lección: "no pude consultar el origen" NO es "el POI ya no existe".
_CERRAR = """
    UPDATE pois_propios SET operativo = false, actualizado_en = now()
    WHERE ciudad = :ciudad AND operativo AND fuente = '{f}'
      AND {col} IS NOT NULL AND {col} <> ALL(CAST(:ids AS text[]))
"""
CERRAR_OVERTURE = text(_CERRAR.format(f="overture", col="overture_id"))
CERRAR_OSM = text(_CERRAR.format(f="osm", col="osm_id"))

# Si una fuente trae menos de esta fracción de lo que ya había, se asume respuesta
# parcial (no un cierre masivo real) y NO se cierra nada de esa fuente.
UMBRAL_CAIDA = 0.5

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
    global CIUDAD, BBOX
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = {a.lower() for a in sys.argv[1:] if a.startswith("-")}
    # El paso 4 es para leerlo con ojos humanos; en las corridas programadas solo
    # ensucia el log. `refresco_pois.cmd` lo pasa siempre.
    sin_validacion = "--sin-validacion" in flags
    CIUDAD = (args[0] if args else CIUDAD_DEFAULT).strip().lower()
    if CIUDAD not in CIUDADES:
        print(f"❌ Ciudad desconocida: {CIUDAD!r}")
        print(f"   Registradas: {', '.join(sorted(CIUDADES))}")
        print("   Para abrir un mercado nuevo, agrega su bbox al dict CIUDADES de este script.")
        sys.exit(1)
    BBOX = CIUDADES[CIUDAD]
    print(f"═══ Mercado: {CIUDAD.upper()} · bbox lon[{BBOX['xmin']}, {BBOX['xmax']}] "
          f"lat[{BBOX['ymin']}, {BBOX['ymax']}] ═══", flush=True)

    print("── 1) Overture Places (6 categorías, umbral de conf por categoría) ──", flush=True)
    t0 = time.time()
    pois = pull_overture()
    print(f"   {len(pois)} POIs Overture ({time.time()-t0:.0f}s)")
    print("── 2) OSM: transporte + comercio + culto/UPC (Overpass) ──", flush=True)
    t0 = time.time()
    transp = pull_osm_transporte()          # None = Overpass caído (≠ [] = sin resultados)
    osm_ok = transp is not None
    transp = transp or []
    print(f"   {len(transp)} POIs de OSM ({time.time()-t0:.0f}s)"
          + ("" if osm_ok else "  ⚠️ FUENTE CAÍDA"))
    pois += transp

    por_cat: dict[str, int] = {}
    for p in pois:
        por_cat[p["categoria"]] = por_cat.get(p["categoria"], 0) + 1
    for cat, n in sorted(por_cat.items(), key=lambda x: -x[1]):
        print(f"     {cat:16} {n}")

    if not pois:
        print("❌ Cero POIs cosechados — abortado ANTES de tocar la DB "
              "(si no, borraríamos la ciudad y la dejaríamos vacía).")
        sys.exit(1)

    # NullPool: una conexión secuencial. Ver la nota en scripts/asignar_corredor.py —
    # con el pool por defecto este script solo podría agotar el techo de Supabase.
    eng = create_engine(SYNC_URL, echo=False, poolclass=NullPool)
    with eng.begin() as db:
        print("── 3) Cargando a pois_propios ──", flush=True)
        for stmt in DDL.strip().split(";"):
            if stmt.strip():
                db.execute(text(stmt))

        # UPSERT por ciudad (migración 020). Antes era TRUNCATE (borraba TODOS los
        # mercados, migración 019) y luego DELETE+INSERT (perdía el `id` y la
        # antigüedad de cada POI). Ahora la fila sobrevive al refresco.
        otras = db.execute(text(
            "SELECT ciudad, count(*) FROM pois_propios WHERE ciudad <> :c GROUP BY 1"
        ), {"c": CIUDAD}).all()
        previos = db.execute(text(
            "SELECT count(*) FROM pois_propios WHERE ciudad = :c"), {"c": CIUDAD}).scalar()
        print(f"   en la tabla antes: {previos} POIs de '{CIUDAD}' · cosechados ahora: {len(pois)}")
        if otras:
            print("   intactas: " + ", ".join(f"{c}={n}" for c, n in otras))

        ov = [p for p in pois if p.get("overture_id")]
        osm = [p for p in pois if p.get("osm_id")]
        if ov:
            db.execute(UPSERT_OVERTURE, ov)
        if osm:
            db.execute(UPSERT_OSM, osm)

        # Cierre POR FUENTE, y solo si esa fuente respondió con volumen creíble.
        # Dos guardas, ambas nacidas del incidente del 2026-07-27 (ver CERRAR_*):
        #   (a) fuente caída  → no se cierra nada de ella.
        #   (b) caída brusca  → si trae <50% de lo que había, se asume respuesta parcial.
        cerrados = 0
        for nombre_f, filas, sent, ok in (
            ("overture", ov, CERRAR_OVERTURE, True),
            ("osm", osm, CERRAR_OSM, osm_ok),
        ):
            previos_f = db.execute(text(
                "SELECT count(*) FROM pois_propios WHERE ciudad=:c AND operativo AND fuente=:f"
            ), {"c": CIUDAD, "f": nombre_f}).scalar()
            if not ok:
                print(f"   ⚠️ '{nombre_f}' no respondió → NO se cierra ninguno de sus "
                      f"{previos_f} POIs")
                continue
            if previos_f and len(filas) < previos_f * UMBRAL_CAIDA:
                print(f"   ⚠️ '{nombre_f}' trajo {len(filas)} vs {previos_f} en tabla "
                      f"(<{UMBRAL_CAIDA:.0%}) → respuesta parcial, NO se cierra nada. Revisar.")
                continue
            ids = [p["overture_id" if nombre_f == "overture" else "osm_id"] for p in filas]
            cerrados += db.execute(sent, {"ciudad": CIUDAD, "ids": ids or [""]}).rowcount

        n = db.execute(text("SELECT count(*) FROM pois_propios WHERE ciudad = :c AND operativo"),
                       {"c": CIUDAD}).scalar()
        total = db.execute(text("SELECT count(*) FROM pois_propios")).scalar()
        print(f"   upsert: {len(ov)} Overture + {len(osm)} OSM · marcados cerrados: {cerrados}")
        print(f"   operativos en '{CIUDAD}': {n} ✅  (tabla completa, incl. cerrados: {total})")

    if sin_validacion:
        eng.dispose()
        _salir(osm_ok)

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
    _salir(osm_ok)


def avisar_ops(asunto: str, detalle: str) -> bool:
    """Manda un aviso operativo por Resend. Devuelve si se envió.

    POR QUÉ EXISTE (2026-08-24, E0.2 del Trust Gate): los códigos de salida de _salir()
    ya tenían señal desde el 2026-07-28, pero nadie los mira. La tarea de Windows escribe
    en logs\\ y ahí se queda. La prueba de que eso no basta es este mismo Trust Gate: el
    release de Overture llevaba semanas apuntando a un prefijo borrado y el fallo no
    llegó a ninguna parte.

    Se envía con requests, síncrono y a propósito: este script no puede usar asyncio
    (DuckDB + asyncio revienta el GIL en Windows, ver la cabecera del módulo), así que
    no se importa app.notifications.

    Sin RESEND_API_KEY o sin ALERTA_OPS_EMAIL no falla: informa por consola y sigue. Un
    aviso que no se puede mandar no debe convertirse en un segundo problema.
    """
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    destino = os.getenv("ALERTA_OPS_EMAIL", "").strip()
    if not api_key or not destino:
        falta = "RESEND_API_KEY" if not api_key else "ALERTA_OPS_EMAIL"
        print(f"⚠️  Aviso NO enviado (falta {falta}). El detalle era:\n{detalle}")
        return False
    remitente = os.getenv("NOTIFY_FROM_EMAIL", "Contexto <onboarding@resend.dev>")
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": remitente,
                "to": [d.strip() for d in destino.split(",") if d.strip()],
                "subject": asunto,
                "text": detalle,
            },
            timeout=20,
            verify=False,
        )
        resp.raise_for_status()
        print(f"📧 Aviso enviado a {destino}.")
        return True
    except Exception as exc:  # noqa: BLE001 — avisar nunca debe tumbar el refresco
        print(f"⚠️  No se pudo enviar el aviso ({type(exc).__name__}: {exc}).")
        print(detalle)
        return False


def _salir(osm_ok: bool):
    """Código de salida con SEÑAL, para que la tarea programada no corra a ciegas.

    Hasta 2026-07-28 esto salía siempre 0, incluso con Overpass caído: la corrida
    quedaba a medias y nadie se enteraba. Ahora:
      0 = las dos fuentes respondieron.
      2 = una fuente no respondió (los datos viejos quedaron intactos, no se cerró
          nada). Es REINTENTABLE — `refresco_pois.cmd` lo reintenta.
      1 = error duro (excepción sin capturar, o cero POIs cosechados).
    """
    if osm_ok:
        print("\n✅ Refresco completo — las dos fuentes respondieron.")
        sys.exit(0)
    print("\n⚠️ Refresco INCOMPLETO: Overpass no respondió. Overture sí se actualizó; "
          "los POIs de OSM quedaron como estaban (no se cerró ninguno). Reintentable.")
    sys.exit(2)


if __name__ == "__main__":
    # Modo aviso puro: refresco_pois.cmd lo invoca cuando agota sus reintentos, para que
    # una tubería caída deje de ser un log que nadie abre. No toca red de datos ni base.
    if "--solo-avisar" in sys.argv:
        # El motivo es lo que venga DESPUÉS de la bandera; el primer argumento suelto es
        # el slug de la ciudad y tomarlo daría un aviso que dice "Motivo: quito".
        _tras = sys.argv[sys.argv.index("--solo-avisar") + 1:]
        motivo = next((a for a in _tras if not a.startswith("--")), "motivo no indicado")
        avisar_ops(
            f"[Contexto] El refresco de POIs falló · {CIUDAD}",
            f"La tarea semanal de pois_propios terminó sin éxito tras sus reintentos.\n\n"
            f"Ciudad: {CIUDAD}\nMotivo/código: {motivo}\n\n"
            f"Revisar el log más reciente en logs\\refresco_pois_{CIUDAD}_*.log",
        )
        sys.exit(0)
    # El corte por credencial ausente vive aqui, no en el cuerpo del modulo: ver
    # exigir_credencial_de_base(). Va DESPUES de --solo-avisar a proposito.
    exigir_credencial_de_base()
    try:
        main()
    except SystemExit:
        raise  # _salir() ya dijo lo suyo con su código
    except Exception as exc:  # noqa: BLE001
        import traceback
        detalle = traceback.format_exc()
        print(f"\n❌ Error duro en el refresco de POIs: {type(exc).__name__}: {exc}")
        avisar_ops(
            f"[Contexto] Error duro en el refresco de POIs · {CIUDAD}",
            f"El refresco de pois_propios se detuvo con un error no recuperable.\n"
            f"No se reintenta: los datos viejos quedaron intactos.\n\n{detalle}",
        )
        sys.exit(1)
