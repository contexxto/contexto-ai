"""B3 · la puerta suave se ofrece UNA VEZ por hilo, y la marca sobrevive al turno siguiente.

EL DEFECTO QUE CIERRA. `_marcar_puerta_ofrecida` escribía `puerta_ofrecida` con
`aupdate_state` sobre una clave que NO estaba declarada en `AgentState`. LangGraph 0.2.60
descarta EN SILENCIO las claves que no encuentra en el esquema: no levanta, así que el
`try/except` del llamador nunca veía nada y su `log.warning` no se emitió jamás —buscarlo en
los logs no detectaba el defecto—. Resultado: `ya_ofrecida` era siempre falso y la oferta de
correo se repetía en CADA turno que cumpliera el callejón honesto, que es exactamente el acoso
que la puerta existe para no tener (`app/puerta.py:33-38`, `app/routers/chat.py:356-359`).

POR QUÉ ESTE FICHERO TIENE SU PROPIO ARNÉS. El fixture de
`tests/test_state_lineage_semilla_del_turno.py` anula `_marcar_puerta_ofrecida` con
monkeypatch, y los dos tests de `tests/test_puerta.py` que tocan la regla «una vez» le pasan
`ya_ofrecida` como argumento. Ninguno de los tres puede ver este defecto: un test que anula la
escritura no prueba que la escritura persista. Aquí el endpoint es real, el grafo es real y el
checkpointer es real (en memoria), y `_marcar_puerta_ofrecida` corre de verdad.

LO QUE ESTE FICHERO NO PROMETE:
  · no prueba la regla 4 («al que ya pidió corredor no se le ofrece»): esa depende de
    `handoff_pedido`, que es otro defecto (se lee y nadie lo escribe) y va aparte;
  · no prueba el camino de streaming SSE salvo en el último test, y sólo en lo que a esta
    marca respecta;
  · no dice nada sobre si la puerta DEBE abrirse en un caso concreto — eso es
    `tests/test_puerta.py`, que prueba `evaluar_puerta` como función pura.
"""
import asyncio

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

import main
from app.agent import graph as G
from app.agent import tools as TOOLS
from app.decision import assembler
from app.routers import chat as chat_mod
from app.sesion_autoridad import Autoridad

ANCLA = {"latitude": -0.20934, "longitude": -78.484919}
SESION = "sesion-puerta-persistencia"


def _fila(aid):
    return {"id": aid, "direccion_estandarizada": f"Calle {aid}", "caminabilidad": 100,
            "walk_score_fuente": None, "score_ruido_predictivo": 1,
            "volumen_trafico_historico": 1, "densidad_poblacional_pico": 1,
            "porcentaje_cobertura_vegetal": 40, "conectividad": None,
            "servicios_cercanos": None, "operacion": "ARRIENDO", "precio": 630,
            "distancia_metros": 572.0, "tipo_activo": "Departamento"}


class _LLM:
    def __init__(self, **_kw):
        self.guion = []

    def bind_tools(self, _t):
        return self

    async def ainvoke(self, _m):
        return self.guion.pop(0) if self.guion else AIMessage(content="respuesta final")


@pytest.fixture(autouse=True)
def _sin_rate_limit(monkeypatch):
    """El limitador cuenta por IP y este fichero llama al mismo endpoint muchas veces desde la
    misma — dos turnos por test, en dos caminos.

    Sin esto la cuota se agota y el 429 se disfraza de dos cosas distintas: aquí, de «la puerta
    no se ofreció»; y en los ficheros que corren DESPUÉS por orden alfabético, de fallos suyos.
    Es el mismo fixture y el mismo motivo que `tests/test_autoridad_endpoints.py`.
    """
    from app.limiter import limiter
    monkeypatch.setattr(limiter, "enabled", False)


