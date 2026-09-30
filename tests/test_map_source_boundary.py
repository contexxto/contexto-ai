"""MAP-SOURCE-BOUNDARY OWN-DATA CUTOVER 0.1 — nada de Google llega a MapLibre.

Todo lo que el producto pinta sobre MapLibre/CARTO —el mini-mapa AURA del anuncio, el Mapa
Vivo con su popup y su chat, el badge del pin de MapSeed— sale de fuentes propias o
abiertas: la capa propia (`pois_vivos`: Overture + OSM + curación), OSM vía Overpass,
Nominatim y Valhalla. El contenido de Google Places, Routes o Geocoding no puede mostrarse
sobre un mapa que no es de Google, y hasta esta unidad lo hacía por siete caminos.

Esta guarda falla si:

  (1) un productor de mapa obtiene Places (relleno de huecos, tour, «qué hay cerca»,
      «ruta a X», entorno persistido);
  (2) geometría de Routes llega a una superficie MapLibre (acción `ruta`, escena con `ruta`,
      `/rutas` con líneas);
  (3) AURA exige la llave de Google;
  (4) AURA etiqueta un POI propio como de Google (o pinta uno que no es propio);
  (5) reaparece un fallback a Google en tour / cerca / ruta a X;
  (6) `servicios_cercanos` / `conectividad` persistidos SIN procedencia vuelven a un mapa;
  (7) el geocodificado que termina en un mapa vuelve a usar Google.

Dos capas: ESTÁTICA (AST sobre todo `app/`: Google solo vive en su provider, en la
definición de la llave y en un geocodificador sin llamador) y de EJECUCIÓN (los productores
reales, con los proveedores de Google sustituidos por espías que CUENTAN y devuelven datos
reconocibles, y la red externa cortada). Cada guarda tiene su mitad negativa.

Escenarios: cobertura propia completa, parcial y cero; con y sin GOOGLE_MAPS_API_KEY;
Valhalla disponible y caído.
"""
from __future__ import annotations

import ast
import asyncio
import json
import socket
from pathlib import Path

import httpx
import pytest

import app.agent.tools as tools
import app.entorno as entorno
import app.place.providers.google as google
import app.routers.assets as assets
import app.rutas as rutas
from app.config import settings
from app.place.legado import con_contexto_vigente, contexto_legado_vigente

RAIZ = Path(__file__).resolve().parents[1]
APP = RAIZ / "app"
LAT, LON = -0.1807, -78.4678
ACTIVO = "0cb128c9-0000-4000-8000-0000000b0da1"
NOMBRE_GOOGLE = "LUGAR-DE-GOOGLE"
# En el formato REAL que tiene la columna (`_formatear`: «emoji nombre a ~N m · …»); con otro
# formato el parser no produciría chips y la prueba de la tarjeta pasaría sin medir nada.
TEXTO_LEGADO_SERV = "💊 Farmacia Legada a ~120 m · 🌳 Parque Legado a ~300 m"
TEXTO_LEGADO_CONECT = "🚇 Estación Legada ~640 m (19 min a pie)"


# ══ Red externa cortada ═════════════════════════════════════════════════════════════
class RedProhibida(BaseException):
    """`BaseException` y no `Exception`: varios productores envuelven su I/O en
    `except Exception`, y un intento de red real se volvería un `None` silencioso."""


