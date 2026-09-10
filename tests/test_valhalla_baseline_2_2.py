# -*- coding: utf-8 -*-
"""PLAN04-2.2-R0B1C0 · línea base ejecutable de Valhalla, ANTES de extraer su I/O.

Este fichero no mueve nada. Congela lo que `app/isocronas.py` hace HOY para que, cuando su
costura HTTP salga a `app/place/providers/valhalla.py`, se pueda demostrar que no cambió
nada observable. Cada número de aquí se MIDIÓ primero contra el cuerpo de `dd025c3` y solo
después se escribió como aserción: ninguna expectativa sale del mandato.

LO QUE ESTE MÓDULO NO ES. No es un test de Valhalla: es un test de nuestro cliente. No
contacta el servicio real —ni siquiera el de localhost— y todos sus datos son sintéticos.
Las 78 isócronas que existen en producción son contexto histórico, no evidencia de esta
unidad; no se leen, no se copian y no aparecen en ningún fixture.

POR QUÉ HACE FALTA UN BASELINE ANTES DEL CORTE. `app/isocronas.py` es el único módulo del
Place Graph que mezcla tres cosas —llamada a un tercero, persistencia y una consulta de
negocio— y hasta hoy **no tenía ni una sola prueba**. Mover su I/O sin esto sería mover a
ciegas: nada diría si la extracción convierte una consulta en dos requests, o una lectura
en una escritura de más.

SECCIONES
  (A) tripwire de red, con control negativo
  (B) el mapa del módulo: qué es I/O, qué es parseo, qué es persistencia, qué es negocio
  (C) el baseline HTTP: método, URL, payload, cliente, nº de requests
  (D) la matriz de degradación: doce formas de fallar, todas medidas
  (E) proveedor vs persistencia: quién toca la red y quién toca la base
  (F) `buscar_por_ancla_tiempo` y el flujo cache-then-generate que SÍ existe
  (G) el seam: dónde se define, quién lo importa y dónde hay que parchear
"""
from __future__ import annotations

import ast
import asyncio
import json
import socket
import types
from pathlib import Path

import httpx
import pytest

import app.isocronas as iso
import app.routers.assets as assets
import app.rutas as rutas
from app.config import settings

_APP = Path(__file__).resolve().parents[1] / "app"
_FICHERO = _APP / "isocronas.py"


# ══ (A) Tripwire de red ══════════════════════════════════════════════════════════════
# Hereda de `BaseException`, y no es un detalle: `isocrona` envuelve TODA su llamada en un
# `except Exception` que devuelve `None`. Un tripwire que heredara de `Exception` sería
# absorbido por ese `except` y esta suite podría salir a Internet informando "None" como si
# fuera una degradación normal. Es exactamente lo que le pasó al de Overpass en R0B1B.
# Loopback vivo a propósito: en Windows `asyncio.run` monta su self-pipe por 127.0.0.1.
_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}


class RedProhibida(BaseException):
    pass


