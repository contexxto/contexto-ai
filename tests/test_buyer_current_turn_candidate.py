"""F3-CURRENT-TURN-CANDIDATE-R0B · el candidato del turno actual, en sombra.

QUÉ CONGELA, y qué NO.

    congela    que el estado que ESTE turno produciría se calcula con la MISMA política de
               E3.2 —una interpretación, un lote, una reducción—, desde el `BuyerContext`
               persistido y el `HumanMessage` canónico de R0A; que la corrección dicha en el
               turno GANA sobre el valor viejo; y que nada de eso se persiste ni decide
    NO congela que el candidato y lo que acabe persistido converjan. Mientras el candidato y
               el updater interpreten por separado —y hoy lo hacen, `T11` lo mide— afirmar
               convergencia sería afirmar que dos llamadas al LLM coinciden

El arnés es el de `test_buyer_actualizador.py`: doble del store y proponente inyectable. Las
pruebas son deterministas a propósito — esto no es un eval del modelo.
"""

from __future__ import annotations

import ast
import asyncio
import datetime as dt
import pathlib
from decimal import Decimal

import pytest
from langchain_core.messages import HumanMessage

from app.buyer import actualizador as act
from app.buyer import candidato as cand
from app.buyer.actualizador import CandidatoTurno, actualizar, computar_candidato
from app.buyer.boundary import (
    BuyerCurrencyV0, ClearPetsRequired, SetBudgetMax, SetPetsRequired,
)
from app.buyer.candidato import (
    DesenlaceCandidato, ObservacionCandidato, observar_candidato_del_turno,
)
from app.buyer.interprete import PropuestaV0
from app.buyer.store import BuyerContextV0, RevisionPersistida, _canonico
from app.contracts.common_v0 import Money

RAIZ = pathlib.Path(__file__).resolve().parent.parent
APP = RAIZ / "app"
CHAT = APP / "routers" / "chat.py"
MODULO = APP / "buyer" / "candidato.py"

T0 = dt.datetime(2026, 9, 11, 12, 0, tzinfo=dt.timezone.utc)
USD = BuyerCurrencyV0.USD
A = "11111111-1111-4111-8111-111111111111"
MSG = "msg-22222222-2222-4222-8222-222222222222"


class _Principal:
    def __init__(self, user_id=A):
        self.user_id = user_id


def _Humano(content, id):  # noqa: N802, A002 — imita la construcción real del turno
    """El `HumanMessage` REAL, no un doble.

    `mensaje._es_util` exige `isinstance(m, HumanMessage)` a propósito —«mismo filtro que el
    legacy `_user_texts`, para que los dos carriles no discrepen sobre qué cuenta como
    mensaje del usuario»—, así que un objeto pato-tipado se descartaría en silencio y estas
    pruebas medirían el descarte en vez de la costura.
    """
    return HumanMessage(content=content, id=id)


def _p(disposicion, **kw):
    return PropuestaV0(disposicion=disposicion, motivo="propuesto", **kw)


def _proponente(*propuestas):
    async def proponer(_texto):
        return propuestas
    return proponer


class _StoreDoble:
    """Mismo contrato que el doble de `test_buyer_actualizador.py`. Cuenta las escrituras."""

    def __init__(self):
        self.revisiones: dict[str, list] = {}
        self.escrituras = 0

    async def cargar_ultima(self, buyer_id, *, db=None):
        historial = self.revisiones.get(buyer_id) or []
        return historial[-1] if historial else None

    async def anexar_revision(self, buyer_id, source_message_id, contexto,
                              expected_revision, *, db=None):
        self.escrituras += 1
        historial = self.revisiones.setdefault(buyer_id, [])
        actual = historial[-1].context_revision if historial else None
        nueva = 0 if actual is None else actual + 1
        guardado = contexto.model_copy(update={"context_revision": nueva, "updated_at": T0})
        historial.append(guardado)
        return RevisionPersistida(guardado, nueva, creada=True)

    def sembrar(self, buyer_id, contexto, revision):
        self.revisiones.setdefault(buyer_id, []).append(
            contexto.model_copy(update={"context_revision": revision, "updated_at": T0}))


