"""G20-B1-R3 · AUTHORITY CONTRACT AVAILABILITY · el contrato no puede llegar vacío.

QUÉ CIERRA. R1 arregló el tipo; R2 ligó cada distancia a la entidad visible. Las dos dan por
supuesto que el contrato territorial LLEGA. Esta unidad prueba que llega **siempre que haya
riesgo territorial**, y que cuando no puede llegar, el turno no continúa sin autoridad.

Absorbe dos gates que hasta hoy vivían sueltos:

  G20-B1-NOCARDS-01      con cero tarjetas, `bloque_autoritativo` devolvía "" y la prohibición
                         NO se emitía. Un panel vacío apagaba el gobierno territorial entero.
  G20-B1-CONTAINMENT-01  `bloque_autoritativo` se llamaba FUERA del `try` de `encaje_node`, así
                         que un fallo de formato mataba el turno (es lo que produjo el canary
                         VOID del 2026-08-30). Y moverlo dentro del `try` sin más habría sido
                         lo contrario: degradación fail-open.

LA PRECISIÓN QUE GOBIERNA LA UNIDAD, y que no hay que perder de vista: «fail-closed» aquí
describe **el canal**, no la prosa. R3 garantiza que el modelo RECIBE la restricción cuando hay
riesgo territorial. NO garantiza que la obedezca — eso exigiría una barrera pre-`yield`, que
G20-B.0 identificó como la única superficie capaz de impedir algo de forma determinista, y
sigue DEFERRED.

    R3 asegura     →  el contrato nunca llega vacío
    R3 NO asegura  →  que la prosa lo respete

LA TABLA DE VERDAD (E = evidencia territorial del turno actual · C = tarjetas visibles):

    E no existe  · C cualquiera  →  contrato no aplicable; "" permitido
    E existe     · C > 0         →  contrato completo de R2
    E existe     · C = 0         →  contrato SIN entidades ni distancias, CON prohibición
    E existe     · falla el enriquecido  →  fallback seguro y OBSERVABLE; nunca ""
    E existe     · falla el fallback     →  no se invoca al LLM

POR QUÉ ESTAS PRUEBAS INVOCAN LOS NODOS REALES. R1 y R2 simulaban la costura («igual que
`encaje_node`»), y para lo suyo bastaba: probaban funciones puras. Aquí lo que se prueba ES el
flujo de control del nodo —qué se captura, qué se propaga, qué se escribe en el estado y si el
modelo llega a invocarse—, así que simularlo sería probar la simulación. Se extraen los
callables reales del `StateGraph`.

FUERA DE ALCANCE: `G20-B1-CANARY-HARNESS-01`, la barrera pre-`yield`, deploy, canary y `tools.py`.
"""
import asyncio
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent import graph as graph_mod
from app.decision import assembler

ARTEFACTO = (Path(__file__).parent / "fixtures"
             / "g20_b1_canary_void_20260830T204022Z.json")

CONSULTA = "La Floresta, Quito, Ecuador"
ANCLA = {"latitude": -0.20934, "longitude": -78.484919, "geometry_type": "point"}
CFG = {"configurable": {"thread_id": "s-g20b1r3"}}
PREFS = {"operacion": "arriendo", "presupuesto_max": 900}


# ── el LLM, falseado antes de construir el grafo ────────────────────────────────

class _LLMFalso:
    """Sustituye a ChatAnthropic. Registra si lo invocaron: eso es la aserción de la fila 5."""

    def __init__(self, **_kw):
        self.invocaciones = []

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, messages):
        self.invocaciones.append(messages)
        return AIMessage(content="prosa del modelo")


def _grafo(monkeypatch):
    """Construye el grafo REAL con el LLM falseado. Devuelve (nodos, llm_falso)."""
    creados = []

    class _Fabrica(_LLMFalso):
        def __init__(self, **kw):
            super().__init__(**kw)
            creados.append(self)

    monkeypatch.setattr(graph_mod, "ChatAnthropic", _Fabrica)
    g = graph_mod._build_graph()

    def nodo(nombre):
        r = g.nodes[nombre].runnable
        return getattr(r, "afunc", None) or r.func

    return nodo, creados[0]


def _encaje(monkeypatch, messages, **extra):
    nodo, _ = _grafo(monkeypatch)
    estado = {"messages": messages, "preferencias": PREFS,
              "preferencias_turno": sum(1 for m in messages if isinstance(m, HumanMessage)),
              **extra}
    return asyncio.run(nodo("encaje")(estado, CFG))


def _filas(rows):
    async def _fake(_ids):
        return (rows, {})
    return _fake


