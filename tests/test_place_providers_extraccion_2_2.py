# -*- coding: utf-8 -*-
"""PLAN04-2.2-R0B1A · la extracción de los proveedores propio y Google.

Qué vigila este fichero, y por qué cada guarda existe:

(A) SITIO DE DEFINICIÓN. Que el cuerpo real viva en el provider y que `rutas.py` NO
    conserve un segundo. Una extracción que copia en vez de mover no rompe nada el día
    que se hace: rompe seis meses después, cuando alguien arregla un borde en una de las
    dos copias y la otra sigue mintiendo. Se mide sobre el AST DEL FICHERO, no con
    `inspect.getsource`, que sigue al objeto y por tanto no puede ver la copia huérfana.

(B) DEPENDENCIA CORRECTA. Ninguno de los dos importa al otro, y ninguno importa
    `app.rutas`, `app.routers` ni `app.agent`. La dirección va del orquestador hacia los
    proveedores y nunca al revés; si se invierte, el módulo del que se estaban separando
    vuelve a ser obligatorio para probarlos.

(C) NINGUNA DECISIÓN MULTI-PROVEEDOR DENTRO DE UN PROVEEDOR. La política —primero la capa
    propia, Google solo para los huecos— vive en `rutas.py`. Un provider que decida caer
    al otro convierte dos capacidades en una y hace imposible medir el presupuesto de
    llamadas, que es justo lo que R0B0 congeló.

(D) FACHADA. La superficie histórica desde `app.rutas` sigue resolviendo AL MISMO OBJETO.

(E) EL SEAM. Y aquí está lo que de verdad importa, la lección que R0B0 dejó escrita:
    identidad de objeto y punto efectivo de parcheo NO son lo mismo. Cada guarda de esta
    sección tiene su mitad negativa, porque una que solo comprueba el caso que funciona
    no distingue «el seam se conservó» de «da igual dónde parchees».

RED: como en R0B0, estas pruebas corren con la salida externa cortada. Sigue siendo local
a este módulo y no política global de la suite.
"""
from __future__ import annotations

import ast
import asyncio
import socket
import subprocess
import sys
from pathlib import Path

import pytest

import app.rutas as rutas
from app.place import providers
from app.place.providers import google, propia

_APP = Path(__file__).resolve().parents[1] / "app"
_PROV = _APP / "place" / "providers"

# ── Lo que se movió, y a dónde ────────────────────────────────────────────────────────
# Compartido: la heurística de marca ancla la aplican LOS DOS, cada uno sobre sus propios
# candidatos. No es de ninguno de los dos, así que vive en el paquete.
_COMPARTIDO = ("_MARCAS_ANCLA", "_MARGEN_MARCA_M", "_es_marca")
_PROPIA = ("log", "_avisar_capa_caida", "_RADIO_M", "_CATS_ENTORNO", "_TRANSPORTE_MASIVO",
           "_RADIO_TRANSP_M", "_PROPIOS_ENTORNO_SQL", "_PROPIOS_TRANSPORTE_SQL", "_fecha",
           "_servicios_propios", "_VERIFICACION_ENTORNO_SQL", "verificacion_de_entorno",
           "_CATS_PROPIAS", "_PROPIOS_NEAREST_SQL", "_NOMBRES_GENERICOS", "_nombre_poi",
           "_nearest_propio")
_GOOGLE = ("_TIMEOUT", "_decode_polyline", "_ruta_a_pie", "_CAT_GOOGLE",
           "_nearest_categoria", "_mejor_transporte")

_DESTINO = {**{n: providers for n in _COMPARTIDO},
            **{n: propia for n in _PROPIA},
            **{n: google for n in _GOOGLE}}
_FICHERO = {providers: _PROV / "__init__.py", propia: _PROV / "propia.py",
            google: _PROV / "google.py"}

# Lo que NO se movió y esta unidad no autoriza mover: la política multi-proveedor.
_ORQUESTACION = ("_servicios_con_coords", "_recolectar_zona")

