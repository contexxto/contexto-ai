"""
`derivar_siguiente` — probado con la MISMA forma de JSON que `tool_stats_embudo` y
`tool_timeline_de_lead` devuelven de verdad (ver `app/agent/crm_tools.py`), no una forma
inventada. El contrato adversarial al final es la prueba dura: ninguna plantilla puede
disparar `evaluar_salida_crm`, el guardián de honestidad del CRM.
"""
import json

from app.agent.crm_guardrails import evaluar_salida_crm
from app.agent.siguiente import derivar_siguiente


def _stats(dormidos=0, hay_registro=True):
    return json.dumps({
        "total_interesados": 12, "por_etapa": {"enganchado": 5, "intencion": 3},
        "calientes_o_piden_corredor": [], "dormidos": dormidos, "por_reenganchar": [],
        "reparto": {"hay_registro": hay_registro, "interesados": 12},
        "_frase_obligatoria": "12 interesados de tu cartera; el reparto completo no tiene registro.",
        "_proveniencia": "Cifras reales del sistema.",
    }, ensure_ascii=False)


def _timeline(lead="Lead #ba0a", reenganche_sugerido=None):
    return json.dumps({
        "lead": lead, "estado": "dormido", "nivel": "tibio", "score": 40,
        "frescura": "dormido", "direccion": "Calle Toledo 2", "razones": ["Se enfrió"],
        "reenganche_sugerido": reenganche_sugerido, "transcript": [], "handoff": [],
        "_proveniencia": "score es heurístico.",
    }, ensure_ascii=False)


def _playbook():
    # tool_playbook_venta: no debe confundirse con ninguna de las otras dos huellas.
    return json.dumps({"_no_respaldo": True, "tema": "objeción de precio", "tacticas": [],
                       "evitar": []}, ensure_ascii=False)


# ══ El catálogo ═══════════════════════════════════════════════════════════════════════
def test_sin_ninguna_tool_no_hay_sugerencia():
    assert derivar_siguiente([]) is None


def test_solo_el_playbook_no_hay_sugerencia():
    assert derivar_siguiente([_playbook()]) is None


def test_dormidos_en_cero_no_sugiere_reenganche():
    assert derivar_siguiente([_stats(dormidos=0)]) is None


def test_dormidos_mayor_a_cero_sugiere_a_quien_escribir():
    assert derivar_siguiente([_stats(dormidos=3)]) == "¿A cuáles de los dormidos les escribo primero?"


def test_sin_registro_de_llegadas_sugiere_activarlo():
    v = derivar_siguiente([_stats(dormidos=0, hay_registro=False)])
    assert v == "¿Cómo empiezo a registrar las llegadas?"


def test_timeline_con_reenganche_sugiere_redactar_con_el_nombre_de_la_tool():
    v = derivar_siguiente([_timeline(lead="Lead #ba0a", reenganche_sugerido="Hola, vi que...")])
    assert v == "Redáctame el mensaje para retomar a Lead #ba0a"


def test_timeline_sin_reenganche_no_sugiere_redactar():
    assert derivar_siguiente([_timeline(reenganche_sugerido=None)]) is None


# ══ Precedencia (más específico gana) ═══════════════════════════════════════════════════
def test_el_timeline_nombrado_gana_sobre_los_dormidos_de_cartera():
    v = derivar_siguiente([_stats(dormidos=5), _timeline(lead="Lead #7c2f", reenganche_sugerido="Hola")])
    assert v == "Redáctame el mensaje para retomar a Lead #7c2f"


def test_dormidos_gana_sobre_sin_registro_dentro_del_mismo_json():
    v = derivar_siguiente([_stats(dormidos=2, hay_registro=False)])
    assert v == "¿A cuáles de los dormidos les escribo primero?"


# ══ Blindaje — un tool_json roto o ajeno no puede tumbar la sugerencia ═════════════════
def test_json_malformado_no_tumba_nada():
    assert derivar_siguiente(["esto no es json", "{"]) is None


def test_una_lista_o_un_numero_en_vez_de_objeto_no_tumba_nada():
    assert derivar_siguiente([json.dumps([1, 2, 3]), json.dumps(42)]) is None


def test_nombre_vacio_no_produce_una_sugerencia_rota():
    assert derivar_siguiente([_timeline(lead="", reenganche_sugerido="Hola")]) is None


def test_el_playbook_no_se_confunde_con_stats_ni_timeline():
    # El playbook trae 'tacticas'/'evitar', ninguna de las dos huellas — no debe disparar nada
    # aunque comparta turno con datos reales de cartera limpios (dormidos=0, con registro).
    assert derivar_siguiente([_playbook(), _stats(dormidos=0, hay_registro=True)]) is None


# ══ Contrato adversarial: ninguna plantilla puede violar el guardián del CRM ═══════════
def test_ninguna_plantilla_dispara_evaluar_salida_crm():
    casos = [
        [_stats(dormidos=4)],
        [_stats(dormidos=0, hay_registro=False)],
        [_timeline(lead="Lead #ba0a", reenganche_sugerido="Hola, vi que...")],
    ]
    for tool_jsons in casos:
        v = derivar_siguiente(tool_jsons)
        assert v is not None
        res = evaluar_salida_crm(v, tool_jsons)
        assert not res["cifra"], f"cifra no respaldada en: {v!r}"
        assert not res["fair_housing"], f"Fair Housing en: {v!r}"
        assert not res["promesa"], f"promesa inflada en: {v!r}"
