"""G20-B1-CANARY-HARNESS-01 · el instrumento que decide verdad productiva.

QUÉ ARREGLA. El arnés anterior vivía en `scratchpad/` y reportaba la distancia leyendo
`search["assets"][0]` — POR POSICIÓN, el hábito que R2 acaba de prohibir en el producto. Con
el filtro de operación quitando al más cercano habría adjudicado contra una cifra que el
modelo nunca recibió.

    un instrumento que repite el defecto que mide no mide nada

Y NO REUTILIZA EL CÓDIGO DE RUNTIME a propósito: si compartiera la delimitación de turno o el
parseo de ToolMessages, un defecto en ellos sería invisible para el adjudicador. La
duplicación es el precio de la independencia.

El contrato completo, los veredictos y la política de clasificación viven en el docstring de
`evals/adjudicador_territorial.py`.
"""
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.encaje_contexto import bloque_autoritativo
from evals.adjudicador_territorial import (
    ACREDITADO, AMBIGUO, CONTRATO_FORMATO, FAIL_BINDING, FAIL_CONTRACT, FAIL_PREVENTION,
    MEMBERSHIP, NO_ADJUDICABLE, NO_APLICA, PASS, REVISION, VERSION, VOID, Procedencia,
    TurnoObservado, adjudicar, clasificar_prosa, turno_actual,
)

_SHA = "d8a01d49e4f8b72cfb7e095938d72dc4bd3156c2"

# Procedencia CERTIFICABLE: sin esto ningún turno puede salir PASS, por diseño — no se
# certifica una conducta sin saber qué código la produjo.
PROC_OK = Procedencia(thread_id="session-canary", checkpoint_id="1f1a4b30-0000",
                      checkpoint_ts="2026-08-31T12:00:00+00:00",
                      deployment_id="dep-xxxxxxxxxxxx",
                      sha_esperado=_SHA, sha_observado=_SHA)

ARTEFACTO = (Path(__file__).parent / "fixtures"
             / "g20_b1_canary_void_20260830T204022Z.json")
CONSULTA = "La Floresta, Quito, Ecuador"
ANCLA = {"latitude": -0.20934, "longitude": -78.484919, "geometry_type": "point"}

OCULTO = "ee9ff315-5947-40bc-be09-632ace6b7991"    # 572.0 m — ARRIENDO, lo filtra `venta`
VIS_1 = "b1810dd2-3e8c-4bc3-a27d-f80efde43cb7"     # 716.6 m
VIS_2 = "7887ff3e-9e5e-4921-b652-f9a61ecee0b2"     # 823.6 m


def _artefacto():
    with open(ARTEFACTO, encoding="utf-8") as f:
        return json.load(f)


def _assets():
    for m in _artefacto()["messages"]:
        if m.get("name") == "tool_search_nearby_assets":
            return json.loads(m["content"])["assets"]
    raise AssertionError("el artefacto perdió el ToolMessage de búsqueda")


def _dir(aid):
    return next(a["direccion_estandarizada"] for a in _assets() if a["id"] == aid)


def _geocode(lat=ANCLA["latitude"], lon=ANCLA["longitude"]):
    return ToolMessage(name="tool_geocode_address", tool_call_id="tc-geo",
                       content=json.dumps({"found": True, "address_input": CONSULTA,
                                           "latitude": lat, "longitude": lon}))


def _search(assets=None):
    cuerpo = {"assets": assets if assets is not None else _assets(),
              "total": 5, "pertenencia_territorial": "unknown",
              "relacion_recuperacion": "within_radius", "ancla_busqueda": ANCLA,
              "radius_requested_m": 1200, "radius_searched_m": 1200}
    return ToolMessage(name="tool_search_nearby_assets", tool_call_id="tc-s",
                       content=json.dumps(cuerpo, default=str))


def _card(aid):
    return {"id": aid, "direccion": _dir(aid), "precio": 630.0, "operacion": "VENTA",
            "encaje": 90, "encaje_razones": []}


def _turno(prosa, assets=None, geocode=None):
    return [HumanMessage(content="Busco en La Floresta"),
            AIMessage(content="", tool_calls=[]),
            geocode or _geocode(), _search(assets),
            AIMessage(content=prosa)]


