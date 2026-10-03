"""R3 · OPERATING STATUS SEMANTICS · la matriz de estado del lector `overture_places_taxonomy_v1`.

Contrato OFICIAL de Overture (`schema/places/place.yaml`, v2.0.0; el mismo enum desde v1.16.0): `operating_status ∈
{open, permanently_closed, temporarily_closed}`, opcional desde v1.17.0 y NULL por defecto desde la nota de 2026-05-20.
`closed` NO existe. Evidencia: RESULTADO_2026-10-02_R3_OPERATING_STATUS_SEMANTICS_PREFLIGHT.md.

Matriz AUTORIZADA (D-OS-1…6), sobre observaciones que la regla acepta por taxonomía + ruta exacta:

                              NUEVA          OPERATIVA        CERRADA
    open + confianza OK       INSERT         UPDATE           REOPEN
    NULL + confianza OK       INSERT         UPDATE           NO TOUCH (cuenta + aviso)
    temporarily_closed        NO INSERT      CLOSE            KEEP CLOSED
    permanently_closed        NO INSERT      CLOSE            KEEP CLOSED
    valor fuera del enum      Overture ROTA al obtener: 0 escrituras, 0 cambios de estado, corrida fallida

La confianza de Contexto decide la PRESENCIA (open / NULL), nunca un cierre. Un cierre explícito solo muta una fila
EXISTENTE cuya `categoria` sigue siendo la que la regla da a su taxonomía (§3: no mezclar taxonomía y estado).

OS1–OS16 del mandato + T-ENUM, categoría incompatible, cobertura con cierres y la RECONSTRUCCIÓN M0 del cierre
(GERS + `ingestion_run_id` → `source_release` / `source_endpoint` → el registro de Overture → `operating_status`).
Capas: ORQUESTACIÓN (motor falso de #189) corre en el CI; POSTGIS (`TEST_POSTGIS_URL`) solo en local.
"""
from __future__ import annotations

import ast
import json

import pytest

from tests.test_poi_refresh_source_isolation import (  # noqa: F401 — fixtures y ayudantes de #189 / R4
    BASE_R3, RAIZ, VIEJO, _corre, _estado, _fuentes, _motor, _osm, _parquet_r3, duckdb_spatial, esquema_pg, foso, pg)
from tests.test_poi_source_provenance_writer import _corridas, _corridas_bd, _provenance, _psql
from tests.test_r3_overture_taxonomy import (ACEPTADAS_BASE, CIERRE_OV, UPSERT_OSM, UPSERT_OV, _con,
                                             _con_lector_real, _estables, _fila, _filas_json, _invariante_m0)

PH = ("pharmacy", "shopping > specialty_store > pharmacy_and_drug_store > pharmacy")    # farmacia · CONF_MIN 0,55
PK = ("park", "sports_and_recreation > park")                                            # parque · CONF_MIN 0,70
LECTURA_PREVIA = "AS operativo_en_capa"


def _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path, extra, capa, cobertura=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    _con_lector_real(foso, duckdb_spatial, monkeypatch, tmp_path, _con(BASE_R3, *extra))
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso, previos={"osm": 1}, capa=capa, cobertura=cobertura or {}, cierres={"overture": 99})
    return motor, _corre(foso)


def _escritas(motor) -> dict:
    [(res, _, filas)] = motor.ejecutadas(UPSERT_OV)
    assert res == "commit"
    return {f["overture_id"]: f for f in filas}


def _obs(tmp_path) -> dict:
    return _fuentes(_estado(tmp_path))["overture"]["observacion"]


