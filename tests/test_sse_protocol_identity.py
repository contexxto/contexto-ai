"""`SSE-PROTOCOL-IDENTITY-R1` · el cable dice de quién es cada turno y bajo qué código corrió.

EL DEFECTO QUE CIERRA. Dos turnos distintos de la misma conversación producían transcripts
**byte a byte idénticos** —208 bytes, mismos eventos—, y el SHA desplegado sólo entraba al
arnés porque alguien lo tecleaba en una bandera de CLI. Con eso, ningún adjudicador podía
decir qué ejecución estaba mirando ni bajo qué código se produjo: un PASS no era atribuible.

LO QUE AÑADE EL PROTOCOLO `contexto-sse/1`:

    meta   PRIMER evento, antes de invocar el grafo · execution_id · runtime_sha · service_id
    todos  tool_call, token y panel llevan el mismo execution_id
    done   terminal normal · checkpoint_id DE ESA EJECUCIÓN · trace_run_id · runtime_sha
    error  terminal alternativo · code y phase de vocabulario CERRADO

`execution_id` es un UUIDv4 del servidor, no el contador de HumanMessage ni el `run_id` de
LangGraph: existe antes de que el grafo emita nada, así que un fallo temprano sigue siendo
atribuible. El `run_id` raíz se conserva aparte como `trace_run_id` — correlación, no identidad.

EL CHECKPOINT ES EL PROPIO, y no es un matiz. Dos peticiones concurrentes sobre el MISMO hilo
se permiten, cada una escribe su linaje, y `aget_state` devuelve una y pierde la otra. Emitir
su `checkpoint_id` sería mentir con un campo que parece preciso.
"""
import json
import logging
import os
import uuid

import pytest
from langchain_core.messages import AIMessage

import main
from app.agent import graph as G_graph
from app.routers import chat as chat_mod

# El arnés de la compuerta ya monta endpoint, grafo y checkpointer reales con dobles
# controlados, y neutraliza auth y rate-limit. Se reutiliza en vez de duplicarlo.
from test_sse_output_gate import ANCLA, _FalsoQueTransmite, _GUION, _card, _fila, mundo  # noqa: F401

TEST_DB = (os.getenv("TEST_DATABASE_URL") or "").replace(
    "postgresql+asyncpg://", "postgresql://")

SHA_VALIDO = "581537d4994f61d1c290c04349f6b94143879c7c"


def _tc(n=1):
    return {"name": "tool_search_nearby_assets",
            "args": {"latitude": ANCLA["latitude"], "longitude": ANCLA["longitude"],
                     "radius_meters": 1200}, "id": f"tc-{n}"}


def _eventos(texto: str) -> list[dict]:
    """Los eventos del cable, en orden, sin normalizar nada."""
    out = []
    for bloque in texto.split("\n\n"):
        linea = next((l for l in bloque.split("\n") if l.startswith("data: ")), None)
        if linea:
            out.append(json.loads(linea[6:]))
    return out


def _post(cliente, texto="Busco arriendo en La Floresta", sesion="ident"):
    return cliente.post("/api/v1/chat/?stream=true",
                        json={"message": texto, "session_id": sesion})


def _tipo(ev: dict) -> str:
    for k in ("meta", "tool_call", "token", "panel", "done", "error"):
        if k in ev:
            return k
    return "?"


# ── meta: primero, y con identidad ────────────────────────────────────────────

def test_meta_es_el_primer_evento_del_cable(mundo):
    cliente, _ = mundo
    _GUION[:] = [AIMessage(content="preambulo", tool_calls=[_tc()]),
                 AIMessage(content="respuesta")]
    evs = _eventos(_post(cliente).text)

    assert _tipo(evs[0]) == "meta", [_tipo(e) for e in evs]
    m = evs[0]["meta"]
    assert m["protocolo"] == "contexto-sse/1"
    assert m["session_id"] == "ident"
    uuid.UUID(m["execution_id"])          # es un UUID de verdad
    assert m["emitido_en"].endswith("Z")


