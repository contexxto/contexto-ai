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

import app.agent.tools as tools
import app.isocronas as isocronas
import app.rutas as rutas
import app.walk_score as walk_score
from app.place import providers
from app.place.providers import google, nominatim, overpass, propia, valhalla

_APP = Path(__file__).resolve().parents[1] / "app"
_PROV = _APP / "place" / "providers"

# ── Lo que se movió, a dónde, y DESDE dónde ──────────────────────────────────────────
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
# R0B1B. Nominatim sale de `app/agent/tools.py` y Overpass de `app/walk_score.py`: son los
# dos primeros símbolos que NO salieron de `rutas.py`, y por eso el origen deja de poder
# darse por supuesto y pasa a ser un dato de la tabla.
_NOMINATIM = ("_reverse_geocode",)
_OVERPASS = ("_OVERPASS_MIRRORS", "_RADIUS_M", "_TIMEOUT", "_fetch_pois")
# R0B1C1. Valhalla es el primer proveedor que NO es de un tercero —corre auto-hospedado— y
# aun así entra por la misma puerta. Con él, `_TIMEOUT` pasa a tener TRES dueños: 5.0 en
# Google, 6.0 en Overpass y 20.0 aquí. La tabla de pares aguanta; un diccionario habría
# dejado dos de los tres sin vigilar.
_VALHALLA = ("logger", "_TIMEOUT", "_CONTORNOS_DEFECTO", "isocrona")

# módulo destino → (su fichero, el fichero del que SALIÓ, sus símbolos)
_EXTRAIDO = (
    (providers, _PROV / "__init__.py", _APP / "rutas.py", _COMPARTIDO),
    (propia, _PROV / "propia.py", _APP / "rutas.py", _PROPIA),
    (google, _PROV / "google.py", _APP / "rutas.py", _GOOGLE),
    (nominatim, _PROV / "nominatim.py", _APP / "agent" / "tools.py", _NOMINATIM),
    (overpass, _PROV / "overpass.py", _APP / "walk_score.py", _OVERPASS),
    (valhalla, _PROV / "valhalla.py", _APP / "isocronas.py", _VALHALLA),
)

# ── Por qué esto son PARES y ya no un diccionario símbolo → módulo ────────────────────
# Desde que Overpass entró hay un HOMÓNIMO legítimo: `_TIMEOUT` vale 5.0 en Google y 6.0 en
# Overpass. Son los plazos de dos llamadas a dos terceros distintos, y fundirlos sería un
# cambio de comportamiento silencioso. Un diccionario símbolo → módulo los habría aplastado
# —la segunda entrada pisa a la primera— y la guarda habría dejado de mirar la mitad de lo
# que dice mirar. La guarda de «exactamente un fichero lo define» lo detectó en cuanto
# Overpass llegó, y por eso ahora la pregunta correcta no es «¿quién lo define?» sino
# «¿lo definen SUS dueños y nadie más?».
#
# Ojo con el par `_RADIO_M` (propia, 1500 m) y `_RADIUS_M` (Overpass, 1600 m): NO son
# homónimos, son dos nombres distintos que difieren solo en el idioma. Se dejan como
# están; unificar la ortografía obligaría a unificar el valor, que es otro radio.
_MOVIDOS = tuple((m, n) for m, _f, _o, ns in _EXTRAIDO for n in ns)
_IDS = [m.__name__.rsplit(".", 1)[-1] + ":" + n for m, n in _MOVIDOS]
_FICHERO = {m: f for m, f, _o, _ns in _EXTRAIDO}
_ORIGEN = {m: o for m, _f, o, _ns in _EXTRAIDO}

_DUENOS: dict[str, list[str]] = {}
for _m, _f, _o, _ns in _EXTRAIDO:
    for _n in _ns:
        _DUENOS.setdefault(_n, []).append(_f.name)

# Todos los ficheros que podrían estar definiendo un símbolo movido: los tres orígenes más
# el paquete entero. El glob hace que un provider futuro entre aquí sin que nadie lo añada.
def _ficheros_vigilados() -> list[Path]:
    return sorted({_APP / "rutas.py", _APP / "walk_score.py", _APP / "agent" / "tools.py",
                   _APP / "isocronas.py", *_PROV.glob("*.py")})

