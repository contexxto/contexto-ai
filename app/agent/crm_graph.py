"""
CRM Vivo — grafo ReAct del CORREDOR (Fase 1).

Un segundo agente (distinto al del comprador) que deja al corredor HABLARLE a su CRM
en lenguaje natural: "¿cuántos leads calientes tengo?", "¿a quién retomo?", "muéstrame
el timeline de [lead]". Espeja app/agent/graph.py (init del modelo con SSL explícito +
llm_node con guardrail Fair Housing) pero con SYSTEM_PROMPT y tools del corredor.

Barandas (docs/DISENO_CRM_Vivo.md): el LLM NARRA, nunca calcula; sin dato → "no tengo ese
dato"; jamás segmenta/perfila por clase protegida; solo los leads del propio corredor.

Persistencia: comparte el AsyncPostgresSaver del agente del comprador (setup_crm_checkpointer,
llamado en el lifespan). El hilo del corredor es estable (crm-{user_id}) → la conversación se
retoma tras recargar. Arranca con MemorySaver hasta que el lifespan monte el checkpointer.
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
- REDACTAR un mensaje de reenganche/seguimiento para un interesado (eres su copiloto): si el corredor te
  lo pide, PRIMERO mira su timeline (tool_timeline_de_lead) y apóyate en su reenganche_sugerido y sus
  razones; redacta un mensaje CÁLIDO y breve que aporte VALOR (un dato verificado del entorno que le
  importaba), listo para copiar y pegar. Nunca de presión ni transaccional, nunca inventes datos. Si no
  hay timeline suficiente, dilo y ofrece un borrador genérico de valor en vez de inventar detalles.

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

ESTILO: español neutro latinoamericano, SIN anglicismos, directo y accionable. Usa TUTEO estándar
("tú tienes", "quieres", "contáctalo", "puedes", "deberías") — NUNCA voseo rioplatense/argentino
(nada de "vos tenés", "querés", "contactá", "podés", "arrancamos"). Prioriza el OUTCOME del corredor
(a quién contactar/retomar, qué lead está caliente), no la actividad bonita. Respuestas cortas; si
listas leads, pocos y con por qué. Cuando haya reenganche sugerido, ofrécelo tal cual.
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

    async def llm_node(state: CRMState, config=None) -> dict:
        # Nombre del corredor (del JWT/perfil, vía config) para que firme los mensajes que redacte.
        # Se inyecta como instrucción POR-LLAMADA (no se persiste en el hilo del checkpointer).
        extra = []
        nombre = ((config or {}).get("configurable") or {}).get("corredor_nombre")
        if nombre:
            extra = [SystemMessage(content=f"El corredor se llama «{nombre}». Cuando redactes un mensaje "
                                           f"para un interesado, fírmalo con «{nombre}» — nunca con «[Tu nombre]».")]
        response = await llm.ainvoke([SYSTEM_PROMPT_CRM] + extra + state["messages"])
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


_crm_builder = _build_crm_graph()
# Compilación por defecto: memoria volátil (para que la app arranque siempre).
# setup_crm_checkpointer() la reemplaza por el AsyncPostgresSaver COMPARTIDO con el agente
# del comprador durante el lifespan → el hilo del corredor (crm-{user_id}) persiste y se retoma.
compiled_crm_graph = _crm_builder.compile(checkpointer=MemorySaver())


def setup_crm_checkpointer(checkpointer) -> None:
    """Re-compila el grafo del CRM con el checkpointer Postgres compartido (mismo pool que el
    agente del comprador, ver graph.get_checkpointer()). Los thread_id no colisionan
    (crm-{user} vs qr-{session}). Si es None (Postgres no disponible), conserva el MemorySaver."""
    global compiled_crm_graph
    if checkpointer is not None:
        compiled_crm_graph = _crm_builder.compile(checkpointer=checkpointer)
        print("  CRM Vivo: checkpointer Postgres compartido ACTIVO — hilo del corredor persistente")