def test_dos_peticiones_identicas_producen_execution_id_distintos(mundo):
    """El defecto original: dos turnos idénticos daban transcripts indistinguibles."""
    cliente, _ = mundo
    vistos = []
    for _ in range(2):
        _GUION[:] = [AIMessage(content="misma respuesta")]
        evs = _eventos(_post(cliente, texto="lo mismo", sesion="gemelo").text)
        vistos.append(evs[0]["meta"]["execution_id"])

    assert vistos[0] != vistos[1], "dos turnos con la misma identidad"


def test_todos_los_eventos_llevan_el_mismo_execution_id(mundo):
    cliente, _ = mundo
    _GUION[:] = [AIMessage(content="preambulo", tool_calls=[_tc()]),
                 AIMessage(content="respuesta final")]
    evs = _eventos(_post(cliente).text)
    eid = evs[0]["meta"]["execution_id"]

    for ev in evs[1:]:
        assert ev.get("execution_id") == eid, f"evento sin identidad o ajena: {ev}"
    assert {_tipo(e) for e in evs} >= {"meta", "tool_call", "token", "panel", "done"}


# ── runtime: válido, ausente, malformado ──────────────────────────────────────

@pytest.mark.parametrize("crudo,esperado", [
    (SHA_VALIDO, SHA_VALIDO),
    (SHA_VALIDO.upper(), SHA_VALIDO),          # se normaliza a minúsculas
    ("581537d", None),                          # abreviado: NO vale
    ("", None),
    ("z" * 40, None),                           # 40 caracteres pero no hex
    (SHA_VALIDO + "0", None),                   # 41
])
def test_runtime_sha_solo_si_son_40_hex(monkeypatch, crudo, esperado):
    monkeypatch.setenv("RENDER_GIT_COMMIT", crudo)
    sha, _ = chat_mod._identidad_runtime()
    assert sha == esperado


def test_runtime_sha_ausente_es_null_no_inventado(mundo, monkeypatch):
    """Sin variable, `null`. JAMÁS el HEAD local: mentiría con apariencia de verdad."""
    cliente, _ = mundo
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)
    _GUION[:] = [AIMessage(content="hola")]
    m = _eventos(_post(cliente, texto="hola", sesion="sinsha").text)[0]["meta"]

    assert m["runtime_sha"] is None
    assert m["service_id"] is None


def test_runtime_sha_valido_viaja_en_meta_y_en_done(mundo, monkeypatch):
    cliente, _ = mundo
    monkeypatch.setenv("RENDER_GIT_COMMIT", SHA_VALIDO.upper())
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-abc")
    _GUION[:] = [AIMessage(content="hola")]
    evs = _eventos(_post(cliente, texto="hola", sesion="consha").text)
    done = next(e for e in evs if "done" in e)

    assert evs[0]["meta"]["runtime_sha"] == SHA_VALIDO
    assert evs[0]["meta"]["service_id"] == "srv-abc"
    assert done["runtime_sha"] == SHA_VALIDO


# ── done y error: terminales mutuamente excluyentes ───────────────────────────

def test_done_lleva_checkpoint_propio_y_trace_run_id(mundo):
    cliente, _ = mundo
    _GUION[:] = [AIMessage(content="respuesta")]
    evs = _eventos(_post(cliente, texto="hola", sesion="done1").text)
    done = next(e for e in evs if "done" in e)

    assert done["checkpoint_id"], "done sin checkpoint_id"
    uuid.UUID(done["trace_run_id"])
    assert _tipo(evs[-1]) == "done"


def test_un_fallo_del_grafo_termina_en_error_y_no_en_done(mundo, monkeypatch):
    """Antes, una excepción dejaba CERO bytes: ni panel, ni done, ni forma de saber qué pasó."""
    cliente, _ = mundo

    async def revienta(*a, **k):
        raise RuntimeError("la contraseña es hunter2 y el prompt dice X")
        yield  # pragma: no cover

    monkeypatch.setattr(G_graph.compiled_graph, "astream_events", revienta)
    _GUION[:] = [AIMessage(content="hola")]
    evs = _eventos(_post(cliente, texto="hola", sesion="boom").text)

    tipos = [_tipo(e) for e in evs]
    assert tipos[0] == "meta" and tipos[-1] == "error", tipos
    assert "done" not in tipos, "done y error no pueden coexistir"

    err = evs[-1]
    # EXACTOS, no «alguno del vocabulario»: `in CODIGOS_ERROR` pasaría con los cinco, y el
    # punto de esta unidad es justo que cada código diga una cosa distinta.
    assert err["error"] == {"code": "execution_failed", "phase": "graph"}
    assert err["checkpoint_id"] is None
    assert err["execution_id"] == evs[0]["meta"]["execution_id"]


