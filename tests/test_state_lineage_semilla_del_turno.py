"""STATE-LINEAGE-R1 · el turno entra con el panel limpio, por los DOS caminos.

EL DEFECTO. `POST /api/v1/chat/` tiene dos ramas y cada una sembraba el estado de entrada de
forma distinta:

    stream=true   messages · spatial_context · sql_results · cards · descartadas · encaje_contexto
    stream=false  messages · spatial_context · sql_results
                                            ↑ y nada más

Las claves de `AgentState` no llevan reducer: son canales `LastValue` que LangGraph persiste y
arrastra al turno siguiente. Así que por `stream=false` un turno que no busca nada heredaba el
panel del turno anterior — y el endpoint lo devolvía como panel del turno actual, porque
`final_state.get("cards")` sólo se reconstruye si viene vacío, y heredado nunca viene vacío.

Efecto de segundo orden: `_auditar_prosa` audita la respuesta de hoy contra las tarjetas de
ayer.

LO QUE ESTABA DEMOSTRADO, y lo que no:

    [VERIFICADO]  el frontend usa stream=true          → camino sano
    [VERIFICADO]  los evals usan stream=false          → pero session_id nuevo por caso
    [DESCONOCIDO] consumidores externos multi-turno    → el endpoint está desplegado

No se puede afirmar que hoy no tenga víctima: sólo que ningún cliente CONOCIDO la sufre.

LA CAUSA NO FUE OLVIDAR UNA LÍNEA. Fue que hubiera DOS sitios donde acordarse de escribirla.
Por eso la corrección es un constructor único de entrada por turno, no tres líneas copiadas al
otro camino: lo segundo arregla el síntoma y deja la bifurcación intacta para la próxima vez.

QUÉ NO SE REINICIA, y por qué:
  · `messages`      lleva reducer `add_messages`: es el hilo, y reiniciarlo sería borrarlo.
  · `preferencias`  continuidad deliberada, con llave de turno (`preferencias_turno`).
  · los índices de R3 se auto-protegen comparándose con el turno actual.

`sql_results` sí se reinicia —ya lo hacían ambos caminos— pero sigue sin tener un solo lector
en todo el repositorio. Queda registrado como `DEAD-STATE-sql_results`, deuda aparte.
"""
import asyncio

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

import main
from app.agent import graph as G
from app.agent import tools as TOOLS
from app.decision import assembler
from app.routers import chat as chat_mod
from app.sesion_autoridad import Autoridad

ANCLA = {"latitude": -0.20934, "longitude": -78.484919}
SESION = "sesion-lineage"

def _fila(aid):
    return {"id": aid, "direccion_estandarizada": f"Calle {aid}", "caminabilidad": 100,
            "walk_score_fuente": None, "score_ruido_predictivo": 1,
            "volumen_trafico_historico": 1, "densidad_poblacional_pico": 1,
            "porcentaje_cobertura_vegetal": 40, "conectividad": None,
            "servicios_cercanos": None, "operacion": "ARRIENDO", "precio": 630,
            "distancia_metros": 572.0, "tipo_activo": "Departamento"}


def _card(aid):
    return {"id": aid, "direccion": f"Calle {aid}", "tipo_activo": "Departamento",
            "operacion": "ARRIENDO", "precio": 630.0, "imagen_url": None, "caminabilidad": 90,
            "caminabilidad_fuente": "osm", "ruido": "BAJO", "vegetacion": 40, "lat": -0.209,
            "lon": -78.484, "caracteristicas": {}, "servicios_cercanos": None,
            "conectividad": None}


_CARD = _card("ee9ff315")


class _LLM:
    def __init__(self, **_kw):
        self.guion = []

    def bind_tools(self, _t):
        return self

    async def ainvoke(self, _m):
        return self.guion.pop(0) if self.guion else AIMessage(content="respuesta final")