# ══════════════════════════════════════════ CONTRATO ══════════════════════════════════════════════
def test_T_ENUM_el_contrato_es_el_oficial_y_cada_valor_tiene_su_clase_explicita(foso):
    assert foso.ESTADOS_OPERATIVOS_V1 == ("open", "permanently_closed", "temporarily_closed"), "schema v2.0.0"
    assert {v: foso.clase_de_estado(v) for v in (None, *foso.ESTADOS_OPERATIVOS_V1)} == {
        None: "UNKNOWN_STATUS", "open": "OPEN", "permanently_closed": "PERMANENTLY_CLOSED",
        "temporarily_closed": "TEMPORARILY_CLOSED"}
    for invalido in ("closed", "Open", "OPEN", "", "unknown", 0, 1.0, b"open", ["open"]):
        assert foso.clase_de_estado(invalido) == "INVALID_STATUS", repr(invalido)
    assert foso.CLASES_PRESENCIA == {"OPEN", "UNKNOWN_STATUS"}
    assert foso.CLASES_CERRADAS == {"TEMPORARILY_CLOSED", "PERMANENTLY_CLOSED"}


def test_T_ENUM_ningun_equivalente_implicito_de_closed_fuera_del_lector_viejo():
    """`estado != "closed"` (o `== "closed"`) no vuelve: el único que queda es el lector VIEJO congelado
    (`pull_overture`, `overture_places_categories_v1`, idéntico a 5436561 y que no se ejecuta en R3)."""
    arbol = ast.parse((RAIZ / "scripts" / "foso_pois_spike.py").read_text(encoding="utf-8"))
    hallados = []
    for f in (n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef) and n.name != "pull_overture"):
        for c in (n for n in ast.walk(f) if isinstance(n, ast.Compare)):
            if any(isinstance(x, ast.Constant) and x.value == "closed" for x in [c.left, *c.comparators]):
                hallados.append(f"{f.name}:{c.lineno}")
    assert hallados == []


# ══════════════════════════════════ OS1–OS12 · la matriz (CI) ═══════════════════════════════════
# (id, operating_status, confianza, estado previo en la capa, decisión, ¿se escribe?, operativo escrito, rows_closed)
MATRIZ = [
    ("OS1_open_sobre_cerrada_reabre", "open", 0.9, (False, "farmacia"), "reabiertas", True, True, 0),
    ("OS1b_open_sobre_operativa", "open", 0.9, (True, "farmacia"), "actualizadas", True, True, 0),
    ("OS1c_open_nueva", "open", 0.9, None, "insertadas", True, True, 0),
    ("OS2_null_sobre_cerrada_no_se_toca", None, 0.9, (False, "farmacia"), "reobservadas_sin_open_explicito", False,
     None, 0),
    ("OS3_null_sobre_operativa_sigue_operativa", None, 0.9, (True, "farmacia"), "actualizadas", True, True, 0),
    ("OS4_null_nueva_entra_operativa", None, 0.9, None, "insertadas", True, True, 0),
    ("OS5_permanent_sobre_operativa_cierra", "permanently_closed", 0.9, (True, "farmacia"), "cerradas", True, False, 1),
    ("OS6_permanent_sobre_cerrada_sigue_cerrada", "permanently_closed", 0.9, (False, "farmacia"), "siguen_cerradas",
     True, False, 0),
    ("OS7_permanent_nueva_no_se_crea", "permanently_closed", 0.9, None, "cerradas_nuevas_omitidas", False, None, 0),
    ("OS8_permanent_con_confianza_0_cierra", "permanently_closed", 0.0, (True, "farmacia"), "cerradas", True, False, 1),
    ("OS9_permanent_bajo_el_umbral_cierra", "permanently_closed", 0.40, (True, "farmacia"), "cerradas", True, False, 1),
    ("OS9b_permanent_con_confianza_NULL_cierra", "permanently_closed", None, (True, "farmacia"), "cerradas", True,
     False, 1),
    ("OS10_temporary_sobre_operativa_cierra", "temporarily_closed", 0.9, (True, "farmacia"), "cerradas", True, False, 1),
    ("OS11_temporary_sobre_cerrada_sigue_cerrada", "temporarily_closed", 0.9, (False, "farmacia"), "siguen_cerradas",
     True, False, 0),
    ("OS12_temporary_nueva_no_se_crea", "temporarily_closed", 0.9, None, "cerradas_nuevas_omitidas", False, None, 0),
]


