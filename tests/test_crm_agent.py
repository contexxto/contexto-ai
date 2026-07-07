"""Tests del CRM Vivo (agente del corredor) — matcher puro + smokes de montaje."""
from app.agent.crm_tools import _match_lead, CRM_TOOLS


LEADS = [
    {"lead": "Lead #ba0a", "email": None, "session_id": "qr-abc-ba0a-dev"},
    {"lead": "mayra241512@gmail.com", "email": "mayra241512@gmail.com", "session_id": "qr-abc-m123-dev"},
    {"lead": "Lead #3f82", "email": None, "session_id": "qr-abc-3f82-dev"},
]


# ── _match_lead (pura) ──────────────────────────────────────────────────────
def test_match_por_id_corto():
    assert _match_lead(LEADS, "ba0a")["lead"] == "Lead #ba0a"


def test_match_por_id_con_hash():
    assert _match_lead(LEADS, "#ba0a")["lead"] == "Lead #ba0a"


def test_match_por_email():
    assert _match_lead(LEADS, "mayra")["email"] == "mayra241512@gmail.com"


def test_match_sin_coincidencia():
    assert _match_lead(LEADS, "zzzz") is None


def test_match_referencia_vacia():
    assert _match_lead(LEADS, "") is None
    assert _match_lead(LEADS, None) is None


def test_match_case_insensitive():
    assert _match_lead(LEADS, "BA0A")["lead"] == "Lead #ba0a"


def test_match_id_exacto_gana_a_substring():
    # 'ba0a' es id corto EXACTO del segundo y substring del email del primero:
    # debe ganar el exacto, para no traer el interesado equivocado en silencio.
    leads = [
        {"lead": "ba0abc@correo.com", "email": "ba0abc@correo.com", "session_id": "sub"},
        {"lead": "Lead #ba0a", "email": None, "session_id": "exact"},
    ]
    assert _match_lead(leads, "ba0a")["session_id"] == "exact"


# ── smokes de montaje ───────────────────────────────────────────────────────
def test_crm_tools_registradas():
    assert len(CRM_TOOLS) == 2
    nombres = {t.name for t in CRM_TOOLS}
    assert "tool_stats_embudo" in nombres and "tool_timeline_de_lead" in nombres


def test_grafo_crm_compila():
    import app.agent.crm_graph as cg
    assert cg.compiled_crm_graph is not None


def test_endpoint_crm_registrado():
    import main
    paths = {getattr(r, "path", "") for r in main.app.routes}
    assert "/api/v1/assets/crm/chat" in paths
    assert "/api/v1/assets/crm/thread" in paths   # historial + reset (persistencia)


def test_setup_crm_checkpointer_no_crashea_con_none():
    # Con None (Postgres no disponible) conserva el MemorySaver, sin romper.
    from app.agent.crm_graph import setup_crm_checkpointer, compiled_crm_graph
    setup_crm_checkpointer(None)
    assert compiled_crm_graph is not None


# ── Fail-closed de Fair Housing del ESTRATEGA (proactivo) ────────────────────
# El Estratega es PROACTIVO (su 1er mensaje sale sin humano en el loop y dirige TODA la cartera).
# Para él, llm_node NO observa-y-entrega: si detecta segmentación/steering REAL por clase protegida
# reemplaza la salida por REFRAME_FAIR_HOUSING. El gate keys EXACTAMENTE en resultado["fair_housing"]
# (violación real, ya SIN los rechazos legítimos). Estos tests fijan ese contrato.
def test_reframe_fair_housing_declina_y_reancla_a_intencion():
    from app.agent.crm_graph import REFRAME_FAIR_HOUSING
    t = REFRAME_FAIR_HOUSING.lower()
    assert len(REFRAME_FAIR_HOUSING) > 80
    assert "fair housing" in t                              # nombra la línea roja
    assert "intención" in t or "pidió corredor" in t        # reancla a señal transaccional
    assert "no puedo" in t                                  # declina


def test_gate_fh_reencuadra_segmentacion_real():
    # La condición que dispara el fail-close en llm_node: fair_housing NO vacío.
    from app.agent.crm_guardrails import evaluar_salida_crm
    r = evaluar_salida_crm("Enfócate en las familias con hijos, son tus mejores cierres", [])
    assert r["fair_housing"]        # → el estratega lo reencuadra


def test_gate_fh_respeta_rechazo_legitimo():
    # Un rechazo bien hecho NO es violación (va a fh_rechazo) → NO se reencuadra.
    from app.agent.crm_guardrails import evaluar_salida_crm
    r = evaluar_salida_crm("No puedo priorizar por familia; me baso en quién pidió corredor y la etapa", [])
    assert not r["fair_housing"]
    assert r["fh_rechazo"]


def test_gate_fh_no_reencuadra_recomendacion_por_intencion():
    # Recomendación limpia por señal de intención → sin violación, se entrega tal cual.
    from app.agent.crm_guardrails import evaluar_salida_crm
    r = evaluar_salida_crm("Contacta hoy a los que pidieron corredor; prioriza por etapa del embudo", [])
    assert not r["fair_housing"]


def test_crmchatreq_modo_rechaza_valor_invalido():
    # modo es Literal['copiloto','estratega'] → un valor arbitrario es 422 en el borde de validación.
    import pytest
    from pydantic import ValidationError
    from app.routers.assets import CRMChatReq
    assert CRMChatReq(message="hola").modo == "copiloto"          # default
    assert CRMChatReq(message="hola", modo="estratega").modo == "estratega"
    with pytest.raises(ValidationError):
        CRMChatReq(message="hola", modo="x" * 1000)