_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    """Corta la salida externa y, además, DEJA RASTRO: `asyncio.gather(...,
    return_exceptions=True)` captura también los `BaseException`, así que un intento real
    a Google dentro de un gather se volvería un resultado descartado y la prueba pasaría en
    verde. El rastro no lo absorbe nadie: se comprueba al terminar cada prueba."""
    intentos: list[str] = []
    originales = {"getaddrinfo": socket.getaddrinfo, "create_connection": socket.create_connection,
                  "connect": socket.socket.connect, "connect_ex": socket.socket.connect_ex}

    def prohibido(nombre):
        def _barrera(*args, **kwargs):
            destino = args[1] if nombre in ("connect", "connect_ex") and len(args) > 1 else (
                args[0] if args else None)
            host = destino[0] if isinstance(destino, (tuple, list)) and destino else destino
            if isinstance(host, bytes):
                host = host.decode("ascii", "replace")
            if str(host) in _LOOPBACK:
                return originales[nombre](*args, **kwargs)
            intentos.append(f"{nombre} -> {destino!r}")
            raise RedProhibida(f"salida de red prohibida: {nombre} -> {destino!r}")
        return _barrera

    monkeypatch.setattr(socket, "getaddrinfo", prohibido("getaddrinfo"))
    monkeypatch.setattr(socket, "create_connection", prohibido("create_connection"))
    monkeypatch.setattr(socket.socket, "connect", prohibido("connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", prohibido("connect_ex"))
    yield intentos
    assert intentos == [], f"hubo intentos de salir a la red (tragados o no): {intentos}"


# ══ Espías de Google: CUENTAN y devuelven datos reconocibles ════════════════════════
class _Espias:
    def __init__(self):
        self.llamadas: list[str] = []

    def total(self) -> int:
        return len(self.llamadas)


@pytest.fixture
def g(monkeypatch):
    """Los cinco caminos a Google, sustituidos en SU módulo. Si un productor los alcanza,
    queda contado y, además, su dato (`LUGAR-DE-GOOGLE`, `fuente: google`) aparece en la
    salida, que se inspecciona aparte."""
    esp = _Espias()

    def _poi(cat):
        return {"nombre": NOMBRE_GOOGLE, "lat": LAT + 0.001, "lon": LON + 0.001,
                "distancia_m": 150, "cat": cat, "fuente": "google", "es_masivo": True}

    async def _nearest(lat, lon, cat, key, tipos=None):
        esp.llamadas.append(f"places:{cat}")
        return _poi(cat)

    async def _mejor(lat, lon, key):
        esp.llamadas.append("places:transporte")
        return _poi("transporte")

    async def _ruta(cliente, o_lat, o_lon, d_lat, d_lon, key):
        esp.llamadas.append("routes")
        return {"duracion_min": 19, "distancia_m": 1520,
                "coords": [[LON, LAT], [LON + 0.002, LAT + 0.002]]}

    async def _entorno(lat, lon, key, max_items=8):
        esp.llamadas.append("places:entorno")
        return {"fuente": "google", "items": [{"nombre": NOMBRE_GOOGLE}],
                "texto": f"💊 {NOMBRE_GOOGLE} (~150 m)"}

    async def _geo(address, key):
        esp.llamadas.append("geocoding")
        return {"lat": LAT, "lon": LON, "formatted": NOMBRE_GOOGLE}

    dobles = {"_nearest_categoria": _nearest, "_mejor_transporte": _mejor,
              "_ruta_a_pie": _ruta, "_entorno_google": _entorno}
    for nombre, doble in dobles.items():
        monkeypatch.setattr(google, nombre, doble)
        # Y en cualquier módulo que vuelva a ligar el nombre (una fachada reintroducida): el
        # espía tiene que morder donde se RESUELVE la llamada, no solo donde vive el cuerpo.
        for modulo in (rutas, entorno, assets, tools):
            if hasattr(modulo, nombre):
                monkeypatch.setattr(modulo, nombre, doble)
    monkeypatch.setattr(tools, "_geocode_google", _geo)
    return esp


@pytest.fixture(params=["", "LLAVE-DE-PRUEBA"], ids=["sin_llave", "con_llave"])
def llave(request, monkeypatch):
    """Con y sin GOOGLE_MAPS_API_KEY el resultado tiene que ser el MISMO: la llave de un
    tercero no puede decidir nada de lo que se pinta."""
    monkeypatch.setattr(settings, "google_maps_api_key", request.param)
    return request.param


# ══ La capa propia, doblada por cobertura ═══════════════════════════════════════════
_CATS_COMPLETA = ("salud", "farmacia", "supermercado", "educacion", "parque",
                  "centro_comercial", "transporte", "iglesia", "seguridad")
COBERTURAS = {
    "completa": _CATS_COMPLETA,
    "parcial": ("farmacia", "parque", "transporte"),
    "cero": (),
}


def _propio(cat, i):
    return {"nombre": f"Propio {cat}", "lat": LAT + 0.0005 * (i + 1), "lon": LON - 0.0004 * (i + 1),
            "distancia_m": 90 + 60 * i, "cat": cat, "fuente": "propio", "marca": None,
            "verificado_en": None, "poi_id": 1000 + i, "es_masivo": cat == "transporte"}


def _instala_capa(monkeypatch, nombre):
    cats = COBERTURAS[nombre]
    entorno_cats = [c for c in cats if c not in ("iglesia", "seguridad")]  # las 7 del entorno

    async def _servicios_propios(lat, lon):
        return {c: _propio(c, i) for i, c in enumerate(entorno_cats)}

    async def _nearest_propio(lat, lon, cat, subtipos=None):
        return _propio(cat, cats.index(cat)) if cat in cats else None

    monkeypatch.setattr(rutas, "_servicios_propios", _servicios_propios)
    monkeypatch.setattr(rutas, "_nearest_propio", _nearest_propio)
    return entorno_cats


@pytest.fixture(params=list(COBERTURAS), ids=[f"cobertura_{c}" for c in COBERTURAS])
def cobertura(request, monkeypatch):
    """(nombre, categorías que la capa cubre — las nueve, iglesia y seguridad incluidas)."""
    _instala_capa(monkeypatch, request.param)
    return request.param, COBERTURAS[request.param]


@pytest.fixture
def lugar(monkeypatch):
    """Nominatim y Overpass, doblados en su punto de resolución efectivo."""
    async def _geo(lat, lon):
        return {"barrio": "La Floresta", "ciudad": "Quito"}

    async def _walk(lat, lon, *a, **k):
        return {"walk_score": 82, "pois_analizados": 120, "fuente": "osm"}

    monkeypatch.setattr(tools, "_reverse_geocode", _geo)
    monkeypatch.setattr(rutas, "walk_score_para", _walk)


def _sin_rastro_de_google(salida) -> None:
    """Ni el nombre de los espías, ni una etiqueta `fuente: google`, ni nada de Routes."""
    crudo = json.dumps(salida, ensure_ascii=False)
    assert NOMBRE_GOOGLE not in crudo, crudo[:400]
    assert '"fuente": "google"' not in crudo, crudo[:400]


def _acciones_de_ruta(salida: dict) -> list:
    """Toda geometría de ruta que el frontend dibujaría como línea sobre MapLibre."""
    lineas = []
    for a in salida.get("acciones") or []:
        if a.get("tipo") == "ruta":
            lineas.append(a)
        for esc in a.get("escenas") or []:
            if esc.get("ruta"):
                lineas.append(esc["ruta"])
    return lineas


# ══ Base de datos falsa, lo justo para los endpoints ════════════════════════════════
class _Res:
    def __init__(self, filas):
        self.filas = filas

    def mappings(self):
        return self

    def all(self):
        return list(self.filas)

    def first(self):
        return self.filas[0] if self.filas else None

    def scalar(self):
        return None


class _Sesion:
    def __init__(self, responde):
        self.responde = responde

    async def execute(self, stmt, params=None):
        return _Res(self.responde(str(stmt), params or {}))

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _fila_legada(**extra):
    base = {"id": ACTIVO, "direccion": "Av. Sintética y Calle Falsa", "tipo_activo": "Departamento",
            "piso_altura": 3, "walk_score": 82, "ruido": "MEDIO", "vegetacion": 12.5,
            "trafico": "MEDIO", "conectividad": TEXTO_LEGADO_CONECT,
            "servicios_cercanos": TEXTO_LEGADO_SERV, "imagen_url": None, "lon": LON, "lat": LAT,
            "estado_revision": "publicado", "confianza_extraccion": 0.9, "distancia_m": 12}
    base.update(extra)
    return base


@pytest.fixture
def cliente(monkeypatch):
    """Cliente HTTP en proceso (ASGI) contra la app real, con la base sustituida."""
    import main
    from app.database import get_db
    from app.limiter import limiter

    monkeypatch.setattr(limiter, "enabled", False)
    estado = {"responde": lambda sql, p: []}

    async def _db():
        yield _Sesion(lambda sql, p: estado["responde"](sql, p))

    main.app.dependency_overrides[get_db] = _db

    def pedir(metodo, ruta, responde=None, **kw):
        if responde is not None:
            estado["responde"] = responde

        async def _go():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                         base_url="http://test") as c:
                return await c.request(metodo, ruta, **kw)
        return asyncio.run(_go())

    try:
        yield pedir
    finally:
        main.app.dependency_overrides.pop(get_db, None)