def test_el_error_no_filtra_la_excepcion(mundo, monkeypatch):
    cliente, _ = mundo

    async def revienta(*a, **k):
        raise RuntimeError("hunter2 · postgresql://u:p@host/db · SYSTEM PROMPT: sé amable")
        yield  # pragma: no cover

    monkeypatch.setattr(G_graph.compiled_graph, "astream_events", revienta)
    _GUION[:] = [AIMessage(content="hola")]
    cuerpo = _post(cliente, texto="hola", sesion="fuga").text

    for prohibido in ("hunter2", "postgresql://", "SYSTEM PROMPT", "RuntimeError", "Traceback"):
        assert prohibido not in cuerpo, f"el cable filtró {prohibido!r}"


def test_checkpoint_no_atribuible_termina_en_error(mundo, monkeypatch):
    """Si no se puede señalar UN checkpoint de esta ejecución, se dice. No se inventa."""
    cliente, _ = mundo

    async def sin_nada(*a, **k):
        raise chat_mod._CheckpointNoAtribuible("checkpoint_not_found", 0)

    monkeypatch.setattr(chat_mod, "_snapshot_de_la_ejecucion", sin_nada)
    _GUION[:] = [AIMessage(content="hola")]
    evs = _eventos(_post(cliente, texto="hola", sesion="nockpt").text)

    assert _tipo(evs[-1]) == "error"
    assert evs[-1]["error"] == {"code": "checkpoint_not_found", "phase": "checkpoint"}
    assert "done" not in [_tipo(e) for e in evs]


def test_checkpoint_ambiguo_termina_en_error(mundo, monkeypatch):
    cliente, _ = mundo

    async def ambiguo(*a, **k):
        raise chat_mod._CheckpointNoAtribuible("checkpoint_ambiguous", 2)

    monkeypatch.setattr(chat_mod, "_snapshot_de_la_ejecucion", ambiguo)
    _GUION[:] = [AIMessage(content="hola")]
    evs = _eventos(_post(cliente, texto="hola", sesion="ambig").text)

    assert evs[-1]["error"]["code"] == "checkpoint_ambiguous"


def test_una_lectura_fallida_del_historial_no_dice_ni_no_existe_ni_fallo_la_ejecucion(
        mundo, monkeypatch, caplog):
    """Los tres códigos de `checkpoint` NO son intercambiables.

    Si la CONSULTA revienta —base caída, API cambiada— lo único demostrado es que no se pudo
    leer. `checkpoint_not_found` afirmaría que la ejecución no dejó rastro y `execution_failed`
    que falló el grafo: dos conclusiones que esta excepción no autoriza.

    Y CUBRE TAMBIÉN EL LOG. Callar la excepción en el cable y volcarla en el servidor no es un
    arreglo: es mover la fuga. La excepción de aquí lleva un secreto a propósito.
    """
    cliente, _ = mundo

    async def historial_roto(_base, filter=None, **_kw):  # noqa: A002
        raise ConnectionError("FATAL: password authentication failed for user 'contexto_admin'")
        yield  # pragma: no cover

    monkeypatch.setattr(chat_mod.agent_graph.compiled_graph,
                        "aget_state_history", historial_roto)
    _GUION[:] = [AIMessage(content="hola")]
    caplog.set_level(logging.DEBUG)
    cuerpo = _post(cliente, texto="hola", sesion="lectura").text
    evs = _eventos(cuerpo)

    assert _tipo(evs[-1]) == "error"
    assert evs[-1]["error"] == {"code": "checkpoint_read_failed", "phase": "checkpoint"}
    assert "done" not in [_tipo(e) for e in evs]
    assert evs[-1]["execution_id"] == evs[0]["meta"]["execution_id"]

    # Ni clase, ni mensaje, ni traza, ni el secreto que traía la excepción.
    for prohibido in ("ConnectionError", "password", "contexto_admin", "Traceback",
                      "authentication"):
        assert prohibido not in cuerpo, f"el cable filtró {prohibido!r}"

    # EL LOG TAMPOCO. `logger.exception()` es `exc_info=True` y volcaría la traza entera —con
    # el mensaje dentro—, cambiando una fuga por el cable por otra por el log.
    registrado = caplog.text
    for prohibido in ("password", "contexto_admin", "authentication", "Traceback",
                      "FATAL"):
        assert prohibido not in registrado, f"el LOG filtró {prohibido!r}"

    # Pero sí conserva lo que sirve para diagnosticar, sin texto libre.
    assert "code=checkpoint_read_failed" in registrado
    assert "phase=checkpoint" in registrado
    assert f"execution_id={evs[0]['meta']['execution_id']}" in registrado