@pytest.fixture
def mundo(monkeypatch):
    """Endpoint REAL + grafo REAL + checkpointer REAL (en memoria), y la marca SIN anular.

    `TestClient` SIN `with`, igual que el resto de la casa: como gestor de contexto ejecuta el
    lifespan, que monta el checkpointer contra la Supabase de PRODUCCIÓN.

    EL ESCENARIO es el «callejón honesto» del §6, construido para ser determinista: la búsqueda
    SÍ encuentra filas —así el nodo `encaje` corre y escribe `preferencias`, que es la condición
    sin la cual no hay puerta— y el panel se queda SIN tarjetas, así que no hay nada que de
    verdad le sirva a la persona. Las dos cosas juntas son el único momento en que la puerta se
    abre sin que nadie la pida.
    """
    async def _rows(_q, _p):
        return [_fila("ee9ff315")]

    async def _sin_tarjetas(_ids):
        return [], {}

    async def _prefs(_t):
        # `dormitorios` está en la whitelist del motor y tiene etiqueta legible, así que
        # produce criterio declarado. Con `{"operacion": ...}` NO habría puerta: esa clave no
        # puntúa y `_criterio_legible` sólo enuncia lo que puntúa.
        return {"dormitorios": 2}

    creados = []

    class _Fab(_LLM):
        def __init__(self, **kw):
            super().__init__(**kw)
            creados.append(self)

    monkeypatch.setattr(TOOLS, "_fetch_rows", _rows)
    monkeypatch.setattr(assembler, "_fetch_cards_rows", _sin_tarjetas)
    monkeypatch.setattr(G, "extraer_preferencias", _prefs)
    monkeypatch.setattr(assembler, "extraer_preferencias", _prefs)
    monkeypatch.setattr(G, "ChatAnthropic", _Fab)

    compilado = G._build_graph().compile(checkpointer=MemorySaver())
    monkeypatch.setattr(G, "compiled_graph", compilado)

    async def _autoridad(*_a, **_k):
        return Autoridad.OWNER

    async def _nada(*_a, **_k):
        return None

    monkeypatch.setattr(chat_mod, "_exigir_autoridad", _autoridad)
    monkeypatch.setattr(chat_mod, "registrar_intencion", _nada)
    monkeypatch.setattr(chat_mod, "actualizar_en_sombra", _nada)
    # `_marcar_puerta_ofrecida` NO se anula: es justamente lo que se prueba.
    monkeypatch.setattr(chat_mod, "_auditar_prosa", lambda *_a, **_k: None)

    from app.auth import get_optional_user
    main.app.dependency_overrides[get_optional_user] = lambda: None

    cliente = TestClient(main.app)
    try:
        yield cliente, creados[0], compilado
    finally:
        main.app.dependency_overrides.clear()


def _guionar(llm):
    llm.guion = [
        AIMessage(content="", tool_calls=[{
            "name": "tool_search_nearby_assets",
            "args": {"latitude": ANCLA["latitude"], "longitude": ANCLA["longitude"],
                     "radius_meters": 1200}, "id": "t1"}]),
        AIMessage(content="respuesta final"),
    ]


def _post(cliente, llm, texto, stream=False, sesion=SESION):
    _guionar(llm)
    return cliente.post(f"/api/v1/chat/?stream={'true' if stream else 'false'}",
                        json={"message": texto, "session_id": sesion})


def _estado(compilado, sesion=SESION):
    return asyncio.run(compilado.aget_state(
        {"configurable": {"thread_id": sesion}})).values


# ── 1 · el escenario abre la puerta ───────────────────────────────────────────

def test_el_callejon_honesto_ofrece_la_puerta(mundo):
    """Control del arnés: sin esto, los tests de abajo pasarían por no ofrecerse nunca."""
    cliente, llm, _ = mundo

    r = _post(cliente, llm, "Busco algo de 2 dormitorios")

    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo.get("puerta"), "el escenario no abrió la puerta: el arnés no prueba nada"
    assert cuerpo["puerta"]["motivo"] == "callejon_honesto"


# ── 2 · la marca PERSISTE · es el test que falla sin la declaración ───────────

def test_la_marca_queda_escrita_en_el_estado_declarado(mundo):
    """ROJO ANTES del arreglo: `puerta_ofrecida` no estaba en `AgentState`, así que
    `aupdate_state` la descartaba en silencio y la clave no aparecía en el checkpoint."""
    cliente, llm, compilado = mundo

    _post(cliente, llm, "Busco algo de 2 dormitorios")

    valores = _estado(compilado)
    assert valores.get("puerta_ofrecida") is True, (
        "la marca no sobrevivió al checkpoint: la clave sigue sin estar declarada en AgentState"
    )


