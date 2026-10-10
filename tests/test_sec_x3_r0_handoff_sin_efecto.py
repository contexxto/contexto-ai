"""SEC-X3-R0 · la tool del LLM NO produce el efecto del handoff.

ANTES (origin/main 5f0d857): un tool call del modelo a `tool_connect_with_broker` llamaba a
`registrar_handoff` → fila `handoff_sesion`, `asignacion`, campana + push + correo diferido
al corredor y, en una conversación sin QR, audiencia del transcript completo para él y su
agencia. El «consentimiento» vivía solo en el prompt y en el docstring.

DESPUÉS: la tool no tiene efecto. Solo valida el inmueble y le dice al modelo que la persona
debe pulsar «Hablar con el corredor»; el efecto queda únicamente en el endpoint HTTP de ese
control explícito (`solicitar_handoff`), con la autoridad de sesión de siempre.

Invariantes que este fichero congela:

    DECISIÓN ≠ PERMISO PARA EJECUTAR
    SALIDA DEL LLM ≠ ACTO DEL COMPRADOR

Las validaciones RESTRINGEN y nunca conceden: ninguna convierte prosa en permiso. Sin
Postgres, sin clave de LLM, sin red. Ningún xfail.
"""
import ast
import json
import pathlib
import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt import ToolNode

import app.agent.tools as T
import app.notifications as notificaciones
import app.routers.chat as chat

RAIZ = pathlib.Path(__file__).resolve().parent.parent

ACTIVO = str(uuid.UUID(int=0x1111))
OTRO = str(uuid.UUID(int=0x2222))
SIN_DUENO = str(uuid.UUID(int=0x3333))
NO_EXISTE = str(uuid.UUID(int=0x4444))

SESION_LIBRE = "session-AbCdEfGhIjKlMnOp"
SESION_QR = f"qr-{ACTIVO}-AbCdEfGhIjKlMnOp"

# Lo que el efecto tocaba. Si cualquiera se alcanza desde la tool, el test falla.
_EFECTOS_EN_CHAT = ("registrar_handoff", "_notificar_corredor", "_congelar_asignacion",
                    "registrar_notificacion", "ensure_handoff_tables")


def _busqueda(*ids, nombre="tool_search_nearby_assets"):
    """El resultado de una tool de búsqueda tal como queda en el hilo."""
    return ToolMessage(content=json.dumps({"assets": [{"id": i} for i in ids]}),
                       name=nombre, tool_call_id=f"call-{nombre}")


@pytest.fixture
def efectos(monkeypatch):
    """Centinelas sobre TODO lo que producía el efecto: registran y fallan si se alcanzan."""
    alcanzados: list[str] = []

    def _centinela(nombre):
        async def _f(*a, **k):
            alcanzados.append(nombre)
            raise AssertionError(f"la tool alcanzó el efecto {nombre}")
        return _f

    for nombre in _EFECTOS_EN_CHAT:
        monkeypatch.setattr(chat, nombre, _centinela(nombre))
    monkeypatch.setattr(notificaciones, "send_notification", _centinela("send_notification"))
    return alcanzados


@pytest.fixture
def catalogo(monkeypatch):
    """Catálogo falso para la única lectura que hace la tool. Registra cada consulta."""
    filas = {
        ACTIVO: {"id": ACTIVO, "con_corredor": True},
        OTRO: {"id": OTRO, "con_corredor": True},
        SIN_DUENO: {"id": SIN_DUENO, "con_corredor": False},
    }
    consultas: list[str] = []

    async def _falso(activo_id):
        consultas.append(activo_id)
        return filas.get(activo_id)

    monkeypatch.setattr(T, "_activo_para_contacto", _falso)
    return consultas


async def _invocar(session_id, activo_id=None, messages=()):
    entrada = {"state": {"messages": list(messages)}}
    if activo_id is not None:
        entrada["activo_id"] = activo_id
    salida = await T.tool_connect_with_broker.ainvoke(
        entrada, config={"configurable": {"thread_id": session_id}})
    return json.loads(salida)


