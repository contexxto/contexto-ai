"""La ÚNICA lectura autoritativa del texto que el modelo le escribe a la persona.

Anthropic/LangChain entregan `AIMessage.content` de dos formas: `str`, o una LISTA de bloques
tipados (`text`, `thinking`, `tool_use`, `input_json_delta`…). Con herramientas atadas o con
thinking llega casi siempre como lista. Todo consumidor que audite o muestre la respuesta tiene
que leerla igual, o dos caminos que deberían coincidir divergen en silencio:

  · `routers/chat._texto_del_chunk` — lo que se transmite y lo que ve la persona;
  · el guardrail de steering de `agent/graph.llm_node` — que hasta MODEL-MIGRATION-PRODUCT-
    HARDENING 0.1 sólo corría si `content` era `str`, así que con lista callaba sin rastro.

Semántica (la que ya tenía `_texto_del_chunk`): un `str` se devuelve tal cual; de una lista sólo
cuentan los bloques `text`, unidos sin separador, porque así se concatenan en pantalla. El
`thinking` no es prosa para la persona y un `tool_use` tampoco. Cualquier otra cosa es "".

`crm_guardrails.texto_de_content` es la lectura del CRM, con otra semántica (une con espacio y
acepta cadenas sueltas); unificarla cambiaría el comportamiento del CRM y queda fuera de esta
unidad.
"""
from __future__ import annotations


def texto_de_salida(contenido) -> str:
    """El texto de `AIMessage.content`, venga como `str` o como lista de bloques."""
    if isinstance(contenido, str):
        return contenido
    if isinstance(contenido, list):
        return "".join(
            b.get("text") or ""
            for b in contenido
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""
