"""POI-REFRESH-SOURCE-ISOLATION · un fallo de Overture ya no impide refrescar OSM (ni al revés).

EL DEFECTO (corrida #7 de `refresco-pois`, 2026-09-29): Overture 2026-09-23.1 (esquema v2.0.0) ya no
trae `categories`; `pull_overture()` lanzó `BinderException` ANTES de descargar OSM y, como la carga era
UNA transacción, el refresco entero abortó. OSM quedó congelado con Overture aunque no depende de ella.

Dos capas:
  · ORQUESTACIÓN (corre en el CI): el `main()` REAL con un motor falso que registra cada transacción
    (commit o rollback) y cada sentencia. El fallo de Overture es el `pull_overture()` REAL contra un
    parquet con el esquema v2 (sin `categories`), generado aquí con DuckDB: reproduce la excepción exacta.
  · POSTGIS (local, con `TEST_POSTGIS_URL`; el Postgres del CI no trae PostGIS): migraciones REALES
    014→022 en un esquema desechable, el `main()` REAL escribiendo, fallos de escritura forzados por
    trigger a mitad de un upsert, y la equivalencia del camino feliz con el script ANTERIOR (`25303ff3`).

POI-SOURCE-PROVENANCE (R4, 2026-10-02): el escritor EXIGE el esquema 043 y escribe procedencia. Estas pruebas
siguen midiendo el aislamiento de #189 con el contrato nuevo: el banco PostGIS aplica también la 023, el perímetro
mínimo de la 040 (RLS + `security_invoker`) y la 043 REAL; las filas de prueba llevan la procedencia que ya
entregan los lectores reales; y una fuente que falla deja su corrida fallida en la base (antes: «no abre la
base»). La matriz propia de R4 vive en `tests/test_poi_source_provenance_writer.py`.

R3 · OVERTURE TAXONOMY V1 (2026-10-02): el lector VIGENTE de Overture es `pull_overture_taxonomia`
(`overture_places_taxonomy_v1`); el de `categories.primary` (`pull_overture`) queda intacto y ya no se ejecuta. Las
pruebas de orquestación inyectan el lector vigente y sus filas (`_ov`, con `taxonomy.primary`); la falla REAL de
Overture es ahora un esquema que el lector no conoce (un release sin `taxonomy`). Y, por D-R3-2, Overture ya NO
cierra por ausencia: solo con `operating_status = 'closed'` declarado por la fuente. OSM no cambia. El aislamiento
entre fuentes se mide exactamente igual. La matriz propia de R3 vive en `tests/test_r3_overture_taxonomy.py`.
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import uuid

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "scripts" / "foso_pois_spike.py"
URL_FALSA = "postgresql+psycopg://refresco:clave-que-no-debe-salir@localhost:5432/x"
BINDER = 'Referenced table "categories" not found'
SHA_PRUEBA = "0123456789abcdef0123456789abcdef01234567"
HUELLA_PRUEBA = "f" * 64
# La etiqueta OSM REAL que produce cada subtipo en la cadena de `pull_osm_transporte` (R4 la conserva).
ETIQUETA_OSM = {"parada_bus": ("highway", "bus_stop"), "park": ("leisure", "park"), "garden": ("leisure", "garden"),
                "pharmacy": ("amenity", "pharmacy"), "metro": ("railway", "subway_entrance"),
                "estacion_tren": ("railway", "station"), "terminal_bus": ("amenity", "bus_station"),
                "estacion": ("public_transport", "station"), "supermercado": ("shop", "supermarket"),
                "minimarket": ("shop", "convenience"), "place_of_worship": ("amenity", "place_of_worship"),
                "police": ("amenity", "police")}
SOURCES_PRUEBA = [{"property": "", "dataset": "meta", "license": "CDLA-Permissive-2.0", "record_id": "1264674866906410",
                   "update_time": "2026-08-10T00:00:00.000Z", "confidence": 0.58, "between": None, "provider": "meta",
                   "resource": "meta", "version": "2026-08-10"},
                  {"property": "/properties/confidence", "dataset": "Overture", "license": "CDLA-Permissive-2.0",
                   "record_id": None, "update_time": "2026-08-14T19:46:07Z", "confidence": None, "between": None,
                   "provider": "overture", "resource": "confidence_calculation", "version": "2026-08-14"}]


def _carga(ruta: pathlib.Path = SCRIPT, nombre: str = "foso_iso"):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ══ motor falso: registra transacciones y sentencias; puede fallar en una sentencia ══════════════
class _R:
    def __init__(self, escalar=None, filas=None, rowcount=0):
        self._e, self._f, self.rowcount = escalar, filas, rowcount

    def scalar(self):
        return self._e

    def all(self):
        return self._f or []


class _Conexion:
    def __init__(self, motor, registro):
        self.motor, self.registro = motor, registro

    def execute(self, sql, params=None):
        s = " ".join(str(sql).split())
        self.registro["sentencias"].append((s, params))
        if self.motor.falla_en and self.motor.falla_en in s:
            raise RuntimeError(f"fallo simulado de la base en: {self.motor.falla_en} (host db.secreto:5432)")
        if s.startswith("SELECT count(*) FROM pois_propios WHERE ciudad=:c AND operativo AND fuente=:f"):
            return _R(escalar=self.motor.previos.get(params["f"], 0))
        if s.startswith("UPDATE pois_propios SET operativo = false"):
            fuente = "overture" if "fuente = 'overture'" in s else "osm"
            return _R(rowcount=self.motor.cierres.get(fuente, 0))
        if "AS cobertura_previa" in s:          # R3: la cobertura previa por categoría de Overture
            return _R(filas=list(self.motor.cobertura.items()))
        if "GROUP BY 1" in s:
            return _R(filas=[])
        if s.startswith("SELECT count(*)"):
            return _R(escalar=0)
        return _R()


class MotorFalso:
    def __init__(self, previos=None, cierres=None, falla_en=None, cobertura=None):
        self.previos, self.cierres, self.falla_en = previos or {}, cierres or {}, falla_en
        self.cobertura = cobertura or {}
        self.transacciones: list[dict] = []
        self.creado = False
        self.dispuesto = False

    @contextlib.contextmanager
    def _tx(self, tipo):
        reg = {"tipo": tipo, "sentencias": [], "resultado": None}
        self.transacciones.append(reg)
        try:
            yield _Conexion(self, reg)
        except BaseException:
            reg["resultado"] = "rollback"
            raise
        reg["resultado"] = "commit"

    def begin(self):
        return self._tx("begin")

    def connect(self):
        return self._tx("connect")

    def dispose(self):
        self.dispuesto = True

    # — lectura de lo que pasó —
    def ejecutadas(self, fragmento):
        return [(t["resultado"], s, p) for t in self.transacciones for s, p in t["sentencias"] if fragmento in s]

    def tx_con(self, fragmento):
        return [t for t in self.transacciones if any(fragmento in s for s, _ in t["sentencias"])]


UPSERT_OV, UPSERT_OSM = "ON CONFLICT (overture_id)", "ON CONFLICT (osm_id)"
# R3: el fragmento es el del UPDATE de cierre (la consulta de cobertura, de solo lectura, también nombra la fuente)
CIERRA_OV, CIERRA_OSM = "AND operativo AND fuente = 'overture'", "AND operativo AND fuente = 'osm'"


def _ov(m, oid, cat="salud", hoja="hospital"):
    """Una fila de Overture como la entrega el lector VIGENTE (R3, `pull_overture_taxonomia`): `taxonomy.primary` en
    su espacio y la columna legada `categoria_overture` (:cat_leaf) NULL, como exige I4 de la 043."""
    return m._normalizar({"nombre": f"Overture {oid}", "categoria": cat, "cat_leaf": None, "lon": -78.5,
                          "lat": -0.2, "confidence": 0.9, "overture_id": oid, "osm_id": None, "marca": None,
                          "direccion": None, "operativo": True, "fuente": "overture",
                          "source_category": hoja, "source_category_namespace": m.NS_OVERTURE_TAXONOMIA,
                          "source_record_version": "7",
                          "source_updated_at": None,          # R1: R4 no interpreta update_time (va en el linaje)
                          "source_lineage": json.dumps(SOURCES_PRUEBA, ensure_ascii=False)})


def _osm(m, oid, cat="transporte", sub="parada_bus"):
    """Una fila de OSM como la entrega `pull_osm_transporte` (con la etiqueta REAL que casó)."""
    clave, valor = ETIQUETA_OSM[sub]
    return m._normalizar({"nombre": f"OSM {oid}", "categoria": cat, "cat_leaf": sub, "lon": -78.49, "lat": -0.19,
                          "confidence": None, "overture_id": None, "osm_id": oid, "marca": None, "direccion": None,
                          "operativo": True, "fuente": "osm", "source_category": valor,
                          "source_category_namespace": f"osm:{clave}"})


def _sin_corrida(filas):
    """Los parámetros del upsert SIN el enlace a la corrida (que el escritor añade al escribir)."""
    return [{k: v for k, v in f.items() if k != "ingestion_run_id"} for f in filas]


@pytest.fixture
def foso(monkeypatch, tmp_path):
    m = _carga()
    monkeypatch.delenv("OVERTURE_RELEASE", raising=False)
    monkeypatch.setenv("REFRESCO_POIS_ESTADO", str(tmp_path / "estado.json"))
    monkeypatch.setattr(m, "SYNC_URL", URL_FALSA)
    monkeypatch.setattr(m, "overture_release", lambda: "2026-09-23.1")
    m.avisos = []
    monkeypatch.setattr(m, "avisar_ops", lambda asunto, detalle: m.avisos.append((asunto, detalle)) or True)
    monkeypatch.setattr(sys, "argv", ["foso_pois_spike.py", "quito", "--sin-validacion"])
    # R4: el SHA del código por la vía explícita de fuera de Actions (en el CI, GITHUB_ACTIONS=true daría el
    # GITHUB_SHA del runner; aquí se fija para que las pruebas sean deterministas).
    for k in ("GITHUB_ACTIONS", "GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_WORKFLOW",
              "REFRESCO_POIS_INVOCATION_REF"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("REFRESCO_POIS_CODE_SHA", SHA_PRUEBA)
    # La huella del esquema de Overture se observa con un DESCRIBE del release: aquí, una fija (la real se
    # prueba aparte, `m._huella_real`, contra parquets locales).
    m._huella_real = m.huella_esquema_overture
    monkeypatch.setattr(m, "huella_esquema_overture", lambda glob: HUELLA_PRUEBA)
    # R3: ninguna prueba toca la red. Si una prueba no inyecta su lector ni su parquet, el lector REAL de Overture
    # lee un archivo local que no existe y falla al instante (IOException), en vez de ir al S3 de Overture.
    monkeypatch.setattr(m, "overture_glob", lambda rel: (tmp_path / f"sin_red_{rel}.parquet").as_posix())
    return m


def _motor(monkeypatch, m, **k) -> MotorFalso:
    motor = MotorFalso(**k)
    # El motor falso no tiene catálogo: la compuerta 043 se da por cumplida (se prueba contra PostGIS aparte).
    monkeypatch.setattr(m, "verificar_esquema_043", lambda eng: [])

    def _crea(url, **kw):
        motor.creado = True
        motor.url, motor.kw = url, kw
        return motor
    monkeypatch.setattr(m, "create_engine", _crea)
    return motor


def _corre(m) -> int:
    with pytest.raises(SystemExit) as salida:
        m.main()
    return salida.value.code


def _estado(tmp_path) -> dict:
    return json.loads((tmp_path / "estado.json").read_text(encoding="utf-8"))


def _fuentes(estado) -> dict:
    return {f["fuente"]: f for f in estado["fuentes"]}


# ══ Overture REAL: parquets con el esquema v1 (con `categories`) y v2 (sin) ═══════════════════════
@pytest.fixture(scope="module")
def duckdb_spatial():
    duckdb = pytest.importorskip("duckdb")
    try:
        con = duckdb.connect()
        con.execute("INSTALL spatial; LOAD spatial;")
        con.close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"sin la extensión spatial de DuckDB ({type(exc).__name__})")
    return duckdb


def _parquet(duckdb, ruta: pathlib.Path, con_categories: bool) -> str:
    """Un places con la estructura REAL de Overture (tipos de `DESCRIBE` de 2026-08-19.0 / 2026-09-23.1):
    v1 trae `categories` además de `taxonomy`; v2 (2026-09-23.x, esquema v2.0.0) ya no la trae."""
    p = ruta.as_posix()
    categories = ("{'primary': hoja_v1, 'alternate': NULL::VARCHAR[]} AS categories," if con_categories else "")
    # `version` y `sources` como en los DOS releases medidos (2026-08-19.0 y 2026-09-23.1): R4 los lee. Cada
    # registro con su raíz (`property` = '') y la entrada de la confianza, con la `version` de SU dataset: ov-1
    # meta con zona (el sello de su volcado), ov-2 Microsoft con zona y un instante propio, ov-3 Foursquare SIN
    # zona. R1: `source_updated_at` es NULL en los tres; su `update_time` va íntegro en `source_lineage`.
    fuente = ("{'property': '', 'dataset': ds, 'license': lic, 'record_id': 'rec-' || id, 'update_time': ut, "
              "'confidence': conf::DOUBLE, 'between': NULL::DOUBLE[], 'provider': lower(ds), 'resource': lower(ds), "
              "'version': vf}")
    conf_ov = ("{'property': '/properties/confidence', 'dataset': 'Overture', 'license': 'CDLA-Permissive-2.0', "
               "'record_id': NULL::VARCHAR, 'update_time': '2026-08-14T19:46:07Z', 'confidence': NULL::DOUBLE, "
               "'between': NULL::DOUBLE[], 'provider': 'overture', 'resource': 'confidence_calculation', "
               "'version': '2026-08-14'}")
    con = duckdb.connect()
    con.execute("LOAD spatial;")
    con.execute(f"""
        COPY (
          SELECT id, {{'primary': nombre}} AS names, {categories}
                 {{'primary': hoja_v2, 'hierarchy': ['raiz', hoja_v2], 'alternates': NULL::VARCHAR[]}} AS taxonomy,
                 hoja_v2 AS basic_category, conf::DOUBLE AS confidence, ST_Point(lon, lat) AS geometry,
                 {{'xmin': lon, 'xmax': lon, 'ymin': lat, 'ymax': lat}} AS bbox,
                 [{{'freeform': 'Calle sintética'}}] AS addresses, {{'names': {{'primary': NULL::VARCHAR}}}} AS brand,
                 'open' AS operating_status, ver::INTEGER AS version, [{fuente}, {conf_ov}] AS sources
          FROM (VALUES ('ov-1', 'Hospital Uno', 'hospital', 'hospital', -78.50, -0.20, 0.91, 9, 'meta',
                        'CDLA-Permissive-2.0', '2026-08-10T00:00:00.000Z', '2026-08-10'),
                       ('ov-2', 'Centro Dos', 'shopping_center', 'shopping_mall', -78.49, -0.19, 0.95, 4, 'Microsoft',
                        'CDLA-Permissive-2.0', '2025-09-24T07:57:19.737Z', '2025-10-20'),
                       ('ov-3', 'Clínica Tres', 'medical_center', 'outpatient_care_facility', -78.48, -0.18, 0.80, 2,
                        'Foursquare', 'Apache-2.0', '2026-04-12T00:00:00.000', '2026-04-14'))
               t(id, nombre, hoja_v1, hoja_v2, lon, lat, conf, ver, ds, lic, ut, vf)
        ) TO '{p}' (FORMAT parquet)""")
    con.close()
    return p


# ══ R3 · parquets con la estructura REAL de 2026-09-23.x y RUTAS REALES de la taxonomía ═════════════
# (id, nombre, taxonomy.primary, taxonomy.hierarchy ' > ', confidence, lon, lat, operating_status, version)
FUERA_BBOX = (-70.0, 10.0)        # existe en el release, no en Quito: para la comprobación de existencia global
BASE_R3 = [
    ("ov-h1", "Hospital Uno", "hospital", "health_care > hospital", 0.91, -78.50, -0.20, None, 9),
    ("ov-ocf", "Centro Médico", "outpatient_care_facility", "health_care > outpatient_care_facility", 0.80, -78.48, -0.18, None, 2),
    ("ov-ph", "Farmacia", "pharmacy", "shopping > specialty_store > pharmacy_and_drug_store > pharmacy", 0.70, -78.49, -0.21, "open", 3),
    ("ov-gr", "Tienda", "grocery_store", "shopping > food_and_beverage_store > grocery_store", 0.75, -78.47, -0.22, None, 1),
    ("ov-sc", "Escuela", "school", "education > place_of_learning > school", 0.80, -78.46, -0.23, None, 1),
    ("ov-cu", "Universidad", "college_university", "education > place_of_learning > college_university", 0.80, -78.45, -0.24, None, 1),
    ("ov-pre", "Jardín", "preschool", "education > place_of_learning > school > preschool", 0.80, -78.44, -0.25, None, 1),
    ("ov-pk", "Parque", "park", "sports_and_recreation > park", 0.85, -78.43, -0.26, None, 1),
    ("ov-pg", "Juegos", "playground", "sports_and_recreation > park > playground", 0.90, -78.42, -0.27, None, 1),
    ("ov-sm", "Centro Dos", "shopping_mall", "shopping > shopping_mall", 0.95, -78.41, -0.28, None, 4),
    ("ov-ds", "Almacén", "department_store", "shopping > department_store", 0.90, -78.42, -0.29, None, 1),
    ("far-ucc", "Urgencias lejos", "urgent_care_clinic",
     "health_care > emergency_or_urgent_care_facility > urgent_care_clinic", 0.90, *FUERA_BBOX, None, 1),
    ("far-dr", "Droguería lejos", "drugstore",
     "shopping > specialty_store > pharmacy_and_drug_store > drugstore", 0.90, *FUERA_BBOX, None, 1),
    # lo que la regla NO ingiere (cada clase de la observación)
    ("ov-low", "Hospital dudoso", "hospital", "health_care > hospital", 0.50, -78.50, -0.20, None, 1),
    ("ov-lowpk", "Parque dudoso", "park", "sports_and_recreation > park", 0.60, -78.43, -0.26, None, 1),
    ("ov-dent", "Dental", "dental_clinic", "health_care > outpatient_care_facility > dental_clinic", 0.90, -78.48, -0.18, None, 1),
    ("ov-hc", "Salud genérica", "health_care", "health_care", 0.90, -78.48, -0.18, None, 1),
    ("ov-rest", "Restaurante", "restaurant", "food_and_drink > restaurant", 0.90, -78.48, -0.18, None, 1),
    ("ov-null", "Sin taxonomía", None, None, 0.90, -78.48, -0.18, None, 1),
]


def _parquet_r3(duckdb, ruta: pathlib.Path, filas=BASE_R3, sin_taxonomy: bool = False,
                taxonomy_tipo: str | None = None) -> str:
    """Un places con los TIPOS REALES de 2026-09-23.x (sin `categories`) y las filas dadas. `sin_taxonomy` y
    `taxonomy_tipo` fabrican un esquema que el lector v1 NO conoce."""
    p = ruta.as_posix()

    def lit(v):
        return "NULL" if v is None else ("'" + str(v).replace("'", "''") + "'" if isinstance(v, str) else repr(v))
    valores = ",\n".join("(" + ", ".join(lit(v) for v in f) + ")" for f in filas)
    if sin_taxonomy:
        taxonomy = ""
    elif taxonomy_tipo == "con_campo_nuevo":
        taxonomy = ("CASE WHEN prim IS NULL THEN NULL ELSE {'primary': prim, 'hierarchy': string_split(jer, ' > '), "
                    "'alternates': NULL::VARCHAR[], 'basic': prim} END AS taxonomy,")
    else:
        taxonomy = ("CASE WHEN prim IS NULL THEN NULL ELSE {'primary': prim, 'hierarchy': string_split(jer, ' > '), "
                    "'alternates': NULL::VARCHAR[]} END AS taxonomy,")
    fuente = ("{'property': '', 'dataset': 'meta', 'license': 'CDLA-Permissive-2.0', 'record_id': 'rec-' || id, "
              "'update_time': '2026-09-14T00:00:00.000Z', 'confidence': conf::DOUBLE, 'between': NULL::DOUBLE[], "
              "'provider': 'meta', 'resource': 'meta', 'version': '2026-09-14'}")
    con = duckdb.connect()
    con.execute("LOAD spatial;")
    con.execute(f"""
        COPY (
          SELECT id::VARCHAR AS id, {{'primary': nombre}} AS names, {taxonomy}
                 prim AS basic_category, conf::DOUBLE AS confidence, ST_Point(lon, lat) AS geometry,
                 {{'xmin': lon::DOUBLE, 'xmax': lon::DOUBLE, 'ymin': lat::DOUBLE, 'ymax': lat::DOUBLE}} AS bbox,
                 [{{'freeform': 'Calle sintética'}}] AS addresses, {{'names': {{'primary': NULL::VARCHAR}}}} AS brand,
                 estado::VARCHAR AS operating_status, ver::INTEGER AS version, [{fuente}] AS sources
          FROM (VALUES {valores}) t(id, nombre, prim, jer, conf, lon, lat, estado, ver)
        ) TO '{p}' (FORMAT parquet)""")
    con.close()
    return p


def test_pull_overture_real_reproduce_el_binder_de_2026_09_23(foso, duckdb_spatial, tmp_path, monkeypatch):
    """La regresión exacta de la corrida #7: el parser actual, SIN reparar, contra el esquema v2."""
    v2 = _parquet(duckdb_spatial, tmp_path / "v2.parquet", con_categories=False)
    monkeypatch.setattr(foso, "overture_glob", lambda rel: v2)
    with pytest.raises(duckdb_spatial.BinderException, match=re.escape(BINDER)):
        foso.pull_overture()