# ── payloads ────────────────────────────────────────────────────────────────────

def _artefacto():
    with open(ARTEFACTO, encoding="utf-8") as f:
        return json.load(f)


def _mensajes_reales():
    fuera = []
    for m in _artefacto()["messages"]:
        if m["type"] == "human":
            fuera.append(HumanMessage(content=m["content"]))
        elif m["type"] == "ai":
            fuera.append(AIMessage(content=m["content"] or "",
                                   tool_calls=m.get("tool_calls") or []))
        else:
            fuera.append(ToolMessage(content=m["content"], name=m["name"],
                                     tool_call_id=m["tool_call_id"]))
    return fuera


def _assets_reales():
    for m in _artefacto()["messages"]:
        if m.get("name") == "tool_search_nearby_assets":
            return json.loads(m["content"])["assets"]
    raise AssertionError("el artefacto perdió el ToolMessage de búsqueda")


def _rows_reales():
    return [{
        "id": a["id"], "direccion": a["direccion_estandarizada"],
        "tipo_activo": a["tipo_activo"], "operacion": a["operacion"],
        "precio": float(a["precio"]), "imagen_url": None,
        "caminabilidad": 90, "caminabilidad_fuente": "osm", "ruido": "BAJO",
        "vegetacion": 40, "lat": -0.2093, "lon": -78.4849,
        "caracteristicas": {"num_dormitorios": 2},
        "servicios_cercanos": "🌳 Parque a ~300 m",
        "conectividad": "🚇 Metro a ~500 m (7 min a pie)",
    } for a in _assets_reales()]


def _geocode(lat=ANCLA["latitude"], lon=ANCLA["longitude"], consulta=CONSULTA):
    return ToolMessage(name="tool_geocode_address", tool_call_id="tc-geo",
                       content=json.dumps({"found": True, "address_input": consulta,
                                           "latitude": lat, "longitude": lon,
                                           "geometry_type": "point"}))


def _search(assets, ancla=ANCLA):
    """Payload de `tool_search_nearby_assets`, con la MISMA forma que `_relacion_de_busqueda`."""
    cuerpo = {"assets": assets, "total": len(assets),
              "pertenencia_territorial": "unknown",
              "radius_requested_m": 1200, "radius_searched_m": 1200}
    if ancla is not None:
        cuerpo["ancla_busqueda"] = ancla
        cuerpo["relacion_recuperacion"] = "within_radius"
    if not assets:
        cuerpo["message"] = "No registered assets within 1200 m of this point."
    return ToolMessage(name="tool_search_nearby_assets", tool_call_id="tc-search",
                       content=json.dumps(cuerpo, default=str))


def _turno(*tools, texto="Busco arriendo en La Floresta"):
    return [HumanMessage(content=texto), AIMessage(content="", tool_calls=[]), *tools]


def _prohibicion_presente(texto: str) -> bool:
    return ("RELACIÓN TERRITORIAL · QUÉ PUEDES AFIRMAR" in texto
            and "pertenencia territorial: NO ESTÁ ESTABLECIDA" in texto
            and "no digas que está fuera ni que no pertenece" in texto)


# ══ FILA 3 · hay evidencia territorial y CERO tarjetas ══════════════════════════
#
# Es `NOCARDS-01`. Sin tarjetas no hay afirmaciones sobre candidatos individuales, pero el
# modelo TAMPOCO queda autorizado a convertir «búsqueda radial alrededor de La Floresta» en
# «búsqueda dentro de La Floresta».

def test_busqueda_territorial_sin_resultados_emite_la_prohibicion(monkeypatch):
    """La búsqueda no encontró nada. Cero tarjetas — y la restricción se emite igual."""
    monkeypatch.setattr(assembler, "_fetch_cards_rows", _filas([]))
    out = _encaje(monkeypatch, _turno(_geocode(), _search([])))

    ctx = out.get("encaje_contexto") or ""
    assert ctx, "cero resultados apagó el contrato entero (NOCARDS-01)"
    assert _prohibicion_presente(ctx)
    assert f"que el inmueble esté «en {CONSULTA}»" in ctx
    assert "NINGUNA distancia quedó ligada" in ctx or "no afirmes distancias" in ctx