def _responde_aura(sql, params):
    if "FROM activos_inmutables" in sql:
        return [{"lat": LAT, "lon": LON, "tipo_activo": "Departamento"}]
    return []  # isocronas_inmueble vacía → se pide a Valhalla en vivo


# ═════════════════════════════════════════════════════════════════════════════════════
# (1)(3)(4) AURA: solo capa propia, sin llave, etiqueta real — y Valhalla arriba o caído
# ═════════════════════════════════════════════════════════════════════════════════════
_ISO = [{"minutos": 15, "geometry": {"type": "Polygon", "coordinates": [[[LON, LAT], [LON + .01, LAT],
                                                                           [LON, LAT + .01], [LON, LAT]]]}}]


def _instala_valhalla(monkeypatch, arriba: bool):
    import app.isocronas as iso

    async def _isocrona(lat, lon, minutos=None):
        return _ISO if arriba else None

    async def _guardar(db, activo_id, feats):
        return None
    monkeypatch.setattr(iso, "isocrona", _isocrona)
    monkeypatch.setattr(iso, "guardar_isocronas_inmueble", _guardar)
    monkeypatch.setattr(rutas, "isocrona", _isocrona)


@pytest.fixture(params=["valhalla_arriba", "valhalla_caido"])
def valhalla(request, monkeypatch):
    _instala_valhalla(monkeypatch, request.param == "valhalla_arriba")
    return request.param


