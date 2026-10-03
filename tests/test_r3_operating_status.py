"""R3 · OPERATING STATUS SEMANTICS + DURABILITY GUARD · la matriz de estado del lector `overture_places_taxonomy_v1`.

Contrato OFICIAL de Overture (`schema/places/place.yaml`, v2.0.0; el mismo enum desde v1.16.0): `operating_status ∈
{open, permanently_closed, temporarily_closed}`, opcional desde v1.17.0 y NULL por defecto desde la nota de 2026-05-20.
`closed` NO existe. Evidencia: RESULTADO_2026-10-02_R3_OPERATING_STATUS_SEMANTICS_PREFLIGHT.md.

DURABILITY GUARD (R3 v1): Overture conserva sus releases públicos ~60 días y el changelog no guarda el valor completo de
`operating_status`; la 043 no tiene dónde conservarlo. Hasta que exista persistencia durable del estado fuente (R5),
OBSERVAR ≠ AUTORIZAR: el estado se clasifica, se cuenta y se avisa, pero NO mueve `operativo`.

                              NUEVA                FILA ACTIVA              FILA CERRADA
    NULL + confianza OK       INSERT               UPDATE                   NO TOUCH + cuenta + aviso
    open + confianza OK       INSERT               UPDATE                   NO TOUCH + aviso (explicit_open_on_closed)
    temporarily_closed        NO INSERT + aviso    NO TOUCH + aviso         NO TOUCH + aviso
    permanently_closed        NO INSERT + aviso    NO TOUCH + aviso         NO TOUCH + aviso
    valor fuera del enum      Overture ROTA al obtener: 0 escrituras, 0 cambios de estado, corrida fallida

Lo ÚNICO que escribe: el alta de una fila NUEVA activa por presencia (OPEN/NULL) y la re-observación de una fila
ACTIVA que sigue activa. `_guarda_durabilidad` lo exige estructuralmente.
Capas: ORQUESTACIÓN (motor falso de #189) corre en el CI; POSTGIS (`TEST_POSTGIS_URL`) solo en local.
"""
from __future__ import annotations

import ast
import itertools
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
ESTADOS = (None, "open", "temporarily_closed", "permanently_closed")
PREVIOS = (None, (True, "farmacia"), (False, "farmacia"))


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
    assert foso.CLASES_EXPLICITAS == {"OPEN", "TEMPORARILY_CLOSED", "PERMANENTLY_CLOSED"}


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


# ════════════════════ DURABILITY GUARD · ningún estado mueve `operativo` (pura + CI) ═══════════════════
def test_DG_ningun_operating_status_cambia_operativo_en_r3_v1(foso):
    """Para TODA clase de estado × TODO estado previo: lo que se escribe es SOLO el alta de una fila NUEVA activa por
    presencia (OPEN/NULL) o la re-observación de una fila ACTIVA. Nunca una fila cerrada, nunca `operativo=false`."""
    for clase, previo in itertools.product(sorted(foso.CLASES_PRESENCIA | foso.CLASES_CERRADAS), PREVIOS):
        decision = foso._decision(clase, previo)
        if decision in foso._ESCRIBEN:
            assert clase in foso.CLASES_PRESENCIA, (clase, previo, decision)
            assert previo is None or previo[0] is True, f"{clase} sobre {previo}: escribiría una fila cerrada"
        else:
            assert decision in foso._AVISAN, (clase, previo, decision)
    assert foso._ESCRIBEN == {"insertadas", "actualizadas"}


@pytest.mark.parametrize("estado", ESTADOS)
@pytest.mark.parametrize("previo", PREVIOS, ids=["nueva", "activa", "cerrada"])
def test_DG_orquestacion_operativo_tras_la_corrida_es_el_de_antes_o_alta_activa(foso, duckdb_spatial, monkeypatch,
                                                                                tmp_path, estado, previo):
    capa = {"os-x": previo} if previo else {}
    motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path, [_fila("os-x", *PH, estado=estado)], capa)
    assert codigo == 0
    escritas = _escritas(motor)
    if "os-x" in escritas:
        assert escritas["os-x"]["operativo"] is True and (previo is None or previo[0] is True), (estado, previo)
    assert _corridas(motor)["overture"][1]["rows_closed"] == 0
    assert all(f["operativo"] is True for f in escritas.values())