def _sin_efecto(r):
    assert r["efecto"] == "ninguno"
    assert r["contacto_registrado"] is False
    assert r["corredor_avisado"] is False


# ── 1 y 2 · el camino feliz NO llama a registrar_handoff ni a ningún efecto ────────────────

async def test_1_ok_no_llama_registrar_handoff_ni_avisa(efectos, catalogo):
    r = await _invocar(SESION_LIBRE, ACTIVO, [HumanMessage("busco"), _busqueda(ACTIVO, OTRO)])
    assert r["ok"] is True and r["activo_id"] == ACTIVO
    _sin_efecto(r)
    assert efectos == []


async def test_2_llamarla_varias_veces_tampoco_produce_efecto(efectos, catalogo):
    hilo = [_busqueda(ACTIVO)]
    for _ in range(3):
        _sin_efecto(await _invocar(SESION_LIBRE, ACTIVO, hilo))
    _sin_efecto(await _invocar(SESION_QR))
    assert efectos == []


@pytest.mark.parametrize("sesion,activo,hilo,motivo", [
    (SESION_LIBRE, "abc-123", [], "ACTIVO_ID_INVALIDO"),
    (SESION_LIBRE, None, [], "SIN_INMUEBLE"),
    (SESION_LIBRE, OTRO, [_busqueda(ACTIVO)], "NO_MOSTRADO_EN_LA_CONVERSACION"),
    (SESION_LIBRE, NO_EXISTE, [_busqueda(NO_EXISTE)], "INMUEBLE_INEXISTENTE"),
    (SESION_LIBRE, SIN_DUENO, [_busqueda(SIN_DUENO)], "SIN_CORREDOR"),
    (SESION_QR, OTRO, [], "ACTIVO_DISTINTO_AL_DEL_LETRERO"),
    ("", ACTIVO, [_busqueda(ACTIVO)], "SIN_SESION"),
])
async def test_2b_ningun_camino_de_fallo_produce_efecto(efectos, catalogo, sesion, activo, hilo, motivo):
    r = await _invocar(sesion, activo, hilo)
    assert r["ok"] is False and r["motivo"] == motivo
    _sin_efecto(r)
    assert efectos == []


# ── 3 · ninguna escritura en base alcanzable desde la tool ────────────────────────────────

class _Res:
    def __init__(self, filas):
        self._filas = filas

    def mappings(self):
        return self

    def all(self):
        return self._filas


class _SesionQueAnota:
    """Sesión de base falsa: anota cada sentencia y cada commit."""

    def __init__(self, log):
        self.log = log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sentencia, params=None):
        self.log.append(("execute", str(sentencia)))
        return _Res([{"id": ACTIVO, "con_corredor": True}])

    async def commit(self):
        self.log.append(("commit", ""))


async def test_3_la_unica_sentencia_es_un_select_y_no_hay_commit(efectos, monkeypatch):
    log: list[tuple[str, str]] = []
    monkeypatch.setattr(T, "AsyncSessionLocal", lambda: _SesionQueAnota(log))
    r = await _invocar(SESION_LIBRE, ACTIVO, [_busqueda(ACTIVO)])
    assert r["ok"] is True
    assert [k for k, _ in log] == ["execute"], log
    sql = log[0][1].strip().upper()
    assert sql.startswith("SELECT ")
    for prohibida in ("INSERT", "UPDATE", "DELETE", "UPSERT", "ALTER", "CREATE"):
        assert prohibida not in sql
    assert efectos == []