# Sonda de aislamiento: importa UN módulo en un intérprete limpio y delata lo que arrastró.
# Se comparte entre la guarda y su mitad negativa a propósito — si fueran dos sondas
# distintas, la negativa podría pasar por medir otra cosa.
_SONDA_AISLAMIENTO = (
    "import importlib, sys; importlib.import_module(%r); "
    "print(','.join(sorted(m for m in sys.modules "
    "if m in ('fastapi', 'app.rutas') "
    "or m.startswith(('fastapi.', 'app.routers', 'app.agent', 'app.rutas.')))))"
)

# Lo que NO se movió y esta unidad no autoriza mover: la política multi-proveedor.
_ORQUESTACION = ("_servicios_con_coords", "_recolectar_zona")

# ── Las fachadas son MÍNIMAS a propósito ─────────────────────────────────────────────
# Se reexporta lo que hace falta y solo eso: o lo sigue usando el código que se quedó, o lo
# importa un consumidor que esta unidad no toca. Reexportarlo todo habría inventado
# superficie pública que nunca existió, y cada nombre de más es un compromiso que alguien
# acabará usando.
# Cada entrada declara de QUÉ provider viene, no solo el nombre: `_TIMEOUT` lo reexportan
# dos fachadas distintas desde dos providers distintos, y comprobar la identidad contra el
# provider equivocado pasaría en verde sin medir nada.
_FACHADA_RUTAS = {
    "_CATS_ENTORNO": (propia, "lo usa `_servicios_con_coords` para calcular los huecos"),
    "_TRANSPORTE_MASIVO": (propia, "lo usa `_panorama_transporte`"),
    "_servicios_propios": (propia, "lo llaman `_servicios_con_coords` y `entorno_curable`"),
    "_nearest_propio": (propia, "lo llama `comando_mapa`"),
    "_avisar_capa_caida": (propia, "lo importa `tests/test_curacion_propaga.py`"),
    "verificacion_de_entorno": (propia, "lo importan `app/decision/assembler.py`, "
                                        "`app/routers/assets.py` y `app/routers/chat.py`"),
    "_TIMEOUT": (google, "lo usan los sitios de llamada heredados de la prosa"),
    "_ruta_a_pie": (google, "lo llaman `_recolectar_zona`, `comando_mapa` y `rutas_desde`"),
    "_nearest_categoria": (google, "lo llaman `_servicios_con_coords`, `comando_mapa` y "
                                   "`recorrido_zona`"),
    "_mejor_transporte": (google, "lo llaman `_servicios_con_coords` y `recorrido_zona`"),
    # `rutas` no es fachada de esto: es CONSUMIDOR. Liga `isocrona` a nivel de módulo desde
    # `app/rutas.py:34` —desde mucho antes de esta unidad, y R0B1C1 no toca ese fichero— y
    # la usa en `_accion_isocrona`. Se declara aquí porque desde fuera se ve igual: el
    # nombre está en su espacio y por tanto es su punto de parcheo efectivo.
    "isocrona": (valhalla, "lo liga `app/rutas.py:34` y lo usa `_accion_isocrona`"),
}

# R0B1B añade dos fachadas más, en los dos módulos de los que salieron los proveedores.
# Ninguna de las dos reexporta hacia `rutas.py`: `app/rutas.py` no se toca en esta unidad.
_FACHADA_TOOLS = {
    "_reverse_geocode": (nominatim,
                         "lo importan DIFERIDO las tres funciones de `app/rutas.py`, y ese "
                         "import es el punto de parcheo que el baseline de R0B0 espía"),
}
_FACHADA_WALK = {
    "_fetch_pois": (overpass, "lo importa a nivel de módulo `app/routers/assets.py`"),
    "_TIMEOUT": (overpass, "es el valor por defecto de `walk_score_para`, que se queda"),
}
# La cuarta fachada. `app/isocronas.py` conserva los cuatro nombres que se fueron porque los
# tres eran superficie histórica suya: `app/rutas.py` liga `isocrona` a nivel de módulo,
# `app/routers/assets.py` la importa diferida desde aquí, y dos scripts también.
_FACHADA_ISO = {
    "isocrona": (valhalla, "la ligan `app/rutas.py`, `app/routers/assets.py` y dos scripts"),
    "_TIMEOUT": (valhalla, "superficie histórica del módulo"),
    "_CONTORNOS_DEFECTO": (valhalla, "superficie histórica del módulo"),
    "logger": (valhalla, "el logger operativo, que conserva el nombre `app.isocronas`"),
}
_FACHADAS = ((rutas, _FACHADA_RUTAS), (tools, _FACHADA_TOOLS), (walk_score, _FACHADA_WALK),
             (isocronas, _FACHADA_ISO))
