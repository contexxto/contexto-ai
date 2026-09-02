"""G20-B1-R3 · LINEAGE · la barrera es del TURNO ACTUAL, no estado heredado.

POR QUÉ EXISTE ESTE MÓDULO. R3 introdujo una decisión de control entre `encaje_node` y
`llm_node`. Esa decisión viaja por `AgentState`, y las claves de `AgentState` **sin reducer**
son canales `LastValue`: LangGraph las persiste en el checkpoint y las arrastra al turno
siguiente. Una barrera que persiste deja de ser una barrera del turno y se convierte en una
propiedad del hilo.

LOS DOS DEFECTOS QUE ESTE MÓDULO FIJA, ambos reproducidos con grafo y checkpointer reales:

  A · `contrato_territorial_faltante` se escribía SÓLO en la rama de fallo y nunca se
      reiniciaba. Un turno en el que el contrato no se pudo construir dejaba el hilo
      INUTILIZADO: el turno siguiente —sano, sin evidencia territorial siquiera— entraba a
      `llm_node`, leía la bandera heredada y devolvía otra vez la salida controlada sin
      invocar al modelo. `invocaciones_llm = 0` en un turno que no tenía nada malo.

  B · `encaje_contexto` se hereda igual. Un turno territorial dejaba su bloque en el canal, y
      el turno siguiente —sin ninguna operación territorial— recibía en su system prompt la
      sección «RELACIÓN TERRITORIAL» del turno anterior. Es la autoridad de ayer gobernando
      la respuesta de hoy: exactamente lo que el invariante 3 prohíbe, entrando por el canal
      de estado en vez de por el historial de mensajes.

EL DEFECTO B NO LO INTRODUJO R3 —es `STATE-LINEAGE-01`, preexistente— pero R3 lo hereda y su
propio invariante lo prohíbe, así que se cierra aquí.

Y NO SE CIERRA A LO BRUTO. El bloque autoritativo no es sólo territorial: lleva el ORDEN
OBLIGATORIO de la lista y las frases obligatorias de PRESUPUESTO, que G19 midió obedecidas
13/13. Que ese bloque siga vivo en los turnos de seguimiento —«¿y el segundo tiene
parqueadero?»— es deseable y deliberado. Lo que NO puede sobrevivir al turno es la sección
territorial, porque describe evidencia de UNA operación de retrieval concreta. Así que la
herencia se recorta, no se apaga.

LA SOLUCIÓN, y por qué esta y no un reset: ambas decisiones se marcan con el ÍNDICE DE TURNO
(`sum(1 for m in messages if isinstance(m, HumanMessage))`), que es el mismo idioma que el
código ya usa para `preferencias_turno`. Un valor viejo simplemente NO COINCIDE con el turno
actual, así que no hace falta reiniciarlo en cada rama —y no se puede olvidar reiniciarlo,
que es justo el error que produjo el defecto A—.

INVARIANTE CRÍTICO: si el turno actual detiene al LLM, la API nunca puede devolver como
respuesta el AIMessage de un turno anterior.
"""
import asyncio
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agent import graph as G
from app.agent import tools as TOOLS
from app.decision import assembler

ANCLA = {"latitude": -0.20934, "longitude": -78.484919}
TERRITORIAL = "RELACIÓN TERRITORIAL · QUÉ PUEDES AFIRMAR"

_FILA_DB = {
    "id": "ee9ff315", "direccion_estandarizada": "Calle Alemania E12-34",
    "caminabilidad": 100, "walk_score_fuente": None, "score_ruido_predictivo": 1,
    "volumen_trafico_historico": 1, "densidad_poblacional_pico": 1,
    "porcentaje_cobertura_vegetal": 40, "conectividad": None, "servicios_cercanos": None,
    "operacion": "ARRIENDO", "precio": 630, "distancia_metros": 572.0,
    "tipo_activo": "Departamento",
}
_FILA_CARD = {
    "id": "ee9ff315", "direccion": "Calle Alemania E12-34", "tipo_activo": "Departamento",
    "operacion": "ARRIENDO", "precio": 630.0, "imagen_url": None, "caminabilidad": 90,
    "caminabilidad_fuente": "osm", "ruido": "BAJO", "vegetacion": 40, "lat": -0.209,
    "lon": -78.484, "caracteristicas": {}, "servicios_cercanos": None, "conectividad": None,
}


