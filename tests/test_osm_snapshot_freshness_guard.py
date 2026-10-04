"""OSM SNAPSHOT FRESHNESS GUARD (D-OSM-1): un espejo de Overpass cuya instantánea es más vieja que la ya aceptada NO se
usa; se prueba el siguiente; si ninguno está al día, OSM queda CAÍDA (0 escrituras, 0 cierres) y Overture sigue.

D-OSM-1 (corrida 37133309229, 2026-10-03): `overpass-api.de` dio 504 y `overpass.kumi.systems` respondió con
`osm3s.timestamp_osm_base` = 2026-07-15T15:22:01Z cuando el máximo ya aplicado era 2026-10-02T14:53:35Z: 171 cierres y
27 reaperturas falsos. Matriz F1–F12 del mandato «OSM SNAPSHOT FRESHNESS GUARD · CODE+CI» + el fixture de regresión
EXACTO (esas dos instantáneas) + la reproducción del defecto con el escritor de `main` (87d4c5b4).
Capas: PURA y ORQUESTACIÓN (motor falso de #189) en el CI; POSTGIS (`TEST_POSTGIS_URL`, la 043 REAL) solo en local.
"""
from __future__ import annotations

import ast
import importlib.util
import subprocess
from datetime import datetime, timezone

import pytest
import requests

from tests.test_poi_refresh_source_isolation import (  # noqa: F401 — fixtures y ayudantes de #189
    RAIZ, _corre, _estado, _foto, _fuentes, _inyecta_lector, _motor, _ov, esquema_pg, foso, pg)

PISO = datetime(2026, 10, 2, 14, 53, 35, tzinfo=timezone.utc)   # el máximo histórico de producción (corrida R4)
IGUAL = "2026-10-02T14:53:35Z"
OBSOLETA = "2026-07-15T15:22:01Z"                                 # la instantánea que sirvió kumi (D-OSM-1)
FRESCA = "2026-10-04T06:00:00Z"
UPSERT_OV, UPSERT_OSM = "ON CONFLICT (overture_id)", "ON CONFLICT (osm_id)"
CIERRA_OSM = "AND operativo AND fuente = 'osm'"
CORRIDA = "INSERT INTO poi_ingestion_run"
MAIN_R3 = "87d4c5b44d620e30c5fc6fd9eb57671d5b590d9a"   # `main` antes de esta unidad (merge de R3, #192)
E504 = requests.HTTPError("504 Server Error: Gateway Timeout")


def _cuerpo(instante, nodos, osm3s=True):
    """Una respuesta de Overpass: paradas de bus con nombre (node/<id>). `instante` va a `osm3s.timestamp_osm_base`."""
    cuerpo = {"version": 0.6, "generator": "Overpass API",
              "elements": [{"type": "node", "id": i, "lat": -0.19, "lon": -78.49,
                            "tags": {"highway": "bus_stop", "name": f"Parada {i}"}} for i in nodos]}
    if osm3s:
        cuerpo["osm3s"] = {"timestamp_osm_base": instante, "copyright": "ODbL"}
    return cuerpo


class _Resp:
    def __init__(self, cuerpo):
        self._c = cuerpo

    def raise_for_status(self):
        return None

    def json(self):
        return self._c


def _espejos(m, monkeypatch, *respuestas):
    """Un comportamiento por espejo, en el orden de `_OVERPASS_ENDPOINTS`: un cuerpo JSON o una excepción. Registra a
    quién se llamó (y cuántas transacciones tenía ya el motor, si se da)."""
    llamadas = []
    tabla = dict(zip(m._OVERPASS_ENDPOINTS, respuestas, strict=True))

    def _post(url, *a, **k):
        llamadas.append(url)
        r = tabla[url]
        if isinstance(r, BaseException):
            raise r
        return _Resp(r)
    monkeypatch.setattr(m.requests, "post", _post)
    return llamadas


def _ids(filas):
    return sorted(f["osm_id"] for f in filas)


def _resultados(m):
    return [i["resultado"] for i in m.FRESCURA_OSM["intentos"]]