@pytest.fixture
def store(monkeypatch):
    doble = _StoreDoble()
    monkeypatch.setattr(act, "cargar_ultima", doble.cargar_ultima)
    monkeypatch.setattr(act, "anexar_revision", doble.anexar_revision)
    return doble


@pytest.fixture
def canary(monkeypatch):
    def _configurar(flag=True, allowlist=A):
        monkeypatch.setattr(cand.settings, "buyer_current_turn_candidate_shadow", flag,
                            raising=False)
        monkeypatch.setattr(cand.settings, "buyer_shadow_allowlist", allowlist, raising=False)
    _configurar()
    return _configurar


@pytest.fixture
def contador(monkeypatch):
    """Cuenta las interpretaciones. Es lo que hace medible la doble llamada de §9."""
    veces = {"n": 0}
    original = act.interpretar_mensaje

    async def contado(mensaje, proponente=None):
        veces["n"] += 1
        return await original(mensaje, proponente)

    monkeypatch.setattr(act, "interpretar_mensaje", contado)
    return veces


def _observar(principal, texto="me equivoqué", propuestas=(), **kw):
    return asyncio.run(observar_candidato_del_turno(
        principal, [_Humano(texto, MSG)], retrieved_at=T0,
        proponente=_proponente(*propuestas), **kw))


# `SetPetsRequired` NO lleva campo: «la operación es la afirmación» (boundary.py). Con un
# `value: bool` podría construirse con `False`, que no significa «ya no lo necesito» —eso es
# `ClearPetsRequired`— sino un requisito distinto que V0 no modela.
_PETS_SI = _p("durable", mutacion=SetPetsRequired())
_PETS_NO = _p("durable", mutacion=ClearPetsRequired())
_BUD_1200 = _p("durable", mutacion=SetBudgetMax(amount=Decimal(1200), currency=USD))


def _ctx(pets=None, budget=None) -> BuyerContextV0:
    datos = {"buyer_id": A, "updated_at": T0}
    if pets is not None:
        datos["property_requirements"] = {"pets_allowed_required": pets}
    if budget is not None:
        datos["financial"] = {"budget_max": Money(amount=Decimal(budget), currency="USD")}
    return BuyerContextV0(**datos)


# ══ T1 · FLAG OFF ══════════════════════════════════════════════════════════════════


def test_T1_flag_apagado_no_computa_nada(canary, store, contador):
    canary(flag=False)
    obs = _observar(_Principal(), propuestas=(_BUD_1200,))
    assert obs.desenlace is DesenlaceCandidato.DESACTIVADA
    assert obs.candidato is None and contador["n"] == 0 and store.escrituras == 0


# ══ T2 · ALLOWLIST VACÍA ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize("lista", ["", "   ", ",", "*", "all"])
def test_T2_fuera_de_cohorte_no_computa(canary, store, contador, lista):
    canary(flag=True, allowlist=lista)
    obs = _observar(_Principal(), propuestas=(_BUD_1200,))
    assert obs.desenlace is DesenlaceCandidato.FUERA_DE_COHORTE
    assert contador["n"] == 0


# ══ T3 · USUARIO AUTENTICADO · T4 · ID CANÓNICO · T9 · REVISIÓN BASE ═══════════════


def test_T3_con_persistido_y_mensaje_canonico_se_calcula_el_candidato(canary, store):
    store.sembrar(A, _ctx(budget=900), 4)
    obs = _observar(_Principal(), propuestas=(_BUD_1200,))
    assert obs.desenlace is DesenlaceCandidato.CALCULADO and obs.hubo_computo
    assert isinstance(obs.candidato, CandidatoTurno)


def test_T4_el_candidato_usa_el_id_CANONICO_del_mensaje(canary, store):
    obs = _observar(_Principal(), propuestas=(_BUD_1200,))
    assert obs.candidato.source_message_id == MSG