_PAR_FACHADA = tuple((mod, n) for mod, d in _FACHADAS for n in sorted(d))
_IDS_FACHADA = [mod.__name__.rsplit(".", 1)[-1] + ":" + n for mod, n in _PAR_FACHADA]


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
@pytest.mark.parametrize("modulo,simbolo", _MOVIDOS, ids=_IDS)
def test_el_cuerpo_vive_en_su_provider(modulo, simbolo):
    assert simbolo in _definidos_en(_FICHERO[modulo]), (
        f"`{simbolo}` debería estar DEFINIDO en {_FICHERO[modulo].name} y no lo está: la "
        f"extracción no lo movió, o lo movió a otro sitio.")


@pytest.mark.parametrize("modulo,simbolo", _MOVIDOS, ids=_IDS)
def test_el_modulo_de_origen_no_conserva_un_segundo_cuerpo(modulo, simbolo):
    """Mover, no copiar. El módulo del que salió puede IMPORTAR el nombre; no definirlo.

    El origen ya no es siempre `rutas.py`: Nominatim salió de `app/agent/tools.py` y
    Overpass de `app/walk_score.py`. Dos implementaciones del mismo nombre divergen en
    silencio — se arregla una y la otra sigue sirviendo la respuesta vieja.
    """
    origen = _ORIGEN[modulo]
    assert simbolo not in _definidos_en(origen), (
        f"`{simbolo}` sigue teniendo un cuerpo en `{origen.name}` además del de su "
        f"provider.")


@pytest.mark.parametrize("modulo,simbolo", _MOVIDOS, ids=_IDS)
def test_lo_definen_sus_duenos_y_nadie_mas(modulo, simbolo):
    """No «exactamente uno»: exactamente SUS dueños.

    `_TIMEOUT` y `_RADIO_M` son homónimos legítimos con dos dueños cada uno —plazos y
    radios de proveedores distintos, con valores distintos—. Exigir un único fichero los
    obligaría a fundirse, que es precisamente el cambio de comportamiento que estas
    guardas existen para impedir.
    """
    dueños = sorted(f.name for f in _ficheros_vigilados()
                    if simbolo in _definidos_en(f))
    assert dueños == sorted(_DUENOS[simbolo]), (
        f"`{simbolo}` está definido en {dueños}; sus dueños declarados son "
        f"{sorted(_DUENOS[simbolo])}.")


def test_el_homonimo_TIMEOUT_tiene_DOS_valores_y_no_debe_fundirse():
    """El contrapeso del anterior. Si algún día los dos plazos coincidieran, la guarda de
    arriba seguiría verde mientras el homónimo dejaba de tener sentido — y alguien lo
    «simplificaría» a una constante compartida, cambiando el plazo de un proveedor.

    Y el par que NO es homónimo pero lo parece: `_RADIO_M` y `_RADIUS_M` difieren solo en
    el idioma y son radios de consultas distintas. Unificar la ortografía obligaría a
    unificar el valor.
    """
    assert google._TIMEOUT == 5.0 and overpass._TIMEOUT == 6.0, (
        "los dos plazos son de llamadas distintas a terceros distintos")
    assert propia._RADIO_M == 1500 and overpass._RADIUS_M == 1600
    assert not hasattr(overpass, "_RADIO_M") and not hasattr(propia, "_RADIUS_M"), (
        "si ambos nombres existieran en ambos módulos, uno de los dos radios estaría "
        "duplicado y el siguiente refactor los fundiría")


@pytest.mark.parametrize("modulo,simbolo",
                         [(m, n) for m, n in _MOVIDOS if callable(getattr(m, n, None))],
                         ids=[i for (m, n), i in zip(_MOVIDOS, _IDS)
                              if callable(getattr(m, n, None))])
