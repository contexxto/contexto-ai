"""F3.0b — la costura de entrada del Buyer Harness.

Demuestra que el mensaje nuevo del usuario llega a la costura **con su identidad real**, que
la selección es determinista y que no se fabrica procedencia bajo ninguna circunstancia.

Lo que estos tests NO demuestran, a propósito: que la costura esté conectada al runtime. No
lo está. F3.0b la construye; E3.2 la cablea. La autoridad productiva sigue siendo el carril
legacy, y hay un test aquí que lo fija.
"""

import asyncio
from typing import Annotated

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.buyer.mensaje import (
    IdentifiedUserMessage,
    MensajeSinIdentidad,
    mensaje_nuevo_de,
)


# ── Identidad real, tomada del estado ──────────────────────────────────────────────


class _Estado(TypedDict):
    messages: Annotated[list, add_messages]


def _grafo():
    g = StateGraph(_Estado)

    async def nodo(state):
        return {}

    g.add_node("n", nodo)
    g.add_edge(START, "n")
    g.add_edge("n", END)
    return g.compile(checkpointer=MemorySaver())


def test_el_id_lo_asigna_add_messages_y_la_costura_lo_toma():
    """El recorrido completo: el mensaje entra sin id, LangGraph se lo asigna, y la costura
    lee ESE id — no uno propio."""
    cg, cfg = _grafo(), {"configurable": {"thread_id": "t-1"}}
    crudo = HumanMessage(content="solo bajo $450")
    assert crudo.id is None, "así lo construye chat.py"

    asyncio.run(cg.ainvoke({"messages": [crudo]}, cfg))
    estado = asyncio.run(cg.aget_state(cfg))
    del_estado = estado.values["messages"][-1]

    identificado = mensaje_nuevo_de(estado.values["messages"])
    assert identificado.message_id == del_estado.id
    assert identificado.text == "solo bajo $450"


def test_un_turno_nuevo_trae_id_nuevo_y_el_anterior_conserva_el_suyo():
    cg, cfg = _grafo(), {"configurable": {"thread_id": "t-2"}}

    asyncio.run(cg.ainvoke({"messages": [HumanMessage(content="busco departamento")]}, cfg))
    primero = mensaje_nuevo_de(asyncio.run(cg.aget_state(cfg)).values["messages"])

    asyncio.run(cg.ainvoke({"messages": [HumanMessage(content="solo bajo $450")]}, cfg))
    estado = asyncio.run(cg.aget_state(cfg)).values["messages"]
    segundo = mensaje_nuevo_de(estado)

    assert segundo.message_id != primero.message_id
    assert segundo.text == "solo bajo $450"
    # El anterior sigue en el hilo, con el MISMO id que tenía.
    assert estado[0].id == primero.message_id


def test_la_seleccion_es_el_ultimo_mensaje_del_usuario():
    """Determinista, sin heurística de "cuál parece nuevo": el último que cumple el filtro."""
    msgs = [
        HumanMessage(content="busco departamento", id="m-1"),
        AIMessage(content="te muestro opciones"),
        ToolMessage(content="{}", name="tool_x", tool_call_id="t"),
        HumanMessage(content="solo bajo $450", id="m-2"),
        AIMessage(content="quedan 2"),
    ]
    assert mensaje_nuevo_de(msgs) == IdentifiedUserMessage(message_id="m-2", text="solo bajo $450")


def test_los_mensajes_del_modelo_y_de_herramienta_no_son_candidatos():
    msgs = [HumanMessage(content="hola", id="m-1"),
            AIMessage(content="respuesta", id="a-1"),
            ToolMessage(content="{}", name="t", tool_call_id="x", id="t-1")]
    assert mensaje_nuevo_de(msgs).message_id == "m-1"


@pytest.mark.parametrize("vacio", ["", "   ", "\n\t "])
def test_un_mensaje_en_blanco_no_desplaza_al_ultimo_util(vacio):
    """Mismo filtro que el legacy `_user_texts`: los dos carriles no pueden discrepar sobre
    qué cuenta como mensaje del usuario."""
    msgs = [HumanMessage(content="solo bajo $450", id="m-1"),
            HumanMessage(content=vacio, id="m-2")]
    assert mensaje_nuevo_de(msgs).message_id == "m-1"


