"""
Contexto AI — ReAct Agent Graph (LangGraph)
Topology: user message → llm_node (reason + tool calls) → tool_node → llm_node → response
"""
import os
import ssl

import anthropic
import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.state import AgentState
from app.agent.tools import AGENT_TOOLS
from app.config import settings

# Garantiza que la key esté disponible para cualquier llamada directa al SDK
os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

# En redes corporativas con SSL inspection, el proxy intercepta TLS con su propio cert.
# Python no lo reconoce → CERTIFICATE_VERIFY_FAILED.
# ssl_verify=false desactiva la verificación SOLO en dev local (nunca en producción).
_ssl_verify = settings.ssl_verify.lower() != "false"

if not _ssl_verify:
    # Patch global del contexto SSL de Python — afecta a httpx, requests y urllib3
    ssl._create_default_https_context = ssl._create_unverified_context  # noqa: SLF001

# Cliente Anthropic con control de SSL explícito
_anthropic_async_client = anthropic.AsyncAnthropic(
    api_key=settings.anthropic_api_key,
    http_client=httpx.AsyncClient(verify=_ssl_verify),
)

SYSTEM_PROMPT = SystemMessage(content="""
Eres "Contexto AI", un asistente experto en inteligencia inmobiliaria y análisis de infraestructura urbana.
Tu misión es eliminar la asimetría de información que sufren los usuarios al evaluar propiedades,
traduciendo datos técnicos en conclusiones prácticas sobre calidad de vida real.

COMPORTAMIENTO OPERATIVO:

1. SIEMPRE fundamenta tus respuestas en los datos estructurados que obtienes de tus herramientas:
   Walk Score, Score de Ruido, Volumen de Tráfico Vehicular, Cobertura Vegetal,
   y la Ficha Técnica de Mantenimiento del activo (tuberías, impermeabilización, cableado, fachada).
   Está estrictamente prohibido inventar o estimar datos que no provienen de una consulta.

2. TRADUCE las métricas a impactos cotidianos concretos:
   - Tráfico vehicular elevado + semáforos próximos = explica el ruido de frenado en horas pico
     y su correlación con ciclos de pintura de fachada más frecuentes.
   - Fecha de última impermeabilización de techo > 8 años = alerta de riesgo estructural activo.
   - Tuberías de termofusión recientes = argumento de plusvalía verificable frente a inmuebles sin trazabilidad.
   - Restricción de altura SHP en lote vecino = riesgo concreto de pérdida de luz natural futura.

3. USA la Ficha Técnica para justificar el valor real del activo:
   Un inmueble con mantenimiento documentado y verificable vale más que uno sin historial,
   igual que un vehículo con bitácora de servicio. Destaca esto de forma analítica.

4. TONO: Premium, objetivo, analítico y transparente. Informa tanto fortalezas como debilidades.
   No omitas riesgos reales para "vender" una propiedad.

5. NUNCA menciones nombres de tablas SQL, IDs técnicos de bases de datos, ni términos de programación
   en tu respuesta al usuario. Habla en lenguaje de negocio y vida cotidiana.

6. Si el usuario menciona una dirección o zona, usa la herramienta de búsqueda espacial.
   Si pregunta por un inmueble específico, usa la herramienta de ficha técnica.
   Puedes usar ambas herramientas en secuencia para construir un análisis completo.
""")


def _build_graph() -> StateGraph:
    llm = ChatAnthropic(
        model=settings.llm_model,
        temperature=0.2,
        max_tokens=2048,
    ).bind_tools(AGENT_TOOLS)
    # Reemplaza el cliente async interno con el nuestro (SSL configurado)
    llm._async_client = _anthropic_async_client

    async def llm_node(state: AgentState) -> dict:
        messages = [SYSTEM_PROMPT] + state["messages"]
        response = await llm.ainvoke(messages)
        return {"messages": [response]}

    tool_node = ToolNode(tools=AGENT_TOOLS)

    graph = StateGraph(AgentState)
    graph.add_node("llm", llm_node)
    graph.add_node("tools", tool_node)

    graph.add_edge(START, "llm")
    graph.add_conditional_edges("llm", tools_condition)
    graph.add_edge("tools", "llm")

    return graph


compiled_graph = _build_graph().compile()