def test_AURA_sale_SOLO_de_la_capa_propia(cliente, g, llave, cobertura, valhalla):
    nombre, cats = cobertura
    r = cliente("GET", f"/api/v1/assets/{ACTIVO}/aura", responde=_responde_aura)
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d) == {"lat", "lon", "tipo_activo", "pois", "isocronas"}, "contrato HTTP"
    assert g.total() == 0, g.llamadas
    _sin_rastro_de_google(d)
    # (4) la etiqueta es la real, y todo lo pintado es propio
    assert {p["fuente"] for p in d["pois"]} <= {"propio"}
    assert len(d["pois"]) == min(6, len(cats)), (nombre, d["pois"])
    for p in d["pois"]:
        assert set(p) == {"nombre", "lat", "lon", "distancia_m", "minutos", "cat", "emoji",
                          "color", "fuente"}
        assert p["minutos"] == max(1, round(p["distancia_m"] / 80))
        assert p["nombre"].startswith("Propio ")
    # Valhalla: la isócrona es propia y degrada sola
    assert (len(d["isocronas"]) == 1) is (valhalla == "valhalla_arriba")


def test_AURA_no_pinta_lo_que_no_es_propio(monkeypatch, g):
    """Defensa en profundidad: aunque algo que no es de la capa propia llegara a
    `_servicios_con_coords`, `_pois_geo` no lo pinta."""
    async def _mezcla(lat, lon, n=6):
        return [_propio("farmacia", 0),
                {"nombre": NOMBRE_GOOGLE, "lat": LAT, "lon": LON, "distancia_m": 99,
                 "cat": "salud", "fuente": "google"}]
    monkeypatch.setattr(rutas, "_servicios_con_coords", _mezcla)
    pois = asyncio.run(assets._pois_geo(LAT, LON))
    assert [p["nombre"] for p in pois] == ["Propio farmacia"]


def test_la_espia_de_AURA_SI_detecta_un_relleno_con_Google(monkeypatch, g, cliente):
    """MITAD NEGATIVA de la guarda de AURA: se fabrica la regresión —un
    `_servicios_con_coords` que vuelve a rellenar con Google— y la guarda la ve."""
    _instala_capa(monkeypatch, "parcial")
    _instala_valhalla(monkeypatch, arriba=False)

    async def _con_relleno(lat, lon, n=6):
        propios = await rutas._servicios_propios(lat, lon)
        propios["salud"] = await google._nearest_categoria(lat, lon, "salud", "k")
        return list(propios.values())

    monkeypatch.setattr(rutas, "_servicios_con_coords", _con_relleno)
    r = cliente("GET", f"/api/v1/assets/{ACTIVO}/aura", responde=_responde_aura)
    assert g.llamadas == ["places:salud"]
    # Y el filtro de `_pois_geo` tampoco lo deja pasar al mapa.
    assert NOMBRE_GOOGLE not in r.text


# ═════════════════════════════════════════════════════════════════════════════════════
# (2) Geometría de Routes: `/rutas` vacío y ninguna acción de mapa con línea
# ═════════════════════════════════════════════════════════════════════════════════════
def test_rutas_responde_vacio_sin_llamar_a_nadie(cliente, g, llave):
    r = cliente("GET", f"/api/v1/assets/{ACTIVO}/rutas",
                responde=lambda sql, p: [{"lat": LAT, "lon": LON}])
    assert r.status_code == 200 and r.json() == {"rutas": [], "disponible": False}
    assert g.total() == 0
    r = cliente("GET", f"/api/v1/assets/{ACTIVO}/rutas", responde=lambda sql, p: [])
    assert r.status_code == 404


_PREGUNTAS = {
    "tour": "hazme un recorrido por la zona",
    "cerca": "qué hay cerca",
    "ruta_metro": "ruta al metro",
    "ruta_farmacia": "farmacia más cercana",
    "ruta_iglesia": "iglesia más cercana",
}