# ── La fachada es MÍNIMA a propósito ──────────────────────────────────────────────────
# Se reexporta lo que hace falta y solo eso: o lo sigue usando el código que se quedó en
# `rutas.py`, o lo importa desde `app.rutas` un consumidor que esta unidad no toca.
# Reexportar los 26 habría inventado superficie pública que nunca existió, y cada nombre
# de más es un compromiso que alguien acabará usando.
_FACHADA = {
    "_CATS_ENTORNO": "lo usa `_servicios_con_coords` para calcular los huecos",
    "_TRANSPORTE_MASIVO": "lo usa `_panorama_transporte`",
    "_servicios_propios": "lo llaman `_servicios_con_coords` y `entorno_curable`",
    "_nearest_propio": "lo llama `comando_mapa`",
    "_avisar_capa_caida": "lo importa `tests/test_curacion_propaga.py`",
    "verificacion_de_entorno": "lo importan `app/decision/assembler.py`, "
                               "`app/routers/assets.py` y `app/routers/chat.py`",
    "_TIMEOUT": "lo usan los sitios de llamada heredados de la prosa",
    "_ruta_a_pie": "lo llaman `_recolectar_zona`, `comando_mapa` y `rutas_desde`",
    "_nearest_categoria": "lo llaman `_servicios_con_coords`, `comando_mapa` y `recorrido_zona`",
    "_mejor_transporte": "lo llaman `_servicios_con_coords` y `recorrido_zona`",
}


# ══ Tripwire de red ══════════════════════════════════════════════════════════════════
# Loopback vivo a propósito: en Windows `asyncio.run` monta su self-pipe por 127.0.0.1, y
# una barrera que lo corta no bloquea la red, bloquea el intérprete. Lo que se corta es la
# salida EXTERNA.
_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}


class RedProhibida(BaseException):
    """Hereda de `BaseException`, no de `Exception`, y no es un detalle.

    `_nearest_categoria` envuelve TODA su llamada en `except Exception: pass`, así que un
    intento de red real dentro de ella devolvía `None` sin dejar rastro y el tripwire se
    lo tragaba entero: el arnés de mutación lo midió como INERTE, que es la forma que
    tiene una guarda de avisar de que no está midiendo. Un `Exception` no puede escapar
    de ese `except`; un `BaseException` sí.

    (La versión de R0B0 hereda de `RuntimeError` y allí basta, porque los dobles cubren
    todos los seams. Aquí no bastaba, y se dice.)
    """