@pytest.mark.parametrize("caso,estado,conf,previo,decision,escrita,operativo,cierres", MATRIZ, ids=[m[0] for m in MATRIZ])
def test_OS1_OS12_cada_celda_de_la_matriz(foso, duckdb_spatial, monkeypatch, tmp_path, caso, estado, conf, previo,
                                          decision, escrita, operativo, cierres):
    capa = {"os-x": previo} if previo else {}
    motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path,
                              [_fila("os-x", *PH, conf=conf, estado=estado)], capa)
    assert codigo == 0
    escritas = _escritas(motor)
    run = _corridas(motor)["overture"][1]
    if escrita:
        f = escritas["os-x"]
        assert (f["operativo"], f["ingestion_run_id"], f["categoria"], f["source_category"],
                f["source_category_namespace"], f["cat_leaf"]) == (operativo, run["id"], "farmacia", "pharmacy",
                                                                   "overture:taxonomy.primary", None)
        assert foso.categoria_de_la_regla(run["reader_contract"], f["source_category_namespace"],
                                          f["source_category"]) == f["categoria"], "M0: procedencia → regla → categoría"
    else:
        assert "os-x" not in escritas, f"{caso}: la fila NO se escribe (ni se crea, ni se reabre, ni se re-enlaza)"
    assert run["rows_closed"] == cierres, "rows_closed = transiciones REALES abierta → cerrada"
    assert run["rows_written"] == len(escritas)
    assert motor.ejecutadas(CIERRE_OV) == [], "Overture no tiene sentencia de cierre propia"
    # las 11 aceptadas de BASE_R3 no están en la capa: también son `insertadas`
    assert _obs(tmp_path)["matriz"][decision] == 1 + (len(ACEPTADAS_BASE) if decision == "insertadas" else 0)


def test_OS2_null_sobre_cerrada_se_cuenta_y_se_avisa(foso, duckdb_spatial, monkeypatch, tmp_path):
    motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path, [_fila("os-x", *PH, estado=None)],
                              {"os-x": (False, "farmacia")})
    assert codigo == 0 and "os-x" not in _escritas(motor)
    [(asunto, detalle)] = foso.avisos
    assert "AVISO DE TAXONOMÍA Y ESTADO" in asunto
    assert "1 POI(s) CERRADOS de la capa reaparecen con operating_status NULL" in detalle and "os-x" in detalle


def test_OS9_el_umbral_de_contexto_decide_la_presencia_nunca_el_cierre(foso, duckdb_spatial, monkeypatch, tmp_path):
    """Parque (CONF_MIN 0,70) a 0,60: por ENCIMA del piso y por DEBAJO de su umbral. `open` así NO entra (presencia);
    `permanently_closed` así SÍ cierra la fila existente (D-OS-2)."""
    extra = [_fila("os-open-bajo", *PK, conf=0.60, estado="open"),
             _fila("os-cierre-bajo", *PK, conf=0.60, estado="permanently_closed")]
    capa = {"os-open-bajo": (False, "parque"), "os-cierre-bajo": (True, "parque")}
    motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path, extra, capa)
    assert codigo == 0
    escritas = _escritas(motor)
    assert "os-open-bajo" not in escritas, "un `open` bajo el umbral no se acepta: no reabre"
    assert escritas["os-cierre-bajo"]["operativo"] is False
    o = _obs(tmp_path)
    assert o["bajo_confianza"] == {"salud": 1, "parque": 2} and o["cerrados_aceptados"] == {"PERMANENTLY_CLOSED": 1}