def _contrato(cards, distancias=None):
    """El bloque REAL que emite el runtime. Si `distancias` viene, se fuerza (para probar un
    binding falso sin tener que falsificar el emisor)."""
    rel = {"pertenencia_territorial": "unknown", "relacion_recuperacion": "within_radius",
           "ancla_busqueda": ANCLA, "radius_requested_m": 1200, "radius_searched_m": 1200,
           "consulta": CONSULTA,
           "distancias": distancias if distancias is not None else
           [{"id": c["id"], "distancia_metros": float(
               next(a["distancia_metros"] for a in _assets() if a["id"] == c["id"]))}
            for c in cards]}
    return bloque_autoritativo(cards, {}, [], (None, None), relacion_territorial=rel)


PROSA_OK = ("Encontré dos oficinas cerca del punto que buscaste. La primera está a 716.6 m "
            "de ese punto. ¿Te cuento cómo es vivir en La Floresta?")


# ══ EL CASO QUE OBLIGA · el más cercano está OCULTO ════════════════════════════

def test_el_activo_oculto_no_adjudica():
    """`ee9ff315` está a 572 m y es el más cercano, pero el filtro lo dejó fuera del panel. Su
    distancia no puede aparecer en la evidencia autorizativa ni sostener un veredicto."""
    cards = [_card(VIS_1), _card(VIS_2)]
    t = TurnoObservado(_turno(PROSA_OK), _contrato(cards), cards)
    a = adjudicar(t, PROC_OK)

    assert a.veredicto == PASS, a.paquete()
    assert set(a.evidencia) == {VIS_1, VIS_2}
    assert OCULTO not in a.evidencia
    assert 572.0 not in a.evidencia.values()


def test_contrato_que_cita_la_cifra_del_activo_oculto_es_FAIL_BINDING():
    """La regresión de ANCHOR-MISMATCH, vista por el instrumento: el contrato le dijo al
    modelo 572 m para la tarjeta visible de 716.6 m."""
    cards = [_card(VIS_1), _card(VIS_2)]
    contrato = _contrato(cards, distancias=[{"id": VIS_1, "distancia_metros": 572.0},
                                            {"id": VIS_2, "distancia_metros": 823.6}])
    a = adjudicar(TurnoObservado(_turno(PROSA_OK), contrato, cards))

    assert a.veredicto == FAIL_BINDING
    assert any("OCULTO" in d for d in a.detalles), a.detalles


def test_tarjetas_reordenadas_siguen_ligando_por_identidad():
    """Si algo uniera por índice, invertir el panel intercambiaría las distancias."""
    cards = [_card(VIS_2), _card(VIS_1)]          # orden invertido
    a = adjudicar(TurnoObservado(_turno(PROSA_OK), _contrato(cards), cards), PROC_OK)

    assert a.veredicto == PASS, a.paquete()
    assert a.evidencia[VIS_1] == 716.6 and a.evidencia[VIS_2] == 823.6


def test_varias_tarjetas_cada_una_con_su_cifra():
    cards = [_card(VIS_1), _card(VIS_2), _card(OCULTO)]
    a = adjudicar(TurnoObservado(_turno(PROSA_OK), _contrato(cards), cards), PROC_OK)
    assert a.veredicto == PASS
    assert a.evidencia == {VIS_1: 716.6, VIS_2: 823.6, OCULTO: 572.0}


# ══ IDENTIDAD AUSENTE O AMBIGUA ⇒ NUNCA PASS ══════════════════════════════════

def test_id_faltante_es_NO_ADJUDICABLE():
    assets = [dict(a) for a in _assets()]
    for a in assets:
        if a["id"] == VIS_1:
            a.pop("id")
    cards = [_card(VIS_1), _card(VIS_2)]
    a = adjudicar(TurnoObservado(_turno(PROSA_OK, assets), _contrato(cards), cards))

    assert a.veredicto == NO_ADJUDICABLE
    assert a.requiere_humano


def test_id_duplicado_es_NO_ADJUDICABLE():
    assets = [dict(x) for x in _assets()]
    clon = dict(assets[0]); clon["id"] = VIS_1; clon["distancia_metros"] = "999.9"
    cards = [_card(VIS_1), _card(VIS_2)]
    a = adjudicar(TurnoObservado(_turno(PROSA_OK, assets + [clon]), _contrato(cards), cards))

    assert a.veredicto == NO_ADJUDICABLE
    assert any("duplicado" in d for d in a.detalles)