class _LLMFalso:
    """Guionizado: `guion` se consume en orden; lo demás es una respuesta final."""

    def __init__(self, **_kw):
        self.guion = []
        self.invocaciones = []

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, messages):
        self.invocaciones.append(messages)
        return self.guion.pop(0) if self.guion else AIMessage(content="respuesta final")


@pytest.fixture
def mundo(monkeypatch):
    """Grafo REAL compilado con MemorySaver. Sin Postgres, sin red, sin producción."""
    async def _fetch_rows(_q, _p):
        return [dict(_FILA_DB)]

    async def _fetch_cards(_ids):
        return ([dict(_FILA_CARD)], {})

    async def _prefs(_textos):
        return {"operacion": "arriendo"}

    monkeypatch.setattr(TOOLS, "_fetch_rows", _fetch_rows)
    monkeypatch.setattr(assembler, "_fetch_cards_rows", _fetch_cards)
    monkeypatch.setattr(G, "extraer_preferencias", _prefs)

    creados = []

    class _Fabrica(_LLMFalso):
        def __init__(self, **kw):
            super().__init__(**kw)
            creados.append(self)

    monkeypatch.setattr(G, "ChatAnthropic", _Fabrica)
    compilado = G._build_graph().compile(checkpointer=MemorySaver())
    return compilado, creados[0]


def _llamada_busqueda():
    return AIMessage(content="", tool_calls=[{
        "name": "tool_search_nearby_assets",
        "args": {"latitude": ANCLA["latitude"], "longitude": ANCLA["longitude"],
                 "radius_meters": 1200},
        "id": "tc-1"}])


def _turno(mundo, hilo, texto, territorial=True):
    """Un turno COMPLETO del grafo real. Devuelve (resultado, estado, nº de invocaciones)."""
    compilado, llm = mundo
    llm.guion = ([_llamada_busqueda()] if territorial else []) + \
                [AIMessage(content="respuesta final")]
    antes = len(llm.invocaciones)
    cfg = {"configurable": {"thread_id": hilo}}
    r = asyncio.run(compilado.ainvoke({"messages": [HumanMessage(content=texto)]}, cfg))
    st = asyncio.run(compilado.aget_state(cfg)).values
    return r, st, len(llm.invocaciones) - antes


def _romper(monkeypatch, que):
    """Rompe el camino enriquecido, el fallback, o ambos."""
    import app.encaje_contexto as enc

    def _boom(*_a, **_k):
        raise RuntimeError("boom")

    if que in ("enriquecido", "todo"):
        monkeypatch.setattr(enc, "bloque_autoritativo", _boom)
    if que in ("fallback", "todo"):
        monkeypatch.setattr(enc, "bloque_territorial_minimo", _boom)


def _system(llm):
    return llm.invocaciones[-1][0].content


# ══ DEFECTO A · la barrera no puede sobrevivir al turno ════════════════════════

def test_fallo_del_fallback_NO_envenena_el_turno_siguiente(mundo, monkeypatch):
    """EL DEFECTO PRINCIPAL. Turno 1 no puede construir el contrato y se detiene, como debe.
    Turno 2 es sano — y tiene que correr."""
    compilado, llm = mundo
    _romper(monkeypatch, "todo")
    _, st1, _ = _turno(mundo, "hilo-A", "Busco arriendo en La Floresta")
    assert st1.get("contrato_faltante_turno") == 1

    monkeypatch.undo()          # el turno 2 corre con el código sano
    _, st2, n2 = _turno(mundo, "hilo-A", "Ahora cuéntame del barrio")

    assert n2 > 0, "la decisión del turno 1 gobernó el turno 2: el hilo quedó inutilizado"
    assert st2["messages"][-1].content == "respuesta final"