def test_cero_candidatos_reales_produce_checkpoint_not_found(mundo, monkeypatch):
    """La rama de cero coincidencias, ejercitada DE VERDAD.

    La otra prueba inyecta la excepción `_CheckpointNoAtribuible`, así que demuestra que el
    emisor la traduce — no que el filtro llegue a devolver vacío. Aquí el historial existe y
    responde: simplemente no hay nada con este `execution_id`.
    """
    cliente, _ = mundo

    async def historial_vacio(_base, filter=None, **_kw):  # noqa: A002
        return
        yield  # pragma: no cover

    monkeypatch.setattr(chat_mod.agent_graph.compiled_graph,
                        "aget_state_history", historial_vacio)
    _GUION[:] = [AIMessage(content="hola")]
    evs = _eventos(_post(cliente, texto="hola", sesion="cero").text)

    assert _tipo(evs[-1]) == "error"
    assert evs[-1]["error"] == {"code": "checkpoint_not_found", "phase": "checkpoint"}
    assert "done" not in [_tipo(e) for e in evs]


def test_los_codigos_de_error_son_un_vocabulario_cerrado():
    assert set(chat_mod.CODIGOS_ERROR) == {
        "execution_failed", "checkpoint_read_failed", "checkpoint_not_found",
        "checkpoint_ambiguous", "serialization_failed"}
    assert set(chat_mod.FASES_ERROR) == {"graph", "checkpoint", "output"}


# ── el checkpoint es EL PROPIO, no el último del hilo ─────────────────────────

def test_el_checkpoint_emitido_es_el_de_esta_ejecucion(mundo):
    """Dos turnos seguidos: cada `done` trae SU checkpoint, no el mismo dos veces."""
    cliente, _ = mundo
    vistos = []
    for i in range(2):
        _GUION[:] = [AIMessage(content=f"respuesta {i}")]
        evs = _eventos(_post(cliente, texto="hola", sesion="secuencial").text)
        done = next(e for e in evs if "done" in e)
        vistos.append((done["execution_id"], done["checkpoint_id"]))

    assert vistos[0][0] != vistos[1][0]
    assert vistos[0][1] != vistos[1][1], "dos turnos con el mismo checkpoint_id"


