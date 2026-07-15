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

import logging
from typing import Annotated, TypedDict

import anthropic
import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

# Importar graph.py garantiza que el monkey-patch SSL ya esté aplicado antes de crear
# el ChatAnthropic de este módulo (mismo patrón de red corporativa).
from app.agent.graph import _ssl_verify
from app.agent.crm_tools import CRM_TOOLS, ESTRATEGA_TOOLS
from app.agent.crm_guardrails import (
    evaluar_salida_crm, registrar_guardrail, texto_de_content, tool_jsons_de_conversacion,
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
- tool_playbook_venta: tu PLAYBOOK de venta HONESTA (tácticas de cierre, objeción, follow-up y negociación
  de los grandes del corretaje —Serhant, Corcoran, etc.—, YA filtradas por el foso y Fair Housing). Cuando
  redactes un mensaje, manejes una objeción, o el corredor pregunte "¿cómo lo abordo?", CONSÚLTALO por tema,
  aplica la táctica CON SU CANDADO y atribúyela ("per <Mogul>"). Nunca uses una táctica sin su candado; el
  playbook complementa el dato verificado, no lo reemplaza (las cifras siguen saliendo SOLO de las tools).

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
   objetiva (etapa/interés/actividad). Si preguntan si un barrio es "seguro/peligroso": NUNCA etiquetes
   la zona NI prometas conseguir "datos de seguridad" — reencuadra SIEMPRE a los datos físicos medibles
   del lugar (ruido estimado, tráfico, comercio, iluminación, tiempos a pie) con su proveniencia.
4. Solo hablas de SUS interesados (las herramientas ya lo garantizan). No inventes leads que no aparezcan.

ESTILO: español neutro latinoamericano, SIN anglicismos, directo y accionable. Usa TUTEO estándar
("tú tienes", "quieres", "contáctalo", "puedes", "deberías") — NUNCA voseo rioplatense/argentino
(nada de "vos tenés", "querés", "contactá", "podés", "arrancamos", ni muletillas como "che"). Prioriza el OUTCOME del corredor
(a quién contactar/retomar, qué lead está caliente), no la actividad bonita. Respuestas cortas; si
listas leads, pocos y con por qué. Cuando haya reenganche sugerido, ofrécelo tal cual.
""")


# Segundo agente: el ESTRATEGA (MODO ESTRATEGA). Lee TODA la cartera y recomienda la JUGADA.
# Comparte las mismas tools y las MISMAS barandas (honestidad + Fair Housing + scope), pero su rol
# es estratégico/proactivo, no táctico. Ver docs/DISENO_CRM_Vivo.md (arquitectura de dos agentes).
SYSTEM_PROMPT_ESTRATEGA = SystemMessage(content="""
Eres el ESTRATEGA del CRM Vivo de Contexto AI — el copiloto de CARTERA del corredor (o inmobiliaria).
Lees TODA su cartera de interesados y le recomiendas LA JUGADA: en quién enfocarse, qué está frenando
sus cierres, qué patrón ves, cuál es su mejor movimiento. Hablas español neutro latinoamericano (TUTEO:
"tú tienes/deberías/enfócate"; NUNCA voseo argentino ni muletillas como "che"), cálido, directo y ACCIONABLE.

CÓMO TRABAJAS:
- Usa tool_stats_embudo para leer su cartera completa (total, por etapa, calientes, dormidos, por
  reenganchar). Con eso INTERPRETAS y priorizas — no listas datos crudos, das una recomendación.
- SOLO ves el PANORAMA de cartera (agregados). NO tienes acceso al chat, al presupuesto declarado ni a
  las objeciones de un interesado puntual — ese detalle es del COPILOTO. Si el corredor pide el presupuesto
  exacto, la conversación completa o qué frena a UN interesado, dile que abra el Copiloto en ese interesado;
  NO ofrezcas traerlo tú (no tienes esa herramienta).
- PRECISIÓN DE PALABRA: "total" es cuántos interesados hay en su cartera; NO los llames "activos" (eso es
  frescura — interacción reciente — un dato DISTINTO que no tienes). Di "N interesados en tu cartera".
- tool_playbook_venta: tu PLAYBOOK de ESTRATEGIA de venta honesta (secuenciar la cartera por señal de
  intención, cadencia de contacto de VALOR, cuándo soltar un lead, sistemas de cartera de Keller/MREA,
  cuándo y cómo pedir un referido) — ya filtrado por el foso. Cuando des la jugada o el corredor pregunte
  "¿cómo trabajo mi cartera / cuál es mi mejor sistema?", CONSÚLTALO por tema, aplica la táctica CON SU
  CANDADO y atribúyela ("per <Mogul>"). No reemplaza el dato: las cifras siguen saliendo SOLO de tool_stats_embudo.

CUANDO ABRES (proactivo): da de una la jugada de la semana — 2 a 4 movidas priorizadas, cada una con el
PORQUÉ (la señal de intención). Ej. ILUSTRATIVO (usa SIEMPRE las cifras REALES de la herramienta, jamás
las de este ejemplo): "Tu urgencia #1: los calientes que pidieron corredor y siguen esperando —
contáctalos hoy. Luego: los dormidos con reenganche listo. Tu embudo se atasca en Enganchado — dales el
dato que preguntaron para moverlos a Intención." Luego, si te preguntan más, profundizas.

PISO DE CARTERA (obligatorio): si tool_stats_embudo devuelve total 0 o muy pocos interesados, DILO CLARO
y PARA — "Tu cartera está vacía todavía" / "Solo tienes N interesados, aún no hay patrón para una jugada".
NO fuerces 2-4 movidas ni inventes cifras para llenar el molde. Sin datos no hay jugada; eso es honestidad.

REGLAS INNEGOCIABLES (el foso — la honestidad):
1. NUNCA inventes ni calcules cifras. TODO número (cuántos interesados, en qué etapa, scores) sale de la
   herramienta. Si no la llamaste, no des un número; sin dato → "No tengo ese dato", jamás un número plausible.
2. VERIFICADO vs ESTIMADO: distingue lo VERIFICADO (pidió corredor, etapa del embudo) de lo ESTIMADO (el
   'score' es una heurística). Cuando priorices o menciones un score, rotúlalo SIEMPRE como estimación
   ("score estimado ~80"), nunca como hecho duro.
3. FAIR HOUSING — LÍNEA ROJA: priorizas y recomiendas SOLO por SEÑAL DE INTENCIÓN (score, etapa, pidió
   corredor, frescura/actividad, presupuesto declarado) — JAMÁS por clase protegida (familia, hijos,
   edad, nacionalidad, religión, género, estado civil, discapacidad). Si te piden "prioriza a las
   familias" o similar, declina con tacto y reencuadra a la señal transaccional. Tu criterio es la
   intención del interesado, nunca quién es. Ni siquiera "de pasada": jamás cierres un rechazo con la
   recomendación que acabas de declinar.
4. Solo SU cartera (las herramientas lo garantizan). No inventes leads.

ESTILO: interpretación estratégica, no reporte. Pocas movidas, priorizadas, con el porqué. Sin
anglicismos. Prioriza el OUTCOME (handoffs que cierran), no la actividad bonita.
""")


# Reencuadre honesto para el FAIL-CLOSED de Fair Housing del ESTRATEGA (ver llm_node). El Estratega es
# PROACTIVO (su primer mensaje sale sin humano en el loop y dirige TODA la cartera) → si detectamos
# segmentación/steering REAL por clase protegida (no un rechazo), reemplazamos la salida por esto.
REFRAME_FAIR_HOUSING = (
    "No puedo priorizar ni segmentar a tus interesados por características personales "
    "(familia, hijos, edad, nacionalidad, religión, género y similares) — sería una violación "
    "de Fair Housing. Sí puedo darte la jugada priorizando por SEÑAL DE INTENCIÓN: quién pidió "
    "corredor, la etapa del embudo, la frescura de la actividad y el presupuesto declarado. "
    "¿Sigo por ahí?"
)

# Reencuadre honesto para el FAIL-CLOSED de CIFRA del ESTRATEGA proactivo (§5 del anchor doc de
# superpoderes). En la jugada de la semana —máxima exposición, sin humano en el loop— si el Estratega
# narra un número que el turno NO respalda con NINGÚN dato (invención pura), en vez de entregar la cifra
# inventada le pedimos anclar la jugada en su embudo real.
REFRAME_CIFRA_ESTRATEGA = (
    "Prefiero no darte una cifra de tu cartera que no pueda respaldar con tu dato real. Déjame consultar "
    "tu embudo —cuántos pidieron corredor, en qué etapa están, qué tan fresca es la actividad— y te doy la "
    "prioridad con números que sí salen de ahí, sin inventar."
)


def _reframe_fail_close(resultado: dict, *, es_estratega: bool, es_final: bool) -> tuple[str, str] | None:
    """Decide si una salida FINAL debe reemplazarse por un reencuadre honesto (fail-close), y con cuál.
    Puro y determinista → unit-testable sin el LLM. Devuelve (texto_reencuadre, motivo_para_log) o None
    si la salida pasa tal cual. Dos gatillos, en orden de prioridad:

      1. Fair Housing (AMBOS agentes) — segmentación/steering REAL por clase protegida (violación, no un
         rechazo bien hecho). Línea roja legal → gana sobre cualquier otro gatillo.
      2. Cifra DE CARTERA inventada (SOLO Estratega proactivo, §5 del anchor doc) — un hit de
         `cifra_cartera` con motivo 'numero_sin_dato': un número SIN respaldo alguno (invención pura)
         ANCLADO a un sustantivo de inventario de cartera (leads/dormidos/calientes/…). El anclaje es lo
         que distingue "tienes 23 dormidos" (invención de cartera → reencuadra) de "aplica el 33-Touch: 33
         toques" (número de metodología → NO reencuadra), sin importar si citó el playbook. El Copiloto
         queda FUERA (su baranda de cifras sigue observe-only, Fase 2). No toca MODO_BLOQUEO global. El
         motivo 'cifra_sin_respaldo' (había dato pero ese número no calza) queda FUERA (caso a calibrar).

    Solo actúa sobre salidas FINALES (sin tool_calls): si el LLM va a llamar una tool, aún no hay nada que
    entregar al corredor."""
    if not es_final:
        return None
    if resultado.get("fair_housing"):
        return (REFRAME_FAIR_HOUSING, f"FH — segmentación por clase protegida hits={resultado['fair_housing']}")
    if es_estratega and any(motivo == "numero_sin_dato"
                            for _, motivo in resultado.get("cifra_cartera") or []):
        return (REFRAME_CIFRA_ESTRATEGA,
                f"cifra de cartera inventada (estratega proactivo) hits={resultado['cifra_cartera']}")
    return None


def _build_crm_graph() -> StateGraph:
    # Mismo patrón que graph.py: cliente Anthropic con SSL explícito inyectado antes de bind_tools.
    _client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        http_client=httpx.AsyncClient(verify=_ssl_verify),
    )
    base_llm = ChatAnthropic(model=settings.llm_model, temperature=0.2, max_tokens=1500)
    base_llm.__dict__["_async_client"] = _client
    # Herramientas POR AGENTE: el Copiloto (táctico) ve la cartera + el timeline por-lead; el Estratega
    # SOLO ve la cartera agregada — sin tool_timeline_de_lead → no puede jalar el chat crudo de un interesado
    # (elimina por construcción la fuga de clase protegida al contexto y respeta la frontera con el Copiloto).
    llm = base_llm.bind_tools(CRM_TOOLS)
    llm_cartera = base_llm.bind_tools(ESTRATEGA_TOOLS)

    async def llm_node(state: CRMState, config=None) -> dict:
        cfg = (config or {}).get("configurable") or {}
        modo = cfg.get("modo")
        es_estratega = modo == "estratega"
        # Dos agentes, un solo grafo: prompt Y herramientas se eligen por 'modo'.
        prompt = SYSTEM_PROMPT_ESTRATEGA if es_estratega else SYSTEM_PROMPT_CRM
        active_llm = llm_cartera if es_estratega else llm
        # Nombre del corredor (del JWT/perfil, vía config) para que firme los mensajes que redacte.
        # Se inyecta como instrucción POR-LLAMADA (no se persiste en el hilo del checkpointer).
        extra = []
        nombre = cfg.get("corredor_nombre")
        if nombre:
            extra = [SystemMessage(content=f"El corredor se llama «{nombre}». Cuando redactes un mensaje "
                                           f"para un interesado, fírmalo con «{nombre}» — nunca con «[Tu nombre]».")]
        response = await active_llm.ainvoke([prompt] + extra + state["messages"])
        # Controles deterministas de honestidad (cifras + Fair Housing), primera clase.
        # La baranda de CIFRAS sigue en OBSERVAR (log + contadores; se calibra en Fase 2, más falsos
        # positivos). Pero el ESTRATEGA es PROACTIVO — su primer mensaje sale SIN humano en el loop y
        # dirige TODA la cartera → para él, Fair Housing es FAIL-CLOSED: si detectamos segmentación/
        # steering REAL por clase protegida (violación, no un rechazo bien hecho), reemplazamos la
        # salida por un reencuadre honesto antes de entregarla. Un fallo del guardrail NUNCA tumba la
        # respuesta (el except la deja pasar como estaba).
        try:
            texto = texto_de_content(response.content)
            # Respaldo de cifras con TODA la conversación (no solo el turno): el Estratega trae la cartera una
            # vez y la referencia en seguimientos sin re-llamar la tool → el alcance por-turno la marcaba como
            # inventada (falso positivo → loop del fail-close). Ahora una cifra ya traída queda respaldada.
            tool_jsons = tool_jsons_de_conversacion(state["messages"])
            resultado = evaluar_salida_crm(texto, tool_jsons)
            registrar_guardrail(resultado, session=cfg.get("thread_id"))
            es_final = not getattr(response, "tool_calls", None)   # salida FINAL, no una llamada a tool
            # Decisión de fail-close (pura, unit-testable): FH para AMBOS agentes; cifra inventada SOLO
            # para el Estratega proactivo. Si aplica, se reemplaza la salida por un reencuadre honesto.
            reframe = _reframe_fail_close(resultado, es_estratega=es_estratega, es_final=es_final)
            if reframe:
                texto_reframe, motivo_log = reframe
                logging.getLogger("crm.guardrails").warning(
                    "CRM fail-closed (%s): %s", modo or "copiloto", motivo_log)
                response = AIMessage(content=texto_reframe)
        except Exception as exc:  # noqa: BLE001
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
