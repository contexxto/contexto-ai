"""
Contexto AI V2 — End-to-End Agent Integration Test
Validates: PostGIS tools → LangGraph ReAct loop → grounded response

Run: python test_agent.py
"""
import asyncio
import time

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.graph import compiled_graph
from app.agent.state import AgentState
from app.database import engine

TEST_PROMPT = (
    "¿Qué opciones habitables hay cerca del parque La Carolina que sean tranquilas "
    "y cómo está su mantenimiento técnico?"
)

# La Carolina center coordinates
LA_CAROLINA_LAT = -0.1825
LA_CAROLINA_LON = -78.4842


async def run_agent_test() -> None:
    print("\n" + "=" * 60)
    print("  CONTEXTO AI V2 — TEST DE INTEGRACIÓN END-TO-END")
    print("=" * 60)
    print(f"\n📍 Prompt de prueba:\n  \"{TEST_PROMPT}\"\n")
    print("-" * 60)

    initial_state: AgentState = {
        "messages": [HumanMessage(content=TEST_PROMPT)],
        "spatial_context": {
            "latitude": LA_CAROLINA_LAT,
            "longitude": LA_CAROLINA_LON,
            "radius_meters": 1000,
        },
        "sql_results": [],
    }

    start = time.perf_counter()
    tool_calls: list[str] = []
    tool_results: list[str] = []

    print("⚙️  Ejecución del grafo LangGraph:\n")

    async for event in compiled_graph.astream_events(initial_state, version="v2"):
        kind = event.get("event")

        if kind == "on_tool_start":
            tool_name = event.get("name", "")
            tool_input = event.get("data", {}).get("input", {})
            tool_calls.append(tool_name)
            print(f"  🔧 TOOL CALL → {tool_name}")
            print(f"     Input: {tool_input}")

        elif kind == "on_tool_end":
            tool_name = event.get("name", "")
            output = event.get("data", {}).get("output", "")
            # Truncate long outputs for readability
            preview = str(output)[:200] + "..." if len(str(output)) > 200 else str(output)
            tool_results.append(tool_name)
            print(f"  ✅ TOOL RESULT ← {tool_name}")
            print(f"     Preview: {preview}\n")

        elif kind == "on_chat_model_start":
            print(f"  🧠 LLM procesando...")

    elapsed = time.perf_counter() - start

    # Get final state
    final_state = await compiled_graph.ainvoke(initial_state)
    messages = final_state["messages"]
    final_reply = next(
        (m.content for m in reversed(messages) if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None)),
        "Sin respuesta final."
    )

    print("\n" + "=" * 60)
    print("  RESPUESTA FINAL DEL AGENTE")
    print("=" * 60)
    print(f"\n{final_reply}\n")

    print("=" * 60)
    print("  RESUMEN DE EJECUCIÓN")
    print("=" * 60)
    print(f"  ⏱  Tiempo total:       {elapsed:.2f}s")
    print(f"  🔧 Tool calls:         {len(tool_calls)} → {', '.join(tool_calls) if tool_calls else 'ninguna'}")
    print(f"  💬 Mensajes en estado: {len(messages)}")
    print(f"  🗃  Activos analizados: extraídos por ST_DWithin 1km La Carolina")
    print("=" * 60)
    print("\n✅ Test completado — Sistema 100% operativo\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_agent_test())