def _es_loopback(destino) -> bool:
    if isinstance(destino, (tuple, list)) and destino:
        return str(destino[0]) in _LOOPBACK
    d = destino.decode() if isinstance(destino, bytes) else str(destino)
    return d in _LOOPBACK


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    originales = {"getaddrinfo": socket.getaddrinfo,
                  "create_connection": socket.create_connection,
                  "connect": socket.socket.connect,
                  "connect_ex": socket.socket.connect_ex}

    def prohibido(nombre):
        def _barrera(*args, **kwargs):
            destino = (args[1] if nombre in ("connect", "connect_ex") and len(args) > 1
                       else (args[0] if args else None))
            if _es_loopback(destino):
                return originales[nombre](*args, **kwargs)
            raise RedProhibida(
                f"salida externa a {destino!r} desde el baseline de Valhalla: algún doble "
                f"dejó de morder y se intentó una llamada real.")
        return _barrera

    monkeypatch.setattr(socket, "getaddrinfo", prohibido("getaddrinfo"))
    monkeypatch.setattr(socket, "create_connection", prohibido("create_connection"))
    monkeypatch.setattr(socket.socket, "connect", prohibido("connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", prohibido("connect_ex"))


def test_A1_el_tripwire_corta_la_salida_externa():
    """El control negativo. Sin esto, la barrera podría no estar haciendo nada."""
    with pytest.raises(RedProhibida):
        socket.getaddrinfo("203.0.113.1", 8002)      # TEST-NET-3: no existe, no responde


def test_A2_el_tripwire_deja_vivo_el_loopback():
    """Contrapeso: cortar loopback rompería `asyncio.run` y ninguna prueba correría."""
    async def _nada():
        return 42
    assert asyncio.run(_nada()) == 42


def test_A3_el_tripwire_NO_puede_ser_absorbido_por_el_except_del_modulo(monkeypatch):
    """La razón de heredar de `BaseException`, demostrada sobre el código real.

    Se deja a `isocrona` salir de verdad contra un host externo. Si `RedProhibida` fuera
    una `Exception`, el `except Exception` de la línea 51 la convertiría en `None` y esta
    prueba pasaría creyendo que midió una degradación — habiendo intentado una conexión.
    """
    monkeypatch.setattr(settings, "valhalla_url", "http://valhalla.invalido.example:8002")
    with pytest.raises(RedProhibida):
        asyncio.run(iso.isocrona(-0.18, -78.48))


# ══ Dobles sintéticos ════════════════════════════════════════════════════════════════
# Todo dato de este fichero es inventado. Nada procede de producción (§12 del mandato).
def _fc(*contornos):
    """Un FeatureCollection sintético con los contornos pedidos."""
    return {"features": [{"properties": {"contour": m},
                          "geometry": {"type": "Polygon", "coordinates": [[[float(m), 0.0]]]}}
                         for m in contornos]}


class _Espia:
    """Doble de `httpx.AsyncClient` que registra lo que recibe y devuelve lo que se le diga."""

    registro: list[dict] = []
    respuesta: object = None
    excepcion: BaseException | None = None
    status: int = 200
    crudo: str | None = None                 # si no es None, `.json()` revienta

    def __init__(self, **kw):
        type(self).registro.append({"evento": "cliente", **kw})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kw):
        type(self).registro.append({"evento": "post", "url": url, **kw})
        if type(self).excepcion is not None:
            raise type(self).excepcion
        espia = type(self)

        class _Resp:
            status_code = espia.status

            def raise_for_status(self):
                if espia.status >= 400:
                    raise httpx.HTTPStatusError(str(espia.status), request=None, response=None)

            def json(self):
                if espia.crudo is not None:
                    raise json.JSONDecodeError("no es json", espia.crudo, 0)
                return espia.respuesta
        return _Resp()

    @classmethod
    def arma(cls, monkeypatch, respuesta=None, excepcion=None, status=200, crudo=None):
        cls.registro, cls.respuesta = [], respuesta
        cls.excepcion, cls.status, cls.crudo = excepcion, status, crudo
        # Se sustituye el NOMBRE `httpx` dentro de `app.isocronas`, no el atributo del
        # módulo httpx compartido. La primera versión hacía lo segundo y rompía cosas muy
        # lejos: `app.agent.graph` construye su cliente de Anthropic al importarse y le
        # pasa un httpx, así que el doble viajaba hasta ahí. Un doble tiene que llegar
        # exactamente hasta donde llega el nombre que sustituye.
        monkeypatch.setattr(iso, "httpx", types.SimpleNamespace(AsyncClient=cls))
        return cls

    @classmethod
    def posts(cls):
        return [e for e in cls.registro if e["evento"] == "post"]


class _Conn:
    """Doble de conexión: cuenta ejecuciones, commits y rollbacks. No hay base de por medio."""

    def __init__(self, filas=()):
        self.sql: list[str] = []
        self.filas = list(filas)
        self.commits = self.rollbacks = 0

    async def execute(self, stmt, params=None):
        self.sql.append(str(stmt).strip().split("\n")[0])
        filas = self.filas

        class _R:
            def mappings(self):
                class _M:
                    def all(self):
                        return filas
                return _M()
        return _R()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    @property
    def escrituras(self):
        return [s for s in self.sql if s.upper().startswith("INSERT")]

    @property
    def lecturas(self):
        return [s for s in self.sql if s.upper().startswith(("SELECT", "WITH"))]


# ══ (B) El mapa del módulo ═══════════════════════════════════════════════════════════
def _arbol():
    return ast.parse(_FICHERO.read_text(encoding="utf-8"))