def test_el_modulo_declarado_del_objeto_es_su_provider(modulo, simbolo):
    """`__module__` es la respuesta del intérprete a «¿de dónde salió esto?». Si dice
    `app.rutas`, `app.agent.tools` o `app.walk_score`, el objeto que se está usando no es
    el que se movió."""
    assert getattr(modulo, simbolo).__module__ == modulo.__name__


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
@pytest.mark.parametrize("fachada,simbolo", _PAR_FACHADA, ids=_IDS_FACHADA)
def test_la_fachada_liga_el_mismo_objeto(fachada, simbolo):
    """`is`, no `==`: la fachada tiene que ligar EL MISMO objeto. Si fuera una copia,
    parchear uno dejaría al otro intacto y las dos mitades divergirían.

    Es la condición literal que el mandato exige para las dos nuevas:
    `tools._reverse_geocode is nominatim._reverse_geocode` y
    `walk_score._fetch_pois is overpass._fetch_pois`.
    """
    proveedor, _razon = dict(_FACHADAS)[fachada][simbolo]
    assert getattr(fachada, simbolo) is getattr(proveedor, simbolo)


@pytest.mark.parametrize("fachada,declarada",
                         [(rutas, _FACHADA_RUTAS), (tools, _FACHADA_TOOLS),
                          (walk_score, _FACHADA_WALK), (isocronas, _FACHADA_ISO)],
                         ids=["rutas", "tools", "walk_score", "isocronas"])
def test_la_fachada_no_reexporta_nada_de_mas(fachada, declarada):
    """Contrapeso del anterior. Reexportarlo todo haría pasar la guarda de arriba y además
    inventaría superficie pública que el módulo nunca tuvo — lo contrario de extraer. Cada
    nombre de cada fachada tiene aquí escrito quién lo necesita.
    """
    # Solo se miran los símbolos que esta unidad movió a un provider: que `walk_score`
    # siga definiendo `_haversine_m` no es reexportar nada.
    reexportados = {n for _m, n in _MOVIDOS if hasattr(fachada, n)}
    assert reexportados == set(declarada), (
        f"de más: {sorted(reexportados - set(declarada))} · "
        f"de menos: {sorted(set(declarada) - reexportados)}")


def test_rutas_NO_recibe_superficie_de_los_proveedores_nuevos():
    """R0B1B no toca `app/rutas.py`, y eso tiene que ser comprobable, no prometido.

    Si `_reverse_geocode` o `_fetch_pois` aparecieran en `rutas`, el import diferido habría
    dejado de serlo y el punto de parcheo del baseline se habría mudado sin que nadie lo
    dijera.

    `_TIMEOUT` se trata aparte y no por comodidad: `rutas._TIMEOUT` SÍ existe y es legítimo
    —es el de Google, reexportado desde R0B1A—. Comprobarlo por el nombre habría dado un
    falso positivo; lo que hay que comprobar es DE QUIÉN es el objeto.
    """
    for nombre in (*_NOMINATIM, *_OVERPASS):
        if nombre == "_TIMEOUT":
            continue
        assert not hasattr(rutas, nombre), (
            f"`rutas.{nombre}` existe: alguien repuntó un import y movió el seam.")
    assert rutas._TIMEOUT is google._TIMEOUT
    assert rutas._TIMEOUT is not overpass._TIMEOUT, (
        "`rutas._TIMEOUT` pasó a ser el de Overpass: eso cambia el plazo de las llamadas "
        "heredadas a Google de 5 s a 6 s")


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