def test_turno_normal_seguido_de_fallo_del_fallback(mundo, monkeypatch):
    """La secuencia inversa: un turno sano no debe impedir que el siguiente se detenga."""
    _, _, n1 = _turno(mundo, "hilo-B", "Busco arriendo en La Floresta")
    assert n1 > 0

    _romper(monkeypatch, "todo")
    r2, st2, _ = _turno(mundo, "hilo-B", "Y en La Carolina?")
    assert st2.get("contrato_faltante_turno") == 2
    assert "no puedo describir con precisión" in r2["messages"][-1].content


def test_cada_encaje_decide_de_nuevo_y_no_hereda(mundo, monkeypatch):
    """La marca lleva el ÍNDICE DE TURNO: un valor viejo no puede coincidir con el actual, así
    que no hace falta reiniciarlo — y no se puede olvidar reiniciarlo."""
    _romper(monkeypatch, "todo")
    _, st1, _ = _turno(mundo, "hilo-C", "Busco arriendo en La Floresta")
    assert st1.get("contrato_faltante_turno") == 1

    monkeypatch.undo()
    _, st2, _ = _turno(mundo, "hilo-C", "Busco arriendo en La Floresta")
    # el valor viejo puede seguir en el canal, pero YA NO GOBIERNA: no es de este turno
    assert st2.get("contrato_faltante_turno") != 2


# ══ DEFECTO B · la autoridad territorial no cruza el turno ═════════════════════

def test_la_seccion_territorial_NO_se_hereda_al_turno_siguiente(mundo):
    """STATE-LINEAGE-01 sobre `encaje_contexto`. El turno 2 no hizo ninguna operación
    territorial: no puede recibir la restricción del turno 1 como si fuera suya."""
    compilado, llm = mundo
    _, st1, _ = _turno(mundo, "hilo-D", "Busco arriendo en La Floresta")
    assert TERRITORIAL in (st1.get("encaje_contexto") or "")

    _turno(mundo, "hilo-D", "hola, gracias", territorial=False)
    assert TERRITORIAL not in _system(llm), (
        "el turno 2 recibió la autoridad territorial del turno 1")


def test_pero_las_reglas_del_PANEL_si_sobreviven_al_seguimiento(mundo):
    """LA MITAD QUE NO SE PUEDE ROMPER. El bloque no es sólo territorial: lleva el ORDEN
    OBLIGATORIO y las frases de PRESUPUESTO, que G19 midió obedecidas 13/13. En un turno de
    seguimiento sobre el MISMO panel esas reglas deben seguir vivas — apagarlas para arreglar
    la herencia territorial cambiaría un defecto por otro."""
    compilado, llm = mundo
    _turno(mundo, "hilo-E", "Busco arriendo en La Floresta")
    _turno(mundo, "hilo-E", "¿y ese tiene parqueadero?", territorial=False)

    system = _system(llm)
    # OJO con el discriminador: «MOTOR DE ENCAJE» aparece en el SYSTEM_PROMPT base
    # (graph.py, regla 10), así que asertar sobre esa frase pasaría siempre — lo comprobó una
    # mutación que devolvía "" y esta prueba no la atrapó. Se asierta sobre la ficha de la
    # tarjeta, que sólo puede venir del bloque emitido.
    assert "Calle Alemania E12-34" in system, (
        "se perdieron las reglas del panel en el turno de seguimiento")
    assert TERRITORIAL not in system, "pero la sección territorial sí debía caerse"


def test_turno_no_territorial_seguido_de_territorial(mundo):
    """La secuencia inversa: el contrato aparece cuando el turno lo exige."""
    compilado, llm = mundo
    _turno(mundo, "hilo-F", "hola", territorial=False)
    assert TERRITORIAL not in _system(llm)

    _turno(mundo, "hilo-F", "Busco arriendo en La Floresta")
    assert TERRITORIAL in _system(llm)


