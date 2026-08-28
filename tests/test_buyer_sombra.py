"""E3.2b.4 · shadow wiring · lo que la sombra NO puede hacer.

Ésta es la primera unidad de la fase que toca producción, así que casi todo lo que hay aquí
son garantías negativas. Las tres que el encargo congela:

```
1  procesa el HumanMessage REAL de un usuario autenticado
2  persiste sin romper el carril legacy
3  cualquier fallo suyo queda aislado y observable
```

La 3 es la que más tests tiene, porque es la única cuya violación no se nota hasta que un
usuario se queda sin respuesta.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.buyer import sombra
from app.buyer.actualizador import EstadoActualizacion, ResultadoUpdater
from app.buyer.sombra import actualizar_en_sombra

B1 = "11111111-1111-4111-8111-111111111111"


class _Usuario:
    def __init__(self, user_id=B1):
        self.user_id = user_id


def _mensajes(texto="máximo 120000 USD", mid="m-1"):
    return [HumanMessage(content=texto, id=mid), AIMessage(content="respuesta")]


@pytest.fixture
def encendida(monkeypatch):
    """Enciende el flag y neutraliza la base: estos tests miden la POLÍTICA de la sombra."""
    monkeypatch.setattr(sombra.settings, "buyer_updater_shadow", True)
    llamadas = []

    async def _actualizar(buyer_id, mensaje, *, retrieved_at, db=None, **kw):
        llamadas.append({"buyer_id": buyer_id, "mensaje": mensaje,
                         "retrieved_at": retrieved_at})
        return ResultadoUpdater(EstadoActualizacion.CREADA, revision=0)

    async def _hay_esquema(_db):
        return True

    class _Sesion:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def commit(self): pass
        async def rollback(self): pass

    monkeypatch.setattr(sombra, "actualizar", _actualizar)
    monkeypatch.setattr(sombra, "_hay_esquema", _hay_esquema)
    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: _Sesion())
    return llamadas


# ══ 1 · procesa el mensaje REAL del usuario autenticado ═════════════════════════════


def test_usa_el_HumanMessage_real_y_su_id(encendida):
    """La costura de F3.0b —`ultimo_mensaje_usuario_identificado`— llevaba desde su creación
    sin consumidor. Éste es el primero, y usa el `id` que LangGraph asignó: no lo fabrica ni
    lo deriva del texto, porque es lo que la procedencia va a citar."""
    asyncio.run(actualizar_en_sombra(_Usuario(), _mensajes(mid="msg-real-42")))

    assert len(encendida) == 1
    assert encendida[0]["mensaje"].message_id == "msg-real-42"
    assert encendida[0]["mensaje"].text == "máximo 120000 USD"


def test_la_raiz_es_el_usuario_autenticado(encendida):
    asyncio.run(actualizar_en_sombra(_Usuario("otro-uid"), _mensajes()))
    assert encendida[0]["buyer_id"] == "otro-uid"


def test_el_instante_de_procesamiento_lo_pone_la_SOMBRA_no_el_reducer(encendida):
    """R-IDEMP-1: el reducer no tiene reloj a propósito. `retrieved_at` es el instante real en
    que procesamos y entra como dato desde aquí."""
    asyncio.run(actualizar_en_sombra(_Usuario(), _mensajes()))
    assert encendida[0]["retrieved_at"].tzinfo is not None


# ══ 2 · las cuatro puertas ══════════════════════════════════════════════════════════


def test_con_el_flag_APAGADO_no_se_ejecuta_ni_una_linea(monkeypatch):
    """El default es la decisión: la cadena corre contra la memoria durable de una persona
    real, así que encenderla tiene que ser un acto deliberado y no algo que llegue con un
    deploy."""
    monkeypatch.setattr(sombra.settings, "buyer_updater_shadow", False)
    llamado = []
    monkeypatch.setattr(sombra, "actualizar",
                        lambda *a, **k: llamado.append(1))

    asyncio.run(actualizar_en_sombra(_Usuario(), _mensajes()))
    assert llamado == []


def test_el_flag_viene_APAGADO_de_fabrica():
    from app.config import Settings

    assert Settings().buyer_updater_shadow is False


@pytest.mark.parametrize("usuario", [None, _Usuario(""), _Usuario("   ")])
def test_un_ANONIMO_no_crea_estado_durable(usuario, encendida):
    """No es un error del turno: es que no hay comprador. El anónimo conversa igual."""
    asyncio.run(actualizar_en_sombra(usuario, _mensajes()))
    assert encendida == []


def test_sin_mensaje_de_usuario_no_se_hace_nada(encendida):
    asyncio.run(actualizar_en_sombra(_Usuario(), [AIMessage(content="hola")]))
    assert encendida == []


def test_sin_ESQUEMA_la_sombra_se_calla_y_avisa_UNA_vez(monkeypatch, caplog):
    """Un despliegue sin migrar es una condición estable: repetir la traza en cada turno
    ahogaría el log sin añadir información."""
    monkeypatch.setattr(sombra.settings, "buyer_updater_shadow", True)
    monkeypatch.setattr(sombra, "_esquema_ausente_avisado", False)

    class _Sesion:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def execute(self, *a, **k):
            class R:
                def scalar(self_): return False
            return R()

    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: _Sesion())
    llamado = []
    monkeypatch.setattr(sombra, "actualizar", lambda *a, **k: llamado.append(1))

    with caplog.at_level(logging.WARNING):
        asyncio.run(actualizar_en_sombra(_Usuario(), _mensajes()))
        asyncio.run(actualizar_en_sombra(_Usuario(), _mensajes()))

    assert llamado == []
    assert sum("falta la tabla" in r.message for r in caplog.records) == 1


# ══ 3 · AISLAMIENTO · la garantía que nadie nota hasta que falla ════════════════════


@pytest.mark.parametrize("explota", [
    RuntimeError("el modelo se cayó"),
    ValueError("dato corrupto"),
    ConnectionError("la base no responde"),
])
def test_NINGUN_fallo_del_updater_se_propaga_al_turno(explota, monkeypatch, caplog):
    """LA GARANTÍA DE ESTA UNIDAD. El turno ya respondió cuando esto empieza; una excepción
    que escapara de aquí llegaría al `create_task` y, según el runtime, a un
    `unhandled exception` — ruido en producción por una capa que aún no da valor."""
    monkeypatch.setattr(sombra.settings, "buyer_updater_shadow", True)

    async def _revienta(*a, **k):
        raise explota

    monkeypatch.setattr(sombra, "_hay_esquema", _revienta)

    class _Sesion:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: _Sesion())

    with caplog.at_level(logging.ERROR):
        asyncio.run(actualizar_en_sombra(_Usuario(), _mensajes()))   # no levanta

    assert any("quedó aislado" in r.message for r in caplog.records), \
        "el fallo se tragó sin dejar rastro: aislado NO es invisible"


def test_la_sombra_no_devuelve_nada_al_turno(encendida):
    """Su firma es la garantía estructural: aunque alguien quisiera usar su salida para
    cambiar la respuesta, no hay salida que usar."""
    assert asyncio.run(actualizar_en_sombra(_Usuario(), _mensajes())) is None


@pytest.mark.parametrize("estado,nivel", [
    (EstadoActualizacion.FALLIDO, logging.ERROR),
    (EstadoActualizacion.CONFLICTO, logging.WARNING),
    (EstadoActualizacion.CREADA, logging.INFO),
    (EstadoActualizacion.NO_OP, logging.INFO),
    (EstadoActualizacion.REPLAY, logging.INFO),
    (EstadoActualizacion.VACIO, logging.INFO),
])
def test_cada_desenlace_deja_rastro_con_su_nivel(estado, nivel, monkeypatch, caplog):
    """Aislada no significa muda. `FALLIDO` es `error` porque el mismo mensaje produjo dos
    estados distintos; `CONFLICTO` es `warning` porque hay una actualización que NO se aplicó
    y alguien tendrá que decidir qué hacer con ella."""
    monkeypatch.setattr(sombra.settings, "buyer_updater_shadow", True)

    async def _actualizar(*a, **k):
        return ResultadoUpdater(estado, revision=3, motivo="por qué")

    async def _si(_db):
        return True

    class _Sesion:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def commit(self): pass
        async def rollback(self): pass

    monkeypatch.setattr(sombra, "actualizar", _actualizar)
    monkeypatch.setattr(sombra, "_hay_esquema", _si)
    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: _Sesion())

    with caplog.at_level(logging.INFO):
        asyncio.run(actualizar_en_sombra(_Usuario(), _mensajes()))

    registros = [r for r in caplog.records if "buyer shadow ·" in r.message]
    assert len(registros) == 1
    assert registros[0].levelno == nivel


# ══ el carril legacy sigue siendo el único que habla ════════════════════════════════


def test_la_sombra_NO_toca_la_respuesta_ni_las_tarjetas():
    """Estructural sobre el endpoint: la llamada a la sombra no puede aparecer entre el
    cálculo de `reply`/`results` y su retorno, ni asignarse a nada.

    Es la propiedad que separa "el pipeline ya corre" de "el pipeline ya decide", y la fase
    entera depende de no confundirlas.
    """
    import pathlib
    import re

    codigo = pathlib.Path("app/routers/chat.py").read_text(encoding="utf-8")
    llamadas = re.findall(r"^.*actualizar_en_sombra\(.*$", codigo, re.MULTILINE)

    assert len(llamadas) == 1, f"se esperaba UNA llamada a la sombra: {llamadas}"
    assert "create_task" in llamadas[0], "la sombra tiene que ser fire-and-forget"
    assert "=" not in llamadas[0].split("create_task")[0], \
        "el resultado de la sombra no puede asignarse a nada"


def test_la_sombra_no_importa_nada_del_carril_de_respuesta():
    """No debe poder tocar tarjetas, prosa ni el grafo: su única salida es el store."""
    import ast
    import pathlib

    arbol = ast.parse(pathlib.Path(sombra.__file__).read_text(encoding="utf-8"))
    importados = {n.module or "" for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)}

    for prohibido in ("app.agent", "app.routers", "app.encaje", "app.verificacion_prosa"):
        assert not any(m.startswith(prohibido) for m in importados), \
            f"la sombra importa {prohibido}: puede influir en la respuesta"