def _fuente_de(nombre: str) -> str:
    for n in _arbol().body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nombre:
            return ast.get_source_segment(_FICHERO.read_text(encoding="utf-8"), n) or ""
    raise AssertionError(f"{nombre} no está definido en {_FICHERO.name}")


def test_B1_el_modulo_tiene_exactamente_los_simbolos_esperados():
    """Si aparece uno nuevo, el mapa de abajo deja de describir el fichero y hay que
    reclasificarlo antes de mover nada."""
    encontrados = set()
    for n in _arbol().body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            encontrados.add(n.name)
        elif isinstance(n, ast.Assign):
            encontrados |= {t.id for t in n.targets if isinstance(t, ast.Name)}
    assert encontrados == {
        "logger", "_TIMEOUT", "_CONTORNOS_DEFECTO",      # configuración
        "isocrona",                                       # I/O + parseo (MIXTA)
        "_UPSERT_ISOCRONA", "guardar_isocronas_inmueble",  # persistencia
        "_WEDGE_SQL", "buscar_por_ancla_tiempo",          # consulta de negocio
    }, sorted(encontrados)


def test_B2_solo_isocrona_hace_red():
    """`httpx` aparece en UNA sola función del módulo. Ésa es la costura extraíble."""
    con_red = [n.name for n in _arbol().body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and "httpx" in _fuente_de(n.name)]
    assert con_red == ["isocrona"]


def test_B3_solo_la_persistencia_y_el_negocio_tocan_la_base():
    """Y `isocrona` no está entre ellas: ni recibe conexión ni ejecuta SQL."""
    con_sql = [n.name for n in _arbol().body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and "conn.execute" in _fuente_de(n.name)]
    assert con_sql == ["guardar_isocronas_inmueble", "buscar_por_ancla_tiempo"]
    fuente = _fuente_de("isocrona")
    assert "conn" not in fuente and "execute" not in fuente
    # Estructuralmente imposible: no tiene por dónde recibir una conexión.
    assert "conn" not in iso.isocrona.__code__.co_varnames


def test_B4_isocrona_es_MIXTA_y_el_corte_esta_entre_el_try_y_el_bucle():
    """La costura mínima, dicha con precisión: dentro de `isocrona` conviven el I/O (el
    `try` con httpx) y el PARSEO de la respuesta (el bucle sobre `features`), que es puro.
    Una extracción honesta parte por ahí; llevarse el bucle al provider sería llevarse
    interpretación, no transporte."""
    fuente = _fuente_de("isocrona")
    assert "httpx.AsyncClient" in fuente and 'fc.get("features"' in fuente
    # El parseo no depende de httpx: opera sobre el dict ya decodificado.
    cuerpo = fuente.split("return None", 1)[1]
    assert "httpx" not in cuerpo and "features" in cuerpo


def test_B5_el_unico_POST_a_valhalla_del_repositorio_esta_aqui():
    """Si algún día aparece un segundo cliente de Valhalla, esta guarda lo delata antes de
    que la extracción cree dos verdades."""
    llamadas = [(p.name, i + 1)
                for p in _APP.rglob("*.py")
                for i, l in enumerate(p.read_text(encoding="utf-8").splitlines())
                if "isochrone" in l and ".post(" in l]
    assert llamadas == [("isocronas.py", 48)], llamadas
    # `app/models.py` tambien nombra `/isochrone`, pero en prosa. Se busca el SITIO DE
    # LLAMADA, no la mencion: una guarda por substring habria dado un falso positivo eterno.


# ══ (C) Baseline HTTP ════════════════════════════════════════════════════════════════
def test_C1_un_solo_request_POST_a_la_ruta_isochrone(monkeypatch):
    _Espia.arma(monkeypatch, respuesta=_fc(15, 30))
    monkeypatch.setattr(settings, "valhalla_url", "http://valhalla-sintetico:8002")
    asyncio.run(iso.isocrona(-0.18, -78.48))
    posts = _Espia.posts()
    assert len(posts) == 1, "UN request cubre todos los contornos; dos sería duplicar cuota"
    assert posts[0]["url"] == "http://valhalla-sintetico:8002/isochrone"