def test_temporary_luego_solo_un_open_explicito_la_reabre(foso, duckdb_spatial, monkeypatch, tmp_path):
    """D-OS-3 en dos corridas del motor falso: temporarily_closed cierra; NULL después NO la reabre; open SÍ."""
    capa = {"os-t": (True, "farmacia")}
    for estado, previo, decision in (("temporarily_closed", (True, "farmacia"), "cerradas"),
                                     (None, (False, "farmacia"), "reobservadas_sin_open_explicito"),
                                     ("open", (False, "farmacia"), "reabiertas")):
        capa["os-t"] = previo
        motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path / estado if estado else tmp_path / "null",
                                  [_fila("os-t", *PH, estado=estado)], capa)
        assert codigo == 0 and _obs(tmp_path)["matriz"][decision] == 1, (estado, decision)


# ══════════════════════════════ OS13 · enum inválido (CI) ═══════════════════════════════════════
@pytest.mark.parametrize("invalido", ["closed", "OPEN", "unknown", ""])
def test_OS13_enum_invalido_overture_rota_cero_escrituras_y_corrida_fallida(foso, duckdb_spatial, monkeypatch, tmp_path,
                                                                            invalido):
    motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path,
                              [_fila("os-x", *PH, estado=invalido), _fila("os-y", *PH, estado="permanently_closed")],
                              {"os-x": (True, "farmacia"), "os-y": (True, "farmacia")})
    assert codigo == 1
    for fragmento in ("cobertura_previa", LECTURA_PREVIA, UPSERT_OV, CIERRE_OV):
        assert motor.ejecutadas(fragmento) == [], f"nada de Overture antes ni después: {fragmento}"
    o = _corridas(motor)["overture"][1]
    assert (o["status"], o["error_phase"], o["error_class"], o["rows_written"], o["rows_closed"]) == (
        "rota", "obtencion", "EstadoOperativoInvalido", None, None)
    assert [r for r, _, _ in motor.ejecutadas(UPSERT_OSM)] == ["commit"], "OSM no se entera (aislamiento de R4)"
    assert repr(invalido) in _fuentes(_estado(tmp_path))["overture"]["error"]


# ═══════════════════ OS14–OS15 · cierre explícito que la regla no acepta (CI) ════════════════════
@pytest.mark.parametrize("caso,fila,motivo", [
    ("OS14_taxonomia_sin_regla", _fila("os-x", "dental_clinic", "health_care > outpatient_care_facility > dental_clinic",
                                       estado="permanently_closed"), "descendiente"),
    ("OS14b_fuera_del_mapa", _fila("os-x", "restaurant", "food_and_drink > restaurant", estado="permanently_closed"),
     "fuera_del_mapa"),
    ("OS14c_taxonomia_NULL", _fila("os-x", None, None, estado="temporarily_closed"), "sin_taxonomia"),
    ("OS14d_nodo_padre", _fila("os-x", "health_care", "health_care", estado="permanently_closed"), "nodo_padre"),
    ("OS15_jerarquia_invalida", _fila("os-x", "hospital", "health_care > clinic", estado="permanently_closed"),
     "jerarquia_invalida")])
def test_OS14_OS15_cierre_no_representable_cuenta_avisa_y_no_muta(foso, duckdb_spatial, monkeypatch, tmp_path, caso,
                                                                  fila, motivo):
    motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path, [fila], {"os-x": (True, "salud")})
    assert codigo == 0
    assert "os-x" not in _escritas(motor) and motor.ejecutadas(CIERRE_OV) == []
    o = _obs(tmp_path)
    assert o["cerrados_no_representables"] == {motivo: 1} and o["cerrados_no_representables_en_capa"] == ["os-x"]
    assert _corridas(motor)["overture"][1]["rows_closed"] == 0
    [(_, detalle)] = foso.avisos
    assert "1 POI(s) ACTIVOS de la capa" in detalle and "os-x" in detalle


