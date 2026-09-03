"""SSE-OUTPUT-GATE-01 · la decisión de publicar texto se toma al FINAL de cada invocación.

QUÉ CIERRA. `PRE-YIELD-01` verificó tres agujeros en el camino SSE:

  H1  la prosa de la ronda 1 —la que el modelo escribe ANTES de llamar a una herramienta—
      se transmitía al cliente token a token, antes de que existiera evidencia territorial,
      contrato o barrera. Ocurrió en producción: el canary de `8322e25` emitió
      «Perfecto, voy a buscar arriendos en La Floresta…» antes del primer `tool_use`.
  H2  en fail-closed, `llm_node` devuelve el mensaje controlado SIN invocar al modelo, así
      que no genera `on_chat_model_stream` y el cliente SSE no recibía NADA: la frase de la
      ronda 1 y luego silencio. Justo lo que R3 dice querer evitar.
  H3  el `panel` salía igual, con tarjetas y sin prosa que las gobernara.

LA COMPUERTA. Se acumulan los chunks por `run_id` y no se publica nada hasta
`on_chat_model_end`; ahí se mira la salida ESTRUCTURALMENTE: si trae `tool_calls`, la prosa
acumulada se descarta entera; si no, se publica en orden y exactamente una vez.

    NO se decide por regex, por el texto, por el nombre de la herramienta ni por el prompt.
    Se decide por `tool_calls`, que es lo que distingue una respuesta de un preámbulo.

ES UNA PÉRDIDA DELIBERADA DE INCREMENTALIDAD. Dentro de una invocación el texto ya no llega
token a token: llega completo al terminar esa invocación. No se puede presentar como
«streaming intacto» — se cambia latencia percibida por gobierno de la salida.

EL DISCRIMINADOR ES ESTRUCTURAL. Sólo se publica lo que emite el nodo `llm`
(`metadata.langgraph_node`), que es el generador de la respuesta al cliente. Hoy no hay otro
chat model dentro de este grafo —`extraer_preferencias` y el intérprete del buyer usan el SDK
crudo de Anthropic y por eso no aparecen en `astream_events`— pero la compuerta no lo supone.

LA SALIDA CONTROLADA. Se detecta en el `on_chain_end` del propio nodo `llm`: su
`data.output.messages` es lo que ESE paso produjo, no el historial. Esa es la frontera
determinista del turno — no se lee «el último AIMessage del checkpoint», que confundiría una
respuesta vieja con la de hoy.
"""
import asyncio
import json
from typing import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.memory import MemorySaver

import main
from app.agent import graph as G
from app.agent import tools as TOOLS
from app.decision import assembler
from app.routers import chat as chat_mod
from app.sesion_autoridad import Autoridad

ANCLA = {"latitude": -0.20934, "longitude": -78.484919}

_GUION: list = []
_FALLA_EN_CHUNK: dict = {}


def _fila(aid="ee9ff315"):
    return {"id": aid, "direccion_estandarizada": f"Calle {aid}", "caminabilidad": 100,
            "walk_score_fuente": None, "score_ruido_predictivo": 1,
            "volumen_trafico_historico": 1, "densidad_poblacional_pico": 1,
            "porcentaje_cobertura_vegetal": 40, "conectividad": None,
            "servicios_cercanos": None, "operacion": "ARRIENDO", "precio": 630,
            "distancia_metros": 572.0, "tipo_activo": "Departamento"}


def _card(aid="ee9ff315"):
    return {"id": aid, "direccion": f"Calle {aid}", "tipo_activo": "Departamento",
            "operacion": "ARRIENDO", "precio": 630.0, "imagen_url": None, "caminabilidad": 90,
            "caminabilidad_fuente": "osm", "ruido": "BAJO", "vegetacion": 40, "lat": -0.209,
            "lon": -78.484, "caracteristicas": {}, "servicios_cercanos": None,
            "conectividad": None}