def test_C2_la_URL_se_concatena_sin_normalizar(monkeypatch):
    """Medido, no deseado: `f"{valhalla_url}/isochrone"` es concatenación directa, así que
    una barra final en la configuración produce `//isochrone`. Se congela como está — si
    algún día se normaliza, será un cambio de comportamiento y no cabe en una extracción."""
    _Espia.arma(monkeypatch, respuesta=_fc(15))
    monkeypatch.setattr(settings, "valhalla_url", "http://host:8002/")
    asyncio.run(iso.isocrona(-0.18, -78.48))
    assert _Espia.posts()[0]["url"] == "http://host:8002//isochrone"


def test_C3_el_payload_exacto(monkeypatch):
    _Espia.arma(monkeypatch, respuesta=_fc(15, 30))
    asyncio.run(iso.isocrona(-0.18, -78.48))
    enviado = _Espia.posts()[0]["json"]
    assert enviado == {
        "locations": [{"lat": -0.18, "lon": -78.48}],
        "costing": "pedestrian",
        "contours": [{"time": 15}, {"time": 30}],
        "polygons": True,
        "denoise": 0.5,
        "generalize": 50,
    }
    # Se manda como JSON, no como formulario, y SIN cabeceras propias.
    assert "data" not in _Espia.posts()[0] and "headers" not in _Espia.posts()[0]


def test_C4_los_minutos_del_llamador_mandan_y_se_vuelven_enteros(monkeypatch):
    _Espia.arma(monkeypatch, respuesta=_fc(7))
    asyncio.run(iso.isocrona(-0.18, -78.48, [7.9]))
    assert _Espia.posts()[0]["json"]["contours"] == [{"time": 7}], "int(), no round()"


def test_C5_el_contorno_por_defecto_es_15_y_30(monkeypatch):
    assert iso._CONTORNOS_DEFECTO == (15, 30)
    assert iso.isocrona.__defaults__ == ((15, 30),)
    _Espia.arma(monkeypatch, respuesta=_fc(15, 30))
    asyncio.run(iso.isocrona(-0.18, -78.48))
    assert _Espia.posts()[0]["json"]["contours"] == [{"time": 15}, {"time": 30}]


def test_C6_el_cliente_se_construye_con_timeout_20_y_verify_de_settings(monkeypatch):
    assert iso._TIMEOUT == 20.0
    _Espia.arma(monkeypatch, respuesta=_fc(15))
    monkeypatch.setattr(settings, "ssl_verify", "true")
    asyncio.run(iso.isocrona(-0.18, -78.48))
    assert _Espia.registro[0] == {"evento": "cliente", "verify": True, "timeout": 20.0}

    _Espia.arma(monkeypatch, respuesta=_fc(15))
    monkeypatch.setattr(settings, "ssl_verify", "false")
    asyncio.run(iso.isocrona(-0.18, -78.48))
    assert _Espia.registro[0]["verify"] is False


def test_C7_la_forma_minima_aceptada_y_el_valor_devuelto(monkeypatch):
    """Qué necesita una feature para sobrevivir: `geometry` no vacío y `properties.contour`
    convertible a número. El contorno se devuelve como INT redondeado."""
    _Espia.arma(monkeypatch, respuesta={"features": [
        {"properties": {"contour": 30.4}, "geometry": {"type": "Polygon", "coordinates": []}}]})
    assert asyncio.run(iso.isocrona(-0.18, -78.48)) == [
        {"minutos": 30, "geometry": {"type": "Polygon", "coordinates": []}}]


def test_C8_el_orden_de_salida_es_el_de_la_respuesta_NO_se_ordena(monkeypatch):
    """Medido y congelado, porque importa: `buscar_por_ancla_tiempo` toma `isos[0]`. Si
    algún día se ordenara por minutos, ese `[0]` cambiaría de significado sin avisar."""
    _Espia.arma(monkeypatch, respuesta=_fc(30, 15))
    assert [i["minutos"] for i in asyncio.run(iso.isocrona(-0.18, -78.48))] == [30, 15]


def test_C9_una_feature_buena_sobrevive_a_una_mala(monkeypatch):
    """Degradación parcial: se descarta la feature rota, no la respuesta entera."""
    _Espia.arma(monkeypatch, respuesta={"features": [
        {"properties": {"contour": 15}, "geometry": {"type": "Polygon"}},
        {"properties": {}, "geometry": None},
    ]})
    assert asyncio.run(iso.isocrona(-0.18, -78.48)) == [
        {"minutos": 15, "geometry": {"type": "Polygon"}}]


