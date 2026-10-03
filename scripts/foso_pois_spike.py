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
import hashlib
import json
import math
import os
import re
import sys
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    """psycopg en vez de asyncpg (este script es sincrono). La TLS NO va en la URL: la pone
    app/db_tls (verify-full contra el ancla de confianza) al abrir el engine. Antes se añadía
    aquí `sslmode=require`, que cifra pero no verifica a quién (#137, cliente MUST HARDEN); y
    hoy la política rechaza a propósito una URL remota que intente fijar TLS por su cuenta."""
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg://")


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

from app import db_tls
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

# ── POI-SOURCE-PROVENANCE (R4, migración 043) ─────────────────────────────────────────────────────
# Tres autoridades que no se mezclan:
#   FUENTE    lo que el proveedor dice de su registro: source_category, source_record_version,
#             source_lineage (por fila) · source_release, source_snapshot_at (corrida);
#   INGESTA   lo que Contexto VIO al leer: source_category_namespace, ingestion_run_id (fila) ·
#             reader_contract, source_schema_fingerprint, source_endpoint, code_sha, instantes, contadores,
#             estado y error (corrida);
#   CONTEXTO  `categoria`: la clasificación funcional. Jamás se escribe en `source_*`.
# Los LECTORES llevan versión: un cambio en la semántica de lectura exige una versión nueva, y la
# migración a `taxonomy` (R3) será OTRO lector, nunca este.
# `source_updated_at` = NULL en TODA fila (decisión del fundador, R1 · 2026-10-02): R4 CONSERVA la
# procedencia, no interpreta el tiempo de la fuente. En Overture, `sources[].update_time` puede ser la
# actualización del registro o la del dataset según el proveedor, y compararlo con `version` sería
# inferencia: queda ÍNTEGRO dentro de `source_lineage` (OVERTURE-SOURCE-TIME-SEMANTICS = DEFER TO R5).
# En OSM, `out body` no trae fecha por elemento. `_invalidas` rechaza cualquier fila que la traiga.
LECTOR_OVERTURE = "overture_places_categories_v1"   # `categories.primary`, el parser de siempre (D-4 sin reparar)
LECTOR_OSM = "osm_overpass_nwr_body_center_v1"      # la consulta `nwr … out body center` de siempre
NS_OVERTURE = "overture:categories.primary"
_PROC = ("source_category", "source_category_namespace", "source_record_version", "source_updated_at",
         "source_lineage")

# Claves comunes a TODO POI (Overture y OSM) — el executemany exige el mismo shape.
_KEYS = ("nombre", "categoria", "cat_leaf", "lon", "lat", "confidence",
         "overture_id", "osm_id", "marca", "direccion", "operativo", "fuente", "ciudad") + _PROC


def _normalizar(p: dict) -> dict:
    d = {k: p.get(k) for k in _KEYS}
    d["ciudad"] = CIUDAD  # el slug del mercado en curso; nunca se toma del POI
    return d


# ── R3 · OVERTURE TAXONOMY V1 (2026-10-02) ───────────────────────────────────────────────────────
# Overture v2.0.0 (2026-09-23.x) eliminó `categories`; la categoría vive en `taxonomy.primary` + `taxonomy.hierarchy`.
# Este es OTRO lector (el de `categories.primary`, `pull_overture`, queda intacto): lee la HOJA EXACTA y exige la RUTA
# EXACTA aceptada. Nunca un subárbol, nunca un nodo padre, nunca `basic_category`. Overture no declara versión de
# taxonomía en el dato: lo que se versiona es ESTE lector (cambiar la tabla o una ruta ⇒ `..._v2`).
# Evidencia de cada entrada: RESULTADO_2026-10-02_R3_OVERTURE_TAXONOMY_V1_CODE_DATA_PREFLIGHT.md §11/§15.
# `outpatient_care_facility` es la sucesora oficial de `medical_center` (D-R3-1): SOLO la hoja exacta; sus 128
# descendientes (dental, laboratorio, fisioterapia…) NO heredan `salud`.
LECTOR_OVERTURE_TAXONOMIA = "overture_places_taxonomy_v1"
NS_OVERTURE_TAXONOMIA = "overture:taxonomy.primary"
TAXONOMIA_V1: dict[str, tuple[tuple[str, ...], str]] = {   # hoja → (ruta aceptada, categoría de Contexto)
    "hospital":                 (("health_care", "hospital"), "salud"),
    "outpatient_care_facility": (("health_care", "outpatient_care_facility"), "salud"),
    "urgent_care_clinic":       (("health_care", "emergency_or_urgent_care_facility", "urgent_care_clinic"), "salud"),
    "pharmacy":                 (("shopping", "specialty_store", "pharmacy_and_drug_store", "pharmacy"), "farmacia"),
    "drugstore":                (("shopping", "specialty_store", "pharmacy_and_drug_store", "drugstore"), "farmacia"),
    "grocery_store":            (("shopping", "food_and_beverage_store", "grocery_store"), "supermercado"),
    "school":                   (("education", "place_of_learning", "school"), "educacion"),
    "college_university":       (("education", "place_of_learning", "college_university"), "educacion"),
    "preschool":                (("education", "place_of_learning", "school", "preschool"), "educacion"),
    "park":                     (("sports_and_recreation", "park"), "parque"),
    "playground":               (("sports_and_recreation", "park", "playground"), "parque"),
    "shopping_mall":            (("shopping", "shopping_mall"), "centro_comercial"),
    "department_store":         (("shopping", "department_store"), "centro_comercial"),
}


def huella_mapa_taxonomia(mapa: dict) -> str:
    """sha256 de la tabla (hoja, ruta aceptada, categoría), ordenada por hoja. Es la VERSIÓN de la regla."""
    canon = "\n".join(f"{h}\t{' > '.join(r)}\t{c}" for h, (r, c) in sorted(mapa.items()))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


HUELLA_TAXONOMIA_V1 = "8be8274fddeb14db474614767a60a3032ae22da0753b49ef1cc261c1502fec7a"
# El registro que hace RECONSTRUIBLE la regla de cada corrida: `poi_ingestion_run.reader_contract` → su tabla.
MAPAS_POR_LECTOR = {LECTOR_OVERTURE_TAXONOMIA: TAXONOMIA_V1}
# Nodos que son ANCESTRO de una hoja aceptada sin ser hoja aceptada (`health_care`, `education`, `shopping`…): un
# registro con `primary` en uno de ellos no determina UNA categoría de Contexto → no se ingiere (ambiguo).
ANCESTROS_V1 = frozenset(n for ruta, _ in TAXONOMIA_V1.values() for n in ruta[:-1]) - set(TAXONOMIA_V1)
# Los descendientes de cada ruta aceptada que YA existían en 2026-09-23.1 (agregado global del release, sha256
# 84e4df65…, evidencia del preflight R3). No se ingieren nunca (no heredan la categoría del padre); uno que NO esté
# aquí es un descendiente NUEVO: tampoco se ingiere, pero se AVISA (puede ser una división de una hoja aceptada).
DESCENDIENTES_CONOCIDOS_V1 = frozenset("""
acupuncture addiction_rehabilitation_center aesthetic_medicine allergy_and_immunology anesthesiology
animal_assisted_therapy architecture_school aromatherapy asian_grocery_store audiology ayurveda
behavior_analysis behavioral_or_mental_health_clinic body_contouring business_school cardiology
charter_school child_psychiatry childrens_hospital chiropractic community_health_center
complementary_and_alternative_medicine concierge_medicine cosmetic_dentistry counseling
crisis_intervention_service dental_clinic dental_hygiene dentistry_school dermatology diagnostic_imaging
doctors_office dog_park doula_service ear_nose_and_throat elementary_school endocrinology endodontics
endoscopy engineering_school environmental_medicine ethical_grocery_store family_counseling family_practice
gastroenterology general_dentistry general_hospital genetics geriatric_medicine geriatric_psychiatry
gerontology hematology hepatology high_school homeopathy hyperbaric_medicine hypnotherapy immunodermatology
indian_grocery_store infectious_disease internal_medicine international_grocery_store japanese_grocery_store
kindergarten korean_grocery_store kosher_grocery_store laboratory_testing lactation_service law_school
marriage_or_relationship_counseling maternity_center medical_sciences_school mexican_grocery_store
middle_school midwifery mobile_clinic montessori_school mountain_bike_park national_park
naturopathic_medicine nephrology neurology neuropathology neurotology nursing obstetrics_and_gynecology
occupational_medicine occupational_therapy oncology ophthalmology optometry organic_grocery_store
orthodontics orthopedics orthotics osteopathic_medicine otolaryngology otology pain_management
paternity_testing pathology pediatric_anesthesiology pediatric_cardiology pediatric_clinic
pediatric_dentistry pediatric_endocrinology pediatric_gastroenterology pediatric_infectious_disease
pediatric_nephrology pediatric_neurology pediatric_oncology pediatric_pulmonology pediatric_radiology
periodontics pharmacy_school phlebology physical_therapy podiatry prenatal_and_perinatal_care
preventive_medicine primary_care_or_general_clinic private_school proctology prosthetics prosthodontics
psychiatric_hospital psychiatry psychoanalysis psychology psychomotor_therapy psychotherapy
public_health_clinic public_school pulmonology radiology reflexology refractive_surgery_or_lasik
rehabilitation_center reiki religious_school reproductive_perinatal_and_womens_care retina_services
rheumatology russian_grocery_store science_school sex_therapy sleep_medicine specialized_health_care
specialty_hospital speech_therapy sports_medicine sports_psychology state_park stress_management_service
suicide_prevention_service tattoo_removal toxicology traditional_chinese_medicine tui_na ultrasound_imaging
urology vascular_medicine veterans_hospital veterinary_school vision_or_eye_care_clinic waldorf_school
water_park
""".split())
# Guarda de COBERTURA (D-R3-2): si una categoría de Contexto cae más de esto frente a la observación anterior, el
# lector no se cree el resultado (deriva de taxonomía probable) y Overture NO escribe ni cierra. NO es regla de cierre.
CAIDA_MAX_COBERTURA = 0.10

# R3 · OPERATING STATUS (contrato OFICIAL de Overture: `schema/places/place.yaml`, v2.0.0 = main, el mismo enum desde
# v1.16.0). `operating_status ∈ {open, permanently_closed, temporarily_closed}`: NO existe `closed`. Es OPCIONAL desde
# v1.17.0 (commit 7133a5a3, 2026-05-06) y, desde la nota de 2026-05-20, NULL por defecto («null instead of open»).
# NULL NO es `open`: es «sin señal de estado». La confianza mide EXISTENCIA, no estado (2026-09-23.1: 978 895
# `permanently_closed`, solo 4 744 con confidence 0). Evidencia: RESULTADO_2026-10-02_R3_OPERATING_STATUS_SEMANTICS_
# PREFLIGHT.md. Cada valor se clasifica EXPLÍCITAMENTE; nada se decide por «distinto de X».
ESTADOS_OPERATIVOS_V1 = ("open", "permanently_closed", "temporarily_closed")
ABIERTO, SIN_SENAL, CERRADO_TEMPORAL, CERRADO_PERMANENTE, ESTADO_INVALIDO = (
    "OPEN", "UNKNOWN_STATUS", "TEMPORARILY_CLOSED", "PERMANENTLY_CLOSED", "INVALID_STATUS")