def _es_loopback(destino) -> bool:
    if isinstance(destino, (tuple, list)) and destino:
        return str(destino[0]) in _LOOPBACK
    return str(destino) in _LOOPBACK


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
                f"salida externa a {destino!r} desde una prueba de providers: algún doble "
                f"dejó de morder y el proveedor real intentó llamar de verdad.")
        return _barrera

    monkeypatch.setattr(socket, "getaddrinfo", prohibido("getaddrinfo"))
    monkeypatch.setattr(socket, "create_connection", prohibido("create_connection"))
    monkeypatch.setattr(socket.socket, "connect", prohibido("connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", prohibido("connect_ex"))


def test_el_tripwire_corta_de_verdad_la_salida_externa():
    """La mitad negativa: si esto no muere con RedProhibida, la barrera es decorativa."""
    with pytest.raises(RedProhibida):
        socket.getaddrinfo("203.0.113.1", 80)     # TEST-NET-3: no existe, no responde


def test_el_tripwire_deja_vivo_el_loopback():
    """Contrapeso: cortar loopback rompería `asyncio.run` y ninguna prueba llegaría a
    ejecutarse. Un tripwire que mata al intérprete no está midiendo la red."""
    async def _nada():
        return 42
    assert asyncio.run(_nada()) == 42


# ══ Utilidades de lectura estática ═══════════════════════════════════════════════════
def _arbol(fichero: Path) -> ast.Module:
    return ast.parse(fichero.read_text(encoding="utf-8"))


def _definidos_en(fichero: Path) -> set[str]:
    """Los nombres que ESE FICHERO define a nivel de módulo, leídos de su texto.

    No se usa `inspect.getsource` a propósito: sigue al objeto hasta su módulo real, así
    que una copia huérfana abandonada en `rutas.py` le resultaría invisible — que es
    exactamente el fallo que esta sección viene a detectar.
    """
    nombres: set[str] = set()
    for n in _arbol(fichero).body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nombres.add(n.name)
        elif isinstance(n, ast.Assign):
            nombres |= {t.id for t in n.targets if isinstance(t, ast.Name)}
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            nombres.add(n.target.id)
    return nombres


def _importados_por(fuente: str) -> set[str]:
    """Los módulos que ese fuente importa, como cadenas punteadas completas."""
    mods: set[str] = set()
    for n in ast.walk(ast.parse(fuente)):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            mods.add(n.module)
            mods |= {f"{n.module}.{a.name}" for a in n.names}
    return mods


def _identificadores(fuente: str) -> set[str]:
    """Los nombres que el CÓDIGO usa. Los comentarios quedan fuera por construcción, y
    eso importa: `propia.py` menciona Google en su prosa ('mismo criterio que Google') y
    una búsqueda de texto plano daría un falso positivo eterno."""
    a = ast.parse(fuente)
    return ({x.id for x in ast.walk(a) if isinstance(x, ast.Name)} |
            {x.attr for x in ast.walk(a) if isinstance(x, ast.Attribute)} |
            {a_.name for n in ast.walk(a) if isinstance(n, (ast.Import, ast.ImportFrom))
             for a_ in n.names})


# ══ (A) Sitio de definición ══════════════════════════════════════════════════════════
@pytest.mark.parametrize("simbolo", sorted(_DESTINO))
def test_el_cuerpo_vive_en_su_provider(simbolo):
    assert simbolo in _definidos_en(_FICHERO[_DESTINO[simbolo]]), (
        f"`{simbolo}` debería estar DEFINIDO en {_FICHERO[_DESTINO[simbolo]].name} y no "
        f"lo está: la extracción no lo movió, o lo movió a otro sitio.")


@pytest.mark.parametrize("simbolo", sorted(_DESTINO))
def test_rutas_no_conserva_un_segundo_cuerpo(simbolo):
    """Mover, no copiar. `rutas.py` puede IMPORTAR el nombre; no puede definirlo."""
    assert simbolo not in _definidos_en(_APP / "rutas.py"), (
        f"`{simbolo}` sigue teniendo un cuerpo en `app/rutas.py` además del de su "
        f"provider. Dos implementaciones del mismo nombre divergen en silencio: se "
        f"arregla una y la otra sigue sirviendo la respuesta vieja.")


@pytest.mark.parametrize("simbolo", sorted(_DESTINO))
def test_exactamente_un_fichero_lo_define(simbolo):
    ficheros = [_APP / "rutas.py", *sorted(_PROV.glob("*.py"))]
    dueños = [f.name for f in ficheros if simbolo in _definidos_en(f)]
    assert dueños == [_FICHERO[_DESTINO[simbolo]].name], (
        f"`{simbolo}` está definido en {dueños}; debería estarlo en exactamente uno.")


@pytest.mark.parametrize("simbolo", sorted(n for n in _DESTINO
                                           if callable(getattr(propia, n, None))
                                           or callable(getattr(google, n, None))
                                           or callable(getattr(providers, n, None))))
def test_el_modulo_declarado_del_objeto_es_su_provider(simbolo):
    """`__module__` es la respuesta del intérprete a «¿de dónde salió esto?». Si dice
    `app.rutas`, el objeto que se está usando no es el que se movió."""
    fn = getattr(_DESTINO[simbolo], simbolo)
    assert fn.__module__ == _DESTINO[simbolo].__name__


def test_la_orquestacion_NO_se_movio():
    """La mitad negativa de (A): si estas dos también se hubieran ido, la guarda de arriba
    seguiría verde y sin embargo la política multi-proveedor habría cruzado la frontera."""
    en_rutas = _definidos_en(_APP / "rutas.py")
    for nombre in _ORQUESTACION:
        assert nombre in en_rutas, (
            f"`{nombre}` decide a QUIÉN se le pregunta. Eso no es implementación de un "
            f"proveedor y esta unidad no autoriza moverlo.")
        for fichero in _PROV.glob("*.py"):
            assert nombre not in _definidos_en(fichero), f"{nombre} apareció en {fichero.name}"


# ══ (B) Dependencia correcta ═════════════════════════════════════════════════════════
_PROHIBIDOS = ("app.rutas", "app.routers", "app.agent")


@pytest.mark.parametrize("fichero", sorted(_PROV.glob("*.py"), key=lambda p: p.name),
                         ids=lambda p: p.name)
def test_ningun_provider_importa_el_modulo_del_que_salio(fichero):
    importados = _importados_por(fichero.read_text(encoding="utf-8"))
    for malo in _PROHIBIDOS:
        assert not any(m == malo or m.startswith(malo + ".") for m in importados), (
            f"{fichero.name} importa `{malo}`. La dirección va del orquestador hacia los "
            f"proveedores; invertirla vuelve a hacer obligatorio `rutas.py` para probarlos.")


def test_propia_no_importa_google_ni_lo_menciona_en_codigo():
    fuente = (_PROV / "propia.py").read_text(encoding="utf-8")
    assert "app.place.providers.google" not in _importados_por(fuente)
    intrusos = sorted(set(_GOOGLE) & _identificadores(fuente))
    assert not intrusos, f"la capa propia usa símbolos de Google: {intrusos}"


def test_google_no_importa_la_capa_propia_ni_la_menciona_en_codigo():
    fuente = (_PROV / "google.py").read_text(encoding="utf-8")
    assert "app.place.providers.propia" not in _importados_por(fuente)
    # `log` se excluye: es un nombre genérico, y que Google tuviera su propio logger no
    # sería una dependencia de la capa propia.
    intrusos = sorted((set(_PROPIA) - {"log"}) & _identificadores(fuente))
    assert not intrusos, f"Google usa símbolos de la capa propia: {intrusos}"


def test_el_paquete_no_importa_sus_propios_submodulos():
    """Si `__init__` importara `propia` o `google`, ninguno de los dos podría importar de
    su propio paquete sin cerrar un ciclo."""
    importados = _importados_por((_PROV / "__init__.py").read_text(encoding="utf-8"))
    assert not any("providers." in m for m in importados), importados


@pytest.mark.parametrize("modulo", ["app.place.providers",
                                    "app.place.providers.propia",
                                    "app.place.providers.google"])
def test_importar_un_provider_no_arrastra_al_orquestador(modulo):
    """La versión ejecutable de (B): el AST solo ve los imports DIRECTOS. Esto lo mide en
    un intérprete limpio, donde un import transitivo sí aparecería."""
    codigo = ("import importlib, sys; importlib.import_module(%r); "
              "print(','.join(sorted(m for m in sys.modules if m == 'app.rutas' "
              "or m.startswith(('app.routers', 'app.agent', 'app.rutas.')))))" % modulo)
    p = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                       cwd=str(_APP.parent), timeout=180)
    assert p.returncode == 0, p.stderr[-2000:]
    assert p.stdout.strip() == "", (
        f"importar `{modulo}` arrastró {p.stdout.strip()}; el provider no es "
        f"independiente del módulo del que se extrajo.")


