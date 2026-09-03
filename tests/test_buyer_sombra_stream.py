"""E3.2b.4a · la sombra también observa el turno que la gente usa de verdad.

E3.2b.4 cableó la sombra en `chat()` **después** del `return` que sirve SSE:

```
chat(stream=True)  →  return StreamingResponse(_stream_agent(...))   ← sale aquí
                      ...
                      create_task(actualizar_en_sombra(user, messages))  ← inalcanzable
```

El resultado en producción fue un `200 OK` sobre `POST /api/v1/chat/?stream=true` y **cero
filas** en `buyer_context_heads`. No falló el updater, el store ni Postgres: la sombra nunca
fue invocada. El propio `_stream_agent` dice dos veces en sus comentarios que *"el stream es
el camino que usa la gente de verdad"* —y era el único sin cobertura de costura—, así que la
lección de este fichero es tan de proceso como de código: **cablear una capa en un endpoint
con dos ramas exige probar las dos ramas.**

Aquí no se prueba la POLÍTICA de la sombra (eso es `test_buyer_sombra.py` y
`test_buyer_shadow_allowlist.py`), sino la COSTURA: que se la llame, una sola vez, con la
identidad real y con el estado final del grafo, y que su fallo no toque el SSE.
"""

from __future__ import annotations

import asyncio
import json
import re
import types

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.routers import chat as chat_mod

SESION = "sess-stream-1"
UID = "11111111-1111-4111-8111-111111111111"


class _Usuario:
    def __init__(self, user_id=UID):
        self.user_id = user_id


def _estado_final():
    """Lo que el grafo dejó en el hilo: el HumanMessage REAL con su id, más la respuesta."""
    return {
        "messages": [HumanMessage(content="máximo 120000 USD", id="msg-del-grafo"),
                     AIMessage(content="respuesta legacy")],
        "cards": [{"id": "activo-1", "titulo": "ficha"}],
        "spatial_context": {},
    }


@pytest.fixture
def grafo(monkeypatch):
    """Dobla el grafo: emite un token y deja un estado final recuperable por `aget_state`."""
    async def _astream_events(_input, config=None, version=None):
        """Secuencia MÍNIMA PERO REAL de una invocación del modelo.

        Antes bastaba un `on_chat_model_stream` suelto, porque el SSE publicaba cada trozo
        sin mirar nada. Desde `SSE-OUTPUT-GATE-01` la publicación se decide al cerrar la
        invocación —`on_chat_model_end`, y sólo si su salida no pide herramienta— y sólo
        para el nodo `llm`, así que un evento huérfano y sin `metadata` ya no representa a
        un modelo hablando: representa a uno que nunca terminó, y de ésos no sale nada.
        Aquí se mide la costura de la sombra, no el transporte: el doble se pone al día.
        """
        md = {"langgraph_node": "llm", "langgraph_step": 1}
        for ev in [
            {"event": "on_chat_model_start", "run_id": "r1", "name": "m",
             "metadata": md, "data": {}},
            {"event": "on_chat_model_stream", "run_id": "r1", "name": "m", "metadata": md,
             "data": {"chunk": types.SimpleNamespace(content="hola")}},
            {"event": "on_chat_model_end", "run_id": "r1", "name": "m", "metadata": md,
             "data": {"output": AIMessage(content="hola")}},
        ]:
            yield ev

    async def _aget_state(_config):
        return types.SimpleNamespace(values=_estado_final())

    async def _aget_state_history(_config, filter=None, **_kw):  # noqa: A002
        """El historial FILTRADO por `execution_id` (`SSE-PROTOCOL-IDENTITY-R1`).

        Desde esa unidad, el turno SSE no lee `aget_state` —que bajo concurrencia del mismo
        hilo devuelve una ejecución y pierde la otra— sino el checkpoint de SU ejecución. El
        doble se pone al día: devuelve un snapshot con la metadata que el emisor espera.
        """
        yield types.SimpleNamespace(
            values=_estado_final(),
            config={"configurable": {"checkpoint_id": "ckpt-doble"}},
            # `source: "loop"` es parte del contrato: sólo lo que escribió el GRAFO puede ser
            # el checkpoint terminal. Una escritura lateral (`update`) hereda el execution_id
            # y ganaría el `max(step)` sin ser de la ejecución. Ver `_FUENTES_DEL_GRAFO`.
            metadata={"execution_id": (filter or {}).get("execution_id"),
                      "step": 1, "source": "loop"})

    async def _aupdate_state(*a, **k):
        return None

    monkeypatch.setattr(chat_mod, "agent_graph", types.SimpleNamespace(
        compiled_graph=types.SimpleNamespace(
            astream_events=_astream_events,
            aget_state=_aget_state,
            aget_state_history=_aget_state_history,
            aupdate_state=_aupdate_state)))
    monkeypatch.setattr(chat_mod, "_texto_del_chunk", lambda c: getattr(c, "content", ""))
    # El resto del carril legacy, neutralizado: aquí se mide la costura de la sombra.
    monkeypatch.setattr(chat_mod, "registrar_intencion", lambda *a, **k: asyncio.sleep(0))
    monkeypatch.setattr(chat_mod, "_auditar_prosa", lambda *a, **k: None)
    monkeypatch.setattr(chat_mod, "_puerta_del_turno", lambda *a, **k: None)
    monkeypatch.setattr(chat_mod, "_map_seed_from_cards", lambda *a, **k: None)