def test_con_resultados_pero_cero_tarjetas_tras_filtros(monkeypatch):
    """La tool devolvió activos, pero el panel quedó vacío. La prohibición se mantiene, y
    NINGUNA entidad oculta se cuela para llenar el bloque (invariante 6)."""
    monkeypatch.setattr(assembler, "_fetch_cards_rows", _filas([]))
    out = _encaje(monkeypatch, _mensajes_reales())

    ctx = out.get("encaje_contexto") or ""
    assert ctx and _prohibicion_presente(ctx)
    for a in _assets_reales():
        assert a["direccion_estandarizada"] not in ctx, "se coló una entidad no mostrada"
        assert f"{float(a['distancia_metros']):g} m" not in ctx, "se coló una distancia oculta"


# ══ FILA 4 · falla el camino enriquecido ═══════════════════════════════════════
#
# Es `CONTAINMENT-01`. El fallo tiene que quedar OBSERVABLE y producir fallback — nunca "" y
# nunca matar el turno.

def test_excepcion_en_construir_panel_deja_fallback(monkeypatch, capsys):
    async def _revienta(*a, **k):
        raise RuntimeError("la base se cayó")
    monkeypatch.setattr(assembler, "construir_panel", _revienta)

    out = _encaje(monkeypatch, _mensajes_reales())
    ctx = out.get("encaje_contexto") or ""

    assert ctx, "un fallo del panel dejó al modelo sin contrato territorial"
    assert _prohibicion_presente(ctx)
    assert "[WARN]" in capsys.readouterr().out, "el fallo no quedó observable"


def test_excepcion_en_el_bloque_enriquecido_deja_fallback(monkeypatch, capsys):
    import app.encaje_contexto as enc

    def _revienta(*a, **k):
        raise ValueError("Unknown format code 'g' for object of type 'str'")
    monkeypatch.setattr(enc, "bloque_autoritativo", _revienta)
    monkeypatch.setattr(assembler, "_fetch_cards_rows", _filas(_rows_reales()))

    out = _encaje(monkeypatch, _mensajes_reales())
    ctx = out.get("encaje_contexto") or ""

    assert ctx, "la regresión del canary VOID volvería a dejar el contrato vacío"
    assert _prohibicion_presente(ctx)
    assert "[WARN]" in capsys.readouterr().out


# ══ FILA 5 · falla también el fallback → NO se invoca al modelo ════════════════

def test_si_ni_el_fallback_se_puede_construir_no_se_invoca_al_LLM(monkeypatch, capsys):
    """LA PRUEBA QUE HACE FAIL-CLOSED AL CONJUNTO.

    Sin ella, «fallback seguro» sería una promesa sin respaldo: bastaría que el fallback
    fallara para volver al mundo de antes, con el modelo escribiendo sin restricción.
    """
    import app.encaje_contexto as enc

    def _revienta(*a, **k):
        raise RuntimeError("nada se puede construir")
    monkeypatch.setattr(enc, "bloque_autoritativo", _revienta)
    monkeypatch.setattr(enc, "bloque_territorial_minimo", _revienta)
    monkeypatch.setattr(assembler, "_fetch_cards_rows", _filas(_rows_reales()))

    nodo, llm = _grafo(monkeypatch)
    msgs = _mensajes_reales()
    estado = {"messages": msgs, "preferencias": PREFS, "preferencias_turno": 1}

    out = asyncio.run(nodo("encaje")(estado, CFG))
    # marcado con el ÍNDICE DE TURNO, no con un booleano: ver el módulo de lineage
    assert out.get("contrato_faltante_turno") == 1
    assert not (out.get("encaje_contexto") or "")
    assert "[WARN]" in capsys.readouterr().out

    salida = asyncio.run(nodo("llm")({**estado, **out}))
    assert llm.invocaciones == [], "se invocó al modelo sin contrato territorial"
    respuesta = salida["messages"][0]
    assert isinstance(respuesta, AIMessage) and respuesta.content.strip()
    assert CONSULTA not in respuesta.content, "la salida controlada nombró el lugar"


# ══ EL MODELO NUNCA RECIBE EL CONTRATO VACÍO ═══════════════════════════════════

@pytest.mark.parametrize("rows", [[], "reales"])
def test_lo_que_llega_al_system_prompt_lleva_la_prohibicion(monkeypatch, rows):
    """No basta con que `encaje_node` retorne algo: hay que mirar lo que el modelo RECIBE.

    Se invoca `llm_node` con el estado que produjo `encaje_node` y se inspecciona el
    SystemMessage. Con y sin tarjetas.
    """
    monkeypatch.setattr(assembler, "_fetch_cards_rows",
                        _filas(_rows_reales() if rows == "reales" else []))
    nodo, llm = _grafo(monkeypatch)
    msgs = _mensajes_reales()
    estado = {"messages": msgs, "preferencias": PREFS, "preferencias_turno": 1}

    out = asyncio.run(nodo("encaje")(estado, CFG))
    asyncio.run(nodo("llm")({**estado, **out}))

    assert llm.invocaciones, "el modelo no se invocó cuando sí había contrato"
    system = llm.invocaciones[0][0]
    assert _prohibicion_presente(system.content), (
        "el modelo recibió contexto territorial requerido SIN la prohibición")