def _funciones(arbol) -> dict[str, ast.AST]:
    return {n.name: n for n in ast.walk(arbol)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_3b_por_ast_la_tool_y_sus_ayudantes_no_escriben():
    """La tool y sus ayudantes no hacen commit, no ejecutan SQL directo salvo la lectura de
    `_activo_para_contacto`, y no contienen sentencias de escritura."""
    arbol = ast.parse((RAIZ / "app/agent/tools.py").read_text(encoding="utf-8"))
    fns = _funciones(arbol)
    for nombre in ("tool_connect_with_broker", "_activo_para_contacto",
                   "_ids_mostrados_en_la_conversacion", "_activo_del_prefijo_qr",
                   "_uuid_canonico", "_respuesta_sin_efecto"):
        nodo = fns[nombre]
        for sub in ast.walk(nodo):
            if isinstance(sub, ast.Attribute):
                assert sub.attr not in ("commit", "execute", "add", "flush"), (nombre, sub.attr)
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                texto = sub.value.upper()
                for prohibida in ("INSERT ", "UPDATE ", "DELETE ", "ALTER ", "CREATE "):
                    assert prohibida not in texto, (nombre, sub.value)


# ── 4 · id inválido o inexistente → falla explícita ──────────────────────────────────────

@pytest.mark.parametrize("malo", ["abc", "not-a-uuid", "123", "qr-" + ACTIVO])
async def test_4_id_invalido_falla_sin_consultar_la_base(efectos, catalogo, malo):
    r = await _invocar(SESION_LIBRE, malo, [_busqueda(ACTIVO)])
    assert r["ok"] is False and r["motivo"] == "ACTIVO_ID_INVALIDO"
    assert catalogo == []


async def test_4b_inexistente_y_sin_corredor_fallan(efectos, catalogo):
    r = await _invocar(SESION_LIBRE, NO_EXISTE, [_busqueda(NO_EXISTE)])
    assert (r["ok"], r["motivo"]) == (False, "INMUEBLE_INEXISTENTE")
    r = await _invocar(SESION_LIBRE, SIN_DUENO, [_busqueda(SIN_DUENO)])
    assert (r["ok"], r["motivo"]) == (False, "SIN_CORREDOR")


# ── 5 · el inmueble tiene que estar en los resultados de ESTA conversación ────────────────

async def test_5_inmueble_que_no_salio_en_resultados_falla(efectos, catalogo):
    r = await _invocar(SESION_LIBRE, OTRO, [_busqueda(ACTIVO)])
    assert (r["ok"], r["motivo"]) == (False, "NO_MOSTRADO_EN_LA_CONVERSACION")
    assert catalogo == []


async def test_5b_mencionarlo_en_prosa_no_lo_vuelve_resultado(efectos, catalogo):
    """El id escrito por la persona o por el modelo no es evidencia: solo cuentan los
    resultados de las tools de búsqueda."""
    hilo = [HumanMessage(f"me interesa {OTRO}"), AIMessage(content=f"el {OTRO} está bien"),
            _busqueda(ACTIVO)]
    r = await _invocar(SESION_LIBRE, OTRO, hilo)
    assert r["motivo"] == "NO_MOSTRADO_EN_LA_CONVERSACION"


async def test_5c_otra_tool_que_no_es_de_busqueda_no_cuenta(efectos, catalogo):
    hilo = [_busqueda(OTRO, nombre="tool_fetch_asset_lifecycle_specs")]
    r = await _invocar(SESION_LIBRE, OTRO, hilo)
    assert r["motivo"] == "NO_MOSTRADO_EN_LA_CONVERSACION"


async def test_5d_el_id_se_compara_en_forma_canonica(efectos, catalogo):
    r = await _invocar(SESION_LIBRE, ACTIVO.upper(), [_busqueda(ACTIVO)])
    assert r["ok"] is True and r["activo_id"] == ACTIVO


# ── 6 · sesión de QR + otro inmueble → rechazo explícito, nunca sustitución ───────────────

async def test_6_qr_con_otro_inmueble_se_rechaza_sin_sustituir(efectos, catalogo):
    r = await _invocar(SESION_QR, OTRO, [_busqueda(OTRO)])
    assert r["ok"] is False and r["motivo"] == "ACTIVO_DISTINTO_AL_DEL_LETRERO"
    assert r["activo_id"] == OTRO, "no se puede reemplazar en silencio por el del letrero"
    assert catalogo == []


async def test_6b_qr_con_el_mismo_inmueble_o_sin_id_es_el_del_letrero(efectos, catalogo):
    for pedido in (None, ACTIVO, ACTIVO.upper()):
        r = await _invocar(SESION_QR, pedido)
        assert r["ok"] is True and r["activo_id"] == ACTIVO
        _sin_efecto(r)


def test_6c_paridad_del_prefijo_con_el_router():
    """La regla del prefijo de la tool es la MISMA que la de `chat.activo_de_session`."""
    casos = [SESION_QR, f"qr-{ACTIVO.upper()}-x", f"qr-{ACTIVO}", "qr-abc-123-x",
             SESION_LIBRE, "qr-", "", f"session-{ACTIVO}", f"QR-{ACTIVO}-x"]
    for s in casos:
        assert T._activo_del_prefijo_qr(s) == chat.activo_de_session(s), s


# ── 7 · ninguna tool del agente importa o llama al efecto ─────────────────────────────────

def _lista_literal(arbol, nombre):
    for n in ast.walk(arbol):
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == nombre for t in n.targets):
            return [e.id for e in n.value.elts if isinstance(e, ast.Name)]
    raise AssertionError(f"no se encontró {nombre}")