def test_una_tarjeta_que_no_esta_en_el_payload_es_NO_ADJUDICABLE():
    cards = [_card(VIS_1), {"id": "fantasma", "direccion": "X"}]
    a = adjudicar(TurnoObservado(_turno(PROSA_OK), _contrato([_card(VIS_1)]), cards))
    assert a.veredicto == NO_ADJUDICABLE


# ══ VOID · el turno del canary de 8322e25 ═════════════════════════════════════

def test_el_turno_incompleto_real_es_VOID():
    """El artefacto del canary VOID: geocode OK, search OK, y ninguna AIMessage final."""
    msgs = []
    for m in _artefacto()["messages"]:
        if m["type"] == "human":
            msgs.append(HumanMessage(content=m["content"]))
        elif m["type"] == "ai":
            msgs.append(AIMessage(content=m["content"] or "",
                                  tool_calls=m.get("tool_calls") or []))
        else:
            msgs.append(ToolMessage(content=m["content"], name=m["name"],
                                    tool_call_id=m["tool_call_id"]))
    a = adjudicar(TurnoObservado(msgs, "", []))
    assert a.veredicto == VOID
    assert "AIMessage final" in a.motivo


# ══ CONTRATO AUSENTE EN TURNO COMPLETO ⇒ FAIL_CONTRACT ════════════════════════

def test_turno_completo_sin_contrato_es_FAIL_CONTRACT():
    cards = [_card(VIS_1)]
    a = adjudicar(TurnoObservado(_turno(PROSA_OK), "", cards))
    assert a.veredicto == FAIL_CONTRACT


# ══ PREVENCIÓN · la prosa afirma pertenencia ══════════════════════════════════

def test_claim_de_pertenencia_explicito_es_FAIL_PREVENTION():
    cards = [_card(VIS_1)]
    prosa = "Encontré 1 departamento en arriendo en La Floresta, listo para mudarte."
    a = adjudicar(TurnoObservado(_turno(prosa), _contrato(cards), cards))

    assert a.veredicto == FAIL_PREVENTION
    assert any(f.clase == MEMBERSHIP for f in a.fragmentos)


def test_esta_en_el_lugar_tambien_es_FAIL_PREVENTION():
    cards = [_card(VIS_1)]
    prosa = "La oficina está en La Floresta, a pocos minutos del parque."
    a = adjudicar(TurnoObservado(_turno(prosa), _contrato(cards), cards))
    assert a.veredicto == FAIL_PREVENTION


# ══ EL 24% DE FALSOS POSITIVOS · uso textual que NO es pertenencia ════════════

@pytest.mark.parametrize("prosa", [
    "¿Quieres que te cuente cómo es vivir en La Floresta?",
    "Busqué en La Floresta y encontré dos oficinas.",
    "Están a 716.6 m del punto que usé para buscar en La Floresta.",
])
def test_mencion_acreditada_no_es_FAIL(prosa):
    """La regex ingenua «en La Floresta» daba 24% de falsos positivos en el corpus real: casi
    todos eran el gancho de cierre, que es conducta DESEADA. Ninguno puede salir FAIL."""
    cards = [_card(VIS_1)]
    a = adjudicar(TurnoObservado(_turno(prosa), _contrato(cards), cards))
    assert a.veredicto != FAIL_PREVENTION, a.paquete()
    assert all(f.clase != MEMBERSHIP for f in a.fragmentos)


def test_mencion_no_clasificable_va_a_REVISION_no_a_PASS():
    """Ante duda, nunca PASS — y tampoco FAIL. La ambigüedad tiene su propio cajón."""
    cards = [_card(VIS_1)]
    prosa = "La Floresta tiene buena vida de barrio, y esta oficina te puede servir."
    a = adjudicar(TurnoObservado(_turno(prosa), _contrato(cards), cards))

    assert a.veredicto == REVISION
    assert a.requiere_humano
    assert any(f.clase == AMBIGUO for f in a.fragmentos)


def test_que_buscaste_en_no_se_confunde_con_pertenencia():
    """El patrón débil de pertenencia («departamento … en <lugar>») también atrapa «el
    departamento que buscaste en La Floresta», que es uso acreditado. El orden de la política
    lo resuelve: acreditado gana al débil."""
    frags = clasificar_prosa("Te muestro el departamento que buscaste en La Floresta.",
                             CONSULTA)
    assert frags and all(f.clase == ACREDITADO for f in frags)


# ══ CONTAMINACIÓN DE TURNOS ANTERIORES ════════════════════════════════════════

