"""Tests del motor de ENCAJE (app/encaje.py) — lógica pura, determinística.

Cubre: scoring por dimensión, honestidad (sin dato / sin declarar → None, nunca un
0% falso), ponderación, clamp, el DELTA de COMPARAR, y — lo innegociable — el guardrail
Fair Housing POR CONSTRUCCIÓN: los atributos de la persona no pueden mover el encaje, y
las razones generadas pasan el detector de steering (fair_housing.es_limpio).
"""
from app.encaje import DIMENSIONES, calcular_encaje, delta_encaje
from app.fair_housing import es_limpio


# ── Scoring por dimensión ────────────────────────────────────────────────────────────
def test_tranquilidad_ruido_bajo_es_encaje_alto():
    r = calcular_encaje({"tranquilidad": True}, {"ruido": "BAJO"})
    assert r["score"] == 100
    assert r["razones"][0]["cumple"] == "alto"


def test_tranquilidad_ruido_alto_es_encaje_bajo():
    r = calcular_encaje({"tranquilidad": True}, {"ruido": "ALTO"})
    assert r["score"] == 0


def test_caminable_escala_con_walk_score():
    assert calcular_encaje({"caminable": True}, {"walk_score": 94})["score"] == 94
    assert calcular_encaje({"caminable": True}, {"walk_score": 40})["score"] == 40


def test_transporte_por_minutos_a_pie():
    assert calcular_encaje({"transporte": True}, {"transporte_min": 8})["score"] == 100
    assert calcular_encaje({"transporte": True}, {"transporte_min": 40})["score"] == 10


def test_area_verde_prefiere_parque_concreto_sobre_vegetacion():
    # Con parque a 4 min Y vegetación baja, gana el dato concreto del parque (alto).
    r = calcular_encaje({"area_verde": True}, {"parque_min": 4, "vegetacion": 10})
    assert r["score"] == 100
    # Sin parque, cae a la cobertura vegetal del sector.
    assert calcular_encaje({"area_verde": True}, {"vegetacion": 70})["score"] == 70


def test_presupuesto_dentro_vs_sobre():
    assert calcular_encaje({"presupuesto_max": 800}, {"precio": 750})["score"] == 100
    assert calcular_encaje({"presupuesto_max": 800}, {"precio": 950})["score"] == 0   # 18% sobre
    # Apenas sobre (≤5%) conserva algo de encaje parcial, no lo mata del todo.
    assert calcular_encaje({"presupuesto_max": 800}, {"precio": 830})["score"] == 40


def test_min_dormitorios():
    assert calcular_encaje({"min_dormitorios": 2}, {"num_dormitorios": 3})["score"] == 100
    assert calcular_encaje({"min_dormitorios": 2}, {"num_dormitorios": 1})["score"] == 40
    assert calcular_encaje({"min_dormitorios": 3}, {"num_dormitorios": 1})["score"] == 0


def test_acepta_mascotas():
    assert calcular_encaje({"acepta_mascotas": True}, {"acepta_mascotas": True})["score"] == 100
    assert calcular_encaje({"acepta_mascotas": True}, {"acepta_mascotas": False})["score"] == 0


# ── Ponderación y combinación ────────────────────────────────────────────────────────
def test_promedio_ponderado_presupuesto_pesa_mas():
    # tranquilidad(1.0)=1.0 + presupuesto(1.5)=0.0 → 1.0/2.5 = 40 (no 50): el peso del
    # presupuesto arrastra el promedio más que una dimensión equitativa.
    r = calcular_encaje({"tranquilidad": True, "presupuesto_max": 500},
                        {"ruido": "BAJO", "precio": 900})
    assert r["score"] == 40


def test_solo_puntua_dimensiones_declaradas():
    # El inmueble tiene ruido ALTO, pero el usuario NO declaró tranquilidad → no cuenta.
    r = calcular_encaje({"caminable": True}, {"walk_score": 90, "ruido": "ALTO"})
    assert r["score"] == 90
    assert r["dimensiones_evaluadas"] == ["caminable"]
    assert all(x["dimension"] != "tranquilidad" for x in r["razones"])