# ══ CHECKPOINT ANTIGUO · sin el campo nuevo ════════════════════════════════════

def test_checkpoint_previo_sin_el_campo_nuevo(mundo):
    """Un hilo creado ANTES de R3 no tiene la clave. Ausente debe significar «no hay barrera»,
    nunca «barrera activa»: lo contrario dejaría inutilizados todos los hilos existentes en el
    momento del despliegue."""
    compilado, llm = mundo
    cfg = {"configurable": {"thread_id": "hilo-viejo"}}

    # estado como lo dejaría una versión anterior: mensajes y bloque, sin las claves de R3
    asyncio.run(compilado.aupdate_state(
        cfg, {"messages": [HumanMessage(content="hola"), AIMessage(content="qué tal")]}))
    estado = asyncio.run(compilado.aget_state(cfg)).values
    assert "contrato_faltante_turno" not in estado

    llm.guion = [AIMessage(content="respuesta final")]
    antes = len(llm.invocaciones)
    r = asyncio.run(compilado.ainvoke({"messages": [HumanMessage(content="sigue")]}, cfg))
    assert len(llm.invocaciones) > antes, "un hilo pre-R3 quedó bloqueado"
    assert r["messages"][-1].content == "respuesta final"


# ══ EL INVARIANTE CRÍTICO ══════════════════════════════════════════════════════

def test_si_el_turno_se_detiene_NO_se_devuelve_el_AIMessage_anterior(mundo, monkeypatch):
    """SI EL TURNO ACTUAL DETIENE AL LLM, LA API NUNCA DEVUELVE LA RESPUESTA DE UN TURNO VIEJO.

    Es el modo de fallo más engañoso de todos: el hilo ya tiene un AIMessage bueno, así que
    cualquier lector que tome «el último AIMessage» encontraría uno y lo daría por respuesta de
    hoy. La persona vería una respuesta plausible, coherente y AJENA a lo que acaba de
    preguntar.
    """
    compilado, llm = mundo
    r1, _, _ = _turno(mundo, "hilo-G", "Busco arriendo en La Floresta")
    anterior = r1["messages"][-1]
    assert isinstance(anterior, AIMessage) and anterior.content == "respuesta final"

    _romper(monkeypatch, "todo")
    r2, st2, n2 = _turno(mundo, "hilo-G", "Y en La Carolina?")

    # El modelo SÍ se invoca UNA vez: la ronda que elige la herramienta, antes de que exista
    # evidencia territorial que gobernar. Lo que la barrera impide es la SEGUNDA entrada, la
    # que escribiría la prosa ya con los resultados delante. Así que 1 es lo correcto y 2 es
    # el defecto — no 0, que sería exigir que el turno ni siquiera pudiera buscar.
    assert n2 == 1, f"entradas a `llm` en el turno: {n2} (2 = la barrera no detuvo la prosa)"

    ultimo = r2["messages"][-1]
    assert isinstance(ultimo, AIMessage)
    assert ultimo is not anterior
    assert ultimo.content != anterior.content
    assert "no puedo describir con precisión" in ultimo.content
    # y el turno actual SÍ produjo un mensaje propio: el hilo no termina en el viejo
    assert r2["messages"].index(ultimo) > r2["messages"].index(anterior)


def test_el_destino_del_grafo_cuando_no_se_invoca_al_LLM(mundo, monkeypatch):
    """El mensaje controlado no lleva `tool_calls`, así que `tools_condition` enruta a END: el
    turno termina limpio en vez de reentrar al bucle."""
    compilado, llm = mundo
    _romper(monkeypatch, "todo")
    r, st, _ = _turno(mundo, "hilo-H", "Busco arriendo en La Floresta")

    ultimo = r["messages"][-1]
    assert not getattr(ultimo, "tool_calls", None), "reentraría al bucle de herramientas"
    proximo = asyncio.run(
        compilado.aget_state({"configurable": {"thread_id": "hilo-H"}})).next
    assert proximo == (), f"el grafo no terminó: siguiente = {proximo}"
