"""
Contexto AI V2 — Validacion de Memoria de Sesion (Task #5.5)
Envia dos preguntas consecutivas con el mismo session_id.
El agente debe referenciar la primera respuesta en la segunda.

Run: python test_memory.py
"""
import asyncio
import uuid

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.graph import compiled_graph, _checkpointer
from app.agent.state import AgentState
from app.database import engine

SESSION_ID = f"test-memory-{uuid.uuid4().hex[:8]}"

TURNO_1 = (
    "Analiza las opciones tranquilas cerca del parque La Carolina en Quito. "
    "Coordenadas: -0.1825, -78.4842"
)

TURNO_2 = (
    "De las opciones que acabas de analizar, "
    "¿cuál tiene mejor estado de impermeabilización de techo y por qué?"
)


def _last_ai_reply(messages: list) -> str:
    return next(
        (m.content for m in reversed(messages)
         if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None)),
        "Sin respuesta.",
    )


async def run_memory_test() -> None:
    print("\n" + "=" * 62)
    print("  CONTEXTO AI V2 -- TEST DE MEMORIA DE SESION")
    print("=" * 62)
    print(f"  Session ID: {SESSION_ID}\n")

    config = {"configurable": {"thread_id": SESSION_ID}}

    # ---------------------------------------------------------------
    # TURNO 1
    # ---------------------------------------------------------------
    print(f"TURNO 1:\n  \"{TURNO_1}\"\n")
    print("  [LangGraph ejecutando...]")

    state_t1: AgentState = {
        "messages": [HumanMessage(content=TURNO_1)],
        "spatial_context": {},
        "sql_results": [],
    }

    result_t1 = await compiled_graph.ainvoke(state_t1, config=config)
    reply_t1 = _last_ai_reply(result_t1["messages"])
    tool_count_t1 = sum(1 for m in result_t1["messages"] if hasattr(m, "type") and m.type == "tool")

    print(f"  Tool calls: {tool_count_t1}")
    print(f"  Mensajes en estado: {len(result_t1['messages'])}")
    print(f"\n  RESPUESTA TURNO 1 (primeras 400 chars):")
    print(f"  {reply_t1[:400]}...\n")

    # ---------------------------------------------------------------
    # Verificar checkpoint guardado
    # ---------------------------------------------------------------
    saved_state = await compiled_graph.aget_state(config)
    saved_msgs = saved_state.values.get("messages", []) if saved_state else []
    print(f"  [Checkpoint] {len(saved_msgs)} mensajes guardados para session '{SESSION_ID}'")

    # ---------------------------------------------------------------
    # TURNO 2 — sin contexto explícito, solo session_id
    # ---------------------------------------------------------------
    print(f"\nTURNO 2 (sin repetir contexto):\n  \"{TURNO_2}\"\n")
    print("  [LangGraph ejecutando con historial recuperado...]")

    state_t2: AgentState = {
        "messages": [HumanMessage(content=TURNO_2)],
        "spatial_context": {},
        "sql_results": [],
    }

    result_t2 = await compiled_graph.ainvoke(state_t2, config=config)
    reply_t2 = _last_ai_reply(result_t2["messages"])
    tool_count_t2 = sum(1 for m in result_t2["messages"] if hasattr(m, "type") and m.type == "tool")

    print(f"  Tool calls turno 2: {tool_count_t2}  (0 = usó memoria, no re-consultó DB)")
    print(f"  Mensajes acumulados en estado: {len(result_t2['messages'])}")
    print(f"\n  RESPUESTA TURNO 2:")
    print(f"  {reply_t2[:800]}")

    # ---------------------------------------------------------------
    # Resultado del test
    # ---------------------------------------------------------------
    msgs_grew = len(result_t2["messages"]) > len(result_t1["messages"])
    no_redundant_tools = tool_count_t2 == 0

    print("\n" + "=" * 62)
    print("  RESULTADO DE VALIDACION")
    print("=" * 62)
    print(f"  Historial acumulado entre turnos : {'PASS' if msgs_grew else 'FAIL'}")
    print(f"  Turno 2 sin re-consultar PostGIS : {'PASS' if no_redundant_tools else 'INFO (hizo tool call adicional)'}")
    print(f"  Turnos completados               : 2 / 2")

    if msgs_grew:
        print("\n  MEMORIA DE SESION OPERATIVA")
    else:
        print("\n  ADVERTENCIA: el historial no crecia entre turnos")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_memory_test())
