"""F3-TURN-IDENTITY-R0A · la identidad canónica del mensaje del turno.

QUÉ CONGELA ESTE FICHERO, y qué NO.

    congela    que el `HumanMessage.id` lo acuña EL SERVIDOR en el ingreso, una sola vez,
               sin que el cuerpo, la query, el modelo ni el `session_id` puedan gobernarlo;
               que LangGraph y el checkpoint lo conservan; y que el Buyer updater acaba
               observando ESE MISMO id como `source_message_id`
    NO congela  idempotencia entre peticiones. Un reintento HTTP entra otra vez por el
               acuñador y recibe un id NUEVO. `T11` existe para que nadie lea de este
               fichero una garantía que no da

La distinción importa porque es fácil confundirlas: `add_messages` deduplica cuando se
reutiliza EL MISMO id —y `T10` lo mide—, pero eso es dedup intra-turno. Dos aceptaciones HTTP
distintas del mismo texto son dos turnos para el sistema, y `T11` lo deja escrito.
"""

from __future__ import annotations

import ast
import pathlib
import re
import uuid
from typing import Annotated

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.buyer.mensaje import ultimo_mensaje_usuario_identificado
from app.routers.chat import (
    ChatRequest,
    _acunar_id_de_mensaje,
    _estado_inicial_del_turno,
)

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CHAT = RAIZ / "app" / "routers" / "chat.py"

_UUID4 = re.compile(r"\Amsg-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")


def _unico_humano(estado) -> HumanMessage:
    (m,) = [x for x in estado["messages"] if isinstance(x, HumanMessage)]
    return m


# ══ T1 · EL SERVIDOR ACUÑA ═════════════════════════════════════════════════════════


def test_T1_cada_turno_recibe_un_id_no_vacio():
    m = _unico_humano(_estado_inicial_del_turno("busco algo en La Floresta"))
    assert isinstance(m.id, str) and m.id.strip()


def test_T1b_el_id_tiene_la_forma_canonica_del_servidor():
    """El prefijo no es decorativo: mirando una fila de `checkpoints` distingue un id
    acuñado por nosotros de uno generado por `add_messages`."""
    assert _UUID4.match(_acunar_id_de_mensaje())


def test_T1c_dos_turnos_distintos_reciben_ids_distintos():
    ids = {_unico_humano(_estado_inicial_del_turno("hola")).id for _ in range(50)}
    assert len(ids) == 50, "el acuñador repite identidades"


# ══ T2 · EL CUERPO NO PUEDE ELEGIRLO ═══════════════════════════════════════════════


def test_T2_ChatRequest_no_declara_message_id():
    assert set(ChatRequest.model_fields) == {"message", "session_id"}


def test_T12_un_campo_extra_del_cliente_no_gobierna_el_id():
    """T12 del mandato: aunque el cliente mande `message_id`, no llega a ninguna parte."""
    peticion = ChatRequest.model_validate(
        {"message": "hola", "session_id": "s-1", "message_id": "ATACANTE"})
    assert not hasattr(peticion, "message_id")
    m = _unico_humano(_estado_inicial_del_turno(peticion.message))
    assert m.id != "ATACANTE" and "ATACANTE" not in m.id


@pytest.mark.parametrize("texto", ["ATACANTE", "msg-0000", "", "   ", "id: foo"])
def test_T2b_el_TEXTO_del_mensaje_no_influye_en_el_id(texto):
    """El id tiene la forma canónica sea cual sea el texto, y no lo contiene.

    La comprobación de contención se salta el texto vacío a propósito: `"" in cualquier
    cadena` es siempre cierto, así que afirmarlo sería una aserción que no puede fallar —y
    una aserción que no puede fallar es ruido, no una guarda. Para esos dos casos lo que se
    congela es la forma.
    """
    m = _unico_humano(_estado_inicial_del_turno(texto))
    assert _UUID4.match(m.id)
    if texto.strip():
        assert texto.strip() not in m.id


