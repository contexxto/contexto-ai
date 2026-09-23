"""PLAN04-2.3-R0A — el selector de categorías de Place: puro, constante y sin cablear.

QUÉ CONGELA ESTE FICHERO. Que `select_place_categories` devuelve HOY, y solo hoy, las seis
categorías de `_CATS_ENTORNO` en su orden; que ningún `BuyerContextV0` —ni siquiera uno
sintético con `place_preferences` que hablen de religión o de seguridad— mueve esa salida;
que el módulo no toca red, base, configuración ni providers; y que nadie en producción lo
llama todavía.

POR QUÉ CASI TODA PRUEBA AQUÍ TIENE MITAD NEGATIVA. Esta serie ya cazó una guarda nacida
muerta —un patrón cuyos `\\b` se volvieron bytes 0x08 al escribirlo, que no podía casar con
nada y pasaba en verde sobre el árbol que debía delatar—, y el arnés no la detectó porque
una guarda gemela sana cubría la misma invariante. La lección quedó escrita: **cada guarda
tiene que demostrar por sí misma que puede ponerse roja**. Aquí eso se traduce en que cada
comprobador se aplica también a material fabricado para que falle.

LO QUE ESTE FICHERO NO AFIRMA. No afirma que Contexto seleccione contexto dinámicamente.
`PRODUCTION_SELECTOR_CALLERS = 0` es una limitación declarada de R0A, y la sección (G) la
mide en vez de prometerla.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.contracts.buyer_v0 import (
    BuyerContextV0,
    CommuteAnchorV0,
    Direction,
    Financial,
    Mobility,
    Objective,
    PlacePreference,
    PropertyRequirements,
)
from app.contracts.common_v0 import Money
from app.place import selector
from app.place.selector import CATEGORIAS_POR_DEFECTO, select_place_categories

_RAIZ = Path(__file__).resolve().parents[1]
_APP = _RAIZ / "app"
_SELECTOR = _APP / "place" / "selector.py"
_PROPIA = _APP / "place" / "providers" / "propia.py"

# El conjunto de R0A, escrito a mano. Se repite aquí a propósito: si la prueba leyera la
# constante del módulo para compararla consigo misma, sería una tautología y la mutación
# «falta una de las seis» nacería inerte.
_SEIS = ("salud", "farmacia", "supermercado", "educacion", "parque", "centro_comercial")

# `D-2.3-b`: fuera del selector en esta fase. Están en el CHECK `ck_pois_categoria` de la
# migración 021, así que la capa propia sabe resolverlas — el punto es que el selector no
# las pida.
_SENSIBLES = ("iglesia", "seguridad")

_CUANDO = datetime(2026, 3, 4, 15, 0, tzinfo=timezone.utc)


def _comprador(**campos) -> BuyerContextV0:
    return BuyerContextV0(buyer_id="comprador-de-prueba", updated_at=_CUANDO, **campos)


# ══ (A) el conjunto de hoy, y su forma ══════════════════════════════════════════════

def test_A_un_comprador_minimo_recibe_las_seis_de_hoy():
    """§10-A. El caso base: nada declarado, el conjunto completo."""
    assert select_place_categories(_comprador()) == _SEIS


def test_A2_la_constante_del_modulo_es_exactamente_ese_conjunto():
    assert CATEGORIAS_POR_DEFECTO == _SEIS


def test_J_la_salida_es_una_tupla_y_no_un_conjunto_ni_una_lista():
    """§10-J. `set` y `frozenset` quedan prohibidos por medición, no por gusto: el orden
    de iteración de un conjunto de cadenas cambia con `PYTHONHASHSEED`. Una `list` se
    descarta por otra razón —es mutable, y quien la reciba puede alterar la constante
    compartida del módulo para todo el proceso—."""
    salida = select_place_categories(_comprador())
    assert type(salida) is tuple, f"la salida es {type(salida).__name__}"
    assert not isinstance(salida, (set, frozenset, list))


def test_J2_la_salida_no_se_puede_alterar_desde_fuera():
    with pytest.raises((AttributeError, TypeError)):
        select_place_categories(_comprador())[0] = "otra"  # type: ignore[index]


# ══ (B) el comprador NO mueve la salida — y eso es deliberado ═══════════════════════
#
# No significa que el selector futuro vaya a ignorar al comprador. Significa que la FASE 2
# es extracción sin cambiar comportamiento, así que R0A no puede estrenar reglas.

_COMPRADORES = {
    "vacío": {},
    "objective": {"objective": Objective.RENT},
    "presupuesto": {"financial": Financial(budget_max=Money(amount="90000", currency="USD"))},
    "requisitos del inmueble": {
        "property_requirements": PropertyRequirements(bedrooms_min=3, area_m2_min=80.0,
                                                      pets_allowed_required=True)},
    "etapa del embudo": {"stage": "explorando"},
    "place_preferences · áreas verdes": {
        "place_preferences": (PlacePreference(dimension="áreas verdes",
                                              direction=Direction.MORE),)},
    "place_preferences · caminabilidad": {
        "place_preferences": (PlacePreference(dimension="caminabilidad",
                                              direction=Direction.MORE),)},
    "place_preferences · ruido": {
        "place_preferences": (PlacePreference(dimension="ruido", direction=Direction.LESS),)},
    "place_preferences · tres a la vez": {
        "place_preferences": (
            PlacePreference(dimension="áreas verdes", direction=Direction.MORE),
            PlacePreference(dimension="supermercado", direction=Direction.MORE),
            PlacePreference(dimension="transporte", direction=Direction.MORE),
        )},
    "commute_anchors": {
        "mobility": Mobility(commute_anchors=(
            CommuteAnchorV0(anchor_id="ancla-1", label="la oficina",
                            raw_location="Av. Amazonas y Naciones Unidas"),))},
}


@pytest.mark.parametrize("nombre", sorted(_COMPRADORES), ids=sorted(_COMPRADORES))
def test_BCD_ningun_comprador_mueve_la_salida(nombre):
    """§10-B, §10-C y §10-D en una sola parametrización: campos irrelevantes para el
    lugar, `place_preferences` sintéticas y `commute_anchors` sintéticos dan los seis."""
    assert select_place_categories(_comprador(**_COMPRADORES[nombre])) == _SEIS


def test_BCD2_el_material_de_arriba_es_de_verdad_distinto():
    """LA MITAD NEGATIVA de la parametrización anterior.

    Si los diez compradores fueran el mismo objeto —un fallo de construcción fácil de no
    ver—, «ninguno mueve la salida» sería cierto y vacío. Aquí se comprueba que son diez
    contextos distintos y que cuatro de ellos traen de verdad señal de LUGAR, que es la
    que tendría que mover la salida el día que 2.3 se complete."""
    construidos = [_comprador(**c) for c in _COMPRADORES.values()]
    volcados = {b.model_dump_json() for b in construidos}
    assert len(volcados) == len(_COMPRADORES), "hay compradores duplicados en el material"
    con_senal_de_lugar = [b for b in construidos
                          if b.place_preferences or b.mobility.commute_anchors]
    assert len(con_senal_de_lugar) == 5, (
        f"el material no ejercita la señal de lugar: {len(con_senal_de_lugar)}")


def test_E_el_mismo_input_dos_veces_da_la_misma_salida():
    """§10-E."""
    comprador = _comprador(place_preferences=(PlacePreference(dimension="ruido"),))
    primera = select_place_categories(comprador)
    segunda = select_place_categories(comprador)
    assert primera == segunda
    assert list(primera) == list(segunda), "mismo contenido pero distinto orden"


def test_E2_el_selector_se_ejecuta_de_verdad(monkeypatch):
    """CONTRA LA PRUEBA QUE PASA SIN LLAMAR AL SELECTOR.

    Todo lo de arriba compara contra `_SEIS`, escrito a mano; nada impide que alguien
    «arregle» un fallo futuro haciendo que las pruebas lean la constante en vez de llamar
    a la función. Esta lo impide: se sabotea el cuerpo y las llamadas tienen que morir."""
    def _saboteado(_buyer):
        raise AssertionError("no se ejecutó el selector")

    monkeypatch.setattr(selector, "select_place_categories", _saboteado)
    with pytest.raises(AssertionError, match="no se ejecutó el selector"):
        selector.select_place_categories(_comprador())


# ══ (C) el orden es estable ENTRE PROCESOS ══════════════════════════════════════════

def _en_interprete_limpio(codigo: str, extra_env: dict[str, str] | None = None):
    """Un intérprete sin las variables del proyecto. `app.config` exige `POSTGRES_*` y en
    este árbol no hay `.env`, así que un módulo que arrastre configuración se cae aquí en
    vez de pasar en verde."""
    base = {k: v for k, v in os.environ.items()
            if k in ("PATH", "SYSTEMROOT", "SystemRoot", "PATHEXT", "TEMP", "TMP",
                     "COMSPEC", "WINDIR", "HOME", "USERPROFILE", "LANG")}
    base["PYTHONDONTWRITEBYTECODE"] = "1"
    base["PYTHONIOENCODING"] = "utf-8"
    if extra_env:
        base.update(extra_env)
    return subprocess.run([sys.executable, "-c", codigo], cwd=str(_RAIZ),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=base)


_SONDA_ORDEN = (
    "from datetime import datetime, timezone\n"
    "from app.contracts.buyer_v0 import BuyerContextV0\n"
    "from app.place.selector import select_place_categories\n"
    "b = BuyerContextV0(buyer_id='x', updated_at=datetime(2026,3,4,15,0,tzinfo=timezone.utc))\n"
    "print('|'.join(select_place_categories(b)))\n"
)


@pytest.mark.parametrize("semilla", ["0", "1", "2", "3", "4"])
def test_F_el_orden_no_depende_de_PYTHONHASHSEED(semilla):
    """§10-F. Medido antes de escribir esto: `frozenset` de estas seis cadenas da cinco
    órdenes distintos en cinco semillas. Por eso la salida es una tupla."""
    p = _en_interprete_limpio(_SONDA_ORDEN, {"PYTHONHASHSEED": semilla})
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == "|".join(_SEIS), f"semilla {semilla}: {p.stdout!r}"


def test_F2_la_sonda_de_orden_sabe_ver_un_orden_distinto():
    """LA MITAD NEGATIVA de F: si la sonda comparase de una forma insensible al orden, F
    pasaría con cualquier permutación. Aquí se comprueba contra la sonda misma."""
    p = _en_interprete_limpio(
        "from app.place.selector import CATEGORIAS_POR_DEFECTO as c\n"
        "print('|'.join(tuple(reversed(c))))\n", {"PYTHONHASHSEED": "0"})
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() != "|".join(_SEIS), "la comparación de F no distingue el orden"


# ══ (D) las categorías sensibles NO pueden aparecer · D-2.3-b ═══════════════════════

_TEXTOS_SENSIBLES = (
    "cerca de mi iglesia como comunidad",
    "quiero ambiente religioso",
    "seguridad",
    "zona segura",
    "barrio sin delincuencia",
    "iglesia",
    "seguridad de la zona",
    "templo cerca",
)


@pytest.mark.parametrize("texto", _TEXTOS_SENSIBLES)
def test_G_ningun_texto_del_comprador_amplia_la_allowlist(texto):
    """§10-G. Una `PlacePreference` sintética que hable de religión o de seguridad no
    puede ampliar la salida.

    ESTO NO ES UNA COMPUERTA DE FAIR HOUSING y no debe leerse como tal. R0A no importa ni
    implementa un segundo motor que juzgue texto: la protección es de FORMA —la salida es
    una constante contenida en una allowlist cerrada de seis—, así que mientras no se
    derive de texto libre no hay nada que un texto pueda ampliar. Cuando 2.3 empiece a
    leer al comprador, esta propiedad se pierde y hará falta una compuerta de verdad."""
    salida = select_place_categories(
        _comprador(place_preferences=(PlacePreference(dimension=texto,
                                                      direction=Direction.MORE),)))
    assert salida == _SEIS
    for sensible in _SENSIBLES:
        assert sensible not in salida


def test_G2_la_salida_esta_contenida_en_la_allowlist_cerrada():
    """La propiedad estructural, dicha una vez: salida ⊆ allowlist de seis."""
    assert set(select_place_categories(_comprador())) <= set(_SEIS)
    assert set(_SEIS).isdisjoint(_SENSIBLES)


def test_G3_la_guarda_de_sensibles_sabe_ver_una_intrusa():
    """LA MITAD NEGATIVA de G. La comprobación de arriba («no está en la salida») pasaría
    también si mirase el sitio equivocado. Se le da una salida contaminada y tiene que
    delatarla."""
    contaminada = _SEIS + ("iglesia",)
    assert any(s in contaminada for s in _SENSIBLES), (
        "la comprobación de categorías sensibles no ve una intrusa: está muerta")


def test_G4_el_selector_no_deriva_categorias_de_texto_libre():
    """La razón por la que G se sostiene, medida sobre el CÓDIGO y no sobre la salida.

    Si el cuerpo del selector nunca lee `place_preferences`, `soft_preferences` ni
    `hard_constraints`, ningún texto puede influir. El día que los lea, esta guarda cae y
    obliga a reabrir `D-2.3-b` — que es exactamente lo que debe pasar."""
    fuente = _SELECTOR.read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    cuerpo = next(n for n in arbol.body
                  if isinstance(n, ast.FunctionDef) and n.name == "select_place_categories")
    leidos = {n.attr for n in ast.walk(cuerpo) if isinstance(n, ast.Attribute)}
    for campo in ("place_preferences", "soft_preferences", "hard_constraints",
                  "mobility", "commute_anchors", "tradeoffs", "unresolved_questions"):
        assert campo not in leidos, f"el selector ya lee `{campo}`: D-2.3-b hay que reabrirla"


# ══ (E) pureza ═════════════════════════════════════════════════════════════════════

def _imports_de(fuente: str) -> set[str]:
    """Todo lo que importa un fichero, incluidos los imports DIFERIDOS dentro de una
    función: meter `import app.config` en un cuerpo es la forma obvia de burlar una
    guarda que solo mirase la cabecera. Por eso se recorre el árbol entero."""
    raices: set[str] = set()
    for n in ast.walk(ast.parse(fuente)):
        if isinstance(n, ast.Import):
            raices.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            if n.level:                       # relativo: `from .providers import x`
                raices.add("." * n.level + (n.module or ""))
            elif n.module:
                raices.add(n.module)
    return raices


def _imports_prohibidos(fuente: str) -> list[str]:
    """Lo único permitido es la biblioteca estándar y `app.contracts.*`. Todo lo demás
    —incluido cualquier otro `app.*` y cualquier paquete de terceros— sobra."""
    malos = []
    for modulo in sorted(_imports_de(fuente)):
        if modulo.startswith("app.contracts"):
            continue
        raiz = modulo.split(".")[0]
        if raiz != "app" and raiz in sys.stdlib_module_names:
            continue
        malos.append(modulo)
    return malos


def test_H_el_selector_solo_importa_stdlib_y_contratos():
    """§6 del mandato, medido por AST."""
    assert _imports_prohibidos(_SELECTOR.read_text(encoding="utf-8")) == []


_FUENTES_SUCIAS = {
    "app.config": "import app.config\n",
    "app.database": "from app.database import engine\n",
    "sqlalchemy": "import sqlalchemy\n",
    "httpx": "import httpx\n",
    "fastapi": "from fastapi import FastAPI\n",
    "starlette": "import starlette.responses\n",
    "langgraph": "import langgraph\n",
    "app.rutas": "from app.rutas import analizar_zona\n",
    "app.routers": "from app.routers import assets\n",
    "app.agent": "from app.agent.tools import tool_analyze_location\n",
    "un provider": "from app.place.providers.propia import _CATS_ENTORNO\n",
    "un provider, relativo": "from .providers import propia\n",
    "app.config, DIFERIDO": "def f():\n    import app.config\n    return app.config\n",
    "un provider, DIFERIDO": "def f():\n    from app.place.providers import google\n    return google\n",
}


@pytest.mark.parametrize("clase", sorted(_FUENTES_SUCIAS), ids=sorted(_FUENTES_SUCIAS))
def test_H2_el_comprobador_de_imports_caza_cada_clase_prohibida(clase):
    """LA MITAD NEGATIVA de H, una por cada clase de dependencia que §6 prohíbe. Que hoy
    el selector no las tenga no prueba nada sobre la guarda; esto sí."""
    assert _imports_prohibidos(_FUENTES_SUCIAS[clase]) != [], (
        f"el comprobador no ve `{clase}`: la guarda de pureza está muerta")


def test_H3_el_comprobador_no_da_falsos_positivos():
    """La otra mitad: lo permitido tiene que pasar, o la guarda sería igual de inútil."""
    limpia = ("from __future__ import annotations\n"
              "import re\n"
              "from dataclasses import dataclass\n"
              "from app.contracts.buyer_v0 import BuyerContextV0\n"
              "from app.contracts.place_v0 import MeasureStatus\n")
    assert _imports_prohibidos(limpia) == []


# La sonda NO pregunta «¿está `socket` cargado?», y la razón está medida: importar
# `app.contracts.buyer_v0` —que §6 permite— ya mete `socket` por su cuenta
# (`typing_extensions` → `asyncio` → `socket`). Preguntar por la PRESENCIA del módulo
# mediría esa herencia y no al selector. Lo que se mide es el DELTA: qué añade el selector
# por encima de lo que la dependencia permitida ya trajo. Eso se pone rojo con cualquier
# import nuevo, `socket` incluido, y no tiene ruido de línea base.
def _sonda_delta(objetivo: str) -> str:
    return ("import sys\n"
            "import app.contracts.buyer_v0\n"
            "antes = set(sys.modules)\n"
            f"import {objetivo}\n"
            "print('NUEVOS:' + ','.join(sorted(set(sys.modules) - antes)))\n")


def test_H4_el_selector_no_anade_nada_sobre_los_contratos():
    """La guarda de AST mira el fuente; esta mira el proceso, sin `POSTGRES_*` y sin
    `.env` — un módulo que rozara `app.config` ni siquiera importaría aquí."""
    p = _en_interprete_limpio(_sonda_delta("app.place.selector"))
    assert p.returncode == 0, f"el selector no importa en un entorno vacío:\n{p.stderr}"
    nuevos = [m for m in p.stdout.strip().removeprefix("NUEVOS:").split(",") if m]
    assert set(nuevos) <= {"app.place", "app.place.selector"}, (
        f"el selector arrastra módulos propios: {sorted(set(nuevos) - {'app.place', 'app.place.selector'})}")


def test_H5_la_sonda_de_delta_sabe_ponerse_roja():
    """LA MITAD NEGATIVA de H4. Se le da un módulo del que SÍ sabemos que arrastra base y
    configuración: si la sonda no delatara a ese, no estaría midiendo nada del otro."""
    p = _en_interprete_limpio(
        _sonda_delta("app.place.providers.propia"),
        {"POSTGRES_DB": "inerte", "POSTGRES_USER": "inerte", "POSTGRES_PASSWORD": "inerte"})
    assert p.returncode == 0, p.stderr
    nuevos = set(p.stdout.strip().removeprefix("NUEVOS:").split(","))
    assert {"app.config", "app.database", "sqlalchemy"} <= nuevos, (
        f"la sonda no delata a un módulo que sí arrastra: {sorted(nuevos)}")


def test_H5b_ningun_modulo_prohibido_por_nombre_se_cuela():
    """La lista explícita de §6, dicha aparte del delta: son dos formas de fallar y una
    puede sobrevivir a la otra si alguien relaja el conjunto esperado de H4."""
    p = _en_interprete_limpio(
        "import sys\n"
        "import app.place.selector\n"
        "malos = [m for m in ('app.config','app.database','app.rutas','app.routers',\n"
        "                     'app.agent','sqlalchemy','httpx','fastapi','starlette',\n"
        "                     'langgraph','app.place.providers','app.place.assembler')\n"
        "         if m in sys.modules]\n"
        "print('ARRASTRA:' + ','.join(malos) if malos else 'LIMPIO')\n")
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == "LIMPIO", p.stdout.strip()


# ── el tripwire dinámico: no basta con que hoy no lo haga ───────────────────────────
#
# Hereda la lección de R0B2A: una barrera que solo levanta una excepción puede ser
# absorbida por un `except` de paso, así que esta REGISTRA además de levantar, y lo que se
# afirma es el registro. Hereda de `BaseException` para no caer en un `except Exception`.

class _EfectoProhibido(BaseException):
    pass


@pytest.fixture
def tripwire(monkeypatch):
    """Arma las barreras y devuelve el registro de intentos."""
    intentos: list[str] = []

    def _barrera(etiqueta):
        def _disparo(*_a, **_k):
            intentos.append(etiqueta)
            raise _EfectoProhibido(etiqueta)
        return _disparo

    import builtins
    import socket
    monkeypatch.setattr(socket, "socket", _barrera("socket.socket"))
    monkeypatch.setattr(socket, "create_connection", _barrera("socket.create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", _barrera("socket.getaddrinfo"))
    monkeypatch.setattr(builtins, "open", _barrera("open"))
    monkeypatch.setattr(os, "getenv", _barrera("os.getenv"))
    monkeypatch.setattr(os.environ, "get", _barrera("os.environ.get"))
    return intentos


def test_H6_llamar_al_selector_no_toca_red_ni_ficheros_ni_entorno(tripwire):
    """§10-H y §11. Con las barreras armadas, la llamada tiene que pasar sin rozarlas."""
    for campos in ({}, {"place_preferences": (PlacePreference(dimension="ruido"),)}):
        assert select_place_categories(_comprador(**campos)) == _SEIS
    assert tripwire == [], f"el selector tocó algo prohibido: {tripwire}"


@pytest.mark.parametrize("efecto", ["socket", "fichero", "entorno"])
def test_H7_el_tripwire_dispara_de_verdad(tripwire, efecto):
    """LA MITAD NEGATIVA del tripwire, una por clase de efecto. Sin esto, `tripwire == []`
    sería cierto tanto si el selector es puro como si las barreras no estuvieran puestas."""
    import socket
    with pytest.raises(_EfectoProhibido):
        if efecto == "socket":
            socket.socket()
        elif efecto == "fichero":
            open(__file__)  # noqa: SIM115
        else:
            os.getenv("PATH")
    assert len(tripwire) == 1, "la barrera levantó la excepción pero no dejó rastro"


# ══ (F) PLACE-SELECTOR-DUAL-DEFAULT-01 · la coherencia con `_CATS_ENTORNO` ══════════

def _literal_de_modulo(fuente: str, nombre: str) -> tuple[str, ...] | None:
    """El valor de una asignación de nivel de módulo, leído del FUENTE.

    Por AST y no importando: cargar `propia.py` traería `app.config` y `sqlalchemy` a este
    proceso, que es justo lo que el selector no puede tocar — y una guarda que para medir
    la pureza tuviera que romperla no serviría de nada."""
    for n in ast.parse(fuente).body:
        objetivo = None
        if isinstance(n, ast.Assign):
            objetivo = next((t.id for t in n.targets if isinstance(t, ast.Name)), None)
            valor = n.value
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            objetivo, valor = n.target.id, n.value
        if objetivo == nombre and valor is not None:
            return tuple(ast.literal_eval(valor))
    return None


def test_I_el_default_del_selector_coincide_con_CATS_ENTORNO():
    """§8 del mandato. La duplicación es declarada y temporal; esta guarda es el precio.

    `PLACE-SELECTOR-DUAL-DEFAULT-01 · TEMPORARY UNTIL RUNTIME WIRING`. Se paga moviendo la
    constante cuando exista cableado, NO creando una dependencia `selector ↔ provider`."""
    del_selector = _literal_de_modulo(_SELECTOR.read_text(encoding="utf-8"),
                                      "CATEGORIAS_POR_DEFECTO")
    del_provider = _literal_de_modulo(_PROPIA.read_text(encoding="utf-8"), "_CATS_ENTORNO")
    assert del_selector is not None, "no se encontró `CATEGORIAS_POR_DEFECTO` en el selector"
    assert del_provider is not None, "no se encontró `_CATS_ENTORNO` en el provider"
    assert del_selector == del_provider, (
        f"divergieron: selector={del_selector} · provider={del_provider}")
    assert del_selector == _SEIS


def test_I2_el_lector_de_literales_encuentra_las_dos_de_verdad():
    """LA MITAD NEGATIVA más importante de I: si el lector devolviera `None` en los dos
    ficheros, la comparación de arriba sería `None == None` y pasaría para siempre."""
    assert _literal_de_modulo(_SELECTOR.read_text(encoding="utf-8"),
                              "CATEGORIAS_POR_DEFECTO") is not None
    assert _literal_de_modulo(_PROPIA.read_text(encoding="utf-8"), "_CATS_ENTORNO") is not None
    assert _literal_de_modulo("X = 1\n", "NO_ESTA") is None


@pytest.mark.parametrize(
    "caso, a, b",
    [
        ("falta una", "A: tuple = ('x', 'y')\n", "B = ['x']\n"),
        ("sobra una", "A: tuple = ('x',)\n", "B = ['x', 'y']\n"),
        ("otro orden", "A: tuple = ('x', 'y')\n", "B = ['y', 'x']\n"),
        ("otra cadena", "A: tuple = ('x', 'y')\n", "B = ['x', 'z']\n"),
    ],
)
def test_I3_la_guarda_de_coherencia_ve_cada_forma_de_divergir(caso, a, b):
    """LA MITAD NEGATIVA de I. Incluye el caso «otro orden», que es el que una comparación
    por conjuntos dejaría pasar en silencio."""
    assert _literal_de_modulo(a, "A") != _literal_de_modulo(b, "B"), caso


def test_I4_la_guarda_de_coherencia_acepta_lo_que_SI_coincide():
    assert _literal_de_modulo("A: tuple = ('x', 'y')\n", "A") == \
           _literal_de_modulo("B = ['x', 'y']\n", "B")


# ══ (G) R0A no está cableado — y se mide, no se promete ════════════════════════════

def test_PRODUCTION_SELECTOR_CALLERS_es_cero():
    """`PRODUCTION_SELECTOR_CALLERS = 0`.

    Esto NO es un criterio de cierre de 2.3 ni una virtud: es la limitación deliberada de
    R0A. La unidad que cablee el selector tendrá que cambiar esta guarda a propósito, que
    es justo lo que se quiere — que nadie lo conecte sin darse cuenta."""
    llamadores = []
    for fichero in sorted(_APP.rglob("*.py")):
        if fichero == _SELECTOR:
            continue
        texto = fichero.read_text(encoding="utf-8")
        if "place.selector" in texto or "select_place_categories" in texto:
            llamadores.append(str(fichero.relative_to(_RAIZ)))
    assert llamadores == [], f"R0A no cablea, y alguien lo cableó: {llamadores}"


def test_la_guarda_de_cableado_sabe_ver_un_llamador(tmp_path):
    """LA MITAD NEGATIVA de la anterior: un barrido que mirase el sitio equivocado daría
    «cero llamadores» para siempre."""
    (tmp_path / "falso.py").write_text(
        "from app.place.selector import select_place_categories\n", encoding="utf-8")
    encontrados = [f.name for f in tmp_path.rglob("*.py")
                   if "place.selector" in f.read_text(encoding="utf-8")]
    assert encontrados == ["falso.py"], "el barrido de llamadores no ve un import directo"