def test_pull_overture_real_sigue_leyendo_el_esquema_v1(foso, duckdb_spatial, tmp_path, monkeypatch):
    """El parser no se tocó: con `categories` (2026-08-19.0) mapea y filtra como siempre."""
    v1 = _parquet(duckdb_spatial, tmp_path / "v1.parquet", con_categories=True)
    monkeypatch.setattr(foso, "overture_glob", lambda rel: v1)
    filas = foso.pull_overture()
    assert sorted((f["overture_id"], f["categoria"], f["cat_leaf"]) for f in filas) == [
        ("ov-1", "salud", "hospital"), ("ov-2", "centro_comercial", "shopping_center"),
        ("ov-3", "salud", "medical_center")]


# ══ A · las dos OK ═══════════════════════════════════════════════════════════════════════════════
def test_A_las_dos_ok_cada_una_en_su_transaccion(foso, monkeypatch, tmp_path, capsys):
    ov, osm = [_ov(foso, "ov-a"), _ov(foso, "ov-b")], [_osm(foso, "node/1"), _osm(foso, "way/2", "parque", "park")]
    monkeypatch.setattr(foso, "pull_overture_taxonomia", lambda: ov)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: osm)
    motor = _motor(monkeypatch, foso, previos={"overture": 2, "osm": 2}, cierres={"overture": 1, "osm": 0})
    assert _corre(foso) == 0
    [t_ov], [t_osm] = motor.tx_con(UPSERT_OV), motor.tx_con(UPSERT_OSM)
    assert t_ov is not t_osm, "cada fuente escribe en SU transacción"
    assert t_ov["resultado"] == t_osm["resultado"] == "commit"
    assert [s for s, _ in t_ov["sentencias"] if CIERRA_OSM in s or UPSERT_OSM in s] == []
    # R3 (D-R3-2): sin cierre explícito de la fuente, Overture no cierra; OSM sigue cerrando por ausencia.
    assert (len(motor.ejecutadas(CIERRA_OV)), len(motor.ejecutadas(CIERRA_OSM))) == (0, 1)
    e = _estado(tmp_path)
    assert e["codigo"] == 0 and e["resultado"] == "COMPLETO · OVERTURE OK · OSM OK"
    assert _fuentes(e)["overture"]["release"] == "2026-09-23.1"
    assert foso.avisos == [] and motor.dispuesto
    assert "Refresco completo" in capsys.readouterr().out


