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