@pytest.fixture
def espia(monkeypatch):
    """Registra CADA invocación a la sombra: cuántas, con qué usuario y con qué mensajes.

    El doble es SÍNCRONO y devuelve un awaitable, en vez de ser `async def`. La diferencia no
    es cosmética: con `create_task(actualizar_en_sombra(...))` la corrutina se AGENDA pero no
    corre hasta que el bucle cede, así que un doble `async` grabaría en un instante que
    depende del planificador —y la primera versión de este fichero falló de forma
    intermitente por eso, la misma clase de defecto que E3.2b.3a—. Grabar en la LLAMADA es
    determinista, y además es justo lo que se quiere afirmar: que la costura invoca a la
    sombra, no que la sombra termine.
    """
    llamadas = []

    def _sombra(user, messages):
        llamadas.append({"user": user, "messages": messages})
        return asyncio.sleep(0)   # `create_task` necesita un awaitable

    monkeypatch.setattr(chat_mod, "actualizar_en_sombra", _sombra)
    return llamadas


async def _consumir(gen):
    trozos = [trozo async for trozo in gen]
    await asyncio.sleep(0)   # deja correr las tareas agendadas: sin esto quedan pendientes
    return trozos


# ══ G1 · el turno stream invoca la sombra ═══════════════════════════════════════════


async def test_un_turno_STREAM_invoca_la_sombra(grafo, espia):
    """EL DEFECTO. Antes de E3.2b.4a esto valía cero: el `return` del endpoint dejaba el
    wiring fuera de alcance y el canary produjo 0 filas con un 200 OK."""
    await _consumir(chat_mod._stream_agent("máximo 120000 USD", SESION, user=_Usuario()))

    assert len(espia) == 1, f"la sombra se invocó {len(espia)} veces en un turno stream"


# ══ G7 · exactamente una vez ════════════════════════════════════════════════════════


async def test_un_turno_STREAM_no_lanza_DOS_tareas_de_sombra(grafo, espia):
    """Muerde la duplicación: si alguien 'arregla' esto añadiendo la llamada también en el
    endpoint, el turno stream dispararía dos veces y el mismo mensaje entraría dos veces al
    updater. La idempotencia del store lo absorbería como REPLAY, y ese verde silencioso es
    justo el que no queremos."""
    await _consumir(chat_mod._stream_agent("máximo 120000 USD", SESION, user=_Usuario()))

    assert len(espia) == 1, f"{len(espia)} tareas de sombra para un solo turno"


# ══ G3 · los mensajes FINALES, no una reconstrucción ════════════════════════════════


async def test_la_sombra_recibe_los_mensajes_FINALES_del_estado_real(grafo, espia):
    """No `payload.message` ni un `HumanMessage` fabricado: los del hilo, con el `id` que
    LangGraph asignó. Es lo que la procedencia va a citar, y lo que hace que un replay del
    mismo turno sea reconocible."""
    await _consumir(chat_mod._stream_agent("máximo 120000 USD", SESION, user=_Usuario()))

    msgs = espia[0]["messages"]
    assert msgs == _estado_final()["messages"], "no son los mensajes del estado final"
    humanos = [m for m in msgs if isinstance(m, HumanMessage)]
    assert humanos[-1].id == "msg-del-grafo", "el id no viene del grafo"


# ══ G4 · identidad ══════════════════════════════════════════════════════════════════


async def test_la_sombra_recibe_el_MISMO_usuario_que_autorizo_el_endpoint(grafo, espia):
    usuario = _Usuario("otro-uid")
    await _consumir(chat_mod._stream_agent("hola", SESION, user=usuario))

    assert espia[0]["user"] is usuario


async def test_un_turno_ANONIMO_llega_a_la_sombra_con_user_None(grafo, espia):
    """La costura no decide: entrega `None` y la PUERTA de la sombra —probada en
    `test_buyer_sombra.py`— es la que se niega a crear estado durable. Meter aquí un `if`
    duplicaría la política en dos sitios, que es como se desincronizan."""
    await _consumir(chat_mod._stream_agent("hola", SESION, user=None))

    assert len(espia) == 1
    assert espia[0]["user"] is None