# ══ (D) Matriz de degradación ════════════════════════════════════════════════════════
# Doce formas de fallar, las doce medidas contra el cuerpo de `dd025c3`. TODAS devuelven
# `None` y NINGUNA propaga excepción: el contrato de este proveedor es uniforme, cosa que
# no puede decirse de los demás del Place Graph.
_DEGRADACION = [
    ("timeout", dict(excepcion=httpx.TimeoutException("timeout"))),
    ("error de conexión", dict(excepcion=httpx.ConnectError("sin conexión"))),
    ("HTTP 404", dict(respuesta=_fc(15), status=404)),
    ("HTTP 500", dict(respuesta=_fc(15), status=500)),
    ("JSON inválido", dict(crudo="<html>no soy json</html>")),
    ("JSON sin 'features'", dict(respuesta={})),
    ("'features' vacío", dict(respuesta={"features": []})),
    ("feature sin geometry", dict(respuesta={"features": [{"properties": {"contour": 15}}]})),
    ("feature sin contour", dict(respuesta={"features": [{"geometry": {"type": "Polygon"}}]})),
    ("contour no numérico", dict(respuesta={"features": [
        {"properties": {"contour": "quince"}, "geometry": {"type": "Polygon"}}]})),
    ("properties = None", dict(respuesta={"features": [
        {"properties": None, "geometry": {"type": "Polygon"}}]})),
    ("geometry = None", dict(respuesta={"features": [
        {"properties": {"contour": 15}, "geometry": None}]})),
]


@pytest.mark.parametrize("caso,kw", _DEGRADACION, ids=[c for c, _ in _DEGRADACION])
def test_D1_toda_degradacion_devuelve_None_y_nunca_revienta(caso, kw, monkeypatch):
    _Espia.arma(monkeypatch, **kw)
    assert asyncio.run(iso.isocrona(-0.18, -78.48)) is None, caso


def test_D2_la_degradacion_NO_es_silenciosa(monkeypatch, caplog):
    """Lo que distingue a este proveedor de `_nearest_categoria`: absorbe la excepción pero
    deja un WARNING con el tipo y el mensaje. Un fallo de Valhalla es visible para el
    operador; un fallo de Google Places, hoy, no."""
    _Espia.arma(monkeypatch, excepcion=httpx.ConnectError("sin conexión"))
    with caplog.at_level("WARNING", logger="app.isocronas"):
        assert asyncio.run(iso.isocrona(-0.18, -78.48)) is None
    assert any("ConnectError" in r.getMessage() for r in caplog.records), caplog.text
    assert "no respondió" in caplog.text


def test_D2b_el_NOMBRE_del_logger_es_app_isocronas():
    """Congelado aparte porque es la trampa del corte que viene.

    `logger = logging.getLogger(__name__)`, así que el nombre lo decide DÓNDE vive el
    módulo. Mover `isocrona` a `app/place/providers/valhalla.py` cambiaría la etiqueta de
    `app.isocronas` a `app.place.providers.valhalla` sin que ninguna otra prueba se
    inmutara — y cualquier filtro de logs del operador que apunte al nombre viejo dejaría
    de ver las caídas de Valhalla. No es un fallo: es una decisión que R0B1C1 tiene que
    tomar a la vista, no de rebote.
    """
    assert iso.logger.name == "app.isocronas"


def test_D3_los_fallos_de_RESPUESTA_no_registran_nada(monkeypatch, caplog):
    """La otra mitad, y es una asimetría real: si Valhalla contesta 200 con contenido
    inservible, el bucle descarta las features y se devuelve `None` SIN ningún registro.
    "Valhalla caído" se ve en los logs; "Valhalla respondió basura" no. Se congela como
    está y se reporta como deuda; corregirlo no cabe en una extracción."""
    _Espia.arma(monkeypatch, respuesta={"features": [{"properties": {}, "geometry": None}]})
    with caplog.at_level("WARNING", logger="app.isocronas"):
        assert asyncio.run(iso.isocrona(-0.18, -78.48)) is None
    assert caplog.text == "", "hoy no registra nada en este camino"


