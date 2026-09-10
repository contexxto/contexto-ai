# -*- coding: utf-8 -*-
"""PLAN04-2.2-R0B2A · línea base de los DOS bloqueadores materiales de la auditoría de cierre.

`PLAN04-2.2-CLOSE-AUDIT` devolvió FAIL con dos bloqueadores, y este fichero los congela
ANTES de corregirlos. No mueve nada, no arregla nada: mide lo que hoy hacen y lo escribe.

BLOQUEADOR 1 — el segundo Google. `app/entorno.py` contiene una implementación viva de
`places:searchNearby` que llena el MISMO campo que produce el Place path
(`servicios_cercanos`), como respaldo, desde `app/routers/assets.py`. Misma capacidad, otra
política: radio 1200 contra 3000, `maxResultCount` 5 contra 8, ocho requests incondicionales
contra uno por hueco, y sin heurística de marca ancla.

BLOQUEADOR 2 — la capa propia a medias. Dos lecturas de `pois_vivos` siguen ejecutándose
desde `app/rutas.py` con su propio `engine.connect()`, fuera de `providers/propia.py`.

TODO ESTO PREEXISTE A 2.2. Se congela para poder moverlo después sin cambiar comportamiento,
no porque la extracción lo haya roto.

LO QUE ESTE FICHERO NO HACE. No corrige la política de `entorno_destacado` aunque contradiga
al foso (allí Google va PRIMERO; en el Place path va la capa propia primero). No toca
`app/entorno.py`, `app/rutas.py` ni `app/routers/assets.py`. Datos 100 % sintéticos, cero
contacto con Google real.
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

import app.entorno as entorno
import app.routers.assets as assets
import app.rutas as rutas
from app.config import settings

_APP = Path(__file__).resolve().parents[1] / "app"
_ENTORNO = _APP / "entorno.py"
_RUTAS = _APP / "rutas.py"


# ══ (A) Tripwire de red — y por qué éste tiene que ser distinto ══════════════════════
# En R0B1B y R0B1C0 bastó con heredar de `BaseException` para escapar de un
# `except Exception`. AQUÍ NO BASTA, y está medido: `_entorno_google` lanza sus ocho
# llamadas con `asyncio.gather(..., return_exceptions=True)`, que captura TAMBIÉN los
# `BaseException`. Con una barrera que solo lanza, las ocho tareas mueren, `gather` guarda
# las excepciones, el filtro `isinstance(r, dict)` las descarta y la función devuelve
# `None`; `entorno_destacado` cae entonces a OSM y la prueba pasa EN VERDE habiendo
# intentado ocho conexiones reales a Google.
#
# Por eso esta barrera DEJA RASTRO además de lanzar. Una excepción es tan fuerte como el
# `except` más laxo que haya entre ella y la prueba; un efecto de lado no lo absorbe nadie.
_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}
_INTENTOS: list[str] = []


class RedProhibida(BaseException):
    pass


def _es_loopback(destino) -> bool:
    if isinstance(destino, (tuple, list)) and destino:
        return str(destino[0]) in _LOOPBACK
    d = destino.decode() if isinstance(destino, bytes) else str(destino)
    return d in _LOOPBACK


def _consumir_intentos() -> list[str]:
    """Devuelve los intentos registrados y los limpia (para el control negativo)."""
    vistos = list(_INTENTOS)
    _INTENTOS.clear()
    return vistos


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    _INTENTOS.clear()
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
            _INTENTOS.append(f"{nombre}->{destino!r}")     # el rastro que nadie absorbe
            raise RedProhibida(f"salida externa a {destino!r}")
        return _barrera

    monkeypatch.setattr(socket, "getaddrinfo", prohibido("getaddrinfo"))
    monkeypatch.setattr(socket, "create_connection", prohibido("create_connection"))
    monkeypatch.setattr(socket.socket, "connect", prohibido("connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", prohibido("connect_ex"))
    yield
    assert _INTENTOS == [], (
        f"esta prueba intentó salir a la red y algún `except` se lo tragó: {_INTENTOS}")


def test_A1_el_tripwire_corta_y_DEJA_RASTRO():
    """Control negativo. Comprueba las dos mitades: que lanza y que registra."""
    with pytest.raises(RedProhibida):
        socket.getaddrinfo("203.0.113.1", 443)      # TEST-NET-3
    assert _consumir_intentos(), "la barrera no dejó rastro; sería absorbible en silencio"


def test_A2_el_tripwire_deja_vivo_el_loopback():
    async def _nada():
        return 42
    assert asyncio.run(_nada()) == 42


def test_A3_el_gather_del_segundo_Google_ABSORBE_hasta_un_BaseException():
    """El hallazgo que obligó a rediseñar la barrera, congelado como comportamiento.

    Se deja a `_entorno_google` salir de verdad. La excepción NO llega hasta aquí: la
    absorbe `asyncio.gather(..., return_exceptions=True)`. Lo único que delata el intento
    es el rastro. Si algún día esto empezara a propagar, este test se pondría rojo y habría
    que saberlo — no es un defecto que esta unidad corrija, es el motivo del diseño.
    """
    monkeypatch_url = "K"
    resultado = asyncio.run(entorno._entorno_google(-0.18, -78.48, monkeypatch_url))
    assert resultado is None, "hoy la absorbe y devuelve None"
    intentos = _consumir_intentos()
    assert len(intentos) >= 1, "se intentó salir a la red y ni siquiera quedó rastro"
    assert "places.googleapis.com" in intentos[0]


# ══ Dobles sintéticos ════════════════════════════════════════════════════════════════
def _lugares(*nombres):
    return {"places": [{"displayName": {"text": n},
                        "location": {"latitude": -0.18 + i / 1000, "longitude": -78.48}}
                       for i, n in enumerate(nombres)]}


class _EspiaHTTP:
    registro: list[dict] = []
    respuesta: object = None
    excepcion: BaseException | None = None
    status: int = 200
    crudo: str | None = None

    def __init__(self, **kw):
        type(self).registro.append({"evento": "cliente", **kw})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kw):
        type(self).registro.append({"evento": "post", "url": url, **kw})
        e = type(self)
        if e.excepcion is not None:
            raise e.excepcion

        class _Resp:
            def raise_for_status(self):
                if e.status >= 400:
                    raise httpx.HTTPStatusError(str(e.status), request=None, response=None)

            def json(self):
                if e.crudo is not None:
                    raise json.JSONDecodeError("no es json", e.crudo, 0)
                return e.respuesta
        return _Resp()

    @classmethod
    def arma(cls, monkeypatch, respuesta=None, excepcion=None, status=200, crudo=None):
        cls.registro, cls.respuesta = [], respuesta
        cls.excepcion, cls.status, cls.crudo = excepcion, status, crudo
        # Se sustituye el nombre `httpx` DENTRO de `app.entorno`, no el módulo compartido.
        monkeypatch.setattr(entorno, "httpx", types.SimpleNamespace(AsyncClient=cls))
        return cls

    @classmethod
    def posts(cls):
        return [e for e in cls.registro if e["evento"] == "post"]


class _Conn:
    def __init__(self, resultados, reg):
        self.resultados, self.reg, self.i = resultados, reg, 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, stmt, params=None):
        texto = str(stmt).strip()
        tabla = next((l.strip() for l in texto.split("\n") if "FROM" in l), texto[:40])
        self.reg["sql"].append(tabla)
        self.reg["params"].append(dict(params or {}))
        r = self.resultados[self.i] if self.i < len(self.resultados) else []
        self.i += 1

        class _R:
            def mappings(self):
                class _M:
                    def all(self):
                        return r
                return _M()

            def scalar(self):
                return r
        return _R()


class _Engine:
    """Doble de engine que CUENTA conexiones. La cuenta importa: `_contenido_isocrona`
    hace DOS queries dentro de UNA sola conexión, y separar una de las dos partiría eso."""

    def __init__(self, resultados, reg, revienta=False):
        self.resultados, self.reg, self.revienta = resultados, reg, revienta

    def connect(self):
        self.reg["connects"] += 1
        if self.revienta:
            raise OSError("la base no responde")
        return _Conn(self.resultados, self.reg)


def _con_db(monkeypatch, resultados, revienta=False):
    reg = {"connects": 0, "sql": [], "params": []}
    monkeypatch.setattr(rutas, "engine", _Engine(resultados, reg, revienta))
    return reg


# ══ (B) El mapa de los dos bloqueadores ══════════════════════════════════════════════
def _definidos(fichero: Path) -> set[str]:
    nombres = set()
    for n in ast.parse(fichero.read_text(encoding="utf-8")).body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nombres.add(n.name)
        elif isinstance(n, ast.Assign):
            nombres |= {t.id for t in n.targets if isinstance(t, ast.Name)}
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            # `_CATEGORIAS: list[dict] = [...]` es un AnnAssign, no un Assign. Olvidarlo
            # deja un símbolo declarado fuera del mapa sin que nada lo avise.
            nombres.add(n.target.id)
    return nombres


def test_B1_el_segundo_Google_sigue_donde_la_auditoria_lo_encontro():
    """Si algún día desaparece de aquí, este baseline deja de describir la realidad y hay
    que rehacerlo antes de mover nada."""
    en_entorno = _definidos(_ENTORNO)
    assert {"_google_nearest", "_entorno_google", "entorno_destacado",
            "extraer_entorno_osm", "_RADIO_M", "_TIMEOUT", "_CATEGORIAS"} <= en_entorno
    texto = _ENTORNO.read_text(encoding="utf-8")
    llamadas = [i + 1 for i, l in enumerate(texto.splitlines())
                if "places.googleapis.com" in l and ".post(" in l]
    assert len(llamadas) == 1, f"se esperaba UNA llamada a Places aquí, hay {llamadas}"


def test_B2_los_dos_SQL_residuales_siguen_en_rutas():
    en_rutas = _definidos(_RUTAS)
    assert {"_DENTRO_POIS_SQL", "_DENTRO_ACTIVOS_SQL", "_PANORAMA_TRANSPORTE_SQL",
            "_contenido_isocrona", "_panorama_transporte", "_frase_dentro"} <= en_rutas
    texto = _RUTAS.read_text(encoding="utf-8")
    assert texto.count("engine.connect()") == 2, "dos conexiones, ni una más"
    assert texto.count("FROM pois_vivos") == 2, "dos lecturas de la vista fuera del provider"


def test_B3_la_frontera_extraida_NO_conoce_a_ninguno_de_los_dos():
    """El contrapeso: lo que ya está detrás del seam no debe empezar a depender de esto."""
    for fichero in (_APP / "place" / "providers").glob("*.py"):
        fuente = fichero.read_text(encoding="utf-8")
        assert "places.googleapis.com" not in fuente or fichero.name == "google.py"
        assert "_entorno_google" not in fuente and "entorno_destacado" not in fuente
        assert "_DENTRO_POIS_SQL" not in fuente and "_PANORAMA_TRANSPORTE_SQL" not in fuente


# ══ (C) Baseline del segundo Google ══════════════════════════════════════════════════
def test_C1_ocho_requests_uno_por_categoria_en_UN_solo_cliente(monkeypatch):
    """La diferencia de coste más grande con el Place path: aquí se piden las OCHO
    categorías siempre, no solo los huecos."""
    _EspiaHTTP.arma(monkeypatch, respuesta=_lugares("X"))
    asyncio.run(entorno._entorno_google(-0.18, -78.48, "LLAVE"))
    posts = _EspiaHTTP.posts()
    assert len(posts) == 8 == len(entorno._CATEGORIAS)
    assert sum(1 for e in _EspiaHTTP.registro if e["evento"] == "cliente") == 1
    assert [p["json"]["includedTypes"] for p in posts] == [
        ["shopping_mall"], ["school"], ["hospital"], ["church"],
        ["police"], ["park"], ["supermarket"], ["pharmacy"]]


def test_C2_endpoint_metodo_headers_y_payload_exactos(monkeypatch):
    _EspiaHTTP.arma(monkeypatch, respuesta=_lugares("X"))
    asyncio.run(entorno._entorno_google(-0.18, -78.48, "LLAVE"))
    p = _EspiaHTTP.posts()[0]
    assert p["url"] == "https://places.googleapis.com/v1/places:searchNearby"
    assert p["headers"] == {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": "LLAVE",
        "X-Goog-FieldMask": "places.displayName,places.location",
    }
    assert p["json"] == {
        "includedTypes": ["shopping_mall"],
        "maxResultCount": 5,
        "rankPreference": "DISTANCE",
        "languageCode": "es",
        "locationRestriction": {
            "circle": {"center": {"latitude": -0.18, "longitude": -78.48}, "radius": 1200.0}},
    }


def test_C3_radio_plazo_y_tope_difieren_del_provider_extraido(monkeypatch):
    """El corazón del bloqueador: misma capacidad, política distinta. Se congelan LOS DOS
    lados para que la consolidación tenga que elegir a la vista, no por descuido."""
    import app.place.providers.google as prov
    assert entorno._RADIO_M == 1200 and entorno._TIMEOUT == 6.0
    assert 'radius": 3000.0' in (
        _APP / "place" / "providers" / "google.py").read_text(encoding="utf-8")
    assert prov._TIMEOUT == 5.0
    _EspiaHTTP.arma(monkeypatch, respuesta=_lugares("X"))
    asyncio.run(entorno._entorno_google(-0.18, -78.48, "K"))
    assert _EspiaHTTP.registro[0] == {"evento": "cliente", "verify": True, "timeout": 6.0}
    # Y la heurística de marca ancla NO existe de este lado.
    assert "_es_marca" not in _ENTORNO.read_text(encoding="utf-8")


def test_C4_el_parseo_y_la_forma_de_retorno(monkeypatch):
    """Se queda el MÁS CERCANO por categoría, con nombre válido, y la salida es
    `{fuente, items, texto}` ordenada por distancia."""
    _EspiaHTTP.arma(monkeypatch, respuesta={"places": [
        {"displayName": {"text": "Lejos"}, "location": {"latitude": -0.19, "longitude": -78.48}},
        {"displayName": {"text": "Cerca"}, "location": {"latitude": -0.1801, "longitude": -78.48}},
        {"displayName": {"text": "sin nombre"}, "location": {"latitude": -0.1800, "longitude": -78.48}},
        {"displayName": {"text": "Sin coords"}, "location": {}},
    ]})
    out = asyncio.run(entorno._entorno_google(-0.18, -78.48, "K"))
    assert set(out) == {"fuente", "items", "texto"}
    assert out["fuente"] == "google"
    assert all(i["nombre"] == "Cerca" for i in out["items"]), "el más cercano válido"
    assert out["items"] == sorted(out["items"], key=lambda i: i["distancia_m"])
    assert set(out["items"][0]) == {"key", "emoji", "label", "nombre", "distancia_m"}
    assert isinstance(out["items"][0]["distancia_m"], int)


def test_C5_tope_de_items(monkeypatch):
    _EspiaHTTP.arma(monkeypatch, respuesta=_lugares("X"))
    assert len(asyncio.run(entorno._entorno_google(-0.18, -78.48, "K", max_items=3))["items"]) == 3


_FALLOS = [
    ("sin resultados", dict(respuesta={"places": []})),
    ("HTTP 404", dict(respuesta=_lugares("X"), status=404)),
    ("HTTP 500", dict(respuesta=_lugares("X"), status=500)),
    ("timeout", dict(excepcion=httpx.TimeoutException("timeout"))),
    ("conexión fallida", dict(excepcion=httpx.ConnectError("sin red"))),
    ("JSON inválido", dict(crudo="<html>")),
    ("JSON incompleto", dict(respuesta={})),
]


@pytest.mark.parametrize("caso,kw", _FALLOS, ids=[c for c, _ in _FALLOS])
def test_C6_toda_degradacion_devuelve_None_y_gasta_los_ocho_requests(caso, kw, monkeypatch):
    """Congelado tal cual, incluido lo caro: los ocho requests se lanzan igual, y el fallo
    se absorbe entero en `gather(return_exceptions=True)` sin registrar nada."""
    _EspiaHTTP.arma(monkeypatch, **kw)
    assert asyncio.run(entorno._entorno_google(-0.18, -78.48, "K")) is None, caso
    assert len(_EspiaHTTP.posts()) == 8, "no hay corte temprano: se pagan las ocho"


def test_C7_sin_credencial_no_se_construye_ni_el_cliente(monkeypatch):
    """`_entorno_google` no comprueba la llave — quien la comprueba es `entorno_destacado`.
    Se congela dónde vive esa decisión."""
    _EspiaHTTP.arma(monkeypatch, respuesta=_lugares("X"))
    monkeypatch.setattr(settings, "google_maps_api_key", "")
    asyncio.run(entorno.entorno_destacado(-0.18, -78.48, None))
    assert _EspiaHTTP.posts() == [], "sin llave no se toca Google"


# ══ (D) La política de `entorno_destacado` ═══════════════════════════════════════════
_POIS = [{"lat": -0.181, "lon": -78.481,
          "tags": {"amenity": "pharmacy", "name": "Fybeca OSM"}}]


def test_D1_la_politica_es_GOOGLE_PRIMERO_y_es_la_contraria_a_la_del_foso(monkeypatch):
    """Se congela, no se corrige. En el Place path manda la capa propia y Google rellena
    huecos; aquí manda Google y OSM es el respaldo. Son dos políticas opuestas para la
    misma pregunta, en dos módulos, y esa es justamente la deuda que R0B2B tendrá que
    resolver a la vista."""
    _EspiaHTTP.arma(monkeypatch, respuesta=_lugares("Farmacia G"))
    monkeypatch.setattr(settings, "google_maps_api_key", "K")
    out = asyncio.run(entorno.entorno_destacado(-0.18, -78.48, _POIS))
    assert out["fuente"] == "google", "con Google respondiendo, OSM no se mira"
    assert len(_EspiaHTTP.posts()) == 8


def test_D2_Google_es_suficiente_cuando_devuelve_AL_MENOS_UN_item(monkeypatch):
    _EspiaHTTP.arma(monkeypatch, respuesta=_lugares("Uno"))
    monkeypatch.setattr(settings, "google_maps_api_key", "K")
    out = asyncio.run(entorno.entorno_destacado(-0.18, -78.48, _POIS))
    assert out["fuente"] == "google" and len(out["items"]) >= 1


def test_D3_cae_a_OSM_solo_si_Google_no_produce_nada(monkeypatch):
    """Y AMBOS se ejecutan en la misma llamada: ocho requests gastados y además el cálculo
    sobre los POIs ya descargados."""
    _EspiaHTTP.arma(monkeypatch, respuesta={"places": []})
    monkeypatch.setattr(settings, "google_maps_api_key", "K")
    out = asyncio.run(entorno.entorno_destacado(-0.18, -78.48, _POIS))
    assert out["fuente"] == "osm"
    assert len(_EspiaHTTP.posts()) == 8, "los ocho requests se pagaron igual"


def test_D4_sin_llave_va_directo_a_OSM_sin_gastar_nada(monkeypatch):
    _EspiaHTTP.arma(monkeypatch, respuesta=_lugares("no debería"))
    monkeypatch.setattr(settings, "google_maps_api_key", "")
    out = asyncio.run(entorno.entorno_destacado(-0.18, -78.48, _POIS))
    assert out["fuente"] == "osm" and _EspiaHTTP.posts() == []


def test_D5_None_cuando_ninguno_de_los_dos_produce(monkeypatch):
    _EspiaHTTP.arma(monkeypatch, respuesta={"places": []})
    monkeypatch.setattr(settings, "google_maps_api_key", "K")
    assert asyncio.run(entorno.entorno_destacado(-0.18, -78.48, None)) is None
    monkeypatch.setattr(settings, "google_maps_api_key", "")
    assert asyncio.run(entorno.entorno_destacado(-0.18, -78.48, None)) is None


def test_D6_las_dos_ramas_producen_LA_MISMA_FORMA(monkeypatch):
    """Lo único que ya está unificado entre los dos caminos, y conviene que siga así: es lo
    que hará barata la consolidación."""
    monkeypatch.setattr(settings, "google_maps_api_key", "K")
    _EspiaHTTP.arma(monkeypatch, respuesta=_lugares("G"))
    g = asyncio.run(entorno.entorno_destacado(-0.18, -78.48, _POIS))
    o = entorno.extraer_entorno_osm(_POIS, -0.18, -78.48)
    assert set(g) == set(o) == {"fuente", "items", "texto"}
    assert set(g["items"][0]) == set(o["items"][0])


# ══ (E) La precedencia REAL en `app/routers/assets.py` ═══════════════════════════════
# No basta con llamar a las dos funciones por separado: lo que hay que congelar es QUÉ
# VALOR acaba en la columna `servicios_cercanos`, que es donde compiten.
def _recompute(monkeypatch, servicios_texto, entorno_texto="del respaldo", pois=_POIS):
    """Ejercita `_recompute_walk_score` entero con dobles y devuelve (params_del_UPDATE,
    nº de veces que se llamó a `entorno_destacado`)."""
    llamadas = {"entorno": 0}
    capturado = {}

    async def _fake_entorno(lat, lon, p):
        llamadas["entorno"] += 1
        return {"fuente": "google", "items": [], "texto": entorno_texto} if entorno_texto else None

    async def _fake_analizar(lat, lon):
        return {"conectividad": "conect", "servicios_texto": servicios_texto}

    class _Sesion:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, stmt, params=None):
            if params and "s" in params:
                capturado.update(params)

        async def commit(self):
            pass

    async def _fake_fetch(lat, lon, timeout=None):
        return pois

    async def _fake_col(session):
        return None

    monkeypatch.setattr(assets, "_fetch_pois", _fake_fetch)
    monkeypatch.setattr(assets, "compute_walk_score",
                        lambda *a, **k: {"walk_score": 71, "fuente": "osm"})
    monkeypatch.setattr(assets, "extraer_conectividad", lambda *a, **k: {"texto": "osm-con"})
    monkeypatch.setattr(assets, "entorno_destacado", _fake_entorno)
    monkeypatch.setattr(assets, "AsyncSessionLocal", _Sesion)
    monkeypatch.setattr(assets, "ensure_walk_score_fuente_column", _fake_col)
    monkeypatch.setattr(rutas, "analizar_zona", _fake_analizar)
    asyncio.run(assets._recompute_walk_score("activo-sintetico-1", -0.18, -78.48))
    return capturado, llamadas["entorno"]


def test_E1_caso_A_el_Place_path_produce_texto_y_el_respaldo_NI_SE_LLAMA(monkeypatch):
    """La precedencia real, y es más fuerte que «gana el primero»: el `or` corta ANTES del
    `await`, así que con el Place path produciendo, el segundo Google no se ejecuta — ni
    gasta una sola llamada."""
    params, veces = _recompute(monkeypatch, servicios_texto="💊 Farmacia del Place path")
    assert params["s"] == "💊 Farmacia del Place path"
    assert veces == 0, "el respaldo se llamó habiendo texto del Place path"


def test_E2_caso_B_el_Place_path_no_produce_y_entra_el_respaldo(monkeypatch):
    params, veces = _recompute(monkeypatch, servicios_texto=None)
    assert params["s"] == "del respaldo"
    assert veces == 1


def test_E3_caso_B_texto_vacio_cuenta_como_NO_producir(monkeypatch):
    """`or` mira la veracidad, no la ausencia: `""` también cede el turno al respaldo."""
    params, veces = _recompute(monkeypatch, servicios_texto="")
    assert params["s"] == "del respaldo" and veces == 1


def test_E4_caso_C_si_el_respaldo_tambien_falla_la_columna_queda_en_None(monkeypatch):
    params, veces = _recompute(monkeypatch, servicios_texto=None, entorno_texto=None)
    assert params["s"] is None, "se escribe None, no una cadena vacía"
    assert veces == 1


def test_E5_la_conectividad_sigue_la_MISMA_precedencia(monkeypatch):
    """La línea de al lado tiene la misma forma y conviene congelarla junta: si la
    consolidación toca una, toca las dos."""
    params, _ = _recompute(monkeypatch, servicios_texto="x")
    assert params["c"] == "conect"


# ══ (F) Baseline del PostGIS residual ════════════════════════════════════════════════
_GEO = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]}


def test_F1_contenido_isocrona_hace_DOS_queries_en_UNA_conexion(monkeypatch):
    """El dato que condiciona la extracción: una sola conexión cubre las dos tablas. Mover
    solo la de `pois_vivos` convertiría 1 conexión en 2, y eso es cambio de comportamiento."""
    reg = _con_db(monkeypatch, [[{"categoria": "farmacia", "n": 3},
                                 {"categoria": "salud", "n": 2}], 7])
    salida = asyncio.run(rutas._contenido_isocrona(_GEO))
    assert reg["connects"] == 1 and len(reg["sql"]) == 2
    assert reg["sql"] == ["FROM pois_vivos", "FROM activos_inmutables"]
    assert reg["params"] == [{"geo": json.dumps(_GEO)}, {"geo": json.dumps(_GEO)}]
    assert "3 farmacias · 2 puntos de salud" in salida and "7 inmuebles" in salida


def test_F2_contenido_isocrona_sin_filas_devuelve_cadena_vacia(monkeypatch):
    reg = _con_db(monkeypatch, [[], 0])
    assert asyncio.run(rutas._contenido_isocrona(_GEO)) == ""
    assert reg["connects"] == 1 and len(reg["sql"]) == 2


def test_F3_contenido_isocrona_con_la_base_caida_devuelve_cadena_vacia(monkeypatch):
    reg = _con_db(monkeypatch, [], revienta=True)
    assert asyncio.run(rutas._contenido_isocrona(_GEO)) == ""
    assert reg["connects"] == 1 and reg["sql"] == [], "ninguna query llegó a ejecutarse"


def _fila(nombre, cat, d, masivo):
    return {"nombre": nombre, "categoria_overture": cat, "lat": -0.18, "lon": -78.48,
            "distancia_m": d, "es_masivo": masivo}


def test_F4_panorama_transporte_una_query_con_sus_cuatro_parametros(monkeypatch):
    """El material lleva SEIS paradas nombradas a propósito, no dos.

    Con dos, el tope de 4 nombres y el dedup por nombre no se ejercitan nunca: la mutación
    que baja el tope nace INERTE y la guarda parece medir sin medir. Es el mismo fallo que
    tumbó dos guardas de orden en 1.6 — el material tiene que hacer que la regla muerda.
    """
    reg = _con_db(monkeypatch, [[
        _fila("Metro La Carolina", "metro", 900, True),
        _fila("Parada Amazonas", "parada", 120, False),
        _fila("Parada Amazonas", "parada", 130, False),      # duplicada: dedup por nombre
        _fila("Parada Naciones Unidas", "parada", 150, False),
        _fila("Parada Shyris", "parada", 170, False),
        _fila("Parada República", "parada", 190, False),
        _fila("Parada Eloy Alfaro", "parada", 210, False),    # la 5ª nombrada: cae por el tope
        _fila("parada de bus", None, 230, False),             # genérica: no se nombra
    ]])
    salida = asyncio.run(rutas._panorama_transporte(-0.18, -78.48))
    assert reg["connects"] == 1 and reg["sql"] == ["FROM pois_vivos"]
    assert sorted(reg["params"][0]) == ["lat", "lon", "masivo", "max_m"]
    assert reg["params"][0]["max_m"] == 2500 == rutas._RADIO_MASIVO_M
    assert reg["params"][0]["masivo"] == rutas._TRANSPORTE_MASIVO
    # La transformación: masivo primero, con minutos a ~80 m/min.
    assert "🚇 **Metro La Carolina** (Metro) a 900 m (~11 min)" in salida["texto"]
    # EXACTAMENTE cuatro paradas nombradas — el tope, ejercitado.
    nombradas = [p for p in ("Parada Amazonas", "Parada Naciones Unidas", "Parada Shyris",
                             "Parada República", "Parada Eloy Alfaro")
                 if f"🚏 {p} (" in salida["texto"]]
    assert len(nombradas) == 4, f"el tope es 4 y se nombraron {len(nombradas)}: {nombradas}"
    assert salida["texto"].count("Parada Amazonas") == 1, "dedup por nombre, no por fila"
    # La cola cuenta el resto de PARADAS (7 no masivas − 4 nombradas = 3).
    assert "+3 paradas más" in salida["texto"]
    assert salida["acciones"][0]["tipo"] == "puntos"
    assert len(salida["acciones"][0]["items"]) == 8, "todos los pines, nombrados o no"


def test_F5_panorama_transporte_sin_filas_y_con_la_base_caida_dan_LO_MISMO(monkeypatch):
    """Y eso es un hallazgo, no una virtud: «no tengo transporte mapeado» se emite igual si
    la capa está vacía que si la base no respondió. Se congela como está."""
    reg_vacio = _con_db(monkeypatch, [[]])
    vacio = asyncio.run(rutas._panorama_transporte(-0.18, -78.48))
    reg_caido = _con_db(monkeypatch, [], revienta=True)
    caido = asyncio.run(rutas._panorama_transporte(-0.18, -78.48))
    assert vacio == caido
    assert "hueco de nuestra capa" in vacio["texto"]
    assert reg_vacio["connects"] == 1 and reg_caido["connects"] == 1


# ══ (G) ¿Hay costura limpia entre el I/O y la prosa? ═════════════════════════════════
def test_G1_contenido_isocrona_SI_tiene_costura__la_prosa_ya_es_funcion_aparte():
    """`_frase_dentro` es pura y existe ya como función: el I/O produce `(filas, activos)` y
    ella los convierte en texto. Ese corte se puede hacer sin inventar nada."""
    assert rutas._frase_dentro([{"categoria": "farmacia", "n": 2}], 0) == (
        "\n\n**Dentro de esa mancha hay:** 2 farmacias.")
    fuente_frase = _RUTAS.read_text(encoding="utf-8").split("def _frase_dentro")[1].split(
        "\nasync def ")[0]
    for io_ in ("engine", "conn", "execute", "await"):
        assert io_ not in fuente_frase, f"`_frase_dentro` dejó de ser pura: {io_}"


def test_G2_panorama_transporte_NO_tiene_costura__I_O_y_prosa_en_UN_solo_cuerpo():
    """La otra mitad, y por eso `PROPIA_RESIDUAL_EXTRACTION_SEAM = NOT CLEAN`.

    Aquí no hay ninguna función pura que reciba las filas: el `engine.connect()`, el
    filtrado, los pines del mapa, el dedup por nombre, los minutos a pie y el texto viven
    todos en el mismo cuerpo. El corte existe —las filas son la frontera natural— pero
    exige PARTIR la función en dos, no mover una. Eso ya no es extracción pura.
    """
    fuente = _RUTAS.read_text(encoding="utf-8").split("async def _panorama_transporte")[1]
    cuerpo = fuente.split("\nasync def ")[0].split("\ndef ")[0]
    assert "engine.connect()" in cuerpo, "el I/O está aquí dentro"
    for prosa in ("acciones", "etiqueta", "🚏", "texto"):
        assert prosa in cuerpo, f"y la prosa también: {prosa}"
    # No existe intermediaria pura a la que entregarle las filas.
    assert "_frase_transporte" not in _definidos(_RUTAS)


# ══ (H) Seams: dónde habrá que poner las fachadas ════════════════════════════════════
def test_H1_entorno_destacado_se_parchea_en_assets_import_de_nivel_de_modulo():
    """`app/routers/assets.py:24` lo importa en la cabecera, así que liga el objeto en SU
    espacio: el punto efectivo de parcheo es `assets.entorno_destacado`."""
    cabecera = assets.__doc__ or ""
    fuente = (_APP / "routers" / "assets.py").read_text(encoding="utf-8")
    assert "from app.entorno import entorno_destacado" in fuente.split("def ")[0]
    assert hasattr(assets, "entorno_destacado")
    assert assets.entorno_destacado is entorno.entorno_destacado
    del cabecera


def test_H2_analizar_zona_se_parchea_en_app_rutas_import_DIFERIDO():
    """El caso opuesto, en la misma función: `analizar_zona` se importa DENTRO de
    `_recompute_walk_score`, así que se resuelve sobre `app.rutas` en cada ejecución y
    `assets.analizar_zona` ni existe."""
    fuente = (_APP / "routers" / "assets.py").read_text(encoding="utf-8")
    assert "        from app.rutas import analizar_zona" in fuente
    assert not hasattr(assets, "analizar_zona")
    assert hasattr(rutas, "analizar_zona")


def test_H3_los_dos_cuerpos_de_PostGIS_se_parchean_en_app_rutas():
    """Ambos resuelven `engine` en el espacio de `rutas`, así que ahí es donde muerde el
    doble — y ahí es donde una futura fachada tendrá que ligar el nombre."""
    assert hasattr(rutas, "engine")
    for nombre in ("_contenido_isocrona", "_panorama_transporte"):
        assert getattr(rutas, nombre).__module__ == "app.rutas"
    import app.place.providers.propia as propia
    assert rutas.engine is propia.engine, "hoy es el MISMO engine, ligado en dos módulos"


def test_H4_el_segundo_Google_NO_comparte_objeto_con_el_provider():
    """Lo contrario del caso anterior, y es la razón de que la consolidación sea trabajo de
    código y no de fachada: son dos funciones distintas, no dos nombres del mismo objeto."""
    import app.place.providers.google as prov
    assert entorno._google_nearest is not prov._nearest_categoria
    assert entorno._RADIO_M != 3000