_PROHIBIDOS = {"registrar_handoff", "_notificar_corredor", "_congelar_asignacion",
               "registrar_notificacion", "send_notification", "solicitar_handoff"}


def test_7_ninguna_tool_de_AGENT_TOOLS_importa_o_llama_el_efecto():
    arbol = ast.parse((RAIZ / "app/agent/tools.py").read_text(encoding="utf-8"))
    fns = _funciones(arbol)
    for nombre in _lista_literal(arbol, "AGENT_TOOLS"):
        for sub in ast.walk(fns[nombre]):
            if isinstance(sub, ast.ImportFrom):
                assert not (sub.module or "").startswith("app.routers"), (nombre, sub.module)
                assert not ({a.name for a in sub.names} & _PROHIBIDOS), nombre
            if isinstance(sub, ast.Name):
                assert sub.id not in _PROHIBIDOS, (nombre, sub.id)
            if isinstance(sub, ast.Attribute):
                assert sub.attr not in _PROHIBIDOS, (nombre, sub.attr)


def test_7b_tools_py_no_importa_nada_de_los_routers():
    arbol = ast.parse((RAIZ / "app/agent/tools.py").read_text(encoding="utf-8"))
    for n in ast.walk(arbol):
        if isinstance(n, ast.ImportFrom):
            assert not (n.module or "").startswith("app.routers"), n.module
        if isinstance(n, ast.Import):
            assert not any(a.name.startswith("app.routers") for a in n.names)


# ── 8 · el camino HTTP explícito sigue intacto ────────────────────────────────────────────

def _llamadas(nodo) -> set[str]:
    out = set()
    for sub in ast.walk(nodo):
        if isinstance(sub, ast.Call):
            f = sub.func
            out.add(f.id if isinstance(f, ast.Name) else getattr(f, "attr", ""))
    return out


def test_8_el_boton_sigue_siendo_el_camino_del_efecto():
    arbol = ast.parse((RAIZ / "app/routers/chat.py").read_text(encoding="utf-8"))
    fns = _funciones(arbol)
    boton = _llamadas(fns["solicitar_handoff"])
    assert {"_exigir_autoridad", "registrar_handoff"} <= boton
    efecto = _llamadas(fns["registrar_handoff"])
    assert {"_congelar_asignacion", "_notificar_corredor"} <= efecto
    # Y nadie más que el botón llama al efecto dentro de app/.
    llamadores = set()
    for py in (RAIZ / "app").rglob("*.py"):
        for nombre, nodo in _funciones(ast.parse(py.read_text(encoding="utf-8"))).items():
            if nombre != "registrar_handoff" and "registrar_handoff" in _llamadas(nodo):
                llamadores.add((py.relative_to(RAIZ).as_posix(), nombre))
    assert llamadores == {("app/routers/chat.py", "solicitar_handoff")}, llamadores