@pytest.mark.parametrize("estado,previo", [("open", (False, "farmacia")), ("permanently_closed", (True, "farmacia")),
                                           ("temporarily_closed", None)], ids=["reapertura", "cierre", "alta_cerrada"])
def test_DG_la_guarda_estructural_detiene_una_transicion_aunque_la_matriz_falle(foso, duckdb_spatial, monkeypatch,
                                                                               tmp_path, estado, previo):
    """Si una matriz defectuosa decidiera escribir una fila CERRADA (reapertura), un cierre, o el alta de una fila
    cerrada, `_guarda_durabilidad` rompe Overture ANTES del upsert: 0 escrituras de Overture, corrida fallida, OSM sigue."""
    monkeypatch.setattr(foso, "_decision", lambda clase, previo: "actualizadas" if previo else "insertadas")
    motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path,
                              [_fila("os-x", *PH, estado=estado)], {"os-x": previo} if previo else {})
    assert codigo == 1 and motor.ejecutadas(UPSERT_OV) == []
    o = _corridas(motor)["overture"][1]
    assert (o["status"], o["error_phase"], o["error_class"]) == ("rota", "validacion", "TransicionSinEvidenciaDurable")
    assert [r for r, _, _ in motor.ejecutadas(UPSERT_OSM)] == ["commit"]


# ══════════════════════════════════ OS1–OS12 · la matriz temporal (CI) ═══════════════════════════════════
# (id, operating_status, confianza, estado previo en la capa, decisión, ¿se escribe?, ¿avisa?)
MATRIZ = [
    ("OS1_open_sobre_cerrada_no_reabre_y_avisa", "open", 0.9, (False, "farmacia"), "explicit_open_on_closed", False, True),
    ("OS1b_open_sobre_activa_actualiza", "open", 0.9, (True, "farmacia"), "actualizadas", True, False),
    ("OS1c_open_nueva_inserta_activa", "open", 0.9, None, "insertadas", True, False),
    ("OS2_null_sobre_cerrada_no_se_toca", None, 0.9, (False, "farmacia"), "reobservadas_sin_open_explicito", False, True),
    ("OS3_null_sobre_activa_sigue_activa", None, 0.9, (True, "farmacia"), "actualizadas", True, False),
    ("OS4_null_nueva_inserta_activa", None, 0.9, None, "insertadas", True, False),
    ("OS5_permanent_sobre_activa_no_cierra_y_avisa", "permanently_closed", 0.9, (True, "farmacia"),
     "permanent_closed_on_active", False, True),
    ("OS6_permanent_sobre_cerrada_no_toca_la_procedencia", "permanently_closed", 0.9, (False, "farmacia"),
     "explicit_close_on_closed", False, True),
    ("OS7_permanent_nueva_no_se_crea", "permanently_closed", 0.9, None, "explicit_close_new", False, True),
    ("OS8_permanent_con_confianza_0_se_observa", "permanently_closed", 0.0, (True, "farmacia"),
     "permanent_closed_on_active", False, True),
    ("OS9_permanent_bajo_el_umbral_se_observa", "permanently_closed", 0.40, (True, "farmacia"),
     "permanent_closed_on_active", False, True),
    ("OS9b_permanent_con_confianza_NULL_se_observa", "permanently_closed", None, (True, "farmacia"),
     "permanent_closed_on_active", False, True),
    ("OS10_temporary_sobre_activa_no_cierra_y_avisa", "temporarily_closed", 0.9, (True, "farmacia"),
     "temporary_closed_on_active", False, True),
    ("OS11_temporary_sobre_cerrada_no_toca_la_procedencia", "temporarily_closed", 0.9, (False, "farmacia"),
     "explicit_close_on_closed", False, True),
    ("OS12_temporary_nueva_no_se_crea", "temporarily_closed", 0.9, None, "explicit_close_new", False, True),
]