# ══════════════════════════════════════ PURA: la guarda por espejo ═══════════════════════════════════════════════
def test_F1_instantanea_posterior_al_piso_se_acepta(foso, monkeypatch):
    monkeypatch.setattr(foso, "PISO_OSM", PISO)
    llamadas = _espejos(foso, monkeypatch, _cuerpo(FRESCA, [1]), E504, E504)
    assert _ids(foso.pull_osm_transporte()) == ["node/1"]
    assert llamadas == foso._OVERPASS_ENDPOINTS[:1]
    assert foso.ULTIMA_OSM == {"endpoint": foso._OVERPASS_ENDPOINTS[0], "snapshot_at": "2026-10-04T06:00:00+00:00"}
    assert _resultados(foso) == ["ACEPTADO"] and foso.FRESCURA_OSM["piso"] == "2026-10-02T14:53:35+00:00"


def test_F2_instantanea_igual_al_piso_se_acepta_idempotente(foso, monkeypatch):
    monkeypatch.setattr(foso, "PISO_OSM", PISO)
    _espejos(foso, monkeypatch, _cuerpo(IGUAL, [1]), E504, E504)
    assert _ids(foso.pull_osm_transporte()) == ["node/1"]
    assert _resultados(foso) == ["IDEMPOTENTE"]
    assert foso.ULTIMA_OSM["snapshot_at"] == "2026-10-02T14:53:35+00:00"


def test_F3_instantanea_anterior_al_piso_se_rechaza_y_se_prueba_el_siguiente(foso, monkeypatch):
    monkeypatch.setattr(foso, "PISO_OSM", PISO)
    llamadas = _espejos(foso, monkeypatch, _cuerpo(OBSOLETA, [1]), E504, E504)
    assert foso.pull_osm_transporte() is None, "desfasado = fallo de ESE espejo, no una lista que escribir"
    assert llamadas == foso._OVERPASS_ENDPOINTS, "tras el desfasado se prueban los demás espejos"
    assert _resultados(foso) == ["DESFASADO", "FALLO", "FALLO"]
    assert foso.FRESCURA_OSM["intentos"][0]["instantanea"] == "2026-07-15T15:22:01+00:00"
    assert foso.ULTIMA_OSM == {}, "nada aceptado: ni espejo ni instantánea"


def test_F4_primero_desfasado_segundo_fresco_se_acepta_el_segundo(foso, monkeypatch):
    monkeypatch.setattr(foso, "PISO_OSM", PISO)
    llamadas = _espejos(foso, monkeypatch, _cuerpo(OBSOLETA, [1, 9]), _cuerpo(FRESCA, [1, 3]), E504)
    assert _ids(foso.pull_osm_transporte()) == ["node/1", "node/3"]
    assert llamadas == foso._OVERPASS_ENDPOINTS[:2]
    assert _resultados(foso) == ["DESFASADO", "ACEPTADO"]
    assert foso.ULTIMA_OSM["endpoint"] == foso._OVERPASS_ENDPOINTS[1]


def test_F5_504_luego_desfasado_luego_fresco_se_acepta_el_tercero(foso, monkeypatch):
    monkeypatch.setattr(foso, "PISO_OSM", PISO)
    llamadas = _espejos(foso, monkeypatch, E504, _cuerpo(OBSOLETA, [1, 9]), _cuerpo(FRESCA, [1, 3]))
    assert _ids(foso.pull_osm_transporte()) == ["node/1", "node/3"]
    assert llamadas == foso._OVERPASS_ENDPOINTS
    assert _resultados(foso) == ["FALLO", "DESFASADO", "ACEPTADO"]
    assert foso.ULTIMA_OSM == {"endpoint": foso._OVERPASS_ENDPOINTS[2], "snapshot_at": "2026-10-04T06:00:00+00:00"}


def test_F6_todos_desfasados_osm_caida_sin_snapshot_vigente(foso, monkeypatch):
    monkeypatch.setattr(foso, "PISO_OSM", PISO)
    _espejos(foso, monkeypatch, *[_cuerpo(OBSOLETA, [1])] * 3)
    r = foso.obtener("osm")
    assert (r.estado, r.fase, r.clase) == ("caida", "obtencion", "SinSnapshotVigente"), "CAÍDA, nunca ROTA"
    assert r.filas is None and r.snapshot_at is None and r.endpoint is None
    assert [i["resultado"] for i in r.observacion["frescura"]["intentos"]] == ["DESFASADO"] * 3