@pytest.fixture
def mundo(monkeypatch):
    """Endpoint REAL + grafo REAL + checkpointer REAL (en memoria). Sin Postgres, sin red.

    `TestClient` SIN `with`, a propósito y por el mismo motivo que documenta
    tests/test_health_memoria.py: como gestor de contexto ejecuta el lifespan de la app, que
    monta el checkpointer contra la Supabase de PRODUCCIÓN.
    """
    # `catalogo` es lo que "hay en la base" en cada momento: mutarlo entre turnos permite
    # probar que una búsqueda NUEVA reemplaza los ids anteriores en vez de unirlos.
    catalogo = ["ee9ff315"]

    async def _rows(_q, _p):
        return [_fila(a) for a in catalogo]

    async def _cards(ids):
        return ([_card(i) for i in ids], {})

    async def _prefs(_t):
        return {"operacion": "arriendo"}

    creados = []

    class _Fab(_LLM):
        def __init__(self, **kw):
            super().__init__(**kw)
            creados.append(self)

    monkeypatch.setattr(TOOLS, "_fetch_rows", _rows)
    monkeypatch.setattr(assembler, "_fetch_cards_rows", _cards)
    monkeypatch.setattr(G, "extraer_preferencias", _prefs)
    # `assembler` lo importa por su cuenta: sin esto, la RECONSTRUCCIÓN del panel
    # (build_result_cards → construir_panel con preferencias=None) sale a la red.
    monkeypatch.setattr(assembler, "extraer_preferencias", _prefs)
    monkeypatch.setattr(G, "ChatAnthropic", _Fab)

    compilado = G._build_graph().compile(checkpointer=MemorySaver())
    monkeypatch.setattr(G, "compiled_graph", compilado)

    # Todo lo que el endpoint hace ALREDEDOR del turno y toca la base o la red.
    async def _autoridad(*_a, **_k):
        return Autoridad.OWNER

    async def _nada(*_a, **_k):
        return None

    monkeypatch.setattr(chat_mod, "_exigir_autoridad", _autoridad)
    monkeypatch.setattr(chat_mod, "registrar_intencion", _nada)
    monkeypatch.setattr(chat_mod, "actualizar_en_sombra", _nada)
    monkeypatch.setattr(chat_mod, "_marcar_puerta_ofrecida", _nada)

    auditados = []

    def _spy(session_id, reply, valores):
        auditados.append({"session": session_id, "reply": reply, "valores": valores})

    monkeypatch.setattr(chat_mod, "_auditar_prosa", _spy)

    from app.auth import get_optional_user
    main.app.dependency_overrides[get_optional_user] = lambda: None

    cliente = TestClient(main.app)
    llm = creados[0]
    try:
        yield cliente, llm, auditados, compilado, catalogo
    finally:
        main.app.dependency_overrides.clear()


def _guionar(llm, territorial):
    llm.guion = ([AIMessage(content="", tool_calls=[{
        "name": "tool_search_nearby_assets",
        "args": {"latitude": ANCLA["latitude"], "longitude": ANCLA["longitude"],
                 "radius_meters": 1200}, "id": "t1"}])] if territorial else []) + \
        [AIMessage(content="respuesta final")]


def _post(cliente, llm, texto, territorial, stream=False, sesion=SESION):
    _guionar(llm, territorial)
    return cliente.post(f"/api/v1/chat/?stream={'true' if stream else 'false'}",
                        json={"message": texto, "session_id": sesion})


def _estado(compilado, sesion=SESION):
    return asyncio.run(compilado.aget_state(
        {"configurable": {"thread_id": sesion}})).values


# ══ 1 · EL CANAL SE LIMPIA · el panel de la VISTA puede rederivarse ══════════
#
# LA DISTINCIÓN QUE GOBIERNA ESTA UNIDAD, y que costó un rodeo encontrar:
#
#   cards (canal de estado)   DERIVED_REBUILD   · debe limpiarse
#   panel.results (vista UI)  SESSION_CONTINUITY· puede rederivarse del historial
#   autoridad territorial     PER_TURN          · nunca puede heredarse
#
# Que un seguimiento conserve el panel en pantalla es deliberado y está escrito en
# `_collect_asset_ids`: «si el turno actual no buscó nada … cae a los acumulados del hilo
# PARA NO VACIAR EL PANEL DE GOLPE». Eso NO se toca aquí; si algún día se discute, es
# `PANEL-CONTINUITY-01`, una decisión de producto, no de higiene de canales.