@pytest.mark.parametrize("caso,estado,conf,previo,decision,escrita,avisa", MATRIZ, ids=[m[0] for m in MATRIZ])
def test_OS1_OS12_cada_celda_de_la_matriz_temporal(foso, duckdb_spatial, monkeypatch, tmp_path, caso, estado, conf,
                                                   previo, decision, escrita, avisa):
    capa = {"os-x": previo} if previo else {}
    motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path,
                              [_fila("os-x", *PH, conf=conf, estado=estado)], capa)
    assert codigo == 0
    escritas = _escritas(motor)
    run = _corridas(motor)["overture"][1]
    if escrita:
        f = escritas["os-x"]
        assert (f["operativo"], f["ingestion_run_id"], f["categoria"], f["source_category"],
                f["source_category_namespace"], f["cat_leaf"]) == (True, run["id"], "farmacia", "pharmacy",
                                                                   "overture:taxonomy.primary", None)
        assert foso.categoria_de_la_regla(run["reader_contract"], f["source_category_namespace"],
                                          f["source_category"]) == f["categoria"], "M0: procedencia → regla → categoría"
    else:
        assert "os-x" not in escritas, f"{caso}: la fila NO se escribe (ni se crea, ni se reabre, ni se cierra, ni se re-enlaza)"
    assert run["rows_closed"] == 0 and run["rows_written"] == len(escritas)
    assert motor.ejecutadas(CIERRE_OV) == [], "Overture no tiene sentencia de cierre propia"
    # las 11 aceptadas de BASE_R3 no están en la capa: también son `insertadas`
    assert _obs(tmp_path)["matriz"][decision] == 1 + (len(ACEPTADAS_BASE) if decision == "insertadas" else 0)
    if avisa:
        [(asunto, detalle)] = foso.avisos
        assert "AVISO DE TAXONOMÍA Y ESTADO" in asunto and f"[{decision}]. GERS: os-x" in detalle
    else:
        assert foso.avisos == []


def test_OS9_el_umbral_de_contexto_decide_la_presencia_y_el_cierre_igual_se_observa(foso, duckdb_spatial, monkeypatch,
                                                                                    tmp_path):
    """Parque (CONF_MIN 0,70) a 0,60: `open` así NO se acepta como presencia (bajo la confianza: es un explícito no
    representable); `permanently_closed` así SÍ se observa como cierre (la confianza no filtra estados), sin mutar."""
    extra = [_fila("os-open-bajo", *PK, conf=0.60, estado="open"),
             _fila("os-cierre-bajo", *PK, conf=0.60, estado="permanently_closed")]
    capa = {"os-open-bajo": (False, "parque"), "os-cierre-bajo": (True, "parque")}
    motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path, extra, capa)
    assert codigo == 0
    escritas = _escritas(motor)
    assert not ({"os-open-bajo", "os-cierre-bajo"} & set(escritas))
    o = _obs(tmp_path)
    assert o["bajo_confianza"] == {"salud": 1, "parque": 2} and o["cierres_explicitos_observados"] == {"PERMANENTLY_CLOSED": 1}
    assert o["explicitos_no_representables"] == {"bajo_confianza": 1}
    assert o["explicitos_no_representables_con_transicion"] == ["os-open-bajo"], "un open sobre una cerrada: se avisa"
    assert o["matriz"]["permanent_closed_on_active"] == 1


def test_una_secuencia_de_estados_no_mueve_operativo(foso, duckdb_spatial, monkeypatch, tmp_path):
    """temporarily_closed → NULL → open → permanently_closed sobre la MISMA fila activa, y open sobre una cerrada: el
    estado canónico no se mueve en ninguna corrida (cada una se cuenta en su celda)."""
    for i, (estado, previo, decision) in enumerate((("temporarily_closed", (True, "farmacia"), "temporary_closed_on_active"),
                                                    (None, (True, "farmacia"), "actualizadas"),
                                                    ("open", (True, "farmacia"), "actualizadas"),
                                                    ("permanently_closed", (True, "farmacia"), "permanent_closed_on_active"),
                                                    ("open", (False, "farmacia"), "explicit_open_on_closed"))):
        motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path / str(i),
                                  [_fila("os-t", *PH, estado=estado)], {"os-t": previo})
        escritas = _escritas(motor)
        assert codigo == 0 and _obs(tmp_path)["matriz"][decision] == 1, (estado, decision)
        assert ("os-t" not in escritas) or (escritas["os-t"]["operativo"] is True and previo[0] is True)


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