def test_D4_valhalla_url_vacio_degrada_sin_salir_a_la_red(monkeypatch):
    """Estado representable: la URL queda en `/isochrone`, httpx la rechaza por protocolo
    y el `except` la absorbe. Se usa el cliente REAL a propósito — el tripwire garantiza
    que si algún día esa URL vacía llegara a resolver, se vería."""
    monkeypatch.setattr(settings, "valhalla_url", "")
    assert asyncio.run(iso.isocrona(-0.18, -78.48)) is None


# ══ (E) Proveedor vs persistencia ════════════════════════════════════════════════════
def test_E1_isocrona_NO_toca_la_base(monkeypatch):
    """La condición que hace posible extraer solo el I/O: el proveedor no persiste nada."""
    _Espia.arma(monkeypatch, respuesta=_fc(15, 30))
    conn = _Conn()
    asyncio.run(iso.isocrona(-0.18, -78.48))
    assert conn.sql == [] and conn.commits == 0
    assert not hasattr(iso, "engine"), "el módulo ni siquiera importa un engine"


def test_E2_guardar_isocronas_inmueble_NO_hace_red(monkeypatch):
    """La condición simétrica: la persistencia no llama a Valhalla. El tripwire está
    armado, así que si lo intentara se vería."""
    _Espia.arma(monkeypatch, respuesta=_fc(15))
    conn = _Conn()
    n = asyncio.run(iso.guardar_isocronas_inmueble(
        conn, "activo-sintetico-1",
        [{"minutos": 15, "geometry": {"type": "Polygon"}},
         {"minutos": 30, "geometry": {"type": "Polygon"}}]))
    assert n == 2
    assert len(conn.escrituras) == 2, "un upsert POR contorno"
    assert _Espia.posts() == [], "cero llamadas a Valhalla"
    assert conn.commits == 0, "NO hace commit: la transacción es del llamador"


def test_E3_guardar_con_cero_features_no_ejecuta_nada():
    conn = _Conn()
    assert asyncio.run(iso.guardar_isocronas_inmueble(conn, "a-1", [])) == 0
    assert conn.sql == []


def test_E4_el_upsert_es_idempotente_por_activo_y_minutos():
    """Congelado porque el batch de los lunes depende de ello: reprocesar no duplica."""
    sql = str(iso._UPSERT_ISOCRONA)
    assert "ON CONFLICT (activo_id, minutos)" in sql
    assert "DO UPDATE SET geom = EXCLUDED.geom" in sql


# ══ (F) `buscar_por_ancla_tiempo` y el flujo que SÍ cachea ═══════════════════════════
def test_F1_buscar_por_ancla_tiempo_llama_a_isocrona_y_luego_lee(monkeypatch):
    """Orden congelado: PRIMERO Valhalla, DESPUÉS la base. Una extracción que lo invirtiera
    haría una consulta PostGIS inútil cada vez que Valhalla está caído."""
    _Espia.arma(monkeypatch, respuesta=_fc(30))
    conn = _Conn(filas=[{"id": "x", "direccion": "d", "metros_al_ancla": 10}])
    filas = asyncio.run(iso.buscar_por_ancla_tiempo(conn, -0.18, -78.48, 30))
    assert len(_Espia.posts()) == 1
    assert len(conn.lecturas) == 1 and conn.escrituras == []
    assert conn.commits == 0
    assert filas == [{"id": "x", "direccion": "d", "metros_al_ancla": 10}]


def test_F2_si_valhalla_no_responde_NO_se_consulta_la_base(monkeypatch):
    """El corto-circuito: cero lecturas. Es la propiedad que la extracción no puede
    perder — sin ella, cada caída de Valhalla costaría una query."""
    _Espia.arma(monkeypatch, respuesta={"features": []})
    conn = _Conn()
    assert asyncio.run(iso.buscar_por_ancla_tiempo(conn, -0.18, -78.48, 30)) is None
    assert len(_Espia.posts()) == 1 and conn.sql == []


def test_F3_pide_UN_solo_contorno_el_que_le_dan(monkeypatch):
    _Espia.arma(monkeypatch, respuesta=_fc(20))
    asyncio.run(iso.buscar_por_ancla_tiempo(_Conn(), -0.18, -78.48, 20))
    assert _Espia.posts()[0]["json"]["contours"] == [{"time": 20}]


