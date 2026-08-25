"""E2.4 — el verificador de prosa proyectado al contrato, sin cambiar qué es una violación.

La prosa que se audita aquí es la MISMA del informe de la batalla Hiinmo (2026-07-31): se
reutilizan sus fixtures a propósito, para que el mapeo se pruebe contra hallazgos reales del
motor y no contra diccionarios armados para que el test pase.

Lo que E2.4 NO cambia, y estos tests lo fijan: qué cuenta como violación, con qué gravedad,
y que la auditoría siga siendo post-respuesta y sin bloqueo.
"""

import ast
import inspect
import pathlib

import pytest

from app.contracts.decision_v0 import ExplanationV0, VerificationStatus
from app.decision.verify import GravedadDesconocida, auditar_explicacion
from app.verificacion_prosa import ALTA, MEDIA, verificar_prosa

_PREFS = {"operacion": "arriendo", "tipo_inmueble": "departamento", "presupuesto_max": 700}


def _card(cid, precio, encaje):
    return {
        "id": cid, "direccion": f"Calle {cid}", "tipo_activo": "Departamento",
        "operacion": "ARRIENDO", "precio": precio, "encaje": encaje,
        "caracteristicas": {"num_dormitorios": 2}, "lat": -0.18, "lon": -78.48,
    }


_PANEL = [_card("d290", 290, 92), _card("d380", 380, 88),
          _card("d550", 550, 80), _card("d710", 710, 71)]

# Prosa real de cada caso. La honesta también, porque un mapeo que marcara WARNING a una
# respuesta correcta sería tan inútil como uno que no marcara nada.
LIMPIA = "Las 2 primeras entran en tu tope de $700."
MEDIA_ORDEN = ("Te los ordeno por encaje:\n"
               "1. Calle d710\n2. Calle d550\n3. Calle d380\n4. Calle d290")
ALTA_CIFRA = "También hay uno de $650 en la misma cuadra."
ALTA_Y_MEDIA = ("Te los ordeno por encaje:\n"
                "1. Calle d710\n2. Calle d550\n3. Calle d380\n4. Calle d290\n"
                "También hay uno de $650 en la misma cuadra.")


# ── Los tres mapeos ────────────────────────────────────────────────────────────────


def test_cero_hallazgos_es_passed():
    explicacion, hallazgos = auditar_explicacion(LIMPIA, _PANEL, _PREFS)
    assert hallazgos == []
    assert explicacion.verification_status is VerificationStatus.PASSED


def test_solo_gravedad_media_es_warning():
    explicacion, hallazgos = auditar_explicacion(MEDIA_ORDEN, _PANEL, _PREFS)
    assert [h["gravedad"] for h in hallazgos] == [MEDIA]
    assert explicacion.verification_status is VerificationStatus.WARNING


def test_cualquier_gravedad_alta_es_failed():
    explicacion, hallazgos = auditar_explicacion(ALTA_CIFRA, _PANEL, _PREFS)
    assert [h["gravedad"] for h in hallazgos] == [ALTA]
    assert explicacion.verification_status is VerificationStatus.FAILED


def test_una_alta_manda_sobre_las_medias():
    """El caso que importa: mezclar no promedia. Una grave con varias leves sigue siendo
    FAILED — si `media` ganara por mayoría, el hallazgo peor quedaría reportado como leve."""
    explicacion, hallazgos = auditar_explicacion(ALTA_Y_MEDIA, _PANEL, _PREFS)
    gravedades = {h["gravedad"] for h in hallazgos}
    assert gravedades == {ALTA, MEDIA}, f"el fixture no produjo ambas: {gravedades}"
    assert explicacion.verification_status is VerificationStatus.FAILED


# ── La arquitectura ────────────────────────────────────────────────────────────────


def _importa(modulo) -> set[str]:
    """Módulos importados, por AST. Buscar el nombre en el texto daría falsos positivos con
    los docstrings —ya pasó tres veces en esta fase—."""
    arbol = ast.parse(pathlib.Path(inspect.getfile(modulo)).read_text(encoding="utf-8"))
    fuera: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.module:
            fuera.add(nodo.module)
        elif isinstance(nodo, ast.Import):
            fuera.update(a.name for a in nodo.names)
    return fuera


def test_el_verificador_del_core_no_conoce_el_transporte():
    """Si `decision.verify` importara el router o FastAPI, la dependencia apuntaría al revés
    y el core volvería a depender de la capa que F2 vino a dejar tonta."""
    from app.decision import verify

    for modulo in _importa(verify):
        assert not modulo.startswith("app.routers"), f"el core importa el router: {modulo}"
        assert not modulo.startswith("fastapi"), f"el core importa FastAPI: {modulo}"