@pytest.mark.parametrize("pregunta", list(_PREGUNTAS), ids=list(_PREGUNTAS))
def test_mapa_conversacional_sin_Google_y_sin_lineas(g, llave, cobertura, lugar, pregunta):
    """(1)(2)(5) tour / cerca / ruta a X: capa propia, ninguna línea de ruta, ningún
    fallback. Con cobertura cero la respuesta dice que no sabe."""
    nombre, cats = cobertura
    out = asyncio.run(rutas.comando_mapa(_PREGUNTAS[pregunta], LAT, LON))
    assert g.total() == 0, g.llamadas
    _sin_rastro_de_google(out)
    assert _acciones_de_ruta(out) == [], "geometría de ruta hacia MapLibre"
    puntos = [it for a in out["acciones"] for it in (a.get("items") or [])]
    puntos += [pt for a in out["acciones"] for esc in (a.get("escenas") or [])
               for pt in (esc.get("puntos") or [])]
    for pt in puntos:
        assert "LUGAR" not in pt.get("etiqueta", "")
    if pregunta == "tour":
        # El recorrido existe SIEMPRE (sin llave también) y tiene exactamente las escenas que
        # la capa cubre: identidad, [parque], [transporte], [super/salud], síntesis.
        (accion,) = out["acciones"]
        esperadas = ["📍"] + (["🌳"] if "parque" in cats else []) \
            + (["🚶"] if "transporte" in cats else []) \
            + (["🛒"] if {"supermercado", "salud"} & set(cats) else []) + ["✨"]
        assert [e["titulo"].split()[0] for e in accion["escenas"]] == esperadas
        return
    if pregunta == "cerca":
        if nombre == "cero":
            assert out["acciones"] == [] and "hueco de nuestra capa" in out["texto"]
        else:
            entorno_cats = [c for c in cats if c not in ("iglesia", "seguridad")]
            assert len(out["acciones"][0]["items"]) == min(6, len(entorno_cats))
        return
    categoria = {"ruta_metro": "transporte", "ruta_farmacia": "farmacia",
                 "ruta_iglesia": "iglesia"}[pregunta]
    if categoria not in cats:
        # (5) Sin cobertura propia para ESA categoría: se dice que no se sabe; no hay relleno.
        assert out["acciones"] == [] and "hueco de nuestra capa" in out["texto"]
    else:
        (accion,) = out["acciones"]
        assert accion["tipo"] == "puntos" and len(accion["items"]) == 1
        assert "estimado" in out["texto"] and "Todo de nuestra capa propia" in out["texto"]


def test_mapa_conversacional_por_HTTP_sin_llave(cliente, g, lugar, monkeypatch):
    """El endpoint real (`POST /mapa/comando`) con la llave vacía: el tour ya no se niega."""
    monkeypatch.setattr(settings, "google_maps_api_key", "")
    _instala_capa(monkeypatch, "completa")
    r = cliente("POST", "/api/v1/assets/mapa/comando",
                json={"pregunta": "recorre la zona", "lat": LAT, "lon": LON})
    assert r.status_code == 200
    d = r.json()
    assert d["acciones"][0]["tipo"] == "tour"
    assert "Google" not in d["texto"]
    assert g.total() == 0 and _acciones_de_ruta(d) == []


def test_la_guarda_de_lineas_SI_detecta_una_ruta():
    """MITAD NEGATIVA: una acción `ruta` o una escena con `ruta` tienen que verse."""
    assert _acciones_de_ruta({"acciones": [{"tipo": "ruta", "coords": [[0, 0], [1, 1]]}]})
    assert _acciones_de_ruta({"acciones": [{"tipo": "tour", "escenas": [{"ruta": {"coords": []}}]}]})


def test_isocrona_propia_con_Valhalla_arriba_y_caido(g, llave, valhalla, monkeypatch):
    async def _vacio(geometry):
        return ""
    monkeypatch.setattr(rutas, "_contenido_isocrona", _vacio)
    out = asyncio.run(rutas.comando_mapa("hasta dónde llego en 15 minutos caminando isócrona", LAT, LON))
    assert g.total() == 0
    if valhalla == "valhalla_arriba":
        assert out["acciones"][0]["tipo"] == "isocrona"
    else:
        assert out["acciones"] == [] and "no está disponible" in out["texto"]


# ═════════════════════════════════════════════════════════════════════════════════════
# Lo que se PERSISTE y acaba en el popup: `_recolectar_zona` / `_recompute_walk_score`
# ═════════════════════════════════════════════════════════════════════════════════════
def test_el_contexto_de_zona_no_llama_a_Google_y_estima_los_minutos(g, llave, cobertura, lugar):
    nombre, cats = cobertura
    materia = asyncio.run(rutas._recolectar_zona(LAT, LON))
    assert g.total() == 0
    assert materia.transporte_ruta_medida is False
    assert {s["fuente"] for s in materia.servicios} <= {"propio"}
    assert materia.se_consultaron_servicios is (nombre != "cero"), "sin cobertura: UNKNOWN"
    if "transporte" in cats:
        assert materia.transporte_minutos == rutas._min_pie(materia.transporte_distancia_m)
    salida = asyncio.run(rutas.analizar_zona(LAT, LON))
    _sin_rastro_de_google(salida)