def test_bool_false_no_es_declarar():
    # Declarar tranquilidad=False = "no me importa", no debe puntuar la dimensión.
    r = calcular_encaje({"tranquilidad": False, "caminable": True}, {"ruido": "BAJO", "walk_score": 60})
    assert r["dimensiones_declaradas"] == ["caminable"]
    assert r["score"] == 60


# ── Honestidad: "no sé" ≠ "no encaja" ────────────────────────────────────────────────
def test_sin_preferencias_score_none():
    # Nada declarado → None, NUNCA un 0% (o un 100%) inventado.
    r = calcular_encaje({}, {"walk_score": 90, "ruido": "BAJO"})
    assert r["score"] is None


def test_declarada_pero_sin_senal_no_castiga_ni_cuenta():
    # Declaró tranquilidad y caminable; el inmueble solo tiene walk_score (sin ruido).
    # → tranquilidad = 'sin_dato' (se explica, aporta=False), score = solo caminable.
    r = calcular_encaje({"tranquilidad": True, "caminable": True}, {"walk_score": 80})
    assert r["score"] == 80
    assert r["dimensiones_evaluadas"] == ["caminable"]
    sin = [x for x in r["razones"] if x["dimension"] == "tranquilidad"][0]
    assert sin["cumple"] == "sin_dato" and sin["aporta"] is False


def test_todas_declaradas_sin_senal_score_none():
    r = calcular_encaje({"tranquilidad": True, "presupuesto_max": 800}, {})
    assert r["score"] is None
    assert len(r["razones"]) == 2  # ambas explicadas como sin_dato
    assert all(not x["aporta"] for x in r["razones"])


def test_score_siempre_en_rango():
    for veg in (-50, 0, 50, 150, 999):
        s = calcular_encaje({"area_verde": True}, {"vegetacion": veg})["score"]
        assert 0 <= s <= 100


# ── Fair Housing (innegociable) ──────────────────────────────────────────────────────
def test_atributos_protegidos_no_mueven_el_encaje():
    """Un input con rasgos de la persona (familia/hijos/origen/género/religión) debe dar
    EXACTAMENTE el mismo score que sin ellos: la whitelist cerrada los ignora por diseño.
    Esto es la barrera estructural anti-steering."""
    base = {"tranquilidad": True, "caminable": True}
    contaminado = {**base, "familia": True, "hijos": 3, "origen": "extranjero",
                   "genero": "F", "religion": "x", "perfil": "familia joven"}
    inm = {"ruido": "MEDIO", "walk_score": 70}
    assert calcular_encaje(base, inm)["score"] == calcular_encaje(contaminado, inm)["score"]
    # Y las dimensiones evaluadas son idénticas (no se coló ninguna clave ajena).
    assert (calcular_encaje(base, inm)["dimensiones_declaradas"]
            == calcular_encaje(contaminado, inm)["dimensiones_declaradas"])


def test_solo_atributos_protegidos_no_produce_encaje():
    # Si SOLO llegan rasgos de la persona (nada de necesidades), no hay nada que puntuar.
    r = calcular_encaje({"familia": True, "hijos": 2}, {"ruido": "BAJO", "walk_score": 95})
    assert r["score"] is None
    assert r["dimensiones_declaradas"] == []


def test_razones_pasan_el_detector_de_steering():
    """Las razones generadas son dato+fuente, nunca veredictos de idoneidad → es_limpio."""
    prefs = {"tranquilidad": True, "caminable": True, "transporte": True, "area_verde": True,
             "presupuesto_max": 800, "min_dormitorios": 2, "acepta_mascotas": True}
    inm = {"ruido": "BAJO", "walk_score": 88, "transporte_min": 12, "parque_min": 6,
           "precio": 950, "num_dormitorios": 1, "acepta_mascotas": False}
    r = calcular_encaje(prefs, inm)
    for razon in r["razones"]:
        assert es_limpio(razon["texto"]), f"razón dispara steering: {razon['texto']!r}"