# ══ B · el caso central: Overture con el BinderException REAL, OSM OK ════════════════════════════
def test_B_fallo_real_de_overture_no_impide_refrescar_osm(foso, duckdb_spatial, monkeypatch, tmp_path, capsys):
    """El caso central de #189 con el lector VIGENTE. Desde R3 el esquema v2 se lee (el Binder de `categories` era
    del lector viejo); el fallo REAL del lector es ahora un esquema que no conoce: un release sin `taxonomy`."""
    roto = _parquet_r3(duckdb_spatial, tmp_path / "sin_taxonomy.parquet", sin_taxonomy=True)
    monkeypatch.setattr(foso, "overture_glob", lambda rel: roto)      # pull_overture_taxonomia REAL
    osm = [_osm(foso, "node/1"), _osm(foso, "node/2"), _osm(foso, "way/3", "parque", "park")]
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: osm)
    motor = _motor(monkeypatch, foso, previos={"osm": 4}, cierres={"osm": 1})
    assert _corre(foso) == 1                                          # una fuente ROTA: sin reintento
    assert motor.ejecutadas(UPSERT_OV) == [] and motor.ejecutadas(CIERRA_OV) == [], \
        "Overture rota: 0 escrituras y 0 cierres"
    [(res, _, filas)] = motor.ejecutadas(UPSERT_OSM)
    assert res == "commit" and _sin_corrida(filas) == osm
    assert len({f["ingestion_run_id"] for f in filas}) == 1, "todas las filas OSM de esta corrida, a SU corrida"
    [(res, _, cierre)] = motor.ejecutadas(CIERRA_OSM)
    assert res == "commit" and cierre["ids"] == ["node/1", "node/2", "way/3"]
    f = _fuentes(_estado(tmp_path))
    assert f["overture"]["estado"] == "rota" and f["overture"]["fase"] == "obtencion"
    assert "taxonomy=AUSENTE" in f["overture"]["error"]
    assert f["overture"]["escritas"] == f["overture"]["cerradas"] == 0 and f["overture"]["obtenidas"] is None
    assert (f["osm"]["estado"], f["osm"]["escritas"], f["osm"]["cerradas"]) == ("ok", 3, 1)
    [(asunto, detalle)] = foso.avisos
    assert "DEGRADADO · OVERTURE ROTA · OSM OK" in asunto and "taxonomy=AUSENTE" in detalle
    salida = capsys.readouterr().out
    assert "RESULTADO: DEGRADADO · OVERTURE ROTA · OSM OK · código 1" in salida