class _FalsoQueTransmite(BaseChatModel):
    """`BaseChatModel` DE VERDAD. Un falso plano no produce `on_chat_model_stream` y daría un
    falso negativo: la primera versión de este probe «demostró» que no se filtraba nada
    porque su modelo no transmitía."""

    @property
    def _llm_type(self) -> str:
        return "falso-transmisor"

    def bind_tools(self, tools, **kw):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kw) -> ChatResult:
        m = _GUION.pop(0) if _GUION else AIMessage(content="final")
        return ChatResult(generations=[ChatGeneration(message=m)])

    async def _astream(self, messages, stop=None, run_manager=None,
                       **kw) -> AsyncIterator[ChatGenerationChunk]:
        m = _GUION.pop(0) if _GUION else AIMessage(content="final")
        texto = m.content if isinstance(m.content, str) else ""
        palabras = texto.split(" ") if texto else []
        for i, p in enumerate(palabras):
            if _FALLA_EN_CHUNK.get("i") == i:
                raise RuntimeError("el modelo reventó a mitad de la transmisión")
            ch = AIMessageChunk(content=p + " ")
            if run_manager:
                await run_manager.on_llm_new_token(p + " ", chunk=ch)
            yield ChatGenerationChunk(message=ch)
        yield ChatGenerationChunk(message=AIMessageChunk(
            content="", tool_calls=getattr(m, "tool_calls", []) or []))


def _tool_call(nombre="tool_search_nearby_assets"):
    return {"name": nombre,
            "args": {"latitude": ANCLA["latitude"], "longitude": ANCLA["longitude"],
                     "radius_meters": 1200},
            "id": "tc-1"}


@pytest.fixture
def mundo(monkeypatch):
    """Endpoint, grafo y checkpointer REALES. `TestClient` sin `with`: el lifespan montaría el
    checkpointer contra la Supabase de producción (ver tests/test_health_memoria.py)."""
    _GUION.clear()
    _FALLA_EN_CHUNK.clear()

    async def _rows(_q, _p):
        return [_fila()]

    async def _cards(ids):
        return ([_card(i) for i in ids], {})

    async def _prefs(_t):
        return {"operacion": "arriendo"}

    async def _nada(*a, **k):
        return None

    async def _autoridad(*a, **k):
        return Autoridad.OWNER

    monkeypatch.setattr(TOOLS, "_fetch_rows", _rows)
    monkeypatch.setattr(assembler, "_fetch_cards_rows", _cards)
    monkeypatch.setattr(G, "extraer_preferencias", _prefs)
    monkeypatch.setattr(assembler, "extraer_preferencias", _prefs)
    monkeypatch.setattr(G, "ChatAnthropic", lambda **kw: _FalsoQueTransmite())
    monkeypatch.setattr(chat_mod, "_exigir_autoridad", _autoridad)
    monkeypatch.setattr(chat_mod, "registrar_intencion", _nada)
    monkeypatch.setattr(chat_mod, "actualizar_en_sombra", _nada)
    monkeypatch.setattr(chat_mod, "_marcar_puerta_ofrecida", _nada)
    monkeypatch.setattr(chat_mod, "_auditar_prosa", lambda *a, **k: None)
    # El limiter es global y su contador sobrevive al módulo: sin esto, los ~12 POST de
    # aquí agotan los 15/min y el 429 cae sobre el SIGUIENTE fichero de la suite, no sobre
    # éste. Costó seis fallos ajenos en `test_state_lineage_semilla_del_turno` averiguarlo.
    from app.limiter import limiter
    monkeypatch.setattr(limiter, "enabled", False)

    compilado = G._build_graph().compile(checkpointer=MemorySaver())
    monkeypatch.setattr(G, "compiled_graph", compilado)

    from app.auth import get_optional_user
    main.app.dependency_overrides[get_optional_user] = lambda: None
    cliente = TestClient(main.app)
    try:
        yield cliente, compilado
    finally:
        main.app.dependency_overrides.clear()


def _sse(texto: str) -> list[tuple]:
    """El transcript tal como lo ve el cliente: (tipo, valor) en orden de llegada."""
    out = []
    for linea in texto.splitlines():
        if not linea.startswith("data: "):
            continue
        try:
            d = json.loads(linea[6:])
        except Exception:  # noqa: BLE001
            continue
        k = next(iter(d))
        if k == "token":
            out.append(("token", d["token"]))
        elif k == "tool_call":
            out.append(("tool_call", d["tool_call"]))
        elif k == "panel":
            out.append(("panel", [c.get("id") for c in (d["panel"].get("results") or [])]))
        elif k == "done":
            out.append(("done", ""))
    return out


def _tokens(tr) -> str:
    return "".join(v for t, v in tr if t == "token")


def _tipos(tr) -> list[str]:
    return [t for t, _ in tr]