def test_F4_NO_EXISTE_un_camino_que_responda_desde_lo_ya_persistido():
    """Hallazgo, y va en contra de lo que sugiere el docstring del módulo.

    `buscar_por_ancla_tiempo` SIEMPRE llama a Valhalla: no consulta `isocronas_inmueble` ni
    tiene rama de caché. Su SQL lee `activos_inmutables` con el polígono recién traído. El
    módulo dice "la cachea por inmueble", y es cierto —lo hace `guardar_isocronas_inmueble`—
    pero esta función no se beneficia de esa caché.

    Se congela el hecho, no la opinión: si mañana alguien añade el camino de caché, esta
    prueba se pone roja y obliga a decirlo en voz alta.
    """
    fuente = _fuente_de("buscar_por_ancla_tiempo")
    assert "isocronas_inmueble" not in fuente
    assert "isocrona(" in fuente and "if not isos" in fuente
    assert "isocronas_inmueble" not in str(iso._WEDGE_SQL)
    assert "activos_inmutables" in str(iso._WEDGE_SQL)


def test_F5_buscar_por_ancla_tiempo_no_tiene_NINGUN_consumidor():
    """El otro hallazgo. Ni `app/`, ni `tests/`, ni `scripts/` la llaman. Está escrita y
    conectada a nada. No se toca —esta unidad no borra código— pero conviene saberlo antes
    de decidir qué arrastra la extracción."""
    raiz = _APP.parent
    consumidores = [p.relative_to(raiz).as_posix()
                    for d in ("app", "tests", "scripts")
                    for p in (raiz / d).rglob("*.py")
                    if p != _FICHERO and p.name != Path(__file__).name
                    and "buscar_por_ancla_tiempo" in p.read_text(encoding="utf-8")]
    assert consumidores == [], f"ya no es código muerto: lo usan {consumidores}"


# ── El flujo cache-then-generate que SÍ existe, y vive en otro fichero ───────────────
# El mandato preguntaba por «el caso donde puede responder con información ya disponible».
# Ese camino existe, pero no en `isocronas.py`: está en `app/routers/assets.py`
# (`_isocronas_geo_cached`), que lee la caché y solo genera si está vacía. Es el flujo real
# de producción y el que una extracción podría romper en su conteo, así que se congela aquí
# —observándolo, sin modificar ese fichero, que está fuera del radio—.
def _cached(conn, lat=-0.18, lon=-78.48):
    return asyncio.run(assets._isocronas_geo_cached(conn, "activo-sintetico-1", lat, lon))


def test_F6_caso_A_cache_HIT_no_llama_a_valhalla(monkeypatch):
    _Espia.arma(monkeypatch, respuesta=_fc(15))
    conn = _Conn(filas=[{"minutos": 15, "geometry": {"type": "Polygon"}}])
    salida = _cached(conn)
    assert _Espia.posts() == [], "con caché no se gasta una llamada"
    assert len(conn.lecturas) == 1 and conn.escrituras == [] and conn.commits == 0
    assert salida == [{"minutos": 15, "geometry": {"type": "Polygon"}}]


def test_F7_caso_B_cache_MISS_genera_una_vez_y_persiste(monkeypatch):
    _Espia.arma(monkeypatch, respuesta=_fc(15, 30))
    conn = _Conn(filas=[])
    salida = _cached(conn)
    assert len(_Espia.posts()) == 1, "UNA llamada, no una por contorno"
    assert len(conn.lecturas) == 1 and len(conn.escrituras) == 2 and conn.commits == 1
    assert [s["minutos"] for s in salida] == [15, 30]


def test_F8_caso_C_MISS_con_valhalla_caido_no_escribe(monkeypatch):
    _Espia.arma(monkeypatch, excepcion=httpx.ConnectError("caído"))
    conn = _Conn(filas=[])
    assert _cached(conn) == []
    assert len(conn.lecturas) == 1 and conn.escrituras == [] and conn.commits == 0


def test_F9_caso_D_sin_coordenadas_lee_pero_no_llama(monkeypatch):
    _Espia.arma(monkeypatch, respuesta=_fc(15))
    conn = _Conn(filas=[])
    assert _cached(conn, lat=None, lon=None) == []
    assert len(conn.lecturas) == 1 and _Espia.posts() == []