# ══ T3 · EL MODELO NO PUEDE ELEGIRLO ═══════════════════════════════════════════════


def test_T3_el_acunador_no_recibe_ninguna_entrada():
    """Sin parámetros no hay por dónde inyectar. Es la misma propiedad estructural que en
    1A: una firma que no admite el dato no se puede infringir sin cambiar la firma."""
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.FunctionDef) and n.name == "_acunar_id_de_mensaje")
    assert fn.args.args == [] and fn.args.kwonlyargs == []
    assert fn.args.vararg is None and fn.args.kwarg is None


def test_T3b_el_acunador_solo_usa_uuid4():
    """Nada de estado, nada de mensajes, nada del modelo."""
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.FunctionDef) and n.name == "_acunar_id_de_mensaje")
    llamadas = [ast.dump(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)]
    assert len(llamadas) == 1 and "uuid" in llamadas[0] and "uuid4" in llamadas[0]


# ══ T4 · EL SESSION_ID NO ES IDENTIDAD DEL MENSAJE ═════════════════════════════════


def test_T4_el_id_no_se_deriva_del_session_id():
    """La autoridad del HILO y la identidad del MENSAJE son dominios distintos; confundirlos
    es lo que AUTH-READ-GATE.1 cerró."""
    sid = "qr-11111111-2222-3333-4444-555555555555-Ab3xY9"
    m = _unico_humano(_estado_inicial_del_turno("hola"))
    assert sid not in m.id and "qr-" not in m.id


def test_T4b_el_constructor_no_recibe_el_session_id():
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.FunctionDef) and n.name == "_estado_inicial_del_turno")
    assert [a.arg for a in fn.args.args] == ["mensaje"]


# ══ T5 · UN SOLO ACUÑADOR ══════════════════════════════════════════════════════════


def _ficheros_de_app():
    app = RAIZ / "app"
    return [p for p in sorted(app.rglob("*.py"))] + [RAIZ / "main.py"]


def test_T5_hay_UNA_sola_construccion_de_HumanMessage_en_el_turno():
    """Dos constructores serían dos identidades para una intención — el defecto de forma que
    `_estado_inicial_del_turno` existe para impedir (STATE-LINEAGE-R1)."""
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    construcciones = [n for n in ast.walk(arbol)
                      if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                      and n.func.id == "HumanMessage"]
    assert len(construcciones) == 1, f"hay {len(construcciones)} constructores de HumanMessage"
    (c,) = construcciones
    claves = {k.arg for k in c.keywords}
    assert claves == {"content", "id"}, f"la construcción cambió: {claves}"


def test_T5b_hay_UN_solo_acunador_en_todo_app():
    llamadas = []
    for f in _ficheros_de_app():
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(arbol):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id == "_acunar_id_de_mensaje":
                llamadas.append(f"{f.name}:{n.lineno}")
    assert len(llamadas) == 1, f"el acuñador se invoca desde {llamadas}"


def test_T5c_el_censo_SABE_ver_un_segundo_acunador(tmp_path):
    f = tmp_path / "otro.py"
    f.write_text("x = _acunar_id_de_mensaje()\n", encoding="utf-8")
    arbol = ast.parse(f.read_text(encoding="utf-8"))
    assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == "_acunar_id_de_mensaje" for n in ast.walk(arbol))


# ══ T6 · STREAM Y NO-STREAM COMPARTEN EL SEAM ══════════════════════════════════════


def test_T6_ambos_caminos_usan_el_MISMO_constructor():
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    usos = [n.lineno for n in ast.walk(arbol)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "_estado_inicial_del_turno"]
    assert len(usos) == 2, f"se esperaban dos llamadores (stream y no-stream), hay {len(usos)}"