def _post(cliente, texto="Busco arriendo en La Floresta", sesion="sse", stream=True):
    return cliente.post(f"/api/v1/chat/?stream={'true' if stream else 'false'}",
                        json={"message": texto, "session_id": sesion})


def _romper(monkeypatch, que):
    import app.encaje_contexto as enc

    def boom(*a, **k):
        raise RuntimeError("boom")

    if que in ("enriquecido", "todo"):
        monkeypatch.setattr(enc, "bloque_autoritativo", boom)
    if que in ("fallback", "todo"):
        monkeypatch.setattr(enc, "bloque_territorial_minimo", boom)


# ══ 1 · EL PREÁMBULO NO SALE ═════════════════════════════════════════════════

def test_prosa_previa_a_la_herramienta_no_produce_ningun_token(mundo):
    """H1. Es la frase que el canary real emitió en producción antes del primer `tool_use`."""
    cliente, _ = mundo
    _GUION[:] = [
        AIMessage(content="Perfecto, voy a buscar arriendos en La Floresta.",
                  tool_calls=[_tool_call()]),
        AIMessage(content="Encontré una opción."),
    ]
    tr = _sse(_post(cliente).text)

    assert "La Floresta" not in _tokens(tr), f"se filtró el preámbulo: {_tokens(tr)!r}"
    assert _tokens(tr).strip() == "Encontré una opción."
    assert _tipos(tr) == ["tool_call", "token", "token", "token", "panel", "done"] or \
        _tipos(tr).count("tool_call") == 1


def test_el_orden_externo_se_conserva(mundo):
    cliente, _ = mundo
    _GUION[:] = [AIMessage(content="preámbulo", tool_calls=[_tool_call()]),
                 AIMessage(content="final")]
    tipos = _tipos(_sse(_post(cliente).text))

    assert tipos[0] == "tool_call"
    assert tipos[-2:] == ["panel", "done"]
    assert tipos.index("tool_call") < tipos.index("panel")


# ══ 2 · RESPUESTA DIRECTA, SIN HERRAMIENTA ═══════════════════════════════════

def test_respuesta_directa_sale_exactamente_una_vez(mundo):
    cliente, _ = mundo
    _GUION[:] = [AIMessage(content="Hola, cuéntame qué buscas.")]
    tr = _sse(_post(cliente, texto="hola").text)

    assert _tokens(tr).strip() == "Hola, cuéntame qué buscas."
    assert _tipos(tr).count("done") == 1
    assert "tool_call" not in _tipos(tr)


# ══ 3 · FAIL-CLOSED · el mensaje controlado SÍ llega ═════════════════════════

def test_fail_closed_emite_el_mensaje_controlado_antes_del_panel(mundo, monkeypatch):
    """H2. `llm_node` lo produce SIN invocar al modelo, así que no hay chunks que acumular:
    la compuerta lo toma de la salida del NODO, que es de este paso y no del historial."""
    cliente, _ = mundo
    _romper(monkeypatch, "todo")
    _GUION[:] = [AIMessage(content="preámbulo que no debe salir",
                           tool_calls=[_tool_call()])]
    tr = _sse(_post(cliente).text)

    texto = _tokens(tr)
    assert "no puedo describir con precisión" in texto, f"transcript: {tr}"
    assert "preámbulo" not in texto
    tipos = _tipos(tr)
    assert tipos.index("token") < tipos.index("panel") < tipos.index("done")
    assert texto.count("no puedo describir con precisión") == 1


def test_fallo_del_enriquecido_sigue_emitiendo_la_prosa_final(mundo, monkeypatch):
    """Fila 4 de R3: hay fallback, el modelo sí escribe, y su prosa se publica normal."""
    cliente, _ = mundo
    _romper(monkeypatch, "enriquecido")
    _GUION[:] = [AIMessage(content="preámbulo", tool_calls=[_tool_call()]),
                 AIMessage(content="prosa final gobernada")]
    tr = _sse(_post(cliente).text)

    assert _tokens(tr).strip() == "prosa final gobernada"
    assert "preámbulo" not in _tokens(tr)


# ══ 4 · SEGUNDA RONDA DE HERRAMIENTA ═════════════════════════════════════════