def test_la_marca_sobrevive_al_turno_siguiente(mundo):
    """Un canal `LastValue` declarado se arrastra al turno siguiente; uno no declarado no
    existe. Esto separa «se escribió» de «sigue ahí cuando hace falta leerlo»."""
    cliente, llm, compilado = mundo

    _post(cliente, llm, "Busco algo de 2 dormitorios")
    _post(cliente, llm, "¿Y si amplío la zona?")

    assert _estado(compilado).get("puerta_ofrecida") is True


# ── 3 · la consecuencia observable · la regla «una vez» ──────────────────────

def test_la_puerta_no_se_repite_en_el_turno_siguiente(mundo):
    """ROJO ANTES: la oferta se repetía en cada turno elegible. Es la regla 3 del §6 y el
    control anti-presión principal del producto."""
    cliente, llm, _ = mundo

    primero = _post(cliente, llm, "Busco algo de 2 dormitorios")
    segundo = _post(cliente, llm, "¿Y si amplío la zona?")

    assert primero.json().get("puerta"), "el primer turno debía ofrecerla"
    assert segundo.json().get("puerta") is None, (
        "la puerta se ofreció DOS veces en el mismo hilo: la regla «una vez» no se aplica"
    )


def test_si_ya_pidio_corredor_no_se_ofrece_la_puerta(mundo, monkeypatch):
    """B1 · la regla 4: «ya hay una puerta más fuerte abierta; insistir con otra es acoso».

    ROJO ANTES: se leía `estado.get("handoff_pedido")`, una clave que NADIE escribía en todo el
    repositorio, así que `pidio_corredor` era siempre False y la puerta se ofrecía igual."""
    cliente, llm, _ = mundo

    async def _si(_sid):
        return True

    monkeypatch.setattr(chat_mod, "_pidio_corredor", _si)

    r = _post(cliente, llm, "Busco algo de 2 dormitorios")

    assert r.status_code == 200
    assert r.json().get("puerta") is None, (
        "se ofreció el aviso a quien ya pidió un corredor: la regla 4 sigue inerte"
    )


# ── 4 · B1 · de dónde sale «ya pidió corredor» ───────────────────────────────

class _DobleDB:
    """Doble mínimo de `AsyncSessionLocal`: sólo tiene que responder un `scalar()`."""

    def __init__(self, estado, revienta=False):
        self._estado, self._revienta = estado, revienta

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def execute(self, _sql, _params):
        if self._revienta:
            raise RuntimeError("relation \"handoff_sesion\" does not exist")

        class _R:
            def __init__(self, v):
                self._v = v

            def scalar(self):
                return self._v

        return _R(self._estado)


@pytest.mark.parametrize("estado_en_tabla,esperado", [
    ("solicitado", True),
    ("activo", True),
    (None, False),
])
def test_pidio_corredor_se_lee_de_handoff_sesion(monkeypatch, estado_en_tabla, esperado):
    """La verdad está en la tabla, que es donde convergen los CUATRO caminos que registran el
    hecho. Cualquier estado de la fila cuenta: lo que importa es que exista."""
    monkeypatch.setattr(chat_mod, "AsyncSessionLocal",
                        lambda: _DobleDB(estado_en_tabla))

    assert asyncio.run(chat_mod._pidio_corredor("sesion-x")) is esperado


def test_si_la_tabla_no_existe_la_puerta_decide_sin_ese_dato(monkeypatch):
    """Best-effort declarado: un aviso no vale un turno roto. Sin las tablas de handoff se
    devuelve False en vez de propagar."""
    monkeypatch.setattr(chat_mod, "AsyncSessionLocal",
                        lambda: _DobleDB(None, revienta=True))

    assert asyncio.run(chat_mod._pidio_corredor("sesion-x")) is False


def test_la_puerta_no_se_alimenta_del_motor_de_intencion():
    """LÍNEA ROJA 1 del §6, por lectura de fuente: «el score de intención no dispara la
    puerta». `_pidio_corredor` lee el HECHO (existe la fila del handoff), y no puede colarse
    por aquí ninguna señal comercial."""
    import inspect

    # Sólo el CÓDIGO: el docstring explica precisamente por qué el score no entra aquí, así
    # que buscar sobre él daría un falso positivo con su propia justificación.
    fuente = inspect.getsource(chat_mod._pidio_corredor)
    cuerpo = fuente.replace(chat_mod._pidio_corredor.__doc__ or "", "")
    for prohibido in ("score", "nivel", "analizar_intencion", "intencion_sesion",
                      "caliente", "tibio"):
        assert prohibido not in cuerpo, (
            f"`_pidio_corredor` menciona «{prohibido}»: el motor de intención no puede "
            f"disparar la captura de correo"
        )