def test_F7_todos_fallan_por_http_comportamiento_de_siempre(foso, monkeypatch):
    monkeypatch.setattr(foso, "PISO_OSM", PISO)
    _espejos(foso, monkeypatch, E504, E504, E504)
    r = foso.obtener("osm")
    assert (r.estado, r.fase, r.clase, r.error) == ("caida", "obtencion", "SinRespuesta", "ningún endpoint respondió")
    assert _resultados(foso) == ["FALLO"] * 3 and "clase" not in foso.FRESCURA_OSM


@pytest.mark.parametrize("cuerpo", [_cuerpo(None, [1], osm3s=False), _cuerpo(None, [1])],
                         ids=["sin_osm3s", "timestamp_null"])
def test_F8_instantanea_nula_espejo_inverificable(foso, monkeypatch, cuerpo):
    monkeypatch.setattr(foso, "PISO_OSM", PISO)
    llamadas = _espejos(foso, monkeypatch, cuerpo, _cuerpo(FRESCA, [3]), E504)
    assert _ids(foso.pull_osm_transporte()) == ["node/3"], "el inverificable no se usa: se acepta el siguiente"
    assert llamadas == foso._OVERPASS_ENDPOINTS[:2] and _resultados(foso) == ["INVERIFICABLE", "ACEPTADO"]


@pytest.mark.parametrize("instante", ["2026-13-45T99:99:99Z", "ayer", "2026-10-02T14:53:35", "", 12345,
                                      "2026-10-0214:53:35Z"],
                         ids=["fecha_imposible", "texto", "sin_zona", "vacio", "numero", "sin_separador"])
def test_F9_instantanea_malformada_espejo_inverificable(foso, monkeypatch, instante):
    monkeypatch.setattr(foso, "PISO_OSM", PISO)
    _espejos(foso, monkeypatch, _cuerpo(instante, [1]), _cuerpo(FRESCA, [3]), E504)
    assert _ids(foso.pull_osm_transporte()) == ["node/3"]
    assert _resultados(foso) == ["INVERIFICABLE", "ACEPTADO"]


def test_sin_historia_vale_cualquier_instantanea_verificable_pero_no_una_inverificable(foso, monkeypatch):
    monkeypatch.setattr(foso, "PISO_OSM", None)
    _espejos(foso, monkeypatch, _cuerpo(None, [1], osm3s=False), _cuerpo(OBSOLETA, [9]), E504)
    assert _ids(foso.pull_osm_transporte()) == ["node/9"], "sin piso, lo verificable se acepta (ciudad nueva)"
    assert _resultados(foso) == ["INVERIFICABLE", "ACEPTADO"] and foso.FRESCURA_OSM["piso"] is None


def test_piso_ilegible_no_se_pide_ningun_espejo(foso, monkeypatch):
    monkeypatch.setattr(foso, "PISO_OSM", foso.PisoFrescuraIlegible("OperationalError"))
    llamadas = _espejos(foso, monkeypatch, _cuerpo(FRESCA, [1]), _cuerpo(FRESCA, [1]), _cuerpo(FRESCA, [1]))
    r = foso.obtener("osm")
    assert llamadas == [], "sin piso no hay con qué juzgar: ni una petición"
    assert (r.estado, r.fase, r.clase) == ("caida", "obtencion", "PisoFrescuraIlegible")


# ══════════════════════════════════════ PURA: el piso (F10) ═════════════════════════════════════════════════════
class _Escalar:
    def __init__(self, v):
        self.v = v

    def scalar(self):
        return self.v


class _MotorPiso:
    """Un motor que solo sabe responder la lectura del piso; registra lo que se le pidió."""

    def __init__(self, valor=None, falla=None):
        self.valor, self.falla, self.sentencias = valor, falla, []

    def connect(self):
        motor = self

        class _C:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql, params=None):
                motor.sentencias.append((" ".join(str(sql).split()), params))
                if motor.falla:
                    raise motor.falla
                return _Escalar(motor.valor)
        return _C()