def test_segunda_tentativa_de_herramienta_tampoco_filtra(mundo):
    """Dos rondas con preámbulo y una tercera que responde: sólo sale la tercera."""
    cliente, _ = mundo
    _GUION[:] = [
        AIMessage(content="primer preámbulo", tool_calls=[_tool_call()]),
        AIMessage(content="segundo preámbulo", tool_calls=[_tool_call()]),
        AIMessage(content="respuesta"),
    ]
    tr = _sse(_post(cliente).text)

    assert _tokens(tr).strip() == "respuesta"
    assert "preámbulo" not in _tokens(tr)
    assert _tipos(tr).count("tool_call") == 2


# ══ 5 · ERROR Y CANCELACIÓN · nunca se vacía tarde ═══════════════════════════

def test_excepcion_a_mitad_de_la_transmision_no_publica_el_buffer(mundo):
    """Un buffer incompleto NUNCA se publica: si el modelo revienta antes de
    `on_chat_model_end`, lo acumulado muere con él.

    Se recoge lo que ALCANZÓ A LLEGAR al cliente antes del fallo, no `r.text`: con
    `r.text` la excepción se traga la respuesta entera y la prueba pasaría sin afirmar
    nada — que es exactamente como pasaba la primera versión de esta prueba.
    """
    cliente, _ = mundo
    _GUION[:] = [AIMessage(content="esto se corta a la mitad del envío")]
    _FALLA_EN_CHUNK["i"] = 3

    recibido: list[str] = []
    try:
        with cliente.stream("POST", "/api/v1/chat/?stream=true",
                            json={"message": "hola", "session_id": "err"}) as r:
            for linea in r.iter_lines():
                recibido.append(linea)
    except BaseException:  # noqa: BLE001 — el fallo del modelo se propaga; interesa lo ya emitido
        pass

    assert not any("esto se corta" in l for l in recibido), \
        f"vació un buffer incompleto: {recibido}"

    # La comprobación anterior NO discrimina por sí sola: la excepción derriba la respuesta
    # antes de que nada se vuelque al socket, así que `recibido` sale vacío incluso con una
    # compuerta que publicara en cada chunk. La que sí discrimina es ésta — una invocación
    # que empieza y transmite pero nunca cierra no autoriza ni un token.
    compuerta = chat_mod._CompuertaSSE()
    md = {"langgraph_node": "llm", "langgraph_step": 1}
    emitido = []
    for kind, datos in [("on_chat_model_start", {}),
                        ("on_chat_model_stream", {"chunk": AIMessageChunk(content="a ")}),
                        ("on_chat_model_stream", {"chunk": AIMessageChunk(content="medias")})]:
        emitido += compuerta.procesar({"event": kind, "run_id": "roto", "name": "m",
                                       "metadata": md, "data": datos})
    assert emitido == [], f"publicó sin `on_chat_model_end`: {emitido}"
    compuerta.cerrar()
    assert not compuerta.pendientes


def test_una_respuesta_historica_no_se_reproduce(mundo):
    """El checkpoint ya trae una respuesta del turno anterior. El turno actual falla en
    fail-closed: la recuperación NO puede servir la respuesta vieja."""
    cliente, compilado = mundo
    _GUION[:] = [AIMessage(content="RESPUESTA DEL TURNO VIEJO")]
    _post(cliente, texto="hola", sesion="hist")

    import app.encaje_contexto as enc
    mp = pytest.MonkeyPatch()

    def boom(*a, **k):
        raise RuntimeError("boom")

    mp.setattr(enc, "bloque_autoritativo", boom)
    mp.setattr(enc, "bloque_territorial_minimo", boom)
    _GUION[:] = [AIMessage(content="preámbulo", tool_calls=[_tool_call()])]
    tr = _sse(_post(cliente, sesion="hist").text)
    mp.undo()

    assert "TURNO VIEJO" not in _tokens(tr), f"reprodujo el historial: {tr}"
    assert "no puedo describir con precisión" in _tokens(tr)


def test_dos_turnos_con_texto_identico_no_confunden_la_frontera(mundo):
    """La frontera del turno no puede depender de comparar contenido: dos turnos con el
    MISMO texto de usuario y la MISMA respuesta deben publicar una vez cada uno."""
    cliente, _ = mundo
    for i in (1, 2):
        _GUION[:] = [AIMessage(content="misma respuesta")]
        tr = _sse(_post(cliente, texto="lo mismo", sesion="igual").text)
        assert _tokens(tr).strip() == "misma respuesta", f"turno {i}: {tr}"
        assert _tokens(tr).count("misma respuesta") == 1


