"""PLAN04-2.2-R0B0 - el baseline de proveedores que R0B1 no podra cambiar.

POR QUE ESTE FICHERO EXISTE ANTES DE MOVER NADA

R0B va a repartir los proveedores entre `app/place/providers/`. El fallo caro de ese
movimiento no es una excepcion: es una llamada de mas. Si tras la extraccion el entorno
pregunta a Google por una categoria que la capa propia YA cubrio, todo sigue
"funcionando" —las tarjetas salen, el texto se arma— y lo unico que cambia es la factura y
el foso, que deja de ser el primero en responder. Ninguna prueba de salida ve eso.

Asi que aqui se congela el PRESUPUESTO DE LLAMADAS: cuantas veces y en que orden logico se
consulta cada proveedor en seis escenarios. No se congelo un numero inventado desde el
mandato: se MIDIO el comportamiento actual con dobles, se contrasto con el codigo, y solo
entonces se escribio.

TRES COSAS QUE ESTE FICHERO NO HACE. No mueve nada. No arregla nada. Y no convierte el
tripwire de red en politica global de la suite: la barrera vive en este modulo.
"""

from __future__ import annotations

import asyncio
import socket
import sys

import pytest

import app.agent.tools as tools
import app.rutas as rutas

# ═════════════════════════════════════════════════════════════════════════════
# (C) TRIPWIRE DE RED - barrera local, sin dependencias nuevas
# ═════════════════════════════════════════════════════════════════════════════


class RedProhibida(RuntimeError):
    """Alguien intento salir a la red desde una prueba de este arnes."""


_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}