# ══ C · Overture sin red, OSM OK ═════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("excepcion", ["requests", "duckdb_http"])
def test_C_overture_sin_red_es_caida_y_osm_se_escribe(foso, monkeypatch, tmp_path, excepcion):
    import requests

    def _caida():
        if excepcion == "requests":
            raise requests.ConnectionError("Max retries exceeded")
        raise foso.duckdb.HTTPException("HTTP Error: 503 Service Unavailable")
    monkeypatch.setattr(foso, "pull_overture_taxonomia", _caida)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso, previos={"osm": 1})
    assert _corre(foso) == 2                                          # reintentable
    assert motor.ejecutadas(UPSERT_OV) == [] and motor.ejecutadas(CIERRA_OV) == []
    assert [r for r, _, _ in motor.ejecutadas(UPSERT_OSM)] == ["commit"]
    e = _estado(tmp_path)
    assert e["resultado"] == "DEGRADADO · OVERTURE CAÍDA · OSM OK"
    assert foso.avisos == [], "con 2 avisa el workflow al agotar los reintentos, no el script"


# ══ D · Overture OK, OSM sin red ═════════════════════════════════════════════════════════════════
def test_D_osm_sin_red_no_escribe_ni_cierra_y_overture_si(foso, monkeypatch, tmp_path):
    monkeypatch.setattr(foso, "pull_overture_taxonomia", lambda: [_ov(foso, "ov-a")])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: None)   # contrato: None = ningún endpoint
    motor = _motor(monkeypatch, foso, previos={"overture": 1}, cierres={"overture": 0})
    assert _corre(foso) == 2
    assert motor.ejecutadas(UPSERT_OSM) == [] and motor.ejecutadas(CIERRA_OSM) == []
    assert [r for r, _, _ in motor.ejecutadas(UPSERT_OV)] == ["commit"]
    assert _estado(tmp_path)["resultado"] == "DEGRADADO · OVERTURE OK · OSM CAÍDA"


