"""F3.0a — la frontera de extracción, caracterizada. EVIDENCIA, no implementación.

    HumanMessage → _user_texts → extraer_preferencias → tool input → _sanitizar → dict

Estos tests fijan lo que el sistema hace HOY, incluidas las pérdidas semánticas. Ninguno
propone lo que debería hacer: eso vive en la matriz CURRENT → TARGET del reporte
`docs/agentic_decision_system/09_PHASE_3_BUYER_EXTRACTION_CHARACTERIZATION.md`.

Todos son deterministas y **sin red**: el cliente Anthropic se sustituye por un doble que
captura la petición. Ninguna aserción depende de lo que un modelo real conteste.

Que un test aquí sea verde NO significa que el comportamiento sea correcto. Significa que
está medido. Varios de ellos documentan defectos reales observados en producción el
2026-08-25, y romperlos sin querer sería perder la evidencia que justifica F3.
"""

import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app import preferencias
from app.contracts.buyer_v0 import CriterionOrigin, DecisionCriterionV0, Operator
from app.decision.assembler import _recortar_grid, _user_texts
from app.decision.context import decidir_sobre_presupuesto
from app.encaje import DIMENSIONES, calcular_encaje
from app.preferencias import _sanitizar, extraer_preferencias


# ── Doble del cliente: captura la petición, cero red ───────────────────────────────


class _Bloque:
    type = "tool_use"
    name = "registrar_preferencias"

    def __init__(self, payload):
        self.input = payload


class _Respuesta:
    def __init__(self, payload):
        self.content = [_Bloque(payload)]


class _ClienteFalso:
    """Sustituye a `anthropic.AsyncAnthropic`. Guarda los kwargs de cada llamada."""

    def __init__(self, payload=None, error=None):
        self.payload, self.error, self.llamadas = payload or {}, error, []
        self.messages = self

    async def create(self, **kw):
        self.llamadas.append(kw)
        if self.error:
            raise self.error
        return _Respuesta(self.payload)


@pytest.fixture
def cliente(monkeypatch):
    def _fabricar(payload=None, error=None):
        c = _ClienteFalso(payload, error)
        monkeypatch.setattr(preferencias.settings, "anthropic_api_key", "sk-fake")
        monkeypatch.setattr(preferencias, "_client", lambda: c)
        return c

    return _fabricar


def _extraer(textos):
    return asyncio.run(extraer_preferencias(textos))


# ── Q1 · qué unidad entra al extractor ─────────────────────────────────────────────


def test_al_extractor_solo_llegan_cadenas_sueltas():
    """`_user_texts` devuelve `m.content`: el objeto `HumanMessage` NO viaja.

    Es el hecho que gobierna toda la unidad. Lo que el extractor recibe es una lista de
    strings sin identidad, sin orden explícito, sin marca de tiempo y sin sesión — así que
    ninguna decisión posterior puede atribuir un campo a un mensaje concreto, por muy buena
    que sea la costura que se le ponga después.
    """
    msgs = [HumanMessage(content="hola", id="msg-1"),
            AIMessage(content="respuesta del modelo"),
            HumanMessage(content="solo bajo $450", id="msg-2")]
    salida = _user_texts(msgs)

    assert salida == ["hola", "solo bajo $450"]
    assert all(isinstance(t, str) for t in salida)
    assert not any(hasattr(t, "id") for t in salida)


def test_la_firma_del_extractor_no_admite_identidad():
    """No es que se pierda por descuido dentro: no cabe en el parámetro."""
    import inspect

    firma = inspect.signature(extraer_preferencias)
    assert list(firma.parameters) == ["mensajes_usuario"]
    assert firma.parameters["mensajes_usuario"].annotation == "list[str]"


# ── Q2 · la identidad SÍ existe aguas arriba ───────────────────────────────────────


def test_el_id_del_mensaje_existe_y_sobrevive_a_la_persistencia():
    """LangGraph asigna un UUID al ingerir el mensaje y el serializador del checkpointer lo
    conserva. O sea: la identidad que `_user_texts` descarta está disponible."""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    crudo = HumanMessage(content="solo bajo $450")
    assert crudo.id is None, "chat.py lo construye sin id; lo asigna add_messages"

    con_id = HumanMessage(content="solo bajo $450", id="db8d3571-d484-4e33-ad51-08afbace028b")
    s = JsonPlusSerializer()
    vuelta = s.loads_typed(s.dumps_typed({"messages": [con_id]}))["messages"][0]
    assert vuelta.id == con_id.id
    assert vuelta.content == con_id.content


