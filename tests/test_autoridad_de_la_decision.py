"""E2.2 · segundo subpaso — QUIÉN MANDA.

Las 40 pruebas de caracterización demuestran que el panel produce lo mismo que antes. No
demuestran POR QUÉ: hoy la presentación y el motor coinciden, pero coincidir no es
obedecer. Dos sitios calculando lo mismo divergen en cuanto uno cambia, y el que se ve es
el que gana.

Estas pruebas separan las dos cosas. Fuerzan a la decisión a decir algo que la
presentación, por su cuenta, habría calculado distinto — y exigen que gane la decisión.
Si alguien volviera a poner un `sort` o una comparación de precio en la capa visual, la
paridad seguiría verde y esto se caería.
"""

import asyncio
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.contracts.common_v0 import RankingEntryV0
from app.decision import assembler
from app.decision.context import PROVIDER_ID_LOCAL

# ── Mismo inventario que el oráculo, para que la comparación sea legítima ────────


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


def _panel(monkeypatch, ids, rows, prefs=PREFS):
    async def fake_fetch(_ids):
        return (rows, {})

    monkeypatch.setattr(assembler, "_fetch_cards_rows", fake_fetch)
    return asyncio.run(assembler.construir_panel(_turno(ids), preferencias=prefs))


# ── Autoridad 1 · el orden lo decide el core, la tarjeta lo sigue ───────────────


def test_las_cards_siguen_al_ranking_aunque_contradiga_el_orden_de_llegada(monkeypatch):
    """LA PRUEBA CENTRAL DEL SUBPASO.

        rows      [A, B]
        ranking   [B, A]     ← el core decide al revés
        cards     [B, A]     ← y la presentación obedece

    Se fuerza un ranking invertido para que el resultado NO pueda salir por casualidad:
    si las tarjetas se ordenaran solas, `ordenar_candidatos` las dejaría [A, B].
    """
    rows = [_row("A", precio=300), _row("B", precio=690)]

    def ranking_invertido(cards, *, prioritario=None, score_version=None):
        al_reves = sorted(cards, key=lambda c: c["id"], reverse=True)
        return tuple(
            RankingEntryV0(provider_id=PROVIDER_ID_LOCAL, property_id=c["id"], rank=i)
            for i, c in enumerate(al_reves, start=1)
        )

    monkeypatch.setattr(assembler, "decidir_ranking", ranking_invertido)
    panel = _panel(monkeypatch, ["A", "B"], rows)
    assert [c["id"] for c in panel["cards"]] == ["B", "A"]


def test_sin_el_ranking_forzado_el_orden_seria_otro(monkeypatch):
    """El contraste que hace válida la prueba anterior: sin forzar nada, el core decide
    [A, B]. Sin esto, "obedece" y "coincide" seguirían siendo indistinguibles."""
    rows = [_row("A", precio=300), _row("B", precio=690)]
    panel = _panel(monkeypatch, ["A", "B"], rows)
    assert [c["id"] for c in panel["cards"]] == ["A", "B"]


def test_una_tarjeta_no_puede_aparecer_en_una_posicion_que_el_ranking_no_le_dio(monkeypatch):
    """Las tarjetas se PROYECTAN sobre el ranking por identidad. No hay un segundo sort
    en paralelo que pueda desalinearse."""
    ids = ["a", "b", "c", "d"]
    rows = [_row(i, precio=300 + n * 50) for n, i in enumerate(ids)]

    capturado = {}
    original = assembler.decidir_ranking

    def espia(cards, **kw):
        r = original(cards, **kw)
        capturado["orden"] = [e.property_id for e in r]
        return r

    monkeypatch.setattr(assembler, "decidir_ranking", espia)
    panel = _panel(monkeypatch, ids, rows)

    visibles = [c["id"] for c in panel["cards"]]
    descartadas = [c["id"] for c in panel["descartadas"]]
    assert visibles + descartadas == capturado["orden"] or set(visibles) <= set(capturado["orden"])
    # El orden relativo de lo visible es exactamente el del ranking.
    posicion = {pid: i for i, pid in enumerate(capturado["orden"])}
    assert visibles == sorted(visibles, key=lambda i: posicion[i])


# ── Autoridad 2 · el presupuesto lo dictamina el core ───────────────────────────