# ══ E · las dos fallan ═══════════════════════════════════════════════════════════════════════════
def _solo_corridas(motor):
    """Desde R4, con las dos fuentes fallidas la base SOLO recibe sus corridas fallidas: ni DDL, ni POIs, ni
    cierres; cada corrida en SU transacción pequeña."""
    sentencias = [s for t in motor.transacciones for s, _ in t["sentencias"]]
    assert not any(s.startswith(("INSERT INTO pois_propios", "UPDATE pois_propios", "CREATE ", "ALTER "))
                   for s in sentencias), "0 escrituras, 0 cierres, 0 DDL"
    corridas = motor.ejecutadas("INSERT INTO poi_ingestion_run")
    assert len(motor.tx_con("INSERT INTO poi_ingestion_run")) == len(corridas) == 2
    return {p["source_provider"]: p for _, _, p in corridas}


def test_E_las_dos_fallan_no_escriben_y_no_dice_refrescada(foso, monkeypatch, tmp_path, capsys):
    def _rota():
        raise foso.duckdb.BinderException(f"Binder Error: {BINDER}!")
    monkeypatch.setattr(foso, "pull_overture_taxonomia", _rota)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: None)
    motor = _motor(monkeypatch, foso)
    assert _corre(foso) == 1
    c = _solo_corridas(motor)
    assert (c["overture"]["status"], c["overture"]["error_phase"]) == ("rota", "obtencion")
    assert (c["osm"]["status"], c["osm"]["error_class"]) == ("caida", "SinRespuesta")
    e = _estado(tmp_path)
    assert e["resultado"] == "SIN REFRESCO · OVERTURE ROTA · OSM CAÍDA"
    assert "La capa NO se actualizó" in capsys.readouterr().out
    [(asunto, _)] = foso.avisos
    assert "SIN REFRESCO · OVERTURE ROTA · OSM CAÍDA" in asunto


def test_E2_las_dos_caidas_es_reintentable_y_tampoco_escriben(foso, monkeypatch, tmp_path):
    import requests

    def _sin_red():
        raise requests.Timeout("timeout")
    monkeypatch.setattr(foso, "pull_overture_taxonomia", _sin_red)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: None)
    motor = _motor(monkeypatch, foso)
    assert _corre(foso) == 2 and foso.avisos == []
    assert {p["status"] for p in _solo_corridas(motor).values()} == {"caida"}
    assert _estado(tmp_path)["resultado"] == "SIN REFRESCO · OVERTURE CAÍDA · OSM CAÍDA"


# ══ F / G · un conjunto inválido invalida SU fuente entera (nada de escrituras parciales) ═════════
@pytest.mark.parametrize("dano", ["sin_id", "categoria_ajena", "coordenada_nan", "no_es_lista"])
def test_F_overture_invalido_no_escribe_nada_de_overture_y_osm_si(foso, monkeypatch, tmp_path, dano):
    filas = [_ov(foso, "ov-a"), _ov(foso, "ov-b")]
    if dano == "sin_id":
        filas[1]["overture_id"] = None
    elif dano == "categoria_ajena":
        filas[1]["categoria"] = "restaurante"
    elif dano == "coordenada_nan":
        filas[1]["lat"] = float("nan")
    else:
        filas = {"no": "lista"}
    monkeypatch.setattr(foso, "pull_overture_taxonomia", lambda: filas)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso, previos={"osm": 1})
    assert _corre(foso) == 1
    assert motor.ejecutadas(UPSERT_OV) == [] and motor.ejecutadas(CIERRA_OV) == [], "ni la fila sana se escribe"
    assert [r for r, _, _ in motor.ejecutadas(UPSERT_OSM)] == ["commit"]
    f = _fuentes(_estado(tmp_path))
    assert (f["overture"]["estado"], f["overture"]["fase"]) == ("rota", "validacion")
    assert f["overture"]["error"].startswith("dataset inválido")


@pytest.mark.parametrize("dano", ["id_mal_formado", "categoria_ajena", "fuente_ajena"])
def test_G_osm_invalido_no_escribe_nada_de_osm_y_overture_si(foso, monkeypatch, tmp_path, dano):
    filas = [_osm(foso, "node/1"), _osm(foso, "node/2")]
    if dano == "id_mal_formado":
        filas[0]["osm_id"] = "123"
    elif dano == "categoria_ajena":
        filas[0]["categoria"] = "salud"
    else:
        filas[0]["fuente"] = "overture"
    monkeypatch.setattr(foso, "pull_overture_taxonomia", lambda: [_ov(foso, "ov-a")])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: filas)
    motor = _motor(monkeypatch, foso, previos={"overture": 1})
    assert _corre(foso) == 1
    assert motor.ejecutadas(UPSERT_OSM) == [] and motor.ejecutadas(CIERRA_OSM) == []
    assert [r for r, _, _ in motor.ejecutadas(UPSERT_OV)] == ["commit"]
    f = _fuentes(_estado(tmp_path))
    assert (f["osm"]["estado"], f["osm"]["fase"]) == ("rota", "validacion")
    [(asunto, _)] = foso.avisos
    assert "DEGRADADO · OVERTURE OK · OSM ROTA" in asunto


# ══ H / I · solo una fuente obtenida y validada cierra, y con sus guardas ═════════════════════════
def test_H_una_fuente_fallida_no_cierra_aunque_tenga_muchos_previos(foso, monkeypatch):
    monkeypatch.setattr(foso, "pull_overture_taxonomia", lambda: (_ for _ in ()).throw(
        foso.duckdb.BinderException(f"Binder Error: {BINDER}!")))
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso, previos={"overture": 2753, "osm": 1})
    _corre(foso)
    assert motor.ejecutadas(CIERRA_OV) == [], "la fuente rota NO cierra sus 2753 POIs viejos"
    assert len(motor.ejecutadas(CIERRA_OSM)) == 1


@pytest.mark.parametrize("previos,cierra", [(2, True), (4, True), (5, False), (9061, False)])
def test_I_la_fuente_sana_cierra_solo_si_pasa_la_guarda_de_caida(foso, monkeypatch, capsys, previos, cierra):
    monkeypatch.setattr(foso, "pull_overture_taxonomia", lambda: [_ov(foso, "ov-a")])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1"), _osm(foso, "node/2")])
    motor = _motor(monkeypatch, foso, previos={"overture": 1, "osm": previos})
    assert _corre(foso) == 0
    assert bool(motor.ejecutadas(CIERRA_OSM)) is cierra                   # 2 filas vs previos·50 %
    if not cierra:
        assert "respuesta parcial, NO se cierra nada" in capsys.readouterr().out


# ══ J / K · un fallo DE ESCRITURA revierte solo su fuente ════════════════════════════════════════
def test_J_falla_el_upsert_de_overture_y_osm_igual_confirma(foso, monkeypatch, tmp_path):
    monkeypatch.setattr(foso, "pull_overture_taxonomia", lambda: [_ov(foso, "ov-a")])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso, previos={"osm": 1}, falla_en=UPSERT_OV)
    assert _corre(foso) == 1
    [t_ov], [t_osm] = motor.tx_con(UPSERT_OV), motor.tx_con(UPSERT_OSM)
    assert (t_ov["resultado"], t_osm["resultado"]) == ("rollback", "commit")
    assert motor.ejecutadas(CIERRA_OV) == []
    f = _fuentes(_estado(tmp_path))
    assert (f["overture"]["estado"], f["overture"]["fase"], f["overture"]["error"]) == ("rota", "escritura", "RuntimeError")
    assert f["overture"]["escritas"] == 0 and f["osm"]["escritas"] == 1