# ══ FILA 1 · el contrato no aplica ═════════════════════════════════════════════

def test_turno_sin_operacion_territorial(monkeypatch):
    """Ninguna búsqueda territorial: no hay contrato que emitir y "" es correcto."""
    monkeypatch.setattr(assembler, "_fetch_cards_rows", _filas([]))
    out = _encaje(monkeypatch, [HumanMessage(content="hola"), AIMessage(content="¿en qué zona?")])
    assert not (out.get("encaje_contexto") or "")
    assert not out.get("contrato_territorial_faltante")


def test_la_evidencia_SOLO_historica_no_activa_el_contrato(monkeypatch):
    """INVARIANTE 3. El turno N-1 buscó; el turno N no. Heredar sería gobernar la respuesta
    de hoy con la autoridad de ayer — el peor modo de fallo, y silencioso."""
    monkeypatch.setattr(assembler, "_fetch_cards_rows", _filas(_rows_reales()))
    previos = _mensajes_reales()
    actuales = [HumanMessage(content="¿y cuántos dormitorios tiene?"),
                AIMessage(content="Tiene 2.")]

    out = _encaje(monkeypatch, previos + actuales)
    ctx = out.get("encaje_contexto") or ""
    assert "RELACIÓN TERRITORIAL" not in ctx, "heredó la autoridad territorial del turno viejo"
    assert not out.get("contrato_territorial_faltante")


# ══ LABEL BINDING · invariantes 4 y 5 ══════════════════════════════════════════

def test_sin_coincidencia_geocoder_ancla_se_abstiene_sin_nombrar(monkeypatch):
    """El geocode del turno NO coincide con el ancla de la búsqueda: el topónimo pierde
    autoridad. Se emite abstención genérica y el lugar NO se nombra."""
    monkeypatch.setattr(assembler, "_fetch_cards_rows", _filas([]))
    out = _encaje(monkeypatch, _turno(_geocode(lat=-0.5), _search([])))

    ctx = out.get("encaje_contexto") or ""
    assert ctx and _prohibicion_presente(ctx)
    assert CONSULTA not in ctx, "nombró el lugar sin label binding"
    assert "NO corresponde a ningún lugar nombrado" in ctx
    assert "pertenezca a ningún barrio o sector" in ctx


# ══ FILA 2 · sin regresiones sobre R2 ══════════════════════════════════════════

def test_contrato_completo_de_R2_intacto(monkeypatch):
    monkeypatch.setattr(assembler, "_fetch_cards_rows", _filas(_rows_reales()))
    out = _encaje(monkeypatch, _mensajes_reales())
    ctx = out.get("encaje_contexto") or ""

    assert _prohibicion_presente(ctx)
    assert "Calle Alemania E12-34 y Gonzalez Suarez, Quito — 572 m" in ctx
    assert out["cards"] and out["cards"][0]["id"].startswith("ee9ff315")
    assert not out.get("contrato_territorial_faltante")


# ══ INVARIANTE 8 · lo que NO se captura ════════════════════════════════════════

def test_CancelledError_se_propaga(monkeypatch):
    """`except Exception` deja pasar `CancelledError` porque hereda de `BaseException`. Se
    fija con prueba para que un `except BaseException` futuro no entre sin que nadie lo vea:
    capturar una cancelación convertiría un turno abortado por el cliente en uno «exitoso»
    sin contrato."""
    async def _cancelado(*a, **k):
        raise asyncio.CancelledError()
    monkeypatch.setattr(assembler, "construir_panel", _cancelado)

    with pytest.raises(asyncio.CancelledError):
        _encaje(monkeypatch, _mensajes_reales())


def test_las_violaciones_de_integridad_siguen_propagandose(monkeypatch):
    """R3 no puede ablandar lo que F0 cerró: las cuatro de integridad semántica se propagan
    con su nombre, no caen al fallback."""
    from app.decision.context import SessionIdAusente

    async def _revienta(*a, **k):
        raise SessionIdAusente("sin session_id")
    monkeypatch.setattr(assembler, "construir_panel", _revienta)

    with pytest.raises(SessionIdAusente):
        _encaje(monkeypatch, _mensajes_reales())