def test_T9_el_artefacto_registra_la_revision_BASE(canary, store):
    """`base_context_revision` es DESDE dónde se redujo. No se promete que sea la anterior a
    la que se persista: si otra conversación escribe en medio, el store rebasa."""
    store.sembrar(A, _ctx(budget=900), 7)
    obs = _observar(_Principal(), propuestas=(_BUD_1200,))
    assert obs.candidato.base_context_revision == 7
    assert obs.candidato.retrieved_at == T0
    assert obs.candidato.buyer_id == A


def test_T9b_sin_estado_previo_la_base_es_None(canary, store):
    obs = _observar(_Principal(), propuestas=(_BUD_1200,))
    assert obs.candidato.base_context_revision is None


# ══ T5 · EL MISMO REDUCTOR ═════════════════════════════════════════════════════════


def test_T5_el_candidato_NO_reimplementa_la_politica(canary):
    """`candidato.py` no importa el intérprete, ni el reductor, ni la frontera: sólo la fase
    COMPUTE común. Si los importara, habría dos caminos que pueden divergir."""
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    modulos = {n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)}
    for prohibido in ("app.buyer.interprete", "app.buyer.reductor", "app.buyer.extractor",
                      "app.buyer.boundary", "app.buyer.store"):
        assert prohibido not in modulos, f"el candidato reimplementa vía {prohibido}"
    assert "app.buyer.actualizador" in modulos