def test_K_falla_el_upsert_de_osm_y_overture_queda_confirmada(foso, monkeypatch, tmp_path):
    monkeypatch.setattr(foso, "pull_overture_taxonomia", lambda: [_ov(foso, "ov-a")])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso, previos={"overture": 1}, falla_en=UPSERT_OSM)
    assert _corre(foso) == 1
    [t_ov], [t_osm] = motor.tx_con(UPSERT_OV), motor.tx_con(UPSERT_OSM)
    assert (t_ov["resultado"], t_osm["resultado"]) == ("commit", "rollback")
    assert motor.ejecutadas(CIERRA_OSM) == []
    [(asunto, _)] = foso.avisos
    assert "DEGRADADO · OVERTURE OK · OSM ROTA" in asunto


def test_K2_falla_el_ddl_y_ninguna_fuente_escribe(foso, monkeypatch, tmp_path):
    monkeypatch.setattr(foso, "pull_overture_taxonomia", lambda: [_ov(foso, "ov-a")])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso, falla_en="CREATE TABLE IF NOT EXISTS pois_propios")
    assert _corre(foso) == 1
    assert motor.ejecutadas(UPSERT_OV) == motor.ejecutadas(UPSERT_OSM) == []
    assert {f["estado"] for f in _estado(tmp_path)["fuentes"]} == {"rota"}


# ══ L · camino feliz: mismas sentencias, mismos datos, mismas guardas que antes ═══════════════════
def test_L_camino_feliz_ejecuta_exactamente_lo_mismo_que_antes(foso, monkeypatch, capsys):
    ov, osm = [_ov(foso, "ov-a"), _ov(foso, "ov-b")], [_osm(foso, "node/1"), _osm(foso, "way/2", "parque", "park")]
    monkeypatch.setattr(foso, "pull_overture_taxonomia", lambda: ov)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: osm)
    motor = _motor(monkeypatch, foso, previos={"overture": 3, "osm": 2}, cierres={"overture": 1, "osm": 0})
    assert _corre(foso) == 0
    negocio = [(s, _sin_corrida(p) if isinstance(p, list) else p) for t in motor.transacciones
               for s, p in t["sentencias"] if s.startswith(("INSERT INTO pois_propios", "UPDATE pois_propios"))]
    # R3 (D-R3-2): Overture ya NO cierra por ausencia: sin `operating_status='closed'` declarado por la fuente no
    # hay UPDATE de cierre de Overture. OSM, idéntico a antes.
    esperado = [(" ".join(str(foso.UPSERT_OVERTURE).split()), ov),
                (" ".join(str(foso.UPSERT_OSM).split()), osm),
                (" ".join(str(foso.CERRAR_OSM).split()), {"ciudad": "quito", "ids": ["node/1", "way/2"]})]
    assert negocio == esperado
    salida = capsys.readouterr().out
    assert "upsert: 2 Overture + 2 OSM · marcados cerrados: 0" in salida
    assert motor.kw.get("connect_args") == {} and motor.url == URL_FALSA       # misma política TLS (loopback)


# ══ M · códigos de salida y su interacción con el workflow ═══════════════════════════════════════
@pytest.mark.parametrize("ov,osm,codigo", [
    ("ok", "ok", 0), ("ok", "caida", 2), ("caida", "ok", 2), ("caida", "caida", 2),
    ("rota", "ok", 1), ("ok", "rota", 1), ("rota", "caida", 1), ("caida", "rota", 1), ("rota", "rota", 1)])
def test_M_codigo_de_salida_por_combinacion(foso, ov, osm, codigo):
    fuentes = [foso.ResultadoFuente("overture", estado=ov), foso.ResultadoFuente("osm", estado=osm)]
    assert foso.codigo_de_salida(fuentes) == codigo


def _paso(flujo: str, nombre: str) -> str:
    i = flujo.index(f"- name: {nombre}")
    j = flujo.find("- name:", i + 1)
    return flujo[i:j if j > -1 else None]


def test_M_el_workflow_reintenta_2_no_reintenta_1_y_avisa_al_fallar():
    flujo = (RAIZ / ".github" / "workflows" / "refresco-pois.yml").read_text(encoding="utf-8")
    paso = _paso(flujo, "Refrescar POIs")
    assert 'python scripts/foso_pois_spike.py "${CIUDAD}" --sin-validacion' in paso
    assert re.search(r'if \[ "\$rc" = "0" \]; then break; fi', paso), "0 corta el bucle"
    assert re.search(r'if \[ "\$rc" = "1" \]; then.*?break', paso, re.S), "1 (fuente ROTA) no se reintenta"
    assert "sleep 600" in paso and "for intento in 1 2 3" in paso, "2 se reintenta"
    aviso = _paso(flujo, "Avisar del fallo")
    assert "if: failure()" in aviso and "--solo-avisar" in aviso


def test_M_solo_avisar_lee_el_resumen_por_fuente_de_la_ultima_corrida(foso, monkeypatch, tmp_path):
    """script ↔ workflow: lo que deja `_salir` es lo que lee el paso «Avisar del fallo»."""
    fuentes = [foso.ResultadoFuente("overture", estado="rota", release="2026-09-23.1", fase="obtencion",
                                    error=f"BinderException: Binder Error: {BINDER}!"),
               foso.ResultadoFuente("osm", estado="ok", obtenidas=3, validadas=3, escritas=3, cerradas=1)]
    foso._guarda_estado(fuentes, foso.veredicto(fuentes), foso.codigo_de_salida(fuentes))
    assert foso.avisar_tras_reintentos(["foso_pois_spike.py", "quito", "--solo-avisar", "codigo 1"]) is True
    [(asunto, detalle)] = foso.avisos
    assert asunto.endswith("· quito · DEGRADADO · OVERTURE ROTA · OSM OK")
    assert "Motivo/código: codigo 1" in detalle and "fuente=overture" in detalle and "estado=rota" in detalle


