"""Tests del guardrail Fair Housing (app/fair_housing.py) — lógica pura."""
from app.fair_housing import detectar_steering, es_limpio


# ── DEBE flaguear: veredictos de idoneidad de barrio por grupo/perfil ──
def test_flag_barrio_familiar():
    hits = detectar_steering("Es un barrio familiar, ideal para criar niños.")
    assert hits
    assert any("familiar" in h[0] for h in hits)


def test_flag_buena_zona_para_familias():
    assert detectar_steering("Esta es una buena zona para familias.")


def test_flag_seguro_para_tu_familia():
    assert detectar_steering("Es seguro para tu familia.")


def test_flag_gente_y_comunidad():
    assert detectar_steering("Es gente de bien, una comunidad como la tuya.")


def test_flag_mejor_barrio_para_ti():
    assert detectar_steering("Sin duda, el mejor barrio para tu familia.")


# ── NO debe flaguear: atribución, dato objetivo, o negativa honesta ──
def test_limpio_atribucion_del_usuario():
    # El sistema cita el adjetivo del usuario y sirve el dato con fuente: defendible.
    txt = ("Tú buscabas tranquilidad: el ruido aquí es estimación por sector ~bajo "
           "(no medición) y la caminabilidad calculada es 94 — juzga tú si encaja.")
    assert es_limpio(txt)


def test_limpio_dato_objetivo():
    assert es_limpio("Hay un colegio a ~6 min y un parque a ~4 min, registrados en el mapa.")


def test_limpio_negativa_honesta_seguridad():
    # Negarse a juzgar la seguridad NO es steering — no debe flaguearse.
    assert es_limpio("No tengo datos de seguridad de la zona; el corredor puede confirmarlo.")


def test_limpio_acentos_y_mayusculas():
    # "niños" con acento y mayúsculas: la normalización no debe perder la detección.
    assert detectar_steering("BARRIO FAMILIAR, ideal para CRIAR niños")
    # y un texto neutro con acentos sigue limpio
    assert es_limpio("La caminabilidad es excepcional según los comercios próximos.")