# ══ G5 · aislamiento: el fallo de la sombra no toca el SSE ══════════════════════════


async def test_si_la_sombra_EXPLOTA_el_SSE_sigue_entero(grafo, monkeypatch):
    """El contrato de E3.2b.4 no se pierde al mover la llamada: token, panel y done siguen
    saliendo y el stream no se corta."""
    def _revienta(user, messages):
        raise RuntimeError("boom")

    monkeypatch.setattr(chat_mod, "actualizar_en_sombra", _revienta)

    trozos = await _consumir(chat_mod._stream_agent("hola", SESION, user=_Usuario()))

    texto = "".join(trozos)
    assert '"token"' in texto, "se perdieron los tokens"
    assert '"panel"' in texto, "se perdió el panel"
    assert '"done"' in texto, "el stream no cerró"


# ══ G6 · cero autoridad sobre lo visible ════════════════════════════════════════════


def _sin_identidad_de_turno(trozos):
    """El transcript con la identidad POR EJECUCIÓN borrada, y sólo ésa.

    Desde `SSE-PROTOCOL-IDENTITY-R1` el cable lleva `execution_id`, `checkpoint_id`,
    `trace_run_id` y una marca de tiempo, y **tienen que cambiar entre dos ejecuciones**: es
    exactamente la propiedad que esa unidad introduce. Comparar bytes crudos prohibiría eso.
    Se normalizan esos cuatro campos —ninguno más— y se compara todo lo demás, que es donde
    vive la propiedad de este gate: la sombra no toca prosa, panel ni orden.
    """
    return [re.sub(r'"(execution_id|checkpoint_id|trace_run_id|emitido_en)": "[^"]*"',
                   r'"\1": "<norm>"', t) for t in trozos]


async def test_la_sombra_NO_cambia_nada_de_lo_que_el_usuario_VE(grafo, espia, monkeypatch):
    """Se corre el turno dos veces —con sombra y con la sombra arrancada de raíz— y el SSE
    tiene que ser idéntico salvo la identidad de cada ejecución. Si la memoria del comprador
    empezara a participar en el ranking, la prosa o el panel, esto lo detecta sin depender de
    qué campo miremos."""
    con = await _consumir(chat_mod._stream_agent("hola", SESION, user=_Usuario()))

    async def _nada(*a, **k):
        return None
    monkeypatch.setattr(chat_mod, "actualizar_en_sombra", _nada)
    sin = await _consumir(chat_mod._stream_agent("hola", SESION, user=_Usuario()))

    assert _sin_identidad_de_turno(con) == _sin_identidad_de_turno(sin), \
        "la sombra alteró la salida visible del turno"

    # Y la identidad DEBE diferir. Se afirma sobre `execution_id` EN CONCRETO: un `con != sin`
    # a secas pasaría aunque `execution_id` desapareciera del cable, porque `emitido_en` ya
    # basta para que los transcripts difieran.
    def _eid(trozos):
        for t in trozos:
            m = re.search(r'"execution_id": "([^"]+)"', t)
            if m:
                return m.group(1)
        return None

    assert _eid(con) and _eid(sin), "el cable dejó de llevar execution_id"
    assert _eid(con) != _eid(sin), "dos ejecuciones con la misma identidad"


# ══ G8 · el camino nuevo pasa POR las puertas, no por al lado ═══════════════════════


@pytest.mark.parametrize("flag,allowlist,caso", [
    (False, UID, "flag apagado"),
    (True, "", "allowlist vacía"),
    (True, "99999999-9999-4999-8999-999999999999", "usuario fuera de la allowlist"),
])
async def test_el_turno_STREAM_no_puede_saltarse_la_politica(flag, allowlist, caso,
                                                             grafo, monkeypatch):
    """Con la sombra REAL —sin doble— el turno SSE tiene que respetar E3.2b.5.

    Los demás tests de este fichero sustituyen `actualizar_en_sombra`, así que ninguno
    demuestra que el camino nuevo esté DETRÁS de las puertas. Un wiring que llamara al
    orquestador directamente pasaría todos ellos y abriría producción entera.
    """
    from app.buyer import sombra as sombra_mod

    monkeypatch.setattr(sombra_mod.settings, "buyer_updater_shadow", flag)
    monkeypatch.setattr(sombra_mod.settings, "buyer_shadow_allowlist", allowlist)
    monkeypatch.setattr(sombra_mod, "_allowlist_vacia_avisado", False)

    llegadas = []

    async def _actualizar(*a, **k):
        llegadas.append(1)

    async def _hay_esquema(_db):
        return True

    monkeypatch.setattr(sombra_mod, "actualizar", _actualizar)
    monkeypatch.setattr(sombra_mod, "_hay_esquema", _hay_esquema)

    await _consumir(chat_mod._stream_agent("máximo 120000 USD", SESION, user=_Usuario()))
    await asyncio.sleep(0)   # la sombra es una tarea: dejarla correr antes de afirmar

    assert llegadas == [], f"el updater corrió con {caso}"