_CLASE_DE_ESTADO = {None: SIN_SENAL, "open": ABIERTO, "temporarily_closed": CERRADO_TEMPORAL,
                    "permanently_closed": CERRADO_PERMANENTE}
CLASES_PRESENCIA = frozenset({ABIERTO, SIN_SENAL})                  # D-OS-1/2: la confianza de Contexto decide si entran
CLASES_CERRADAS = frozenset({CERRADO_TEMPORAL, CERRADO_PERMANENTE})  # D-OS-2: la confianza NO las filtra
CLASES_EXPLICITAS = frozenset({ABIERTO, CERRADO_TEMPORAL, CERRADO_PERMANENTE})   # la fuente AFIRMA un estado


def clase_de_estado(valor) -> str:
    """`operating_status` de la fuente → su clase (OPEN · UNKNOWN_STATUS · TEMPORARILY_CLOSED · PERMANENTLY_CLOSED ·
    INVALID_STATUS). Cualquier valor fuera del contrato es INVALID_STATUS: Overture entera queda ROTA (D-OS-5)."""
    return _CLASE_DE_ESTADO.get(valor, ESTADO_INVALIDO) if isinstance(valor, (str, type(None))) else ESTADO_INVALIDO


def categoria_de_la_regla(reader_contract: str | None, namespace: str | None, source_category: str | None) -> str | None:
    """RECONSTRUCCIÓN (M0): la categoría de Contexto que la regla de ESA corrida da a ESE valor de la fuente, o None.
    Fila → `ingestion_run_id` → `reader_contract` (+ `code_sha`) → esta tabla. Nunca se infiere de `categoria`."""
    if reader_contract in MAPAS_POR_LECTOR and namespace == NS_OVERTURE_TAXONOMIA:
        entrada = MAPAS_POR_LECTOR[reader_contract].get(source_category)
        return entrada[1] if entrada else None
    if reader_contract == LECTOR_OVERTURE and namespace == NS_OVERTURE:
        return LEAF_TO_CAT.get(source_category)
    return None


class GuardaTaxonomia(Exception):
    """Una guarda de R3 que invalida la fuente Overture ANTES de escribir o cerrar. `clase` es lo único que se
    persiste en la corrida (`error_class`); el texto (sin SQL ni URL) va al resumen."""

    def __init__(self, clase: str, detalle: str):
        super().__init__(detalle)
        self.clase = clase


def huella_esquema_overture(glob: str) -> str:
    """sha256 de la estructura que Contexto OBSERVA en el release (OBSERVACIÓN DE LA INGESTA).

    No es una versión declarada por Overture (el dato no la trae: el Parquet solo lleva `geo` 1.1.0 y
    `ARROW:schema`), ni «places/v2». Entra al hash, exactamente: cada columna de PRIMER nivel de
    `DESCRIBE SELECT * FROM read_parquet(<glob>)` como `nombre<TAB>tipo`, con el tipo COMPLETO tal como lo
    escribe DuckDB (los STRUCT y las LIST anidados incluidos, en su orden de campos); las líneas ordenadas
    por nombre (el orden físico no es material para un lector que selecciona por nombre) y unidas por
    `\\n`, en UTF-8. Misma estructura → misma huella; una columna o un tipo distintos → otra. Si el
    `DESCRIBE` falla, no hay huella: nunca se inventa."""
    con = duckdb.connect()
    try:
        con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
        filas = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{glob}')").fetchall()
    finally:
        con.close()
    canonica = "\n".join(sorted(f"{nombre}\t{tipo}" for nombre, tipo, *_ in filas))
    return hashlib.sha256(canonica.encode("utf-8")).hexdigest()


def pull_overture() -> list[dict]:
    """Places del bbox de Quito en nuestras 6 categorías, confianza ≥ CONF_MIN.

    El LECTOR es el de siempre (`categories.primary`): contra un release sin `categories` (esquema v2.0.0,
    2026-09-23.x) sigue fallando con BinderException — D-4 NO se repara aquí (R3). Lo único nuevo es que
    también lee `version` y `sources` (presentes en v1 y v2) para conservar la procedencia por fila."""
    release = overture_release()
    print(f"   Overture release: {release}")
    leaf_list = "', '".join(LEAF_TO_CAT.keys())
    con = duckdb.connect()
    try:
        con.execute("INSTALL spatial; INSTALL httpfs; LOAD spatial; LOAD httpfs; SET s3_region='us-west-2';")
        q = f"""
            SELECT id AS overture_id, names.primary AS nombre, categories.primary AS cat_leaf,
                   confidence, ST_Y(geometry) AS lat, ST_X(geometry) AS lon,
                   addresses[1].freeform AS direccion, brand.names.primary AS marca, operating_status,
                   version, sources
            FROM read_parquet('{overture_glob(release)}')
            WHERE bbox.xmin BETWEEN {BBOX['xmin']} AND {BBOX['xmax']}
              AND bbox.ymin BETWEEN {BBOX['ymin']} AND {BBOX['ymax']}
              AND confidence > {CONF_FLOOR}
              AND categories.primary IN ('{leaf_list}')
        """
        cols = ["overture_id", "nombre", "cat_leaf", "confidence", "lat", "lon",
                "direccion", "marca", "operating_status", "version", "sources"]
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
        # Procedencia (FUENTE): el valor de `categories.primary` TAL CUAL —el mismo que va a
        # `categoria_overture`, como exige la 043 para este espacio—, la versión del registro y su
        # `sources[]` VERBATIM (con su licencia, sin interpretarla). El espacio es de la INGESTA.
        r["source_category"] = r["cat_leaf"]
        r["source_category_namespace"] = NS_OVERTURE
        r["source_record_version"] = None if r.get("version") is None else str(r["version"])
        r["source_updated_at"] = None   # R4 no interpreta `update_time`: va íntegro en el linaje (R5)
        r["source_lineage"] = None if r.get("sources") is None else json.dumps(r["sources"], ensure_ascii=False)
        out.append(_normalizar(r))
    return out


# Lo que `pull_overture_taxonomia` observa de la CORRIDA (como ULTIMA_OSM): la observación estructurada (contadores),
# la deriva que invalida la fuente, las alertas (descendientes nuevos) y los GERS que la FUENTE declara cerrados.
ULTIMA_OVERTURE: dict = {}
# Los tipos EXACTOS de lo que el lector usa. Cualquier otro tipo (un campo nuevo en `taxonomy`, `hierarchy` como texto…)
# es un esquema que este lector no conoce: falla cerrado al obtener (Overture ROTA, sin escribir ni cerrar).
ESQUEMA_TAXONOMIA_V1 = {"id": "VARCHAR", "confidence": "DOUBLE", "operating_status": "VARCHAR", "version": "INTEGER",
                        "taxonomy": 'STRUCT("primary" VARCHAR, hierarchy VARCHAR[], alternates VARCHAR[])'}
COLUMNAS_TAXONOMIA_V1 = ("names", "geometry", "addresses", "brand", "sources", "bbox")