def test_OS15b_cierre_con_ruta_distinta_en_hoja_aceptada_es_deriva_y_nada_se_muta(foso, duckdb_spatial, monkeypatch,
                                                                                  tmp_path):
    """La política source-invalid YA PROBADA: una hoja aceptada con otra jerarquía es DERIVA, con cualquier estado."""
    motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path,
                              [_fila("os-x", "hospital", "health_care > medical_facility > hospital",
                                     estado="permanently_closed")], {"os-x": (True, "salud")})
    assert codigo == 1
    for fragmento in ("cobertura_previa", LECTURA_PREVIA, UPSERT_OV):
        assert motor.ejecutadas(fragmento) == [], fragmento
    assert _corridas(motor)["overture"][1]["error_class"] == "DerivaTaxonomia"


def test_cierre_con_categoria_incompatible_cuenta_avisa_y_no_muta(foso, duckdb_spatial, monkeypatch, tmp_path):
    """§3: un cierre explícito NO muta una fila cuya categoría vigente no es la que la regla da a su taxonomía."""
    motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path,
                              [_fila("os-x", *PH, estado="permanently_closed")], {"os-x": (True, "salud")})
    assert codigo == 0 and "os-x" not in _escritas(motor)
    assert _obs(tmp_path)["matriz"]["cierre_categoria_incompatible"] == 1
    assert _corridas(motor)["overture"][1]["rows_closed"] == 0
    [(_, detalle)] = foso.avisos
    assert "categoría vigente NO es la que la regla da a su taxonomía" in detalle and "os-x" in detalle


# ═══════════════════ cobertura: un cierre es ESTADO, no desaparición de la taxonomía (CI) ══════════════════
def test_la_cobertura_cuenta_los_cierres_explicitos_y_no_los_confunde_con_deriva(foso, duckdb_spatial, monkeypatch,
                                                                                 tmp_path):
    cerradas = [_fila(f"os-c{i}", *PH, estado="permanently_closed") for i in range(11)]
    capa = {f"os-c{i}": (True, "farmacia") for i in range(11)}
    motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path, cerradas, capa, cobertura={"farmacia": 12})
    assert codigo == 0, "12 observaciones de farmacia (1 presencia + 11 cierres) ≥ 12·90 %: no es deriva"
    assert _corridas(motor)["overture"][1]["rows_closed"] == 11
    assert _obs(tmp_path)["cobertura"]["farmacia"] == [12, 12]
    # contraste: si esas 11 DESAPARECEN del release (no un cierre), la guarda sí dispara
    motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path / "b", [], capa, cobertura={"farmacia": 12})
    assert codigo == 1 and _corridas(motor)["overture"][1]["error_class"] == "CaidaDeCobertura"


def test_invalidas_exige_la_clase_de_estado_y_su_operativo(foso, duckdb_spatial, monkeypatch, tmp_path):
    from tests.test_r3_overture_taxonomy import _lee
    filas, obs = _lee(foso, duckdb_spatial, monkeypatch, tmp_path,
                      _con(BASE_R3, _fila("os-c", *PH, estado="permanently_closed")))
    estados = dict(obs["estados"])
    assert foso._invalidas("overture", filas, foso.LECTOR_OVERTURE_TAXONOMIA, estados) == []
    sin_clase = {k: v for k, v in estados.items() if k != "os-c"}
    assert foso._invalidas("overture", filas, foso.LECTOR_OVERTURE_TAXONOMIA, sin_clase) == [
        "1 fila(s) con estado operativo de la fuente"]
    mentira = {**estados, "os-c": "UNKNOWN_STATUS"}                      # operativo=false con clase de presencia
    assert foso._invalidas("overture", filas, foso.LECTOR_OVERTURE_TAXONOMIA, mentira) == [
        "1 fila(s) con estado operativo de la fuente"]