def test_la_presentacion_no_puede_convertir_un_fuera_de_presupuesto_en_dentro(monkeypatch):
    """El core dice que una opción BARATA está sobre presupuesto. La presentación no
    tiene forma de contradecirlo: ya no ve el tope ni el precio.

    Es artificial a propósito — $300 contra un tope de $700 jamás saldría del cálculo
    real. Justo por eso prueba obediencia y no coincidencia.
    """
    rows = [_row("barata", precio=300), _row("otra", precio=350)]

    monkeypatch.setattr(assembler, "decidir_sobre_presupuesto",
                        lambda cards, prefs: frozenset({"barata"}))
    panel = _panel(monkeypatch, ["barata", "otra"], rows)

    assert [c["id"] for c in panel["cards"]] == ["otra"]
    assert [c["id"] for c in panel["descartadas"]] == ["barata"]


def test_la_presentacion_tampoco_puede_cortar_por_su_cuenta(monkeypatch):
    """La otra dirección, y la que se olvida: si el core NO la marcó, la presentación no
    puede sacarla aunque el precio le parezca alto."""
    rows = [_row("cara", precio=5000), _row("normal", precio=300)]

    monkeypatch.setattr(assembler, "decidir_sobre_presupuesto",
                        lambda cards, prefs: frozenset())
    panel = _panel(monkeypatch, ["cara", "normal"], rows)

    assert "cara" in [c["id"] for c in panel["cards"]], (
        "la capa visual volvió a decidir sobre presupuesto por su cuenta"
    )


def test_el_corte_ya_no_ve_el_tope_ni_el_precio():
    """Estructural: `_recortar_grid` no recibe preferencias, así que no PUEDE recalcular
    el presupuesto aunque alguien lo intentara. Mover la decisión de sitio no basta; hay
    que quitarle a la presentación los insumos para volver a tomarla."""
    import inspect

    firma = inspect.signature(assembler._recortar_grid)
    assert "preferencias" not in firma.parameters
    assert "sobre_presupuesto" in firma.parameters

    fuente = inspect.getsource(assembler._recortar_grid)
    assert "presupuesto_max" not in fuente
    assert "_MARGEN_PRESUPUESTO" not in fuente


def test_el_assembler_ya_no_ordena_por_su_cuenta():
    """`ordenar_candidatos` sigue siendo el criterio, pero se invoca desde el core.

    Se comprueba sobre el AST y no sobre el texto: el nombre aparece legítimamente en el
    comentario que explica por qué ya no se llama, y un `not in fuente` daría un falso
    positivo. Es el mismo error que ya se cometió dos veces en F1 y una en E2.1 — buscar
    la AUSENCIA de un nombre en prosa no responde una pregunta estructural.
    """
    import ast
    import inspect
    import textwrap

    arbol = ast.parse(textwrap.dedent(inspect.getsource(assembler.construir_panel)))
    llamadas = {
        n.func.id for n in ast.walk(arbol)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "ordenar_candidatos" not in llamadas, (
        "construir_panel volvió a ordenar por su cuenta en vez de proyectar el ranking"
    )
    assert "decidir_ranking" in llamadas
    assert "decidir_sobre_presupuesto" in llamadas


# ── La decisión y lo que se ve no pueden divergir ───────────────────────────────


def test_el_ranking_lleva_la_identidad_estable_de_e1_3(monkeypatch):
    rows = [_row("x", precio=300)]
    cards = [assembler._card_from_row(r, PREFS) for r in rows]
    ranking = assembler.decidir_ranking(cards)
    assert ranking[0].identidad_externa == (PROVIDER_ID_LOCAL, "x")
    assert ranking[0].rank == 1


def test_un_score_en_el_ranking_nunca_va_sin_su_version(monkeypatch):
    """`RankingEntryV0` lo exige, y aquí se comprueba contra datos reales del panel."""
    rows = [_row("x", precio=300), _row("y", precio=690)]
    cards = [assembler._card_from_row(r, PREFS) for r in rows]
    for e in assembler.decidir_ranking(cards):
        if e.score is not None:
            assert e.score_version, f"{e.property_id} lleva score sin score_version"


def test_sin_preferencias_el_ranking_no_inventa_scores(monkeypatch):
    """Sin necesidades declaradas no hay nada que puntuar: `score=None` y, por tanto,
    tampoco `score_version`."""
    rows = [_row("a"), _row("b")]
    cards = [assembler._card_from_row(r, None) for r in rows]
    for e in assembler.decidir_ranking(cards):
        assert e.score is None and e.score_version is None
