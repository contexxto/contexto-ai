"""Tests offline del motor de reenganche (app/reenganche.py) — lógica pura."""
from app.intencion import analizar_intencion
from app.reenganche import (
    clasificar_frescura,
    evaluar_reenganche,
    HORAS_MIN_REENGANCHE,
    DIAS_FRIO_PROFUNDO,
    HORAS_ANTI_REPETICION,
)

# Horas de inactividad que caen limpio en "dormido" (>= mínimo, < frío profundo).
HORAS_DORMIDO_OK = HORAS_MIN_REENGANCHE + 24


def _intencion_zona():
    """Lead que exploró el entorno (señal transaccional 'zona'), no caliente."""
    return analizar_intencion(mensajes_usuario=["¿Cómo es el ruido y la caminabilidad del barrio?"])


# ── clasificar_frescura ─────────────────────────────────────────────────────
def test_frescura_desconocida_sin_marca():
    assert clasificar_frescura(None) == "desconocida"


def test_frescura_activo_reciente():
    assert clasificar_frescura(1.0) == "activo"
    assert clasificar_frescura(HORAS_MIN_REENGANCHE - 1) == "activo"


def test_frescura_dormido():
    assert clasificar_frescura(HORAS_MIN_REENGANCHE) == "dormido"
    assert clasificar_frescura(DIAS_FRIO_PROFUNDO * 24 - 1) == "dormido"


def test_frescura_frio_profundo():
    assert clasificar_frescura(DIAS_FRIO_PROFUNDO * 24 + 1) == "frio_profundo"


# ── evaluar_reenganche: cuándo NO (el silencio por defecto) ─────────────────
def test_no_reenganche_a_caliente():
    intenc = analizar_intencion(mensajes_usuario=["¿Me das el contacto del corredor?"], es_qr=True)
    assert intenc["nivel"] == "caliente"
    assert evaluar_reenganche(intencion=intenc, horas_inactividad=HORAS_DORMIDO_OK) is None


def test_no_reenganche_en_handoff():
    # Un lead que pidió visita dispara handoff → ya es del corredor, no se reengancha.
    intenc = analizar_intencion(mensajes_usuario=["¿Se puede agendar una visita?"], es_qr=True)
    assert intenc["handoff_sugerido"] is True
    assert evaluar_reenganche(intencion=intenc, horas_inactividad=HORAS_DORMIDO_OK) is None


def test_no_reenganche_demasiado_pronto():
    intenc = _intencion_zona()
    assert evaluar_reenganche(intencion=intenc, horas_inactividad=HORAS_MIN_REENGANCHE - 1) is None


def test_no_reenganche_sin_senal_transaccional():
    # Solo saludó → sin ángulo de valor → silencio.
    intenc = analizar_intencion(mensajes_usuario=["Hola, buenas"])
    assert evaluar_reenganche(intencion=intenc, horas_inactividad=HORAS_DORMIDO_OK) is None


def test_no_reenganche_por_clase_protegida():
    """Fair Housing: 'perfil' (necesidad declarada, sin señal transaccional pura) NO es
    un ángulo de reenganche. Un lead cuya única señal es 'perfil' no se reengancha."""
    intenc = analizar_intencion(mensajes_usuario=["Estoy mirando dentro de mi presupuesto"])
    assert intenc["senales"].get("perfil") is True
    assert evaluar_reenganche(intencion=intenc, horas_inactividad=HORAS_DORMIDO_OK) is None


def test_no_reenganche_repetido_reciente():
    intenc = _intencion_zona()
    r = evaluar_reenganche(
        intencion=intenc, horas_inactividad=HORAS_DORMIDO_OK,
        horas_desde_ultimo_reenganche=HORAS_ANTI_REPETICION - 1,
    )
    assert r is None


def test_reenganche_permitido_tras_espera_anti_repeticion():
    intenc = _intencion_zona()
    r = evaluar_reenganche(
        intencion=intenc, horas_inactividad=HORAS_DORMIDO_OK,
        horas_desde_ultimo_reenganche=HORAS_ANTI_REPETICION + 1,
    )
    assert r is not None


# ── evaluar_reenganche: cuándo SÍ, y cómo ───────────────────────────────────
def test_reenganche_por_zona_es_valor_primero():
    intenc = _intencion_zona()
    r = evaluar_reenganche(intencion=intenc, horas_inactividad=HORAS_DORMIDO_OK,
                           direccion="La Carolina 123")
    assert r is not None
    assert r["reenganchar"] is True
    assert r["angulo"] == "entorno"
    assert r["frescura"] == "dormido"
    assert r["tono"] == "valor"
    assert r["canal_sugerido"] == "email"
    # Valor-primero: honesto y sin empuje transaccional.
    assert "sin compromiso" in r["mensaje"].lower()
    assert "sigues interesado" not in r["mensaje"].lower()
    assert "La Carolina 123" in r["mensaje"]


def test_reenganche_lidera_con_ficha_si_pregunto_ficha():
    intenc = analizar_intencion(
        mensajes_usuario=["¿Me pasas la ficha técnica y el estado de la tubería?"])
    r = evaluar_reenganche(intencion=intenc, horas_inactividad=HORAS_DORMIDO_OK)
    assert r is not None and r["angulo"] == "ficha"


def test_novedad_verificada_refuerza_mensaje():
    intenc = _intencion_zona()
    nov = [{"tipo": "entorno", "etiqueta": "caminabilidad medida con comercios reales (78/100)"}]
    r = evaluar_reenganche(intencion=intenc, horas_inactividad=HORAS_DORMIDO_OK, novedades=nov)
    assert r["novedad"] == nov[0]
    assert "78/100" in r["mensaje"]


def test_novedad_de_otro_tipo_no_se_fuerza_mal():
    # Si la novedad no calza con el ángulo, igual se puede usar como refuerzo disponible,
    # pero nunca rompe: el mensaje sale bien formado.
    intenc = _intencion_zona()
    nov = [{"tipo": "precio", "etiqueta": "precio verificado y lo que incluye"}]
    r = evaluar_reenganche(intencion=intenc, horas_inactividad=HORAS_DORMIDO_OK, novedades=nov)
    assert r is not None and isinstance(r["mensaje"], str) and r["mensaje"]


def test_horas_desconocidas_el_motor_puede_sugerir_frescura_desconocida():
    # El motor puro no exige conocer el tiempo (el CRM sí lo gatea). Frescura desconocida.
    intenc = _intencion_zona()
    r = evaluar_reenganche(intencion=intenc, horas_inactividad=None)
    assert r is not None
    assert r["frescura"] == "desconocida"


def test_intencion_no_dict_devuelve_none():
    assert evaluar_reenganche(intencion=None, horas_inactividad=HORAS_DORMIDO_OK) is None
