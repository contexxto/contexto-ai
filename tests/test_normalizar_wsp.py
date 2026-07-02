"""
Tests del normalizador de WhatsApp del corredor (assets._normalizar_wsp), que alimenta
el deep-link wa.me del handoff (interesado -> corredor). wa.me exige solo dígitos:
código de país + número, sin '+', sin '00' de prefijo internacional, sin espacios.
"""
from app.routers.assets import _normalizar_wsp


def test_formato_internacional_con_mas_y_espacios():
    assert _normalizar_wsp("+593 99 912 3456") == "593999123456"


def test_prefijo_00_internacional_se_quita():
    assert _normalizar_wsp("00593999123456") == "593999123456"


def test_ya_limpio_se_mantiene():
    assert _normalizar_wsp("593999123456") == "593999123456"


def test_mexico_con_guiones_y_parentesis():
    # El piloto Linden es en Puebla (México, +52) — el normalizador no es Ecuador-only.
    assert _normalizar_wsp("+52 (55) 1234-5678") == "525512345678"


def test_ecuador_formato_local_con_cero_se_completa_a_internacional():
    # Bug real (revisión adversarial, 2026-07-02): un corredor ecuatoriano lo mas
    # probable es que teclee su numero como lo ve en su propio celular — formato LOCAL
    # con el 0 inicial, no internacional. Sin completar el codigo de pais, el boton de
    # WhatsApp (wa.me/0984171860) queda roto en silencio, y el banner del letrero
    # mostraba "+0984171860" (no marcable). Debe completarse a "593984171860".
    assert _normalizar_wsp("0984171860") == "593984171860"


def test_numero_de_10_digitos_que_no_empieza_en_cero_no_se_toca():
    # Un numero de 10 digitos que YA trae codigo de pais (no empieza en '0') no debe
    # sufrir la regla de completado — solo aplica al patron inequivoco 0+9 digitos.
    assert _normalizar_wsp("5219999999") == "5219999999"


def test_none_y_vacio_devuelven_none():
    assert _normalizar_wsp(None) is None
    assert _normalizar_wsp("") is None
    assert _normalizar_wsp("   ") is None
    # Solo símbolos, sin dígitos → None (no guarda basura).
    assert _normalizar_wsp("+  -()") is None