def test_la_guarda_de_dependencias_SI_PUEDE_fallar():
    """La mitad negativa de (B), sobre fuente fabricada: si el detector no ve una
    importación prohibida escrita a mano, tampoco vería la de verdad."""
    assert "app.rutas" in _importados_por("from app.rutas import _servicios_con_coords")
    assert "app.place.providers.google" in _importados_por(
        "from app.place.providers.google import _CAT_GOOGLE")
    assert set(_GOOGLE) & _identificadores("x = _CAT_GOOGLE['transporte']")


# ══ (C) Ninguna decisión multi-proveedor dentro de un proveedor ══════════════════════
def _decide_caer_al_otro(fuente: str, ajenos: tuple[str, ...]) -> bool:
    """¿Este fuente decide llamar al OTRO proveedor? Se mide sobre el AST: un `if` cuyo
    cuerpo referencie símbolos del otro, o cualquier uso de sus nombres."""
    return bool(set(ajenos) & _identificadores(fuente))


def test_ningun_provider_decide_el_fallback_hacia_el_otro():
    assert not _decide_caer_al_otro((_PROV / "propia.py").read_text(encoding="utf-8"), _GOOGLE)
    assert not _decide_caer_al_otro((_PROV / "google.py").read_text(encoding="utf-8"),
                                    tuple(n for n in _PROPIA if n != "log"))