# ══ (G) El seam ══════════════════════════════════════════════════════════════════════
def test_G1_donde_se_define_hoy():
    assert iso.isocrona.__module__ == "app.isocronas"
    assert iso.guardar_isocronas_inmueble.__module__ == "app.isocronas"
    assert iso.buscar_por_ancla_tiempo.__module__ == "app.isocronas"


def test_G2_rutas_importa_a_NIVEL_DE_MODULO_asi_que_se_parchea_en_rutas():
    fuente = (_APP / "rutas.py").read_text(encoding="utf-8")
    assert "from app.isocronas import isocrona" in fuente.split("def ")[0], (
        "el import de rutas.py está en la cabecera, no dentro de una función")
    assert hasattr(rutas, "isocrona") and rutas.isocrona is iso.isocrona


def test_G3_assets_importa_DIFERIDO_asi_que_se_parchea_en_app_isocronas():
    fuente = (_APP / "routers" / "assets.py").read_text(encoding="utf-8")
    assert "    from app.isocronas import guardar_isocronas_inmueble, isocrona" in fuente, (
        "el import de assets.py está DENTRO de la función, indentado")
    assert not hasattr(assets, "isocrona"), (
        "si esto existiera, el import habría dejado de ser diferido y el punto de parcheo "
        "se habría mudado")


def test_G4_parchear_rutas_isocrona_MUERDE(monkeypatch):
    """El seam de `rutas`, ejercitado. No toca la base: con `None` la función corta antes."""
    llamadas = []

    async def doble(lat, lon, minutos=None):
        llamadas.append((lat, lon, minutos))
        return None

    monkeypatch.setattr(rutas, "isocrona", doble)
    salida = asyncio.run(rutas._accion_isocrona(-0.18, -78.48, "isocrona 15 min"))
    assert llamadas == [(-0.18, -78.48, [15])]
    assert "no está disponible" in salida["texto"] and salida["acciones"] == []


def test_G5_parchear_app_isocronas_NO_alcanza_a_rutas(monkeypatch):
    """LA MITAD NEGATIVA. `rutas.isocrona is iso.isocrona` es cierto, y aun así reasignar el
    módulo de origen NO cambia lo que ejecuta `rutas`: ligó el objeto en su propio espacio
    de nombres al importar. Confundirlo da un doble que no muerde y una prueba que sale a
    la red — el mismo error que R0B0 documentó para `walk_score_para`."""
    llamadas = []

    async def doble(lat, lon, minutos=None):
        llamadas.append(1)
        return None

    monkeypatch.setattr(iso, "isocrona", doble)
    monkeypatch.setattr(rutas, "isocrona", lambda *a, **k: _nunca())

    async def _nunca():
        return None

    asyncio.run(rutas._accion_isocrona(-0.18, -78.48, "isocrona 15 min"))
    assert llamadas == [], "parchear el origen no puede afectar a rutas"


def test_G6_parchear_app_isocronas_SI_alcanza_a_assets(monkeypatch):
    """El caso opuesto y por qué la matriz de seams tiene dos filas: `assets` importa
    DIFERIDO, así que resuelve sobre `app.isocronas` en cada ejecución."""
    llamadas = []

    async def doble(lat, lon, minutos=(15, 30)):
        llamadas.append(1)
        return None

    monkeypatch.setattr(iso, "isocrona", doble)
    conn = _Conn(filas=[])
    assert _cached(conn) == []
    assert llamadas == [1], "el doble en el módulo de origen SÍ muerde en assets"


def test_G7_el_baseline_NO_puede_pasar_sin_ejecutar_isocrona(monkeypatch):
    """La guarda contra un baseline vacío. Si los dobles dejaran de registrar, o `isocrona`
    dejara de llamarse, este contador se quedaría en cero y todo lo de arriba mediría el
    aire. Es el control que R0B0 tuvo que añadir a posteriori; aquí nace con él."""
    _Espia.arma(monkeypatch, respuesta=_fc(15))
    asyncio.run(iso.isocrona(-0.18, -78.48))
    assert len(_Espia.posts()) == 1
    assert _Espia.posts()[0]["json"]["costing"] == "pedestrian"
