"""TR-1 · la puerta suave YA NO se ofrece — probado con endpoint, grafo y checkpointer REALES.

EXPECTED UPDATE · SURFACE RETIRED BY OFD-02 (Plan 1.1 · TR-1). Este fichero nació para B3: que
la puerta se ofreciera UNA vez por hilo y que la marca `puerta_ofrecida` sobreviviera al turno
siguiente. La puerta se retiró —prometía un aviso que ningún código envía—, así que lo que se
prueba ahora es lo contrario, con el MISMO arnés y el MISMO escenario:

  · el «callejón honesto» (criterio declarado + panel vacío), que antes abría la puerta, ya no
    la abre — ni por el camino no-stream ni por SSE, ni cuando la persona dice «avísame»;
  · la marca `puerta_ofrecida` ya no se escribe (la clave sigue declarada en `AgentState`, inerte,
    por compatibilidad con checkpoints viejos);
  · el campo `puerta` sigue en el contrato y vale `null`.

Los tests que se invirtieron llevan la marca `EXPECTED UPDATE`. Los de B1 (`_pidio_corredor`, la
regla 4 de la puerta) se RETIRARON con la función, que sólo servía a la puerta: su versión íntegra
vive en `8d8dd683:tests/test_puerta_persistencia.py`. Los de B2 —el modelo pidiendo el correo en
prosa— siguen aquí sin tocar una línea: ese control no depende de la puerta.

POR QUÉ EL ARNÉS REAL. Un test que anulara la emisión de la puerta no probaría que ya no se
emite. Aquí el endpoint, el grafo y el checkpointer son reales (en memoria), y los tests
invertidos comprueban ANTES que el escenario sigue siendo el callejón honesto: sin eso pasarían
por la razón equivocada.
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
    # Nada de la puerta se anula: su retirada es justamente lo que se prueba.
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


# ── 1 · el escenario sigue siendo el callejón honesto, y la puerta ya no se abre ────

def _es_callejon_honesto(compilado, cuerpo, sesion=SESION):
    """Control del arnés: las dos condiciones que ANTES abrían la puerta siguen dándose.
    Sin esto, los tests de abajo pasarían aunque el escenario dejara de ser el que era."""
    valores = _estado(compilado, sesion)
    assert (valores.get("preferencias") or {}).get("dormitorios") == 2, (
        "no hay criterio declarado: el escenario ya no es el callejón honesto")
    assert not cuerpo.get("results"), "el panel trae tarjetas: ya no es un callejón"


def test_el_callejon_honesto_ya_no_ofrece_la_puerta(mundo):
    """EXPECTED UPDATE · SURFACE RETIRED BY OFD-02. Antes: `test_el_callejon_honesto_ofrece_la_puerta`
    (control del arnés que exigía `puerta`). Ahora el mismo escenario devuelve `puerta: null`."""
    cliente, llm, compilado = mundo

    r = _post(cliente, llm, "Busco algo de 2 dormitorios")

    assert r.status_code == 200
    cuerpo = r.json()
    _es_callejon_honesto(compilado, cuerpo)
    assert "puerta" in cuerpo, "la clave `puerta` salió del contrato: un frontend viejo la lee"
    assert cuerpo["puerta"] is None, "la puerta retirada se volvió a ofrecer"


@pytest.mark.parametrize("texto", [
    "avísame cuando haya algo de 2 dormitorios",
    "me avisas si sale algo de 2 dormitorios",
    "¿me puedes avisar cuando aparezca un depa de 2 dormitorios?",
])
def test_pedir_aviso_ya_no_abre_la_puerta(mundo, texto):
    """El segundo disparador de la puerta era que la persona lo pidiera. Ya no hay nada que
    ofrecer: pedirlo no crea la oferta."""
    cliente, llm, compilado = mundo

    r = _post(cliente, llm, texto)

    assert r.status_code == 200
    assert r.json()["puerta"] is None


# ── 2 · la marca ya no se escribe (EXPECTED UPDATE de B3) ─────────────────────

def test_la_marca_ya_no_se_escribe(mundo):
    """EXPECTED UPDATE · SURFACE RETIRED BY OFD-02. Antes: `test_la_marca_queda_escrita_en_el_estado_declarado`
    y `test_la_marca_sobrevive_al_turno_siguiente` (B3). Sin puerta no hay nada que marcar: la
    clave sigue declarada en `AgentState` pero nadie la escribe, ni en el primer turno ni después."""
    cliente, llm, compilado = mundo

    _post(cliente, llm, "Busco algo de 2 dormitorios")
    _post(cliente, llm, "¿Y si amplío la zona?")

    assert not _estado(compilado).get("puerta_ofrecida")


# ── 3 · ningún turno la ofrece (EXPECTED UPDATE de la regla «una vez») ────────

def test_ningun_turno_ofrece_la_puerta(mundo):
    """EXPECTED UPDATE · SURFACE RETIRED BY OFD-02. Antes: `test_la_puerta_no_se_repite_en_el_turno_siguiente`,
    que exigía la puerta en el primer turno y no en el segundo. Ahora no sale en ninguno."""
    cliente, llm, _ = mundo

    primero = _post(cliente, llm, "Busco algo de 2 dormitorios")
    segundo = _post(cliente, llm, "¿Y si amplío la zona?")

    assert primero.json()["puerta"] is None
    assert segundo.json()["puerta"] is None


# ── 4 · B1 · RETIRADO con la puerta ───────────────────────────────────────────
# `_pidio_corredor` (B1) leía `handoff_sesion` para la regla 4 de la puerta —«al que ya pidió
# corredor no se le ofrece»— y no tenía otro llamador. Se retiró con la puerta, y con ella sus
# cinco casos: `test_si_ya_pidio_corredor_no_se_ofrece_la_puerta`,
# `test_pidio_corredor_se_lee_de_handoff_sesion` (×3), `test_si_la_tabla_no_existe_la_puerta_decide_sin_ese_dato`
# y `test_la_puerta_no_se_alimenta_del_motor_de_intencion`.
# EXPECTED UPDATE · SURFACE RETIRED BY OFD-02 — no fallaban: probaban código que ya no existe.


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


def test_tampoco_se_ofrece_por_el_camino_de_streaming(mundo):
    """EXPECTED UPDATE · SURFACE RETIRED BY OFD-02. Antes: `test_tampoco_se_repite_por_el_camino_de_streaming`,
    que exigía la puerta en el primer turno SSE. El stream es el camino que usa la gente de
    verdad: el panel sigue llevando la clave `puerta`, siempre `null`, y la marca no se escribe."""
    import json

    cliente, llm, compilado = mundo

    for texto in ("Busco algo de 2 dormitorios", "avísame cuando haya algo de 2 dormitorios"):
        r = _post(cliente, llm, texto, stream=True)
        assert r.status_code == 200
        paneles = []
        for linea in r.text.splitlines():
            if linea.startswith("data:"):
                try:
                    evento = json.loads(linea[5:].strip())
                except ValueError:
                    continue
                if isinstance(evento, dict) and "panel" in evento:
                    paneles.append(evento["panel"])
        assert paneles, "el stream no emitió el panel: el arnés no prueba nada"
        assert all("puerta" in p and p["puerta"] is None for p in paneles)
        assert "callejon_honesto" not in r.text

    assert not _estado(compilado).get("puerta_ofrecida")