# ── Q3 · dónde se pierde la procedencia ────────────────────────────────────────────


def test_el_dict_no_conserva_de_que_mensaje_salio_cada_campo(cliente):
    c = cliente({"presupuesto_max": 450, "tipo_inmueble": "departamento"})
    salida = _extraer(["busco departamento", "solo bajo $450"])

    assert salida == {"presupuesto_max": 450.0, "tipo_inmueble": "departamento"}
    assert all(not isinstance(v, dict) for v in salida.values()), (
        "los valores son escalares: no hay dónde colgar procedencia"
    )
    # Y la petición que se envió tampoco separa los mensajes: van en UN solo bloque.
    enviado = c.llamadas[0]["messages"]
    assert len(enviado) == 1 and enviado[0]["role"] == "user"
    assert "busco departamento" in enviado[0]["content"]
    assert "solo bajo $450" in enviado[0]["content"]


def test_el_modelo_no_podria_atribuir_aunque_quisiera(cliente):
    """Los mensajes se concatenan con guiones en un único turno de usuario. Ni siquiera un
    extractor perfecto podría devolver "esto salió del mensaje 2": no recibe mensaje 2."""
    c = cliente({})
    _extraer(["uno", "dos", "tres"])
    contenido = c.llamadas[0]["messages"][0]["content"]
    assert contenido == "Mensajes del usuario:\n- uno\n- dos\n- tres"


# ── Q4/Q5 · reconstrucción por transcript y ventana de 12 ──────────────────────────


def test_el_extractor_reconstruye_desde_transcript_no_actualiza_estado(cliente):
    """No recibe el estado anterior: cada turno re-deriva todo desde los mensajes."""
    import inspect

    fuente = inspect.getsource(extraer_preferencias)
    assert "state" not in fuente and "preferencias_previas" not in fuente
    c = cliente({})
    _extraer(["a"])
    assert set(c.llamadas[0]) >= {"model", "system", "tools", "messages"}
    assert "preferencias" not in c.llamadas[0]


def test_la_ventana_de_12_deja_fuera_lo_declarado_al_principio(cliente):
    """CASO D. Con 13 mensajes humanos, el primero NO llega al modelo.

    Es la pérdida más silenciosa del pipeline: una necesidad declarada sigue siendo verdad
    para la persona, pero el sistema deja de verla porque se corrió de la ventana. Y como el
    extractor reconstruye desde cero cada turno, no queda ningún rastro de que existió.
    """
    c = cliente({})
    mensajes = ["necesito que acepten mascotas"] + [f"mensaje {i}" for i in range(2, 14)]
    assert len(mensajes) == 13

    _extraer(mensajes)
    contenido = c.llamadas[0]["messages"][0]["content"]

    assert "necesito que acepten mascotas" not in contenido
    assert "mensaje 2" in contenido and "mensaje 13" in contenido
    assert contenido.count("\n- ") == 12


def test_los_vacios_no_ocupan_lugar_en_la_ventana(cliente):
    """El recorte va sobre los textos YA filtrados, no sobre los mensajes crudos."""
    c = cliente({})
    _extraer(["primero"] + ["", "   "] + [f"m{i}" for i in range(12)])
    contenido = c.llamadas[0]["messages"][0]["content"]
    assert "primero" not in contenido
    assert contenido.count("\n- ") == 12


# ── Q6 · qué pasa cuando la extracción falla ───────────────────────────────────────


def test_un_fallo_de_extraccion_devuelve_vacio_no_lo_anterior(cliente):
    """CASO E. El extractor se traga el error y devuelve `{}`.

    No devuelve "no sé" ni conserva lo de antes: devuelve *ausencia de necesidades*, que es
    indistinguible de "la persona no ha pedido nada". El nodo escribe ese `{}` en el estado
    junto al turno actual, así que dentro de ese turno tampoco se reintenta.
    """
    c = cliente(error=TimeoutError("la API no respondió"))
    assert _extraer(["necesito 3 dormitorios y que acepten mascotas"]) == {}
    assert len(c.llamadas) == 1, "no hay reintento"