def _verifica_esquema_taxonomia(con, glob: str) -> None:
    tipos = {n: t for n, t, *_ in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{glob}')").fetchall()}
    malos = [f"{c}={tipos.get(c, 'AUSENTE')}" for c, t in ESQUEMA_TAXONOMIA_V1.items() if tipos.get(c) != t]
    malos += [f"{c}=AUSENTE" for c in COLUMNAS_TAXONOMIA_V1 if c not in tipos]
    if malos:
        raise GuardaTaxonomia("EsquemaInesperado", "esquema que el lector " + LECTOR_OVERTURE_TAXONOMIA
                              + " no conoce: " + ", ".join(malos))


def _hojas_ausentes_del_release(con, glob: str, hojas) -> list[str]:
    """De las hojas aceptadas que no aparecen en el bbox, cuáles NO existen en NINGÚN registro del release. Que falte
    en una ciudad es normal (Quito no tiene `drugstore`); que falte en el release entero es un renombre o una
    retirada: la regla ya no describe la taxonomía publicada. Medido: ~4 s si existe (se corta al primero), ~84 s si
    no (recorre el release)."""
    return [h for h in sorted(hojas) if not con.execute(
        f"SELECT count(*) FROM (SELECT 1 FROM read_parquet('{glob}') WHERE taxonomy.primary = ? LIMIT 1)", [h]
    ).fetchone()[0]]


def pull_overture_taxonomia() -> list[dict]:
    """El lector `overture_places_taxonomy_v1` (R3): Places del bbox → hoja exacta + ruta exacta → categoría de Contexto.

    Mantiene SEPARADAS cinco dimensiones que el lector de `categories` mezclaba (D-R3-2 + OPERATING STATUS):
      TAXONOMÍA        ¿`taxonomy.primary` es una hoja de la tabla versionada? (si no: NO se ingiere);
      JERARQUÍA        ¿`hierarchy` es EXACTAMENTE la ruta aceptada? (si no, en una hoja aceptada: DERIVA → Overture
                       ROTA con cualquier confianza y cualquier estado);
      CONFIANZA        el umbral de Contexto por categoría: decide la PRESENCIA (`open` / NULL), nunca un cierre;
      ESTADO FUENTE    `operating_status` clasificado EXPLÍCITAMENTE (`clase_de_estado`): OPEN · UNKNOWN_STATUS (NULL) ·
                       TEMPORARILY_CLOSED · PERMANENTLY_CLOSED · INVALID_STATUS (cualquier otro valor: Overture ROTA
                       ANTES de escribir, D-OS-5);
      ESTADO PREVIO    el de la fila en la capa: este lector NO lo conoce; la matriz se aplica en `escribir`
                       (`_matriz_de_estado`, misma transacción, antes del upsert).
    Devuelve las observaciones que la regla ACEPTA: de PRESENCIA (OPEN/NULL + mapa + ruta + confianza, `operativo=true`)
    y de CIERRE EXPLÍCITO (TEMPORARILY/PERMANENTLY_CLOSED + mapa + ruta, CUALQUIER confianza, `operativo=false`); la
    clase de cada GERS va aparte en `ULTIMA_OVERTURE["estados"]` (la forma de la fila no cambia). DURABILITY GUARD:
    en R3 v1 un estado observado NO autoriza ninguna transición de `operativo` (ver la matriz sobre
    `ESTADO_EN_CAPA_OVERTURE`): los cierres se OBSERVAN, se cuentan y se avisan; no se escriben. Un estado explícito
    (open / temporarily / permanently_closed) cuya observación la regla NO acepta (sin taxonomía, jerarquía inválida,
    fuera del mapa, nodo padre, descendiente, bajo la confianza) se cuenta en `explicitos_no_representables` y se avisa si
    implicaría una transición en la capa; la fila NO se toca: su procedencia vigente sigue explicando su `categoria`.
    Lo NO aceptado no se escribe y NO se cierra: «Contexto no lo ingirió» no es «el lugar cerró».
    Guardas que invalidan Overture entera (sin escribir ni cerrar): esquema distinto y estado fuera del contrato (al
    obtener), ruta distinta de la aceptada en una hoja aceptada y hoja aceptada que desaparece del release (en la
    validación de `obtener`)."""
    ULTIMA_OVERTURE.clear()
    if huella_mapa_taxonomia(TAXONOMIA_V1) != HUELLA_TAXONOMIA_V1:
        raise GuardaTaxonomia("MapaSinVersion", "la tabla de " + LECTOR_OVERTURE_TAXONOMIA + " cambió sin versión nueva")
    release = overture_release()
    glob = overture_glob(release)
    print(f"   Overture release: {release} · lector {LECTOR_OVERTURE_TAXONOMIA}")
    con = duckdb.connect()
    try:
        con.execute("INSTALL spatial; INSTALL httpfs; LOAD spatial; LOAD httpfs; SET s3_region='us-west-2';")
        _verifica_esquema_taxonomia(con, glob)
        filas = con.execute(f"""
            SELECT id, names.primary, taxonomy.primary, taxonomy.hierarchy, confidence, ST_Y(geometry), ST_X(geometry),
                   addresses[1].freeform, brand.names.primary, operating_status, version, sources
            FROM read_parquet('{glob}')
            WHERE bbox.xmin BETWEEN {BBOX['xmin']} AND {BBOX['xmax']}
              AND bbox.ymin BETWEEN {BBOX['ymin']} AND {BBOX['ymax']}
        """).fetchall()
        obs = {"registros_bbox": len(filas), "por_estado": Counter(), "aceptadas": Counter(),
               "bajo_confianza": Counter(), "fuera_del_mapa": 0, "nodo_padre": Counter(), "descendientes_conocidos": 0,
               "descendientes_nuevos": Counter(), "sin_taxonomia": 0, "jerarquia_invalida": 0,
               "ruta_distinta": Counter(), "cierres_explicitos_observados": Counter(),
               "explicitos_no_representables": Counter()}
        deriva, no_representables, presentes, out, estados, invalidos = [], {}, set(), [], {}, Counter()
        for (oid, nombre, primary, jerarquia, conf, lat, lon, direccion, marca, valor_estado, version,
             sources) in filas:
            clase = clase_de_estado(valor_estado)               # ESTADO FUENTE (explícito)
            obs["por_estado"][clase] += 1
            if clase == ESTADO_INVALIDO:
                invalidos[repr(valor_estado)] += 1
                continue
            cierre_explicito = clase in CLASES_CERRADAS
            motivo = None                           # por qué la regla NO acepta esta observación (None = aceptada)
            ruta = tuple(jerarquia or ())
            if primary is None:                                 # TAXONOMÍA
                obs["sin_taxonomia"] += 1
                motivo = "sin_taxonomia"
            elif not ruta or ruta[-1] != primary:               # JERARQUÍA (contrato de Overture)
                obs["jerarquia_invalida"] += 1      # viola el contrato de Overture: `primary` = último de `hierarchy`
                motivo = "jerarquia_invalida"
            elif primary in TAXONOMIA_V1:
                presentes.add(primary)
                aceptada, cat = TAXONOMIA_V1[primary]
                if ruta != aceptada:                            # JERARQUÍA (regla de Contexto)
                    # Deriva de la FUENTE, sea cual sea la confianza o el estado: ni `confidence` (regla de aceptación
                    # de Contexto) ni un cierre pueden ocultar que la taxonomía publicada ya no es la que la regla
                    # describe.
                    obs["ruta_distinta"][f"{primary} @ {' > '.join(ruta)}"] += 1
                    deriva.append(f"{primary}: ruta {' > '.join(ruta)} ≠ aceptada {' > '.join(aceptada)}")
                    motivo = "ruta_distinta"
                elif not cierre_explicito and (conf is None or conf <= CONF_FLOOR or conf < CONF_MIN[cat]):
                    obs["bajo_confianza"][cat] += 1                # CONFIANZA: solo decide la PRESENCIA (D-OS-2)
                    motivo = "bajo_confianza"
                else:
                    if cierre_explicito:
                        obs["cierres_explicitos_observados"][clase] += 1
                    else:
                        obs["aceptadas"][cat] += 1
                    estados[oid] = clase
                    out.append(_normalizar({
                        "nombre": nombre, "categoria": cat, "cat_leaf": None, "lon": lon, "lat": lat,
                        "confidence": conf, "overture_id": oid, "osm_id": None, "marca": marca, "direccion": direccion,
                        # PRESENCIA (OPEN / NULL) → true; CIERRE EXPLÍCITO (TEMPORARILY / PERMANENTLY_CLOSED) → false.
                        # Lo que la fila de la capa haga con esto lo decide la matriz (`_matriz_de_estado`).
                        "operativo": clase in CLASES_PRESENCIA, "fuente": "overture",
                        # FUENTE: `taxonomy.primary` TAL CUAL; la INGESTA declara el campo. `categoria_overture`
                        # (:cat_leaf) va NULL: v0 la rotula siempre `categories.primary` (I4 de la 043 lo exige).
                        "source_category": primary, "source_category_namespace": NS_OVERTURE_TAXONOMIA,
                        "source_record_version": None if version is None else str(version), "source_updated_at": None,
                        "source_lineage": None if sources is None else json.dumps(sources, ensure_ascii=False)}))
            elif primary in ANCESTROS_V1:
                obs["nodo_padre"][primary] += 1
                motivo = "nodo_padre"
            elif any(len(ruta) > len(a) and ruta[:len(a)] == a for a, _ in TAXONOMIA_V1.values()):
                if primary in DESCENDIENTES_CONOCIDOS_V1:
                    obs["descendientes_conocidos"] += 1
                else:
                    obs["descendientes_nuevos"][primary] += 1
                motivo = "descendiente"
            else:
                obs["fuera_del_mapa"] += 1
                motivo = "fuera_del_mapa"
            if clase in CLASES_EXPLICITAS and motivo is not None:
                # La fuente AFIRMA un estado que la regla NO acepta. El contrato actual (una sola procedencia por fila,
                # 043) no puede representarlo sin destruir la que explica la `categoria` vigente: se OBSERVA (cuenta,
                # GERS y su clase), se AVISA si implicaría una transición en la capa, y la fila NO se toca (R5).
                obs["explicitos_no_representables"][motivo] += 1
                no_representables[oid] = clase
        if invalidos:
            raise GuardaTaxonomia("EstadoOperativoInvalido",
                                  f"operating_status fuera del contrato {ESTADOS_OPERATIVOS_V1} + NULL: "
                                  + ", ".join(f"{v}×{n}" for v, n in sorted(invalidos.items())))
        desaparecidas = _hojas_ausentes_del_release(con, glob, set(TAXONOMIA_V1) - presentes)
    finally:
        con.close()
    deriva += [f"{h}: la hoja aceptada no existe en el release {release}" for h in desaparecidas]
    nuevos = dict(obs["descendientes_nuevos"])
    ULTIMA_OVERTURE.update({
        "observacion": {k: (dict(v) if isinstance(v, Counter) else v) for k, v in obs.items()},
        "deriva": sorted(set(deriva)), "explicitos_no_representables": no_representables, "estados": estados,
        "alertas": [f"descendiente NUEVO no ingerido: {p} ({n} registros)" for p, n in sorted(nuevos.items())]})
    if not out and not deriva:
        raise RuntimeError(f"Overture devolvió 0 filas aceptadas para el release {release} y el bbox de {CIUDAD}. "
                           "No se continúa.")
    return out


_OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",   # mirror de respaldo
    "https://overpass.private.coffee/api/interpreter",  # 3er mirror: los dos de arriba
    # cayeron JUNTOS dos veces el 27-28/07/2026 (504); un tercero independiente
    # baja la probabilidad de corrida incompleta del refresco semanal.
]

# Lo que `pull_overture`/`pull_osm_transporte` observan de la CORRIDA (no de una fila). Variables de módulo
# y no valores de retorno a propósito: `pull_*()` conserva su firma (las pruebas y los arneses la usan).
ULTIMA_OSM: dict = {}


def _instante_con_zona(texto) -> str | None:
    """Un instante ISO 8601 CON zona → ISO normalizado; sin zona, vacío o ilegible → None (no se supone UTC)."""
    if not isinstance(texto, str) or not texto.strip():
        return None
    try:
        dt = datetime.fromisoformat(texto.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.isoformat() if dt.tzinfo is not None and dt.utcoffset() is not None else None


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
    ULTIMA_OSM.clear()
    for url in _OVERPASS_ENDPOINTS:
        try:
            r = requests.post(url, data={"data": query}, headers=headers,
                              timeout=120, verify=False)
            r.raise_for_status()
            cuerpo = r.json()
            elems = cuerpo.get("elements", [])
            # Procedencia de la CORRIDA: qué mirror respondió y la instantánea que DECLARA Overpass
            # (`osm3s.timestamp_osm_base`). Con `out body` no llega ni `version` ni `timestamp` por elemento.
            ULTIMA_OSM["endpoint"] = url
            ULTIMA_OSM["snapshot_at"] = _instante_con_zona((cuerpo.get("osm3s") or {}).get("timestamp_osm_base"))
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
        # `etiqueta` = la (clave, valor) REAL que casó en esta cadena: es la categoría de la FUENTE.
        # El mapeo a `categoria`/subtipo (Contexto) NO cambia: solo se deja de perder qué etiqueta fue.
        if tags.get("amenity") == "pharmacy":
            if not tags.get("name"):
                continue
            categoria, subtipo, nombre = "farmacia", "pharmacy", tags["name"]
            etiqueta = ("amenity", "pharmacy")
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
            etiqueta = ("shop", tags["shop"])
        elif tags.get("amenity") == "place_of_worship":
            if not tags.get("name"):
                continue
            categoria, subtipo, nombre = "iglesia", "place_of_worship", tags["name"]
            etiqueta = ("amenity", "place_of_worship")
        elif tags.get("amenity") == "police":
            # El PUESTO DE POLICÍA como servicio físico (igual que un hospital), NO una
            # medida de qué tan seguro es el barrio. El canon prohíbe lo segundo; esto
            # es un hecho con dirección. Ver migración 021 y el rótulo en _CAT_LABEL.
            if not tags.get("name"):
                continue
            categoria, subtipo, nombre = "seguridad", "police", tags["name"]
            etiqueta = ("amenity", "police")
        elif tags.get("leisure") in ("park", "garden"):
            # Refuerzo a la categoría más flaca (Overture: 109 en todo Quito por su
            # umbral de confianza; OSM tiene 357 parques CON NOMBRE). Solo con nombre,
            # mismo criterio que el comercio: "ruta al parque" → "Parque" a secas no
            # aporta; los 800+ sin nombre son mayormente verde residual de barrio.
            if not tags.get("name"):
                continue
            categoria, subtipo, nombre = "parque", tags["leisure"], tags["name"]
            etiqueta = ("leisure", tags["leisure"])
        # ── transporte ───────────────────────────────────────────────────────
        elif tags.get("railway") == "subway_entrance" or tags.get("station") == "subway":
            categoria, subtipo, nombre = "transporte", "metro", tags.get("name") or "Estación de Metro"
            # Las dos etiquetas dan el MISMO subtipo; la procedencia guarda cuál fue (en el orden de la
            # condición: `railway` primero).
            etiqueta = (("railway", "subway_entrance") if tags.get("railway") == "subway_entrance"
                        else ("station", "subway"))
        elif tags.get("railway") == "station":
            categoria, subtipo, nombre = "transporte", "estacion_tren", tags.get("name") or "Estación de tren"
            etiqueta = ("railway", "station")
        elif tags.get("amenity") == "bus_station":
            categoria, subtipo, nombre = "transporte", "terminal_bus", tags.get("name") or "Terminal de bus"
            etiqueta = ("amenity", "bus_station")
        elif tags.get("public_transport") == "station":
            categoria, subtipo, nombre = "transporte", "estacion", tags.get("name") or "Estación"
            etiqueta = ("public_transport", "station")
        elif tags.get("highway") == "bus_stop":
            categoria, subtipo, nombre = "transporte", "parada_bus", tags.get("name") or "Parada de bus"
            etiqueta = ("highway", "bus_stop")
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
            # Procedencia: la etiqueta REAL (FUENTE) y su clave como espacio (INGESTA). `out body` no trae
            # versión ni fecha por elemento, ni hay `sources[]`: NULL, no se inventa.
            "source_category": etiqueta[1], "source_category_namespace": f"osm:{etiqueta[0]}",
            "source_record_version": None, "source_updated_at": None, "source_lineage": None,
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

# R4 · la procedencia va APARTE de las columnas de negocio (`_COLS`/`_VALS`/`_SET` no cambian: otros arneses
# las recomponen). Un UPSERT que vuelve a observar la fila la re-enlaza a la corrida ACTUAL y sobrescribe sus
# campos de origen; un cierre por AUSENCIA (CERRAR_OSM) no los toca. R3: Overture no tiene sentencia de cierre y, por la
# DURABILITY GUARD, este UPSERT solo da de alta filas nuevas activas o re-observa filas activas (`_matriz_de_estado`
# decide QUÉ filas; `_guarda_durabilidad` impide que cambie el `operativo` de ninguna fila existente).
_COLS_PROC = ("ingestion_run_id, source_category, source_category_namespace, source_record_version, "
              "source_updated_at, source_lineage")
_VALS_PROC = ("CAST(:ingestion_run_id AS uuid), :source_category, :source_category_namespace, :source_record_version, "
              "CAST(:source_updated_at AS timestamptz), CAST(:source_lineage AS jsonb)")
_SET_PROC = ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLS_PROC.split(", "))