# ═══════════════════ OS14–OS15 · estado explícito que la regla no acepta (CI) ════════════════════
@pytest.mark.parametrize("caso,fila,motivo", [
    ("OS14_taxonomia_sin_regla", _fila("os-x", "dental_clinic", "health_care > outpatient_care_facility > dental_clinic",
                                       estado="permanently_closed"), "descendiente"),
    ("OS14b_fuera_del_mapa", _fila("os-x", "restaurant", "food_and_drink > restaurant", estado="permanently_closed"),
     "fuera_del_mapa"),
    ("OS14c_taxonomia_NULL", _fila("os-x", None, None, estado="temporarily_closed"), "sin_taxonomia"),
    ("OS14d_nodo_padre", _fila("os-x", "health_care", "health_care", estado="permanently_closed"), "nodo_padre"),
    ("OS15_jerarquia_invalida", _fila("os-x", "hospital", "health_care > clinic", estado="permanently_closed"),
     "jerarquia_invalida")])
def test_OS14_OS15_estado_no_representable_cuenta_avisa_y_no_muta(foso, duckdb_spatial, monkeypatch, tmp_path, caso,
                                                                  fila, motivo):
    motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path, [fila], {"os-x": (True, "salud")})
    assert codigo == 0
    assert "os-x" not in _escritas(motor) and motor.ejecutadas(CIERRE_OV) == []
    o = _obs(tmp_path)
    assert o["explicitos_no_representables"] == {motivo: 1} and o["explicitos_no_representables_con_transicion"] == ["os-x"]
    assert o["matriz"]["explicit_status_not_representable"] == 1
    assert _corridas(motor)["overture"][1]["rows_closed"] == 0
    [(_, detalle)] = foso.avisos
    assert "[explicit_status_not_representable]. GERS: os-x" in detalle


def test_OS15b_estado_con_ruta_distinta_en_hoja_aceptada_es_deriva_y_nada_se_muta(foso, duckdb_spatial, monkeypatch,
                                                                                  tmp_path):
    """La política source-invalid YA PROBADA: una hoja aceptada con otra jerarquía es DERIVA, con cualquier estado."""
    motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path,
                              [_fila("os-x", "hospital", "health_care > medical_facility > hospital",
                                     estado="permanently_closed")], {"os-x": (True, "salud")})
    assert codigo == 1
    for fragmento in ("cobertura_previa", LECTURA_PREVIA, UPSERT_OV):
        assert motor.ejecutadas(fragmento) == [], fragmento
    assert _corridas(motor)["overture"][1]["error_class"] == "DerivaTaxonomia"