def test_no_hay_doble_emision_entre_el_vaciado_y_la_recuperacion(mundo):
    """El camino normal publica en `on_chat_model_end`; la recuperación mira la salida del
    nodo. Si ambos actuaran, la respuesta saldría dos veces."""
    cliente, _ = mundo
    _GUION[:] = [AIMessage(content="preámbulo", tool_calls=[_tool_call()]),
                 AIMessage(content="UNICA")]
    tr = _sse(_post(cliente).text)
    assert _tokens(tr).count("UNICA") == 1, f"doble emisión: {tr}"


# ══ 6 · DISCRIMINADOR ESTRUCTURAL · lo que no es el generador no sale ════════

def test_una_invocacion_que_no_es_del_nodo_llm_no_se_publica():
    """La compuerta se prueba en aislamiento con eventos sintéticos: hoy no hay otro chat
    model dentro de este grafo, pero la compuerta no puede asumirlo. El discriminador es
    `metadata.langgraph_node`, no el nombre del modelo ni el orden."""
    compuerta = chat_mod._CompuertaSSE()
    ev = [
        {"event": "on_chat_model_start", "run_id": "r-int", "name": "Interno",
         "metadata": {"langgraph_node": "otro_nodo", "langgraph_step": 1}, "data": {}},
        {"event": "on_chat_model_stream", "run_id": "r-int", "name": "Interno",
         "metadata": {"langgraph_node": "otro_nodo", "langgraph_step": 1},
         "data": {"chunk": AIMessageChunk(content="texto interno")}},
        {"event": "on_chat_model_end", "run_id": "r-int", "name": "Interno",
         "metadata": {"langgraph_node": "otro_nodo", "langgraph_step": 1},
         "data": {"output": AIMessage(content="texto interno")}},
    ]
    emitido = []
    for e in ev:
        emitido += compuerta.procesar(e)
    assert emitido == [], f"publicó una invocación ajena al nodo llm: {emitido}"


def test_los_buffers_no_se_mezclan_entre_run_ids():
    """Dos invocaciones simultáneas del nodo `llm`: cada una publica lo suyo, y la que trae
    `tool_calls` no arrastra a la otra."""
    compuerta = chat_mod._CompuertaSSE()
    md = {"langgraph_node": "llm", "langgraph_step": 1}

    def ev(kind, rid, **d):
        return {"event": kind, "run_id": rid, "name": "m", "metadata": md, "data": d}

    salida = []
    for e in [
        ev("on_chat_model_start", "A"),
        ev("on_chat_model_start", "B"),
        ev("on_chat_model_stream", "A", chunk=AIMessageChunk(content="AAA")),
        ev("on_chat_model_stream", "B", chunk=AIMessageChunk(content="BBB")),
        ev("on_chat_model_end", "A",
           output=AIMessage(content="AAA", tool_calls=[_tool_call()])),
        ev("on_chat_model_end", "B", output=AIMessage(content="BBB")),
    ]:
        salida += compuerta.procesar(e)

    assert salida == ["BBB"], f"mezcló buffers: {salida}"


def test_los_buffers_se_limpian_al_cerrar():
    compuerta = chat_mod._CompuertaSSE()
    md = {"langgraph_node": "llm", "langgraph_step": 1}
    compuerta.procesar({"event": "on_chat_model_start", "run_id": "X", "name": "m",
                        "metadata": md, "data": {}})
    compuerta.procesar({"event": "on_chat_model_stream", "run_id": "X", "name": "m",
                        "metadata": md, "data": {"chunk": AIMessageChunk(content="a medias")}})
    assert compuerta.pendientes
    compuerta.cerrar()
    assert not compuerta.pendientes, "quedaron buffers vivos tras cerrar"


# ══ 7 · EL CAMINO NO-STREAM NO CAMBIA ════════════════════════════════════════

def test_stream_false_intacto(mundo):
    cliente, _ = mundo
    _GUION[:] = [AIMessage(content="preámbulo", tool_calls=[_tool_call()]),
                 AIMessage(content="respuesta no-stream")]
    r = _post(cliente, sesion="nostream", stream=False)

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["reply"] == "respuesta no-stream"
    assert [c["id"] for c in cuerpo["results"]] == ["ee9ff315"]