def _mas(tupla: str, extra: str) -> str:
    """`(a, b)` + `c, d` → `(a, b, c, d)`."""
    return tupla.strip()[:-1].rstrip() + ",\n            " + extra + ")"


UPSERT_OVERTURE = text(f"""
    INSERT INTO pois_propios {_mas(_COLS, _COLS_PROC)} VALUES {_mas(_VALS, _VALS_PROC)}
    ON CONFLICT (overture_id) WHERE overture_id IS NOT NULL DO UPDATE SET {_SET.rstrip()},
        {_SET_PROC}
""")
UPSERT_OSM = text(f"""
    INSERT INTO pois_propios {_mas(_COLS, _COLS_PROC)} VALUES {_mas(_VALS, _VALS_PROC)}
    ON CONFLICT (osm_id) WHERE osm_id IS NOT NULL DO UPDATE SET {_SET.rstrip()},
        {_SET_PROC}
""")

# El MANIFIESTO de la corrida (migración 043). Lo inserta el escritor AL FINAL de la transacción de su fuente
# (la FK de `pois_propios.ingestion_run_id` es diferida); una fuente fallida, en una transacción propia.
_CORRIDA_COLS = ("id", "source_provider", "ciudad", "status", "reader_contract", "source_release",
                 "source_schema_fingerprint", "source_snapshot_at", "source_endpoint", "code_sha", "invocation_ref",
                 "started_at", "fetched_at", "completed_at", "rows_fetched", "rows_valid", "rows_written",
                 "rows_closed", "error_class", "error_phase")
_CORRIDA_CAST = {"id": "uuid", "source_snapshot_at": "timestamptz", "started_at": "timestamptz",
                 "fetched_at": "timestamptz", "completed_at": "timestamptz"}
INSERT_CORRIDA = text(
    f"INSERT INTO poi_ingestion_run ({', '.join(_CORRIDA_COLS)}) VALUES ("
    + ", ".join(f"CAST(:{c} AS {_CORRIDA_CAST[c]})" if c in _CORRIDA_CAST else f":{c}" for c in _CORRIDA_COLS) + ")")

# La COMPUERTA 043: sin el esquema exacto, el escritor no escribe NADA (ni POIs, ni cierres, ni corridas).
# Nombres sin esquema: se resuelven por `search_path`, como `pois_propios` en el resto del script.
FIRMA_PROC_043 = ("ingestion_run_id:uuid:f:f,source_category:text:f:f,source_category_namespace:text:f:f,"
                  "source_record_version:text:f:f,source_updated_at:timestamp with time zone:f:f,source_lineage:jsonb:f:f")
FIRMA_CORRIDA_043 = ("id:uuid:t:t,source_provider:text:t:f,ciudad:text:t:f,status:text:t:f,reader_contract:text:t:f,"
                     "source_release:text:f:f,source_schema_fingerprint:text:f:f,"
                     "source_snapshot_at:timestamp with time zone:f:f,source_endpoint:text:f:f,code_sha:text:t:f,"
                     "invocation_ref:text:f:f,started_at:timestamp with time zone:t:f,"
                     "fetched_at:timestamp with time zone:f:f,completed_at:timestamp with time zone:t:f,"
                     "rows_fetched:integer:f:f,rows_valid:integer:f:f,rows_written:integer:f:f,rows_closed:integer:f:f,"
                     "error_class:text:f:f,error_phase:text:f:f")
CKS_043 = ["ck_pois_categoria_fuente_con_espacio", "ck_pois_columna_legada_coherente", "ck_pois_corrida_exige_espacio",
           "ck_pois_espacio_de_su_fuente", "ck_pois_espacio_vocabulario", "ck_pois_linaje_forma",
           "ck_pois_procedencia_exige_corrida"]
_FIRMA = ("string_agg(attname || ':' || format_type(atttypid, atttypmod) || ':' || "
          "CASE WHEN attnotnull THEN 't' ELSE 'f' END || ':' || CASE WHEN atthasdef THEN 't' ELSE 'f' END, ',' ORDER BY attnum)")
VERIFICA_043 = text(rf"""
    SELECT to_regclass('poi_ingestion_run') IS NOT NULL AS corridas,
           (SELECT {_FIRMA} FROM pg_attribute WHERE attrelid = to_regclass('pois_propios') AND NOT attisdropped
              AND attname IN ('ingestion_run_id', 'source_category', 'source_category_namespace',
                              'source_record_version', 'source_updated_at', 'source_lineage')) AS firma_proc,
           (SELECT {_FIRMA} FROM pg_attribute WHERE attrelid = to_regclass('poi_ingestion_run') AND attnum > 0
              AND NOT attisdropped) AS firma_corrida,
           (SELECT count(*) FROM pg_constraint WHERE conrelid = to_regclass('pois_propios') AND contype = 'c'
              AND convalidated AND conname = ANY(CAST(:cks AS text[]))) AS cks_capa,
           (SELECT count(*) FROM pg_constraint WHERE conrelid = to_regclass('pois_propios') AND contype = 'f'
              AND conname = 'fk_pois_ingestion_run' AND condeferrable AND condeferred AND confdeltype = 'r'
              AND convalidated AND confrelid = to_regclass('poi_ingestion_run')) AS fk,
           (SELECT count(*) FROM pg_constraint WHERE conrelid = to_regclass('poi_ingestion_run') AND convalidated
              AND (conname LIKE 'ck\_pir\_%' OR conname = 'uq_pir_id_proveedor_ciudad')) AS cks_corrida
""")


def verificar_esquema_043(eng) -> list[str]:
    """Qué le falta a la base para el esquema 043 (vacío = completo). Solo lectura de catálogo. Si la base no
    responde, la excepción sube: el llamador la trata como «no se puede escribir»."""
    with eng.connect() as db:
        v = db.execute(VERIFICA_043, {"cks": CKS_043}).mappings().one()
    faltas = []
    if not v["corridas"]:
        faltas.append("no existe poi_ingestion_run")
    if v["firma_proc"] != FIRMA_PROC_043:
        faltas.append("las 6 columnas de procedencia de pois_propios no están exactas")
    if v["corridas"] and v["firma_corrida"] != FIRMA_CORRIDA_043:
        faltas.append("poi_ingestion_run no tiene las columnas exactas")
    if v["cks_capa"] != len(CKS_043):
        faltas.append(f"invariantes de pois_propios: {v['cks_capa']} de {len(CKS_043)}")
    if v["fk"] != 1:
        faltas.append("falta la FK diferida fk_pois_ingestion_run")
    if v["corridas"] and v["cks_corrida"] != 16:
        faltas.append(f"invariantes de poi_ingestion_run: {v['cks_corrida']} de 16")
    return faltas

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
CERRAR_OSM = text(_CERRAR.format(f="osm", col="osm_id"))
# R3 (D-R3-2) · en Overture la AUSENCIA ya NO cierra. Lo que el lector no aceptó (fuera del mapa, bajo la confianza
# de Contexto, taxonomía desconocida) o lo que no vino sigue siendo un lugar que la fuente NO dijo cerrado: marcarlo
# `operativo = false` sería afirmar un hecho que nadie observó. La semántica temporal de la ausencia es R5 · freshness.
# M0 · NO hay sentencia de cierre propia de Overture. La 043 guarda UNA procedencia vigente por fila, y esa procedencia
# tiene que seguir explicando la `categoria` vigente (procedencia → regla → categoría): todo cambio de una fila entra
# por el UPSERT normal, con la procedencia y la categoría de ESTA corrida.
# OPERATING STATUS · DURABILITY GUARD (R3 v1). Overture conserva sus releases públicos un máximo de ~60 días y el
# changelog no guarda el valor completo de `operating_status`; la 043 no tiene dónde conservarlo. Por eso, hasta que
# exista persistencia durable del estado fuente, OBSERVAR un estado ≠ AUTORIZAR una transición: ninguna transición de
# `operativo` puede depender de una observación de `operating_status` que Contexto no conserve. Se OBSERVA, se CLASIFICA,
# se CUENTA y se AVISA; el estado canónico no se mueve.
# MATRIZ TEMPORAL AUTORIZADA (sobre observaciones que la regla acepta: taxonomía + ruta exacta):
#
#                                 fila NUEVA               fila ACTIVA                    fila CERRADA
#   NULL               + conf OK  INSERT (activa)          UPDATE (sigue activa)          NO TOUCH · cuenta + aviso
#   OPEN               + conf OK  INSERT (activa)          UPDATE (sigue activa)          NO TOUCH · cuenta + aviso
#   TEMPORARILY_CLOSED (cualq.)   NO INSERT · cuenta+aviso NO TOUCH · cuenta + aviso      NO TOUCH · cuenta + aviso
#   PERMANENTLY_CLOSED (cualq.)   NO INSERT · cuenta+aviso NO TOUCH · cuenta + aviso      NO TOUCH · cuenta + aviso
#   INVALID_STATUS                Overture ROTA al obtener: no escribe, no cambia ningún estado
#
# Lo ÚNICO que se escribe: una fila NUEVA activa por PRESENCIA (OPEN/NULL; no es una transición de un estado canónico
# previo) y la re-observación de una fila ACTIVA que sigue activa. `_guarda_durabilidad` lo exige estructuralmente: si
# alguna escritura cambiara el `operativo` de una fila existente, o escribiera una fila cerrada, Overture queda ROTA sin
# escribir nada. Una observación explícita sobre una fila que ya está en ese estado TAMPOCO reemplaza su procedencia.
# DEUDA R5 (prerrequisito, documentada): preservar durablemente el estado fuente / la observación temporal ANTES de
# habilitar transiciones de estado canónico (reapertura por `open`, cierre por `temporarily/permanently_closed`).
# Esta lectura —misma transacción, SOLO LECTURA y ANTES del upsert— da el estado previo de cada GERS observado (aceptado
# o explícito no representable): de ella salen la matriz, la guarda y los avisos.
ESTADO_EN_CAPA_OVERTURE = text("""
    SELECT overture_id, operativo AS operativo_en_capa, categoria FROM pois_propios
    WHERE ciudad = :c AND fuente = 'overture' AND overture_id = ANY(CAST(:ids AS text[]))
""")
# R3 · la cobertura PREVIA por categoría contra la que se mide la caída: las filas operativas que observó la última
# corrida OK de Overture de esta ciudad; si no hubo ninguna (la primera corrida R3), todas las operativas de Overture
# (la capa legada). Solo lectura, dentro de la MISMA transacción y ANTES del upsert.
COBERTURA_PREVIA_OVERTURE = text("""
    SELECT categoria, count(*) AS cobertura_previa FROM pois_propios
    WHERE ciudad = :c AND fuente = 'overture' AND operativo
      AND (ingestion_run_id = (SELECT id FROM poi_ingestion_run
                               WHERE source_provider = 'overture' AND ciudad = :c AND status = 'ok'
                               ORDER BY completed_at DESC LIMIT 1)
           OR NOT EXISTS (SELECT 1 FROM poi_ingestion_run
                          WHERE source_provider = 'overture' AND ciudad = :c AND status = 'ok'))
    GROUP BY 1
""")

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