def test_F10_el_piso_es_el_maximo_historico_aceptado_por_ciudad_y_lector(foso):
    sql = " ".join(str(foso.PISO_FRESCURA_OSM_SQL).split())
    assert sql.startswith("SELECT max(source_snapshot_at) FROM poi_ingestion_run WHERE")
    for filtro in ("source_provider = 'osm'", "ciudad = :c", "status = 'ok'", "reader_contract = :lector",
                   "source_snapshot_at IS NOT NULL"):
        assert filtro in sql, filtro
    assert "ORDER BY" not in sql and "LIMIT" not in sql and "completed_at" not in sql, \
        "el MÁXIMO histórico, nunca «la última corrida»: una desfasada que se coló no baja el piso"
    motor = _MotorPiso(PISO)
    assert foso.leer_piso_frescura_osm(motor) == PISO
    assert motor.sentencias[0][0] == "SET TRANSACTION READ ONLY", "lectura EXPLÍCITA de solo lectura"
    assert motor.sentencias[1][1] == {"c": "quito", "lector": "osm_overpass_nwr_body_center_v1"}


@pytest.mark.parametrize("motor, esperado", [
    (_MotorPiso(None), None),
    (_MotorPiso(datetime(2026, 10, 2, 14, 53, 35)), "PisoFrescuraIlegible"),     # sin zona: no se supone UTC
    (_MotorPiso("2026-10-02T14:53:35Z"), "PisoFrescuraIlegible"),                 # no es un instante
    (_MotorPiso(falla=RuntimeError("relation poi_ingestion_run does not exist (host db.secreto)")),
     "PisoFrescuraIlegible"),
], ids=["sin_historia", "sin_zona", "texto", "base_falla"])
def test_F10b_piso_ausente_o_ilegible(foso, motor, esperado):
    piso = foso.leer_piso_frescura_osm(motor)
    if esperado is None:
        assert piso is None
    else:
        assert isinstance(piso, foso.PisoFrescuraIlegible) and piso.clase == esperado
        assert "db.secreto" not in str(piso), "solo la clase del error: nunca el texto (arrastra host o SQL)"


# ══════════════════════════════════════ ORQUESTACIÓN: `main()` con el motor falso ═══════════════════════════════
def test_el_piso_se_lee_antes_de_pedir_ningun_espejo_y_en_su_propia_transaccion_de_lectura(foso, monkeypatch):
    _inyecta_lector(monkeypatch, foso, lambda: [_ov(foso, "ov-a")])
    motor = _motor(monkeypatch, foso, previos={"overture": 1, "osm": 1})
    orden = []
    real = foso.leer_piso_frescura_osm
    monkeypatch.setattr(foso, "leer_piso_frescura_osm", lambda eng: orden.append("piso") or real(eng))
    llamadas = _espejos(foso, monkeypatch, _cuerpo(FRESCA, [1]), E504, E504)
    _post = foso.requests.post
    monkeypatch.setattr(foso.requests, "post", lambda url, *a, **k: orden.append("espejo") or _post(url, *a, **k))
    assert _corre(foso) == 0
    assert orden == ["piso", "espejo"] and llamadas == foso._OVERPASS_ENDPOINTS[:1]
    t0 = motor.transacciones[0]
    assert t0["tipo"] == "connect" and [s for s, _ in t0["sentencias"]][0] == "SET TRANSACTION READ ONLY"
    assert t0["sentencias"][1][0].startswith("SELECT max(source_snapshot_at) FROM poi_ingestion_run")
    assert not [s for s, _ in t0["sentencias"] if not s.startswith(("SET TRANSACTION READ ONLY", "SELECT"))], \
        "la lectura del piso no escribe nada"