def test_el_checkpoint_no_conserva_el_panel_almacenado_del_turno_anterior(mundo):
    """INVARIANTE 1. Lo que no puede sobrevivir es el ESTADO: que el turno 2 vuelva a mostrar
    el panel es continuidad; que lo tome del canal en vez de rederivarlo es confiar en un
    residuo que nadie garantizó que siga siendo cierto."""
    cliente, llm, _, compilado, catalogo = mundo

    r1 = _post(cliente, llm, "Busco arriendo en La Floresta", territorial=True)
    assert [c["id"] for c in r1.json()["results"]] == ["ee9ff315"]
    assert _estado(compilado)["cards"], "el turno 1 debía dejar panel en el canal"

    _post(cliente, llm, "hola, gracias", territorial=False)
    v = _estado(compilado)
    assert not v.get("cards"), "el canal `cards` quedó heredado"
    assert not v.get("descartadas"), "el canal `descartadas` quedó heredado"
    assert not (v.get("encaje_contexto") or ""), "el canal `encaje_contexto` quedó heredado"


def test_un_seguimiento_puede_rederivar_el_MISMO_panel_desde_messages(mundo):
    """INVARIANTE 2. La continuidad de la vista no depende del canal: se reconstruye del
    hilo. Es lo que hace que limpiar el canal sea seguro."""
    cliente, llm, _, compilado, catalogo = mundo

    r1 = _post(cliente, llm, "Busco arriendo en La Floresta", territorial=True)
    r2 = _post(cliente, llm, "¿y ese tiene parqueadero?", territorial=False)

    assert [c["id"] for c in r2.json()["results"]] == [c["id"] for c in r1.json()["results"]]
    assert not _estado(compilado).get("cards"), "se rederivó, pero además quedó residuo"


def test_una_busqueda_NUEVA_reemplaza_los_ids_sin_mezclar(mundo):
    """INVARIANTE 3. Si el turno SÍ busca, manda su búsqueda: ni unión ni mezcla con la
    anterior. Es el guard que impide que «continuidad» degenere en acumulación."""
    cliente, llm, _, compilado, catalogo = mundo

    r1 = _post(cliente, llm, "Busco en La Floresta", territorial=True)
    assert [c["id"] for c in r1.json()["results"]] == ["ee9ff315"]

    catalogo[:] = ["b1810dd2"]          # la nueva búsqueda encuentra otra cosa
    r2 = _post(cliente, llm, "Ahora en La Carolina", territorial=True)
    ids = [c["id"] for c in r2.json()["results"]]

    assert ids == ["b1810dd2"], f"la búsqueda nueva no reemplazó: {ids}"
    assert "ee9ff315" not in ids, "se mezclaron los ids del turno anterior"


def test_descartadas_tambien_se_limpia(mundo):
    cliente, llm, _, compilado, catalogo = mundo
    _post(cliente, llm, "Busco arriendo en La Floresta", territorial=True)
    _post(cliente, llm, "gracias", territorial=False)
    assert not _estado(compilado).get("descartadas")


# ══ 2 · LA AUDITORÍA VE EXACTAMENTE LO QUE SALE POR HTTP ═════════════════════

def test_auditar_prosa_recibe_el_mismo_panel_que_sale_por_HTTP(mundo):
    """INVARIANTE 4. Si divergen, el verificador de prosa mide un panel que la persona nunca
    vio — y su veredicto deja de decir algo sobre el turno servido."""
    cliente, llm, auditados, _, catalogo = mundo

    r1 = _post(cliente, llm, "Busco arriendo en La Floresta", territorial=True)
    assert auditados and auditados[-1]["valores"]["cards"] == r1.json()["results"]

    r2 = _post(cliente, llm, "gracias", territorial=False)
    assert auditados[-1]["valores"]["cards"] == r2.json()["results"]


# ══ 3 · stream=true CONSERVA su comportamiento ═══════════════════════════════

def test_el_camino_de_streaming_no_cambia(mundo):
    """El camino que usa la gente: mismo panel en la vista, mismo canal limpio."""
    cliente, llm, _, compilado, catalogo = mundo
    sesion = "sesion-stream"

    r1 = _post(cliente, llm, "Busco arriendo en La Floresta", True, stream=True, sesion=sesion)
    assert r1.status_code == 200 and "ee9ff315" in r1.text
    assert _estado(compilado, sesion)["cards"]

    r2 = _post(cliente, llm, "gracias", False, stream=True, sesion=sesion)
    assert r2.status_code == 200
    assert '"panel"' in r2.text
    assert not _estado(compilado, sesion).get("cards"), "el canal quedó heredado en el stream"