def test_el_router_consume_el_core_y_no_reimplementa_el_mapeo():
    """El router puede seguir llamando a `registrar` —la observabilidad es del módulo
    legacy—, pero NO puede volver a leer gravedades por su cuenta: ahí es donde una regla
    de decisión se filtra a la capa de transporte."""
    import app.routers.chat as chat

    importados = _importa(chat)
    assert "app.decision.verify" in importados, "el router no pasa por el Decision Core"

    fuente = pathlib.Path(inspect.getfile(chat)).read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    llamadas = {
        n.func.id for n in ast.walk(arbol)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "verificar_prosa" not in llamadas, (
        "el router sigue llamando al verificador legacy directo: la costura no está en medio"
    )
    assert "auditar_explicacion" in llamadas


def test_el_core_reutiliza_la_logica_legacy_en_vez_de_copiarla():
    from app.decision import verify

    assert "app.verificacion_prosa" in _importa(verify)


# ── Los hallazgos legacy salen intactos ────────────────────────────────────────────


@pytest.mark.parametrize("reply", [LIMPIA, MEDIA_ORDEN, ALTA_CIFRA, ALTA_Y_MEDIA])
def test_la_costura_no_altera_ni_un_hallazgo(reply):
    """Mismo objeto, mismo orden, mismos códigos y evidencias. Si la costura filtrara o
    reordenara, `registrar` contaría distinto y los evals señalarían otra frase."""
    _, por_el_core = auditar_explicacion(reply, _PANEL, _PREFS)
    assert por_el_core == verificar_prosa(reply, _PANEL, _PREFS)


def test_el_estado_no_reemplaza_a_los_hallazgos():
    """Un estado sin hallazgos diría "algo falló" sin decir qué: la evidencia literal es lo
    que hace accionable el informe."""
    _, hallazgos = auditar_explicacion(ALTA_CIFRA, _PANEL, _PREFS)
    assert hallazgos[0]["evidencia"] and hallazgos[0]["detalle"]
    assert hallazgos[0]["codigo"] == "cifra_sin_procedencia"


# ── Nada se normaliza en silencio ──────────────────────────────────────────────────


def test_una_gravedad_nueva_falla_ruidosamente(monkeypatch):
    """Agregar una gravedad en `verificacion_prosa.py` sin decidir su proyección tiene que
    doler aquí. Mandarla a WARNING "por si acaso" dejaría una violación grave reportada como
    leve para siempre."""
    from app.decision import verify

    monkeypatch.setattr(
        verify, "verificar_prosa",
        lambda *a, **k: [{"codigo": "x", "gravedad": "critica", "detalle": "", "evidencia": ""}],
    )
    with pytest.raises(GravedadDesconocida, match="critica"):
        verify.auditar_explicacion("lo que sea", _PANEL, _PREFS)


# ── Audit-only: no toca el turno ───────────────────────────────────────────────────


def test_la_auditoria_no_modifica_la_respuesta_ni_las_tarjetas():
    """Post-respuesta y en observación. El día que se active el bloqueo será una decisión
    con una cifra detrás, no un efecto colateral de esta costura."""
    reply, panel = ALTA_CIFRA, [dict(c) for c in _PANEL]
    explicacion, _ = auditar_explicacion(reply, panel, dict(_PREFS))
    assert explicacion.verification_status is VerificationStatus.FAILED
    assert reply == ALTA_CIFRA, "la auditoría reescribió la prosa"
    assert panel == _PANEL, "la auditoría mutó las tarjetas que ve la persona"


def test_el_router_no_bloquea_ni_reescribe_por_un_veredicto_failed():
    """`_auditar_prosa` devuelve None y su cuerpo no tiene `return` de valor ni `raise`: no
    hay forma de que el veredicto cambie lo que se le entrega a la persona."""
    import app.routers.chat as chat

    arbol = ast.parse(pathlib.Path(inspect.getfile(chat)).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.FunctionDef) and n.name == "_auditar_prosa")
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Return) and n.value is not None]
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Raise)]


# ── El contrato acepta la explicación, sin persistirla ─────────────────────────────


def test_un_decision_context_puede_recibir_la_explicacion_verificada():
    """Demuestra que la pieza encaja. NO se persiste: guardar el objeto exigiría meter los
    DecisionContext en el checkpointer o construir un store, y eso es F6. Infraestructura
    nueva solo para poder decir que llenamos un campo es justo lo que no se hace aquí."""
    from datetime import datetime, timezone

    from app.decision.context import assemble_decision_context_v0

    fila = {"id": "11111111-2222-3333-4444-555555555555", "tipo_activo": "Departamento",
            "operacion": "ARRIENDO", "precio": 380, "lat": -0.1807, "lon": -78.4867,
            "caracteristicas": {}}
    decision = assemble_decision_context_v0(
        row=fila, preferencias=_PREFS, encaje=None, session_id="s-e24",
        decision_id="scope:1", created_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
    )
    assert decision.explanation is None, "se construye ANTES de que exista prosa"

    explicacion, _ = auditar_explicacion(ALTA_CIFRA, _PANEL, _PREFS)
    con_explicacion = decision.model_copy(update={"explanation": explicacion})

    assert isinstance(con_explicacion.explanation, ExplanationV0)
    assert con_explicacion.explanation.verification_status is VerificationStatus.FAILED
    assert decision.explanation is None, "el original es inmutable: model_copy no lo tocó"