def test_la_guarda_del_fallback_SI_PUEDE_fallar():
    """La mitad negativa de (C). Sin esto, `_decide_caer_al_otro` podría devolver False
    para todo y las dos aserciones de arriba pasarían sin medir nada."""
    fabricado = ("async def _servicios_propios(lat, lon):\n"
                 "    filas = await _consulta()\n"
                 "    if not filas:\n"
                 "        return await _nearest_categoria(lat, lon, 'salud', k)\n"
                 "    return filas\n")
    assert _decide_caer_al_otro(fabricado, _GOOGLE)


def test_la_politica_sigue_estando_en_rutas():
    """Contrapeso: que los providers no decidan no basta si nadie decide. El hueco se
    calcula donde siempre — en el orquestador."""
    fuente = (_APP / "rutas.py").read_text(encoding="utf-8")
    assert "faltantes = [c for c in _CATS_ENTORNO if c not in propios]" in fuente


# ══ (D) Fachada ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("simbolo", sorted(_FACHADA))
def test_la_fachada_liga_el_mismo_objeto(simbolo):
    """`is`, no `==`: la fachada tiene que ligar EL MISMO objeto. Si fuera una copia,
    parchear uno dejaría al otro intacto y las dos mitades divergirían."""
    assert getattr(rutas, simbolo) is getattr(_DESTINO[simbolo], simbolo)


def test_la_fachada_no_reexporta_nada_de_mas():
    """Contrapeso del anterior. Reexportar los 26 símbolos haría pasar la guarda de arriba
    y además inventaría superficie pública que `app.rutas` nunca tuvo — lo contrario de
    extraer. Cada nombre de la fachada tiene aquí escrito quién lo necesita.
    """
    reexportados = {n for n in _DESTINO if hasattr(rutas, n)}
    assert reexportados == set(_FACHADA), (
        f"de más: {sorted(reexportados - set(_FACHADA))} · "
        f"de menos: {sorted(set(_FACHADA) - reexportados)}")


def test_la_superficie_historica_sigue_importandose_desde_app_rutas():
    """Estos cuatro los importan ficheros que esta unidad NO toca: `app/decision/
    assembler.py`, `app/routers/assets.py`, `app/routers/chat.py` y una prueba. Si la
    fachada se rompe, se rompen ellos y no este fichero."""
    from app.rutas import (  # noqa: F401
        _avisar_capa_caida, _nearest_propio, _servicios_propios, verificacion_de_entorno,
    )


def test_los_consumidores_reales_siguen_resolviendo():
    import app.decision.assembler as da
    import app.routers.chat as rc
    assert da.verificacion_de_entorno is propia.verificacion_de_entorno
    assert rc.verificacion_de_entorno is propia.verificacion_de_entorno


# ══ (E) El seam: dónde hay que parchear para que el doble muerda ═════════════════════
def _spy(retorno):
    async def doble(*args, **kwargs):
        doble.llamadas += 1
        return retorno
    doble.llamadas = 0
    return doble


def test_parchear_en_rutas_SIGUE_mordiendo(monkeypatch):
    """Lo que el baseline de R0B0 da por hecho, dicho explícitamente.

    `_servicios_con_coords` se quedó en `rutas.py`, así que resuelve `_servicios_propios`
    en el espacio de nombres de `rutas`. Por eso la extracción no obligó a cambiar ni una
    línea del baseline: el punto de parcheo efectivo no se movió.
    """
    doble = _spy({})
    monkeypatch.setattr(rutas, "_servicios_propios", doble)
    asyncio.run(rutas._servicios_con_coords(-0.18, -78.48, "", 6))
    assert doble.llamadas == 1


