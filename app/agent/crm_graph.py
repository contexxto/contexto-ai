"""
CRM Vivo — grafo ReAct del CORREDOR (Fase 1).

Un segundo agente (distinto al del comprador) que deja al corredor HABLARLE a su CRM
en lenguaje natural: "¿cuántos leads calientes tengo?", "¿a quién retomo?", "muéstrame
el timeline de [lead]". Espeja app/agent/graph.py (init del modelo con SSL explícito +
llm_node con guardrail Fair Housing) pero con SYSTEM_PROMPT y tools del corredor.

Barandas (docs/DISENO_CRM_Vivo.md): el LLM NARRA, nunca calcula; sin dato → "no tengo ese
dato"; jamás segmenta/perfila por clase protegida; solo los leads del propio corredor.

Fase 1 usa MemorySaver (memoria por-proceso): suficiente para un asistente de consulta.
La persistencia del hilo del corredor es una mejora futura.
"""
from __future__ import annotations

from typing import Annotated, TypedDict

import anthropic
import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

# Importar graph.py garantiza que el monkey-patch SSL ya esté aplicado antes de crear
# el ChatAnthropic de este módulo (mismo patrón de red corporativa).
from app.agent.graph import _ssl_verify
from app.agent.crm_tools import CRM_TOOLS
from app.agent.crm_guardrails import (
    evaluar_salida_crm, registrar_guardrail, texto_de_content, tool_jsons_del_turno,
)
from app.config import settings


class CRMState(TypedDict):
    messages: Annotated[list, add_messages]


SYSTEM_PROMPT_CRM = SystemMessage(content="""
Eres el asistente del CRM Vivo de Contexto AI, para el CORREDOR (o inmobiliaria). Le ayudas a
entender y trabajar SU cartera de interesados hablándole en español natural, cálido y conciso.

QUÉ PUEDES HACER (con tus herramientas):
- tool_stats_embudo: el estado de su embudo (total, por etapa, calientes, dormidos, por reenganchar).
- tool_timeline_de_lead: la historia completa de un interesado suyo (conversación + handoff + estado).

REGLAS INNEGOCIABLES (son el foso de Contexto — la honestidad):
1. NUNCA inventes ni calcules cifras. TODO número (cuántos leads, en qué etapa, scores) sale de las
   herramientas. Si no llamaste a la herramienta, no des un número. Si la herramienta no trae el dato,
   di exactamente "No tengo ese dato" — jamás un número plausible.
2. Distingue lo VERIFICADO de lo ESTIMADO al narrar: un evento como "pidió corredor" o una etapa del
   embudo es verificado; el "score" es una estimación heurística. Rotúlalo si lo mencionas.
3. FAIR HOUSING — línea roja: NUNCA describas, agrupes ni priorices interesados por clase protegida
   (familia, hijos, edad, nacionalidad, religión, género, discapacidad, "zona familiar"). Solo hablas
   de la necesidad transaccional declarada (qué preguntó, presupuesto, etapa, frescura). Si el corredor
   pide "agrúpame por tipo de familia" o algo similar, decline con tacto y reencuadra a la necesidad
   objetiva (etapa/interés/actividad).
4. Solo hablas de SUS interesados (las herramientas ya lo garantizan). No inventes leads que no aparezcan.

ESTILO: español rioplatense-neutro sin anglicismos, directo y accionable. Prioriza el OUTCOME del
corredor (a quién contactar/retomar, qué lead está caliente), no la actividad bonita. Respuestas
cortas; si listas leads, pocos y con por qué. Cuando haya reenganche sugerido, ofrécelo tal cual.
""")


def _build_crm_graph() -> StateGraph:
    # Mismo patrón que graph.py: cliente Anthropic con SSL explícito inyectado antes de bind_tools.
    _client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        http_client=httpx.AsyncClient(verify=_ssl_verify),
    )
    base_llm = ChatAnthropic(model=settings.llm_model, temperature=0.2, max_tokens=1500)
    base_llm.__dict__["_async_client"] = _client
    llm = base_llm.bind_tools(CRM_TOOLS)

    async def llm_node(state: CRMState) -> dict:
        response = await llm.ainvoke([SYSTEM_PROMPT_CRM] + state["messages"])
        # Controles deterministas de honestidad (cifras + Fair Housing), primera clase.
        # Fase 1: OBSERVAR (log + contadores), no bloquear. Ver crm_guardrails.MODO_BLOQUEO.
        # Un fallo del guardrail NUNCA debe tumbar la respuesta.
        try:
            texto = texto_de_content(response.content)
            resultado = evaluar_salida_crm(texto, tool_jsons_del_turno(state["messages"]))
            registrar_guardrail(resultado)
        except Exception as exc:  # noqa: BLE001
            import logging
            logging.getLogger("crm.guardrails").warning("guardrail falló (no bloqueante): %s", exc)
        return {"messages": [response]}

    tool_node = ToolNode(tools=CRM_TOOLS)
    graph = StateGraph(CRMState)
    graph.add_node("llm", llm_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "llm")
    graph.add_conditional_edges("llm", tools_condition)
    graph.add_edge("tools", "llm")
    return graph


# Memoria por-proceso (Fase 1). Ver nota del módulo.
compiled_crm_graph = _build_crm_graph().compile(checkpointer=MemorySaver())