def test_el_turno_siguiente_recupera_porque_relee_el_transcript(cliente):
    """La otra cara: como se reconstruye desde el transcript, el fallo es TRANSITORIO…"""
    c = cliente(error=TimeoutError("caída"))
    assert _extraer(["quiero 3 dormitorios"]) == {}

    c2 = cliente({"dormitorios": 3})
    assert _extraer(["quiero 3 dormitorios"]) == {"dormitorios": 3}


def test_pero_deja_de_ser_transitorio_si_ademas_salio_de_la_ventana(cliente):
    """…salvo que la declaración ya no esté en los últimos 12. Ahí la pérdida es definitiva:
    ni el estado la guardaba ni el transcript la muestra ya."""
    c = cliente({})
    _extraer(["acepta mascotas"] + [f"m{i}" for i in range(12)])
    assert "acepta mascotas" not in c.llamadas[0]["messages"][0]["content"]


# ── Q7 · lo que el dict no puede representar ───────────────────────────────────────


def test_el_dict_es_plano_y_sin_ejes_semanticos(cliente):
    """Un valor escalar por dimensión. No hay dónde poner operador, origen, dureza,
    vigencia, evidencia ni corrección — no es que estén vacíos: no existen."""
    cliente({"presupuesto_max": 450, "dormitorios": 3, "caminable": True})
    salida = _extraer(["lo que sea"])
    assert salida == {"presupuesto_max": 450.0, "dormitorios": 3, "caminable": True}
    for v in salida.values():
        assert isinstance(v, (int, float, bool, str))


def test_el_schema_del_tool_no_tiene_operador_ni_origen():
    props = preferencias._TOOL["input_schema"]["properties"]
    assert set(props) == set(DIMENSIONES) | {"operacion"}
    for campo, esquema in props.items():
        assert set(esquema) <= {"type", "description", "enum"}, campo


def test_solo_se_registra_la_necesidad_afirmada():
    """`caminable: False` se descarta. "No me importa caminar" y "no lo dijo" colapsan en
    el mismo estado: ausencia."""
    assert _sanitizar({"caminable": False, "tranquilidad": True}) == {"tranquilidad": True}


# ── CASO C · "necesito al menos 3 dormitorios" ─────────────────────────────────────


def test_caso_C_al_menos_3_se_registra_como_3(cliente):
    """El prompt (regla 3b) ordena registrar el número nombrado y NO expandirlo a mínimo.
    Eso es normalización fiel del NÚMERO: el 3 es correcto."""
    cliente({"dormitorios": 3})
    assert _extraer(["Necesito al menos 3 dormitorios."]) == {"dormitorios": 3}


@pytest.mark.parametrize("tiene,s_esperado", [(3, 1.0), (4, 0.6), (5, 0.6)])
def test_caso_C_el_motor_lo_trata_como_EXACTO_y_penaliza_tener_de_mas(tiene, s_esperado):
    """LA PÉRDIDA SEMÁNTICA, medida. El número se conservó; el OPERADOR no.

    La persona dijo "al menos 3" y un inmueble de 4 la satisface por completo — pero el
    motor lo puntúa 0,6 y la razón dice "Tiene 4 dormitorios, pediste 3", como si tener de
    más fuera un defecto. No es un error del motor: `calcular_encaje` hace exactamente lo
    que el dict le permite expresar, porque `{dormitorios: 3}` no distingue `EQ` de `GTE`.
    """
    e = calcular_encaje({"dormitorios": 3}, {"num_dormitorios": tiene})
    razon = next(r for r in e["razones"] if r["dimension"] == "dormitorios")
    assert razon["s"] == s_esperado


def test_caso_C_el_contrato_F1_ya_sabe_representarlo():
    """`DecisionCriterionV0` con `operator=GTE` expresa sin pérdida lo que el dict no puede.
    No hace falta contrato nuevo: hace falta una costura que lo alimente."""
    criterio = DecisionCriterionV0(
        criterion_id="c-bedrooms",
        dimension="bedrooms",
        operator=Operator.GTE,
        value=3,
        origin=CriterionOrigin.STATED,
    )
    assert criterio.operator is Operator.GTE and criterio.value == 3
    assert criterio.evidence == (), "sin evidencia resoluble todavía — es F3.0b en adelante"


