"""E2.2 · cierre — el turno REAL decide a través de `DecisionContextV0`.

Las pruebas de autoridad anteriores demuestran que `proyectar_cards` obedece al objeto.
Estas demuestran algo distinto y que faltaba: que el runtime **construye ese objeto** y
proyecta a través de él, en vez de tener el contrato tipado por un lado y la decisión
funcional por otro.

Sin esto tendríamos dos cores, y E2.3 colgaría evidencia de un objeto que nadie consume.
"""

import asyncio
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.contracts.decision_v0 import DecisionContextV0
from app.decision import assembler
from app.decision.context import SessionIdAusente


def _row(rid, **over):
    row = {
        "id": rid, "direccion": f"Dir {rid}", "tipo_activo": "Departamento",
        "operacion": "ARRIENDO", "precio": 380, "imagen_url": None,
        "caminabilidad": 95, "caminabilidad_fuente": "osm", "ruido": "BAJO",
        "vegetacion": 42, "lat": -0.18, "lon": -78.48,
        "caracteristicas": {"num_dormitorios": 2, "acepta_mascotas": True},
        "servicios_cercanos": "🌳 Parque a ~300 m",
        "conectividad": "🚇 Metro a ~500 m (7 min a pie)",
    }
    row.update(over)
    return row


def _turno(ids):
    return [
        HumanMessage(content="consulta"),
        ToolMessage(content=json.dumps({"assets": [{"id": i} for i in ids]}),
                    name="tool_search_nearby_assets", tool_call_id="t1"),
        AIMessage(content="Encontré algunas opciones."),
    ]


PREFS = {"operacion": "arriendo", "tipo_inmueble": "departamento",
         "presupuesto_max": 700, "caminable": True, "acepta_mascotas": True}


def _panel(monkeypatch, ids, rows, prefs=PREFS, session_id="s-real"):
    async def fake_fetch(_ids):
        return (rows, {})

    monkeypatch.setattr(assembler, "_fetch_cards_rows", fake_fetch)
    return asyncio.run(
        assembler.construir_panel(_turno(ids), session_id=session_id, preferencias=prefs)
    )


# ── el runtime construye el objeto y proyecta a través de él ────────────────────


def test_el_panel_construye_decision_contexts_reales(monkeypatch):
    """Se espía el builder: si el turno no lo llama, el contrato seguiría siendo
    decorativo."""
    creados = []
    original = assembler.assemble_decision_context_v0

    def espia(**kw):
        d = original(**kw)
        creados.append(d)
        return d

    monkeypatch.setattr(assembler, "assemble_decision_context_v0", espia)
    _panel(monkeypatch, ["a", "b"], [_row("a", precio=300), _row("b", precio=690)])

    assert creados, "el turno no construyó ningún DecisionContextV0"
    assert all(isinstance(d, DecisionContextV0) for d in creados)
    assert {d.buyer.buyer_id for d in creados} == {"session:s-real"}


def test_todas_las_decisiones_del_turno_comparten_el_mismo_ranking(monkeypatch):
    """Es la decisión DEL TURNO, no una opinión por tarjeta. Si divergieran, la card que
    se proyectara primero decidiría por las demás."""
    creados = []
    original = assembler.assemble_decision_context_v0
    monkeypatch.setattr(
        assembler, "assemble_decision_context_v0",
        lambda **kw: creados.append(original(**kw)) or creados[-1],
    )
    _panel(monkeypatch, ["a", "b", "c"],
           [_row("a", precio=300), _row("b", precio=690), _row("c", precio=500)])

    rankings = {tuple(e.property_id for e in d.ranking) for d in creados}
    assert len(rankings) == 1, f"decisiones con rankings distintos: {rankings}"


def test_el_orden_visible_es_el_del_ranking_del_contrato(monkeypatch):
    """El eslabón que cierra la cadena: contrato → proyección → lo que la persona ve."""
    creados = []
    original = assembler.assemble_decision_context_v0
    monkeypatch.setattr(
        assembler, "assemble_decision_context_v0",
        lambda **kw: creados.append(original(**kw)) or creados[-1],
    )
    panel = _panel(monkeypatch, ["a", "b", "c"],
                   [_row("a", precio=300), _row("b", precio=690), _row("c", precio=500)])

    del_contrato = [e.property_id for e in creados[0].ranking]
    visibles = [c["id"] for c in panel["cards"]]
    posicion = {pid: i for i, pid in enumerate(del_contrato)}
    assert visibles == sorted(visibles, key=lambda i: posicion[i])


def test_la_reconstruccion_pasa_por_la_misma_autoridad(monkeypatch):
    """`build_result_cards` —el camino de fallback y del historial— no tiene una ruta
    propia: delega en el mismo panel. Dos caminos funcionales serían justo lo que la
    inversión vino a eliminar."""
    rows = [_row("a", precio=300), _row("b", precio=690)]

    async def fake_fetch(_ids):
        return (rows, {})

    monkeypatch.setattr(assembler, "_fetch_cards_rows", fake_fetch)
    cards = asyncio.run(
        assembler.build_result_cards(_turno(["a", "b"]), session_id="s-real", preferencias=PREFS)
    )
    panel = _panel(monkeypatch, ["a", "b"], rows)
    assert [c["id"] for c in cards] == [c["id"] for c in panel["cards"]]


# ── la identidad de ejecución no se inventa ─────────────────────────────────────


@pytest.mark.parametrize("malo", [None, "", "   "])
def test_sin_session_id_el_turno_no_fabrica_una_identidad(monkeypatch, malo):
    """`session:unknown`, un UUID nuevo o cualquier relleno producirían un
    `DecisionContextV0` que valida y no corresponde a nadie."""
    with pytest.raises(SessionIdAusente):
        _panel(monkeypatch, ["a"], [_row("a")], session_id=malo)