# ═══════════════════ cobertura: un estado no es desaparición de la taxonomía (CI) ══════════════════
def test_la_cobertura_cuenta_los_cierres_explicitos_y_no_los_confunde_con_deriva(foso, duckdb_spatial, monkeypatch,
                                                                                 tmp_path):
    cerradas = [_fila(f"os-c{i}", *PH, estado="permanently_closed") for i in range(11)]
    capa = {f"os-c{i}": (True, "farmacia") for i in range(11)}
    motor, codigo = _corre_os(foso, duckdb_spatial, monkeypatch, tmp_path, cerradas, capa, cobertura={"farmacia": 12})
    assert codigo == 0, "12 observaciones de farmacia (1 presencia + 11 cierres) ≥ 12·90 %: no es deriva"
    assert _corridas(motor)["overture"][1]["rows_closed"] == 0 and not (set(capa) & set(_escritas(motor)))
    assert _obs(tmp_path)["cobertura"]["farmacia"] == [12, 12]
    # contraste: si esas 11 DESAPARECEN del release (no un estado), la guarda sí dispara
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
def test_PG_DG_ningun_estado_explicito_mueve_una_fila_y_lo_escrito_se_reconstruye(foso, duckdb_spatial, esquema_pg,
                                                                                 monkeypatch, tmp_path):
    """DURABILITY GUARD en la base REAL (043): tras una 1.ª corrida, la 2.ª trae permanently_closed (confianza 0) y
    temporarily_closed sobre filas ACTIVAS, open sobre una CERRADA y NULL sobre una cerrada legada → las cuatro, BYTE A
    BYTE iguales (estado y procedencia histórica); `rows_closed` 0. M0: la categoría de toda fila escrita se reconstruye
    desde su corrida (043, durable) y el estado OBSERVADO de cada fila escrita es de presencia (OPEN/NULL), leído del
    registro del release que declara la corrida (`source_endpoint`)."""
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
    antes = _filas_json(esquema_pg)
    dos = [_fila("m0-perm", *PH, conf=0.0, estado="permanently_closed"), _fila("m0-temp", *PH, estado="temporarily_closed"),
           _fila("m0-null", *PH), _fila("m0-open", *PH, estado="open"), _fila("m0-abrir", *PH, estado="open"),
           _fila("m0-legado-cerrado", *PH)]
    r2 = _parquet_r3(duckdb_spatial, tmp_path / "r2.parquet", BASE_R3 + estables + dos)
    monkeypatch.setattr(foso, "overture_glob", lambda rel: r2)
    assert _corre(foso) == 0
    d = _filas_json(esquema_pg)
    for oid in ("m0-perm", "m0-temp", "m0-abrir", "m0-legado-cerrado"):
        assert d[oid] == antes[oid], f"{oid}: el estado observado NO mueve la fila (ni su procedencia histórica)"
    run = [c for c in _corridas_bd(esquema_pg) if c["source_provider"] == "overture"][-1]
    assert run["rows_closed"] == 0
    [(endpoint,)] = _psql(esquema_pg, f"SELECT source_endpoint FROM poi_ingestion_run WHERE id = '{run['id']}'")
    assert endpoint == r2 and run["source_release"] == "2026-09-23.1"
    filas = _psql(esquema_pg, f"""SELECT overture_id, operativo FROM pois_propios
                                  WHERE ingestion_run_id = '{run['id']}' ORDER BY overture_id""")
    con = duckdb_spatial.connect()
    fuente = dict(con.execute(f"SELECT id, operating_status FROM read_parquet('{endpoint}')").fetchall())
    con.close()
    for oid, operativo in filas:                             # GERS + corrida → release → registro → estado observado
        assert operativo is True and foso.clase_de_estado(fuente[oid]) in foso.CLASES_PRESENCIA, (oid, fuente[oid])
    escritas = {oid for oid, _ in filas}
    assert {"m0-null", "m0-open"} <= escritas and not ({"m0-perm", "m0-temp", "m0-abrir", "m0-legado-cerrado"} & escritas)
    # M0 (043, durable): procedencia → regla → categoría en TODA fila con procedencia: las escritas por la 2.ª corrida Y
    # las que la guarda dejó con la procedencia histórica de la 1.ª (m0-perm, m0-temp, m0-abrir)
    run1 = [c for c in _corridas_bd(esquema_pg) if c["source_provider"] == "overture"][-2]
    historicas = _psql(esquema_pg, f"SELECT overture_id FROM pois_propios WHERE ingestion_run_id = '{run1['id']}'")
    assert {h for h, in historicas} >= {"m0-perm", "m0-temp", "m0-abrir"}
    assert _invariante_m0(esquema_pg, foso) == run["rows_written"] + len(historicas)
    m = _obs(tmp_path)["matriz"]
    assert (m["permanent_closed_on_active"], m["temporary_closed_on_active"], m["explicit_open_on_closed"],
            m["reobservadas_sin_open_explicito"]) == (1, 1, 1, 1)