# ── CASO A · "solo lo que esté bajo $450" ──────────────────────────────────────────


def test_caso_A_el_dict_no_distingue_solo_bajo_de_hasta(cliente):
    """Ambas frases producen el MISMO dict. La dureza que la persona expresó con "solo"
    no tiene dónde vivir."""
    cliente({"presupuesto_max": 450})
    duro = _extraer(["Ahora muéstrame solo lo que esté bajo $450."])
    blando = _extraer(["Busco algo de hasta $450, pero puedo estirarme."])
    assert duro == blando == {"presupuesto_max": 450.0}


@pytest.mark.parametrize("precio,visible", [(380, True), (470, True), (495, True), (496, False)])
def test_caso_A_con_tope_450_un_inmueble_de_470_sigue_en_pantalla(precio, visible):
    """EL COMPORTAMIENTO REAL, demostrado. El corte usa un margen del 10 %:
    límite = 450 × 1,10 = 495. Un $470 no se marca y no se recorta.

    Es exactamente el caso que distingue un tope DURO de un presupuesto flexible, y hoy el
    sistema resuelve a favor del segundo — en silencio, por una constante, sin que nadie
    haya declarado esa interpretación. NO se corrige aquí: se deja medido.
    """
    cards = [{"id": str(precio), "precio": precio, "encaje": 100}]
    sobre = decidir_sobre_presupuesto(cards, {"presupuesto_max": 450})
    assert (str(precio) not in sobre) is visible
    if visible:
        assert [c["id"] for c in _recortar_grid(cards, sobre)] == [str(precio)]


# ── CASO B · "¿cuál de estos es el más caminable?" ─────────────────────────────────


def test_caso_B_una_pregunta_comparativa_cabe_en_el_schema_como_preferencia(cliente):
    """El schema admite `caminable: True`. Lo que NO existe es una forma de decir que fue
    el objetivo de ESE turno y no un criterio de compra.

    Este test NO afirma que la persona declarara una preferencia persistente: afirma que el
    esquema no puede distinguir las dos cosas, así que cualquiera que sea la verdad, el
    sistema la representa igual.
    """
    cliente({"caminable": True})
    assert _extraer(["¿Cuál de estos es el más caminable?"]) == {"caminable": True}


def test_caso_B_no_hay_eje_situacional_ni_de_vigencia():
    assert "situational" not in str(preferencias._TOOL).lower()
    assert not any(k in DIMENSIONES for k in ("vigencia", "persistente", "turno"))


# ── Q8 · Fair Housing: las tres barreras, intactas ─────────────────────────────────


def test_FH_1_el_schema_del_tool_es_una_whitelist_cerrada():
    props = set(preferencias._TOOL["input_schema"]["properties"])
    assert props == set(DIMENSIONES) | {"operacion"}


def test_FH_2_el_prompt_prohibe_inferir_desde_quien_es_la_persona():
    s = preferencias._SYSTEM.lower()
    assert "nunca infieras" in s
    for rasgo in ("hijos", "edad", "nacionalidad", "origen", "religión", "género", "discapacidad"):
        assert rasgo in s


@pytest.mark.parametrize("bruto", [
    {"familia": True, "hijos": 2, "tranquilidad": True},
    {"raza": "x", "edad": 30, "presupuesto_max": 700},
    {"nacionalidad": "ec", "religion": "y", "caminable": True},
])
def test_FH_3_el_sanitizador_descarta_todo_rasgo_de_persona(bruto):
    limpio = _sanitizar(bruto)
    assert set(limpio) <= set(DIMENSIONES) | {"operacion"}
    for ajeno in ("familia", "hijos", "raza", "edad", "nacionalidad", "religion"):
        assert ajeno not in limpio


def test_FH_la_operacion_es_enum_cerrado():
    assert _sanitizar({"operacion": "arriendo"}) == {"operacion": "arriendo"}
    assert _sanitizar({"operacion": "permuta"}) == {}
    assert _sanitizar({"operacion": "ARRIENDO "}) == {"operacion": "arriendo"}