# ── POI-REFRESH-SOURCE-ISOLATION (2026-10-02) · cada fuente es independiente ──────────
#
# EL DEFECTO (corrida #7 del workflow, 2026-09-29): Overture publicó su esquema v2.0.0 sin
# `categories`, y `pull_overture()` lanzó BinderException ANTES de que se descargara OSM. Como
# además toda la carga vivía en UNA transacción, el refresco entero abortaba: OSM, que no depende
# de Overture, quedó congelado con ella. Ahora:
#   · cada fuente se OBTIENE y se VALIDA por separado; su fallo queda en SU estado y no impide
#     la otra;
#   · cada fuente se ESCRIBE en SU propia transacción (upsert + cierre): atómica dentro de la
#     fuente, independiente entre fuentes. Un fallo al escribir una no revierte la otra;
#   · una fuente que no se obtuvo, no se validó o no se escribió NO cierra nada, NO cuenta como
#     «0 filas» y NO se reporta como refrescada.
# Lo que NO cambia: las consultas, el mapeo, los umbrales, el upsert, las sentencias de cierre y
# sus guardas (que se evalúan en el mismo punto que antes: tras el upsert de esa fuente).
FUENTE_OK = "ok"
FUENTE_CAIDA = "caida"   # no respondió (red, HTTP): reintentable
FUENTE_ROTA = "rota"     # error duro (esquema, datos inválidos, escritura): reintentar no ayuda
_ETIQUETA = {FUENTE_OK: "OK", FUENTE_CAIDA: "CAÍDA", FUENTE_ROTA: "ROTA"}

# Lo que una fila puede ser, por fuente: la estructura que ya producen los pull. Es una guarda
# ESTRUCTURAL (no se escribe basura); el mapeo y los umbrales ya los aplicó el pull.
_CATS_OSM = frozenset({"transporte", "supermercado", "farmacia", "iglesia", "seguridad", "parque"})
_ID_OSM = re.compile(r"^(node|way|relation)/\d+$")


@dataclass
class ResultadoFuente:
    """Lo que pasó con UNA fuente en esta corrida. Es lo que se resume, se guarda y se avisa."""

    fuente: str                                   # 'overture' | 'osm'
    estado: str | None = None
    release: str | None = None
    filas: list | None = field(default=None, repr=False)
    obtenidas: int | None = None
    validadas: int | None = None
    escritas: int = 0
    cerradas: int = 0
    segundos: float = 0.0
    fase: str | None = None                       # dónde falló: obtencion | validacion | escritura
    error: str | None = None                      # clase (+ 1.ª línea al obtener). Nunca SQL ni URL.
    # ── R4 · la CORRIDA (poi_ingestion_run) ──
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    clase: str | None = None                      # SOLO la clase del error: lo único que se persiste
    started_at: str | None = None
    fetched_at: str | None = None
    endpoint: str | None = None
    snapshot_at: str | None = None                # OSM: osm3s.timestamp_osm_base
    schema_fingerprint: str | None = None         # Overture: huella del esquema OBSERVADO
    manifiesto: str | None = None                 # 'persistido' | 'NOT PERSISTED'
    # ── R3 · el lector que se ejecutó y lo que observó (sin migración: va al resumen, al estado y al aviso) ──
    lector: str | None = None                     # → poi_ingestion_run.reader_contract
    observacion: dict | None = None               # contadores: aceptadas, bajo_confianza, fuera_del_mapa, nodo_padre…
    alertas: list = field(default_factory=list)   # p. ej. descendientes nuevos (no se ingieren, se avisan)
    explicitos_no_representables: dict = field(default_factory=dict, repr=False)   # GERS → clase del estado explícito no aceptado
    estados: dict = field(default_factory=dict, repr=False)    # OPERATING STATUS: GERS aceptado → su clase de estado

    def linea(self) -> str:
        def v(x):
            return "-" if x is None else x
        return (f"fuente={self.fuente} release={v(self.release)} estado={_ETIQUETA.get(self.estado, self.estado)} "
                f"obtenidas={v(self.obtenidas)} validadas={v(self.validadas)} escritas={self.escritas} "
                f"cerradas={self.cerradas} segundos={self.segundos:.1f}"
                + (f" fase_error={self.fase} error={self.error}" if self.error else ""))

    def resumen(self) -> dict:
        return {k: getattr(self, k) for k in ("fuente", "estado", "release", "obtenidas", "validadas",
                                               "escritas", "cerradas", "segundos", "fase", "error",
                                               "run_id", "manifiesto", "lector", "observacion", "alertas")}


def _primera_linea(exc: BaseException) -> str:
    """Clase + primera línea del mensaje, recortada. Para errores de OBTENCIÓN (fuente pública)."""
    texto = (str(exc).strip().splitlines() or [""])[0]
    return f"{type(exc).__name__}: {texto[:160]}" if texto else type(exc).__name__


def _es_caida(exc: BaseException) -> bool:
    """¿La fuente NO RESPONDIÓ (red, HTTP), o respondió y lo que dio no sirve? Lo primero se
    reintenta; lo segundo no (un esquema roto no se arregla en 10 minutos)."""
    return isinstance(exc, (requests.ConnectionError, requests.Timeout, duckdb.HTTPException))


def _invalidas(fuente: str, filas, lector: str | None = None, estados: dict | None = None) -> list[str]:
    """Por qué el conjunto NO es escribible (vacío = válido). Una sola fila mala invalida la FUENTE
    entera: escribir el resto sería una escritura parcial de esa fuente. La coherencia de la procedencia se juzga
    con la regla del LECTOR que produjo las filas (por defecto, el lector vigente de cada fuente). Con `estados`
    (OPERATING STATUS), cada fila de Overture tiene que tener una clase de estado válida y su `operativo` tiene que ser
    EXACTAMENTE el de esa clase (presencia → true, cierre explícito → false)."""
    lector = lector or (LECTOR_OVERTURE_TAXONOMIA if fuente == "overture" else LECTOR_OSM)
    if not isinstance(filas, list):
        return [f"la fuente no devolvió una lista ({type(filas).__name__})"]
    motivos: Counter = Counter()
    for p in filas:
        if not isinstance(p, dict) or set(p) != set(_KEYS):
            motivos["forma de fila distinta"] += 1
            continue
        if p["fuente"] != fuente or p["ciudad"] != CIUDAD:
            motivos["fuente o ciudad ajena"] += 1
        if fuente == "overture":
            if not (isinstance(p["overture_id"], str) and p["overture_id"].strip()) or p["osm_id"] is not None:
                motivos["identificador de Overture"] += 1
            if p["categoria"] not in CONF_MIN:
                motivos["categoría"] += 1
        else:
            if not (isinstance(p["osm_id"], str) and _ID_OSM.match(p["osm_id"])) or p["overture_id"] is not None:
                motivos["identificador de OSM"] += 1
            if p["categoria"] not in _CATS_OSM:
                motivos["categoría"] += 1
        if not all(isinstance(p[k], (int, float)) and not isinstance(p[k], bool) and math.isfinite(p[k])
                   for k in ("lat", "lon")):
            motivos["coordenadas"] += 1
        # R4 · procedencia coherente ANTES de tocar la base (la 043 lo exige igual; aquí falla cerrado sin
        # escribir): toda fila declara de qué campo sale su categoría de origen, del MISMO dataset; en Overture,
        # `categories.primary` es el valor de `categoria_overture` tal cual (el que lee Place Evidence v0).
        ns, cat_origen = p.get("source_category_namespace"), p.get("source_category")
        if fuente == "overture" and lector == LECTOR_OVERTURE_TAXONOMIA:
            # R3: `taxonomy.primary` en su espacio, la columna legada NULL (I4) y la categoría = la de la tabla v1.
            entrada = TAXONOMIA_V1.get(cat_origen)
            if (ns != NS_OVERTURE_TAXONOMIA or p["cat_leaf"] is not None or entrada is None
                    or entrada[1] != p["categoria"]):
                motivos["procedencia de la categoría"] += 1
            if estados is not None:
                clase = estados.get(p["overture_id"])
                if (clase not in CLASES_PRESENCIA | CLASES_CERRADAS
                        or p["operativo"] is not (clase in CLASES_PRESENCIA)):
                    motivos["estado operativo de la fuente"] += 1
        elif fuente == "overture":
            if ns != NS_OVERTURE or cat_origen != p["cat_leaf"] or not cat_origen:
                motivos["procedencia de la categoría"] += 1
        elif not (isinstance(ns, str) and ns.startswith("osm:") and isinstance(cat_origen, str) and cat_origen):
            motivos["procedencia de la categoría"] += 1
        if fuente == "osm" and any(p.get(k) is not None for k in
                                   ("source_record_version", "source_updated_at", "source_lineage")):
            motivos["procedencia que OSM no entrega"] += 1
        if p.get("source_updated_at") is not None:
            motivos["source_updated_at: R4 no interpreta el tiempo de la fuente (R5)"] += 1
    return [f"{n} fila(s) con {m}" for m, n in motivos.items()]


def _ahora() -> str:
    """Reloj de la corrida (UTC, con zona). Un solo reloj —el del proceso— para started/fetched/completed."""
    return datetime.now(timezone.utc).isoformat()


_SHA = re.compile(r"[0-9a-f]{40}")