def test_M_solo_avisar_por_la_linea_de_comandos_real(tmp_path):
    """El mismo camino que el workflow: un proceso aparte, sin base, sin red, sin Resend."""
    estado = tmp_path / "estado.json"
    estado.write_text(json.dumps({"ciudad": "quito", "resultado": "DEGRADADO · OVERTURE OK · OSM CAÍDA", "codigo": 2,
                                  "fuentes": [{"fuente": "overture", "estado": "ok"},
                                              {"fuente": "osm", "estado": "caida", "error": "ningún endpoint respondió"}]}),
                      encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("RESEND", "ALERTA", "DATABASE"))}
    env.update(REFRESCO_POIS_ESTADO=str(estado), POSTGRES_DB="x", POSTGRES_USER="x", POSTGRES_PASSWORD="x",
               PYTHONUTF8="1")
    p = subprocess.run([sys.executable, str(SCRIPT), "quito", "--solo-avisar", "codigo 2"], env=env, cwd=RAIZ,
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert p.returncode == 0, p.stderr[-800:]
    assert "Aviso NO enviado" in p.stdout and "estado=caida" in p.stdout and "Motivo/código: codigo 2" in p.stdout


# ══ N · el aviso y el resumen distinguen la fuente, sin secretos ══════════════════════════════════
@pytest.mark.parametrize("rompe,esperado", [
    ("overture", "DEGRADADO · OVERTURE ROTA · OSM OK"),
    ("osm", "DEGRADADO · OVERTURE OK · OSM ROTA"),
    ("las_dos", "SIN REFRESCO · OVERTURE ROTA · OSM ROTA")])
def test_N_el_aviso_dice_que_fuente_se_rompio(foso, monkeypatch, tmp_path, capsys, rompe, esperado):
    def _rota():
        raise foso.duckdb.BinderException(f"Binder Error: {BINDER}!")
    monkeypatch.setattr(foso, "pull_overture_taxonomia", _rota if rompe in ("overture", "las_dos") else lambda: [_ov(foso, "ov-a")])
    monkeypatch.setattr(foso, "pull_osm_transporte",
                        (lambda: [{"roto": True}]) if rompe in ("osm", "las_dos") else (lambda: [_osm(foso, "node/1")]))
    motor = _motor(monkeypatch, foso, previos={"overture": 1, "osm": 1})
    assert _corre(foso) == 1
    [(asunto, detalle)] = foso.avisos
    assert esperado in asunto
    salida = capsys.readouterr().out
    for linea in [l for l in salida.splitlines() if l.strip().startswith("fuente=")]:
        for campo in ("release=", "estado=", "obtenidas=", "validadas=", "escritas=", "cerradas=", "segundos="):
            assert campo in linea
    todo = salida + asunto + detalle + (tmp_path / "estado.json").read_text(encoding="utf-8")
    assert "clave-que-no-debe-salir" not in todo and "refresco:" not in todo


def test_N_un_error_de_escritura_solo_deja_la_clase(foso, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(foso, "pull_overture_taxonomia", lambda: [_ov(foso, "ov-a")])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    _motor(monkeypatch, foso, previos={"overture": 1}, falla_en=UPSERT_OSM)
    _corre(foso)
    todo = capsys.readouterr().out + (tmp_path / "estado.json").read_text(encoding="utf-8") + str(foso.avisos)
    assert "db.secreto" not in todo and "fallo simulado" not in todo, "el texto del error de base no se publica"


# ══ POSTGIS · el main() REAL escribiendo en un esquema desechable con las migraciones reales ═══════
URL_PG = os.getenv("TEST_POSTGIS_URL", "")            # postgresql+psycopg://… con PostGIS (local)
pg = pytest.mark.skipif(not URL_PG, reason="sin TEST_POSTGIS_URL: el Postgres del CI no trae PostGIS")
MIGRACIONES = ("014_pois_propios.sql", "019_pois_propios_ciudad.sql", "020_pois_propios_id_origen_unico.sql",
               "021_pois_propios_iglesia_seguridad.sql", "022_osm_id_con_tipo.sql", "023_curacion_engancha_poi.sql")


def aplica_043(c, esquema: str) -> None:
    """La 043 REAL sobre el esquema desechable: su texto nombra `public.`, que aquí es `<esquema>.`. Antes, lo
    mínimo del perímetro de la 040 que la 043 exige como precondición (RLS en la capa, `security_invoker` en la
    vista); el dueño es quien aplica, sin grantees externos."""
    c.execute("ALTER TABLE pois_propios ENABLE ROW LEVEL SECURITY")
    c.execute("ALTER VIEW pois_vivos SET (security_invoker = true)")
    sql = (RAIZ / "migrations" / "043_poi_source_provenance.sql").read_text(encoding="utf-8")
    c.execute(sql.replace("public.", f"{esquema}."))
VIEJO = "2026-09-22 14:30:03+00"


def _conninfo() -> str:
    from sqlalchemy.engine import make_url
    u = make_url(URL_PG)
    return f"host={u.host} port={u.port} dbname={u.database} user={u.username} password={u.password}"


def _banco(conninfo: str, esquema: str) -> dict:
    """Un esquema desechable con las migraciones REALES de la capa y 2 filas de Overture + 3 de OSM viejas."""
    import psycopg
    with psycopg.connect(conninfo, autocommit=True) as c:
        c.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        c.execute(f"CREATE SCHEMA {esquema}")
        c.execute(f"SET search_path TO {esquema}, public")
        for mig in MIGRACIONES:
            c.execute((RAIZ / "migrations" / mig).read_text(encoding="utf-8"))
        aplica_043(c, esquema)
        c.execute(f"""
            INSERT INTO pois_propios (nombre, categoria, categoria_overture, geom, fuente, confianza, overture_id, osm_id,
                                      operativo, ciudad, actualizado_en) VALUES
              ('Overture viejo a', 'salud', 'hospital', ST_SetSRID(ST_MakePoint(-78.5,-0.2),4326), 'overture', 0.9, 'ov-a', NULL, true, 'quito', '{VIEJO}'),
              ('Overture viejo b', 'salud', 'hospital', ST_SetSRID(ST_MakePoint(-78.5,-0.2),4326), 'overture', 0.9, 'ov-b', NULL, true, 'quito', '{VIEJO}'),
              ('OSM viejo 1', 'transporte', 'parada_bus', ST_SetSRID(ST_MakePoint(-78.49,-0.19),4326), 'osm', NULL, NULL, 'node/1', true, 'quito', '{VIEJO}'),
              ('OSM viejo 2', 'transporte', 'parada_bus', ST_SetSRID(ST_MakePoint(-78.49,-0.19),4326), 'osm', NULL, NULL, 'node/2', true, 'quito', '{VIEJO}'),
              ('OSM viejo 3', 'transporte', 'parada_bus', ST_SetSRID(ST_MakePoint(-78.49,-0.19),4326), 'osm', NULL, NULL, 'node/3', true, 'quito', '{VIEJO}')
        """)
    return {"conninfo": conninfo, "esquema": esquema, "url": f"{URL_PG}?options=-csearch_path%3D{esquema}%2Cpublic"}


def _borra(conninfo: str, esquema: str) -> None:
    import psycopg
    with psycopg.connect(conninfo, autocommit=True) as c:
        c.execute(f"DROP SCHEMA IF EXISTS {esquema} CASCADE")


@pytest.fixture
def esquema_pg():
    if "localhost" not in URL_PG and "127.0.0.1" not in URL_PG:
        pytest.fail("TEST_POSTGIS_URL debe ser loopback: estas pruebas escriben")
    esquema = f"poi_iso_{uuid.uuid4().hex[:10]}"
    banco = _banco(_conninfo(), esquema)
    yield banco
    _borra(banco["conninfo"], esquema)


def _foto(esq) -> dict:
    import psycopg
    with psycopg.connect(esq["conninfo"]) as c:
        c.execute(f"SET search_path TO {esq['esquema']}, public")
        filas = c.execute("""SELECT coalesce(overture_id, osm_id), fuente, nombre, categoria, categoria_overture, confianza,
                                    operativo, actualizado_en > %s::timestamptz, ST_AsText(geom)
                             FROM pois_propios ORDER BY 1""", (VIEJO,)).fetchall()
    return {f[0]: {"fuente": f[1], "nombre": f[2], "categoria": f[3], "sub": f[4], "conf": f[5], "operativo": f[6],
                   "tocada": f[7], "geom": f[8]} for f in filas}


def _trigger_que_falla(esq, columna, valor):
    import psycopg
    with psycopg.connect(esq["conninfo"], autocommit=True) as c:
        c.execute(f"SET search_path TO {esq['esquema']}, public")
        c.execute(f"""CREATE FUNCTION falla_en_{columna}() RETURNS trigger LANGUAGE plpgsql AS $$
                      BEGIN IF NEW.{columna} = '{valor}' THEN RAISE EXCEPTION 'fallo forzado'; END IF; RETURN NEW; END $$""")
        c.execute(f"CREATE TRIGGER t_falla BEFORE INSERT OR UPDATE ON pois_propios FOR EACH ROW "
                  f"EXECUTE FUNCTION falla_en_{columna}()")


@pg
def test_PG_B_overture_rota_real_osm_escribe_y_cierra_overture_intacta(foso, duckdb_spatial, esquema_pg,
                                                                         monkeypatch, tmp_path):
    antes = _foto(esquema_pg)
    monkeypatch.setattr(foso, "SYNC_URL", esquema_pg["url"])
    roto = _parquet_r3(duckdb_spatial, tmp_path / "sin_taxonomy.parquet", sin_taxonomy=True)   # R3: fallo REAL
    monkeypatch.setattr(foso, "overture_glob", lambda rel: roto)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [
        {**_osm(foso, "node/1"), "nombre": "OSM refrescado 1"}, _osm(foso, "node/2"), _osm(foso, "node/4")])
    assert _corre(foso) == 1
    d = _foto(esquema_pg)
    assert {k: d[k] for k in ("ov-a", "ov-b")} == {k: antes[k] for k in ("ov-a", "ov-b")}, "Overture: 0 escrituras"
    assert d["node/1"]["nombre"] == "OSM refrescado 1" and d["node/1"]["tocada"]
    assert d["node/4"]["operativo"] and d["node/2"]["tocada"]
    assert d["node/3"]["operativo"] is False, "OSM cierra lo que ya no vino (3 de 4 ≥ 50 %)"
    f = _fuentes(_estado(tmp_path))
    assert (f["overture"]["estado"], f["osm"]["estado"], f["osm"]["escritas"], f["osm"]["cerradas"]) == ("rota", "ok", 3, 1)


@pg
def test_PG_J_un_fallo_a_mitad_del_upsert_de_overture_lo_revierte_entero_y_osm_confirma(
        foso, esquema_pg, monkeypatch, tmp_path):
    _trigger_que_falla(esquema_pg, "overture_id", "ov-boom")
    antes = _foto(esquema_pg)
    monkeypatch.setattr(foso, "SYNC_URL", esquema_pg["url"])
    monkeypatch.setattr(foso, "pull_overture_taxonomia", lambda: [{**_ov(foso, "ov-a"), "nombre": "Overture NUEVO a"},
                                                         _ov(foso, "ov-boom")])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1"), _osm(foso, "node/2"),
                                                              _osm(foso, "node/3")])
    assert _corre(foso) == 1
    d = _foto(esquema_pg)
    assert d["ov-a"] == antes["ov-a"], "la fila de Overture escrita ANTES del fallo se revirtió con su fuente"
    assert "ov-boom" not in d
    assert all(d[k]["tocada"] for k in ("node/1", "node/2", "node/3")), "OSM confirmó en SU transacción"


