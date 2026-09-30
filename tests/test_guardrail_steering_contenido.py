"""H1 · el guardrail de steering de `llm_node` evalúa la respuesta VENGA COMO VENGA el content.

EL DEFECTO (MODEL-MIGRATION-PRODUCT-HARDENING 0.1). `llm_node` sólo llamaba a
`detectar_steering` si `response.content` era `str`. Con herramientas atadas —y con thinking—
Anthropic/LangChain entregan una LISTA de bloques, así que el guardrail no corría y no dejaba
rastro. Se vio en el arnés de paridad del 2026-09-30: una respuesta de claude-sonnet-5 que
`detectar_steering` marca en dos frases no produjo ningún `[FAIR-HOUSING]` en el grafo.

Estas pruebas construyen el grafo REAL con el LLM falseado y llaman al nodo `llm` con cada forma
de content. Si alguien restaura la condición `isinstance(texto, str)`, las variantes de lista
vuelven a callar y estas pruebas se ponen rojas: ése es el control negativo.

No cambia la semántica de `detectar_steering` (B2 · falsos positivos por negación citada queda
documentado aparte).
"""
import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agent import graph as G

FRASE = "Te recomiendo esta zona familiar, ideal para criar a tus hijos."
LIMPIA = "Con un barrio concreto te doy caminabilidad, ruido y servicios con su fuente."


class _LLM:
    def __init__(self, **_kw):
        self.respuesta = None

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, _messages):
        return self.respuesta


def _salida_del_nodo(monkeypatch, capsys, contenido) -> str:
    creados = []

    class _Fab(_LLM):
        def __init__(self, **kw):
            super().__init__(**kw)
            creados.append(self)

    monkeypatch.setattr(G, "ChatAnthropic", _Fab)
    g = G._build_graph()
    creados[0].respuesta = AIMessage(content=contenido)
    r = g.nodes["llm"].runnable
    nodo = getattr(r, "afunc", None) or r.func
    capsys.readouterr()
    asyncio.run(nodo({"messages": [HumanMessage("¿Es buena zona para mi familia?")]}))
    return capsys.readouterr().out


FORMAS_CON_STEERING = {
    "string": FRASE,
    "bloques_de_texto": [{"type": "text", "text": "Te recomiendo esta zona familiar, "},
                         {"type": "text", "text": "ideal para criar a tus hijos."}],
    "thinking_mas_texto": [{"type": "thinking", "thinking": "", "signature": "sig"},
                           {"type": "text", "text": FRASE}],
    "tool_mas_texto": [{"type": "text", "text": FRASE},
                       {"type": "tool_use", "id": "t1", "name": "tool_search_nearby_assets",
                        "input": {"latitude": -0.2, "longitude": -78.5}}],
}


@pytest.mark.parametrize("forma", sorted(FORMAS_CON_STEERING))
def test_el_guardrail_corre_con_cualquier_forma_de_content(monkeypatch, capsys, forma):
    salida = _salida_del_nodo(monkeypatch, capsys, FORMAS_CON_STEERING[forma])
    assert "[FAIR-HOUSING]" in salida, f"el guardrail no evaluó la respuesta con content {forma}"


@pytest.mark.parametrize("contenido", ["", [], [{"type": "thinking", "thinking": "", "signature": "s"}]],
                         ids=["string_vacio", "lista_vacia", "solo_thinking"])
def test_contenido_vacio_no_dispara_ni_revienta(monkeypatch, capsys, contenido):
    assert "[FAIR-HOUSING]" not in _salida_del_nodo(monkeypatch, capsys, contenido)


@pytest.mark.parametrize("contenido", [LIMPIA, [{"type": "text", "text": LIMPIA}]], ids=["string", "bloques"])
def test_texto_limpio_no_dispara(monkeypatch, capsys, contenido):
    assert "[FAIR-HOUSING]" not in _salida_del_nodo(monkeypatch, capsys, contenido)


def test_el_pensamiento_no_se_audita_como_prosa(monkeypatch, capsys):
    """El thinking no es lo que la persona lee: una frase prohibida SÓLO en el bloque thinking no
    dispara. El guardrail audita la respuesta emitida, no el razonamiento."""
    contenido = [{"type": "thinking", "thinking": FRASE, "signature": "s"},
                 {"type": "text", "text": LIMPIA}]
    assert "[FAIR-HOUSING]" not in _salida_del_nodo(monkeypatch, capsys, contenido)
