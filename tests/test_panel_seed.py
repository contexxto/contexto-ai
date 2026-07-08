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


# ── Fase C — foco 'lead' (per-interesado → puente al Copiloto) ────────────────
# 'lead' es el ÚLTIMO recurso: los focos de cartera tienen prioridad. La referencia va en 'resalta' cruda;
# el frontend la resuelve contra /mine/leads y solo muestra el puente si resuelve (sobre-extracción inofensiva).
@pytest.mark.parametrize("mensaje,ref", [
    ("cuéntame de mayra", "mayra"),
    ("y de #ba0a?", "ba0a"),                        # id corto tiene prioridad sobre la cola de texto
    ("el interesado ana@correo.com", "ana@correo.com"),  # email tiene prioridad
    ("qué pasa con Juan", "juan"),
    ("háblame de la señora Pérez", "la senora perez"),
])
def test_foco_lead_detecta_y_extrae_referencia(mensaje, ref):
    assert derivar_foco(mensaje) == "lead"
    ps = derivar_panel_seed(mensaje, modo="estratega")
    assert ps["foco"] == "lead" and ps["resalta"] == ref and ps["caption"] is None


def test_cartera_gana_a_lead():
    # Una pregunta de CARTERA nunca se lee como 'lead' aunque tenga 'de X': el foco de cartera matchea antes.
    assert derivar_foco("¿cómo va la tasa de handoff?") == "handoff"
    assert derivar_foco("¿dónde se atasca mi embudo?") == "embudo"
    # Y el playbook (sin foco de dashboard) sigue devolviendo None, no 'lead'.
    assert derivar_foco("¿cuál es mi mejor sistema de cartera?") is None


def test_lead_ref_de_clase_protegida_no_segmenta():
    # 'cuéntame de las familias' dispara foco 'lead' (transaccional: un puente), NO un foco demográfico.
    # La ref 'las familias' NO resuelve a ningún interesado en el frontend → sin puente. Sin segmentación.
    ps = derivar_panel_seed("cuéntame de las familias", modo="estratega")
    assert ps["foco"] == "lead" and ps["foco"] in FOCOS      # es el puente, no un 'foco' de clase


def test_foco_lead_conserva_nombre_multipalabra():
    # Hallazgo #2 (regresión): el greedy soltaba el nombre. Ahora la cola arranca en el PRIMER conector y
    # CONSERVA el nombre real (el frontend lo tokeniza y descarta las palabras de agregado).
    ps = derivar_panel_seed("cuéntame de juan pérez de mi cartera", modo="estratega")
    assert ps["foco"] == "lead" and "juan perez" in ps["resalta"]
    ps2 = derivar_panel_seed("háblame de pedro con calma", modo="estratega")
    assert ps2["foco"] == "lead" and ps2["resalta"].startswith("pedro")


def test_cartera_sin_keyword_no_es_lead():
    # Hallazgo #6: una pregunta de cartera SIN keyword no debe caer a foco 'lead' (la cola son puras
    # palabras de agregado). derivar_foco → None → el frontend conserva el foco actual del dashboard.
    for m in ["cuéntame de la cartera", "cuéntame del pipeline", "qué hay de nuevo en la cartera"]:
        assert derivar_foco(m) is None


# ── Fase D — el dashboard como ENTRADA (contrato del bucle) ──────────────────
# Espejo EXACTO de ESTADO_LBL en frontend/src/AnalisisPanel.jsx (las 9 etiquetas que el clic puede emitir).
_ETIQUETAS_EMBUDO = ["Anónimo", "Identificado", "Explorando", "Enganchado", "Intención",
                     "Confirmado", "Completado", "Returning", "Dormido"]


@pytest.mark.parametrize("lbl", _ETIQUETAS_EMBUDO)
def test_clic_en_etapa_del_embudo_reenfoca_embudo(lbl):
    # El clic en CUALQUIER barra del embudo debe re-enfocar el widget de embudo. 'Dormido' colisionaba con
    # la regla de reenganche ('dormid') → se desambigua con la regla "en el embudo" (prioridad). Cubrir las
    # 9 etiquetas evita que una futura colisión de label pase en verde.
    q = f"¿Qué hago con mis 6 en {lbl} para moverlos en el embudo?"
    assert derivar_foco(q) == "embudo", f"'{lbl}' debería re-enfocar embudo, no {derivar_foco(q)}"


def test_clic_en_cohortes_reenfoca_cohortes():
    assert derivar_foco("¿Cómo van mis 3 interesados maduros?") == "cohortes"
    assert derivar_foco("¿Y mis 7 en vuelo?") == "cohortes"


def test_desambiguacion_no_rompe_reenganche_genuino():
    # La regla "en el embudo" NO debe robarle los focos legítimos de reenganche (que no hablan del embudo).
    assert derivar_foco("¿A quién reenganchar primero?") == "reenganche"
    assert derivar_foco("¿tengo dormidos para reactivar?") == "reenganche"
