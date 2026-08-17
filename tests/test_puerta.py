"""
Tests de la PUERTA SUAVE (app/puerta.py) — cuándo se ofrece avisar, y cuándo NO.

Lo que se prueba con más dureza es lo que NO debe pasar. Una puerta de captura de
correos deriva sola hacia el acoso; la única defensa que aguanta es que las reglas de
no-presión sean código con test, no una intención escrita en un prompt.

Las dos líneas rojas tienen test propio y nombre explícito:
  · el SCORE de intención no dispara la puerta;
  · sin criterio declarado no hay puerta, por muchos turnos que pasen.
"""
import pytest

from app.puerta import (
    ENCAJE_SUFICIENTE,
    PROMESA,
    criterio_whitelist,
    detectar_solicitud_contacto,
    evaluar_puerta,
    pidio_aviso,
)

PREFS = {"tipo_inmueble": "departamento", "presupuesto_max": 800, "tranquilidad": True}


def _card(encaje=90, duros=None):
    return {"id": "a", "encaje": encaje, "duros_incumplidos": duros or []}


# ── El callejón honesto: el ÚNICO momento en que esto es un servicio ────────────────

def test_criterio_declarado_y_nada_que_encaje_abre_la_puerta():
    d = evaluar_puerta(preferencias=PREFS, cards=[])
    assert d is not None
    assert d["motivo"] == "callejon_honesto"
    assert d["promesa"] == PROMESA
    # La puerta repite lo que la persona pidió, con sus términos.
    assert "departamento" in d["detalle"] and "800" in d["detalle"]


def test_si_hay_algo_que_sirve_NO_se_ofrece_nada():
    # No es un callejón: encontró lo que buscaba. Pedirle el correo aquí sería un peaje.
    assert evaluar_puerta(preferencias=PREFS, cards=[_card(encaje=88)]) is None


def test_una_opcion_mostrable_pero_floja_sigue_siendo_callejon():
    # El panel enseña desde 60; que algo sea mostrable no es que sea lo que pidió.
    assert evaluar_puerta(preferencias=PREFS, cards=[_card(encaje=62)]) is not None
    assert evaluar_puerta(preferencias=PREFS,
                          cards=[_card(encaje=ENCAJE_SUFICIENTE)]) is None


def test_una_opcion_del_tipo_equivocado_no_cierra_la_busqueda():
    # Pidió departamento y esto es una casa: su encaje viene topado, y aunque no lo
    # estuviera, no es lo que pidió.
    assert evaluar_puerta(preferencias=PREFS,
                          cards=[_card(encaje=95, duros=["tipo_inmueble"])]) is not None


# ── Las dos LÍNEAS ROJAS ────────────────────────────────────────────────────────────

def test_LINEA_ROJA_sin_criterio_declarado_no_hay_puerta():
    # Ni con el panel vacío, ni con veinte turnos, ni nunca. Sin criterio no hay nada
    # que prometer avisar, y pedir el correo sería el umbral-con-reloj que esto rechaza.
    for prefs in ({}, None, {"perfil": "familia"}, {"tipo_inmueble": ""}):
        assert evaluar_puerta(preferencias=prefs, cards=[]) is None


def test_LINEA_ROJA_el_score_de_intencion_no_dispara_la_puerta():
    # `evaluar_puerta` NO recibe score ni nivel: es imposible por construcción atarla al
    # motor de intención. Si alguien lo agrega, este test deja de compilar el contrato.
    import inspect
    params = set(inspect.signature(evaluar_puerta).parameters)
    assert not params & {"score", "nivel", "intencion", "handoff_sugerido", "turnos"}


def test_el_criterio_solo_puede_enunciar_lo_que_el_motor_puntua():
    # Un atributo de la persona que llegue en preferencias NO puede colarse a la prosa de
    # la puerta: se lee la misma whitelist cerrada que usa el encaje.
    d = evaluar_puerta(preferencias={**PREFS, "perfil": "familia con niños",
                                     "origen": "extranjero"}, cards=[])
    assert d is not None
    assert "familia" not in d["detalle"] and "extranjero" not in d["detalle"]