def code_sha() -> str | None:
    """El SHA EXACTO del código que corre, o None (FAIL CLOSED). En GitHub Actions, `GITHUB_SHA` (el commit que
    el runner sacó); fuera de Actions, SOLO la vía explícita `REFRESCO_POIS_CODE_SHA`. Nunca un nombre de rama,
    «main», «latest» ni un `git rev-parse` de un árbol que podría estar modificado: 40 hex en minúsculas o nada."""
    v = os.getenv("GITHUB_SHA", "") if os.getenv("GITHUB_ACTIONS") == "true" else os.getenv("REFRESCO_POIS_CODE_SHA", "")
    v = (v or "").strip()
    return v if _SHA.fullmatch(v) else None


def invocation_ref() -> str | None:
    """Referencia NO secreta y reproducible de la ejecución: `github-actions:<workflow>:<run_id>:<attempt>` en
    Actions; fuera, `REFRESCO_POIS_INVOCATION_REF` si se fija, o NULL. Sin URLs ni tokens."""
    if os.getenv("GITHUB_ACTIONS") == "true" and os.getenv("GITHUB_RUN_ID", "").isdigit():
        flujo = re.sub(r"[^A-Za-z0-9_.-]", "_", os.getenv("GITHUB_WORKFLOW", "") or "-")[:60]
        intento = os.getenv("GITHUB_RUN_ATTEMPT", "1")
        return f"github-actions:{flujo}:{os.getenv('GITHUB_RUN_ID')}:{intento if intento.isdigit() else '1'}"
    v = (os.getenv("REFRESCO_POIS_INVOCATION_REF") or "").strip()
    return v[:120] if v else None


class _SinNadaQueEscribir(Exception):
    """Control de flujo: sin fuente útil (o sin el esquema 043) no hay DDL T0 ni foto previa."""


def _pull_overture_con_release(r: "ResultadoFuente") -> list[dict]:
    """El lector VIGENTE de Overture (R3: `pull_overture_taxonomia`, `overture_places_taxonomy_v1`) con el release que
    eligió anotado en el resultado. Se resuelve una vez y se le pasa por OVERTURE_RELEASE para que el anotado sea
    exactamente el leído. Antes de leer, Contexto OBSERVA la estructura del release (`huella_esquema_overture`): si
    eso falla, no hay huella; si lo que falla después es el lector (p. ej. un esquema que no conoce), la huella
    observada SÍ queda en la corrida ROTA. El lector de `categories.primary` (`pull_overture`) ya no se ejecuta: desde
    v2.0.0 ese campo no existe (D-4)."""
    r.release = overture_release()
    r.endpoint = overture_glob(r.release)
    r.schema_fingerprint = huella_esquema_overture(r.endpoint)
    previo = os.environ.get("OVERTURE_RELEASE")
    os.environ["OVERTURE_RELEASE"] = r.release
    try:
        return pull_overture_taxonomia()
    finally:
        if previo is None:
            os.environ.pop("OVERTURE_RELEASE", None)
        else:
            os.environ["OVERTURE_RELEASE"] = previo


def obtener(fuente: str) -> ResultadoFuente:
    """Descarga y valida UNA fuente. Nunca lanza: lo que pase queda en el resultado."""
    r = ResultadoFuente(fuente)
    r.lector = LECTOR_OVERTURE_TAXONOMIA if fuente == "overture" else LECTOR_OSM
    r.started_at = _ahora()
    t0 = time.time()
    try:
        filas = _pull_overture_con_release(r) if fuente == "overture" else pull_osm_transporte()
    except Exception as exc:  # noqa: BLE001 — se registra en SU estado; la otra fuente sigue
        r.estado = FUENTE_CAIDA if _es_caida(exc) else FUENTE_ROTA
        # Una guarda de R3 persiste SU clase (EsquemaInesperado, MapaSinVersion); el resto, la de la excepción.
        r.fase, r.error, r.clase = "obtencion", _primera_linea(exc), getattr(exc, "clase", None) or type(exc).__name__
        r.segundos = time.time() - t0
        print(f"   ❌ {fuente}: {r.error}")
        return r
    r.segundos = time.time() - t0
    if fuente == "osm":
        r.endpoint, r.snapshot_at = ULTIMA_OSM.get("endpoint"), ULTIMA_OSM.get("snapshot_at")
    if filas is None:  # contrato de pull_osm_transporte: None = ningún endpoint respondió (≠ [])
        r.estado, r.fase, r.error, r.clase = FUENTE_CAIDA, "obtencion", "ningún endpoint respondió", "SinRespuesta"
        return r
    r.fetched_at = _ahora()
    r.obtenidas = len(filas) if isinstance(filas, list) else None
    if fuente == "overture":
        r.observacion = ULTIMA_OVERTURE.get("observacion")
        r.alertas = list(ULTIMA_OVERTURE.get("alertas") or [])
        r.explicitos_no_representables = dict(ULTIMA_OVERTURE.get("explicitos_no_representables") or {})
        r.estados = dict(ULTIMA_OVERTURE.get("estados") or {})
        deriva = ULTIMA_OVERTURE.get("deriva") or []
        if deriva:
            # R3 · la regla ya no describe la taxonomía publicada (ruta distinta o hoja desaparecida): Overture
            # ENTERA queda ROTA, antes de cualquier escritura o cierre. OSM sigue en lo suyo.
            r.estado, r.fase, r.clase = FUENTE_ROTA, "validacion", "DerivaTaxonomia"
            r.error = ("deriva de taxonomía: " + "; ".join(deriva))[:300]
            print(f"   ❌ {fuente}: {r.error}")
            return r
    invalidas = _invalidas(fuente, filas, r.lector, r.estados if fuente == "overture" else None)
    if fuente == "overture" and not (r.release and r.schema_fingerprint):
        # La 043 exige release + huella en una corrida OK de Overture: sin ellas, la estructura no se observó.
        invalidas.append("release o huella de esquema no observados")
    if invalidas:
        r.estado, r.fase, r.clase = FUENTE_ROTA, "validacion", "DatasetInvalido"
        r.error = ("dataset inválido: " + "; ".join(invalidas))[:300]
        print(f"   ❌ {fuente}: {r.error}")
        return r
    r.validadas, r.filas, r.estado = len(filas), filas, FUENTE_OK
    return r


def _manifiesto(r: ResultadoFuente, ident: dict, **contadores) -> dict:
    """La fila de `poi_ingestion_run` de ESTA corrida. Lo que no se observó, va NULL."""
    ok = r.estado == FUENTE_OK
    return {"id": r.run_id, "source_provider": r.fuente, "ciudad": CIUDAD, "status": r.estado,
            "reader_contract": r.lector or (LECTOR_OVERTURE_TAXONOMIA if r.fuente == "overture" else LECTOR_OSM),
            "source_release": r.release if r.fuente == "overture" else None,
            "source_schema_fingerprint": r.schema_fingerprint if r.fuente == "overture" else None,
            "source_snapshot_at": r.snapshot_at if r.fuente == "osm" else None,
            "source_endpoint": r.endpoint, "code_sha": ident["code_sha"], "invocation_ref": ident["invocation_ref"],
            "started_at": r.started_at, "fetched_at": r.fetched_at, "completed_at": _ahora(),
            "rows_fetched": r.obtenidas, "rows_valid": r.validadas,
            "rows_written": contadores.get("escritas") if ok else None,
            "rows_closed": contadores.get("cerradas") if ok else None,
            "error_class": None if ok else r.clase, "error_phase": None if ok else r.fase}


def registrar_fallo(eng, r: ResultadoFuente, ident: dict) -> None:
    """Una fuente CAÍDA o ROTA deja su corrida en una transacción PROPIA y pequeña, sin ninguna fila de POIs.
    Si ni eso se puede guardar, se dice: MANIFEST NOT PERSISTED. Sin reintento, sin fingir éxito."""
    try:
        with eng.begin() as db:
            db.execute(INSERT_CORRIDA, _manifiesto(r, ident))
        r.manifiesto = "persistido"
    except Exception as exc:  # noqa: BLE001 — el aviso de la fuente fallida ya sale por _salir
        r.manifiesto = "NOT PERSISTED"
        print(f"   ⚠️ {r.fuente}: MANIFEST NOT PERSISTED ({type(exc).__name__})")


# DURABILITY GUARD · las ÚNICAS decisiones que escriben: alta de una fila nueva activa y re-observación de una activa.
_ESCRIBEN = frozenset({"insertadas", "actualizadas"})
# Las que se cuentan Y se avisan (el estado observado querría mover la fila; no hay evidencia durable para hacerlo).
_AVISAN = ("reobservadas_sin_open_explicito", "explicit_open_on_closed", "temporary_closed_on_active",
           "permanent_closed_on_active", "explicit_close_on_closed", "explicit_close_new")


def _decision(clase: str, previo: tuple | None) -> str:
    """UNA celda de la matriz temporal (ver DURABILITY GUARD sobre `ESTADO_EN_CAPA_OVERTURE`). `previo` = (operativo,
    categoria) de la fila en la capa, o None si el GERS no está. Explícita para cada clase: nada por «distinto de X»."""
    if clase == SIN_SENAL:
        if previo is None:
            return "insertadas"
        return "actualizadas" if previo[0] else "reobservadas_sin_open_explicito"
    if clase == ABIERTO:
        if previo is None:
            return "insertadas"
        return "actualizadas" if previo[0] else "explicit_open_on_closed"        # reabrir exige evidencia durable
    if clase == CERRADO_TEMPORAL:
        if previo is None:
            return "explicit_close_new"
        return "temporary_closed_on_active" if previo[0] else "explicit_close_on_closed"
    if clase == CERRADO_PERMANENTE:
        if previo is None:
            return "explicit_close_new"
        return "permanent_closed_on_active" if previo[0] else "explicit_close_on_closed"
    raise ValueError(f"clase de estado no válida en la matriz: {clase!r}")   # INVALID no llega aquí (rota al obtener)


def _guarda_durabilidad(filas: list[dict], capa: dict) -> None:
    """DURABILITY GUARD (R3 v1), estructural: NINGUNA escritura puede cambiar el `operativo` de una fila existente ni
    escribir una fila cerrada. Solo pasan: fila NUEVA con `operativo=true` y fila EXISTENTE activa que sigue activa.
    Si algo más llegara aquí (un error de la matriz), Overture queda ROTA sin escribir nada."""
    malas = [p["overture_id"] for p in filas
             if p["operativo"] is not True or (capa.get(p["overture_id"]) is not None and capa[p["overture_id"]][0] is not True)]
    if malas:
        raise GuardaTaxonomia("TransicionSinEvidenciaDurable",
                              f"{len(malas)} escritura(s) cambiarían el estado canónico sin evidencia durable del estado "
                              f"fuente (R5): " + ", ".join(malas[:10]))


