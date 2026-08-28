"""E3.2b.5 · la sombra falla CERRADA — el flag ya no alcanza para correr.

E3.2b.4 dejó la cadena conectada tras un booleano. Cerrado ese gate supimos algo que cambia
el cálculo: **la sombra hace `commit()`**. Encender el flag no es "empezar a observar", es
empezar a escribir memoria durable de personas reales. Un solo booleano no puede ser la
distancia entre `OFF` y *todos los autenticados*.

La decisión congelada, y es una CONJUNCIÓN:

```
buyer_updater_shadow == True   AND   user_id ∈ allowlist   →   puede correr
```

Todo lo demás es NADIE. En particular estas tres, que son las que un rollout suele
regalarse por comodidad y aquí están prohibidas por test:

```
allowlist vacía        →  NADIE   (nunca "entonces todos")
"*" en la allowlist    →  NADIE   (no hay comodín)
flag apagado           →  NADIE   (aunque el usuario esté allowlisted)
```

Este fichero es casi todo garantías negativas por el mismo motivo que
`test_buyer_sombra.py`: el radio de explosión de equivocarse aquí no se nota hasta que ya
hay estado escrito de alguien que nunca debió entrar al canary.
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
import re

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.buyer import sombra
from app.buyer.actualizador import EstadoActualizacion, ResultadoUpdater
from app.buyer.sombra import actualizar_en_sombra

CANARY = "11111111-1111-4111-8111-111111111111"
OTRO = "22222222-2222-4222-8222-222222222222"


class _Usuario:
    def __init__(self, user_id=CANARY):
        self.user_id = user_id


def _mensajes(texto="máximo 120000 USD", mid="m-1"):
    return [HumanMessage(content=texto, id=mid), AIMessage(content="respuesta")]


@pytest.fixture
def banco(monkeypatch):
    """Deja la sombra lista para correr salvo por la POLÍTICA, que es lo que se mide aquí.

    Devuelve dos listas: a quién se llamó al updater y cuántas veces se abrió la base. La
    segunda existe porque "no llegó al updater" y "no tocó la base" son propiedades distintas
    y sólo la segunda descarta que un no-autorizado consuma una conexión del pool.
    """
    monkeypatch.setattr(sombra.settings, "buyer_updater_shadow", True)
    monkeypatch.setattr(sombra, "_allowlist_vacia_avisado", False, raising=False)
    llamadas, sesiones = [], []

    async def _actualizar(buyer_id, mensaje, *, retrieved_at, db=None, **kw):
        llamadas.append(buyer_id)
        return ResultadoUpdater(EstadoActualizacion.CREADA, revision=0)

    async def _hay_esquema(_db):
        return True

    class _Sesion:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def commit(self): pass
        async def rollback(self): pass

    def _abrir():
        sesiones.append(1)
        return _Sesion()

    monkeypatch.setattr(sombra, "actualizar", _actualizar)
    monkeypatch.setattr(sombra, "_hay_esquema", _hay_esquema)
    monkeypatch.setattr("app.database.AsyncSessionLocal", _abrir)
    return llamadas, sesiones


def _allowlist(monkeypatch, valor):
    monkeypatch.setattr(sombra.settings, "buyer_shadow_allowlist", valor, raising=False)


# ══ 1 · el default no habilita a nadie ══════════════════════════════════════════════


def test_la_allowlist_viene_VACIA_de_fabrica():
    """Igual que el flag: el default ES la decisión. Que el repo no traiga a nadie dentro
    obliga a que habilitar el canary sea un acto por entorno."""
    from app.config import Settings

    assert Settings().buyer_shadow_allowlist == ""


def test_con_la_allowlist_VACIA_no_pasa_NADIE_aunque_el_flag_este_ENCENDIDO(banco, monkeypatch):
    """La trampa concreta que este test prohíbe: leer una allowlist vacía como "sin
    restricción". Es el default de media docena de sistemas de feature flags y convertiría
    encender el flag en abrir la puerta a todos los autenticados."""
    llamadas, sesiones = banco
    _allowlist(monkeypatch, "")

    asyncio.run(actualizar_en_sombra(_Usuario(), _mensajes()))

    assert llamadas == [], "una allowlist vacía dejó correr al updater"
    assert sesiones == [], "una allowlist vacía abrió una sesión de base"


# ══ 2 · la conjunción, no la disyunción ═════════════════════════════════════════════


def test_solo_el_usuario_ALLOWLISTED_llega_al_updater(banco, monkeypatch):
    llamadas, _ = banco
    _allowlist(monkeypatch, CANARY)

    asyncio.run(actualizar_en_sombra(_Usuario(CANARY), _mensajes()))

    assert llamadas == [CANARY]


def test_un_usuario_FUERA_de_la_allowlist_no_llega_al_updater(banco, monkeypatch):
    """El canary encierra el radio de explosión. Un segundo usuario autenticado del mismo
    despliegue tiene que seguir sin memoria durable."""
    llamadas, sesiones = banco
    _allowlist(monkeypatch, CANARY)

    asyncio.run(actualizar_en_sombra(_Usuario(OTRO), _mensajes()))

    assert llamadas == []
    assert sesiones == []


def test_el_flag_APAGADO_gana_aunque_el_usuario_este_ALLOWLISTED(banco, monkeypatch):
    """Es una CONJUNCIÓN. Poblar la allowlist no puede encender nada por su cuenta: si
    bastara con estar en la lista, el interruptor de apagado dejaría de existir."""
    llamadas, _ = banco
    monkeypatch.setattr(sombra.settings, "buyer_updater_shadow", False)
    _allowlist(monkeypatch, CANARY)

    asyncio.run(actualizar_en_sombra(_Usuario(CANARY), _mensajes()))

    assert llamadas == []


@pytest.mark.parametrize("usuario", [None, _Usuario(""), _Usuario("   ")])
def test_un_ANONIMO_no_pasa_ni_con_la_allowlist_POBLADA(usuario, banco, monkeypatch):
    """La puerta de AUTH sigue delante. Sin raíz no hay comprador, y una allowlist poblada
    no puede fabricar una."""
    llamadas, _ = banco
    _allowlist(monkeypatch, f"{CANARY},{OTRO}, ,")

    asyncio.run(actualizar_en_sombra(usuario, _mensajes()))

    assert llamadas == []


# ══ 3 · las formas de abrir la puerta sin querer ════════════════════════════════════


@pytest.mark.parametrize("comodin", ["*", "all", "ALL", "true", "1", "%"])
def test_NINGUN_comodin_abre_la_allowlist(comodin, banco, monkeypatch):
    """No hay valor mágico. `*` es un identificador literal que nadie tiene, y por eso la
    respuesta correcta a `*` es exactamente la misma que a una lista vacía: nadie.

    Se prueba con seis por lo mismo que el guard de producción se reescribió como lista
    blanca: enumerar lo prohibido falla en cuanto aparece un nombre nuevo. Aquí lo que se
    afirma es que el mecanismo NO tiene rama de comodín, y por eso da igual cuál se pruebe.
    """
    llamadas, _ = banco
    _allowlist(monkeypatch, comodin)

    asyncio.run(actualizar_en_sombra(_Usuario(CANARY), _mensajes()))

    assert llamadas == [], f"{comodin!r} funcionó como comodín"


@pytest.mark.parametrize("intruso", [
    CANARY[:20],                    # prefijo del allowlisted
    CANARY + "-extra",              # el allowlisted es prefijo suyo
    CANARY[8:],                     # subcadena interior
])
def test_la_allowlist_no_abre_por_PREFIJO_ni_por_SUBCADENA(intruso, banco, monkeypatch):
    """Pertenencia a un conjunto, no `in` sobre la cadena de configuración. Con `in` sobre
    el string crudo, `"1111" in "1111...,2222..."` es cierto y cualquier id que sea trozo de
    otro entra. Es el fallo clásico de esta forma de allowlist."""
    llamadas, _ = banco
    _allowlist(monkeypatch, f"{CANARY},{OTRO}")

    asyncio.run(actualizar_en_sombra(_Usuario(intruso), _mensajes()))

    assert llamadas == [], f"{intruso!r} entró por coincidencia parcial"


def test_la_allowlist_tolera_el_FORMATO_que_escribe_una_persona(banco, monkeypatch):
    """Espacios alrededor, entradas vacías por comas de más y mayúsculas: un UUID es hex y
    su comparación es insensible a caja por definición. Tolerar esto no abre nada —el
    conjunto sigue siendo cerrado— y evita que un canary quede silenciosamente apagado
    porque alguien pegó el id en mayúsculas."""
    llamadas, _ = banco
    _allowlist(monkeypatch, f"  {OTRO} , , {CANARY.upper()}  ,")

    asyncio.run(actualizar_en_sombra(_Usuario(CANARY), _mensajes()))

    assert llamadas == [CANARY]


# ══ 4 · observabilidad y aislamiento, que no se pierden ═════════════════════════════


def test_encender_el_flag_SIN_allowlist_avisa_UNA_vez(banco, monkeypatch, caplog):
    """Flag encendido y allowlist vacía es una CONFIGURACIÓN ROTA, no un estado de reposo:
    alguien creyó que activó el canary. Se avisa —para que sea diagnosticable— y una sola
    vez, por el mismo motivo que la puerta del esquema: es una condición estable y repetirla
    por turno ahogaría el log."""
    _allowlist(monkeypatch, "")

    with caplog.at_level(logging.WARNING, logger="app.buyer.sombra"):
        for _ in range(3):
            asyncio.run(actualizar_en_sombra(_Usuario(), _mensajes()))

    avisos = [r for r in caplog.records if "allowlist" in r.message.lower()]
    assert len(avisos) == 1, f"se avisó {len(avisos)} veces"


def test_un_usuario_RECHAZADO_no_deja_rastro_por_turno(banco, monkeypatch, caplog):
    """El rechazo es el caso NORMAL de un canary: todos los demás usuarios pasan por aquí en
    cada turno. Registrarlo convertiría el log en una lista de quién conversó."""
    llamadas, _ = banco
    _allowlist(monkeypatch, CANARY)

    with caplog.at_level(logging.INFO, logger="app.buyer.sombra"):
        for _ in range(3):
            asyncio.run(actualizar_en_sombra(_Usuario(OTRO), _mensajes()))

    assert llamadas == []
    assert caplog.records == [], f"el rechazo dejó rastro: {[r.message for r in caplog.records]}"


def test_un_fallo_con_el_usuario_ALLOWLISTED_sigue_AISLADO(banco, monkeypatch, caplog):
    """La garantía de E3.2b.4 no se pierde al añadir la puerta: el turno ya respondió."""
    _allowlist(monkeypatch, CANARY)

    async def _explota(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(sombra, "actualizar", _explota)

    with caplog.at_level(logging.ERROR, logger="app.buyer.sombra"):
        asyncio.run(actualizar_en_sombra(_Usuario(CANARY), _mensajes()))

    assert any("aislado" in r.message for r in caplog.records), "el fallo quedó invisible"


# ══ 5 · el identificador no vive en el repositorio ══════════════════════════════════


def test_NINGUN_identificador_de_canary_esta_HARDCODEADO():
    """El id habilitado sale de configuración y nunca del código. Un UUID literal en la
    política sería un canary que viaja en el deploy: imposible de apagar sin release, e
    imposible de saber quién es leyendo el panel del entorno."""
    raiz = pathlib.Path(__file__).resolve().parent.parent
    uuid_literal = re.compile(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

    culpables = []
    for py in [*(raiz / "app" / "buyer").rglob("*.py"), raiz / "app" / "config.py"]:
        if "__pycache__" in py.parts:
            continue
        if uuid_literal.search(py.read_text(encoding="utf-8")):
            culpables.append(str(py.relative_to(raiz)).replace("\\", "/"))

    assert culpables == [], f"hay un identificador hardcodeado en {culpables}"