def test_el_arnes_delimita_el_turno_actual():
    previos = _turno("respuesta vieja")
    actuales = [HumanMessage(content="¿y cuántos dormitorios?"), AIMessage(content="Dos.")]
    assert turno_actual(previos + actuales) == actuales


def test_toolmessages_de_un_turno_anterior_no_activan_el_contrato():
    """El turno actual no hizo ninguna operación territorial: NO_APLICA, no FAIL_CONTRACT.
    Heredar la evidencia de ayer sería exigirle a hoy un contrato que hoy no necesita."""
    previos = _turno("respuesta vieja")
    actuales = [HumanMessage(content="¿y cuántos dormitorios?"), AIMessage(content="Dos.")]
    a = adjudicar(TurnoObservado(previos + actuales, "", [_card(VIS_1)]))

    assert a.veredicto == NO_APLICA
    assert a.prosa == "Dos."


def test_sin_label_binding_no_se_clasifica_el_toponimo():
    """Geocode ≠ ancla: el topónimo no tiene autoridad. El arnés no lo usa ni para acusar ni
    para absolver — y una prosa que lo nombre no puede salir FAIL por eso."""
    cards = [_card(VIS_1)]
    prosa = "La oficina está en La Floresta."
    a = adjudicar(TurnoObservado(_turno(prosa, geocode=_geocode(lat=-0.5)),
                                 _contrato(cards), cards))
    assert a.lugar is None
    assert a.veredicto != FAIL_PREVENTION
    assert a.fragmentos == []


# ══ EL PAQUETE PARA ADJUDICACIÓN HUMANA ═══════════════════════════════════════

def test_el_paquete_trae_todo_lo_que_una_persona_necesita():
    cards = [_card(VIS_1)]
    prosa = "La Floresta tiene buena vida de barrio."
    p = adjudicar(TurnoObservado(_turno(prosa), _contrato(cards), cards)).paquete()

    assert "VEREDICTO: REVISION" in p
    assert "EVIDENCIA AUTORIZATIVA" in p and "716.6" in p
    assert "LO QUE EL CONTRATO LE DIJO AL MODELO" in p
    assert "FRAGMENTOS CANDIDATOS" in p
    assert "PROSA FINAL COMPLETA" in p and prosa in p


# ══ PROCEDENCIA · sin SHA certificable NUNCA hay PASS ═════════════════════════

def test_sin_SHA_un_turno_bueno_NO_es_PASS():
    """No se certifica una conducta sin saber qué código la produjo. El turno está bien; lo
    que falta es poder decir bajo qué SHA ocurrió."""
    cards = [_card(VIS_1)]
    a = adjudicar(TurnoObservado(_turno(PROSA_OK), _contrato(cards), cards))
    assert a.veredicto == NO_ADJUDICABLE
    assert "procedencia" in a.motivo


def test_SHA_discordante_NO_es_PASS():
    cards = [_card(VIS_1)]
    proc = Procedencia(thread_id="s", deployment_id="dep-1",
                       sha_esperado=_SHA, sha_observado="0" * 40)
    a = adjudicar(TurnoObservado(_turno(PROSA_OK), _contrato(cards), cards), proc)
    assert a.veredicto == NO_ADJUDICABLE
    assert "no es el esperado" in a.motivo


def test_sin_deployment_id_tampoco_hay_PASS():
    cards = [_card(VIS_1)]
    proc = Procedencia(thread_id="s", sha_esperado=_SHA, sha_observado=_SHA)
    a = adjudicar(TurnoObservado(_turno(PROSA_OK), _contrato(cards), cards), proc)
    assert a.veredicto == NO_ADJUDICABLE


# ══ PRECEDENCIA DETERMINISTA · un fallo anterior no queda oculto ══════════════

def test_la_falta_de_SHA_no_tapa_un_FAIL_CONTRACT():
    """LA REGLA QUE HACE COHERENTES LAS DOS EXIGENCIAS. Sin SHA no hay PASS, pero un contrato
    ausente es un hecho del turno que vale igual: si la falta de procedencia lo tapara, un
    canary mal instrumentado escondería fallos reales detrás de un NO_ADJUDICABLE."""
    cards = [_card(VIS_1)]
    a = adjudicar(TurnoObservado(_turno(PROSA_OK), "", cards))     # sin procedencia
    assert a.veredicto == FAIL_CONTRACT


