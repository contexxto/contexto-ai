"""Tests del CRM Vivo (agente del corredor) — matcher puro + smokes de montaje."""
from app.agent.crm_tools import _match_lead, CRM_TOOLS, ESTRATEGA_TOOLS


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
    assert len(CRM_TOOLS) == 3
    nombres = {t.name for t in CRM_TOOLS}
    assert nombres == {"tool_stats_embudo", "tool_timeline_de_lead", "tool_playbook_venta"}


def test_estratega_no_ve_timeline_por_lead():
    # Frontera por-agente: el Estratega SOLO ve la cartera agregada. Sin tool_timeline_de_lead no
    # puede jalar el chat crudo de un interesado → no hay fuga de clase protegida a su contexto, y
    # el detalle por-lead queda del lado del Copiloto (por construcción, no solo por prompt).
    nombres = {t.name for t in ESTRATEGA_TOOLS}
    assert nombres == {"tool_stats_embudo", "tool_playbook_venta"}   # cartera + playbook, SIN timeline por-lead
    assert "tool_timeline_de_lead" not in nombres


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


# ── Playbook de venta (retrieval del Corredor-Brain, bundleado) ──────────────
# tool_playbook_venta consulta el JSON destilado del LLM-wiki, filtrando por AGENTE (modo). Estos tests
# fijan: el playbook carga, ninguna táctica usable es 🔴, el ruteo por agente NO filtra de más, y los
# anti-patrones se ofrecen como 'evitar'.
def _pb(tema, modo):
    import asyncio, json
    from app.agent.crm_tools import tool_playbook_venta
    return json.loads(asyncio.run(tool_playbook_venta.ainvoke({"tema": tema}, config={"configurable": {"modo": modo}})))


def test_playbook_carga_y_sin_rojos():
    from app.agent.crm_tools import _load_playbook
    pb = _load_playbook()
    assert pb["n_tacticas"] > 20 and pb["n_evitar"] > 0
    # ninguna táctica USABLE es 🔴 (esas van solo en 'evitar')
    assert all(t["foso"] != "rojo" for t in pb["tacticas"])
    # cada táctica tiene los campos clave para aplicarla honestamente
    for t in pb["tacticas"][:8]:
        assert t["titulo"] and t["agente"] and t["foso"]


def test_playbook_en_ambos_toolsets():
    from app.agent.crm_tools import CRM_TOOLS, ESTRATEGA_TOOLS
    assert "tool_playbook_venta" in {t.name for t in CRM_TOOLS}
    assert "tool_playbook_venta" in {t.name for t in ESTRATEGA_TOOLS}


def test_playbook_ruteo_copiloto_no_ve_estratega():
    # El Copiloto SOLO ve tácticas con agente copiloto|ambos (nunca las de solo-estratega, p.ej. 33-Touch).
    from app.agent.crm_tools import _load_playbook
    por_titulo = {t["titulo"]: t["agente"] for t in _load_playbook()["tacticas"]}
    d = _pb("cadencia de contacto nurture 33-touch de la base", "copiloto")
    for t in d["tacticas"]:
        assert por_titulo[t["titulo"]] in ("copiloto", "ambos")


def test_playbook_ruteo_estratega():
    from app.agent.crm_tools import _load_playbook
    por_titulo = {t["titulo"]: t["agente"] for t in _load_playbook()["tacticas"]}
    d = _pb("priorizar la cartera y su cadencia", "estratega")
    for t in d["tacticas"]:
        assert por_titulo[t["titulo"]] in ("estratega", "ambos", "corredor")


def test_playbook_ofrece_antipatrones():
    # Sobre un tema de manipulación, debe surgir el anti-patrón a EVITAR.
    d = _pb("escasez y urgencia para forzar el cierre", "copiloto")
    assert any("scasez" in e["NO_USAR"].lower() or "urgencia" in e["NO_USAR"].lower() for e in d["evitar"])


# ── Fixes de la revisión adversarial del playbook ───────────────────────────
def test_playbook_no_respalda_cifras_de_cartera():
    # Hallazgo #1: el JSON del playbook (marcado _no_respaldo) NUNCA respalda una cifra narrada sobre
    # la cartera, aunque contenga números de los moguls (33-touch, "~30% referidos", 2000).
    import json
    from app.agent.crm_guardrails import cifras_no_respaldadas
    playbook_out = json.dumps({"_no_respaldo": True, "tacticas": [
        {"que_es": "33 toques al año; cerca del 30% del negocio son referidos; 2000 contactos ≈ 1M"}]})
    hits = cifras_no_respaldadas("Cerca del 30% de tu cartera son referidos y tienes 33 dormidos", [playbook_out])
    assert hits, "el playbook es coaching: no debe respaldar cifras de cartera"


def test_detector_promesa_inflada():
    # Hallazgo #2: el candado 'no infles el outcome' vuelto control determinista.
    from app.agent.crm_guardrails import detectar_promesa_inflada
    assert detectar_promesa_inflada("Compra ya, seguro sube de precio el próximo año")
    assert detectar_promesa_inflada("Te garantizo que esta casa se revaloriza")
    assert detectar_promesa_inflada("Vas a ser muy feliz en esta zona")
    assert detectar_promesa_inflada("Es una inversión segura, sin riesgo")
    # Alta precisión: la afirmación honesta con dato/rótulo NO cae.
    assert not detectar_promesa_inflada("El tráfico ronda ~5 mil vehículos/día (dato verificado)")
    assert not detectar_promesa_inflada("Pidió corredor y está en Intención; su score estimado es alto")


def test_evaluar_salida_expone_promesa():
    from app.agent.crm_guardrails import evaluar_salida_crm
    assert evaluar_salida_crm("Garantizado que esta propiedad se revaloriza", [])["promesa"]
    assert not evaluar_salida_crm("Contacta a los que pidieron corredor; prioriza por etapa", [])["promesa"]