def test_F6_main_todos_desfasados_0_escrituras_0_cierres_osm_y_overture_sigue(foso, monkeypatch, tmp_path):
    _inyecta_lector(monkeypatch, foso, lambda: [_ov(foso, "ov-a")])
    motor = _motor(monkeypatch, foso, previos={"overture": 1, "osm": 3}, cierres={"osm": 3})
    monkeypatch.setattr(foso, "leer_piso_frescura_osm", lambda eng: PISO)
    _espejos(foso, monkeypatch, *[_cuerpo(OBSOLETA, [1, 9])] * 3)
    assert _corre(foso) == 2, "OSM CAÍDA → reintentable (código 2), nunca ROTA (1)"
    assert motor.ejecutadas(UPSERT_OSM) == [] and motor.ejecutadas(CIERRA_OSM) == [], "0 escrituras y 0 cierres OSM"
    assert motor.ejecutadas(UPSERT_OV), "F11: Overture se escribe igual, independiente"
    corridas = {p["source_provider"]: p for _, _, p in motor.ejecutadas(CORRIDA)}
    o = corridas["osm"]
    assert (o["status"], o["error_class"], o["error_phase"], o["rows_written"], o["rows_closed"], o["source_snapshot_at"],
            o["source_endpoint"]) == ("caida", "SinSnapshotVigente", "obtencion", None, None, None, None)
    assert corridas["overture"]["status"] == "ok"
    f = _fuentes(_estado(tmp_path))
    assert [i["resultado"] for i in f["osm"]["observacion"]["frescura"]["intentos"]] == ["DESFASADO"] * 3


def test_main_piso_ilegible_osm_caida_sin_red_y_overture_sigue(foso, monkeypatch, tmp_path):
    _inyecta_lector(monkeypatch, foso, lambda: [_ov(foso, "ov-a")])
    motor = _motor(monkeypatch, foso, previos={"overture": 1, "osm": 3}, falla_en="max(source_snapshot_at)")
    llamadas = _espejos(foso, monkeypatch, _cuerpo(FRESCA, [1]), _cuerpo(FRESCA, [1]), _cuerpo(FRESCA, [1]))
    assert _corre(foso) == 2
    assert llamadas == [], "sin piso legible no se pide ningún espejo"
    assert motor.ejecutadas(UPSERT_OSM) == [] and motor.ejecutadas(CIERRA_OSM) == []
    assert motor.ejecutadas(UPSERT_OV)
    o = {p["source_provider"]: p for _, _, p in motor.ejecutadas(CORRIDA)}["osm"]
    assert (o["status"], o["error_class"]) == ("caida", "PisoFrescuraIlegible")
    assert "db.secreto" not in (tmp_path / "estado.json").read_text(encoding="utf-8")


def test_REGRESION_D_OSM_1_el_espejo_desfasado_no_cierra_ni_reabre(foso, monkeypatch):
    """El fixture EXACTO de D-OSM-1: piso 2026-10-02 14:53:35Z (R4) y kumi con 2026-07-15 15:22:01Z.
    En la capa: node/1, node/2, node/3 activos y node/9 CERRADO (cerrado por ausencia antes).
    kumi (desfasado) trae node/1, node/2 y node/9: con el escritor viejo, node/3 se CERRABA y node/9 se REABRÍA.
    private.coffee (fresco) trae node/1, node/2 y node/3: es el que se acepta."""
    _inyecta_lector(monkeypatch, foso, lambda: [_ov(foso, "ov-a")])
    motor = _motor(monkeypatch, foso, previos={"overture": 1, "osm": 3}, cierres={"osm": 0})
    monkeypatch.setattr(foso, "leer_piso_frescura_osm", lambda eng: PISO)
    llamadas = _espejos(foso, monkeypatch, E504, _cuerpo(OBSOLETA, [1, 2, 9]), _cuerpo(FRESCA, [1, 2, 3]))
    assert _corre(foso) == 0
    assert llamadas == foso._OVERPASS_ENDPOINTS, "el espejo siguiente SÍ se intentó"
    [(_, _, escritas)] = motor.ejecutadas(UPSERT_OSM)
    assert sorted(p["osm_id"] for p in escritas) == ["node/1", "node/2", "node/3"]
    assert "node/9" not in {p["osm_id"] for p in escritas}, "0 reaperturas falsas (node/9 sigue cerrado)"
    [(_, _, cierre)] = motor.ejecutadas(CIERRA_OSM)
    assert "node/3" in cierre["ids"], "0 cierres falsos: node/3 está en la instantánea aceptada"
    o = {p["source_provider"]: p for _, _, p in motor.ejecutadas(CORRIDA)}["osm"]
    assert (o["status"], o["source_endpoint"], o["source_snapshot_at"]) == (
        "ok", foso._OVERPASS_ENDPOINTS[2], "2026-10-04T06:00:00+00:00")
    assert [(i["resultado"], i.get("instantanea")) for i in foso.FRESCURA_OSM["intentos"]] == [
        ("FALLO", None), ("DESFASADO", "2026-07-15T15:22:01+00:00"), ("ACEPTADO", "2026-10-04T06:00:00+00:00")]