def test_whitelist_no_incluye_rasgos_de_persona():
    # Guardrail de diseño: ninguna dimensión de la whitelist es un atributo de la persona.
    prohibidas = {"familia", "hijos", "perfil", "genero", "origen", "religion", "edad", "raza"}
    assert not (set(DIMENSIONES) & prohibidas)


# ── Robustez ante input sucio (LLM / scraper) — nunca crashea, degrada a 'sin dato' ──
def test_precio_string_no_crashea():
    # Precio como string (dato de scraper) → coacciona o degrada, jamás TypeError.
    r = calcular_encaje({"presupuesto_max": 800}, {"precio": "750"})
    assert r["score"] == 100  # "750" coacciona a 750, dentro de presupuesto
    r2 = calcular_encaje({"presupuesto_max": 800}, {"precio": "no disponible"})
    assert r2["score"] is None  # basura → sin dato, no crash


def test_precio_nan_o_inf_es_sin_dato():
    assert calcular_encaje({"presupuesto_max": 800}, {"precio": float("nan")})["score"] is None
    assert calcular_encaje({"presupuesto_max": 800}, {"precio": float("inf")})["score"] is None


def test_presupuesto_cero_no_es_declarable():
    # Un tope de 0 no es una necesidad real → no se declara, no puntúa (nada de 100% con $0).
    r = calcular_encaje({"presupuesto_max": 0}, {"precio": 0})
    assert r["dimensiones_declaradas"] == []
    assert r["score"] is None


def test_acepta_mascotas_string_no_invierte_veredicto():
    # "no" (string) debe leerse como False, NO como truthy → encaje 0, no 100.
    assert calcular_encaje({"acepta_mascotas": True}, {"acepta_mascotas": "no"})["score"] == 0
    assert calcular_encaje({"acepta_mascotas": True}, {"acepta_mascotas": "sí"})["score"] == 100
    # Valor irreconocible → sin dato (no lo forzamos a un veredicto).
    assert calcular_encaje({"acepta_mascotas": True}, {"acepta_mascotas": "quizás"})["score"] is None


def test_walk_score_string_y_dormitorios_bool():
    assert calcular_encaje({"caminable": True}, {"walk_score": "88"})["score"] == 88
    # min_dormitorios=True (bool) NO es un número declarado → se ignora.
    assert calcular_encaje({"min_dormitorios": True}, {"num_dormitorios": 3})["dimensiones_declaradas"] == []


# ── DELTA (modo COMPARAR) ────────────────────────────────────────────────────────────
def test_delta_muestra_donde_gana_cada_uno():
    prefs = {"tranquilidad": True, "transporte": True}
    a = {"ruido": "BAJO", "transporte_min": 30}     # tranquilo pero transporte lejos
    b = {"ruido": "ALTO", "transporte_min": 8}      # ruidoso pero transporte cerca
    d = delta_encaje(prefs, a, b)
    por_dim = {x["dimension"]: x for x in d["dimensiones"]}
    assert por_dim["tranquilidad"]["gana"] == "a"
    assert por_dim["transporte"]["gana"] == "b"
    assert d["a"]["score"] is not None and d["b"]["score"] is not None


def test_delta_empate_y_sin_dato():
    prefs = {"caminable": True, "area_verde": True}
    a = {"walk_score": 80}                 # verde sin dato en ambos
    b = {"walk_score": 80}
    d = delta_encaje(prefs, a, b)
    por_dim = {x["dimension"]: x for x in d["dimensiones"]}
    assert por_dim["caminable"]["gana"] == "empate"
    assert por_dim["area_verde"]["gana"] == "sin_dato"