def _matriz_de_estado(db, r: ResultadoFuente) -> tuple[list[dict], Counter, dict, list[str]]:
    """OPERATING STATUS · en la MISMA transacción, SOLO LECTURA y ANTES del upsert: el estado previo de cada GERS
    observado → la decisión de la matriz temporal → la guarda de durabilidad. Devuelve (filas que se escriben, conteo
    por decisión, GERS de las decisiones que se avisan, GERS de la capa a los que un estado explícito NO representable
    les implicaría una transición)."""
    ids = [p["overture_id"] for p in r.filas] + list(r.explicitos_no_representables)
    capa = {}
    if ids:
        capa = {oid: (op, cat) for oid, op, cat in db.execute(ESTADO_EN_CAPA_OVERTURE, {"c": CIUDAD, "ids": ids}).all()}
    escribir_, conteo, avisos = [], Counter(), {k: [] for k in _AVISAN}
    for p in r.filas:
        decision = _decision(r.estados[p["overture_id"]], capa.get(p["overture_id"]))
        conteo[decision] += 1
        if decision in avisos:
            avisos[decision].append(p["overture_id"])
        if decision in _ESCRIBEN:
            escribir_.append(p)
    _guarda_durabilidad(escribir_, capa)
    if r.explicitos_no_representables:
        conteo["explicit_status_not_representable"] = len(r.explicitos_no_representables)
    con_transicion = sorted(oid for oid, clase in r.explicitos_no_representables.items() if oid in capa and (
        (clase in CLASES_CERRADAS and capa[oid][0]) or (clase == ABIERTO and not capa[oid][0])))
    return escribir_, conteo, avisos, con_transicion


def _guarda_cobertura(db, r: ResultadoFuente) -> None:
    """R3 · D-R3-2: si una categoría de Contexto cae MÁS del 10 % frente a la cobertura previa (§ COBERTURA_PREVIA_*),
    la taxonomía probablemente cambió bajo el lector: Overture no escribe ni cierra. Es una guarda de DERIVA, no una
    regla de cierre (con o sin ella, lo no aceptado jamás se cierra).
      DENOMINADOR  las filas Overture OPERATIVAS de la ciudad que observó la última corrida OK (o, si no hubo, la capa
                   legada), por `categoria`.
      NUMERADOR    TODAS las observaciones que la regla acepta por TAXONOMÍA + RUTA, por categoría, ANTES de la matriz:
                   las de presencia (OPEN / NULL con la confianza de Contexto) Y los cierres explícitos (cualquier
                   confianza), estén o no en la capa y se escriban o no. Un cierre es un ESTADO de la fuente, no la
                   desaparición de una hoja: contarlo evita confundir «la fuente dice que cerró» con «la taxonomía
                   cambió». Igual con las presencias NULL sobre filas cerradas (no se tocan, pero existen)."""
    previa = {cat: n for cat, n in db.execute(COBERTURA_PREVIA_OVERTURE, {"c": CIUDAD}).all()}
    nueva = Counter(p["categoria"] for p in r.filas)
    caidas = [f"{cat} {nueva.get(cat, 0)} < {n}·{1 - CAIDA_MAX_COBERTURA:.0%}" for cat, n in sorted(previa.items())
              if n and nueva.get(cat, 0) < n * (1 - CAIDA_MAX_COBERTURA)]
    if r.observacion is not None:
        r.observacion["cobertura"] = {cat: [n, nueva.get(cat, 0)] for cat, n in sorted(previa.items())}
    if caidas:
        raise GuardaTaxonomia("CaidaDeCobertura", "cobertura por categoría bajo el umbral: " + "; ".join(caidas))


def escribir(eng, r: ResultadoFuente, ident: dict) -> None:
    """UNA transacción para ESTA fuente: upsert + cierre con sus guardas + SU corrida. Si algo falla, se
    revierte ESTA fuente ENTERA —POIs, cierres y corrida— y nada más: la otra confirmó, o confirmará, en la
    suya. Después, la corrida fallida se intenta guardar aparte (`registrar_fallo`).

    UPSERT por identificador de origen (migración 020): la fila sobrevive al refresco con su `id`.
    Antes era TRUNCATE (borraba TODOS los mercados, migración 019) y luego DELETE+INSERT.
    R4: cada fila escrita queda enlazada a ESTA corrida (`ingestion_run_id`); la corrida se inserta AL FINAL,
    con los contadores ya conocidos (la FK es diferida: se comprueba en el COMMIT).
    R3: en Overture, la guarda de cobertura va PRIMERO (antes de escribir nada) y no hay sentencia de cierre: la
    MATRIZ TEMPORAL de OPERATING STATUS (`_matriz_de_estado`, solo lectura, misma transacción) decide qué observaciones
    aceptadas entran por el upsert, y la DURABILITY GUARD exige que ninguna cambie el `operativo` de una fila existente:
    en R3 v1 no hay transiciones de estado canónico (`rows_closed` = 0); los estados explícitos se cuentan y se avisan.
    OSM no cambia: cierra por ausencia, con su guarda."""
    es_overture = r.fuente == "overture"
    upsert, clave = (UPSERT_OVERTURE, "overture_id") if es_overture else (UPSERT_OSM, "osm_id")
    filas = [{**p, "ingestion_run_id": r.run_id} for p in r.filas]
    t0 = time.time()
    try:
        no_representables_en_capa: list[str] = []
        matriz, avisos = Counter(), {}
        with eng.begin() as db:
            cerradas = 0
            if es_overture:
                _guarda_cobertura(db, r)
                a_escribir, matriz, avisos, no_representables_en_capa = _matriz_de_estado(db, r)
                filas = [{**p, "ingestion_run_id": r.run_id} for p in a_escribir]
                cerradas = 0          # DURABILITY GUARD: ninguna transición abierta → cerrada en R3 v1 (ver la guarda)
            if filas:
                db.execute(upsert, filas)
            if not es_overture:
                # Cierre POR FUENTE con la guarda de caída brusca, contada en el mismo punto que antes
                # (tras el upsert de esta fuente). Ver el incidente del 2026-07-27 en CERRAR_*.
                previos_f = db.execute(text(
                    "SELECT count(*) FROM pois_propios WHERE ciudad=:c AND operativo AND fuente=:f"
                ), {"c": CIUDAD, "f": r.fuente}).scalar()
                if previos_f and len(r.filas) < previos_f * UMBRAL_CAIDA:
                    print(f"   ⚠️ '{r.fuente}' trajo {len(r.filas)} vs {previos_f} en tabla "
                          f"(<{UMBRAL_CAIDA:.0%}) → respuesta parcial, NO se cierra nada. Revisar.")
                else:
                    ids = [p[clave] for p in r.filas]
                    cerradas = db.execute(CERRAR_OSM, {"ciudad": CIUDAD, "ids": ids or [""]}).rowcount
            db.execute(INSERT_CORRIDA, _manifiesto(r, ident, escritas=len(filas), cerradas=cerradas))
        r.escritas, r.cerradas, r.manifiesto = len(filas), cerradas, "persistido"
        if es_overture:
            if r.observacion is not None:
                r.observacion["matriz"] = dict(matriz)
                r.observacion["explicitos_no_representables_con_transicion"] = no_representables_en_capa

            def _gers(ids):
                return ", ".join(ids[:20]) + (" …" if len(ids) > 20 else "")
            textos = {
                "reobservadas_sin_open_explicito": "POI(s) CERRADOS de la capa reaparecen con operating_status NULL: NULL "
                                                   "no es `open` → siguen cerrados y NO se tocan",
                "explicit_open_on_closed": "POI(s) CERRADOS de la capa vienen `open` en la fuente: reabrir exige conservar "
                                           "durablemente esa evidencia (R5) → NO se tocan",
                "temporary_closed_on_active": "POI(s) ACTIVOS de la capa vienen `temporarily_closed`: cerrar exige "
                                              "evidencia durable (R5) → NO se tocan",
                "permanent_closed_on_active": "POI(s) ACTIVOS de la capa vienen `permanently_closed`: cerrar exige "
                                              "evidencia durable (R5) → NO se tocan",
                "explicit_close_on_closed": "POI(s) ya CERRADOS de la capa vienen cerrados en la fuente: NO se reemplaza "
                                            "su procedencia histórica (R5)",
                "explicit_close_new": "lugar(es) que la capa NO tiene vienen cerrados en la fuente: NO se crean"}
            for clave in _AVISAN:
                ids = avisos.get(clave) or []
                if ids:
                    r.alertas.append(f"{len(ids)} {textos[clave]} [{clave}]. GERS: " + _gers(ids))
            if no_representables_en_capa:
                r.alertas.append(
                    f"la fuente afirma un estado para {len(no_representables_en_capa)} POI(s) de la capa que implicaría "
                    f"una transición, pero la regla {LECTOR_OVERTURE_TAXONOMIA} no acepta esa observación: NO se tocan "
                    f"[explicit_status_not_representable]. GERS: " + _gers(no_representables_en_capa))
    except GuardaTaxonomia as exc:  # R3 · la guarda invalidó Overture ANTES de escribir o cerrar: nada se tocó
        r.estado, r.fase, r.clase = FUENTE_ROTA, "validacion", exc.clase
        r.error = f"{exc.clase}: {exc}"[:300]
        r.escritas = r.cerradas = 0
        print(f"   ❌ {r.fuente}: {r.error} → NO se escribe ni se cierra nada de Overture")
        registrar_fallo(eng, r, ident)
    except Exception as exc:  # noqa: BLE001 — rollback de ESTA fuente; la otra no se toca
        # Solo la clase: el texto de un error de la base arrastra SQL, parámetros o el host.
        r.estado, r.fase, r.error, r.clase = FUENTE_ROTA, "escritura", type(exc).__name__, type(exc).__name__
        r.escritas = r.cerradas = 0
        print(f"   ❌ {r.fuente}: la escritura falló ({r.error}) → revertida; la otra fuente no se toca")
        registrar_fallo(eng, r, ident)
    r.segundos += time.time() - t0


def codigo_de_salida(fuentes: list[ResultadoFuente]) -> int:
    """0 = todas OK · 2 = ninguna rota pero alguna caída (reintentable) · 1 = alguna rota (no se
    reintenta: un esquema roto no se arregla esperando). Mismos códigos que antes."""
    estados = {f.estado for f in fuentes}
    if FUENTE_ROTA in estados:
        return 1
    if FUENTE_CAIDA in estados:
        return 2
    return 0


def veredicto(fuentes: list[ResultadoFuente]) -> str:
    partes = " · ".join(f"{f.fuente.upper()} {_ETIQUETA[f.estado]}" for f in fuentes)
    if all(f.estado == FUENTE_OK for f in fuentes):
        return f"COMPLETO · {partes}"
    if not any(f.estado == FUENTE_OK for f in fuentes):
        return f"SIN REFRESCO · {partes}"
    return f"DEGRADADO · {partes}"


def _ruta_estado(ciudad: str) -> Path:
    """`logs/` (ignorado por git), o `REFRESCO_POIS_ESTADO` si se fija (pruebas)."""
    fijada = os.getenv("REFRESCO_POIS_ESTADO", "").strip()
    if fijada:
        return Path(fijada)
    return Path(__file__).resolve().parent.parent / "logs" / f"refresco_pois_estado_{ciudad}.json"