# ══ 4 · LO QUE SÍ TIENE CONTINUIDAD ══════════════════════════════════════════

def test_messages_y_preferencias_conservan_continuidad(mundo):
    """Reiniciar el panel no puede llevarse por delante el hilo ni las necesidades
    declaradas: son continuidad deliberada, no residuo."""
    cliente, llm, _, compilado, catalogo = mundo

    _post(cliente, llm, "Busco arriendo en La Floresta", territorial=True)
    v1 = _estado(compilado)
    assert v1.get("preferencias") == {"operacion": "arriendo"}
    n1 = len(v1["messages"])

    _post(cliente, llm, "gracias", territorial=False)
    v2 = _estado(compilado)
    assert v2.get("preferencias") == {"operacion": "arriendo"}, "se perdieron las preferencias"
    assert len(v2["messages"]) > n1, "el hilo se truncó"
    assert any(getattr(m, "content", "") == "Busco arriendo en La Floresta"
               for m in v2["messages"]), "se perdió el turno anterior del hilo"


# ══ 5 · UN CHECKPOINT VIEJO CON PANEL HEREDADO SE SANEA ══════════════════════

def test_un_checkpoint_previo_contaminado_queda_saneado(mundo):
    """Los hilos que ya existen en producción pueden traer panel heredado del código viejo.
    El primer turno tras el arreglo tiene que limpiarlos, no arrastrarlos."""
    cliente, llm, _, compilado, catalogo = mundo
    sesion = "sesion-sucia"
    cfg = {"configurable": {"thread_id": sesion}}

    asyncio.run(compilado.aupdate_state(cfg, {
        "messages": [HumanMessage(content="viejo"), AIMessage(content="respuesta vieja")],
        "cards": [dict(_CARD)],
        "descartadas": [dict(_CARD)],
        "encaje_contexto": "BLOQUE VIEJO CONTAMINADO",
    }))
    assert _estado(compilado, sesion)["cards"], "el arnés no dejó el estado sucio"

    r = _post(cliente, llm, "hola", territorial=False, sesion=sesion)
    assert r.json()["results"] == []
    v = _estado(compilado, sesion)
    assert not v.get("cards") and not v.get("descartadas")
    assert not (v.get("encaje_contexto") or "")


# ══ 6 · UN SOLO CONSTRUCTOR, NO DOS SITIOS QUE RECORDAR ══════════════════════

def test_los_dos_caminos_usan_el_MISMO_constructor():
    """LA PRUEBA DE LA CAUSA, no del síntoma.

    Copiar las tres líneas al otro camino arreglaría este defecto y dejaría la bifurcación
    intacta para el siguiente. Se fija que exista UN constructor y que ambos caminos lo usen:
    así una clave nueva sólo se puede olvidar en un sitio, y ese sitio tiene pruebas.
    """
    import ast
    import inspect

    fuente = inspect.getsource(chat_mod)
    arbol = ast.parse(fuente)
    nombres = {n.name for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef)}
    assert "_estado_inicial_del_turno" in nombres, "no existe el constructor compartido"

    for fn in ("_stream_agent", "chat"):
        nodo = next(n for n in ast.walk(arbol)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn)
        llamadas = {c.func.id for c in ast.walk(nodo)
                    if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        assert "_estado_inicial_del_turno" in llamadas, (
            f"{fn} no usa el constructor compartido")


def test_el_constructor_reinicia_los_cinco_canales_y_no_toca_los_demas():
    inicial = chat_mod._estado_inicial_del_turno("hola")
    assert inicial["cards"] == []
    assert inicial["descartadas"] == []
    assert inicial["encaje_contexto"] == ""
    assert inicial["spatial_context"] == {}
    assert inicial["sql_results"] == []
    assert [m.content for m in inicial["messages"]] == ["hola"]
    # continuidad deliberada: NO se siembran
    assert "preferencias" not in inicial
    assert "preferencias_turno" not in inicial