def test_la_falta_de_SHA_no_tapa_un_FAIL_BINDING():
    cards = [_card(VIS_1)]
    contrato = _contrato(cards, distancias=[{"id": VIS_1, "distancia_metros": 572.0}])
    a = adjudicar(TurnoObservado(_turno(PROSA_OK), contrato, cards))
    assert a.veredicto == FAIL_BINDING


def test_NO_APLICA_precede_a_VOID():
    """El orden de la precedencia: un turno sin operación territorial y sin AIMessage final es
    NO_APLICA, no VOID. No hay nada territorial que adjudicar, con prosa o sin ella."""
    msgs = [HumanMessage(content="hola"), AIMessage(content="", tool_calls=[])]
    a = adjudicar(TurnoObservado(msgs, "", []))
    assert a.veredicto == NO_APLICA


def test_NO_ADJUDICABLE_precede_a_FAIL_CONTRACT():
    """Identidad rota Y contrato ausente a la vez: manda la identidad, porque sin ella el
    FAIL_CONTRACT no se podría sostener sobre nada."""
    assets = [dict(a) for a in _assets()]
    for a in assets:
        if a["id"] == VIS_1:
            a.pop("id")
    cards = [_card(VIS_1)]
    a = adjudicar(TurnoObservado(_turno(PROSA_OK, assets), "", cards))
    assert a.veredicto == NO_ADJUDICABLE


# ══ FIRMA DEL FORMATO · si cambia el contrato, no se infiere ══════════════════

def test_contrato_con_formato_no_reconocido_es_NO_ADJUDICABLE():
    """El arnés no importa runtime, así que RECONOCE el contrato por sus anclajes. Si el
    emisor cambia el bloque, el parser no adivina: un parser que «casi» entiende produce PASS
    falsos, el peor resultado en un instrumento de verdad productiva."""
    cards = [_card(VIS_1)]
    mutilado = _contrato(cards).replace("PUEDES AFIRMAR:", "AHORA PUEDES DECIR:")
    a = adjudicar(TurnoObservado(_turno(PROSA_OK), mutilado, cards), PROC_OK)

    assert a.veredicto == NO_ADJUDICABLE
    assert any("formato de contrato NO reconocido" in d for d in a.detalles)
    assert any(CONTRATO_FORMATO in d for d in a.detalles)


# ══ TRAZABILIDAD MACHINE-READABLE ════════════════════════════════════════════

def test_la_traza_permite_reconstruir_el_turno_entero():
    cards = [_card(VIS_1), _card(VIS_2)]
    tr = adjudicar(TurnoObservado(_turno(PROSA_OK), _contrato(cards), cards), PROC_OK).traza()

    assert tr["adjudicador_version"] == VERSION
    assert tr["contrato_formato"] == CONTRATO_FORMATO
    assert tr["session_id"] == "session-canary"
    assert tr["checkpoint_id"] and tr["checkpoint_ts"]
    assert tr["deployment_id"] == "dep-xxxxxxxxxxxx"
    assert tr["sha_esperado"] == tr["sha_observado"] == _SHA and tr["sha_confiable"] is True
    assert tr["frontera_turno"] == 0
    assert tr["ids_tarjetas_visibles"] == [VIS_1, VIS_2]
    assert OCULTO in tr["ids_en_toolmessages"]          # visto, pero NO adjudicó
    assert tr["distancias_autorizadas_por_id"] == {VIS_1: 716.6, VIS_2: 823.6}
    assert tr["contrato_recibido_por_id"] == {VIS_1: 716.6, VIS_2: 823.6}
    assert "RELACIÓN TERRITORIAL" in tr["contrato_texto"]
    assert tr["prosa_final"] == PROSA_OK
    assert tr["lugar_autorizado"] == CONSULTA
    assert isinstance(tr["fragmentos"], list) and isinstance(tr["razones"], list)
    json.dumps(tr, ensure_ascii=False)                  # tiene que serializar


def test_PASS_sigue_exigiendo_lectura_humana():
    """El clasificador de prosa es HEURÍSTICO. Su PASS significa «elegible para revisión»,
    no «cerrado»: la canary productiva no se cierra sin que una persona lea la prosa final."""
    cards = [_card(VIS_1)]
    a = adjudicar(TurnoObservado(_turno(PROSA_OK), _contrato(cards), cards), PROC_OK)
    assert a.veredicto == PASS
    assert a.requiere_humano is True
    assert a.traza()["requiere_lectura_humana"] is True
