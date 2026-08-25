"""¿Puede un nodo leer el `thread_id` del `RunnableConfig` en la versión FIJADA?

Esta prueba existe antes del cableado y no después, a propósito. La decisión de sacar el
`session_id` del `RunnableConfig` en vez de meterlo en `AgentState` depende de un
comportamiento de LangGraph, y el repo está fijado en `langgraph==0.2.60`: lo que valga
en la documentación de la versión actual no dice nada sobre la que corre aquí.

Si esto pasa, `RunnableConfig` es la fuente canónica del `session_id` dentro del nodo y
`AgentState` no se toca — la identidad de EJECUCIÓN no tiene por qué convertirse en
estado conversacional mutable.

Si fallara, habría que propagarlo por el estado, pero solo entonces y habiendo
demostrado la necesidad.
"""

import asyncio
from typing import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph


class _Estado(TypedDict, total=False):
    visto: str


def test_un_nodo_recibe_el_thread_id_del_config():
    """El mismo `{"configurable": {"thread_id": …}}` que arma `_langgraph_config`."""
    capturado = {}

    async def nodo(state: _Estado, config: RunnableConfig):
        capturado["thread_id"] = config["configurable"]["thread_id"]
        return {"visto": capturado["thread_id"]}

    g = StateGraph(_Estado)
    g.add_node("n", nodo)
    g.add_edge(START, "n")
    g.add_edge("n", END)
    compilado = g.compile()

    # Estado inicial no vacío: con `{}` esta versión levanta "PASSTHROUGH value must be
    # replaced", que es del canal de estado y no del config — no confundir una cosa con
    # la otra al leer el fallo.
    salida = asyncio.run(
        compilado.ainvoke({"visto": ""}, {"configurable": {"thread_id": "sesion-real-42"}})
    )

    assert capturado["thread_id"] == "sesion-real-42"
    assert salida["visto"] == "sesion-real-42"


def test_el_config_del_endpoint_produce_esa_forma():
    """No basta con que LangGraph lo entregue: tiene que ser el mismo que el endpoint
    construye hoy, o estaríamos probando una forma que nadie usa."""
    from app.routers.chat import _langgraph_config

    cfg = _langgraph_config("s-1")
    assert cfg["configurable"]["thread_id"] == "s-1"


def test_sin_thread_id_el_nodo_no_puede_inventarselo():
    """Documenta el borde: si alguien invoca el grafo sin `thread_id`, el nodo se queda
    sin identidad de ejecución. Ese caso NO se rellena con un valor por defecto — se
    convierte en `SessionIdAusente` en el nodo real."""
    capturado = {}

    async def nodo(state: _Estado, config: RunnableConfig):
        capturado["configurable"] = dict(config.get("configurable") or {})
        return {"visto": "ok"}

    g = StateGraph(_Estado)
    g.add_node("n", nodo)
    g.add_edge(START, "n")
    g.add_edge("n", END)

    asyncio.run(g.compile().ainvoke({"visto": ""}, {}))
    assert not capturado["configurable"].get("thread_id")