def test_recompute_persiste_sin_Google(g, llave, cobertura, lugar, monkeypatch):
    """El job que escribe `conectividad` y `servicios_cercanos`: sin Google en ninguna de
    las dos, tenga o no cobertura propia (sin ella, cae a OSM)."""
    osm = [{"lat": LAT + 0.001, "lon": LON, "tags": {"amenity": "pharmacy", "name": "Farmacia OSM"}},
           {"lat": LAT + 0.004, "lon": LON, "tags": {"railway": "station", "name": "Estación OSM"}}]
    escrito = {}

    async def _fetch(lat, lon, timeout=None):
        return osm

    class _S:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, stmt, params=None):
            if params and "UPDATE activos_inmutables" in str(stmt):
                escrito.update(params)
            return _Res([])

        async def commit(self):
            pass

    async def _col(db):
        return None
    monkeypatch.setattr(assets, "_fetch_pois", _fetch)
    monkeypatch.setattr(assets, "AsyncSessionLocal", lambda: _S())
    monkeypatch.setattr(assets, "ensure_walk_score_fuente_column", _col)
    asyncio.run(assets._recompute_walk_score(ACTIVO, LAT, LON))
    assert g.total() == 0, g.llamadas
    assert escrito, "el job no escribió"
    _sin_rastro_de_google({"c": escrito.get("c"), "s": escrito.get("s")})


def test_entorno_destacado_y_geocoder_con_llave_no_llaman_a_Google(g, monkeypatch):
    """(1)(7) El entorno persistido es OSM; el geocodificado cuyo resultado acaba en un mapa
    (ancla del agente → MapSeed; ingesta → `geom`) es Nominatim."""
    monkeypatch.setattr(settings, "google_maps_api_key", "LLAVE-DE-PRUEBA")
    pois = [{"lat": LAT + 0.001, "lon": LON, "tags": {"amenity": "pharmacy", "name": "Farmacia OSM"}}]
    assert asyncio.run(entorno.entorno_destacado(LAT, LON, pois))["fuente"] == "osm"

    class _Loc:
        address, latitude, longitude = "La Floresta, Quito", LAT, LON

    class _Nom:
        def __init__(self, *a, **k):
            pass

        def geocode(self, *a, **k):
            return _Loc()
    monkeypatch.setattr(tools, "Nominatim", _Nom)
    d = json.loads(asyncio.run(tools.tool_geocode_address.ainvoke({"address": "La Floresta"})))
    assert d["source"] == "nominatim"
    assert g.total() == 0, g.llamadas


# ═════════════════════════════════════════════════════════════════════════════════════
# (6) Los textos persistidos sin procedencia NO vuelven a un mapa
# ═════════════════════════════════════════════════════════════════════════════════════
def test_la_compuerta_de_legado_solo_abre_con_procedencia_propia():
    assert contexto_legado_vigente(TEXTO_LEGADO_SERV) is None
    assert contexto_legado_vigente(TEXTO_LEGADO_SERV, "google") is None
    assert contexto_legado_vigente(TEXTO_LEGADO_SERV, "osm") is None
    assert contexto_legado_vigente(TEXTO_LEGADO_SERV, "propio") == TEXTO_LEGADO_SERV
    assert contexto_legado_vigente(None, "propio") is None
    fila = {"id": ACTIVO, "servicios_cercanos": TEXTO_LEGADO_SERV, "conectividad": TEXTO_LEGADO_CONECT}
    assert con_contexto_vigente(fila) == {"id": ACTIVO, "servicios_cercanos": None, "conectividad": None}
    assert fila["servicios_cercanos"] == TEXTO_LEGADO_SERV, "la frontera copia; no muta la fila"


def _sin_textos_legados(props: dict) -> None:
    assert "conectividad" in props and "servicios_cercanos" in props, "el contrato conserva las claves"
    assert props["conectividad"] is None and props["servicios_cercanos"] is None, props


def test_geojson_del_Mapa_Vivo_no_lleva_textos_legados(cliente, monkeypatch):
    import main
    from app.auth import get_optional_user

    main.app.dependency_overrides[get_optional_user] = lambda: object()
    try:
        r = cliente("GET", "/api/v1/assets/geojson", responde=lambda sql, p: [_fila_legada()])
    finally:
        main.app.dependency_overrides.pop(get_optional_user, None)
    assert r.status_code == 200
    props = r.json()["features"][0]["properties"]
    _sin_textos_legados(props)
    assert props["walk_score"] == 82, "el resto de los scores sigue llegando"


def test_near_del_Mapa_Vivo_no_lleva_textos_legados(cliente):
    """ACTUALIZACIÓN ESPERADA (NEAR-PERIMETER 0.1, opción A): sin sesión `/near` ya no trae las
    claves de entorno —ni con valor ni en null—, así que el legado no puede aparecer; con sesión
    las trae, y sin procedencia propia siguen en null (la frontera de D1)."""
    import main
    from app.auth import CurrentUser, get_optional_user

    r = cliente("GET", f"/api/v1/assets/near?lat={LAT}&lon={LON}",
                responde=lambda sql, p: [_fila_legada()])
    assert r.status_code == 200
    anon = r.json()["features"][0]["properties"]
    assert "conectividad" not in anon and "servicios_cercanos" not in anon
    main.app.dependency_overrides[get_optional_user] = lambda: CurrentUser(user_id="u-msb")
    try:
        r = cliente("GET", f"/api/v1/assets/near?lat={LAT}&lon={LON}",
                    responde=lambda sql, p: [_fila_legada()])
    finally:
        main.app.dependency_overrides.pop(get_optional_user, None)
    assert r.status_code == 200
    _sin_textos_legados(r.json()["features"][0]["properties"])


