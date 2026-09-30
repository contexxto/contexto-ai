"""H1 · la ÚNICA lectura autoritativa del texto que el modelo le escribe a la persona.

`app.texto_salida.texto_de_salida` es la fuente; `routers/chat._texto_del_chunk` y el guardrail
de `llm_node` la reutilizan. La semántica es la que ya tenía `_texto_del_chunk` (lo que la
persona ve): sólo bloques `text`, unidos sin separador. `crm_guardrails.texto_de_content` es la
lectura del CRM, con otra semántica, y queda fuera de esta unidad.
"""
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from app.routers.chat import _texto_del_chunk
from app.texto_salida import texto_de_salida

CASOS = {
    "string": ("hola", "hola"),
    "bloques_de_texto": ([{"type": "text", "text": "ho"}, {"type": "text", "text": "la"}], "hola"),
    "thinking_mas_texto": ([{"type": "thinking", "thinking": "secreto", "signature": "s"},
                            {"type": "text", "text": "hola"}], "hola"),
    "tool_mas_texto": ([{"type": "text", "text": "hola"},
                        {"type": "tool_use", "id": "t", "name": "x", "input": {}},
                        {"type": "input_json_delta", "partial_json": "{\"a\""}], "hola"),
    "string_vacio": ("", ""),
    "lista_vacia": ([], ""),
    "none": (None, ""),
    "solo_thinking": ([{"type": "thinking", "thinking": "x", "signature": "s"}], ""),
    "texto_none_en_bloque": ([{"type": "text", "text": None}, {"type": "text", "text": "ok"}], "ok"),
}


@pytest.mark.parametrize("nombre", sorted(CASOS))
def test_texto_de_salida(nombre):
    contenido, esperado = CASOS[nombre]
    assert texto_de_salida(contenido) == esperado


@pytest.mark.parametrize("nombre", sorted(k for k in CASOS if k != "none"))
def test_texto_del_chunk_es_la_misma_lectura(nombre):
    contenido, esperado = CASOS[nombre]
    for envoltorio in (AIMessage, AIMessageChunk):
        assert _texto_del_chunk(envoltorio(content=contenido)) == esperado


def test_texto_del_chunk_sin_content_sigue_devolviendo_vacio():
    """Semántica preservada: un objeto sin `.content` (o un str suelto) no es un chunk del modelo."""
    assert _texto_del_chunk(object()) == ""
    assert _texto_del_chunk("hola suelto") == ""
