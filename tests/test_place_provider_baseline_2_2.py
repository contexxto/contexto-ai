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
    socket, o construir un cliente httpx, no abre nada y debe seguir permitido (hasta
    MAP-SOURCE-BOUNDARY `_recolectar_zona` construia uno aunque la ruta estuviera doblada)."""
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


def test_D3_la_capa_propia_se_resuelve_en_rutas_y_GOOGLE_YA_NO_ESTA_AHI():
    """`_servicios_con_coords` llama a `_servicios_propios` por nombre global de su propio
    modulo, asi que el punto de parcheo efectivo es `rutas._servicios_propios`.

    ACTUALIZACION ESPERADA (MAP-SOURCE-BOUNDARY, 2026-09-30). Antes este test exigia que
    `_nearest_categoria`, `_mejor_transporte` y `_ruta_a_pie` tambien se resolvieran en
    `rutas`: eran el relleno de Google. La unidad los saco de la fachada a proposito —un
    nombre de Google en el espacio de los productores del mapa es una invitacion a volver
    a llamarlo—, asi que ahora se exige lo contrario."""
    assert hasattr(rutas, "_servicios_propios")
    for nombre in ("_nearest_categoria", "_mejor_transporte", "_ruta_a_pie"):
        assert not hasattr(rutas, nombre), nombre


# ═════════════════════════════════════════════════════════════════════════════
# (B) BASELINE DE LLAMADAS - medido primero, congelado despues
# ═════════════════════════════════════════════════════════════════════════════
#
# ACTUALIZACION ESPERADA (MAP-SOURCE-BOUNDARY, 2026-09-30). El presupuesto de R0B0 era
# «la capa propia primero y Google solo para los huecos, mas la ruta a pie con Routes».
# La unidad corta a Google de todo lo que acaba sobre MapLibre, y `_recolectar_zona` es
# de eso: su prosa se persiste en `activos_inmutables.conectividad` y se pintaba en el
# popup del Mapa Vivo. El presupuesto nuevo es mas simple y mas estricto: Nominatim,
# Overpass y la capa propia, UNA vez cada uno, en todos los escenarios —con llave o sin
# ella, con huecos o sin ellos—, y Google NI UNA.
#
# Los dobles de Google se instalan ahora en SU modulo (`app.place.providers.google`): es
# el unico sitio desde el que alguien podria volver a llamarlos, porque `rutas` ya no los
# liga. La mitad negativa (B8) demuestra que el espia sigue viendo una llamada si aparece.

PROPIA = "propia:_servicios_propios"
G_CATEGORIA = "google:_nearest_categoria"
G_TRANSPORTE = "google:_mejor_transporte"
G_RUTA = "google:_ruta_a_pie"
OVERPASS = "overpass:walk_score_para"
NOMINATIM = "nominatim:_reverse_geocode"
PRESUPUESTO = {NOMINATIM: 1, OVERPASS: 1, PROPIA: 1}


def _poi(cat, d=100, **extra):
    base = {"nombre": f"{cat}-x", "cat": cat, "distancia_m": d, "fuente": "propio",
            "lat": -0.18, "lon": -78.48}
    base.update(extra)
    return base


def _todas_las_categorias() -> dict:
    from app.place.providers.propia import _CATS_ENTORNO
    propios = {c: _poi(c) for c in _CATS_ENTORNO}
    propios["transporte"] = _poi("transporte", 640, es_masivo=True)
    return propios


def _espias_de_google(monkeypatch, registro):
    """Dobles de los tres de Google, en SU modulo. Si alguno se llama, queda escrito."""
    import app.place.providers.google as google

    async def _nearest(lat, lon, cat, k, tipos=None):
        registro.append((G_CATEGORIA, cat))
        return _poi(cat, 500, fuente="google")

    async def _mejor(lat, lon, k):
        registro.append((G_TRANSPORTE, None))
        return _poi("transporte", 800, es_masivo=True, fuente="google")

    async def _ruta(cliente, o_lat, o_lon, d_lat, d_lon, k):
        registro.append((G_RUTA, None))
        return {"duracion_min": 19, "distancia_m": 1520}

    monkeypatch.setattr(google, "_nearest_categoria", _nearest)
    monkeypatch.setattr(google, "_mejor_transporte", _mejor)
    monkeypatch.setattr(google, "_ruta_a_pie", _ruta)
    return google


def recolectar_espiando(monkeypatch, *, propios, key, walk_falla=False):
    """Ejecuta `_recolectar_zona` con TODOS los proveedores doblados y registra las
    llamadas en orden. Devuelve (registro, materia).

    Cada doble se instala en su punto de resolucion EFECTIVO (ver seccion D). El tripwire
    de red sigue activo: si alguno no mordiera, la prueba moriria con `RedProhibida` en
    vez de salir a Internet.
    """
    from app.config import settings

    registro: list[tuple[str, object]] = []

    async def _propios(lat, lon):
        registro.append((PROPIA, None))
        return dict(propios)

    async def _walk(lat, lon):
        registro.append((OVERPASS, None))
        if walk_falla:
            raise RuntimeError("Overpass caido")
        return {"walk_score": 70, "pois_analizados": 100, "fuente": "osm"}

    async def _geo(lat, lon):
        registro.append((NOMINATIM, None))
        return {"barrio": "Sintetico"}

    _espias_de_google(monkeypatch, registro)
    monkeypatch.setattr(rutas, "_servicios_propios", _propios)
    monkeypatch.setattr(rutas, "walk_score_para", _walk)
    monkeypatch.setattr(tools, "_reverse_geocode", _geo)   # <- en SU modulo, no en rutas
    monkeypatch.setattr(settings, "google_maps_api_key", key)

    materia = asyncio.run(rutas._recolectar_zona(-0.18, -78.48))
    return registro, materia


def _conteo(registro) -> dict:
    c: dict = {}
    for q, _ in registro:
        c[q] = c.get(q, 0) + 1
    return c


def test_B1_con_cobertura_propia_completa_GOOGLE_NO_SE_TOCA_NI_PARA_LA_RUTA(monkeypatch):
    """EL INVARIANTE DEL FOSO, ahora sin excepcion. Antes Google aun medía la ruta a pie
    hasta la parada; ya no: los minutos son la estimacion recta / 80, declarada como tal."""
    registro, materia = recolectar_espiando(monkeypatch, propios=_todas_las_categorias(),
                                            key="LLAVE")
    assert _conteo(registro) == PRESUPUESTO
    assert materia.transporte_ruta_medida is False
    assert materia.transporte_distancia_m == 640
    assert materia.transporte_minutos == rutas._min_pie(640) == 8
    assert {s.get("fuente") for s in materia.servicios} == {"propio"}


def test_B2_si_falta_UNA_categoria_se_queda_ausente_y_NADIE_la_rellena(monkeypatch):
    """Antes: una categoria ausente, una llamada a Google. Ahora: ninguna. La cobertura
    parcial se ve como cobertura parcial."""
    propios = {k: v for k, v in _todas_las_categorias().items() if k != "farmacia"}
    registro, materia = recolectar_espiando(monkeypatch, propios=propios, key="LLAVE")
    assert _conteo(registro) == PRESUPUESTO
    assert "farmacia" not in {s["cat"] for s in materia.servicios}
    assert materia.se_consultaron_servicios is True


def test_B3_sin_credencial_de_Google_LA_CAPA_PROPIA_SI_SE_CONSULTA(monkeypatch):
    """R0B0 congelo aqui un defecto y dejo escrito que merecia su propia unidad: sin la
    llave de un TERCERO, `_recolectar_zona` cortaba antes de consultar nuestra capa y el
    foso se apagaba. MAP-SOURCE-BOUNDARY es esa unidad: la llave ya no decide nada."""
    registro, materia = recolectar_espiando(monkeypatch, propios=_todas_las_categorias(),
                                            key="")
    assert _conteo(registro) == PRESUPUESTO
    assert len(materia.servicios) == 6
    assert materia.se_consultaron_servicios is True


def test_B3b_sin_cobertura_propia_NO_SE_SABE_y_no_se_rellena(monkeypatch):
    """Cobertura cero (un punto fuera de Quito, o la capa caida): la respuesta honesta es
    «no se sabe» (UNKNOWN), no «se busco y no hay», y tampoco un relleno de Google."""
    registro, materia = recolectar_espiando(monkeypatch, propios={}, key="LLAVE")
    assert _conteo(registro) == PRESUPUESTO
    assert materia.servicios == []
    assert materia.transporte is None
    assert materia.se_consultaron_servicios is False


def test_B4_si_Overpass_falla_el_resto_del_fetch_no_se_entera(monkeypatch):
    """La caminabilidad degrada sola: `walk` queda vacio y todo lo demas sigue igual.
    Ese `{}` es lo que 1.2 traduce a `insufficient_evidence`."""
    registro, materia = recolectar_espiando(monkeypatch, propios=_todas_las_categorias(),
                                            key="LLAVE", walk_falla=True)
    assert _conteo(registro) == PRESUPUESTO
    assert materia.walk == {}
    assert len(materia.servicios) == 6


def test_B5_los_minutos_al_transporte_son_SIEMPRE_la_estimacion_en_recta(monkeypatch):
    """Antes, si Routes fallaba se conservaba el estimado; ahora el estimado es lo unico
    que hay, y la materia lo declara (`transporte_ruta_medida=False`), que es lo que el
    ensamblador convierte en HEURISTIC_ESTIMATE con su limitacion."""
    _, materia = recolectar_espiando(monkeypatch, propios=_todas_las_categorias(),
                                     key="LLAVE")
    assert materia.transporte_ruta_medida is False
    assert materia.transporte_minutos == rutas._min_pie(materia.transporte_distancia_m)


def test_B6_sin_transporte_propio_NO_se_descubre_ni_se_mide_con_Google(monkeypatch):
    """Antes Google hacia dos cosas aqui: descubrir la parada y medir la caminata. Ahora
    ninguna: sin parada en nuestra capa no hay transporte en la materia."""
    propios = {k: v for k, v in _todas_las_categorias().items() if k != "transporte"}
    registro, materia = recolectar_espiando(monkeypatch, propios=propios, key="LLAVE")
    assert _conteo(registro) == PRESUPUESTO
    assert materia.transporte is None
    assert materia.transporte_minutos is None
    assert materia.transporte_ruta_medida is False


# ── el orden logico, congelado aparte del conteo ─────────────────────────────


def test_B7_con_dos_huecos_el_registro_sigue_sin_nada_de_Google(monkeypatch):
    """La precedencia ya no tiene a quien ordenar: con dos huecos (farmacia y transporte)
    el registro contiene exactamente los tres proveedores abiertos o propios."""
    propios = {k: v for k, v in _todas_las_categorias().items()
               if k not in ("farmacia", "transporte")}
    registro, _ = recolectar_espiando(monkeypatch, propios=propios, key="LLAVE")
    assert {q for q, _ in registro} == set(PRESUPUESTO)
    assert not [q for q, _ in registro if q.startswith("google:")]


def test_B8_el_espia_SI_puede_detectar_una_llamada_a_Google(monkeypatch):
    """La mitad negativa del baseline. Se fabrica la regresion —un `_servicios_con_coords`
    que vuelve a rellenar con Google— y el espia tiene que verla. Si no la viera, los
    escenarios de arriba estarian midiendo nada."""
    import app.place.providers.google as google

    async def _con_relleno(lat, lon, n=6):
        propios = await rutas._servicios_propios(lat, lon)
        if "farmacia" not in propios:
            propios["farmacia"] = await google._nearest_categoria(lat, lon, "farmacia", "k")
        return list(propios.values())

    monkeypatch.setattr(rutas, "_servicios_con_coords", _con_relleno)
    propios = {k: v for k, v in _todas_las_categorias().items() if k != "farmacia"}
    registro, _ = recolectar_espiando(monkeypatch, propios=propios, key="LLAVE")
    assert _conteo(registro).get(G_CATEGORIA) == 1, (
        "una llamada a Google tiene que quedar registrada; si no, el espia esta ciego")


def test_B9_el_arnes_corre_sin_tocar_la_red(monkeypatch):
    """Cierre del circulo: el escenario nominal completo, con el tripwire armado. Que
    termine significa que ningun doble se quedo sin morder."""
    assert socket.getaddrinfo is not socket.__dict__.get("_getaddrinfo_original", None)
    registro, materia = recolectar_espiando(monkeypatch, propios=_todas_las_categorias(),
                                            key="LLAVE")
    assert registro and materia.lugar == {"barrio": "Sintetico"}
    assert not hasattr(rutas, "httpx"), (
        "rutas ya no construye clientes HTTP: todo lo que sale a la red es de un provider")