def test_T5b_la_fase_COMPUTE_usa_el_reductor_real():
    arbol = ast.parse((APP / "buyer" / "actualizador.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "computar_candidato")
    llamadas = {n.func.id for n in ast.walk(fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert {"interpretar_mensaje", "cargar_ultima", "reducir"} <= llamadas


# ══ T6 · CORRECCIÓN DE MASCOTAS EN EL MISMO TURNO ══════════════════════════════════


def test_T6_la_correccion_del_turno_GANA_sobre_el_valor_persistido(canary, store):
    """Persistido N-1: acepta mascotas. Turno N: «me equivoqué, no lo necesito».

    El candidato refleja la corrección. Si ganara el valor viejo, conceder autoridad a la
    memoria persistida sería una REGRESIÓN — que es exactamente lo que bloqueaba LEVEL 2.
    """
    store.sembrar(A, _ctx(pets=True), 3)
    obs = _observar(_Principal(), texto="ya no necesito que acepten mascotas",
                    propuestas=(_PETS_NO,))
    assert obs.candidato.contexto.property_requirements.pets_allowed_required is None


def test_T6b_sin_la_correccion_el_valor_persistido_SOBREVIVE(canary, store):
    """LA MITAD NEGATIVA: si el candidato ignorase la base, T6 sería cierto y vacío."""
    store.sembrar(A, _ctx(pets=True), 3)
    obs = _observar(_Principal(), texto="hola", propuestas=(_BUD_1200,))
    assert obs.candidato.contexto.property_requirements.pets_allowed_required is True


# ══ T7 · CORRECCIÓN DE PRESUPUESTO ═════════════════════════════════════════════════


def test_T7_900_persistido_y_1200_dicho_ahora_dan_1200(canary, store):
    """El caso que abrió toda esta línea de trabajo.

    EL TEXTO LLEVA `USD` A PROPÓSITO. La primera versión de esta prueba decía sólo «1200» y
    daba 900: con `BUYER_MARKET_CURRENCY` vacío —el valor por defecto— la guarda de G16 no
    puede acreditar la denominación, la afirmación cae a `AMBIGUOUS`, y R5 dice que una
    ambigüedad **no pisa** un valor que ya existe; sólo abre una pregunta. No era un fallo
    del candidato: era G16 funcionando.

    Y deja una precondición operativa a la vista: en un despliegue sin
    `BUYER_MARKET_CURRENCY` declarado, «mi máximo es 1200 dólares» NO corrige el presupuesto.
    Es exactamente la precondición de activación que el acta de E3.2 registró en su §6.1.
    """
    store.sembrar(A, _ctx(budget=900), 2)
    obs = _observar(_Principal(), texto="en realidad mi máximo es 1200 USD",
                    propuestas=(_BUD_1200,))
    assert obs.candidato.contexto.financial.budget_max.amount == Decimal(1200)


def test_T7c_sin_denominacion_acreditable_la_ambiguedad_NO_pisa_el_valor(canary, store):
    """LA MITAD NEGATIVA, y una propiedad real del sistema, no un accidente del arnés.

    Sin `USD` en la cláusula y sin mercado declarado, el presupuesto persistido SOBREVIVE y
    se abre una pregunta. Que el candidato respete esto demuestra que usa la política de
    E3.2 entera —G16 incluida— y no una versión suya simplificada.
    """
    store.sembrar(A, _ctx(budget=900), 2)
    obs = _observar(_Principal(), texto="en realidad mi máximo es 1200",
                    propuestas=(_BUD_1200,))
    assert obs.candidato.contexto.financial.budget_max.amount == Decimal(900)
    assert [q.about_field for q in obs.candidato.contexto.unresolved_questions] == \
           ["financial.budget_max"]


def test_T7b_y_no_concede_autoridad(canary, store):
    """El candidato existe y no decide: `chat.py` lo descarta (T13)."""
    store.sembrar(A, _ctx(budget=900), 2)
    obs = _observar(_Principal(), propuestas=(_BUD_1200,))
    assert obs.candidato is not None
    assert store.revisiones[A][-1].financial.budget_max.amount == Decimal(900)


# ══ T8 · CERO PERSISTENCIA ═════════════════════════════════════════════════════════


def test_T8_el_candidato_no_escribe_ni_una_revision(canary, store):
    for _ in range(5):
        _observar(_Principal(), propuestas=(_BUD_1200,))
    assert store.escrituras == 0 and store.revisiones.get(A) is None


def test_T8b_el_contador_de_escrituras_SABE_contar(canary, store):
    """LA MITAD NEGATIVA: el updater real SÍ escribe, con la misma fase COMPUTE."""
    asyncio.run(actualizar(A, _MsgId(), retrieved_at=T0,
                           proponente=_proponente(_BUD_1200)))
    assert store.escrituras == 1


class _MsgId:
    message_id = MSG
    text = "en realidad mi máximo es 1200"


# ══ T10 · UNA INTERPRETACIÓN POR CANDIDATO ═════════════════════════════════════════


def test_T10_un_candidato_es_UNA_interpretacion(canary, store, contador):
    _observar(_Principal(), propuestas=(_BUD_1200,))
    assert contador["n"] == 1


def test_T10b_un_candidato_es_UN_lote_y_UNA_reduccion(canary, store):
    obs = _observar(_Principal(), propuestas=(_BUD_1200,))
    assert obs.candidato.lote is not None
    assert isinstance(obs.candidato.contexto, BuyerContextV0)


# ══ T11 · CONTABILIDAD DE LA DOBLE LLAMADA ═════════════════════════════════════════


def test_T11_con_AMBOS_canarios_el_turno_se_interpreta_DOS_veces(canary, store, contador):
    """CONGELA UNA DEUDA, no una garantía.

    Con el candidato y el updater encendidos a la vez, el mismo turno pasa dos veces por el
    intérprete: una antes de decidir y otra después, en la sombra. R0B no lo arregla —unir
    candidato y persistencia es R0C— y mientras existan DOS interpretaciones independientes
    **no se puede afirmar que el candidato y lo persistido converjan**: `interpretar_mensaje`
    usa el LLM y dos llamadas pueden no coincidir.
    """
    _observar(_Principal(), propuestas=(_BUD_1200,))
    asyncio.run(actualizar(A, _MsgId(), retrieved_at=T0,
                           proponente=_proponente(_BUD_1200)))
    assert contador["n"] == 2, (
        "si esto bajara a 1 sin que R0C lo hubiera unido, la cuenta estaría mintiendo")


def test_T11b_el_candidato_solo_interpreta_una_vez(canary, store, contador):
    _observar(_Principal(), propuestas=(_BUD_1200,))
    assert contador["n"] == 1


# ══ T12 / T13 · SIN CONSUMIDOR DE DECISIÓN ═════════════════════════════════════════


def test_T12_el_candidato_no_llega_a_la_decision():
    """Ni al estado, ni al config, ni al prompt, ni al motor."""
    fuente = CHAT.read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    llamada = next(n for n in ast.walk(arbol)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id == "observar_candidato_del_turno")
    assert llamada is not None
    # el módulo del candidato no conoce la superficie de decisión
    mod = ast.parse(MODULO.read_text(encoding="utf-8"))
    modulos = {n.module or "" for n in ast.walk(mod) if isinstance(n, ast.ImportFrom)}
    for prohibido in ("app.decision", "app.encaje", "app.orden", "app.agent",
                      "app.place", "app.routers"):
        assert not any(m.startswith(prohibido) for m in modulos), f"toca {prohibido}"


def test_T12b_AgentState_no_gana_claves_del_comprador():
    estado = (APP / "agent" / "state.py").read_text(encoding="utf-8")
    for prohibido in ("buyer", "candidato", "principal", "user_id"):
        assert prohibido not in estado


def test_T12c_langgraph_config_no_transporta_el_candidato():
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.FunctionDef) and n.name == "_langgraph_config")
    volcado = ast.dump(fn)
    for prohibido in ("buyer", "candidato", "principal", "user_id"):
        assert prohibido not in volcado


def test_T13_chat_DESCARTA_el_resultado():
    """La llamada es una sentencia de expresión, no una asignación: nadie se queda con él."""
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    for n in ast.walk(arbol):
        if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            assert "observar_candidato_del_turno" not in ast.dump(n), (
                "el candidato se está guardando en una variable de chat.py")


def test_T13b_hay_DOS_llamadores_de_UNA_sola_funcion():
    """Stream y no-stream, porque el mensaje canónico nace tras el branch. Lo que no puede
    haber es dos implementaciones."""
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    llamadas = [n for n in ast.walk(arbol)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "observar_candidato_del_turno"]
    assert len(llamadas) == 2


# ══ T14 · ANÓNIMO ══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("anon", [None, "", "   "])
def test_T14_el_anonimo_no_computa_ni_se_inventa(canary, store, contador, anon):
    principal = None if anon is None else _Principal(anon)
    obs = _observar(principal, propuestas=(_BUD_1200,))
    assert obs.desenlace is DesenlaceCandidato.SIN_PRINCIPAL
    assert contador["n"] == 0 and obs.candidato is None


# ══ T15 · FALLA ABIERTA ════════════════════════════════════════════════════════════


@pytest.mark.parametrize("boom", [RuntimeError, ConnectionError, ValueError])
def test_T15_un_fallo_del_computo_no_rompe_el_turno(canary, monkeypatch, boom):
    async def _revienta(*a, **k):
        raise boom("simulado")

    monkeypatch.setattr(cand, "computar_candidato", _revienta)
    obs = _observar(_Principal(), propuestas=(_BUD_1200,))
    assert obs.desenlace is DesenlaceCandidato.FALLO and obs.candidato is None


def test_T15b_un_mensaje_sin_identidad_no_rompe_el_turno(canary, store):
    """R0A garantiza el id; si aun así faltara, la sonda no puede tumbar el chat."""
    obs = asyncio.run(observar_candidato_del_turno(
        _Principal(), [_Humano("sin id", None)], retrieved_at=T0,
        proponente=_proponente(_BUD_1200)))
    assert obs.desenlace is DesenlaceCandidato.FALLO


def test_T15c_sin_afirmaciones_se_distingue_de_un_fallo(canary, store):
    obs = _observar(_Principal(), propuestas=())
    assert obs.desenlace is DesenlaceCandidato.SIN_AFIRMACIONES


# ══ T16 · SIN RASTRO SENSIBLE ══════════════════════════════════════════════════════


def test_T16_el_log_no_lleva_nada_del_comprador(canary, store, caplog):
    store.sembrar(A, _ctx(budget=900, pets=True), 2)
    with caplog.at_level("INFO"):
        _observar(_Principal(), propuestas=(_BUD_1200,))
    texto = " ".join(r.getMessage() for r in caplog.records)
    for secreto in (A, "1200", "900", "mascota", "pets", "budget", "presupuesto"):
        assert secreto not in texto, f"el log filtró `{secreto}`"


def test_T16b_el_modulo_no_registra_el_contexto():
    fuente = MODULO.read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr in ("log", "info", "warning", "error", "exception"):
            volcado = ast.dump(n)
            for prohibido in ("contexto", "candidato.contexto", "user_id", "email"):
                assert prohibido not in volcado, f"el log menciona {prohibido}"


# ══ T17 · MUTACIONES ═══════════════════════════════════════════════════════════════


def test_T17a_romper_el_id_canonico_se_detecta(canary, store):
    obs = _observar(_Principal(), propuestas=(_BUD_1200,))
    assert obs.candidato.source_message_id == MSG
    assert obs.candidato.source_message_id != "otro-id"


def test_T17b_romper_el_reuso_del_reductor_se_detecta():
    """Si `candidato.py` importara el reductor, T5 lo vería."""
    fingido = ast.parse("from app.buyer.reductor import reducir\n")
    modulos = {n.module for n in ast.walk(fingido) if isinstance(n, ast.ImportFrom)}
    assert "app.buyer.reductor" in modulos


def test_T17c_romper_la_no_persistencia_se_detecta(canary, store):
    asyncio.run(actualizar(A, _MsgId(), retrieved_at=T0,
                           proponente=_proponente(_BUD_1200)))
    assert store.escrituras == 1, "el contador no distinguiría escribir de no escribir"


def test_T17d_romper_la_correccion_del_turno_se_detecta(canary, store):
    """Si el candidato devolviera la base sin reducir, T6 y T7 se pondrían rojas."""
    store.sembrar(A, _ctx(budget=900), 2)
    base = store.revisiones[A][-1]
    obs = _observar(_Principal(), propuestas=(_BUD_1200,))
    assert _canonico(obs.candidato.contexto) != _canonico(base)


def test_T17e_romper_el_aislamiento_candidato_decision_se_detecta():
    """Si `chat.py` asignara el resultado, T13 lo vería."""
    roto = ast.parse("async def f(u, m):\n"
                     "    x = await observar_candidato_del_turno(u, m)\n")
    assert any(isinstance(n, ast.Assign) and "observar_candidato_del_turno" in ast.dump(n)
               for n in ast.walk(roto))


# ══ PARIDAD ════════════════════════════════════════════════════════════════════════


def test_paridad_el_estado_del_turno_no_cambia():
    from app.routers.chat import _estado_inicial_del_turno
    estado = _estado_inicial_del_turno("hola")
    assert set(estado) == {"messages", "spatial_context", "sql_results", "cards",
                           "descartadas", "encaje_contexto"}


def test_paridad_AGENT_TOOLS_no_cambia():
    arbol = ast.parse((APP / "agent" / "tools.py").read_text(encoding="utf-8"))
    for n in ast.walk(arbol):
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "AGENT_TOOLS" for t in n.targets):
            assert len(n.value.elts) == 9
            return
    raise AssertionError("no se encontró AGENT_TOOLS")


def test_la_observacion_es_un_tipo_cerrado():
    obs = ObservacionCandidato(DesenlaceCandidato.DESACTIVADA)
    assert set(ObservacionCandidato.__dataclass_fields__) == {
        "desenlace", "candidato", "duracion_ms"}
    assert obs.hubo_computo is False