def test_anuncio_junto_al_mini_mapa_no_lleva_textos_legados(cliente, monkeypatch):
    async def _nada(*a, **k):
        return None

    async def _sin_curaciones(db, activo_id):
        return []

    async def _sin_verificacion(ids):
        return {}
    monkeypatch.setattr(assets, "ensure_walk_score_fuente_column", _nada)
    monkeypatch.setattr(assets, "fetch_curaciones", _sin_curaciones)
    monkeypatch.setattr(assets, "verificacion_de_entorno", _sin_verificacion)
    fila = _fila_legada(walk_score_fuente="osm", caracteristicas={}, operacion="arriendo",
                        precio=650, tiene_ficha=False)
    r = cliente("GET", f"/api/v1/assets/{ACTIVO}/anuncio", responde=lambda sql, p: [fila])
    assert r.status_code == 200, r.text
    _sin_textos_legados(r.json())


def _panel_de(monkeypatch, fila):
    """El panel REAL (`construir_panel` → `_decidir_desde_filas`) con la base doblada."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from app.decision import assembler
    from app.routers import chat

    async def _fetch(_ids):
        return ([fila], {})
    monkeypatch.setattr(assembler, "_fetch_cards_rows", _fetch)
    mensajes = [HumanMessage(content="depa"),
                ToolMessage(content=json.dumps({"assets": [{"id": fila["id"]}]}),
                            name="tool_find_assets_by_text", tool_call_id="t1"),
                AIMessage(content="Encontré esto.")]
    return asyncio.run(chat.construir_panel(mensajes, session_id="s-msb", preferencias={}))


def test_tarjeta_y_badge_de_MapSeed_sin_chips_legados(monkeypatch):
    from app.decision.assembler import _pois_de_intencion
    from app.routers.chat import _map_seed_from_cards

    # Control: este texto, sin la frontera, SÍ produce chips (y por tanto el badge).
    assert len(_pois_de_intencion(TEXTO_LEGADO_SERV)) == 2

    fila = {"id": ACTIVO, "lat": LAT, "lon": LON, "tipo_activo": "Departamento",
            "servicios_cercanos": TEXTO_LEGADO_SERV, "conectividad": TEXTO_LEGADO_CONECT,
            "caracteristicas": {}, "precio": 500, "operacion": "arriendo"}
    (card,) = _panel_de(monkeypatch, fila)["cards"]
    assert card["pois"] == []
    assert _map_seed_from_cards([card])["pines"][0]["badge"] is None


def test_la_compuerta_de_legado_SI_PUEDE_fallar(cliente, monkeypatch):
    """MITAD NEGATIVA: con la compuerta neutralizada (identidad), el texto legado reaparece
    en el popup — así que las pruebas de arriba sí miden la compuerta, no una casualidad."""
    import main
    from app.auth import get_optional_user

    monkeypatch.setattr(assets, "con_contexto_vigente", lambda fila: dict(fila))
    main.app.dependency_overrides[get_optional_user] = lambda: object()
    try:
        r = cliente("GET", "/api/v1/assets/geojson", responde=lambda sql, p: [_fila_legada()])
    finally:
        main.app.dependency_overrides.pop(get_optional_user, None)
    assert r.json()["features"][0]["properties"]["servicios_cercanos"] == TEXTO_LEGADO_SERV


# ═════════════════════════════════════════════════════════════════════════════════════
# ESTÁTICA: dónde puede vivir Google dentro de `app/`
# ═════════════════════════════════════════════════════════════════════════════════════
_SIMBOLOS_GOOGLE = {"_nearest_categoria", "_mejor_transporte", "_ruta_a_pie", "_entorno_google",
                    "_google_nearest", "_geocode_google", "_decode_polyline", "_CAT_GOOGLE",
                    "google_maps_api_key"}
_MODULO_GOOGLE = "app.place.providers.google"

# Dónde SÍ puede aparecer, y por qué. Cualquier otro sitio es un productor potencial de mapa.
_PERMITIDO = {
    "app/place/providers/google.py": "el provider: es donde vive Google",
    "app/config.py": "la definición de la llave",
}
# En `app/agent/tools.py` solo DENTRO de `_geocode_google`: el geocodificador sin llamador.
_PERMITIDO_EN_FUNCION = {("app/agent/tools.py", "_geocode_google")}


def _docstrings(arbol) -> set[int]:
    """Los docstrings pueden NOMBRAR a Google (lo hacen, para explicar el corte); no cuentan."""
    ids = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            cuerpo = getattr(nodo, "body", [])
            if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(cuerpo[0].value, ast.Constant):
                ids.add(id(cuerpo[0].value))
    return ids


def _hallazgos(fuente: str, rel: str) -> list[str]:
    arbol = ast.parse(fuente)
    exentos: set[int] = _docstrings(arbol)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                (rel, nodo.name) in _PERMITIDO_EN_FUNCION:
            exentos |= {id(n) for n in ast.walk(nodo)}
    fuera = []
    for nodo in ast.walk(arbol):
        if id(nodo) in exentos:
            continue
        nombre = (nodo.id if isinstance(nodo, ast.Name) else
                  nodo.attr if isinstance(nodo, ast.Attribute) else None)
        if nombre in _SIMBOLOS_GOOGLE:
            fuera.append(f"{rel}:{nodo.lineno} usa {nombre}")
        if isinstance(nodo, ast.ImportFrom):
            modulo = nodo.module or ""
            if modulo == _MODULO_GOOGLE or (modulo == "app.place.providers"
                                            and any(a.name == "google" for a in nodo.names)):
                fuera.append(f"{rel}:{nodo.lineno} importa el provider de Google")
            fuera += [f"{rel}:{nodo.lineno} importa {a.name}" for a in nodo.names
                      if a.name in _SIMBOLOS_GOOGLE]
        if isinstance(nodo, ast.Import) and any(a.name == _MODULO_GOOGLE for a in nodo.names):
            fuera.append(f"{rel}:{nodo.lineno} importa el provider de Google")
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and \
                "googleapis.com" in nodo.value:
            fuera.append(f"{rel}:{nodo.lineno} habla con googleapis.com")
    return fuera


def _escanea(raiz: Path) -> list[str]:
    fuera = []
    for ruta in sorted((raiz / "app").rglob("*.py")):
        rel = ruta.relative_to(raiz).as_posix()
        if rel not in _PERMITIDO:
            fuera += _hallazgos(ruta.read_text(encoding="utf-8"), rel)
    return fuera


def test_Google_solo_vive_en_su_provider_la_llave_y_un_geocodificador_sin_llamador():
    """(1)(3)(5)(7) La forma estructural de todo lo anterior. Un productor de mapa que
    vuelva a llamar a Places, Routes o Geocoding —o que lea la llave de Google— tiene que
    nombrar uno de estos símbolos, o importar el provider, fuera de los sitios permitidos."""
    assert _escanea(RAIZ) == []


def test_nadie_llama_al_geocodificador_de_Google():
    llamadas = []
    for ruta in sorted(APP.rglob("*.py")):
        for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Call):
                f = nodo.func
                n = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
                if n == "_geocode_google":
                    llamadas.append(f"{ruta.relative_to(RAIZ).as_posix()}:{nodo.lineno}")
    assert llamadas == []


def test_la_guarda_estatica_SI_PUEDE_fallar(tmp_path):
    """MITAD NEGATIVA sobre fuente fabricada: las cinco formas de volver a Google."""
    (tmp_path / "app" / "place" / "providers").mkdir(parents=True)
    (tmp_path / "app" / "agent").mkdir(parents=True)
    (tmp_path / "app" / "mapa.py").write_text(
        "from app.place.providers.google import _ruta_a_pie\n"
        "from app.config import settings\n"
        "async def productor(lat, lon):\n"
        "    k = settings.google_maps_api_key\n"
        "    return await _ruta_a_pie(None, lat, lon, lat, lon, k)\n", encoding="utf-8")
    (tmp_path / "app" / "otro.py").write_text(
        "import httpx\n"
        "URL = 'https://places.googleapis.com/v1/places:searchNearby'\n", encoding="utf-8")
    (tmp_path / "app" / "agent" / "tools.py").write_text(
        "async def _geocode_google(a, k):\n"
        "    return 'https://maps.googleapis.com/maps/api/geocode/json'\n"
        "async def tool_geocode_address(a):\n"
        "    return await _geocode_google(a, 'k')\n", encoding="utf-8")
    (tmp_path / "app" / "place" / "providers" / "google.py").write_text(
        "async def _ruta_a_pie(*a):\n    return 'https://routes.googleapis.com'\n", encoding="utf-8")
    hallados = "\n".join(_escanea(tmp_path))
    assert "app/mapa.py:1 importa el provider de Google" in hallados
    assert "app/mapa.py:4 usa google_maps_api_key" in hallados
    assert "app/mapa.py:5 usa _ruta_a_pie" in hallados
    assert "app/otro.py:2 habla con googleapis.com" in hallados
    assert "app/agent/tools.py:4 usa _geocode_google" in hallados
    assert "app/agent/tools.py:2" not in hallados, "dentro de `_geocode_google` está permitido"
    assert "google.py" not in hallados, "el provider está permitido"
