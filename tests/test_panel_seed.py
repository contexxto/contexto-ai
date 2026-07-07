"""Tests de panel_seed — el derivador de foco del dashboard vivo del Estratega (SPEC_Analisis_Vivo).

Fija el contrato de la directiva: vocabulario CERRADO, el backend decide el foco (no el LLM libre),
solo el Estratega la emite, y sin señal clara devuelve None (el frontend conserva el foco actual).
"""
import pytest

from app.agent.panel_seed import FOCOS, derivar_foco, derivar_panel_seed


# ── derivar_foco (puro, acento-insensible) ───────────────────────────────────
@pytest.mark.parametrize("mensaje,esperado", [
    ("¿Cómo voy con los que piden corredor?", "handoff"),
    ("¿cómo va mi handoff?", "handoff"),
    ("¿estoy cerrando?", "handoff"),
    ("¿Dónde se atasca mi embudo?", "embudo"),
    ("¿qué frena mis cierres?", "embudo"),          # 'frena' (embudo) gana a 'cierres' (handoff) por orden
    ("muéstrame el cuello de mi funnel", "embudo"),
    ("¿A quién reenganchar primero?", "reenganche"),
    ("¿tengo dormidos para reactivar?", "reenganche"),
    ("¿qué tan maduros están mis resultados?", "cohortes"),
    ("¿cuántos en vuelo?", "cohortes"),
])
def test_derivar_foco_mapea_pregunta(mensaje, esperado):
    assert derivar_foco(mensaje) == esperado


@pytest.mark.parametrize("mensaje", [
    "¿Cuál es mi mejor sistema de cartera?",   # pregunta de playbook → sin foco de dashboard
    "gracias, muy útil",
    "hola",
    "",
    None,
])
def test_derivar_foco_sin_senal_es_none(mensaje):
    # Sin señal clara → None: el frontend conserva el foco actual ('no salta sin señal').
    assert derivar_foco(mensaje) is None


def test_derivar_foco_solo_focos_del_vocabulario_cerrado():
    # Cualquier salida no-None pertenece al vocabulario CERRADO (nunca un foco inventado).
    for m in ["handoff", "embudo atascado", "reenganchar dormidos", "cohortes maduras", "xyz"]:
        f = derivar_foco(m)
        assert f is None or f in FOCOS


# ── derivar_panel_seed (contrato del turno) ──────────────────────────────────
def test_panel_seed_solo_estratega():
    # El Copiloto NUNCA dirige el dashboard (es por-lead) → None aunque el texto tenga señal.
    assert derivar_panel_seed("¿cómo va mi handoff?", modo="copiloto") is None
    ps = derivar_panel_seed("¿cómo va mi handoff?", modo="estratega")
    assert ps == {"foco": "handoff", "resalta": None, "caption": None}


def test_panel_seed_sin_senal_none():
    # Estratega pero sin señal → None (el frontend conserva el foco).
    assert derivar_panel_seed("¿cuál es mi mejor sistema de cartera?", modo="estratega") is None


def test_panel_seed_contrato_de_campos():
    # El contrato SIEMPRE trae las 3 claves (foco no-None; resalta/caption reservados para Fase B/caption).
    ps = derivar_panel_seed("¿dónde se atasca mi embudo?", modo="estratega")
    assert set(ps.keys()) == {"foco", "resalta", "caption"}
    assert ps["foco"] == "embudo" and ps["resalta"] is None and ps["caption"] is None


def test_panel_seed_no_perfila_por_clase_protegida():
    # Fair Housing por construcción: aunque el texto mencione una clase protegida, NO existe un foco
    # demográfico → o cae en un foco transaccional legítimo o en None; jamás un 'foco' de clase.
    for m in ["enfócate en las familias", "prioriza a los jóvenes", "los extranjeros de mi cartera"]:
        ps = derivar_panel_seed(m, modo="estratega")
        assert ps is None or ps["foco"] in FOCOS