def _escritor_de_main(tmp_path):
    p = subprocess.run(["git", "show", f"{MAIN_R3}:scripts/foso_pois_spike.py"], cwd=RAIZ, capture_output=True)
    if p.returncode != 0:
        pytest.skip("sin historia git (clon superficial): no hay escritor de main con que comparar")
    ruta = tmp_path / "foso_main_r3.py"
    ruta.write_bytes(p.stdout)
    return ruta, p.stdout.decode("utf-8")


def test_REPRODUCCION_con_el_escritor_de_main_el_desfasado_se_aceptaba(tmp_path, monkeypatch):
    """El DEFECTO, reproducido con el código de `main` (87d4c5b4) y las mismas respuestas: aceptaba kumi."""
    ruta, _ = _escritor_de_main(tmp_path)
    spec = importlib.util.spec_from_file_location("foso_main_r3", ruta)
    viejo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(viejo)
    _espejos(viejo, monkeypatch, E504, _cuerpo(OBSOLETA, [1, 2, 9]), _cuerpo(FRESCA, [1, 2, 3]))
    filas = viejo.pull_osm_transporte()
    assert _ids(filas) == ["node/1", "node/2", "node/9"], "main aceptaba la instantánea de julio"
    assert viejo.ULTIMA_OSM == {"endpoint": viejo._OVERPASS_ENDPOINTS[1], "snapshot_at": "2026-07-15T15:22:01+00:00"}