def _guarda_estado(fuentes: list[ResultadoFuente], resultado: str, codigo: int) -> None:
    """El resumen por fuente, para que el aviso del workflow (--solo-avisar) diga QUÉ fuente falló.
    Sin secretos: estados, conteos, release y clase de error."""
    try:
        ruta = _ruta_estado(CIUDAD)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({"ciudad": CIUDAD, "escrito_en": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                    "resultado": resultado, "codigo": codigo,
                                    "fuentes": [f.resumen() for f in fuentes]}, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    except OSError as exc:
        print(f"⚠️  No se pudo guardar el estado del refresco ({type(exc).__name__}).")


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
    # R4: cada corrida guarda el SHA EXACTO del código que la ejecutó. Sin él no se escribe nada.
    sha = code_sha()
    if sha is None:
        print("❌ CODE SHA no determinable (GITHUB_SHA en Actions, REFRESCO_POIS_CODE_SHA fuera; 40 hex) "
              "→ FAIL CLOSED: 0 escrituras, 0 cierres, 0 corridas.")
        _guarda_estado([], "SIN REFRESCO · CODE SHA NO DETERMINABLE", 1)
        avisar_ops(f"[Contexto] Refresco de POIs SIN REFRESCO · CODE SHA NO DETERMINABLE · {CIUDAD}",
                   "El refresco no sabe qué código lo ejecuta (GITHUB_SHA / REFRESCO_POIS_CODE_SHA): "
                   "no escribe procedencia sin él. No se tocó la base.")
        sys.exit(1)
    ident = {"code_sha": sha, "invocation_ref": invocation_ref()}

    print("── 1) Overture Places (6 categorías, umbral de conf por categoría) ──", flush=True)
    ov = obtener("overture")
    if ov.estado == FUENTE_OK:
        print(f"   {ov.validadas} POIs Overture ({ov.segundos:.0f}s)")
    print("── 2) OSM: transporte + comercio + culto/UPC (Overpass) ──", flush=True)
    osm = obtener("osm")
    if osm.estado == FUENTE_OK:
        print(f"   {osm.validadas} POIs de OSM ({osm.segundos:.0f}s)")
    elif osm.estado == FUENTE_CAIDA:
        print("   0 POIs de OSM  ⚠️ FUENTE CAÍDA")
    fuentes = [ov, osm]
    utiles = [f for f in fuentes if f.estado == FUENTE_OK]

    por_cat: dict[str, int] = {}
    for f in utiles:
        for p in f.filas:
            por_cat[p["categoria"]] = por_cat.get(p["categoria"], 0) + 1
    for cat, n in sorted(por_cat.items(), key=lambda x: -x[1]):
        print(f"     {cat:16} {n}")

    if not utiles:
        print("❌ Ninguna fuente se obtuvo — La capa NO se actualizó (0 escrituras, 0 cierres). "
              "Solo se registran sus corridas fallidas, si la base lo permite.")

    # NullPool: una conexión secuencial. Ver la nota en scripts/asignar_corredor.py —
    # con el pool por defecto este script solo podría agotar el techo de Supabase.
    # TLS del núcleo (#137): verify-full con el ancla de app/db_tls, por connect_args — en
    # psycopg los kwargs ganan sobre la conninfo. En el runner, el ancla la instala
    # refresco-pois.yml en su ruta canónica antes de este paso.
    eng = create_engine(SYNC_URL, echo=False, poolclass=NullPool,
                        connect_args=db_tls.kwargs_psycopg(SYNC_URL))
    try:
        # R4 · COMPUERTA 043 (solo lectura de catálogo), ANTES de cualquier escritura y del DDL T0.
        try:
            faltas = verificar_esquema_043(eng)
        except Exception as exc:  # noqa: BLE001 — base inalcanzable: tampoco se puede registrar nada
            faltas = [f"la base no respondió ({type(exc).__name__})"]
        if faltas:
            print("❌ ESQUEMA 043 AUSENTE O INCOMPLETO → FAIL CLOSED: 0 escrituras, 0 cierres, 0 corridas. "
                  "MANIFEST NOT PERSISTED. " + "; ".join(faltas))
            for f in fuentes:
                if f.estado == FUENTE_OK:
                    f.estado, f.fase, f.error, f.clase = FUENTE_ROTA, "escritura", "Esquema043Ausente", "Esquema043Ausente"
                f.manifiesto = "NOT PERSISTED"
            utiles = []
            fuentes_a_registrar = []
        else:
            fuentes_a_registrar = fuentes
        if utiles:
            print("── 3) Cargando a pois_propios ──", flush=True)
        try:
            if not utiles:
                raise _SinNadaQueEscribir
            with eng.begin() as db:
                # El DDL idempotente y la foto previa: su propia transacción, antes de las fuentes.
                for stmt in DDL.strip().split(";"):
                    if stmt.strip():
                        db.execute(text(stmt))
                otras = db.execute(text(
                    "SELECT ciudad, count(*) FROM pois_propios WHERE ciudad <> :c GROUP BY 1"
                ), {"c": CIUDAD}).all()
                previos = db.execute(text(
                    "SELECT count(*) FROM pois_propios WHERE ciudad = :c"), {"c": CIUDAD}).scalar()
            print(f"   en la tabla antes: {previos} POIs de '{CIUDAD}' · cosechados ahora: "
                  f"{sum(len(f.filas) for f in utiles)}")
            if otras:
                print("   intactas: " + ", ".join(f"{c}={n}" for c, n in otras))
        except _SinNadaQueEscribir:
            pass                            # sin fuente útil (o sin 043) no hay DDL T0 ni foto previa
        except Exception as exc:  # noqa: BLE001 — sin esquema no escribe ninguna fuente
            for f in utiles:
                f.estado, f.fase, f.error, f.clase = FUENTE_ROTA, "escritura", type(exc).__name__, type(exc).__name__
            print(f"   ❌ preparar la tabla falló ({type(exc).__name__}) → no se escribe ninguna fuente")
            utiles = []

        for f in fuentes_a_registrar:
            if f.estado == FUENTE_OK:
                escribir(eng, f, ident)
            else:
                print(f"   ⚠️ '{f.fuente}' {_ETIQUETA[f.estado]} ({f.fase}) → NO se escribe ni se cierra "
                      "ninguno de sus POIs")
                registrar_fallo(eng, f, ident)

        if any(f.estado == FUENTE_OK for f in fuentes):
            with eng.connect() as db:
                n = db.execute(text("SELECT count(*) FROM pois_propios WHERE ciudad = :c AND operativo"),
                               {"c": CIUDAD}).scalar()
                total = db.execute(text("SELECT count(*) FROM pois_propios")).scalar()
            print(f"   upsert: {ov.escritas} Overture + {osm.escritas} OSM · marcados cerrados: "
                  f"{ov.cerradas + osm.cerradas}")
            print(f"   operativos en '{CIUDAD}': {n} ✅  (tabla completa, incl. cerrados: {total})")

        if not sin_validacion and any(f.estado == FUENTE_OK for f in fuentes):
            _validacion_humana(eng)
    finally:
        eng.dispose()
    _salir(fuentes)


def _validacion_humana(eng) -> None:
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


def _salir(fuentes: list[ResultadoFuente]):
    """Código de salida con SEÑAL y resumen POR FUENTE, para que nada corra a ciegas.

      0 = las dos fuentes se obtuvieron y se escribieron.
      2 = ninguna rota, pero alguna no respondió: lo que sí respondió quedó escrito y lo de la
          caída quedó intacto (no se cerró nada). Es REINTENTABLE: el workflow y
          `refresco_pois.cmd` reintentan, y el reintento vuelve a escribir la fuente sana (upsert
          idempotente; el cierre repite sus guardas).
      1 = alguna fuente ROTA (esquema, datos inválidos, escritura): no se reintenta. La otra
          pudo quedar escrita: el resumen y el aviso dicen cuál.
    Hasta el 2026-10-02 un error de Overture salía con 1 sin haber tocado OSM.
    """
    resultado, codigo = veredicto(fuentes), codigo_de_salida(fuentes)
    print("\n── Resumen por fuente ──")
    for f in fuentes:
        print("   " + f.linea())
    for f in fuentes:
        print(f"   corrida {f.fuente}: {f.run_id} · manifiesto {f.manifiesto or 'no intentado'}")
    for f in fuentes:
        if f.observacion is not None:   # R3: lo que el lector vio y NO ingirió (sin migración: log + estado + aviso)
            print(f"   observación {f.fuente} ({f.lector}): " + json.dumps(f.observacion, ensure_ascii=False))
    alertas = [f"{f.fuente}: {a}" for f in fuentes for a in f.alertas]
    for a in alertas:
        print(f"   ⚠️ AVISO {a}")
    print(f"   RESULTADO: {resultado} · código {codigo}")
    _guarda_estado(fuentes, resultado, codigo)
    if alertas and codigo != 1:   # con 1 ya sale el aviso de fuente rota, que las incluye
        avisar_ops(f"[Contexto] Refresco de POIs · AVISO DE TAXONOMÍA Y ESTADO · {CIUDAD}",
                   "El refresco terminó sin fuente rota, pero la fuente trae algo que la regla NO aplicó (no se "
                   "ingirió, o no se cambió el estado de la fila):\n\n" + "\n".join(alertas))
    if codigo == 0:
        print("\n✅ Refresco completo — las dos fuentes respondieron.")
    elif codigo == 2:
        print("\n⚠️ Refresco INCOMPLETO: alguna fuente no respondió. Lo que respondió se actualizó; "
              "lo de la caída quedó como estaba (no se cerró ninguno). Reintentable.")
    else:
        print("\n❌ Refresco con una fuente ROTA: no se reintenta. Ver el resumen por fuente.")
        avisar_ops(f"[Contexto] Refresco de POIs {resultado} · {CIUDAD}",
                   "El refresco de pois_propios terminó con al menos una fuente rota.\n"
                   "Una fuente rota NO escribe ni cierra nada; la otra pudo refrescarse.\n\n"
                   + "\n".join(f.linea() for f in fuentes)
                   + ("\n\nAvisos:\n" + "\n".join(alertas) if alertas else ""))
    sys.exit(codigo)


def _estado_guardado(ciudad: str) -> dict | None:
    try:
        return json.loads(_ruta_estado(ciudad).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def avisar_tras_reintentos(argv: list[str]) -> bool:
    """Modo aviso puro (`--solo-avisar`): el workflow y refresco_pois.cmd lo invocan cuando agotan
    sus reintentos, para que una tubería caída deje de ser un log que nadie abre. No toca red de
    datos ni base. Lee el resumen por fuente que dejó la última corrida para decir QUÉ falló."""
    # El motivo es lo que venga DESPUÉS de la bandera; el primer argumento suelto ANTES de ella es
    # el slug de la ciudad (tomarlo como motivo daría un aviso que dice "Motivo: quito").
    i = argv.index("--solo-avisar")
    motivo = next((a for a in argv[i + 1:] if not a.startswith("--")), "motivo no indicado")
    ciudad = next((a for a in argv[1:i] if not a.startswith("-")), CIUDAD).strip().lower()
    estado = _estado_guardado(ciudad)
    por_fuente = ("\n".join(" · ".join(f"{k}={v}" for k, v in f.items() if v is not None)
                            for f in estado["fuentes"]) if estado else "(sin resumen por fuente guardado)")
    return avisar_ops(
        f"[Contexto] El refresco de POIs falló · {ciudad}" + (f" · {estado['resultado']}" if estado else ""),
        f"La tarea semanal de pois_propios terminó sin éxito tras sus reintentos.\n\n"
        f"Ciudad: {ciudad}\nMotivo/código: {motivo}\n\n"
        f"Última corrida, por fuente:\n{por_fuente}\n\n"
        f"Revisar el log más reciente en logs\\refresco_pois_{ciudad}_*.log",
    )


if __name__ == "__main__":
    if "--solo-avisar" in sys.argv:
        avisar_tras_reintentos(sys.argv)
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