# ── 5 · B2 · el control hermano: el modelo pidiendo el correo por su cuenta ──

@pytest.mark.parametrize("frase", [
    "Dame tu correo y te aviso cuando entre algo.",
    "¿Cuál es tu email?",
    "Necesito tu teléfono para mandarte las opciones.",
    "Escribe tu correo aquí abajo.",
])
def test_pedir_el_contacto_en_prosa_se_registra(frase):
    """ROJO ANTES: `detectar_solicitud_contacto` existía, tenía tests y NINGÚN llamador en
    runtime, así que el resquicio que su propia cabecera dice cazar seguía abierto."""
    from app.verificacion_prosa import MEDIA, verificar_prosa

    hallazgos = verificar_prosa(frase, cards=None, puerta_abierta=False)

    codigos = [h["codigo"] for h in hallazgos]
    assert "contacto_pedido_en_prosa" in codigos, f"no se detectó en: {frase!r}"
    hallazgo = next(h for h in hallazgos if h["codigo"] == "contacto_pedido_en_prosa")
    assert hallazgo["gravedad"] == MEDIA, (
        "la gravedad adjudicada es `media`: incumple una regla declarada sin afirmar nada falso"
    )
    assert hallazgo["evidencia"], "sin la frase literal el informe obliga a releer el turno"


def test_con_la_puerta_abierta_nombrar_el_correo_no_es_violacion():
    """Lo dice la propia función: con la directiva emitida, su texto ya habla del aviso y el
    modelo puede nombrarlo. Evaluarlo igual inundaría el contador de falsos positivos."""
    from app.verificacion_prosa import verificar_prosa

    hallazgos = verificar_prosa("Dame tu correo y te aviso.", cards=None,
                                puerta_abierta=True)

    assert [h for h in hallazgos if h["codigo"] == "contacto_pedido_en_prosa"] == []


def test_mencionar_el_correo_sin_pedirlo_no_es_violacion():
    """Alta precisión, igual que el resto del módulo: «el corredor te escribirá a tu correo» es
    legítimo y frecuente después de un handoff."""
    from app.verificacion_prosa import verificar_prosa

    hallazgos = verificar_prosa("El corredor te escribirá a tu correo en breve.",
                                cards=None, puerta_abierta=False)

    assert [h for h in hallazgos if h["codigo"] == "contacto_pedido_en_prosa"] == []


def test_el_veredicto_del_turno_queda_en_warning_y_no_en_failed():
    """La consecuencia de elegir `media`: se MIDE sin precomprometer que el día del interruptor
    de bloqueo un turno se descarte por este motivo."""
    from app.contracts.decision_v0 import VerificationStatus
    from app.decision.verify import auditar_explicacion

    explicacion, hallazgos = auditar_explicacion(
        "Dame tu correo, por favor.", cards=None, puerta_abierta=False)

    assert any(h["codigo"] == "contacto_pedido_en_prosa" for h in hallazgos)
    assert explicacion.verification_status is VerificationStatus.WARNING


def test_el_control_corre_en_un_turno_sin_panel():
    """Un turno puramente conversacional no tiene tarjetas, y es justo donde el modelo tiene más
    espacio para pedir el dato. El chequeo no puede depender de que haya panel."""
    from app.verificacion_prosa import verificar_prosa

    assert any(h["codigo"] == "contacto_pedido_en_prosa"
               for h in verificar_prosa("¿Cuál es tu correo?", cards=[], puerta_abierta=False))


def test_tampoco_se_repite_por_el_camino_de_streaming(mundo):
    """El stream es el camino que usa la gente de verdad. La marca la escribe la rama SSE con
    su propia config de escritura lateral, así que se prueba aparte."""
    cliente, llm, compilado = mundo

    primero = _post(cliente, llm, "Busco algo de 2 dormitorios", stream=True)
    assert primero.status_code == 200
    assert '"puerta"' in primero.text and "callejon_honesto" in primero.text
    assert _estado(compilado).get("puerta_ofrecida") is True

    segundo = _post(cliente, llm, "¿Y si amplío la zona?", stream=True)
    assert "callejon_honesto" not in segundo.text, (
        "la puerta volvió a ofrecerse por el camino de streaming"
    )