async def test_con_el_canary_HABILITADO_el_turno_STREAM_si_llega_al_updater(grafo, monkeypatch):
    """POSITIVO DE CONTROL del test de arriba, y no es opcional.

    Los tres casos negativos afirman `llegadas == []`, y eso saldría verde también si la
    sombra no corriera por un motivo ajeno a la política —una tarea que nunca se planifica,
    una costura rota, un doble mal puesto—. Sin esta prueba, aquel `parametrize` podría estar
    midiendo nada y nadie se enteraría. Aquí se demuestra que el mismo montaje SÍ alcanza el
    updater cuando la política lo permite, que es lo que convierte a los tres negativos en
    evidencia.
    """
    from app.buyer import sombra as sombra_mod

    monkeypatch.setattr(sombra_mod.settings, "buyer_updater_shadow", True)
    monkeypatch.setattr(sombra_mod.settings, "buyer_shadow_allowlist", UID)

    llegadas = []

    async def _actualizar(buyer_id, mensaje, **k):
        llegadas.append({"buyer_id": buyer_id, "message_id": mensaje.message_id})
        raise RuntimeError("suficiente: ya demostró que llega")

    async def _hay_esquema(_db):
        return True

    class _Sesion:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def commit(self): pass
        async def rollback(self): pass

    monkeypatch.setattr(sombra_mod, "actualizar", _actualizar)
    monkeypatch.setattr(sombra_mod, "_hay_esquema", _hay_esquema)
    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: _Sesion())

    await _consumir(chat_mod._stream_agent("máximo 120000 USD", SESION, user=_Usuario()))
    await asyncio.sleep(0)

    assert len(llegadas) == 1, "el turno stream del canary no alcanzó el updater"
    assert llegadas[0]["buyer_id"] == UID
    assert llegadas[0]["message_id"] == "msg-del-grafo", \
        "el updater no recibió el mensaje del estado final"


# ══ G4 (segunda mitad) · el ENDPOINT entrega la identidad al stream ═════════════════


async def test_el_ENDPOINT_pasa_el_usuario_autenticado_al_stream(monkeypatch):
    """El eslabón que faltaba, y lo descubrió una mutación que se escapó.

    Los tests de arriba llaman a `_stream_agent(..., user=...)` directamente, así que ninguno
    veía si `chat()` se molesta en pasarlo. Como el parámetro tiene default `None`, borrar el
    argumento en el endpoint dejaba la suite entera en verde y la sombra recibiendo `None`
    para SIEMPRE — es decir, el mismo síntoma que este hotfix arregla (cero filas), pero con
    los tests aplaudiendo. Por eso se ejercita el endpoint de verdad.
    """
    from starlette.requests import Request

    from app.sesion_autoridad import Autoridad

    visto = {}

    async def _falso_stream(message, session_id, user=None):
        visto.update({"message": message, "session_id": session_id, "user": user})
        for trozo in ():
            yield trozo

    async def _autoridad(*a, **k):
        return Autoridad.OWNER

    async def _actividad(*a, **k):
        return None

    monkeypatch.setattr(chat_mod, "_stream_agent", _falso_stream)
    monkeypatch.setattr(chat_mod, "_exigir_autoridad", _autoridad)
    monkeypatch.setattr(chat_mod, "marcar_actividad_lead", _actividad)

    peticion = Request({"type": "http", "method": "POST", "path": "/", "headers": [],
                        "client": ("test", 0), "query_string": b""})
    usuario = _Usuario("uid-del-endpoint")

    respuesta = await chat_mod.chat(
        peticion, chat_mod.ChatRequest(message="hola", session_id=SESION),
        stream=True, user=usuario)

    # Consumir el cuerpo: es lo que fuerza a que el generador se construya de verdad.
    async for _ in respuesta.body_iterator:
        pass

    assert visto.get("user") is usuario, \
        f"el endpoint no entregó el usuario al stream: {visto}"
    assert visto.get("session_id") == SESION


def test_el_panel_del_stream_no_conoce_el_BuyerContext():
    """La contraparte estática: el carril que produce lo visible no puede leer la memoria del
    comprador todavía. Consumirla es otra unidad."""
    import inspect

    fuente = inspect.getsource(chat_mod._stream_agent)
    for prohibido in ("BuyerContext", "cargar_ultima", "buyer.store", "buyer.actualizador"):
        assert prohibido not in fuente, f"el stream lee {prohibido}"