@pg
def test_PG_K_un_fallo_a_mitad_del_upsert_de_osm_no_toca_overture_ya_confirmada(foso, esquema_pg, monkeypatch, tmp_path):
    _trigger_que_falla(esquema_pg, "osm_id", "node/666")
    antes = _foto(esquema_pg)
    monkeypatch.setattr(foso, "SYNC_URL", esquema_pg["url"])
    monkeypatch.setattr(foso, "pull_overture_taxonomia", lambda: [{**_ov(foso, "ov-a"), "nombre": "Overture NUEVO a"},
                                                         _ov(foso, "ov-b")])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [{**_osm(foso, "node/1"), "nombre": "OSM NUEVO 1"},
                                                              _osm(foso, "node/666")])
    assert _corre(foso) == 1
    d = _foto(esquema_pg)
    assert d["ov-a"]["nombre"] == "Overture NUEVO a" and d["ov-a"]["tocada"], "Overture confirmó"
    assert {k: d[k] for k in ("node/1", "node/2", "node/3")} == {k: antes[k] for k in ("node/1", "node/2", "node/3")}
    assert "node/666" not in d


def _script_anterior(tmp_path) -> pathlib.Path | None:
    p = subprocess.run(["git", "show", "25303ff3b9cf30ed316ebb0b8af602e2b6100279:scripts/foso_pois_spike.py"],
                       cwd=RAIZ, capture_output=True)
    if p.returncode != 0:
        return None
    ruta = tmp_path / "foso_anterior.py"
    ruta.write_bytes(p.stdout)
    return ruta


@pg
def test_PG_L_camino_feliz_deja_la_tabla_igual_que_el_script_anterior(foso, esquema_pg, monkeypatch, tmp_path):
    ruta = _script_anterior(tmp_path)
    if ruta is None:
        pytest.skip("sin historia git (clon superficial): no hay script anterior con que comparar")
    viejo = _carga(ruta, "foso_anterior")
    ov = [{**_ov(foso, "ov-a"), "nombre": "Overture NUEVO a"}, _ov(foso, "ov-c")]
    osm = [_osm(foso, "node/1"), _osm(foso, "node/2"), _osm(foso, "way/9", "parque", "park")]
    siembra = _foto(esquema_pg)
    # el NUEVO sobre este esquema…
    monkeypatch.setattr(foso, "SYNC_URL", esquema_pg["url"])
    monkeypatch.setattr(foso, "pull_overture_taxonomia", lambda: ov)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: osm)
    assert _corre(foso) == 0
    nuevo = _foto(esquema_pg)
    # …y el ANTERIOR sobre un esquema GEMELO (mismas migraciones, misma siembra), con las mismas fuentes
    gemelo = _banco(esquema_pg["conninfo"], f"{esquema_pg['esquema']}_v")
    try:
        monkeypatch.setattr(viejo, "SYNC_URL", gemelo["url"])
        monkeypatch.setattr(viejo, "pull_overture", lambda: [dict(p) for p in ov])
        monkeypatch.setattr(viejo, "pull_osm_transporte", lambda: [dict(p) for p in osm])
        with pytest.raises(SystemExit) as salida:
            viejo.main()
        assert salida.value.code == 0
        anterior = _foto(gemelo)
    finally:
        _borra(gemelo["conninfo"], gemelo["esquema"])
    # R3 (D-R3-2): la ÚNICA diferencia con el script anterior es la que manda el fundador. `ov-b` ya no vino de
    # Overture: el anterior la cerraba por ausencia (afirmaba «cerrado» sin que la fuente lo dijera); R3 no la toca.
    assert {k for k in nuevo if nuevo[k] != anterior.get(k)} == {"ov-b"}, "todo lo demás, EXACTAMENTE igual"
    assert anterior["ov-b"]["operativo"] is False and nuevo["ov-b"] == siembra["ov-b"], "R3: ov-b intacta"
    assert nuevo["node/3"]["operativo"] is False, "OSM sigue cerrando por ausencia (no cambia)"