# ══════════════════════════════ OS16 · las 31 históricas (CI) ═════════════════════════════════════
def test_OS16_31_historicas_cerradas_reobservadas_con_NULL_cero_reaperturas(foso, duckdb_spatial, monkeypatch, tmp_path):
    """El caso del preflight: 31 filas CERRADAS en la capa (cerradas por la lógica vieja de AUSENCIA), que el release
    actual trae con operating_status NULL y taxonomía + confianza aceptables → 31 siguen cerradas, 0 reabiertas, 31
    contadas como `reobservadas_sin_open_explicito` y avisadas."""
    historicas = [_fila(f"h31-{i:02d}", *PH, conf=0.80, estado=None) for i in range(31)]
    capa = {f"h31-{i:02d}": (False, "farmacia") for i in range(31)}
    motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path, historicas, capa)
    assert codigo == 0
    escritas = _escritas(motor)
    assert not (set(capa) & set(escritas)), "ninguna de las 31 se escribe: ni se reabre ni se re-enlaza"
    o = _obs(tmp_path)
    assert o["matriz"] == {"insertadas": len(ACEPTADAS_BASE), "reobservadas_sin_open_explicito": 31}
    assert _corridas(motor)["overture"][1]["rows_closed"] == 0
    [(_, detalle)] = foso.avisos
    assert "31 POI(s) CERRADOS de la capa reaparecen con operating_status NULL" in detalle


# ══════════════════════════════════════════ POSTGIS (local) ═══════════════════════════════════════
def _siembra(esq, filas):
    """Filas LEGADAS (sin procedencia), con su estado: (overture_id, categoria, categories.primary, operativo)."""
    import psycopg
    with psycopg.connect(esq["conninfo"], autocommit=True) as c:
        c.execute(f"SET search_path TO {esq['esquema']}, public")
        for oid, cat, legado, op in filas:
            c.execute("INSERT INTO pois_propios (nombre, categoria, categoria_overture, geom, fuente, confianza, "
                      "overture_id, operativo, ciudad, actualizado_en) VALUES (%s, %s, %s, "
                      "ST_SetSRID(ST_MakePoint(-78.5,-0.2),4326), 'overture', 0.9, %s, %s, 'quito', %s)",
                      (f"Legado {oid}", cat, legado, oid, op, VIEJO))


@pg
def test_PG_OS16_las_31_historicas_quedan_byte_a_byte(foso, duckdb_spatial, esquema_pg, monkeypatch, tmp_path):
    _siembra(esquema_pg, [(f"h31-{i:02d}", "farmacia", "pharmacy", False) for i in range(31)])
    antes = _filas_json(esquema_pg)
    monkeypatch.setattr(foso, "SYNC_URL", esquema_pg["url"])
    monkeypatch.setattr(foso, "huella_esquema_overture", foso._huella_real)
    _con_lector_real(foso, duckdb_spatial, monkeypatch, tmp_path,
                     BASE_R3 + _estables(5) + [_fila(f"h31-{i:02d}", *PH, conf=0.80) for i in range(31)])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    assert _corre(foso) == 0
    d = _filas_json(esquema_pg)
    for oid in (f"h31-{i:02d}" for i in range(31)):
        assert d[oid] == antes[oid], f"{oid}: NULL no reabre ni re-enlaza: la fila, byte a byte"
        assert json.loads(d[oid])["operativo"] is False and json.loads(d[oid])["ingestion_run_id"] is None
    run = [c for c in _corridas_bd(esquema_pg) if c["source_provider"] == "overture"][-1]
    assert run["rows_closed"] == 0 and _invariante_m0(esquema_pg, foso) == run["rows_written"]
    assert _obs(tmp_path)["matriz"]["reobservadas_sin_open_explicito"] == 31