# ── 9 · lo que ve el LLM y lo que le dice el prompt ───────────────────────────────────────

def test_9_el_llm_solo_ve_activo_id():
    props = T.tool_connect_with_broker.tool_call_schema.model_json_schema().get("properties", {})
    assert set(props) == {"activo_id"}


def test_9b_la_descripcion_de_la_tool_dice_que_no_contacta():
    desc = T.tool_connect_with_broker.description
    assert "DOES NOT" in desc and "Hablar con el corredor" in desc
    assert "transfers the conversation" not in desc


def test_9c_el_prompt_no_atribuye_el_contacto_a_la_tool():
    from app.agent.graph import SYSTEM_PROMPT
    texto = SYSTEM_PROMPT.content
    assert "no lleva argumentos" not in texto
    assert "para conectarlo DENTRO del chat" not in texto
    assert "¿te conecto con el corredor" not in texto.lower()
    assert "NO contacta a nadie" in texto
    assert "«Hablar con el corredor»" in texto


async def test_9d_el_resultado_nunca_afirma_que_hubo_contacto(efectos, catalogo):
    r = await _invocar(SESION_LIBRE, ACTIVO, [_busqueda(ACTIVO)])
    assert "avisé" not in r["message"].lower()
    assert "no contactó a nadie ni produjo ningún efecto de handoff" in r["message"]
    assert "no produjo ninguna nueva divulgación ni cambió la audiencia" in r["message"]


# ── 9e · CLOSEOUT: sin sobreafirmar lo que pertenece a SEC-X2-R0 ──────────────────────────
#
# SEC-X3-R0 prueba LLM OUTPUT ≠ BUYER ACT. NO prueba ATTRIBUTION ≠ DISCLOSURE AUTHORITY:
# en una sesión qr- el código heredado (X-2) puede haber concedido audiencia del transcript
# ANTES del clic. Ningún texto de esta unidad puede afirmar que «no se compartió nada» ni que
# el clic es el (primer) momento en que se comparte la conversación.

_SOBREAFIRMACIONES = (
    "no se compartió nada",
    "no se comparte nada",
    "comparte la conversación",
    "compartir la conversación",
    "consentimiento para compartir",
)


async def test_9e_ningun_resultado_afirma_que_no_se_compartio_nada(efectos, catalogo):
    casos = [(SESION_LIBRE, ACTIVO, [_busqueda(ACTIVO)]), (SESION_QR, None, []),
             (SESION_LIBRE, "abc", []), (SESION_QR, OTRO, []),
             (SESION_LIBRE, OTRO, [_busqueda(ACTIVO)]), (SESION_LIBRE, None, [])]
    for sesion, activo, hilo in casos:
        texto = (await _invocar(sesion, activo, hilo))["message"].lower()
        for frase in _SOBREAFIRMACIONES:
            assert frase not in texto, (sesion, activo, frase)


def test_9f_el_prompt_no_hace_del_clic_el_momento_de_la_divulgacion():
    from app.agent.graph import SYSTEM_PROMPT
    texto = SYSTEM_PROMPT.content.lower()
    for frase in _SOBREAFIRMACIONES + ("ese clic es",):
        assert frase not in texto, frase
    assert "no comparte nada" not in texto


def test_9g_la_descripcion_de_la_tool_no_sobreafirma():
    desc = T.tool_connect_with_broker.description.lower()
    for frase in ("share the conversation", "consent to share", "that click is"):
        assert frase not in desc, frase
    assert "creates no new disclosure" in desc