def test_el_checkpoint_de_done_es_RE_DERIVABLE_con_la_regla_publicada(mundo):
    """La prueba que ata el defecto que encontró la revisión adversarial pre-push.

    Un turno con tarjetas dispara una escritura POSTERIOR al grafo (`map_seed`). Se le pasaba
    un config sin `execution_id` creyendo que así quedaba fuera de la ejecución — pero
    `aupdate_state` escribe `{**metadata_del_checkpoint_anterior, **la_que_pasas}`, así que
    HEREDABA el `execution_id` y quedaba con un `step` mayor que el terminal.

    Efecto medido antes del arreglo: `done` anunciaba el checkpoint del step 4 (`loop`) y la
    regla publicada devolvía el del step 5 (`update`). El campo dejaba de ser re-derivable —
    un `checkpoint_id` que parece preciso y señala otra cosa, que es exactamente lo que este
    protocolo existe para no tener.
    """
    import asyncio

    cliente, compilado = mundo
    _GUION[:] = [AIMessage(content="preambulo", tool_calls=[_tc()]),
                 AIMessage(content="respuesta con panel")]
    evs = _eventos(_post(cliente, sesion="rederiv").text)
    eid = evs[0]["meta"]["execution_id"]
    done = next(e for e in evs if "done" in e)

    async def filtrado():
        base = chat_mod._langgraph_config("rederiv")
        filas = []
        async for s in compiled_history(compilado, base, eid):
            filas.append(s)
        return filas

    def compiled_history(grafo, base, eid_):
        return grafo.aget_state_history(base, filter={"execution_id": eid_})

    filas = asyncio.run(filtrado())
    del_grafo = [s for s in filas
                 if (s.metadata or {}).get("source") in chat_mod._FUENTES_DEL_GRAFO]
    assert del_grafo, "el filtro por execution_id no devolvió checkpoints del grafo"

    tope = max((s.metadata or {}).get("step") for s in del_grafo)
    terminales = [s for s in del_grafo if (s.metadata or {}).get("step") == tope]
    assert len(terminales) == 1
    rederivado = terminales[0].config["configurable"]["checkpoint_id"]

    assert rederivado == done["checkpoint_id"], (
        "el checkpoint_id de `done` no se puede re-derivar con la regla publicada")

    # Y la escritura lateral quedó FUERA de la ejecución, que es el cinturón del arreglo.
    laterales = [s for s in filas if (s.metadata or {}).get("source") == "update"]
    assert not laterales, "una escritura lateral quedó atribuida a esta ejecución"


def test_seleccion_estructural_toma_el_step_mayor_de_SU_ejecucion(monkeypatch):
    """La regla de terminalidad, en aislamiento: mayor `step` entre los de esta ejecución.

    Se le dan checkpoints de DOS ejecuciones mezclados, con el ajeno en un `step` más alto y
    con una ESCRITURA LATERAL propia (`source: "update"`) todavía más alta: elegir «el último
    del hilo» daría el ajeno, y no excluir la lateral daría un checkpoint que el turno nunca
    anunció.
    """
    import types

    class _Snap:
        def __init__(self, cid, eid, step, source="loop"):
            self.config = {"configurable": {"checkpoint_id": cid}}
            # `source` es parte del contrato: sólo lo que escribió el grafo
            # (`loop`/`input`) puede ser terminal. Ver `_FUENTES_DEL_GRAFO`.
            self.metadata = {"execution_id": eid, "step": step, "source": source}
            self.values = {"marca": cid}

    async def historia(_base, filter=None):  # noqa: A002
        for s in [_Snap("ajeno-alto", "OTRA", 9), _Snap("lateral-mio", "MIA", 7, "update"),
                  _Snap("mio-1", "MIA", 1), _Snap("mio-0", "MIA", 0),
                  _Snap("ajeno-bajo", "OTRA", 0)]:
            if not filter or s.metadata["execution_id"] == filter.get("execution_id"):
                yield s

    monkeypatch.setattr(chat_mod.agent_graph, "compiled_graph",
                        types.SimpleNamespace(aget_state_history=historia))
    import asyncio
    snap = asyncio.run(chat_mod._snapshot_de_la_ejecucion(
        {"configurable": {"thread_id": "t"}}, "MIA"))

    assert snap.config["configurable"]["checkpoint_id"] == "mio-1"


def test_empate_en_el_step_maximo_es_ambiguo_no_una_apuesta(monkeypatch):
    import types

    class _Snap:
        def __init__(self, cid, step):
            self.config = {"configurable": {"checkpoint_id": cid}}
            self.metadata = {"execution_id": "MIA", "step": step, "source": "loop"}

    async def historia(_base, filter=None):  # noqa: A002
        for s in [_Snap("a", 3), _Snap("b", 3)]:
            yield s

    monkeypatch.setattr(chat_mod.agent_graph, "compiled_graph",
                        types.SimpleNamespace(aget_state_history=historia))
    import asyncio
    with pytest.raises(chat_mod._CheckpointNoAtribuible) as exc:
        asyncio.run(chat_mod._snapshot_de_la_ejecucion(
            {"configurable": {"thread_id": "t"}}, "MIA"))
    assert exc.value.code == "checkpoint_ambiguous"