@pg
def test_PG_M0_el_estado_de_cada_fila_se_reconstruye_desde_su_corrida_y_el_release(foso, duckdb_spatial, esquema_pg,
                                                                                  monkeypatch, tmp_path):
    """RECONSTRUCCIÓN (sin columna nueva y sin tocar `source_lineage`): fila → `ingestion_run_id` → corrida
    (`source_release`, `source_endpoint`) → el registro INMUTABLE de ese release por GERS → `operating_status`. En
    TODA fila escrita por la corrida: su `operativo` es EXACTAMENTE el de la matriz para ese estado; y toda fila con
    `operativo=false` enlazada a una corrida de este lector viene de un cierre EXPLÍCITO de la fuente."""
    monkeypatch.setattr(foso, "SYNC_URL", esquema_pg["url"])
    monkeypatch.setattr(foso, "huella_esquema_overture", foso._huella_real)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    estables = _estables(10)
    uno = [_fila(f"m0-{k}", *PH) for k in ("perm", "temp", "null", "open", "abrir")]
    r1 = _parquet_r3(duckdb_spatial, tmp_path / "r1.parquet", BASE_R3 + estables + uno)
    monkeypatch.setattr(foso, "overture_glob", lambda rel: r1)
    assert _corre(foso) == 0
    _siembra(esquema_pg, [("m0-legado-cerrado", "farmacia", "pharmacy", False)])
    import psycopg
    with psycopg.connect(esquema_pg["conninfo"], autocommit=True) as c:      # m0-abrir: cerrada antes de la 2.ª corrida
        c.execute(f"SET search_path TO {esquema_pg['esquema']}, public")
        c.execute("UPDATE pois_propios SET operativo = false WHERE overture_id = 'm0-abrir'")
    dos = [_fila("m0-perm", *PH, conf=0.0, estado="permanently_closed"), _fila("m0-temp", *PH, estado="temporarily_closed"),
           _fila("m0-null", *PH), _fila("m0-open", *PH, estado="open"), _fila("m0-abrir", *PH, estado="open"),
           _fila("m0-legado-cerrado", *PH)]
    r2 = _parquet_r3(duckdb_spatial, tmp_path / "r2.parquet", BASE_R3 + estables + dos)
    monkeypatch.setattr(foso, "overture_glob", lambda rel: r2)
    assert _corre(foso) == 0
    run = [c for c in _corridas_bd(esquema_pg) if c["source_provider"] == "overture"][-1]
    [(endpoint,)] = _psql(esquema_pg, f"SELECT source_endpoint FROM poi_ingestion_run WHERE id = '{run['id']}'")
    assert endpoint == r2 and run["source_release"] == "2026-09-23.1"
    filas = _psql(esquema_pg, f"""SELECT overture_id, operativo FROM pois_propios
                                  WHERE ingestion_run_id = '{run['id']}' ORDER BY overture_id""")
    con = duckdb_spatial.connect()
    fuente = dict(con.execute(f"SELECT id, operating_status FROM read_parquet('{endpoint}')").fetchall())
    con.close()
    for oid, operativo in filas:                             # GERS + corrida → release → registro → estado
        clase = foso.clase_de_estado(fuente[oid])
        assert clase != "INVALID_STATUS" and operativo is (clase in foso.CLASES_PRESENCIA), (oid, clase, operativo)
        if operativo is False:
            assert clase in foso.CLASES_CERRADAS, f"{oid}: un false de este lector solo sale de un cierre explícito"
    reconstruido = {oid: foso.clase_de_estado(fuente[oid]) for oid, _ in filas if oid.startswith("m0-")}
    assert reconstruido == {"m0-perm": "PERMANENTLY_CLOSED", "m0-temp": "TEMPORARILY_CLOSED", "m0-null": "UNKNOWN_STATUS",
                            "m0-open": "OPEN", "m0-abrir": "OPEN"}
    assert run["rows_closed"] == 2, "m0-perm (confianza 0) y m0-temp: transiciones reales"
    p = _provenance(esquema_pg)
    assert p["m0-abrir"]["operativo"] is True, "OPEN explícito reabre"
    assert p["m0-legado-cerrado"]["operativo"] is False and p["m0-legado-cerrado"]["run"] is None, \
        "NULL sobre una cerrada legada: intacta, sin procedencia"
    assert _invariante_m0(esquema_pg, foso) == run["rows_written"]