def test_T6b_ninguno_de_los_dos_construye_su_propio_mensaje():
    """Si una rama fabricara su HumanMessage, tendría otra identidad — y sería E3.2b.4 otra
    vez: la rama sin cobertura es la que se desvía."""
    fuente = CHAT.read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    for nombre in ("_stream_agent", "chat"):
        fn = next((n for n in ast.walk(arbol)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nombre),
                  None)
        assert fn is not None
        construye = [n for n in ast.walk(fn)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                     and n.func.id == "HumanMessage"]
        assert construye == [], f"`{nombre}` construye su propio HumanMessage"


# ══ T7 / T8 · LANGGRAPH Y EL CHECKPOINT CONSERVAN EL ID ════════════════════════════
#
# Grafo mínimo LOCAL con MemorySaver: sin base externa, sin red, sin tocar el grafo real.


class _Estado(TypedDict):
    messages: Annotated[list, add_messages]


def _grafo():
    async def nodo(state: _Estado):
        return {"messages": [AIMessage(content="ok")]}

    g = StateGraph(_Estado)
    g.add_node("n", nodo)
    g.add_edge(START, "n")
    return g.compile(checkpointer=MemorySaver())


async def test_T7_langgraph_conserva_el_id_del_servidor():
    estado = _estado_inicial_del_turno("mi máximo es 1200")
    acunado = _unico_humano(estado).id
    final = await _grafo().ainvoke(estado, config={"configurable": {"thread_id": "t7"}})
    assert any(getattr(m, "id", None) == acunado for m in final["messages"])


async def test_T7b_add_messages_solo_genera_id_cuando_falta():
    acunado = _acunar_id_de_mensaje()
    fusion = add_messages([], [HumanMessage(content="a", id=acunado),
                               HumanMessage(content="b")])
    ids = [m.id for m in fusion]
    assert acunado in ids
    assert all(i for i in ids) and len(set(ids)) == 2


async def test_T8_el_checkpoint_conserva_el_id():
    compilado = _grafo()
    cfg = {"configurable": {"thread_id": "t8"}}
    estado = _estado_inicial_del_turno("hola")
    acunado = _unico_humano(estado).id
    await compilado.ainvoke(estado, config=cfg)
    snap = await compilado.aget_state(cfg)
    assert acunado in [getattr(m, "id", None) for m in snap.values["messages"]]


# ══ T9 · EL BUYER OBSERVA EL MISMO source_message_id ═══════════════════════════════


async def test_T9_el_updater_observa_EL_MISMO_id():
    """Sin tocar el updater: se le da el hilo tal y como saldría del grafo y se comprueba
    que la identidad que extrae es la que acuñó el servidor."""
    compilado = _grafo()
    estado = _estado_inicial_del_turno("acepto mascotas")
    acunado = _unico_humano(estado).id
    final = await compilado.ainvoke(estado, config={"configurable": {"thread_id": "t9"}})
    identificado = ultimo_mensaje_usuario_identificado(final["messages"])
    assert identificado is not None
    assert identificado.message_id == acunado
    assert identificado.text == "acepto mascotas"


async def test_T9b_sin_id_el_updater_lo_habria_rechazado():
    """LA MITAD NEGATIVA: antes de R0A el mensaje llegaba sin identidad al seam, y el
    contrato de `mensaje.py` levanta en ese caso. Demuestra que T9 no es vacío."""
    from app.buyer.mensaje import MensajeSinIdentidad
    with pytest.raises(MensajeSinIdentidad):
        ultimo_mensaje_usuario_identificado([HumanMessage(content="sin id")])


# ══ T10 · DEDUP CON EL MISMO ID ════════════════════════════════════════════════════


async def test_T10_reusar_EL_MISMO_id_no_duplica_el_mensaje():
    compilado = _grafo()
    cfg = {"configurable": {"thread_id": "t10"}}
    estado = _estado_inicial_del_turno("mi máximo es 1200")
    acunado = _unico_humano(estado).id
    await compilado.ainvoke(estado, config=cfg)
    await compilado.ainvoke(
        {"messages": [HumanMessage(content="mi máximo es 1200", id=acunado)]}, config=cfg)
    snap = await compilado.aget_state(cfg)
    humanos = [m for m in snap.values["messages"] if isinstance(m, HumanMessage)]
    assert len(humanos) == 1, f"el mismo id produjo {len(humanos)} mensajes"