def test_parchear_en_el_PROVIDER_no_alcanza_al_orquestador(monkeypatch):
    """LA MITAD NEGATIVA, y la razón por la que esta sección existe.

    `rutas._servicios_propios is propia._servicios_propios` es cierto, y aun así reasignar
    uno NO cambia lo que ejecuta el otro: lo que manda es dónde se resuelve el nombre en la
    llamada. Confundirlo no da un error, da un doble que no muerde y una prueba que sale a
    la red — por eso el tripwire está armado mientras esto corre.
    """
    doble = _spy({})
    monkeypatch.setattr(propia, "_servicios_propios", doble)
    monkeypatch.setattr(rutas, "_servicios_propios", _spy({}))   # el real no toca la base
    asyncio.run(rutas._servicios_con_coords(-0.18, -78.48, "", 6))
    assert doble.llamadas == 0, (
        "parchear el provider afectó al orquestador: entonces `rutas.py` dejó de resolver "
        "el nombre en su propio espacio y el seam del baseline ya no es el que dice ser.")


def test_la_llamada_INTERNA_de_google_ya_no_se_parchea_desde_rutas(monkeypatch):
    """UN CAMBIO DE SEAM QUE LA EXTRACCIÓN SÍ PRODUJO, medido y fijado aquí.

    Antes del corte, `_mejor_transporte` y `_nearest_categoria` vivían los dos en
    `rutas.py`, así que parchear `rutas._nearest_categoria` interceptaba también la
    llamada interna del primero. Ahora los dos viven en `google.py` y esa llamada se
    resuelve allí: parchear en `rutas` ya no la alcanza.

    El baseline de R0B0 no lo observa porque sustituye `_mejor_transporte` entero, y por
    eso pasó intacto. Se deja escrito para que nadie lo descubra a la mala.
    """
    doble = _spy(None)
    monkeypatch.setattr(rutas, "_nearest_categoria", doble)
    monkeypatch.setattr(google, "_nearest_categoria", _spy(None))   # el real no sale a la red
    asyncio.run(google._mejor_transporte(-0.18, -78.48, "llave"))
    assert doble.llamadas == 0

    # Y el punto que SÍ la alcanza:
    dentro = _spy(None)
    monkeypatch.setattr(google, "_nearest_categoria", dentro)
    asyncio.run(google._mejor_transporte(-0.18, -78.48, "llave"))
    assert dentro.llamadas == 2, "metro y bus: dos intentos, como antes del corte"


def test_la_capa_propia_sigue_yendo_primero_y_google_solo_a_los_huecos(monkeypatch):
    """El presupuesto congelado por R0B0, comprobado a través de la frontera nueva.

    No duplica el baseline: aquí lo que se mide es que la POLÍTICA sobrevivió al corte, con
    los proveedores ya en módulos distintos. Si algún doble dejara de morder, el proveedor
    real intentaría salir y el tripwire lo convertiría en un fallo visible en vez de en
    lentitud.
    """
    # OJO: "transporte" NO está en `_CATS_ENTORNO`; es una rama de decisión aparte en
    # `_servicios_con_coords`. Si el material solo cubriera las seis categorías de la
    # lista, Google seguiría siendo llamado para transporte y la aserción de abajo
    # mediría otra cosa. Se cubre explícitamente.
    cubiertas = {c: {"nombre": f"propio {c}", "distancia_m": 100 + i, "cat": c,
                     "fuente": "propia"}
                 for i, c in enumerate([*propia._CATS_ENTORNO, "transporte"])
                 if c != "farmacia"}
    propios, nearest, transporte = _spy(cubiertas), _spy(None), _spy(None)
    monkeypatch.setattr(rutas, "_servicios_propios", propios)
    monkeypatch.setattr(rutas, "_nearest_categoria", nearest)
    monkeypatch.setattr(rutas, "_mejor_transporte", transporte)

    asyncio.run(rutas._servicios_con_coords(-0.18, -78.48, "llave", 6))

    assert propios.llamadas == 1, "la capa propia se consulta exactamente una vez"
    assert nearest.llamadas == 1, "Google solo para el hueco real (farmacia), ni uno más"
    assert transporte.llamadas == 0, "la propia ya cubría transporte: Google no se toca"
