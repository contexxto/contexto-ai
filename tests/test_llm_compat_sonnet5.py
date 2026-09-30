"""Migración Sonnet 4.5 → Sonnet 5, paso 1: el mismo código sirve para los dos modelos.

Anthropic retira `claude-sonnet-4-5` el 2026-11-24. `claude-sonnet-5` rompe dos supuestos:

  * responde **400** a un `temperature` distinto del default (el chat y el CRM mandaban 0.2);
  * si se omite `thinking`, **razona por defecto** y ese razonamiento cuenta contra
    `max_tokens` (`extraer_preferencias` tiene tope 400).

Este fichero congela las dos promesas del paso 1:

  1. **En 4.5 nada cambia.** Lo que sale por el cable es lo de antes: `temperature=0.2` en el
     chat y el CRM, y sin razonamiento (ahora explícito, antes por omisión).
  2. **En Sonnet 5 nada da 400 ni razona a escondidas.** Toda llamada al LLM de `app/` fija
     `thinking`, y ninguna fija un `temperature` literal.

La segunda se mide por AST sobre `app/`, no por grep, y la guarda se prueba contra una fuente
sintética que la infringe: una regla que sólo se ejerce cuando alguien la rompe no está medida.
"""
import ast
import asyncio
import pathlib

import httpx
import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

import evals.run_evals as run_evals
from app import config, preferencias
from app.agent import crm_graph, graph
from app.config import THINKING_APAGADO, temperatura_llm

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SONNET_45 = "claude-sonnet-4-5-20250929"
SONNET_5 = "claude-sonnet-5"


# ── La guarda estructural ──────────────────────────────────────────────────────────────

def _es_llamada_al_llm(nodo: ast.Call) -> bool:
    f = nodo.func
    if isinstance(f, ast.Name) and f.id == "ChatAnthropic":
        return True
    return (isinstance(f, ast.Attribute) and f.attr in ("create", "stream")
            and isinstance(f.value, ast.Attribute) and f.value.attr == "messages")


def _infracciones(fuente: str) -> list[str]:
    """Llamadas al LLM sin `thinking` o con un `temperature` literal."""
    malas = []
    for nodo in ast.walk(ast.parse(fuente)):
        if not (isinstance(nodo, ast.Call) and _es_llamada_al_llm(nodo)):
            continue
        kws = {k.arg: k.value for k in nodo.keywords}
        if "thinking" not in kws:
            malas.append(f"línea {nodo.lineno}: sin thinking")
        if isinstance(kws.get("temperature"), ast.Constant) and kws["temperature"].value is not None:
            malas.append(f"línea {nodo.lineno}: temperature literal")
    return malas