# ═════════════════════════════════════════════════════════════════════════════════════
# (F) R0B1B — Nominatim y Overpass
#
# Dos extracciones que NO salieron de `rutas.py`, y eso cambia dos cosas. Primero, el
# módulo de origen es otro y las guardas de arriba ya lo leen de la tabla. Segundo, y más
# delicado: el seam de Nominatim NO vive donde vive el objeto. Los tres llamadores están
# en `app/rutas.py` y los tres importan DENTRO de la función, así que resuelven el atributo
# sobre `app.agent.tools` en cada ejecución. Por eso la fachada no es cortesía: es el punto
# de parcheo que el baseline de R0B0 espía, y moverlo habría roto sus pruebas de Nominatim.
# ═════════════════════════════════════════════════════════════════════════════════════
def test_el_import_diferido_de_rutas_sigue_apuntando_a_app_agent_tools():
    """La condición que hace que el baseline no cambie una línea.

    Si alguien repunta estos tres imports al módulo nuevo, `rutas` sigue sin tener el
    atributo —así que la guarda de `hasattr` seguiría verde— pero
    `monkeypatch.setattr(tools, "_reverse_geocode", ...)` deja de morder y las pruebas que
    cuentan Nominatim empiezan a salir a la red de verdad. Es un fallo silencioso, y por
    eso se comprueba el TEXTO del import y no solo el efecto.
    """
    fuente = (_APP / "rutas.py").read_text(encoding="utf-8")
    apariciones = fuente.count("from app.agent.tools import _reverse_geocode")
    assert apariciones == 3, (
        f"se esperaban los TRES imports diferidos desde `app.agent.tools` y hay "
        f"{apariciones}. Repuntarlos al provider mueve el seam del baseline.")
    assert "from app.place.providers.nominatim import" not in fuente, (
        "`rutas.py` no puede importar el provider directamente: esta unidad no lo toca, y "
        "hacerlo mudaría el punto de parcheo efectivo.")


def test_parchear_la_fachada_de_tools_SIGUE_alcanzando_a_los_llamadores(monkeypatch):
    """El seam de Nominatim, ejercitado y no razonado.

    `_reverse_geocode` ya no se define en `tools.py`, pero el import diferido de los
    llamadores hace `getattr` sobre ese módulo en cada llamada. Parchear la fachada tiene
    que seguir cambiando lo que ejecuta `recorrido_zona`.
    """
    doble = _spy({"texto": "doble", "barrio": None, "ciudad": None, "pais": None})
    monkeypatch.setattr(tools, "_reverse_geocode", doble)
    monkeypatch.setattr(rutas, "walk_score_para", _spy(None))
    monkeypatch.setattr(rutas, "_servicios_con_coords", _spy([]))
    monkeypatch.setattr(rutas, "_mejor_transporte", _spy(None))
    asyncio.run(rutas.recorrido_zona(-0.18, -78.48))
    assert doble.llamadas == 1, (
        "el doble no mordió: el import diferido dejó de resolver sobre `app.agent.tools`")


def test_parchear_el_PROVIDER_de_nominatim_no_alcanza_a_los_llamadores(monkeypatch):
    """LA MITAD NEGATIVA. `tools._reverse_geocode is nominatim._reverse_geocode` es cierto
    y aun así reasignar el provider NO cambia lo que ejecuta el llamador: lo que manda es
    dónde se resuelve el nombre en la llamada. Sin esta mitad, la de arriba no distinguiría
    «el seam se conservó» de «da igual dónde parchees»."""
    doble = _spy({"texto": "doble", "barrio": None, "ciudad": None, "pais": None})
    monkeypatch.setattr(nominatim, "_reverse_geocode", doble)
    monkeypatch.setattr(tools, "_reverse_geocode", _spy(None))   # el real no sale a la red
    monkeypatch.setattr(rutas, "walk_score_para", _spy(None))
    monkeypatch.setattr(rutas, "_servicios_con_coords", _spy([]))
    monkeypatch.setattr(rutas, "_mejor_transporte", _spy(None))
    asyncio.run(rutas.recorrido_zona(-0.18, -78.48))
    assert doble.llamadas == 0


def test_tool_geocode_address_conserva_sus_imports_de_geopy():
    """El geocodificado DIRECTO no se movió y sigue necesitando la clase `Nominatim` en
    `tools.py`. De eso depende, además, `tests/test_relacion_espacial_tools.py`, que
    parchea esa clase y que esta unidad no puede tocar. Limpiar el import «porque ya no se
    usa» rompería una prueba ajena sin que nada lo avisara aquí."""
    fuente = (_APP / "agent" / "tools.py").read_text(encoding="utf-8")
    assert "from geopy.geocoders import Nominatim" in fuente
    assert "from geopy.exc import GeocoderTimedOut, GeocoderUnavailable" in fuente
    assert hasattr(tools, "Nominatim") and hasattr(tools, "GeocoderTimedOut")
    # Y el cuerpo del directo sigue donde estaba, sin haberse ido de polizón.
    assert "_geocode_sync" in _identificadores(fuente)