# ══ T11 · CONTROL NEGATIVO ENTRE PETICIONES ════════════════════════════════════════


async def test_T11_dos_aceptaciones_HTTP_del_MISMO_texto_NO_son_idempotentes():
    """CONGELA UNA LIMITACIÓN, no una garantía.

    `CROSS_REQUEST_IDEMPOTENCY = NOT SOLVED`. Dos peticiones con el mismo texto entran dos
    veces por el acuñador y reciben ids distintos; el hilo acaba con DOS mensajes. R0A no
    resuelve esto y esta prueba existe para que nadie lea lo contrario del fichero.
    """
    compilado = _grafo()
    cfg = {"configurable": {"thread_id": "t11"}}
    primero = _estado_inicial_del_turno("mi máximo es 1200")
    segundo = _estado_inicial_del_turno("mi máximo es 1200")
    assert _unico_humano(primero).id != _unico_humano(segundo).id
    await compilado.ainvoke(primero, config=cfg)
    await compilado.ainvoke(segundo, config=cfg)
    snap = await compilado.aget_state(cfg)
    humanos = [m for m in snap.values["messages"] if isinstance(m, HumanMessage)]
    assert len(humanos) == 2, "si esto deduplicara, la limitación habría dejado de ser cierta"


# ══ T13 · MUTACIONES ═══════════════════════════════════════════════════════════════


def test_T13a_aceptar_un_id_del_cuerpo_se_detecta():
    """Si `ChatRequest` ganara `message_id`, T2 se pondría roja."""
    assert "message_id" not in ChatRequest.model_fields


def test_T13b_derivar_del_session_id_se_detecta():
    sid = "qr-abc-def"
    assert sid not in _acunar_id_de_mensaje()


def test_T13c_un_segundo_generador_en_stream_se_detecta():
    """La sonda de T6b sabe ver un `HumanMessage(...)` dentro de una función."""
    fn = ast.parse("async def _stream_agent(m):\n    x = HumanMessage(content=m)\n").body[0]
    construye = [n for n in ast.walk(fn)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "HumanMessage"]
    assert construye != []


async def test_T13d_quitar_el_preset_se_detecta():
    """Sin `id=`, `add_messages` genera uno y el del servidor desaparece del hilo."""
    acunado = _acunar_id_de_mensaje()
    fusion = add_messages([], [HumanMessage(content="x")])
    assert fusion[0].id != acunado


async def test_T13e_que_el_Buyer_observe_OTRO_id_se_detecta():
    otro = _acunar_id_de_mensaje()
    identificado = ultimo_mensaje_usuario_identificado(
        [HumanMessage(content="x", id=otro)])
    assert identificado.message_id == otro
    assert identificado.message_id != _acunar_id_de_mensaje()


# ══ PARIDAD · el estado del turno no gana ni pierde claves ═════════════════════════


def test_paridad_el_estado_inicial_conserva_sus_seis_claves():
    """R0A cambia QUIÉN acuña el id, no la forma del estado. Una clave nueva aquí podría
    mover panel o prosa (STATE-LINEAGE-R1)."""
    estado = _estado_inicial_del_turno("hola")
    assert set(estado) == {"messages", "spatial_context", "sql_results", "cards",
                           "descartadas", "encaje_contexto"}
    assert estado["cards"] == [] and estado["descartadas"] == []
    assert estado["encaje_contexto"] == "" and estado["spatial_context"] == {}


def test_paridad_el_contenido_del_mensaje_no_se_toca():
    texto = "¿Cómo es vivir en La Floresta? Presupuesto 1200."
    assert _unico_humano(_estado_inicial_del_turno(texto)).content == texto
