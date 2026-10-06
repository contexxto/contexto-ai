"""R3 · OVERTURE TAXONOMY V1 · el lector `overture_places_taxonomy_v1` y la frontera de cierre de Overture.

Overture v2.0.0 (2026-09-23.x) eliminó `categories`; el lector de `categories.primary` quedó roto (D-4). R3 añade
OTRO lector, versionado: `taxonomy.primary` + la RUTA EXACTA aceptada → categoría de Contexto. Nunca subárbol, nunca
nodo padre, nunca `basic_category`. Y separa lo que el lector viejo mezclaba (D-R3-2): lo que Contexto NO ingiere
(fuera del mapa, bajo su umbral de confianza, taxonomía desconocida o ausente del resultado) ya NO se cierra.
M0 FINAL + OPERATING STATUS + DURABILITY GUARD: un estado EXPLÍCITO de la fuente (`open`, `permanently_closed`,
`temporarily_closed`: el contrato oficial; `closed` NO existe) se OBSERVA, se cuenta y se avisa, pero en R3 v1 NO
autoriza ninguna transición de `operativo` (Contexto aún no conserva durablemente esa observación: R5). La fila no se
toca y la procedencia vigente de toda fila sigue explicando su categoría vigente. La matriz completa vive en
`tests/test_r3_operating_status.py`.

Matriz (RESULTADO_2026-10-02_R3_OVERTURE_TAXONOMY_V1_CODE_DATA_PREFLIGHT.md §16 + el mandato CODE+CI):
  F1 esquema v2 real · F2 deriva de esquema · F3 mapeos seguros · F4 reparentado · F5 renombre · F6 cambio semántico
  F7 categoría desconocida / descendiente nuevo · F8 ambiguo / jerarquía inválida · F9 procedencia reconstruible
  F10 regresión R4 (aislamiento) · F11 honestidad histórica · F12 versión del mapa · F13 caída de cobertura
  F14 v0 congelado · F15 regresión con el dato REAL de Quito (local, con el fixture congelado)
  F16 mutación: arnés aparte (evidencia), no es una prueba de esta suite
  C1–C7 la frontera de cierre.
Capas: PURA y ORQUESTACIÓN (motor falso de #189) corren en el CI; POSTGIS (`TEST_POSTGIS_URL`) solo en local.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess

import pytest

from tests.test_poi_refresh_source_isolation import (  # noqa: F401 — fixtures y ayudantes de #189 / R4
    BASE_R3, FUERA_BBOX, HUELLA_PRUEBA, RAIZ, SHA_PRUEBA, VIEJO, _corre, _estado, _foto, _fuentes, _motor, _osm, _ov,
    _parquet_r3, _sin_corrida, duckdb_spatial, esquema_pg, foso, pg)
from tests.test_poi_source_provenance_writer import CORRIDA, _corridas, _corridas_bd, _provenance, _psql

UPSERT_OV, UPSERT_OSM = "ON CONFLICT (overture_id)", "ON CONFLICT (osm_id)"
CIERRE_OV = "AND operativo AND fuente = 'overture'"
CIERRE_OSM = "AND operativo AND fuente = 'osm'"
ACEPTADAS_BASE = {"ov-h1": "salud", "ov-ocf": "salud", "ov-ph": "farmacia", "ov-gr": "supermercado",
                  "ov-sc": "educacion", "ov-cu": "educacion", "ov-pre": "educacion", "ov-pk": "parque",
                  "ov-pg": "parque", "ov-sm": "centro_comercial", "ov-ds": "centro_comercial"}
# La versión de la regla, FIJADA aquí y no solo en el código: cambiar la tabla o una ruta sin publicar un lector
# nuevo hace fallar F12 (D-R3-5).
VERSIONES_PUBLICADAS = {"overture_places_taxonomy_v1": "8be8274fddeb14db474614767a60a3032ae22da0753b49ef1cc261c1502fec7a"}


def _fila(oid, primary, ruta, conf=0.9, lon=-78.45, lat=-0.2, estado=None, ver=1, nombre=None):
    return (oid, nombre or f"Lugar {oid}", primary, ruta, conf, lon, lat, estado, ver)


def _con(base, *extra, quitar=()):
    return [f for f in base if f[0] not in set(quitar)] + list(extra)


def _lee(foso, duckdb_spatial, monkeypatch, tmp_path, filas=BASE_R3, nombre="r.parquet", **kw):
    ruta = _parquet_r3(duckdb_spatial, tmp_path / nombre, filas, **kw)
    monkeypatch.setattr(foso, "overture_glob", lambda rel: ruta)
    return foso.pull_overture_taxonomia(), foso.ULTIMA_OVERTURE


def _con_lector_real(foso, duckdb_spatial, monkeypatch, tmp_path, filas=BASE_R3, nombre="r.parquet", **kw):
    ruta = _parquet_r3(duckdb_spatial, tmp_path / nombre, filas, **kw)
    monkeypatch.setattr(foso, "overture_glob", lambda rel: ruta)
    return ruta


# ══════════════════════════════════════════ PURA ══════════════════════════════════════════════════
def test_F1_el_lector_nuevo_lee_el_esquema_v2_y_el_viejo_sigue_roto(foso, duckdb_spatial, monkeypatch, tmp_path):
    filas, obs = _lee(foso, duckdb_spatial, monkeypatch, tmp_path)
    assert {f["overture_id"]: f["categoria"] for f in filas} == ACEPTADAS_BASE
    assert obs["deriva"] == [] and obs["alertas"] == []
    with pytest.raises(duckdb_spatial.BinderException, match='"categories" not found'):
        foso.pull_overture()                       # `overture_places_categories_v1` intacto: sigue sin `categories`


@pytest.mark.parametrize("variante,esperado", [("sin_taxonomy", "taxonomy=AUSENTE"),
                                               ("con_campo_nuevo", "taxonomy=STRUCT")])
def test_F2_esquema_inesperado_falla_cerrado_al_obtener(foso, duckdb_spatial, monkeypatch, tmp_path, variante, esperado):
    kw = {"sin_taxonomy": True} if variante == "sin_taxonomy" else {"taxonomy_tipo": "con_campo_nuevo"}
    with pytest.raises(foso.GuardaTaxonomia) as exc:
        _lee(foso, duckdb_spatial, monkeypatch, tmp_path, **kw)
    assert exc.value.clase == "EsquemaInesperado" and esperado in str(exc.value)


def test_F3_los_mapeos_seguros_conservan_la_fuente_tal_cual(foso, duckdb_spatial, monkeypatch, tmp_path):
    filas, _ = _lee(foso, duckdb_spatial, monkeypatch, tmp_path)
    fuente = {f[0]: f for f in BASE_R3}
    for f in filas:
        primary = fuente[f["overture_id"]][2]
        assert (f["source_category"], f["source_category_namespace"]) == (primary, "overture:taxonomy.primary")
        assert f["cat_leaf"] is None, "I4: con taxonomy.primary, categoria_overture va NULL"
        assert f["categoria"] == foso.TAXONOMIA_V1[primary][1] and f["source_category"] != f["categoria"]
        assert f["source_updated_at"] is None and f["source_record_version"] == str(fuente[f["overture_id"]][8])
        linaje = json.loads(f["source_lineage"])
        assert linaje[0]["record_id"] == f"rec-{f['overture_id']}" and linaje[0]["license"] == "CDLA-Permissive-2.0"
    assert foso._invalidas("overture", filas, foso.LECTOR_OVERTURE_TAXONOMIA) == []


def test_F4_reparentado_de_una_hoja_aceptada_es_deriva(foso, duckdb_spatial, monkeypatch, tmp_path):
    filas_r = _con(BASE_R3, _fila("ov-rep", "hospital", "health_care > medical_facility > hospital"))
    _, obs = _lee(foso, duckdb_spatial, monkeypatch, tmp_path, filas_r)
    assert obs["deriva"] == ["hospital: ruta health_care > medical_facility > hospital ≠ aceptada health_care > hospital"]
    # PATCH M0: la confianza NO oculta la deriva (es regla de aceptación de Contexto, no verdad de la fuente)
    for conf, nombre in ((0.40, "r2.parquet"), (None, "r3.parquet")):
        filas_r = _con(BASE_R3, _fila("ov-rep", "hospital", "health_care > medical_facility > hospital", conf=conf))
        filas, obs = _lee(foso, duckdb_spatial, monkeypatch, tmp_path, filas_r, nombre=nombre)
        assert obs["deriva"] == ["hospital: ruta health_care > medical_facility > hospital ≠ aceptada health_care > hospital"]
        assert "ov-rep" not in {f["overture_id"] for f in filas}
        assert obs["observacion"]["ruta_distinta"] == {"hospital @ health_care > medical_facility > hospital": 1}


@pytest.mark.parametrize("conf", [0.40, None])
def test_F4_deriva_con_confianza_bajo_el_piso_rompe_overture_sin_escribir_ni_cerrar(foso, duckdb_spatial, monkeypatch,
                                                                                    tmp_path, conf):
    """PATCH M0 · 1: hoja mapeada + ruta distinta + confianza < CONF_FLOOR (o NULL) → Overture ROTA (DerivaTaxonomia),
    0 escrituras y 0 cierres, aunque el release traiga además un cierre explícito. OSM sigue."""
    filas = _con(BASE_R3, _fila("ov-rep", "hospital", "health_care > medical_facility > hospital", conf=conf),
                 _fila("ov-cerrado", "pharmacy", "shopping > specialty_store > pharmacy_and_drug_store > pharmacy",
                       estado="permanently_closed"))
    _con_lector_real(foso, duckdb_spatial, monkeypatch, tmp_path, filas)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso, previos={"osm": 1}, cierres={"overture": 5})
    assert _corre(foso) == 1
    for fragmento in ("cobertura_previa", "AS operativo_en_capa", UPSERT_OV, CIERRE_OV):
        assert motor.ejecutadas(fragmento) == [], fragmento
    o = _corridas(motor)["overture"][1]
    assert (o["status"], o["error_phase"], o["error_class"], o["rows_written"], o["rows_closed"]) == (
        "rota", "validacion", "DerivaTaxonomia", None, None)
    assert [r for r, _, _ in motor.ejecutadas(UPSERT_OSM)] == ["commit"]


def test_F5_renombre_entra_por_su_hoja_nueva_y_la_vieja_no(foso, duckdb_spatial, monkeypatch, tmp_path):
    filas_r = _con(BASE_R3, _fila("ov-sc-viejo", "shopping_center", "shopping > shopping_center"))
    filas, obs = _lee(foso, duckdb_spatial, monkeypatch, tmp_path, filas_r)
    por_id = {f["overture_id"]: f for f in filas}
    assert por_id["ov-sm"]["categoria"] == "centro_comercial" and por_id["ov-sm"]["source_category"] == "shopping_mall"
    assert "ov-sc-viejo" not in por_id and obs["observacion"]["fuera_del_mapa"] == 2      # + el restaurante


def test_F6_cambio_semantico_solo_la_hoja_exacta_de_ocf_y_nada_retirado(foso, duckdb_spatial, monkeypatch, tmp_path):
    filas_r = _con(BASE_R3,
                   _fila("ov-lab", "laboratory_testing",
                         "health_care > outpatient_care_facility > diagnostics_imaging_or_lab_service > laboratory_testing"),
                   _fila("ov-mc", "medical_center", "health_care > medical_center"),
                   _fila("ov-doc", "doctor", "health_care > doctor"))
    filas, obs = _lee(foso, duckdb_spatial, monkeypatch, tmp_path, filas_r)
    por_id = {f["overture_id"]: f for f in filas}
    assert por_id["ov-ocf"]["categoria"] == "salud"                       # D-R3-1: la hoja exacta
    assert not ({"ov-dent", "ov-lab", "ov-mc", "ov-doc"} & set(por_id)), "sus descendientes y lo retirado, NO"
    assert obs["observacion"]["descendientes_conocidos"] == 2 and obs["alertas"] == []


def test_F7_desconocida_no_entra_y_el_descendiente_nuevo_se_avisa(foso, duckdb_spatial, monkeypatch, tmp_path):
    filas_r = _con(BASE_R3,
                   _fila("ov-poly", "polyclinic", "health_care > outpatient_care_facility > polyclinic"),
                   _fila("ov-poly2", "polyclinic", "health_care > outpatient_care_facility > polyclinic"),
                   _fila("ov-zzz", "zzz_nueva", "zzz_nueva"))
    filas, obs = _lee(foso, duckdb_spatial, monkeypatch, tmp_path, filas_r)
    assert not ({"ov-poly", "ov-poly2", "ov-zzz"} & {f["overture_id"] for f in filas})
    assert obs["observacion"]["descendientes_nuevos"] == {"polyclinic": 2}
    assert obs["alertas"] == ["descendiente NUEVO no ingerido: polyclinic (2 registros)"]
    assert obs["deriva"] == [], "un descendiente nuevo NO invalida la fuente: no entra y se avisa"


def test_F8_ambiguo_e_invalido_no_entran(foso, duckdb_spatial, monkeypatch, tmp_path):
    filas_r = _con(BASE_R3,
                   _fila("ov-edu", "education", "education"),
                   _fila("ov-mal", "hospital", "health_care > clinic"),               # hierarchy[-1] ≠ primary
                   _fila("ov-sinruta", "hospital", None),                             # sin hierarchy
                   _fila("ov-otrol0", "health_care", "financial_service"))            # medido en el dato real
    filas, obs = _lee(foso, duckdb_spatial, monkeypatch, tmp_path, filas_r)
    assert not ({"ov-edu", "ov-mal", "ov-sinruta", "ov-otrol0", "ov-hc"} & {f["overture_id"] for f in filas})
    o = obs["observacion"]
    assert o["nodo_padre"] == {"health_care": 1, "education": 1} and o["jerarquia_invalida"] == 3
    assert o["sin_taxonomia"] == 1 and obs["deriva"] == []


def test_la_observacion_cuenta_cada_clase_y_cuadra_con_el_bbox(foso, duckdb_spatial, monkeypatch, tmp_path):
    _, obs = _lee(foso, duckdb_spatial, monkeypatch, tmp_path)
    o = obs["observacion"]
    assert o["aceptadas"] == {"salud": 2, "farmacia": 1, "supermercado": 1, "educacion": 3, "parque": 2,
                              "centro_comercial": 2}
    assert o["bajo_confianza"] == {"salud": 1, "parque": 1}
    assert (o["descendientes_conocidos"], o["nodo_padre"], o["fuera_del_mapa"], o["sin_taxonomia"]) == (
        1, {"health_care": 1}, 1, 1)
    clases = (sum(o["aceptadas"].values()) + sum(o["bajo_confianza"].values()) + o["descendientes_conocidos"]
              + sum(o["nodo_padre"].values()) + o["fuera_del_mapa"] + o["sin_taxonomia"] + o["jerarquia_invalida"]
              + sum(o["descendientes_nuevos"].values()) + sum(o["ruta_distinta"].values()))
    assert clases == o["registros_bbox"] == len(BASE_R3) - 2, "cada registro del bbox, en UNA clase (2 fuera del bbox)"


def test_hoja_aceptada_desaparecida_del_release_es_deriva(foso, duckdb_spatial, monkeypatch, tmp_path):
    """Fuera de Quito puede faltar una hoja (no hay `drugstore`); en TODO el release, no: renombre o retirada."""
    _, obs = _lee(foso, duckdb_spatial, monkeypatch, tmp_path, _con(BASE_R3, quitar=("far-dr",)))
    assert obs["deriva"] == ["drugstore: la hoja aceptada no existe en el release 2026-09-23.1"]
    _, obs = _lee(foso, duckdb_spatial, monkeypatch, tmp_path, BASE_R3, nombre="ok.parquet")
    assert obs["deriva"] == [], "far-dr fuera del bbox basta: existe en el release"


def test_F12_la_regla_tiene_version_y_cambiarla_sin_version_nueva_falla(foso, duckdb_spatial, monkeypatch, tmp_path):
    for lector, mapa in foso.MAPAS_POR_LECTOR.items():
        assert foso.huella_mapa_taxonomia(mapa) == VERSIONES_PUBLICADAS[lector] == foso.HUELLA_TAXONOMIA_V1
    canon = "\n".join(f"{h}\t{' > '.join(r)}\t{c}" for h, (r, c) in sorted(foso.TAXONOMIA_V1.items()))
    assert foso.HUELLA_TAXONOMIA_V1 == hashlib.sha256(canon.encode("utf-8")).hexdigest()
    # una ruta aceptada cambiada «en caliente» (sin lector nuevo) → el lector no corre
    monkeypatch.setitem(foso.TAXONOMIA_V1, "hospital", (("health_care", "medical_facility", "hospital"), "salud"))
    with pytest.raises(foso.GuardaTaxonomia) as exc:
        _lee(foso, duckdb_spatial, monkeypatch, tmp_path)
    assert exc.value.clase == "MapaSinVersion"


def test_F12_la_tabla_es_una_funcion_sin_subarbol_ni_padres(foso):
    for hoja, (ruta, cat) in foso.TAXONOMIA_V1.items():
        assert ruta[-1] == hoja and cat in foso.CONF_MIN, (hoja, ruta, cat)
        assert not any(len(r) > len(ruta) and r[:len(ruta)] == ruta and h != hoja and foso.TAXONOMIA_V1[h][1] != cat
                       for h, (r, _) in foso.TAXONOMIA_V1.items()), "una hoja aceptada bajo otra, de OTRA categoría"
    assert not (foso.ANCESTROS_V1 & set(foso.TAXONOMIA_V1)) and not (foso.DESCENDIENTES_CONOCIDOS_V1 & set(foso.TAXONOMIA_V1))
    assert foso.TAXONOMIA_V1["outpatient_care_facility"] == (("health_care", "outpatient_care_facility"), "salud")
    for d in ("dental_clinic", "laboratory_testing", "physical_therapy", "counseling"):     # D-R3-1: NO heredan salud
        assert d not in foso.TAXONOMIA_V1 and d in foso.DESCENDIENTES_CONOCIDOS_V1
    assert "categories.primary" not in str(foso.TAXONOMIA_V1) and "basic_category" not in str(foso.TAXONOMIA_V1)


def test_F14_v0_congelado_y_honesto_con_las_filas_r3(foso):
    from app.contracts.place_evidence_v0 import SourceCategoryNamespace
    from app.place import clasificacion
    assert clasificacion.OVERTURE_V0 == foso.LEAF_TO_CAT, "LEAF_TO_CAT / OVERTURE_V0 intactos"
    assert "overture:taxonomy.primary" not in {n.value for n in SourceCategoryNamespace}
    # una fila R3 llega a v0 con `categoria_overture` NULL → la categoría de la fuente es DESCONOCIDA (D-R3-3)
    c = clasificacion.clasificar_servicio({"categoria_capa_origen": None, "cat": "salud", "dataset": "overture"})
    assert c.objeto is not None and (c.objeto.source_category, c.objeto.source_category_namespace) == (None, None)


def test_categoria_de_la_regla_reconstruye_sin_inventar(foso):
    t, c = foso.LECTOR_OVERTURE_TAXONOMIA, foso.LECTOR_OVERTURE
    assert foso.categoria_de_la_regla(t, "overture:taxonomy.primary", "outpatient_care_facility") == "salud"
    assert foso.categoria_de_la_regla(t, "overture:taxonomy.primary", "dental_clinic") is None
    assert foso.categoria_de_la_regla(c, "overture:categories.primary", "medical_center") == "salud"
    assert foso.categoria_de_la_regla(t, "overture:categories.primary", "hospital") is None, "espacio cruzado: nada"
    assert foso.categoria_de_la_regla(None, None, None) is None, "lo histórico sin corrida no se reconstruye"


def test_el_lector_viejo_no_cambio_ni_una_linea(foso):
    """`overture_places_categories_v1` (`pull_overture`) idéntico al de 5436561 (el baseline de R3)."""
    import ast
    p = subprocess.run(["git", "show", "543656178223378e5e0e0ca1e8bbe731a761f02e:scripts/foso_pois_spike.py"],
                       cwd=RAIZ, capture_output=True)
    if p.returncode != 0:
        pytest.skip("sin historia git (clon superficial)")

    def funcion(texto, nombre):
        return next(ast.unparse(n) for n in ast.walk(ast.parse(texto)) if isinstance(n, ast.FunctionDef) and n.name == nombre)
    actual = (RAIZ / "scripts" / "foso_pois_spike.py").read_text(encoding="utf-8")
    base = p.stdout.decode("utf-8")
    # `pull_osm_transporte` salió de esta lista con la OSM SNAPSHOT FRESHNESS GUARD (D-OSM-1), que la cambia A
    # PROPÓSITO: su consulta y su mapeo siguen fijados contra `main` en tests/test_osm_snapshot_freshness_guard.py.
    for nombre in ("pull_overture", "huella_esquema_overture", "overture_release"):
        assert funcion(actual, nombre) == funcion(base, nombre), nombre
    for constante in ('LECTOR_OVERTURE = "overture_places_categories_v1"', 'NS_OVERTURE = "overture:categories.primary"',
                      'LECTOR_OSM = "osm_overpass_nwr_body_center_v1"'):
        assert constante in actual and constante in base


def test_ninguna_migracion_nueva_y_el_workflow_intacto():
    """D-R3-4: sin 044. Y la frontera de cierre se resolvió sin tocar `refresco-pois.yml`."""
    assert sorted(p.name for p in (RAIZ / "migrations").glob("[0-9][0-9][0-9]_*.sql"))[-1] == "043_poi_source_provenance.sql"
    p = subprocess.run(["git", "diff", "--name-only", "543656178223378e5e0e0ca1e8bbe731a761f02e", "--",
                        "migrations", ".github", "app"], cwd=RAIZ, capture_output=True, text=True)
    if p.returncode != 0:
        pytest.skip("sin historia git")
    assert p.stdout.strip() == "", p.stdout


# ══════════════════════════════════════ ORQUESTACIÓN (CI) ═════════════════════════════════════════
def test_F2_orquestacion_esquema_desconocido_rota_sin_escribir_ni_cerrar_y_osm_sigue(foso, duckdb_spatial,
                                                                                    monkeypatch, tmp_path):
    _con_lector_real(foso, duckdb_spatial, monkeypatch, tmp_path, sin_taxonomy=True)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso, previos={"osm": 1})
    assert _corre(foso) == 1
    assert motor.ejecutadas(UPSERT_OV) == [] and motor.ejecutadas(CIERRE_OV) == []
    o = _corridas(motor)["overture"][1]
    assert (o["status"], o["error_phase"], o["error_class"], o["reader_contract"]) == (
        "rota", "obtencion", "EsquemaInesperado", "overture_places_taxonomy_v1")
    assert [r for r, _, _ in motor.ejecutadas(UPSERT_OSM)] == ["commit"]


@pytest.mark.parametrize("caso", ["reparentado", "hoja_desaparecida"])
def test_F4_F10_deriva_invalida_overture_antes_de_la_base_y_osm_escribe(foso, duckdb_spatial, monkeypatch, tmp_path, caso):
    filas = (_con(BASE_R3, _fila("ov-rep", "hospital", "health_care > medical_facility > hospital"))
             if caso == "reparentado" else _con(BASE_R3, quitar=("far-ucc",)))
    _con_lector_real(foso, duckdb_spatial, monkeypatch, tmp_path, filas)
    osm = [_osm(foso, "node/1"), _osm(foso, "node/2")]
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: osm)
    motor = _motor(monkeypatch, foso, previos={"osm": 2}, cobertura={"salud": 1})
    assert _corre(foso) == 1
    for fragmento in ("cobertura_previa", UPSERT_OV, CIERRE_OV):
        assert motor.ejecutadas(fragmento) == [], f"ni cobertura, ni upsert, ni cierre de Overture: {fragmento}"
    o = _corridas(motor)["overture"][1]
    assert (o["status"], o["error_phase"], o["error_class"], o["rows_written"]) == ("rota", "validacion",
                                                                                    "DerivaTaxonomia", None)
    [(res, _, filas_osm)] = motor.ejecutadas(UPSERT_OSM)
    assert res == "commit" and _sin_corrida(filas_osm) == osm
    assert len(motor.ejecutadas(CIERRE_OSM)) == 1, "OSM sigue con su semántica (C7)"
    f = _fuentes(_estado(tmp_path))
    assert "deriva de taxonomía" in f["overture"]["error"] and f["osm"]["estado"] == "ok"


def test_F7_orquestacion_descendiente_nuevo_corrida_ok_y_aviso(foso, duckdb_spatial, monkeypatch, tmp_path, capsys):
    _con_lector_real(foso, duckdb_spatial, monkeypatch, tmp_path,
                     _con(BASE_R3, _fila("ov-poly", "polyclinic", "health_care > outpatient_care_facility > polyclinic")))
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso, previos={"osm": 1})
    assert _corre(foso) == 0
    [(_, _, filas)] = motor.ejecutadas(UPSERT_OV)
    assert "ov-poly" not in {f["overture_id"] for f in filas}
    [(asunto, detalle)] = foso.avisos
    assert "AVISO DE TAXONOMÍA" in asunto and "polyclinic (1 registros)" in detalle
    e = _fuentes(_estado(tmp_path))["overture"]
    assert e["alertas"] == ["descendiente NUEVO no ingerido: polyclinic (1 registros)"]
    assert e["observacion"]["descendientes_nuevos"] == {"polyclinic": 1}, "resultado estructurado (sin migración)"
    assert "observación overture (overture_places_taxonomy_v1)" in capsys.readouterr().out


def test_F9_orquestacion_la_categoria_se_reconstruye_desde_la_corrida(foso, duckdb_spatial, monkeypatch, tmp_path):
    _con_lector_real(foso, duckdb_spatial, monkeypatch, tmp_path)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso, previos={"osm": 1})
    assert _corre(foso) == 0
    run = _corridas(motor)["overture"][1]
    [(_, _, filas)] = motor.ejecutadas(UPSERT_OV)
    assert {f["ingestion_run_id"] for f in filas} == {run["id"]}
    for f in filas:   # fila → corrida → (reader_contract, code_sha, release) → regla → categoría
        assert foso.categoria_de_la_regla(run["reader_contract"], f["source_category_namespace"],
                                          f["source_category"]) == f["categoria"]
        assert foso.MAPAS_POR_LECTOR[run["reader_contract"]][f["source_category"]][0][-1] == f["source_category"]
    assert (run["reader_contract"], run["code_sha"], run["source_release"]) == (
        "overture_places_taxonomy_v1", SHA_PRUEBA, "2026-09-23.1")


def test_F10_osm_rota_overture_se_escribe_sola(foso, duckdb_spatial, monkeypatch, tmp_path):
    _con_lector_real(foso, duckdb_spatial, monkeypatch, tmp_path)
    malo = _osm(foso, "node/1")
    malo["categoria"] = "salud"
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [malo])
    motor = _motor(monkeypatch, foso, previos={"osm": 9})
    assert _corre(foso) == 1
    assert motor.ejecutadas(UPSERT_OSM) == [] and motor.ejecutadas(CIERRE_OSM) == []
    [(res, _, filas)] = motor.ejecutadas(UPSERT_OV)
    assert res == "commit" and {f["overture_id"] for f in filas} == set(ACEPTADAS_BASE)


@pytest.mark.parametrize("previa,pasa", [({"salud": 2}, True), ({"salud": 3}, False), ({"salud": 20, "parque": 2}, False),
                                         ({"centro_comercial": 2, "farmacia": 1}, True), ({"educacion": 4}, False)])
def test_F13_C6_caida_de_cobertura_falla_antes_de_escribir_o_cerrar(foso, duckdb_spatial, monkeypatch, tmp_path,
                                                                     previa, pasa):
    """10 %: salud 2 aceptadas → previa 2 pasa (2 ≥ 1,8), previa 3 no (2 < 2,7). C6: con un cierre explícito observado
    sobre una fila activa (que la DURABILITY GUARD no aplica) y otro no representable, si la guarda de cobertura falla no
    se escribe nada."""
    filas = _con(BASE_R3, _fila("ov-cerrado", "restaurant", "food_and_drink > restaurant", estado="permanently_closed"),
                 _fila("ov-cerrada-ok", "pharmacy", "shopping > specialty_store > pharmacy_and_drug_store > pharmacy",
                       estado="permanently_closed"))
    _con_lector_real(foso, duckdb_spatial, monkeypatch, tmp_path, filas)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso, previos={"osm": 1}, cobertura=previa, capa={"ov-cerrada-ok": (True, "farmacia")})
    codigo = _corre(foso)
    [t_ov] = [t for t in motor.transacciones if any("cobertura_previa" in s for s, _ in t["sentencias"])]
    if pasa:
        assert codigo == 0 and t_ov["resultado"] == "commit"
        sent = [s for s, _ in t_ov["sentencias"]]
        assert sent[0].startswith("SELECT categoria"), "la guarda va PRIMERO"
        assert "AS operativo_en_capa" in sent[1] and UPSERT_OV in sent[2], "estado previo (solo lectura) → upsert → corrida"
        [(_, _, escritas)] = motor.ejecutadas(UPSERT_OV)
        assert motor.ejecutadas(CIERRE_OV) == []
        assert "ov-cerrada-ok" not in {f["overture_id"] for f in escritas}, "DURABILITY GUARD: se observa, no se cierra"
        assert _corridas(motor)["overture"][1]["rows_closed"] == 0
    else:
        assert codigo == 1 and t_ov["resultado"] == "rollback"
        assert [s for s, _ in t_ov["sentencias"] if not s.startswith("SELECT categoria")] == [], "nada tras la guarda"
        o = _corridas(motor)["overture"][1]
        assert (o["status"], o["error_phase"], o["error_class"]) == ("rota", "validacion", "CaidaDeCobertura")
        assert [r for r, _, _ in motor.ejecutadas(UPSERT_OSM)] == ["commit"], "OSM no se entera"


# ══ C · la frontera de cierre, en el motor falso (CI) ═════════════════════════════════════════════
def _cierres_ov(motor):
    return [p for _, _, p in motor.ejecutadas(CIERRE_OV)]


@pytest.mark.parametrize("caso,fila", [
    ("C1_bajo_confianza", _fila("ov-x", "hospital", "health_care > hospital", conf=0.40)),
    ("C2_taxonomia_no_mapeada", _fila("ov-x", "dental_clinic", "health_care > outpatient_care_facility > dental_clinic")),
    ("C3_primary_desconocida", _fila("ov-x", None, None)),
    ("C4_ausente", None)])
def test_C1_C4_lo_no_aceptado_no_cierra(foso, duckdb_spatial, monkeypatch, tmp_path, caso, fila):
    filas = _con(BASE_R3, *([fila] if fila else []))
    _con_lector_real(foso, duckdb_spatial, monkeypatch, tmp_path, filas)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso, previos={"overture": 50, "osm": 1}, cierres={"overture": 7},
                   capa={"ov-x": (True, "salud")})
    assert _corre(foso) == 0
    assert _cierres_ov(motor) == [], "sin cierre explícito aceptado de la fuente, Overture no cierra NADA"
    [(_, lectura, _)] = motor.ejecutadas("AS operativo_en_capa")
    assert lectura.startswith("SELECT"), "el estado previo se LEE (una vez), nunca se escribe"
    [(_, _, escritas)] = motor.ejecutadas(UPSERT_OV)
    assert "ov-x" not in {f["overture_id"] for f in escritas}
    assert _corridas(motor)["overture"][1]["rows_closed"] == 0


CERRADAS_C5 = [
    _fila("ov-cerrado-aceptado", "pharmacy", "shopping > specialty_store > pharmacy_and_drug_store > pharmacy",
          estado="permanently_closed"),                                                        # en la capa, activa
    _fila("ov-cerrado-nuevo", "pharmacy", "shopping > specialty_store > pharmacy_and_drug_store > pharmacy",
          estado="permanently_closed"),                                                        # NO está en la capa
    _fila("ov-cerrado-bajo", "hospital", "health_care > hospital", conf=0.40,
          estado="temporarily_closed"),                                                        # bajo la confianza
    _fila("ov-cerrado-sinmapa", "dental_clinic", "health_care > outpatient_care_facility > dental_clinic",
          estado="permanently_closed"),                                                        # taxonomía sin regla
    _fila("ov-cerrado-sintax", None, None, estado="permanently_closed"),                        # taxonomía NULL
    _fila("ov-cerrado-otro", "restaurant", "food_and_drink > restaurant", estado="permanently_closed")]  # fuera, NO en la capa


def test_C5_un_cierre_explicito_se_observa_cuenta_y_avisa_pero_no_muta_ninguna_fila(foso, duckdb_spatial, monkeypatch,
                                                                                  tmp_path):
    """DURABILITY GUARD: un cierre explícito (con CUALQUIER confianza) sobre una fila ACTIVA, sobre un GERS que NO está,
    o que la regla NO acepta → se observa, se cuenta y se AVISA, y NINGUNA escritura toca esas filas. `rows_closed` = 0:
    en R3 v1 no hay transición de estado canónico sin evidencia durable (R5)."""
    _con_lector_real(foso, duckdb_spatial, monkeypatch, tmp_path, _con(BASE_R3, *CERRADAS_C5))
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    capa = {"ov-cerrado-aceptado": (True, "farmacia"), "ov-cerrado-bajo": (True, "salud"),
            "ov-cerrado-sinmapa": (True, "salud"), "ov-cerrado-sintax": (True, "educacion")}
    motor = _motor(monkeypatch, foso, previos={"osm": 1}, capa=capa, cierres={"overture": 99})
    assert _corre(foso) == 0
    [(_, _, escritas)] = motor.ejecutadas(UPSERT_OV)
    run = _corridas(motor)["overture"][1]
    assert {f["overture_id"] for f in escritas} == set(ACEPTADAS_BASE), "solo las presencias nuevas de BASE_R3"
    assert all(f["operativo"] is True for f in escritas)
    escrituras_ov = [s for t in motor.transacciones for s, _ in t["sentencias"]
                     if s.startswith(("UPDATE pois_propios", "DELETE")) and "overture" in s]
    assert escrituras_ov == [] and motor.ejecutadas(CIERRE_OV) == [], "Overture no tiene ninguna otra escritura"
    assert run["rows_closed"] == 0 and run["rows_written"] == len(ACEPTADAS_BASE)
    o = _fuentes(_estado(tmp_path))["overture"]["observacion"]
    assert o["cierres_explicitos_observados"] == {"PERMANENTLY_CLOSED": 2, "TEMPORARILY_CLOSED": 1}
    assert o["explicitos_no_representables"] == {"descendiente": 1, "sin_taxonomia": 1, "fuera_del_mapa": 1}
    assert o["explicitos_no_representables_con_transicion"] == ["ov-cerrado-sinmapa", "ov-cerrado-sintax"]
    assert o["matriz"] == {"insertadas": len(ACEPTADAS_BASE), "permanent_closed_on_active": 1,
                           "temporary_closed_on_active": 1, "explicit_close_new": 1,
                           "explicit_status_not_representable": 3}
    [(asunto, detalle)] = foso.avisos
    assert "AVISO DE TAXONOMÍA" in asunto
    for frag in ("[permanent_closed_on_active]. GERS: ov-cerrado-aceptado", "[temporary_closed_on_active]. GERS: ov-cerrado-bajo",
                 "[explicit_close_new]. GERS: ov-cerrado-nuevo",
                 "[explicit_status_not_representable]. GERS: ov-cerrado-sinmapa, ov-cerrado-sintax"):
        assert frag in detalle, frag
    assert "ov-cerrado-otro" not in detalle, "un no representable que no está en la capa no implica transición: solo se cuenta"


def test_C7_el_cambio_de_overture_no_toca_la_semantica_de_osm(foso, duckdb_spatial, monkeypatch, tmp_path):
    _con_lector_real(foso, duckdb_spatial, monkeypatch, tmp_path)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1"), _osm(foso, "node/2")])
    motor = _motor(monkeypatch, foso, previos={"osm": 3}, cierres={"osm": 1})
    assert _corre(foso) == 0
    [(_, sql, cierre)] = motor.ejecutadas(CIERRE_OSM)
    assert " ".join(str(foso.CERRAR_OSM).split()) == sql and cierre["ids"] == ["node/1", "node/2"]
    assert "<> ALL" in sql, "OSM: cierre por AUSENCIA, como antes"
    motor = _motor(monkeypatch, foso, previos={"osm": 9})            # la guarda del 50 % de OSM, igual
    assert _corre(foso) == 0 and motor.ejecutadas(CIERRE_OSM) == []


# ══════════════════════════════════════════ POSTGIS (local) ═══════════════════════════════════════
def _siembra_overture(esq, filas):
    """Filas LEGADAS de Overture (anteriores a R3: `categoria_overture` = categories.primary, sin procedencia)."""
    import psycopg
    with psycopg.connect(esq["conninfo"], autocommit=True) as c:
        c.execute(f"SET search_path TO {esq['esquema']}, public")
        for oid, cat, legado in filas:
            c.execute("INSERT INTO pois_propios (nombre, categoria, categoria_overture, geom, fuente, confianza, "
                      "overture_id, operativo, ciudad, actualizado_en) VALUES (%s, %s, %s, "
                      "ST_SetSRID(ST_MakePoint(-78.5,-0.2),4326), 'overture', 0.9, %s, true, 'quito', %s)",
                      (f"Legado {oid}", cat, legado, oid, VIEJO))


def _estables(n=20):
    """Filas que se mantienen entre corridas para que la guarda de cobertura no oculte lo que se prueba."""
    rutas = {"hospital": "health_care > hospital", "school": "education > place_of_learning > school",
             "park": "sports_and_recreation > park",
             "pharmacy": "shopping > specialty_store > pharmacy_and_drug_store > pharmacy",
             "grocery_store": "shopping > food_and_beverage_store > grocery_store"}
    return [_fila(f"st-{h}-{i}", h, r) for h, r in rutas.items() for i in range(n)]


def _filas_json(esq) -> dict:
    """Cada fila de la capa como `row_to_json` (TODAS las columnas, también la procedencia): igualdad = byte a byte."""
    return {f[0]: f[1] for f in _psql(esq, "SELECT coalesce(overture_id, osm_id), row_to_json(p)::text FROM pois_propios p")}


def _invariante_m0(esq, foso) -> int:
    """M0 FINAL: para TODA fila Overture con procedencia, procedencia vigente → regla vigente → `categoria` vigente."""
    filas = _psql(esq, """SELECT p.overture_id, p.categoria, r.reader_contract, p.source_category_namespace, p.source_category
                          FROM pois_propios p JOIN poi_ingestion_run r ON r.id = p.ingestion_run_id
                          WHERE p.fuente = 'overture'""")
    for oid, cat, lector, ns, sc in filas:
        assert foso.categoria_de_la_regla(lector, ns, sc) == cat, (oid, cat, lector, ns, sc)
    return len(filas)


@pg
def test_PG_C1_C5_F11_dos_corridas_reales_la_frontera_de_cierre_en_la_base(foso, duckdb_spatial, esquema_pg,
                                                                           monkeypatch, tmp_path):
    monkeypatch.setattr(foso, "SYNC_URL", esquema_pg["url"])
    monkeypatch.setattr(foso, "huella_esquema_overture", foso._huella_real)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1"), _osm(foso, "node/2"),
                                                              _osm(foso, "node/3")])
    casos = [_fila("x-conf", "hospital", "health_care > hospital"), _fila("x-dent", "hospital", "health_care > hospital"),
             _fila("x-null", "park", "sports_and_recreation > park"), _fila("x-gone", "school",
                                                                            "education > place_of_learning > school"),
             _fila("x-cerradaA", "pharmacy", "shopping > specialty_store > pharmacy_and_drug_store > pharmacy"),
             _fila("x-cerradaB", "grocery_store", "shopping > food_and_beverage_store > grocery_store"),
             _fila("x-cerradaC", "hospital", "health_care > hospital"),
             _fila("x-cerradaD", "school", "education > place_of_learning > school")]
    r1 = _parquet_r3(duckdb_spatial, tmp_path / "r1.parquet", BASE_R3 + _estables(30) + casos)
    monkeypatch.setattr(foso, "overture_glob", lambda rel: r1)
    assert _corre(foso) == 0
    antes, prov1 = _filas_json(esquema_pg), _provenance(esquema_pg)
    run1 = [c for c in _corridas_bd(esquema_pg) if c["source_provider"] == "overture"][-1]
    assert _invariante_m0(esquema_pg, foso) > 0
    # 2.ª corrida: cada caso de la frontera
    casos2 = [_fila("x-conf", "hospital", "health_care > hospital", conf=0.40),                                 # C1
              _fila("x-dent", "dental_clinic", "health_care > outpatient_care_facility > dental_clinic"),        # C2
              _fila("x-null", None, None),                                                                      # C3
              _fila("x-cerradaA", "pharmacy", "shopping > specialty_store > pharmacy_and_drug_store > pharmacy",
                    estado="permanently_closed"),                                        # aceptada + cierre
              _fila("x-nueva-cerrada", "pharmacy", "shopping > specialty_store > pharmacy_and_drug_store > pharmacy",
                    estado="permanently_closed"),                                        # cierre, NUEVA → no se crea
              _fila("x-cerradaB", "grocery_store", "shopping > food_and_beverage_store > grocery_store", conf=0.40,
                    estado="temporarily_closed"),                                        # bajo la confianza + cierre
              _fila("x-cerradaC", "dental_clinic", "health_care > outpatient_care_facility > dental_clinic",
                    estado="permanently_closed"),                                        # sin regla + cierre
              _fila("x-cerradaD", None, None, estado="permanently_closed")]              # taxonomía NULL + cierre
    r2 = _parquet_r3(duckdb_spatial, tmp_path / "r2.parquet", BASE_R3 + _estables(30) + casos2)        # C4: x-gone
    monkeypatch.setattr(foso, "overture_glob", lambda rel: r2)
    foso.avisos.clear()
    assert _corre(foso) == 0
    d, prov2 = _filas_json(esquema_pg), _provenance(esquema_pg)
    run2 = [c for c in _corridas_bd(esquema_pg) if c["source_provider"] == "overture"][-1]
    # C1–C4, los cierres NO aceptados Y los cierres explícitos aceptados (DURABILITY GUARD): la fila, BYTE A BYTE igual
    # (estado, categoría, procedencia, todo). Ningún `operating_status` mueve el estado canónico en R3 v1.
    for oid in ("x-conf", "x-dent", "x-null", "x-gone", "x-cerradaA", "x-cerradaB", "x-cerradaC", "x-cerradaD"):
        assert d[oid] == antes[oid], f"{oid}: la fila no se toca"
        assert prov2[oid]["run"] == run1["id"] and prov2[oid]["operativo"] is True, oid
    assert "x-nueva-cerrada" not in d, "un cierre explícito NO crea la fila"
    assert run2["rows_closed"] == 0, "sin transiciones de estado canónico sin evidencia durable"
    # M0 FINAL · procedencia vigente → regla vigente → categoría vigente, en TODA fila con procedencia
    assert _invariante_m0(esquema_pg, foso) == run2["rows_written"] + sum(
        1 for oid in d if prov2.get(oid, {}).get("run") == run1["id"])
    # la señal NO se ignora: se cuenta y se avisa
    o = _fuentes(_estado(tmp_path))["overture"]["observacion"]
    assert o["cierres_explicitos_observados"] == {"PERMANENTLY_CLOSED": 2, "TEMPORARILY_CLOSED": 1}
    assert o["explicitos_no_representables"] == {"descendiente": 1, "sin_taxonomia": 1}
    assert o["explicitos_no_representables_con_transicion"] == ["x-cerradaC", "x-cerradaD"]
    assert (o["matriz"]["permanent_closed_on_active"], o["matriz"]["temporary_closed_on_active"],
            o["matriz"]["explicit_close_new"]) == (1, 1, 1)
    [(asunto, detalle)] = foso.avisos
    assert "AVISO DE TAXONOMÍA" in asunto and "x-cerradaC, x-cerradaD" in detalle
    assert "[permanent_closed_on_active]. GERS: x-cerradaA" in detalle and "x-cerradaB" in detalle
    osm2 = [c for c in _corridas_bd(esquema_pg) if c["source_provider"] == "osm"][-1]          # C7: OSM, como siempre
    assert all(prov2[n]["run"] == osm2["id"] and prov2[n]["operativo"] for n in ("node/1", "node/2", "node/3"))
    # F11 · lo legado que nunca se re-observó, intacto y sin procedencia
    for oid in ("ov-a", "ov-b"):
        assert d[oid] == antes[oid] and all(prov2[oid][k] is None for k in ("run", "cat", "ns", "ver", "lin"))
    assert prov1["ov-h1"]["run"] == run1["id"] and prov2["ov-h1"]["run"] == run2["id"], "re-observada → corrida nueva"


@pg
def test_PG_F9_F11_reconstruccion_desde_la_base_y_el_legado_honesto(foso, duckdb_spatial, esquema_pg, monkeypatch,
                                                                     tmp_path):
    _siembra_overture(esquema_pg, [("ov-h1", "salud", "hospital"), ("ov-ocf", "salud", "medical_center"),
                                   ("ov-viejo", "salud", "medical_center")])
    monkeypatch.setattr(foso, "SYNC_URL", esquema_pg["url"])
    monkeypatch.setattr(foso, "huella_esquema_overture", foso._huella_real)
    # con 5 estables por categoría, la cobertura previa (las 5 legadas de salud) no dispara la guarda
    _con_lector_real(foso, duckdb_spatial, monkeypatch, tmp_path, BASE_R3 + _estables(5))
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1"), _osm(foso, "node/2")])
    assert _corre(foso) == 0
    filas = _psql(esquema_pg, """SELECT p.overture_id, p.categoria, p.categoria_overture, p.source_category,
                                        p.source_category_namespace, r.reader_contract, r.code_sha, r.source_release
                                 FROM pois_propios p LEFT JOIN poi_ingestion_run r ON r.id = p.ingestion_run_id
                                 WHERE p.fuente = 'overture'""")
    reconstruidas = 0
    for oid, cat, legado, sc, ns, lector, sha, rel in filas:
        if lector is None:                       # legado: sin corrida, nada que reconstruir y nada inventado
            assert sc is None and ns is None and foso.categoria_de_la_regla(lector, ns, sc) is None, oid
            continue
        assert (lector, sha, rel, legado) == ("overture_places_taxonomy_v1", SHA_PRUEBA, "2026-09-23.1", None), oid
        assert foso.categoria_de_la_regla(lector, ns, sc) == cat, oid
        reconstruidas += 1
    assert reconstruidas == len(ACEPTADAS_BASE) + 25
    p = {f[0]: f for f in filas}
    assert p["ov-ocf"][2] is None and p["ov-ocf"][3] == "outpatient_care_facility", \
        "re-observada: la columna legada (categories.primary) pasa a NULL y la fuente es la de taxonomy (I4)"
    assert p["ov-viejo"][2] == "medical_center" and p["ov-viejo"][5] is None, "no re-observada: intacta, sin relleno"


@pg
@pytest.mark.parametrize("conf", [0.9, 0.40, None])
def test_PG_F10_deriva_deja_overture_byte_identica_y_osm_escribe(foso, duckdb_spatial, esquema_pg, monkeypatch,
                                                                 tmp_path, conf):
    """Deriva de ruta en una hoja aceptada con CUALQUIER confianza (0,9 · 0,40 · NULL) → Overture ROTA, 0 escrituras
    y 0 cierres en la base real (aunque el release traiga un cierre explícito aceptable de una fila de la capa)."""
    _siembra_overture(esquema_pg, [("ov-ph", "farmacia", "pharmacy")])
    antes = _filas_json(esquema_pg)
    monkeypatch.setattr(foso, "SYNC_URL", esquema_pg["url"])
    _con_lector_real(foso, duckdb_spatial, monkeypatch, tmp_path,
                     _con(BASE_R3, _fila("ov-rep", "hospital", "health_care > medical_facility > hospital", conf=conf),
                          _fila("ov-ph", "pharmacy", "shopping > specialty_store > pharmacy_and_drug_store > pharmacy",
                                estado="permanently_closed"), quitar=("ov-ph",)))
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [{**_osm(foso, "node/1"), "nombre": "OSM NUEVO"},
                                                              _osm(foso, "node/2")])
    assert _corre(foso) == 1
    d, f = _foto(esquema_pg), _filas_json(esquema_pg)
    assert {k: f[k] for k in f if not k.startswith("node/")} == {k: antes[k] for k in antes if not k.startswith("node/")}, \
        "Overture: 0 escrituras y 0 cierres, byte a byte (incluida ov-ph, que la fuente declara cerrada)"
    assert d["node/1"]["nombre"] == "OSM NUEVO" and d["node/3"]["operativo"] is False
    assert {c["source_provider"]: (c["status"], c["error_class"]) for c in _corridas_bd(esquema_pg)} == {
        "overture": ("rota", "DerivaTaxonomia"), "osm": ("ok", None)}


# ═════════ OPERATING STATUS · la matriz contra los CHECK REALES de la 043 (corre en el CI: PG15 sin PostGIS) ═════════
from tests.test_migracion_043 import URL as URL_CI, _aplica, banco  # noqa: E402,F401 — fixture del banco de la 043
from tests.test_poi_source_provenance_writer import _motor_sincrono  # noqa: E402

pg_ci = pytest.mark.skipif(not URL_CI, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas")


@pg_ci
async def test_PGCI_OS_la_matriz_lee_el_estado_previo_sin_tocar_ninguna_fila_bajo_la_043(foso, banco):
    """OPERATING STATUS + DURABILITY GUARD contra la 043 REAL (corre en el CI): Overture no tiene sentencia de cierre. Lo
    único que el escritor ejecuta ANTES del upsert es UNA lectura del estado previo (operativo, categoria) de los GERS
    observados; de ella sale cada celda de la matriz temporal, y SOLO se escriben presencias sobre filas nuevas o activas.
    La tabla queda BYTE A BYTE igual tras medir."""
    from sqlalchemy import text
    await _aplica(banco)
    eng = _motor_sincrono(foso)
    capa = [("m0-abierta", "farmacia", "pharmacy", True), ("m0-cerrada", "farmacia", "pharmacy", False),
            ("m0-null-cerrada", "salud", "hospital", False), ("m0-open-cerrada", "parque", "park", False),
            ("m0-temp-activa", "educacion", "school", True), ("m0-historica", "parque", "park", True),
            ("m0-open-activa", "salud", "hospital", True), ("m0-no-repr", "salud", "medical_center", True)]
    r = foso.ResultadoFuente("overture", estado="ok", lector=foso.LECTOR_OVERTURE_TAXONOMIA,
                             explicitos_no_representables={"m0-no-repr": foso.CERRADO_PERMANENTE,
                                                           "m0-fuera-de-la-capa": foso.ABIERTO})
    r.filas = [{"overture_id": "m0-abierta", "categoria": "farmacia", "operativo": False},     # PERM · activa
               {"overture_id": "m0-cerrada", "categoria": "farmacia", "operativo": False},     # TEMP · cerrada
               {"overture_id": "m0-nueva", "categoria": "farmacia", "operativo": False},       # PERM · nueva
               {"overture_id": "m0-null-cerrada", "categoria": "salud", "operativo": True},    # NULL · cerrada
               {"overture_id": "m0-open-cerrada", "categoria": "parque", "operativo": True},   # OPEN · cerrada
               {"overture_id": "m0-temp-activa", "categoria": "educacion", "operativo": False},  # TEMP · activa
               {"overture_id": "m0-historica", "categoria": "parque", "operativo": True},      # NULL · activa
               {"overture_id": "m0-open-activa", "categoria": "salud", "operativo": True},     # OPEN · activa
               {"overture_id": "m0-open-nueva", "categoria": "salud", "operativo": True}]      # OPEN · nueva
    r.estados = {"m0-abierta": foso.CERRADO_PERMANENTE, "m0-cerrada": foso.CERRADO_TEMPORAL,
                 "m0-nueva": foso.CERRADO_PERMANENTE, "m0-null-cerrada": foso.SIN_SENAL, "m0-open-cerrada": foso.ABIERTO,
                 "m0-temp-activa": foso.CERRADO_TEMPORAL, "m0-historica": foso.SIN_SENAL, "m0-open-activa": foso.ABIERTO,
                 "m0-open-nueva": foso.ABIERTO}
    todo = text("SELECT md5(string_agg(row_to_json(p)::text, '|' ORDER BY p.id)) FROM pois_propios p")
    try:
        with eng.begin() as db:
            for oid, cat, leg, op in capa:
                db.execute(text("INSERT INTO pois_propios (nombre, categoria, categoria_overture, geom, fuente, confianza, "
                                "overture_id, operativo, ciudad) VALUES (:n, :c, :l, 'SRID=4326;POINT(-78.5 -0.2)', "
                                "'overture', 0.9, :o, :op, 'quito')"), {"n": f"Legado {oid}", "c": cat, "l": leg, "o": oid,
                                                                       "op": op})
        with eng.connect() as db:
            antes = db.execute(todo).scalar()
        with eng.begin() as db:
            escribir, conteo, avisos, con_transicion = foso._matriz_de_estado(db, r)
        with eng.connect() as db:
            despues = db.execute(todo).scalar()
    finally:
        eng.dispose()
    assert {p["overture_id"] for p in escribir} == {"m0-historica", "m0-open-activa", "m0-open-nueva"}, \
        "solo presencias sobre filas activas o nuevas"
    assert conteo == {"permanent_closed_on_active": 1, "explicit_close_on_closed": 1, "explicit_close_new": 1,
                      "reobservadas_sin_open_explicito": 1, "explicit_open_on_closed": 1,
                      "temporary_closed_on_active": 1, "actualizadas": 2, "insertadas": 1,
                      "explicit_status_not_representable": 2}
    assert {k: v for k, v in avisos.items() if v} == {
        "permanent_closed_on_active": ["m0-abierta"], "explicit_close_on_closed": ["m0-cerrada"],
        "explicit_close_new": ["m0-nueva"], "reobservadas_sin_open_explicito": ["m0-null-cerrada"],
        "explicit_open_on_closed": ["m0-open-cerrada"], "temporary_closed_on_active": ["m0-temp-activa"]}
    assert con_transicion == ["m0-no-repr"], "un cierre no representable sobre una fila ACTIVA (el aviso)"
    assert despues == antes, "la lectura del estado previo es SOLO LECTURA: la tabla entera, byte a byte, igual"
    assert "UPDATE" not in str(foso.ESTADO_EN_CAPA_OVERTURE).upper() and not hasattr(foso, "CERRAR_OVERTURE"), \
        "Overture no tiene sentencia de cierre propia"


# ══════════════════════════ F15 · el dato REAL de Quito (fixture congelado, local) ═══════════════════
FIXTURE = os.getenv("R3_QUITO_FIXTURE_DIR", "")
# El bbox de Quito de 2026-09-23.1 TAL CUAL (todas las columnas): su proyección es, registro a registro, el fixture
# congelado del preflight (sha256 8805199d…, 0/0 diferencias) y su huella de esquema es la del release en S3 y la de la
# corrida #9 (9504becd…). Evidencia: r3_09_extrae_crudo.json.
HUELLA_FIXTURE_CRUDO = "4cb87be6f45311bb661f18cfb1de7bcf4f4b99cf85ea2df6f6e38ffad7e268cb"
HUELLA_ESQUEMA_RELEASE = "9504becd1b123eabeca024841a2c79ba4398705de79b1d5e131860864e95e129"
HUELLA_AGREGADO_B = "84e4df65b5914b51eda22a91f27c9f675cb9110ea358703ca75ba036a6bd5dec"
real = pytest.mark.skipif(not FIXTURE, reason="sin R3_QUITO_FIXTURE_DIR: el extracto real de Quito no va al repo")


@real
def test_F15_el_lector_sobre_el_bbox_real_de_quito_2026_09_23_1(foso, duckdb_spatial, monkeypatch):
    base = pathlib.Path(FIXTURE)
    quito, agregado = base / "quito_2026-09-23.1_crudo.parquet", base / "global_2026-09-23.1.parquet"
    assert hashlib.sha256(quito.read_bytes()).hexdigest() == HUELLA_FIXTURE_CRUDO
    assert hashlib.sha256(agregado.read_bytes()).hexdigest() == HUELLA_AGREGADO_B
    assert foso._huella_real(quito.as_posix()) == HUELLA_ESQUEMA_RELEASE, "la estructura del release REAL"
    monkeypatch.setattr(foso, "overture_glob", lambda rel: quito.as_posix())
    con = duckdb_spatial.connect()
    globales = {p for p, in con.execute(f"SELECT DISTINCT tax_primary FROM read_parquet('{agregado.as_posix()}')").fetchall()}
    con.close()
    # la existencia en el RELEASE se responde con el agregado global congelado del mismo release (no con el bbox)
    monkeypatch.setattr(foso, "_hojas_ausentes_del_release", lambda con, glob, hojas: sorted(set(hojas) - globales))
    filas = foso.pull_overture_taxonomia()
    obs = foso.ULTIMA_OVERTURE
    assert obs["deriva"] == [] and obs["alertas"] == [], "el dato real de hoy no dispara ninguna guarda"
    from collections import Counter
    assert dict(Counter(f["categoria"] for f in filas)) == {"salud": 724, "educacion": 960, "farmacia": 451,
                                                            "supermercado": 304, "centro_comercial": 138, "parque": 129}
    assert len(filas) == 2706 and obs["observacion"]["registros_bbox"] == 71655
    # OPERATING STATUS: el DOMINIO observado (no un literal supuesto) ⊆ el contrato oficial + NULL
    con = duckdb_spatial.connect()
    dominio = {v for v, in con.execute(f"SELECT DISTINCT operating_status FROM read_parquet('{quito.as_posix()}')").fetchall()}
    con.close()
    assert dominio <= set(foso.ESTADOS_OPERATIVOS_V1) | {None} and dominio == {None, "open"}
    assert obs["observacion"]["por_estado"] == {"UNKNOWN_STATUS": 71650, "OPEN": 5}
    assert obs["observacion"]["cierres_explicitos_observados"] == {}, \
        "Quito 2026-09-23.1: ningún cierre explícito (0 permanently_closed, 0 temporarily_closed)"
    assert obs["observacion"]["explicitos_no_representables"] == {"fuera_del_mapa": 5}, "los 5 `open`: fuera del mapa"
    assert set(foso.ULTIMA_OVERTURE["estados"].values()) == {"UNKNOWN_STATUS"}, "las 2706 aceptadas: NULL (sin señal)"
    assert foso._invalidas("overture", filas, foso.LECTOR_OVERTURE_TAXONOMIA, foso.ULTIMA_OVERTURE["estados"]) == []