def test_la_violacion_de_integridad_no_se_degrada_a_legacy():
    """El `except Exception` de `encaje_node` es best-effort para fallos OPERACIONALES.
    Estas tres no: si se tragaran, el turno seguiría por el camino viejo y la condición
    que habría hecho falso el DecisionContext quedaría invisible — el modo de fallo que
    F0 se pasó cerrando."""
    import ast
    import inspect
    import pathlib

    import app.agent.graph as g

    fuente = pathlib.Path(g.__file__).read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    nodo = next(
        n for n in ast.walk(arbol)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "encaje_node"
    )
    manejadores = [h for t in ast.walk(nodo) if isinstance(t, ast.Try) for h in t.handlers]
    reraise = [
        h for h in manejadores
        if any(isinstance(s, ast.Raise) and s.exc is None for s in h.body)
    ]
    assert reraise, "encaje_node no re-lanza ninguna excepción: todo se degrada en silencio"
    # Y el manejador que re-lanza va ANTES del genérico, o nunca se alcanzaría.
    generico = [
        h for h in manejadores
        if isinstance(h.type, ast.Name) and h.type.id == "Exception"
    ]
    assert manejadores.index(reraise[0]) < manejadores.index(generico[0])


# ── determinismo del turno ──────────────────────────────────────────────────────


def test_mismo_input_y_mismo_session_id_dan_la_misma_decision(monkeypatch):
    """Salvo lo inyectado como volátil: `created_at` y el ámbito se congelan para que la
    comparación sea del contenido y no del reloj ni del generador de ids."""
    monkeypatch.setattr(assembler, "_ahora_utc", lambda: __import__("datetime").datetime(
        2026, 8, 25, 12, 0, 0, tzinfo=__import__("datetime").timezone.utc))
    monkeypatch.setattr(assembler, "_nuevo_scope_id", lambda: "scope-fijo")

    creados = []
    original = assembler.assemble_decision_context_v0
    monkeypatch.setattr(
        assembler, "assemble_decision_context_v0",
        lambda **kw: creados.append(original(**kw)) or creados[-1],
    )
    rows = [_row("a", precio=300), _row("b", precio=690)]
    _panel(monkeypatch, ["a", "b"], rows)
    primera = [d.model_dump(mode="json") for d in creados]

    creados.clear()
    _panel(monkeypatch, ["a", "b"], rows)
    assert [d.model_dump(mode="json") for d in creados] == primera


def _espiar(monkeypatch, creados):
    original = assembler.assemble_decision_context_v0
    monkeypatch.setattr(
        assembler, "assemble_decision_context_v0",
        lambda **kw: creados.append(original(**kw)) or creados[-1],
    )


def test_cada_candidato_del_turno_tiene_su_propia_identidad(monkeypatch):
    creados = []
    _espiar(monkeypatch, creados)
    _panel(monkeypatch, ["a", "b"], [_row("a", precio=300), _row("b", precio=690)])
    ids = [d.decision_id for d in creados]
    assert len(set(ids)) == len(ids), "dos candidatos compartieron decision_id"


def test_dos_turnos_sobre_la_misma_propiedad_no_comparten_identidad(monkeypatch):
    """EL DEFECTO QUE ESTO CIERRA. Con `decision_id = session:property`, la misma
    propiedad en la misma sesión recibía la misma identidad en turnos distintos —aunque
    cambiaran preferencias, ranking o evidencia—, y E2.3 va a colgar afirmaciones de esa
    identidad. Dos decisiones distintas no pueden ser una sola.
    """
    rows = [_row("a", precio=300)]

    primero = []
    _espiar(monkeypatch, primero)
    _panel(monkeypatch, ["a"], rows, prefs=PREFS)

    segundo = []
    _espiar(monkeypatch, segundo)
    _panel(monkeypatch, ["a"], rows, prefs={**PREFS, "presupuesto_max": 2000})

    assert primero[0].decision_id != segundo[0].decision_id, (
        "la misma propiedad en la misma sesión reusó decision_id entre turnos"
    )
    assert primero[0].buyer.buyer_id == segundo[0].buyer.buyer_id, (
        "la SESIÓN sí es la misma: lo que cambia es la instancia de decisión"
    )


def test_todo_el_panel_comparte_ambito_e_instante(monkeypatch):
    """Las decisiones de un panel son el MISMO evento lógico."""
    creados = []
    _espiar(monkeypatch, creados)
    _panel(monkeypatch, ["a", "b", "c"],
           [_row("a", precio=300), _row("b", precio=690), _row("c", precio=500)])

    ambitos = {d.decision_id.rsplit(":", 1)[0] for d in creados}
    assert len(ambitos) == 1, f"un mismo panel produjo varios ámbitos: {ambitos}"
    assert len({d.created_at for d in creados}) == 1, (
        "las decisiones del mismo panel llevan instantes distintos: no son el mismo evento"
    )


# ── nada de identidad persistente ───────────────────────────────────────────────


def test_no_se_introduce_buyer_store_ni_identidad_persistente(monkeypatch):
    """El puente es la EJECUCIÓN conversacional, no el comprador. F3 lo sustituye."""
    creados = []
    original = assembler.assemble_decision_context_v0
    monkeypatch.setattr(
        assembler, "assemble_decision_context_v0",
        lambda **kw: creados.append(original(**kw)) or creados[-1],
    )
    _panel(monkeypatch, ["a"], [_row("a")])
    d = creados[0]
    assert d.buyer.buyer_id.startswith("session:")
    assert d.buyer.context_revision is None, "no hay historial de comprador que citar"