# ── Fail-closed: no se fabrica identidad ───────────────────────────────────────────


@pytest.mark.parametrize("sin_id", [None, "", "   "])
def test_sin_id_la_costura_falla_cerrado(sin_id):
    """LA REGLA CENTRAL. Un id inventado produciría una EvidenceRef que valida y miente sobre
    su propio origen — la misma familia que `place_id` inventado o `decision_id` colisionado."""
    msgs = [HumanMessage(content="necesito 3 dormitorios", id=sin_id)]
    with pytest.raises(MensajeSinIdentidad, match="no trae"):
        mensaje_nuevo_de(msgs)


def test_no_se_deriva_la_identidad_del_texto():
    """Dos turnos con el MISMO texto deben tener identidades DISTINTAS. Un hash del contenido
    los colapsaría, y entonces una corrección posterior sería indistinguible de la
    declaración original."""
    a = mensaje_nuevo_de([HumanMessage(content="sí", id="m-1")])
    b = mensaje_nuevo_de([HumanMessage(content="sí", id="m-2")])
    assert a.text == b.text and a.message_id != b.message_id


def test_el_modulo_no_genera_identificadores():
    """Por AST: si apareciera `uuid`, `hash` o `random` aquí, la regla se habría roto sin que
    ningún test funcional lo notara."""
    import ast
    import inspect
    import pathlib

    from app.buyer import mensaje

    arbol = ast.parse(pathlib.Path(inspect.getfile(mensaje)).read_text(encoding="utf-8"))
    importados = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.ImportFrom) and n.module:
            importados.add(n.module.split(".")[0])
        elif isinstance(n, ast.Import):
            importados.update(a.name.split(".")[0] for a in n.names)
    assert not importados & {"uuid", "random", "secrets", "hashlib", "time", "datetime"}

    llamadas = {n.func.id for n in ast.walk(arbol)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "hash" not in llamadas and "id" not in llamadas


# ── Ausente ≠ vacío ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("sin_nada", [[], None, [AIMessage(content="hola")]])
def test_sin_mensajes_del_usuario_devuelve_none_y_no_levanta(sin_nada):
    """`None` es "no hay nada que procesar", no un fallo. Se distingue a propósito de
    `MensajeSinIdentidad`, que sí lo es — la misma distinción que gobierna los contratos F1."""
    assert mensaje_nuevo_de(sin_nada) is None


def test_el_objeto_es_inmutable_y_cerrado():
    m = mensaje_nuevo_de([HumanMessage(content="hola", id="m-1")])
    with pytest.raises(Exception):
        m.message_id = "otro"
    with pytest.raises(Exception):
        IdentifiedUserMessage(message_id="m", text="t", origen="inventado")


@pytest.mark.parametrize("campo,valor", [("message_id", ""), ("text", "")])
def test_no_admite_campos_vacios(campo, valor):
    datos = {"message_id": "m-1", "text": "hola", campo: valor}
    with pytest.raises(Exception):
        IdentifiedUserMessage(**datos)


# ── PARIDAD: la autoridad productiva no cambió ─────────────────────────────────────


def test_la_costura_no_esta_cableada_al_runtime():
    """F3.0b construye la costura; E3.2 la cablea. Que ningún módulo de producción la importe
    es lo que garantiza que el ranking visible siga saliendo del carril legacy."""
    import ast
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parent.parent
    consumidores = []
    for py in (raiz / "app").rglob("*.py"):
        if "__pycache__" in str(py) or py.parts[-2] == "buyer":
            continue
        arbol = ast.parse(py.read_text(encoding="utf-8"))
        for n in ast.walk(arbol):
            if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("app.buyer"):
                consumidores.append(str(py.relative_to(raiz)))
            elif isinstance(n, ast.Import) and any(a.name.startswith("app.buyer") for a in n.names):
                consumidores.append(str(py.relative_to(raiz)))
    assert not consumidores, f"la costura ya se consume en producción: {consumidores}"


def test_el_carril_legacy_sigue_intacto():
    """`_user_texts` no cambió: sigue devolviendo cadenas. F3.0b NO refactoriza el extractor
    antiguo — el blob concatenado (L2) se elimina por diseño en el carril nuevo, no
    arreglando el viejo."""
    from app.decision.assembler import _user_texts

    msgs = [HumanMessage(content="uno", id="m-1"), HumanMessage(content="dos", id="m-2")]
    assert _user_texts(msgs) == ["uno", "dos"]
    assert all(isinstance(t, str) for t in _user_texts(msgs))


def test_el_extractor_legacy_conserva_su_firma():
    import inspect

    from app.preferencias import extraer_preferencias

    firma = inspect.signature(extraer_preferencias)
    assert list(firma.parameters) == ["mensajes_usuario"]


def test_la_costura_no_toca_los_contratos_de_F1():
    """No importa `app.contracts`: F3.0b no construye `EvidenceRefV0` todavía, porque hacerlo
    exigiría decidir `persistence_policy`, que no está congelada."""
    import ast
    import inspect
    import pathlib

    from app.buyer import mensaje

    arbol = ast.parse(pathlib.Path(inspect.getfile(mensaje)).read_text(encoding="utf-8"))
    modulos = {n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module}
    assert not any(m.startswith("app.contracts") for m in modulos)


# ── Fair Housing: la costura no abre un bypass ─────────────────────────────────────


def test_el_texto_sigue_siendo_texto_sin_sanitizar():
    """La costura TRANSPORTA texto libre; no lo convierte en criterios. Ese es justo el motivo
    por el que no puede haber un camino de aquí al motor sin pasar por la whitelist.

    El mensaje de este test contiene atributos protegidos a propósito: la costura los deja
    pasar como TEXTO —no es su trabajo filtrarlos— y por eso la barrera determinista tiene
    que existir aguas abajo, antes de derivar cualquier criterio.
    """
    crudo = "tengo tres hijos y busco algo tranquilo"
    m = mensaje_nuevo_de([HumanMessage(content=crudo, id="m-1")])
    assert m.text == crudo
    assert not hasattr(m, "tranquilidad") and not hasattr(m, "hijos")
    assert set(m.model_dump()) == {"message_id", "text"}


def test_la_costura_no_puede_alimentar_el_motor_por_su_cuenta():
    """No expone nada con forma de preferencia: no hay atajo desde aquí a `calcular_encaje`
    que se salte `_sanitizar`."""
    from app.encaje import DIMENSIONES

    campos = set(IdentifiedUserMessage.model_fields)
    assert campos == {"message_id", "text"}
    assert not campos & set(DIMENSIONES)


def test_la_barrera_de_sanitizacion_sigue_siendo_la_unica_puerta():
    """FH-3 intacta: `_sanitizar` descarta todo lo que no esté en la whitelist. F3.0b no la
    modifica ni la rodea."""
    from app.preferencias import _sanitizar

    assert _sanitizar({"hijos": 3, "familia": True, "tranquilidad": True}) == {"tranquilidad": True}


# ── Caso congelado: mención ≠ preferencia durable ──────────────────────────────────


def test_una_mencion_no_es_estado_durable_del_comprador():
    """CASO B de F3.0a, congelado como política. La costura entrega el mensaje y su id;
    NO decide si "¿cuál de estos es el más caminable?" es un criterio de compra o el objetivo
    de ese turno.

    Que `IdentifiedUserMessage` no tenga ningún campo de preferencia es lo que hace imposible
    que esa clasificación ocurra aquí por accidente. La hará el updater (E3.2), con la
    política durable / turn-only / ambiguo → no persistir.
    """
    m = mensaje_nuevo_de([HumanMessage(content="¿Cuál de estos es el más caminable?", id="m-1")])
    assert m.text == "¿Cuál de estos es el más caminable?"
    assert set(m.model_dump()) == {"message_id", "text"}, (
        "si aquí apareciera algo como `caminable`, la clasificación se habría colado en la costura"
    )
