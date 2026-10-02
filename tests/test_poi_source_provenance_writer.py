"""POI-SOURCE-PROVENANCE · WRITER (R4): el refresco de POIs escribe procedencia REAL bajo el esquema 043.

Matriz A–AD del mandato WRITER CODE+CI 0.1, en tres capas:
  · PURA (CI): la regla de `source_updated_at`, la huella del esquema observado, el SHA y la referencia de la
    ejecución, el lector REAL de OSM (etiqueta exacta + instantánea de Overpass) y el de Overture (contra parquets
    locales con la estructura REAL de los releases medidos).
  · ORQUESTACIÓN (CI): el `main()` REAL con el motor falso de #189: compuerta 043, una corrida por fuente, las
    corridas fallidas en SU transacción, el aislamiento entre fuentes y que solo la CLASE del error se persiste.
  · POSTGIS (local, `TEST_POSTGIS_URL`): el `main()` REAL contra un esquema con la 043 REAL: atomicidad de
    POIs + corrida, la FK diferida, el enlace por fila, cierres que no re-enlazan, histórico intacto, contadores
    que cuadran con SQL, permisos intactos y lectores sin columnas nuevas.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re

import pytest

from tests.test_poi_refresh_source_isolation import (  # noqa: F401 — fixtures y ayudantes de #189
    BINDER, HUELLA_PRUEBA, RAIZ, SCRIPT, SHA_PRUEBA, SOURCES_PRUEBA, URL_PG, _corre, _estado, _foto, _fuentes, _motor,
    _osm, _ov, _parquet, _sin_corrida, _trigger_que_falla, duckdb_spatial, esquema_pg, foso, pg)

CORRIDA = "INSERT INTO poi_ingestion_run"
UPSERT_OV, UPSERT_OSM = "ON CONFLICT (overture_id)", "ON CONFLICT (osm_id)"


def _corridas(motor) -> dict:
    return {p["source_provider"]: (res, p) for res, _, p in motor.ejecutadas(CORRIDA)}


# ══════════════════════════════════════ PURA ══════════════════════════════════════════════════════
@pytest.mark.parametrize("fuentes,esperado", [
    ([{"property": "", "update_time": "2026-08-10T00:00:00.000Z"}], "2026-08-10T00:00:00+00:00"),       # meta
    ([{"property": "", "update_time": "2025-09-24T07:57:19.737Z"}], "2025-09-24T07:57:19.737000+00:00"),  # Microsoft
    ([{"property": "", "update_time": "2026-04-12T08:00:00-05:00"}], "2026-04-12T08:00:00-05:00"),     # offset explícito
    ([{"property": None, "update_time": "2026-08-10T00:00:00Z"}], "2026-08-10T00:00:00+00:00"),        # raíz sin pointer
    ([{"property": "", "update_time": "2026-04-12T00:00:00.000"}], None),                               # J · SIN zona
    ([{"property": "/properties/confidence", "update_time": "2026-08-14T19:46:07Z"}], None),            # sin raíz
    ([{"property": "", "update_time": "2026-08-10T00:00:00Z"},
      {"property": "", "update_time": "2026-08-11T00:00:00Z"}], None),                                  # dos raíces
    ([{"property": "", "update_time": "ayer"}], None), ([{"property": "", "update_time": None}], None),
    ([], None), (None, None), ("no es lista", None)])
def test_J_K_source_updated_at_solo_con_una_raiz_y_zona_explicita(foso, fuentes, esperado):
    assert foso.actualizacion_declarada(fuentes) == esperado


def test_L_M_N_la_huella_del_esquema_es_determinista_y_detecta_cambios(foso, duckdb_spatial, tmp_path):
    huella = foso._huella_real
    v1a = _parquet(duckdb_spatial, tmp_path / "v1a.parquet", con_categories=True)
    v1b = _parquet(duckdb_spatial, tmp_path / "v1b.parquet", con_categories=True)
    v2 = _parquet(duckdb_spatial, tmp_path / "v2.parquet", con_categories=False)
    con = duckdb_spatial.connect()
    con.execute("LOAD spatial;")                      # para que la copia conserve la GEOMETRY (GeoParquet)
    for nombre, sql in (("v1_tipo", f"SELECT * REPLACE (CAST(version AS BIGINT) AS version) FROM read_parquet('{v1a}')"),
                        ("v1_otros_datos", f"SELECT * REPLACE (id || '-x' AS id, 1 AS version) FROM read_parquet('{v1a}') WHERE id <> 'ov-2'"),
                        ("v1_sin_geo", f"SELECT * REPLACE (ST_AsWKB(geometry) AS geometry) FROM read_parquet('{v1a}')")):
        con.execute(f"COPY ({sql}) TO '{(tmp_path / (nombre + '.parquet')).as_posix()}' (FORMAT parquet)")
    con.close()
    con = duckdb_spatial.connect()                    # como el escritor: sin spatial
    filas = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{v1a}')").fetchall()
    con.close()
    otra = {n: huella((tmp_path / f"{n}.parquet").as_posix()) for n in ("v1_tipo", "v1_otros_datos", "v1_sin_geo")}
    # N · misma estructura (otros datos, otras filas) → misma huella; y la definición canónica es la documentada.
    assert huella(v1a) == huella(v1a) == huella(v1b) == otra["v1_otros_datos"]
    canonica = "\n".join(sorted(f"{n}\t{t}" for n, t, *_ in filas))
    assert huella(v1a) == hashlib.sha256(canonica.encode("utf-8")).hexdigest() and re.fullmatch(r"[0-9a-f]{64}", huella(v1a))
    # M · sin `categories` (v2), con un tipo distinto o con la geometría como BLOB sin metadatos `geo` → otra huella.
    assert huella(v2) != huella(v1a)
    assert otra["v1_tipo"] != huella(v1a) and otra["v1_sin_geo"] != huella(v1a)


@pytest.mark.parametrize("env,esperado", [
    ({"GITHUB_ACTIONS": "true", "GITHUB_SHA": SHA_PRUEBA}, SHA_PRUEBA),
    ({"REFRESCO_POIS_CODE_SHA": SHA_PRUEBA}, SHA_PRUEBA),
    ({"GITHUB_ACTIONS": "true", "REFRESCO_POIS_CODE_SHA": SHA_PRUEBA}, None),     # en Actions solo vale GITHUB_SHA
    ({"REFRESCO_POIS_CODE_SHA": "main"}, None), ({"REFRESCO_POIS_CODE_SHA": "latest"}, None),
    ({"REFRESCO_POIS_CODE_SHA": "feat/poi-source-provenance-writer"}, None),
    ({"REFRESCO_POIS_CODE_SHA": SHA_PRUEBA[:12]}, None), ({"REFRESCO_POIS_CODE_SHA": SHA_PRUEBA.upper()}, None),
    ({"GITHUB_ACTIONS": "true", "GITHUB_SHA": "refs/heads/main"}, None), ({}, None)])
def test_O_P_code_sha_exacto_o_nada(foso, monkeypatch, env, esperado):
    for k in ("GITHUB_ACTIONS", "GITHUB_SHA", "REFRESCO_POIS_CODE_SHA"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert foso.code_sha() == esperado


def test_invocation_ref_no_secreta_y_reproducible(foso, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_RUN_ID", "36964119468")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    monkeypatch.setenv("GITHUB_WORKFLOW", "refresco-pois")
    assert foso.invocation_ref() == "github-actions:refresco-pois:36964119468:2"
    monkeypatch.delenv("GITHUB_ACTIONS")
    assert foso.invocation_ref() is None
    monkeypatch.setenv("REFRESCO_POIS_INVOCATION_REF", "local:ensayo-r4")
    assert foso.invocation_ref() == "local:ensayo-r4"


ETIQUETAS = [("amenity", "pharmacy"), ("shop", "supermarket"), ("shop", "convenience"), ("amenity", "place_of_worship"),
             ("amenity", "police"), ("leisure", "park"), ("leisure", "garden"), ("railway", "subway_entrance"),
             ("station", "subway"), ("railway", "station"), ("amenity", "bus_station"), ("public_transport", "station"),
             ("highway", "bus_stop")]


def _overpass(foso, monkeypatch, elementos, osm3s=True):
    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            cuerpo = {"version": 0.6, "generator": "Overpass API", "elements": elementos}
            if osm3s:
                cuerpo["osm3s"] = {"timestamp_osm_base": "2026-10-02T04:37:05Z", "copyright": "ODbL"}
            return cuerpo
    monkeypatch.setattr(foso.requests, "post", lambda *a, **k: _Resp())


def test_F_G_H_osm_conserva_la_etiqueta_real_la_instantanea_y_nada_inventado(foso, monkeypatch):
    elementos = [{"type": "node", "id": n, "lat": -0.2, "lon": -78.5, "tags": {k: v, "name": f"Lugar {n}"}}
                 for n, (k, v) in enumerate(ETIQUETAS, start=1)]
    # el metro por las DOS etiquetas a la vez: gana `railway` (el orden de la condición)
    elementos.append({"type": "way", "id": 99, "center": {"lat": -0.2, "lon": -78.5},
                      "tags": {"railway": "subway_entrance", "station": "subway", "name": "Doble"}})
    _overpass(foso, monkeypatch, elementos)
    filas = {f["osm_id"]: f for f in foso.pull_osm_transporte()}
    for n, (k, v) in enumerate(ETIQUETAS, start=1):
        f = filas[f"node/{n}"]
        assert (f["source_category_namespace"], f["source_category"]) == (f"osm:{k}", v), f      # G
        assert f["source_category"] not in ("supermercado", "farmacia", "transporte", "parque")   # nunca la de Contexto
        assert (f["source_record_version"], f["source_updated_at"], f["source_lineage"]) == (None, None, None)  # H
    assert (filas["way/99"]["source_category_namespace"], filas["way/99"]["source_category"]) == ("osm:railway",
                                                                                                    "subway_entrance")
    assert filas["node/9"]["cat_leaf"] == filas["node/8"]["cat_leaf"] == "metro", "el subtipo de Contexto NO cambió"
    assert foso.ULTIMA_OSM == {"endpoint": foso._OVERPASS_ENDPOINTS[0], "snapshot_at": "2026-10-02T04:37:05+00:00"}  # F
    _overpass(foso, monkeypatch, elementos, osm3s=False)
    foso.pull_osm_transporte()
    assert foso.ULTIMA_OSM["snapshot_at"] is None, "sin osm3s no se inventa la instantánea"


def test_B_I_overture_categories_conserva_version_sources_verbatim_y_la_regla_de_fecha(foso, duckdb_spatial, tmp_path,
                                                                                         monkeypatch):
    v1 = _parquet(duckdb_spatial, tmp_path / "v1.parquet", con_categories=True)
    monkeypatch.setattr(foso, "overture_glob", lambda rel: v1)
    filas = {f["overture_id"]: f for f in foso.pull_overture()}
    con = duckdb_spatial.connect()
    originales = {i: s for i, s in con.execute(f"SELECT id, sources FROM read_parquet('{v1}')").fetchall()}
    con.close()
    for oid, f in filas.items():
        assert f["source_category"] == f["cat_leaf"] and f["source_category_namespace"] == "overture:categories.primary"
        assert json.loads(f["source_lineage"]) == originales[oid], "sources[] VERBATIM (con su licencia)"
    assert [f["source_record_version"] for f in (filas["ov-1"], filas["ov-2"], filas["ov-3"])] == ["9", "4", "2"]
    assert filas["ov-1"]["source_updated_at"] == "2026-08-10T00:00:00+00:00"            # meta, con Z
    assert filas["ov-3"]["source_updated_at"] is None, "Foursquare sin zona → NULL"
    assert json.loads(filas["ov-3"]["source_lineage"])[0]["license"] == "Apache-2.0"


def test_Z_ningun_camino_de_esta_unidad_escribe_taxonomy(foso):
    fuente = SCRIPT.read_text(encoding="utf-8")
    assert "overture:taxonomy.primary" not in fuente and foso.NS_OVERTURE == "overture:categories.primary"
    assert foso.LECTOR_OVERTURE == "overture_places_categories_v1" and foso.LECTOR_OSM == "osm_overpass_nwr_body_center_v1"
    from app.contracts.place_evidence_v0 import SourceCategoryNamespace
    assert "overture:taxonomy.primary" not in {n.value for n in SourceCategoryNamespace}


# ═══════════════════════════════════ ORQUESTACIÓN ═════════════════════════════════════════════════
def test_A_sin_esquema_043_falla_cerrado_sin_escribir_nada(foso, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(foso, "pull_overture", lambda: [_ov(foso, "ov-a")])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso, previos={"overture": 1, "osm": 1})
    monkeypatch.setattr(foso, "verificar_esquema_043", lambda eng: ["no existe poi_ingestion_run"])
    assert _corre(foso) == 1
    sentencias = [s for t in motor.transacciones for s, _ in t["sentencias"]]
    assert sentencias == [], f"0 escrituras, 0 cierres, 0 corridas, 0 DDL: {sentencias}"
    f = _fuentes(_estado(tmp_path))
    assert {(x["estado"], x["fase"], x["error"], x["manifiesto"]) for x in f.values()} == {
        ("rota", "escritura", "Esquema043Ausente", "NOT PERSISTED")}
    assert "MANIFEST NOT PERSISTED" in capsys.readouterr().out


def test_A2_base_inalcanzable_en_la_compuerta_es_lo_mismo(foso, monkeypatch, tmp_path):
    monkeypatch.setattr(foso, "pull_overture", lambda: [_ov(foso, "ov-a")])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso)

    def _caida(eng):
        raise ConnectionError("server closed the connection (host db.secreto)")
    monkeypatch.setattr(foso, "verificar_esquema_043", _caida)
    assert _corre(foso) == 1 and [t for t in motor.transacciones if t["sentencias"]] == []
    assert "db.secreto" not in (tmp_path / "estado.json").read_text(encoding="utf-8")


def test_P_sha_invalido_falla_cerrado_antes_de_todo(foso, monkeypatch, tmp_path):
    monkeypatch.setenv("REFRESCO_POIS_CODE_SHA", "main")
    llamado = []
    monkeypatch.setattr(foso, "pull_overture", lambda: llamado.append("ov") or [])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: llamado.append("osm") or [])
    motor = _motor(monkeypatch, foso)
    assert _corre(foso) == 1
    assert motor.creado is False and llamado == [], "ni base ni fuentes"
    e = _estado(tmp_path)
    assert e["resultado"] == "SIN REFRESCO · CODE SHA NO DETERMINABLE" and e["codigo"] == 1
    [(asunto, _)] = foso.avisos
    assert "CODE SHA" in asunto


def test_S_las_dos_ok_una_corrida_por_fuente_en_su_transaccion_con_sus_contadores(foso, monkeypatch, tmp_path):
    ov, osm = [_ov(foso, "ov-a"), _ov(foso, "ov-b")], [_osm(foso, "node/1"), _osm(foso, "way/2", "parque", "park")]
    monkeypatch.setattr(foso, "pull_overture", lambda: ov)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: osm)
    monkeypatch.setattr(foso, "ULTIMA_OSM", {"endpoint": "https://overpass-api.de/api/interpreter",
                                             "snapshot_at": "2026-10-02T04:37:05+00:00"})
    motor = _motor(monkeypatch, foso, previos={"overture": 2, "osm": 2}, cierres={"overture": 1, "osm": 0})
    assert _corre(foso) == 0
    c = _corridas(motor)
    assert set(c) == {"overture", "osm"}
    for fuente, frag in (("overture", UPSERT_OV), ("osm", UPSERT_OSM)):
        [t] = motor.tx_con(frag)
        assert CORRIDA in t["sentencias"][-1][0], "la corrida, AL FINAL de la transacción de SU fuente"
        [(res, _, filas)] = motor.ejecutadas(frag)
        assert {f["ingestion_run_id"] for f in filas} == {c[fuente][1]["id"]}
    o, s = c["overture"][1], c["osm"][1]
    assert (o["status"], o["reader_contract"], o["source_release"], o["source_schema_fingerprint"],
            o["source_snapshot_at"]) == ("ok", "overture_places_categories_v1", "2026-09-23.1", HUELLA_PRUEBA, None)
    assert (o["rows_fetched"], o["rows_valid"], o["rows_written"], o["rows_closed"]) == (2, 2, 2, 1)
    assert (s["status"], s["reader_contract"], s["source_release"], s["source_schema_fingerprint"],
            s["source_snapshot_at"]) == ("ok", "osm_overpass_nwr_body_center_v1", None, None, "2026-10-02T04:37:05+00:00")
    for p in (o, s):
        assert p["code_sha"] == SHA_PRUEBA and p["error_class"] is p["error_phase"] is None
        assert p["started_at"] <= p["fetched_at"] <= p["completed_at"]
    assert {x["manifiesto"] for x in _fuentes(_estado(tmp_path)).values()} == {"persistido"}


def test_C_Q_overture_taxonomy_rota_con_su_huella_y_osm_ok(foso, duckdb_spatial, monkeypatch, tmp_path):
    v2 = _parquet(duckdb_spatial, tmp_path / "v2.parquet", con_categories=False)   # el esquema de 2026-09-23.x
    monkeypatch.setattr(foso, "overture_glob", lambda rel: v2)
    monkeypatch.setattr(foso, "huella_esquema_overture", foso._huella_real)      # la huella REAL del parquet
    osm = [_osm(foso, "node/1"), _osm(foso, "node/2")]
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: osm)
    motor = _motor(monkeypatch, foso, previos={"osm": 2})
    assert _corre(foso) == 1                                                       # D-4 sigue: degradado / exit 1
    assert motor.ejecutadas(UPSERT_OV) == [] and motor.ejecutadas("fuente = 'overture'") == []
    c = _corridas(motor)
    res, o = c["overture"]
    assert res == "commit" and len(motor.tx_con(CORRIDA)) == 2
    assert (o["status"], o["error_phase"], o["error_class"]) == ("rota", "obtencion", "BinderException")
    assert o["source_release"] == "2026-09-23.1" and o["source_schema_fingerprint"] == foso._huella_real(v2), \
        "la estructura SÍ se observó antes del Binder: su huella queda"
    assert o["rows_written"] is o["rows_closed"] is o["fetched_at"] is None
    assert c["osm"][1]["status"] == "ok" and [r for r, _, _ in motor.ejecutadas(UPSERT_OSM)] == ["commit"]


def test_C2_sin_poder_observar_el_esquema_no_hay_huella(foso, monkeypatch):
    def _sin_release(glob):
        raise foso.duckdb.IOException("IO Error: No files found that match the pattern")
    monkeypatch.setattr(foso, "huella_esquema_overture", _sin_release)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso, previos={"osm": 1})
    assert _corre(foso) == 1
    o = _corridas(motor)["overture"][1]
    assert (o["status"], o["source_release"], o["source_schema_fingerprint"], o["error_class"]) == (
        "rota", "2026-09-23.1", None, "IOException"), "release resuelto sí; huella inventada no"


def test_D_overture_sin_red_es_caida_registrada(foso, monkeypatch):
    import requests

    def _caida():
        raise requests.ConnectionError("Max retries exceeded with url: https://user:secreto@s3/x")
    monkeypatch.setattr(foso, "pull_overture", _caida)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso, previos={"osm": 1})
    assert _corre(foso) == 2
    o = _corridas(motor)["overture"][1]
    assert (o["status"], o["error_phase"], o["error_class"]) == ("caida", "obtencion", "ConnectionError")
    assert "secreto" not in json.dumps(o) and "Max retries" not in json.dumps(o)                 # AD


def test_R_overture_ok_y_osm_rota_por_validacion(foso, monkeypatch):
    monkeypatch.setattr(foso, "pull_overture", lambda: [_ov(foso, "ov-a")])
    malo = _osm(foso, "node/1")
    malo["source_category_namespace"] = None                                       # procedencia incompleta
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [malo])
    motor = _motor(monkeypatch, foso, previos={"overture": 1})
    assert _corre(foso) == 1
    assert motor.ejecutadas(UPSERT_OSM) == [] and motor.ejecutadas("fuente = 'osm'") == []
    c = _corridas(motor)
    assert (c["osm"][1]["status"], c["osm"][1]["error_phase"], c["osm"][1]["error_class"]) == (
        "rota", "validacion", "DatasetInvalido")
    assert c["osm"][1]["rows_fetched"] == 1 and c["osm"][1]["rows_valid"] is None
    assert c["overture"][1]["status"] == "ok" and [r for r, _, _ in motor.ejecutadas(UPSERT_OV)] == ["commit"]


@pytest.mark.parametrize("dano", ["ns_ajeno", "categoria_distinta_de_la_columna_legada", "osm_con_lineage"])
def test_la_procedencia_incoherente_invalida_su_fuente_antes_de_la_base(foso, monkeypatch, dano):
    ov, osm = [_ov(foso, "ov-a")], [_osm(foso, "node/1")]
    if dano == "ns_ajeno":
        ov[0]["source_category_namespace"] = "overture:taxonomy.primary"
    elif dano == "categoria_distinta_de_la_columna_legada":
        ov[0]["source_category"] = "grocery_store"
    else:
        osm[0]["source_lineage"] = "[]"
    monkeypatch.setattr(foso, "pull_overture", lambda: ov)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: osm)
    motor = _motor(monkeypatch, foso, previos={"overture": 1, "osm": 1})
    assert _corre(foso) == 1
    fuente = "osm" if dano == "osm_con_lineage" else "overture"
    assert motor.ejecutadas(UPSERT_OSM if fuente == "osm" else UPSERT_OV) == []
    assert _corridas(motor)[fuente][1]["error_phase"] == "validacion"


def test_T_las_dos_fallan_dos_corridas_fallidas_y_cero_pois(foso, monkeypatch, tmp_path):
    def _rota():
        raise foso.duckdb.BinderException(f"Binder Error: {BINDER}!")
    malo = _osm(foso, "node/1")
    malo["categoria"] = "salud"
    monkeypatch.setattr(foso, "pull_overture", _rota)
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [malo])
    motor = _motor(monkeypatch, foso, previos={"overture": 2753, "osm": 5788})
    assert _corre(foso) == 1
    sentencias = [s for t in motor.transacciones for s, _ in t["sentencias"]]
    assert not any(s.startswith(("INSERT INTO pois_propios", "UPDATE pois_propios", "CREATE ", "ALTER ")) for s in sentencias)
    c = _corridas(motor)
    assert {k: (v[0], v[1]["status"], v[1]["error_phase"]) for k, v in c.items()} == {
        "overture": ("commit", "rota", "obtencion"), "osm": ("commit", "rota", "validacion")}
    assert all(len(t["sentencias"]) == 1 for t in motor.tx_con(CORRIDA)), "cada corrida fallida, sola"
    assert _estado(tmp_path)["resultado"] == "SIN REFRESCO · OVERTURE ROTA · OSM ROTA"


def test_U_V_un_fallo_de_escritura_revierte_pois_y_corrida_y_deja_la_fallida_aparte(foso, monkeypatch, tmp_path):
    monkeypatch.setattr(foso, "pull_overture", lambda: [_ov(foso, "ov-a")])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    motor = _motor(monkeypatch, foso, previos={"overture": 1}, falla_en=UPSERT_OSM)
    assert _corre(foso) == 1
    [t_osm] = motor.tx_con(UPSERT_OSM)
    assert t_osm["resultado"] == "rollback" and not any(CORRIDA in s for s, _ in t_osm["sentencias"])
    fallida = [t for t in motor.tx_con(CORRIDA)
               if any(CORRIDA in s and p["source_provider"] == "osm" for s, p in t["sentencias"])]
    assert len(fallida) == 1 and fallida[0]["resultado"] == "commit"
    assert len(fallida[0]["sentencias"]) == 1, "la corrida fallida va SOLA en su transacción pequeña"
    p = fallida[0]["sentencias"][0][1]
    assert (p["status"], p["error_phase"], p["error_class"], p["rows_written"]) == ("rota", "escritura", "RuntimeError", None)
    assert "db.secreto" not in json.dumps(p) and "fallo simulado" not in json.dumps(p)          # AD
    assert _corridas(motor)["overture"][1]["status"] == "ok"


def test_manifest_not_persisted_si_ni_la_corrida_fallida_entra(foso, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(foso, "pull_overture", lambda: [_ov(foso, "ov-a")])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    _motor(monkeypatch, foso, previos={"overture": 1}, falla_en="INSERT INTO poi_ingestion_run")
    assert _corre(foso) == 1
    f = _fuentes(_estado(tmp_path))
    assert {(x["estado"], x["manifiesto"]) for x in f.values()} == {("rota", "NOT PERSISTED")}
    assert capsys.readouterr().out.count("MANIFEST NOT PERSISTED") == 2, "ni éxito fingido ni reintento"


def test_el_escritor_no_crea_ni_migra_esquema_ni_concede_nada():
    """AB · la autoridad la puso la 043; el escritor solo escribe filas (el DDL T0 de siempre, idempotente)."""
    fuente = "\n".join(l.split("#", 1)[0] for l in SCRIPT.read_text(encoding="utf-8").splitlines())
    assert not re.search(r"(?i)\b(GRANT|REVOKE|CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?poi_ingestion_run|"
                         r"ALTER\s+TABLE\s+poi_ingestion_run|ROW\s+LEVEL\s+SECURITY)\b", fuente)
    assert not re.search(r"(?i)ADD COLUMN IF NOT EXISTS (ingestion_run_id|source_)", fuente)


# ═════════════════════════════════════ POSTGIS ════════════════════════════════════════════════════
def _psql(esq, sql, *a):
    import psycopg
    with psycopg.connect(esq["conninfo"]) as c:
        c.execute(f"SET search_path TO {esq['esquema']}, public")
        return c.execute(sql, a).fetchall()


def _provenance(esq) -> dict:
    filas = _psql(esq, """SELECT coalesce(overture_id, osm_id), ingestion_run_id::text, source_category,
                                 source_category_namespace, source_record_version, source_updated_at, source_lineage,
                                 categoria_overture, operativo
                          FROM pois_propios ORDER BY 1""")
    return {f[0]: dict(zip(("run", "cat", "ns", "ver", "upd", "lin", "legado", "operativo"), f[1:])) for f in filas}


def _corridas_bd(esq) -> list[dict]:
    cols = ("id::text", "source_provider", "status", "reader_contract", "source_release", "source_schema_fingerprint",
            "source_snapshot_at", "code_sha", "rows_fetched", "rows_valid", "rows_written", "rows_closed",
            "error_class", "error_phase")
    return [dict(zip([c.split("::")[0] for c in cols], f))
            for f in _psql(esq, f"SELECT {', '.join(cols)} FROM poi_ingestion_run ORDER BY completed_at")]


def _utc(texto: str):
    from datetime import datetime
    return datetime.fromisoformat(texto)


@pg
def test_PG_A_sin_043_no_escribe_nada(foso, esquema_pg, monkeypatch):
    import psycopg
    with psycopg.connect(esquema_pg["conninfo"], autocommit=True) as c:
        c.execute(f"SET search_path TO {esquema_pg['esquema']}, public")
        c.execute("ALTER TABLE pois_propios DROP CONSTRAINT ck_pois_linaje_forma")       # 043 INCOMPLETA
    antes = _foto(esquema_pg)
    monkeypatch.setattr(foso, "SYNC_URL", esquema_pg["url"])
    monkeypatch.setattr(foso, "pull_overture", lambda: [_ov(foso, "ov-a")])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    assert _corre(foso) == 1
    assert _foto(esquema_pg) == antes and _corridas_bd(esquema_pg) == []


@pg
def test_PG_B_E_F_G_las_dos_ok_procedencia_real_y_contadores_que_cuadran(foso, duckdb_spatial, esquema_pg, monkeypatch,
                                                                         tmp_path):
    v1 = _parquet(duckdb_spatial, tmp_path / "v1.parquet", con_categories=True)
    monkeypatch.setattr(foso, "overture_glob", lambda rel: v1)
    monkeypatch.setattr(foso, "overture_release", lambda: "2026-08-19.0")
    monkeypatch.setattr(foso, "huella_esquema_overture", foso._huella_real)
    osm = [_osm(foso, "node/1"), _osm(foso, "node/2"), _osm(foso, "way/9", "parque", "park")]
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: osm)
    monkeypatch.setattr(foso, "ULTIMA_OSM", {"endpoint": "https://overpass-api.de/api/interpreter",
                                             "snapshot_at": "2026-10-02T04:37:05+00:00"})
    monkeypatch.setattr(foso, "SYNC_URL", esquema_pg["url"])
    assert _corre(foso) == 0
    o, s = [{c["source_provider"]: c for c in _corridas_bd(esquema_pg)}[k] for k in ("overture", "osm")]
    assert (o["status"], o["source_release"], o["source_schema_fingerprint"]) == ("ok", "2026-08-19.0", foso._huella_real(v1))
    assert (s["status"], s["source_snapshot_at"], s["source_release"]) == (
        "ok", _utc("2026-10-02T04:37:05+00:00"), None)
    assert o["code_sha"] == s["code_sha"] == SHA_PRUEBA
    p = _provenance(esquema_pg)
    for oid in ("ov-1", "ov-2", "ov-3"):
        assert (p[oid]["run"], p[oid]["ns"], p[oid]["cat"]) == (o["id"], "overture:categories.primary", p[oid]["legado"])
    assert p["ov-1"]["upd"] == _utc("2026-08-10T00:00:00+00:00") and p["ov-3"]["upd"] is None
    assert p["ov-2"]["upd"] == _utc("2025-09-24T07:57:19.737+00:00")
    con = duckdb_spatial.connect()
    original = dict(con.execute(f"SELECT id, sources FROM read_parquet('{v1}')").fetchall())
    con.close()
    assert all(p[oid]["lin"] == original[oid] for oid in original), "I · sources[] ida y vuelta por la base"
    for oid in ("node/1", "node/2", "way/9"):
        assert (p[oid]["run"], p[oid]["ver"], p[oid]["upd"], p[oid]["lin"]) == (s["id"], None, None, None)
    assert (p["node/1"]["ns"], p["node/1"]["cat"]) == ("osm:highway", "bus_stop")
    # AC · los contadores de la corrida son los de SQL.
    for c in (o, s):
        assert c["rows_written"] == _psql(esquema_pg, "SELECT count(*) FROM pois_propios WHERE ingestion_run_id = %s",
                                          c["id"])[0][0]
    assert s["rows_closed"] == 1 and p["node/3"]["operativo"] is False
    assert o["rows_closed"] == 2 and p["ov-a"]["operativo"] is False and p["ov-b"]["operativo"] is False


@pg
def test_PG_W_X_Y_cierre_no_reenlaza_reobservada_si_e_historico_intacto(foso, esquema_pg, monkeypatch):
    monkeypatch.setattr(foso, "SYNC_URL", esquema_pg["url"])
    monkeypatch.setattr(foso, "pull_overture", lambda: [_ov(foso, "ov-a"), _ov(foso, "ov-b")])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1"), _osm(foso, "node/2"),
                                                              _osm(foso, "node/3")])
    assert _corre(foso) == 0
    r1 = _provenance(esquema_pg)
    # 2.ª corrida: node/3 ya no viene (se CIERRA) y node/1 se vuelve a observar.
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1"), _osm(foso, "node/2")])
    assert _corre(foso) == 0
    r2 = _provenance(esquema_pg)
    osm2 = [c for c in _corridas_bd(esquema_pg) if c["source_provider"] == "osm"][-1]
    assert r2["node/3"]["operativo"] is False and r2["node/3"]["run"] == r1["node/3"]["run"] != osm2["id"], \
        "W · el cierre no re-enlaza: la fila conserva la corrida que la observó por última vez"
    assert r2["node/1"]["run"] == osm2["id"] != r1["node/1"]["run"], "X · reobservada → corrida actual"
    assert len(_corridas_bd(esquema_pg)) == 4, "una corrida por fuente y ejecución"


@pg
def test_PG_Y_el_historico_no_tocado_queda_null(foso, esquema_pg, monkeypatch):
    monkeypatch.setattr(foso, "SYNC_URL", esquema_pg["url"])
    monkeypatch.setattr(foso, "pull_overture", lambda: (_ for _ in ()).throw(
        foso.duckdb.BinderException(f"Binder Error: {BINDER}!")))
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1"), _osm(foso, "node/2"),
                                                              _osm(foso, "node/3")])
    assert _corre(foso) == 1
    p = _provenance(esquema_pg)
    for oid in ("ov-a", "ov-b"):                                   # Overture ROTA: sus filas viejas, intactas y NULL
        assert all(p[oid][k] is None for k in ("run", "cat", "ns", "ver", "upd", "lin")), p[oid]
    assert {c["source_provider"]: c["status"] for c in _corridas_bd(esquema_pg)} == {"overture": "rota", "osm": "ok"}


@pg
@pytest.mark.parametrize("fuente", ["osm", "overture"])
def test_PG_U_V_fallo_a_mitad_revierte_pois_y_corrida_ok(foso, esquema_pg, monkeypatch, fuente):
    if fuente == "osm":
        _trigger_que_falla(esquema_pg, "osm_id", "node/666")
    else:
        _trigger_que_falla(esquema_pg, "overture_id", "ov-boom")
    antes = _foto(esquema_pg)
    monkeypatch.setattr(foso, "SYNC_URL", esquema_pg["url"])
    monkeypatch.setattr(foso, "pull_overture", lambda: [{**_ov(foso, "ov-a"), "nombre": "NUEVO"}] +
                        ([_ov(foso, "ov-boom")] if fuente == "overture" else []))
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [{**_osm(foso, "node/1"), "nombre": "NUEVO"}] +
                        ([_osm(foso, "node/666")] if fuente == "osm" else []))
    assert _corre(foso) == 1
    despues, corridas, p = _foto(esquema_pg), _corridas_bd(esquema_pg), _provenance(esquema_pg)
    rota = next(c for c in corridas if c["source_provider"] == fuente)
    assert (rota["status"], rota["error_phase"], rota["rows_written"]) == ("rota", "escritura", None)
    assert _psql(esquema_pg, "SELECT count(*) FROM pois_propios WHERE ingestion_run_id = %s", rota["id"])[0][0] == 0
    clave = "node/1" if fuente == "osm" else "ov-a"
    assert despues[clave] == antes[clave] and p[clave]["run"] is None, "el POI de la fuente fallida, intacto y sin enlace"
    sana = next(c for c in corridas if c["source_provider"] != fuente)
    assert sana["status"] == "ok"


@pg
def test_PG_AA_AB_lectores_sin_columnas_nuevas_y_permisos_intactos(foso, esquema_pg, monkeypatch):
    import psycopg
    acl = "SELECT relname, coalesce(relacl::text, '-'), relrowsecurity FROM pg_class WHERE relnamespace = %s::regnamespace " \
          "AND relname IN ('pois_propios', 'poi_ingestion_run', 'pois_vivos') ORDER BY 1"
    antes = _psql(esquema_pg, acl, esquema_pg["esquema"])
    vista = [r[0] for r in _psql(esquema_pg, "SELECT attname FROM pg_attribute WHERE attrelid = 'pois_vivos'::regclass "
                                             "AND attnum > 0 AND NOT attisdropped ORDER BY attnum")]
    monkeypatch.setattr(foso, "SYNC_URL", esquema_pg["url"])
    monkeypatch.setattr(foso, "pull_overture", lambda: [_ov(foso, "ov-a")])
    monkeypatch.setattr(foso, "pull_osm_transporte", lambda: [_osm(foso, "node/1")])
    assert _corre(foso) in (0, 1)
    assert _psql(esquema_pg, acl, esquema_pg["esquema"]) == antes
    assert [r[0] for r in _psql(esquema_pg, "SELECT attname FROM pg_attribute WHERE attrelid = 'pois_vivos'::regclass "
                                            "AND attnum > 0 AND NOT attisdropped ORDER BY attnum")] == vista
    assert not ({"ingestion_run_id", "source_lineage", "source_updated_at", "source_record_version"} & set(vista))
    propia = (RAIZ / "app" / "place" / "providers" / "propia.py").read_text(encoding="utf-8")
    params = {"lat": -0.19, "lon": -78.49, "max_m": 3000, "cats": ["transporte", "salud"], "masivo": ["metro"]}
    nuevas = {"ingestion_run_id", "source_lineage", "source_updated_at", "source_record_version", "source_category",
              "source_category_namespace"}
    for nombre in ("_PROPIOS_ENTORNO_SQL", "_PROPIOS_TRANSPORTE_SQL"):      # el SQL REAL de los lectores
        sql = re.search(nombre + r' = text\("""(.*?)"""\)', propia, re.S).group(1)
        sql = re.sub(r"(?<!:):([A-Za-z_]\w*)", r"%(\1)s", sql)            # :param → %(param)s; `::tipo` intacto
        with psycopg.connect(esquema_pg["conninfo"]) as c:
            c.execute(f"SET search_path TO {esquema_pg['esquema']}, public")
            cur = c.execute(sql, params)
            columnas = {d.name for d in cur.description}
            assert cur.fetchall(), f"{nombre} lee filas del banco"
        assert not (nuevas & columnas), nombre


def test_AA_ningun_lector_de_la_app_nombra_la_procedencia_nueva():
    """AA · `/aura`, Place Evidence v0 y el resto de la app no leen columnas de la 043 (R5 es otra unidad)."""
    patron = re.compile(r"\b(ingestion_run_id|source_lineage|source_updated_at|source_record_version|poi_ingestion_run)\b")
    hallazgos = [f"{p.relative_to(RAIZ)}:{i}" for p in (RAIZ / "app").rglob("*.py")
                 for i, l in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if patron.search(l)]
    assert hallazgos == []
    # `source_category(_namespace)` SÍ existen en la app, pero como campos del CONTRATO v0 (que los deriva de
    # `categoria_overture` + `fuente`), nunca como columnas leídas de la capa.
    sql_app = "\n".join(re.findall(r'text\("""(.*?)"""\)', "\n".join(
        p.read_text(encoding="utf-8") for p in (RAIZ / "app").rglob("*.py")), re.S))
    assert not re.search(r"\bsource_category", sql_app)