def test_la_demanda_NO_persiste_atributos_fuera_de_la_whitelist():
    # `demanda.criterio` se guarda en la base y se agrega después. Si una clave de clase
    # protegida sobreviviera hasta ahí, quedaría en el activo exactamente lo que la
    # whitelist cerrada existe para mantener fuera — y eso es peor que no tener el activo.
    sucio = {**PREFS, "perfil": "familia con niños", "origen": "venezolano",
             "religion": "católica", "edad": 34}
    assert criterio_whitelist(sucio) == PREFS
    d = evaluar_puerta(preferencias=sucio, cards=[])
    assert d["criterio_raw"] == PREFS
    assert not ({"perfil", "origen", "religion", "edad"} & set(d["criterio_raw"]))


# ── Las cinco reglas de no-presión ──────────────────────────────────────────────────

def test_regla_3_una_sola_vez():
    assert evaluar_puerta(preferencias=PREFS, cards=[], ya_ofrecida=True) is None


def test_regla_4_si_ya_pidio_corredor_no_se_le_ofrece_nada_mas():
    # Ya hay una puerta más fuerte abierta; insistir con otra es acoso.
    assert evaluar_puerta(preferencias=PREFS, cards=[], pidio_corredor=True) is None


def test_regla_5_la_promesa_es_fija_y_acotada():
    d = evaluar_puerta(preferencias=PREFS, cards=[])
    assert d["promesa"] == PROMESA
    assert "Nada más" in d["promesa"]   # el límite es parte de la promesa


# ── Disparador 2: lo pide la persona ────────────────────────────────────────────────

@pytest.mark.parametrize("texto", [
    "avísame cuando tengas algo", "me avisas si sale algo", "¿me puedes avisar?",
    "notifícame cuando aparezca", "escríbeme cuando haya algo",
])
def test_pedido_explicito_abre_la_puerta_aunque_haya_opciones(texto):
    assert pidio_aviso(texto)
    d = evaluar_puerta(preferencias=PREFS, cards=[_card(encaje=95)], texto_usuario=texto)
    assert d is not None and d["motivo"] == "lo_pidio"


@pytest.mark.parametrize("texto", [
    "", None, "quiero ver el aviso del inmueble", "cuánto cuesta",
    "me interesa este departamento", "gracias por el dato",
])
def test_no_se_inventa_un_pedido_que_no_hubo(texto):
    assert not pidio_aviso(texto)


# ── El control hermano ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto", [
    "Déjame tu correo y te aviso",
    "¿Cuál es tu email?",
    "Necesito tu teléfono para continuar",
    "Escribe tu correo aquí abajo",
    "Dame tu whatsapp",
])
def test_caza_al_modelo_pidiendo_contacto_por_su_cuenta(texto):
    assert detectar_solicitud_contacto(texto), f"debió cazar: {texto}"


@pytest.mark.parametrize("texto", [
    # Mención legítima DESPUÉS de un handoff: el corredor ya tiene el canal.
    "El corredor te escribirá a tu correo en las próximas horas.",
    "Tu solicitud quedó registrada; te contactan por este chat.",
    # Hablar del inmueble, no de la persona.
    "El departamento tiene 2 dormitorios y está dentro de tu presupuesto.",
    "No tengo ese dato.",
    "",
])
def test_alta_precision_no_marca_la_mencion_legitima(texto):
    assert detectar_solicitud_contacto(texto) == [], f"falso positivo en: {texto}"


# ── Defensivo ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cards", [None, [], [None], ["x"], [{"encaje": "alto"}],
                                   [{"encaje": True}], [{}]])
def test_cards_basura_no_revientan_y_degradan_a_callejon(cards):
    # Sin una opción legible que sirva, el estado honesto es el callejón — nunca una
    # excepción en mitad del turno.
    d = evaluar_puerta(preferencias=PREFS, cards=cards)
    assert d is not None and d["motivo"] == "callejon_honesto"


def test_el_detalle_se_acota():
    prefs = {"tipo_inmueble": "departamento " * 200, "presupuesto_max": 800}
    d = evaluar_puerta(preferencias=prefs, cards=[])
    assert len(d["detalle"]) <= 300