def test_overpass_no_se_llevo_ni_una_linea_de_calculo():
    """El corte del mandato: el provider obtiene datos, Contexto calcula la caminabilidad.

    `PLAN04-1.2` ya adjudicó esta frontera en la evidencia —el puntaje va con
    `provider="contexto"` y solo los insumos con `provider="overpass"`—. Moverla al
    directorio equivocado la contradiría en la estructura.
    """
    calculo = ("_haversine_m", "_decay", "_matches", "compute_walk_score",
               "_clasificar_hub", "extraer_conectividad", "_CATEGORIES", "_TOTAL_WEIGHT",
               "_DENSITY_WEIGHTS", "_DENSITY_MAX", "_HUB_LABEL", "walk_score_para")
    en_overpass = _definidos_en(_PROV / "overpass.py")
    en_walk = _definidos_en(_APP / "walk_score.py")
    for nombre in calculo:
        assert nombre not in en_overpass, f"`{nombre}` es cálculo y se coló en el provider"
        assert nombre in en_walk, f"`{nombre}` desapareció de `app/walk_score.py`"


def test_walk_score_para_sigue_definido_en_walk_score():
    assert walk_score.walk_score_para.__module__ == "app.walk_score"
    assert "walk_score_para" not in _definidos_en(_PROV / "overpass.py")
    # Y su plazo por defecto no cambió al mudarse la constante.
    assert walk_score.walk_score_para.__defaults__ == (6.0,)


def test_el_import_historico_de_assets_sigue_alcanzando_el_provider():
    """`app/routers/assets.py` importa `_fetch_pois` de `app.walk_score` a nivel de módulo
    y esta unidad no lo toca. La fachada tiene que ligar el mismo objeto o
    `_recompute_walk_score` se queda sin proveedor."""
    import app.routers.assets as assets
    assert assets._fetch_pois is overpass._fetch_pois
    fuente = (_APP / "routers" / "assets.py").read_text(encoding="utf-8")
    assert "from app.place.providers" not in fuente, (
        "assets.py no debe importar el provider directamente: esta unidad no lo toca")


@pytest.mark.parametrize("modulo", ["app.place.providers.nominatim",
                                    "app.place.providers.overpass",
                                    "app.place.providers.valhalla"])
def test_los_providers_nuevos_se_importan_sin_arrastrar_la_aplicacion(modulo):
    """(C) Aislamiento, medido en un intérprete limpio: ni FastAPI, ni routers, ni agent,
    ni `app.rutas`. El AST solo ve los imports directos; esto ve los transitivos."""
    p = subprocess.run([sys.executable, "-c", _SONDA_AISLAMIENTO % modulo],
                       capture_output=True, text=True, cwd=str(_APP.parent), timeout=180)
    assert p.returncode == 0, p.stderr[-2000:]
    assert p.stdout.strip() == "", f"importar `{modulo}` arrastró {p.stdout.strip()}"


def test_la_guarda_de_aislamiento_SI_PUEDE_fallar():
    """Mitad negativa de (C): el mismo detector, contra un módulo que SÍ arrastra la
    aplicación. Si esto saliera limpio, el de arriba no estaría midiendo nada."""
    p = subprocess.run([sys.executable, "-c", _SONDA_AISLAMIENTO % "app.rutas"],
                       capture_output=True, text=True, cwd=str(_APP.parent), timeout=180)
    assert p.returncode == 0, p.stderr[-2000:]
    assert "app.rutas" in p.stdout, "el detector no ve ni lo que tiene delante"


def test_el_provider_de_overpass_conserva_su_degradacion_exacta(monkeypatch):
    """`None` cuando TODOS los mirrors fallan — no una lista vacía.

    La diferencia no es cosmética: una lista vacía significa «no hay nada alrededor» y hace
    que `PlaceContextV0` publique un cero medido; `None` significa «el proveedor no
    contestó» y cae a `insufficient_evidence`. Fundirlas fue el defecto que `PLAN04-1.2`
    corrigió. Aquí se ejercita con los dos mirrors caídos, y el tripwire garantiza que el
    fallo es el simulado y no una salida real a la red.
    """
    class _ClienteCaido:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            raise OSError("mirror caido")

    monkeypatch.setattr(overpass.httpx, "AsyncClient", _ClienteCaido)
    assert asyncio.run(overpass._fetch_pois(-0.18, -78.48)) is None
    assert len(overpass._OVERPASS_MIRRORS) == 2, "se intentan dos mirrors, no uno"