def _es_loopback(destino) -> bool:
    """El bucle de eventos de asyncio necesita el loopback para vivir.

    En Windows, `asyncio.run` monta un *self-pipe* con un socketpair contra 127.0.0.1: si
    la barrera cortara eso, no bloquearia la red, bloquearia el interprete. La primera
    version de esta guarda lo hacia, y los nueve escenarios morian antes de empezar. La
    barrera tiene que cortar la salida EXTERNA, que es la que cuesta dinero y delata un
    doble que no mordio.
    """
    if not isinstance(destino, (tuple, list)) or not destino:
        return False
    return str(destino[0]) in _LOOPBACK


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    """Cualquier intento de salir FUERA muere aqui, no en el runner de CI.

    Por que hace falta: hoy la suite no toca la red porque ninguna prueba llama a los
    proveedores, no porque algo lo impida. Un doble que se vuelva no-op —un renombrado, un
    parche aplicado en el sitio equivocado— saldria a Internet de verdad, y el fallo
    apareceria como lentitud o como un flaky, nunca como lo que es.

    Se interceptan las tres puertas: la resolucion de nombres, `connect` sobre un socket
    ya creado, y el atajo `create_connection`. Sin ninguna libreria externa: esto es
    `socket`, que ya esta en la biblioteca estandar.
    """
    def prohibido(nombre):
        def _barrera(*args, **kwargs):
            destino = args[1] if nombre == "connect" and len(args) > 1 else (
                args[0] if args else None)
            if _es_loopback(destino):
                return _originales[nombre](*args, **kwargs)
            raise RedProhibida(
                f"una prueba del arnes de proveedores intento abrir red ({nombre} -> "
                f"{destino!r}). Los proveedores se sustituyen con dobles; si este error "
                "salta, el doble no se aplico donde se resuelve de verdad (ver la seccion "
                "de semantica de parcheo)"
            )
        return _barrera

    _originales = {
        "getaddrinfo": socket.getaddrinfo,
        "create_connection": socket.create_connection,
        "connect": socket.socket.connect,
        "connect_ex": socket.socket.connect_ex,
    }
    monkeypatch.setattr(socket, "getaddrinfo", prohibido("getaddrinfo"))
    monkeypatch.setattr(socket, "create_connection", prohibido("create_connection"))
    monkeypatch.setattr(socket.socket, "connect", prohibido("connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", prohibido("connect_ex"))


def test_C_el_tripwire_SI_intercepta_una_conexion_deliberada():
    """LA MITAD NEGATIVA. Una barrera que nunca podria dispararse no es una barrera.

    Se intenta salir de verdad —tres puertas, una por cada intercepcion— y se exige que
    las tres mueran con nuestro error y no con un timeout.
    """
    with pytest.raises(RedProhibida):
        socket.getaddrinfo("example.invalid", 80)
    with pytest.raises(RedProhibida):
        socket.create_connection(("example.invalid", 80), timeout=1)
    with pytest.raises(RedProhibida):
        s = socket.socket()
        try:
            s.connect(("203.0.113.1", 80))     # TEST-NET-3: nunca enrutable
        finally:
            s.close()


async def _devuelve_uno():
    return 1


def test_C2_el_tripwire_no_estorba_a_lo_que_no_es_red():
    """Contrapeso: la barrera no puede volverse un impuesto sobre el resto. Crear un
    socket, o construir un cliente httpx, no abre nada y debe seguir permitido — de hecho
    `_recolectar_zona` construye un `httpx.AsyncClient` aunque la ruta este doblada."""
    s = socket.socket()
    s.close()
    import httpx
    httpx.AsyncClient()          # construir no conecta
    # y el loopback sigue vivo, que es lo que necesita el bucle de eventos de asyncio
    import asyncio
    assert asyncio.run(_devuelve_uno()) == 1


# ═════════════════════════════════════════════════════════════════════════════
# (D) SEMANTICA DE PARCHEO - donde se resuelve de verdad cada proveedor
# ═════════════════════════════════════════════════════════════════════════════
#
# `rutas.X is provider.X` NO significa que reasignar `rutas.X` cambie lo que ejecuta el
# proveedor, ni al reves. Lo que manda es DONDE SE RESUELVE EL NOMBRE en el momento de la
# llamada, y en este modulo conviven los dos casos opuestos:
#
#   walk_score_para   importado A NIVEL DE MODULO en rutas.py. La llamada resuelve
#                     `rutas.walk_score_para`, asi que hay que parchear AHI. Parchear
#                     `app.walk_score.walk_score_para` NO tiene efecto: rutas ya ligo el
#                     objeto en su propio espacio de nombres al importar.
#
#   _reverse_geocode  importado DENTRO de `_recolectar_zona` (diferido, para no cerrar el
#                     ciclo con app.agent.tools). La llamada resuelve
#                     `app.agent.tools._reverse_geocode` en cada ejecucion, asi que hay
#                     que parchear ALLI. `rutas._reverse_geocode` ni siquiera existe.
#
# Confundirlos no da un error: da un doble que no muerde y una prueba que sale a la red.


def test_D_walk_score_se_resuelve_en_rutas_y_no_en_su_modulo_de_origen():
    assert hasattr(rutas, "walk_score_para"), (
        "rutas.py importa walk_score_para a nivel de modulo: ese es el punto de parcheo"
    )
    import app.walk_score as ws
    assert rutas.walk_score_para is ws.walk_score_para, "hoy son el mismo objeto..."
    # ...pero eso NO implica que parchear el origen cambie lo que rutas ejecuta:
    testigo = object()
    original = ws.walk_score_para
    try:
        ws.walk_score_para = testigo
        assert rutas.walk_score_para is not testigo, (
            "si esto fallara, parchear el modulo de origen bastaria; no es el caso, y "
            "por eso el arnes parchea `rutas.walk_score_para`"
        )
    finally:
        ws.walk_score_para = original


def test_D2_reverse_geocode_se_resuelve_en_su_modulo_y_NO_en_rutas():
    assert not hasattr(rutas, "_reverse_geocode"), (
        "el import es DIFERIDO dentro de `_recolectar_zona`: no hay nada que parchear en "
        "rutas, y creer que lo hay deja el doble sin efecto"
    )
    assert hasattr(tools, "_reverse_geocode")


def test_D3_los_proveedores_de_servicios_se_resuelven_como_globales_de_rutas():
    """`_servicios_con_coords` llama a estos tres por nombre global de su propio modulo,
    asi que el punto de parcheo efectivo es `rutas.<nombre>`."""
    for nombre in ("_servicios_propios", "_nearest_categoria", "_mejor_transporte",
                   "_ruta_a_pie"):
        assert hasattr(rutas, nombre), nombre


# ═════════════════════════════════════════════════════════════════════════════
# (B) BASELINE DE LLAMADAS - medido primero, congelado despues
# ═════════════════════════════════════════════════════════════════════════════

PROPIA = "propia:_servicios_propios"
G_CATEGORIA = "google:_nearest_categoria"
G_TRANSPORTE = "google:_mejor_transporte"
G_RUTA = "google:_ruta_a_pie"
OVERPASS = "overpass:walk_score_para"
NOMINATIM = "nominatim:_reverse_geocode"


def _poi(cat, d=100, **extra):
    base = {"nombre": f"{cat}-x", "cat": cat, "distancia_m": d, "fuente": "propio",
            "lat": -0.18, "lon": -78.48}
    base.update(extra)
    return base


def _todas_las_categorias() -> dict:
    propios = {c: _poi(c) for c in rutas._CATS_ENTORNO}
    propios["transporte"] = _poi("transporte", 640, es_masivo=True)
    return propios


def recolectar_espiando(monkeypatch, *, propios, key, walk_falla=False,
                        routes_falla=False):
    """Ejecuta `_recolectar_zona` con TODOS los proveedores doblados y registra las
    llamadas en orden. Devuelve (registro, materia).

    Cada doble se instala en su punto de resolucion EFECTIVO (ver seccion D). El tripwire
    de red sigue activo: si alguno no mordiera, la prueba moriria con `RedProhibida` en
    vez de salir a Internet.
    """
    registro: list[tuple[str, object]] = []

    async def _propios(lat, lon):
        registro.append((PROPIA, None))
        return dict(propios)

    async def _nearest(lat, lon, cat, k, tipos=None):
        registro.append((G_CATEGORIA, cat))
        return _poi(cat, 500, fuente="google")

    async def _mejor(lat, lon, k):
        registro.append((G_TRANSPORTE, None))
        return _poi("transporte", 800, es_masivo=True, fuente="google")

    async def _ruta(cliente, o_lat, o_lon, d_lat, d_lon, k):
        registro.append((G_RUTA, None))
        if routes_falla:
            raise RuntimeError("Routes caido")
        return {"duracion_min": 19, "distancia_m": 1520}

    async def _walk(lat, lon):
        registro.append((OVERPASS, None))
        if walk_falla:
            raise RuntimeError("Overpass caido")
        return {"walk_score": 70, "pois_analizados": 100, "fuente": "osm"}

    async def _geo(lat, lon):
        registro.append((NOMINATIM, None))
        return {"barrio": "Sintetico"}

    monkeypatch.setattr(rutas, "_servicios_propios", _propios)
    monkeypatch.setattr(rutas, "_nearest_categoria", _nearest)
    monkeypatch.setattr(rutas, "_mejor_transporte", _mejor)
    monkeypatch.setattr(rutas, "_ruta_a_pie", _ruta)
    monkeypatch.setattr(rutas, "walk_score_para", _walk)
    monkeypatch.setattr(tools, "_reverse_geocode", _geo)   # <- en SU modulo, no en rutas
    monkeypatch.setattr(rutas.settings, "google_maps_api_key", key)

    materia = asyncio.run(rutas._recolectar_zona(-0.18, -78.48))
    return registro, materia


def _conteo(registro) -> dict:
    c: dict = {}
    for q, _ in registro:
        c[q] = c.get(q, 0) + 1
    return c


def test_B1_si_la_capa_propia_cubre_la_categoria_GOOGLE_NO_LA_VUELVE_A_PEDIR(monkeypatch):
    """EL INVARIANTE DEL FOSO, y la razon principal de este fichero.

    Con la capa propia cubriendo las seis categorias y el transporte, Google Places no se
    consulta NI UNA VEZ. Lo unico que se le pide es la ruta a pie, que la capa propia no
    sabe calcular. Si tras extraer providers apareciera aqui un `_nearest_categoria`, el
    foso habria dejado de ser el primero en responder y la factura subiria en silencio.
    """
    registro, materia = recolectar_espiando(monkeypatch, propios=_todas_las_categorias(),
                                            key="LLAVE")
    assert _conteo(registro) == {NOMINATIM: 1, OVERPASS: 1, PROPIA: 1, G_RUTA: 1}
    assert G_CATEGORIA not in _conteo(registro)
    assert G_TRANSPORTE not in _conteo(registro)
    assert materia.transporte_ruta_medida is True


def test_B2_si_falta_UNA_categoria_Google_rellena_SOLO_ese_hueco(monkeypatch):
    """El fallback es quirurgico: una categoria ausente, una llamada. No siete."""
    propios = {k: v for k, v in _todas_las_categorias().items() if k != "farmacia"}
    registro, _ = recolectar_espiando(monkeypatch, propios=propios, key="LLAVE")
    assert _conteo(registro) == {NOMINATIM: 1, OVERPASS: 1, PROPIA: 1,
                                 G_CATEGORIA: 1, G_RUTA: 1}
    categorias_pedidas = [d for q, d in registro if q == G_CATEGORIA]
    assert categorias_pedidas == ["farmacia"], categorias_pedidas


def test_B3_sin_credencial_de_Google_no_hay_ni_un_intento(monkeypatch):
    """Sin llave no se intenta nada de Google. Ni categorias, ni transporte, ni ruta.

    OJO, y esto se congela como ESTA, no como deberia estar: sin llave tampoco se consulta
    LA CAPA PROPIA. `_recolectar_zona` corta con `... if key else []` antes de llegar a
    ella, asi que el foso se apaga cuando falta una credencial de un TERCERO. Es el
    comportamiento actual y R0B0 lo congela; corregirlo no esta autorizado aqui y merece
    su propia unidad.
    """
    registro, materia = recolectar_espiando(monkeypatch, propios=_todas_las_categorias(),
                                            key="")
    assert _conteo(registro) == {NOMINATIM: 1, OVERPASS: 1}
    assert PROPIA not in _conteo(registro), (
        "si esto cambia, alguien arreglo el corto-circuito: bienvenido, pero es un cambio "
        "de comportamiento y no cabe en una extraccion"
    )
    assert materia.servicios == []
    assert materia.se_consultaron_servicios is False


def test_B4_si_Overpass_falla_el_resto_del_fetch_no_se_entera(monkeypatch):
    """La caminabilidad degrada sola: `walk` queda vacio y todo lo demas sigue igual.
    Ese `{}` es lo que 1.2 traduce a `insufficient_evidence`."""
    registro, materia = recolectar_espiando(monkeypatch, propios=_todas_las_categorias(),
                                            key="LLAVE", walk_falla=True)
    assert _conteo(registro) == {NOMINATIM: 1, OVERPASS: 1, PROPIA: 1, G_RUTA: 1}
    assert materia.walk == {}
    assert len(materia.servicios) == 6


def test_B5_si_Google_Routes_falla_se_conserva_la_estimacion_en_recta(monkeypatch):
    """Se intenta la ruta UNA vez y, al fallar, se conserva el estimado recta / 80 sobre
    la distancia que trajo el descubrimiento. No se reintenta ni se pierde el transporte."""
    registro, materia = recolectar_espiando(monkeypatch, propios=_todas_las_categorias(),
                                            key="LLAVE", routes_falla=True)
    assert _conteo(registro) == {NOMINATIM: 1, OVERPASS: 1, PROPIA: 1, G_RUTA: 1}
    assert materia.transporte_ruta_medida is False
    assert materia.transporte_distancia_m == 640
    assert materia.transporte_minutos == rutas._min_pie(640) == 8


def test_B6_descubrir_la_parada_y_medir_la_ruta_son_DOS_llamadas_distintas(monkeypatch):
    """Sin transporte propio, Google hace dos cosas conceptualmente separadas: encontrar
    la parada y medir la caminata. 1.2 las acredita como dos evidencias distintas, y esa
    separacion empieza aqui, en el numero de llamadas."""
    propios = {k: v for k, v in _todas_las_categorias().items() if k != "transporte"}
    registro, materia = recolectar_espiando(monkeypatch, propios=propios, key="LLAVE")
    assert _conteo(registro) == {NOMINATIM: 1, OVERPASS: 1, PROPIA: 1,
                                 G_TRANSPORTE: 1, G_RUTA: 1}
    orden = [q for q, _ in registro]
    assert orden.index(G_TRANSPORTE) < orden.index(G_RUTA), (
        "no se puede medir la ruta a una parada que todavia no se ha descubierto"
    )
    assert materia.transporte_ruta_medida is True


# ── el orden logico, congelado aparte del conteo ─────────────────────────────


def test_B7_el_orden_logico_del_fetch_es_estable(monkeypatch):
    """La capa propia se consulta ANTES que el relleno de Google, y la ruta DESPUES del
    descubrimiento. No se congelan tiempos: se congela la precedencia."""
    propios = {k: v for k, v in _todas_las_categorias().items()
               if k not in ("farmacia", "transporte")}
    registro, _ = recolectar_espiando(monkeypatch, propios=propios, key="LLAVE")
    orden = [q for q, _ in registro]
    assert orden.index(PROPIA) < orden.index(G_CATEGORIA)
    assert orden.index(PROPIA) < orden.index(G_TRANSPORTE)
    assert orden.index(G_TRANSPORTE) < orden.index(G_RUTA)


def test_B8_el_espia_SI_puede_detectar_una_llamada_de_mas(monkeypatch):
    """La mitad negativa del baseline. Si el registro no reaccionara a una llamada
    adicional, los seis escenarios de arriba estarian midiendo nada."""
    propios = {k: v for k, v in _todas_las_categorias().items() if k != "farmacia"}
    registro_uno, _ = recolectar_espiando(monkeypatch, propios=propios, key="LLAVE")
    faltan_dos = {k: v for k, v in propios.items() if k != "parque"}
    registro_dos, _ = recolectar_espiando(monkeypatch, propios=faltan_dos, key="LLAVE")
    assert _conteo(registro_uno)[G_CATEGORIA] == 1
    assert _conteo(registro_dos)[G_CATEGORIA] == 2, (
        "dos huecos tienen que producir dos llamadas; si no, el espia esta ciego"
    )


def test_B9_el_arnes_corre_sin_tocar_la_red(monkeypatch):
    """Cierre del circulo: el escenario nominal completo, con el tripwire armado. Que
    termine significa que ningun doble se quedo sin morder."""
    assert socket.getaddrinfo is not socket.__dict__.get("_getaddrinfo_original", None)
    registro, materia = recolectar_espiando(monkeypatch, propios=_todas_las_categorias(),
                                            key="LLAVE")
    assert registro and materia.lugar == {"barrio": "Sintetico"}
    assert "httpx" in sys.modules, "rutas usa httpx; el tripwire actua en socket, no ahi"
