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


def test_none_y_vacio_devuelven_none():
    assert _normalizar_wsp(None) is None
    assert _normalizar_wsp("") is None
    assert _normalizar_wsp("   ") is None
    # Solo símbolos, sin dígitos → None (no guarda basura).
    assert _normalizar_wsp("+  -()") is None