# ── 9h/9i · FINAL CLOSEOUT: el corredor recibe una solicitud, no la decisión ──────────────
#
#     DECISIÓN ≠ AUTORIDAD
#     HANDOFF ≠ TRANSFERENCIA DE LA PROPIEDAD DE LA DECISIÓN
#
# El corredor recibe una solicitud de contacto / atención humana: no adquiere la decisión del
# comprador ni autoridad sobre ella. Y el docstring de `registrar_handoff` no puede afirmar lo
# que es de SEC-X2-R0 (audiencia legacy antes del clic) ni de UI-04 (qué inmueble manda el
# botón). Se compara en texto plano: una frase partida en dos líneas sigue siendo la frase.

def _plano(texto: str) -> str:
    return " ".join(texto.lower().split())


def test_9h_el_prompt_no_transfiere_la_decision_al_corredor():
    from app.agent.graph import SYSTEM_PROMPT
    texto = _plano(SYSTEM_PROMPT.content)
    for frase in ("transfiere la decisión", "transferir la decisión", "se le transfiere",
                  "transferencia de la decisión", "traspasa la decisión", "cede la decisión",
                  "delega la decisión", "asume la decisión", "decisión pasa al corredor",
                  "en manos del corredor", "el corredor decide", "decide el corredor"):
        assert frase not in texto, frase
    assert ("solicitar contacto con un corredor humano para continuar la atención o coordinar "
            "el siguiente paso") in texto


def test_9i_el_docstring_de_registrar_handoff_no_sobreafirma():
    doc = _plano(chat.registrar_handoff.__doc__ or "")
    for frase in ("solo lo dispara el clic", "audiencia del transcript) solo", "solo el clic",
                  "no se comparte nada", "no se compartió nada", "en pantalla",
                  "que ve la persona", "está viendo"):
        assert frase not in doc, frase
    # SEC-X2-R0 (actualización esperada): el docstring ya no remite UI-04 a «otra unidad»;
    # ahora dice qué hace el acto y sigue sin sobreafirmar la audiencia legacy.
    assert "no afirma que no haya existido audiencia legacy antes de sec-x2-r0" in doc
    assert "aquí no se infiere ninguno" in doc
    assert "principal_requested_at" in doc
    assert "solo restringe" in doc and "nunca concede" in doc


# ── 10 · por el camino REAL: ToolNode inyecta el estado y no hay efecto ───────────────────

async def test_10_toolnode_inyecta_el_hilo_y_no_produce_efecto(efectos, catalogo):
    llamada = AIMessage(content="", tool_calls=[{
        "name": "tool_connect_with_broker", "args": {"activo_id": ACTIVO}, "id": "c-1"}])
    hilo = [HumanMessage("quiero visitarlo"), _busqueda(ACTIVO), llamada]
    salida = await ToolNode(T.AGENT_TOOLS).ainvoke(
        {"messages": hilo}, config={"configurable": {"thread_id": SESION_LIBRE}})
    (msg,) = salida["messages"]
    r = json.loads(msg.content)
    assert r["ok"] is True and r["activo_id"] == ACTIVO
    _sin_efecto(r)
    assert efectos == []


async def test_10b_toolnode_sin_resultado_en_el_hilo_rechaza(efectos, catalogo):
    llamada = AIMessage(content="", tool_calls=[{
        "name": "tool_connect_with_broker", "args": {"activo_id": ACTIVO}, "id": "c-2"}])
    salida = await ToolNode(T.AGENT_TOOLS).ainvoke(
        {"messages": [HumanMessage("sí, conéctame"), llamada]},
        config={"configurable": {"thread_id": SESION_LIBRE}})
    r = json.loads(salida["messages"][0].content)
    assert (r["ok"], r["motivo"]) == (False, "NO_MOSTRADO_EN_LA_CONVERSACION")
    assert efectos == []