# ══════════════════════════════════════ AISLAMIENTO (F11, F12) ══════════════════════════════════════════════════
def _nodos(texto):
    return {n.name: n for n in ast.walk(ast.parse(texto)) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


def _asignaciones(texto):
    """Las asignaciones de primer nivel (también las anotadas: `TAXONOMIA_V1: dict[...] = {...}`)."""
    out = {}
    for n in ast.parse(texto).body:
        if isinstance(n, ast.Assign):
            out.update({t.id: ast.unparse(n.value) for t in n.targets if isinstance(t, ast.Name)})
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.value is not None:
            out[n.target.id] = ast.unparse(n.value)
    return out


def test_F11_overture_no_cambia_ni_una_linea(tmp_path):
    _, base = _escritor_de_main(tmp_path)
    actual = (RAIZ / "scripts" / "foso_pois_spike.py").read_text(encoding="utf-8")
    fa, fb = _nodos(actual), _nodos(base)
    for nombre in ("pull_overture", "pull_overture_taxonomia", "_pull_overture_con_release", "overture_release",
                   "huella_esquema_overture", "_matriz_de_estado", "_decision", "_guarda_durabilidad",
                   "_guarda_cobertura", "escribir", "_invalidas", "_manifiesto", "registrar_fallo", "ResultadoFuente",
                   "clase_de_estado", "verificar_esquema_043"):
        assert ast.unparse(fa[nombre]) == ast.unparse(fb[nombre]), nombre
    aa, ab = _asignaciones(actual), _asignaciones(base)
    for nombre in ("TAXONOMIA_V1", "HUELLA_TAXONOMIA_V1", "LECTOR_OVERTURE_TAXONOMIA", "NS_OVERTURE_TAXONOMIA",
                   "ESTADO_EN_CAPA_OVERTURE", "COBERTURA_PREVIA_OVERTURE", "CAIDA_MAX_COBERTURA", "UPSERT_OVERTURE",
                   "_ESCRIBEN", "_AVISAN", "CONF_MIN", "ESTADOS_OPERATIVOS_V1"):
        assert aa[nombre] == ab[nombre], nombre


def test_F12_la_guarda_de_volumen_del_50_por_ciento_no_cambia(foso, tmp_path, monkeypatch):
    _, base = _escritor_de_main(tmp_path)
    actual = (RAIZ / "scripts" / "foso_pois_spike.py").read_text(encoding="utf-8")
    aa, ab = _asignaciones(actual), _asignaciones(base)
    for nombre in ("UMBRAL_CAIDA", "CERRAR_OSM", "UPSERT_OSM", "_OVERPASS_ENDPOINTS", "LECTOR_OSM"):
        assert aa[nombre] == ab[nombre], nombre
    assert foso.UMBRAL_CAIDA == 0.5


def test_F12b_aceptada_pero_parcial_la_guarda_del_50_por_ciento_sigue_sin_cerrar(foso, monkeypatch):
    _inyecta_lector(monkeypatch, foso, lambda: [_ov(foso, "ov-a")])
    motor = _motor(monkeypatch, foso, previos={"overture": 1, "osm": 10}, cierres={"osm": 9})
    monkeypatch.setattr(foso, "leer_piso_frescura_osm", lambda eng: PISO)
    _espejos(foso, monkeypatch, _cuerpo(FRESCA, [1, 2]), E504, E504)
    assert _corre(foso) == 0
    assert motor.ejecutadas(UPSERT_OSM) and motor.ejecutadas(CIERRA_OSM) == [], "2 < 10·50 %: respuesta parcial"


def test_el_lector_osm_solo_cambia_en_la_guarda(tmp_path):
    """`pull_osm_transporte`: la consulta y el mapeo de cada elemento (etiqueta → categoría) idénticos a `main`."""
    _, base = _escritor_de_main(tmp_path)
    actual = (RAIZ / "scripts" / "foso_pois_spike.py").read_text(encoding="utf-8")
    fa, fb = _nodos(actual)["pull_osm_transporte"], _nodos(base)["pull_osm_transporte"]

    def partes(f):
        consulta = next(ast.unparse(n) for n in f.body if isinstance(n, ast.Assign)
                        and getattr(n.targets[0], "id", None) == "query")
        mapeo = next(ast.unparse(n) for n in f.body if isinstance(n, ast.For) and ast.unparse(n.iter) == "elems")
        return consulta, mapeo
    assert partes(fa) == partes(fb)


# ══════════════════════════════════════ POSTGIS (local): la 043 REAL ════════════════════════════════════════════
def _corrida_osm(esq, snapshot, completed, status="ok", lector="osm_overpass_nwr_body_center_v1", ciudad="quito"):
    import uuid

    import psycopg
    ok = status == "ok"
    with psycopg.connect(esq["conninfo"], autocommit=True) as c:
        c.execute(f"SET search_path TO {esq['esquema']}, public")
        c.execute("""INSERT INTO poi_ingestion_run (id, source_provider, ciudad, status, reader_contract,
                         source_snapshot_at, source_endpoint, code_sha, started_at, fetched_at, completed_at,
                         rows_fetched, rows_valid, rows_written, rows_closed, error_class, error_phase)
                     VALUES (%s, 'osm', %s, %s, %s, %s, %s, %s, %s::timestamptz - interval '2 minutes',
                             %s, %s, %s, %s, %s, %s, %s, %s)""",
                  (str(uuid.uuid4()), ciudad, status, lector, snapshot,
                   "https://overpass-api.de/api/interpreter" if ok else None, "0" * 40, completed,
                   completed if ok else None, completed, 3 if ok else None, 3 if ok else None, 3 if ok else None,
                   0 if ok else None, None if ok else "SinRespuesta", None if ok else "obtencion"))


def _piso_pg(foso, esq):
    from sqlalchemy.pool import NullPool
    eng = foso.create_engine(esq["url"], poolclass=NullPool, connect_args=foso.db_tls.kwargs_psycopg(esq["url"]))
    try:
        return foso.leer_piso_frescura_osm(eng)
    finally:
        eng.dispose()


@pg
def test_PG_F10_el_piso_es_el_maximo_historico_no_la_ultima_corrida(foso, esquema_pg):
    assert _piso_pg(foso, esquema_pg) is None, "sin corridas OSM aceptadas: sin historia"
    _corrida_osm(esquema_pg, "2026-10-02 14:53:35+00", "2026-10-02 14:54:57+00")           # R4: el máximo
    _corrida_osm(esquema_pg, "2026-07-15 15:22:01+00", "2026-10-03 15:29:48+00")           # la desfasada, POSTERIOR
    _corrida_osm(esquema_pg, None, "2026-10-04 00:00:00+00", status="caida")               # caída: no cuenta
    _corrida_osm(esquema_pg, "2026-12-01 00:00:00+00", "2026-12-01 00:01:00+00", ciudad="puebla")       # otra ciudad
    _corrida_osm(esquema_pg, "2026-11-01 00:00:00+00", "2026-11-01 00:01:00+00", lector="osm_otro_v2")  # otro lector
    assert _piso_pg(foso, esquema_pg) == PISO


def _escribe_osm_cerrada(esq, osm_id):
    import psycopg
    with psycopg.connect(esq["conninfo"], autocommit=True) as c:
        c.execute(f"SET search_path TO {esq['esquema']}, public")
        c.execute("""INSERT INTO pois_propios (nombre, categoria, categoria_overture, geom, fuente, osm_id, operativo, ciudad,
                                               actualizado_en)
                     VALUES ('OSM cerrado', 'transporte', 'parada_bus', ST_SetSRID(ST_MakePoint(-78.49,-0.19),4326),
                             'osm', %s, false, 'quito', '2026-09-22 14:30:03+00')""", (osm_id,))


def _regresion_pg(m, esq, monkeypatch):
    monkeypatch.setattr(m, "SYNC_URL", esq["url"])
    _corrida_osm(esq, "2026-10-02 14:53:35+00", "2026-10-02 14:54:57+00")
    _escribe_osm_cerrada(esq, "node/9")
    _inyecta_lector(monkeypatch, m, lambda: [_ov(m, "ov-a"), _ov(m, "ov-b")])
    _espejos(m, monkeypatch, E504, _cuerpo(OBSOLETA, [1, 2, 9]), _cuerpo(FRESCA, [1, 2, 3]))
    return _corre(m)


@pg
def test_PG_REGRESION_D_OSM_1_contra_la_043_real(foso, esquema_pg, monkeypatch):
    assert _regresion_pg(foso, esquema_pg, monkeypatch) == 0
    d = _foto(esquema_pg)
    assert d["node/3"]["operativo"] is True, "0 cierres falsos"
    assert d["node/9"]["operativo"] is False and d["node/9"]["tocada"] is False, "0 reaperturas falsas: ni tocada"
    import psycopg
    with psycopg.connect(esquema_pg["conninfo"]) as c:
        c.execute(f"SET search_path TO {esquema_pg['esquema']}, public")
        ult = c.execute("""SELECT status, source_endpoint, source_snapshot_at = %s::timestamptz, rows_closed
                           FROM poi_ingestion_run WHERE source_provider = 'osm' ORDER BY completed_at DESC LIMIT 1""",
                        (FRESCA,)).fetchone()
    assert ult == ("ok", foso._OVERPASS_ENDPOINTS[2], True, 0)
    assert _piso_pg(foso, esquema_pg) == datetime(2026, 10, 4, 6, 0, tzinfo=timezone.utc), "el piso SUBE con lo aceptado"


@pg
def test_PG_REPRODUCCION_con_el_escritor_de_main_cerraba_y_reabria(foso, esquema_pg, monkeypatch, tmp_path):
    """El defecto contra la 043 REAL: el escritor de `main` acepta kumi → cierra node/3 y reabre node/9. (El fixture
    `foso` deja el entorno de la corrida: SHA, argv, estado; los atributos del módulo viejo se fijan aquí.)"""
    ruta, _ = _escritor_de_main(tmp_path)
    spec = importlib.util.spec_from_file_location("foso_main_r3_pg", ruta)
    viejo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(viejo)
    monkeypatch.setenv("REFRESCO_POIS_ESTADO", str(tmp_path / "estado_viejo.json"))
    monkeypatch.setattr(viejo, "avisar_ops", lambda asunto, detalle: True)
    monkeypatch.setattr(viejo, "overture_release", lambda: "2026-09-23.1")
    monkeypatch.setattr(viejo, "huella_esquema_overture", lambda glob: "0" * 64)
    assert _regresion_pg(viejo, esquema_pg, monkeypatch) == 0
    d = _foto(esquema_pg)
    assert d["node/3"]["operativo"] is False and d["node/9"]["operativo"] is True, "el defecto: cierre y reapertura falsos"