# ── lo que NO debe existir ────────────────────────────────────────────────────

def test_el_cable_no_lleva_turn_id_request_id_ni_deployment_id(mundo):
    cliente, _ = mundo
    _GUION[:] = [AIMessage(content="preambulo", tool_calls=[_tc()]),
                 AIMessage(content="respuesta")]
    cuerpo = _post(cliente, sesion="sinsobras").text

    for prohibido in ("turn_id", "request_id", "deployment_id"):
        assert prohibido not in cuerpo, f"el cable trae {prohibido}, que se retiró a propósito"


# ── Postgres real: la ligadura bajo concurrencia del MISMO hilo ───────────────

@pytest.mark.skipif(not TEST_DB, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas")
def test_postgres_liga_cada_checkpoint_a_su_ejecucion_bajo_concurrencia():
    """La precondición de la unidad, como prueba permanente.

    Dos ejecuciones SIMULTÁNEAS sobre el mismo `thread_id`: LangGraph permite ambas, cada una
    escribe su linaje, y el historial FILTRADO por `execution_id` las separa. `aget_state`
    devuelve una sola — por eso no se usa.
    """
    import asyncio
    import sys

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.graph.message import add_messages
    from langchain_core.messages import HumanMessage
    from typing_extensions import Annotated, TypedDict

    if sys.platform == "win32":   # psycopg async no corre sobre ProactorEventLoop
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    class Estado(TypedDict):
        messages: Annotated[list, add_messages]

    async def lento(_e):
        await asyncio.sleep(0.08)
        return {"messages": [AIMessage(content="lenta")]}

    async def rapido(_e):
        return {"messages": [AIMessage(content="rapida")]}

    def grafo(fn):
        g = StateGraph(Estado)
        g.add_node("responder", fn)
        g.add_edge(START, "responder")
        g.add_edge("responder", END)
        return g

    async def corre():
        async with AsyncPostgresSaver.from_conn_string(TEST_DB) as saver:
            await saver.setup()
            gl = grafo(lento).compile(checkpointer=saver)
            gr = grafo(rapido).compile(checkpointer=saver)
            hilo = "ident-" + uuid.uuid4().hex[:8]
            ea, eb = str(uuid.uuid4()), str(uuid.uuid4())

            def cfg(e):
                return {"configurable": {"thread_id": hilo},
                        "metadata": {"execution_id": e, "protocolo": "contexto-sse/1"}}

            await asyncio.gather(
                gl.ainvoke({"messages": [HumanMessage(content="A")]}, config=cfg(ea)),
                gr.ainvoke({"messages": [HumanMessage(content="B")]}, config=cfg(eb)))

            base = {"configurable": {"thread_id": hilo}}
            por_eid = {}
            for etiqueta, eid in (("A", ea), ("B", eb)):
                filas = []
                async for s in gl.aget_state_history(base, filter={"execution_id": eid}):
                    filas.append((s.config["configurable"]["checkpoint_id"],
                                  (s.metadata or {}).get("step"),
                                  (s.values or {}).get("messages", [])))
                por_eid[etiqueta] = filas

            todos = []
            async for s in gl.aget_state_history(base):
                todos.append((s.metadata or {}).get("execution_id"))
            return por_eid, todos

    por_eid, todos = asyncio.run(corre())

    assert all(e for e in todos), "hay checkpoints sin execution_id"
    assert len(set(todos)) == 2, f"se esperaban 2 ejecuciones, hay {set(todos)}"
    assert por_eid["A"] and por_eid["B"], "el filtro devolvió vacío"
    ids_a = {c for c, _, _ in por_eid["A"]}
    ids_b = {c for c, _, _ in por_eid["B"]}
    assert not (ids_a & ids_b), "el filtro mezcló checkpoints de dos ejecuciones"

    for etiqueta, esperado in (("A", "lenta"), ("B", "rapida")):
        filas = por_eid[etiqueta]
        tope = max(s for _, s, _ in filas)
        terminales = [f for f in filas if f[1] == tope]
        assert len(terminales) == 1, f"{etiqueta}: {len(terminales)} candidatos terminales"
        msgs = terminales[0][2]
        assert msgs and msgs[-1].content == esperado