def _llamadas_por_fichero() -> dict[str, int]:
    conteo = {}
    for ruta in sorted((RAIZ / "app").rglob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        n = sum(1 for x in ast.walk(arbol) if isinstance(x, ast.Call) and _es_llamada_al_llm(x))
        if n:
            conteo[ruta.relative_to(RAIZ).as_posix()] = n
    return conteo


def test_el_inventario_de_llamadas_al_llm_es_el_conocido():
    """Si aparece una llamada nueva, este test obliga a mirarla. Y evita que la guarda de abajo
    pase en verde por haber recorrido un árbol vacío."""
    assert _llamadas_por_fichero() == {
        "app/agent/crm_graph.py": 1,
        "app/agent/graph.py": 1,
        "app/buyer/interprete.py": 1,
        "app/preferencias.py": 1,
        "app/routers/match.py": 2,
        "app/vision.py": 1,
    }


def test_toda_llamada_al_llm_de_app_fija_thinking_y_ninguna_temperature_literal():
    malas = {}
    for ruta in sorted((RAIZ / "app").rglob("*.py")):
        encontradas = _infracciones(ruta.read_text(encoding="utf-8"))
        if encontradas:
            malas[ruta.relative_to(RAIZ).as_posix()] = encontradas
    assert malas == {}


def test_la_guarda_muerde_con_una_fuente_sintetica():
    sintetica = (
        "llm = ChatAnthropic(model=m, temperature=0.2, max_tokens=10)\n"
        "r = await cliente().messages.create(model=m, max_tokens=10, messages=[])\n"
        "ok = ChatAnthropic(model=m, temperature=temperatura_llm(0.2), thinking=T)\n"
    )
    assert _infracciones(sintetica) == [
        "línea 1: sin thinking",
        "línea 1: temperature literal",
        "línea 2: sin thinking",
    ]


# ── Lo que sale por el cable, según el modelo ─────────────────────────────────────────

def test_temperatura_llm_solo_se_conserva_en_sonnet_45(monkeypatch):
    monkeypatch.setattr(config.settings, "llm_model", SONNET_45)
    assert temperatura_llm(0.2) == 0.2
    monkeypatch.setattr(config.settings, "llm_model", SONNET_5)
    assert temperatura_llm(0.2) is None


def _kwargs_del_constructor(monkeypatch, modulo, constructor) -> list[dict]:
    """Construye el grafo REAL con ChatAnthropic falseado y devuelve lo que le pasaron."""
    capturados = []

    class _Fab:
        def __init__(self, **kw):
            capturados.append(kw)

        def bind_tools(self, _tools):
            return self

    monkeypatch.setattr(modulo, "ChatAnthropic", _Fab)
    getattr(modulo, constructor)()
    assert capturados, "el constructor no creó ningún ChatAnthropic"
    return capturados


@pytest.mark.parametrize("modulo,constructor", [(graph, "_build_graph"),
                                                (crm_graph, "_build_crm_graph")])
@pytest.mark.parametrize("modelo,temperatura", [(SONNET_45, 0.2), (SONNET_5, None)])
def test_payload_real_de_langchain_del_chat_y_del_crm(monkeypatch, modulo, constructor,
                                                       modelo, temperatura):
    monkeypatch.setattr(config.settings, "llm_model", modelo)
    for kw in _kwargs_del_constructor(monkeypatch, modulo, constructor):
        payload = ChatAnthropic(**kw, api_key="sk-falsa")._get_request_payload(
            [HumanMessage("hola")])
        assert payload["model"] == modelo
        assert payload["thinking"] == {"type": "disabled"}
        assert payload.get("temperature") == temperatura
        if temperatura is None:
            assert "temperature" not in payload  # ni siquiera el default: no se envía


class _ClienteFalso:
    def __init__(self):
        self.llamadas = []
        self.messages = self

    async def create(self, **kw):
        self.llamadas.append(kw)
        raise RuntimeError("sin red en tests")


def test_extraer_preferencias_manda_el_razonamiento_apagado(monkeypatch):
    cliente = _ClienteFalso()
    monkeypatch.setattr(preferencias.settings, "anthropic_api_key", "sk-falsa")
    monkeypatch.setattr(preferencias, "_client", lambda: cliente)
    assert asyncio.run(preferencias.extraer_preferencias(["quiero 3 dormitorios"])) == {}
    assert cliente.llamadas[0]["thinking"] == THINKING_APAGADO == {"type": "disabled"}
    assert cliente.llamadas[0]["max_tokens"] == 400


# ── El juez de los evals ─────────────────────────────────────────────────────────────

def test_el_juez_que_no_responde_no_aprueba(monkeypatch):
    """Con el modelo del juez retirado, cada llamada fallaba y contaba como APROBADA."""
    def _post_caido(*_a, **_kw):
        raise httpx.ConnectError("modelo retirado")

    monkeypatch.setattr(run_evals, "ANTHROPIC_API_KEY", "sk-falsa")
    monkeypatch.setattr(run_evals.httpx, "post", _post_caido)
    ok, razon = run_evals.judge("¿hay algo?", "sí", "debe responder")
    assert ok is False
    assert "juez no disponible" in razon


def test_el_juez_por_defecto_no_es_un_modelo_retirado():
    assert not run_evals.JUDGE_MODEL.startswith("claude-3")
