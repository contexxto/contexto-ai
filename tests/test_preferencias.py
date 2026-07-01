"""Tests de la captura de preferencias (app/preferencias.py).

La extracción real usa el LLM (no se testea aquí). Sí testeamos las partes puras y críticas:
el SANITIZADOR (última barrera Fair Housing: whitelist cerrada + tipos) y la DEGRADACIÓN
(sin API key / sin mensajes → {}, jamás una excepción que rompa el chat).
"""
import asyncio

from app import preferencias
from app.encaje import DIMENSIONES
from app.preferencias import _sanitizar, extraer_preferencias


# ── Sanitizador: whitelist cerrada (Fair Housing) ────────────────────────────────────
def test_sanitizar_descarta_atributos_de_persona():
    bruto = {"tranquilidad": True, "caminable": True,
             "familia": True, "hijos": 3, "origen": "x", "genero": "F", "perfil": "familia"}
    limpio = _sanitizar(bruto)
    assert limpio == {"tranquilidad": True, "caminable": True}
    # Ninguna clave fuera de la whitelist sobrevive.
    assert set(limpio) <= set(DIMENSIONES)


def test_sanitizar_bool_solo_true():
    # True se registra; False = "no me importa" → se descarta (no puntúa la dimensión).
    assert _sanitizar({"tranquilidad": True, "caminable": False}) == {"tranquilidad": True}


def test_sanitizar_numericos_positivos():
    assert _sanitizar({"presupuesto_max": 800.0}) == {"presupuesto_max": 800.0}
    assert _sanitizar({"min_dormitorios": 2.0}) == {"min_dormitorios": 2}  # → int
    # Cero / negativo / NaN / no-numérico → descartado.
    assert _sanitizar({"presupuesto_max": 0}) == {}
    assert _sanitizar({"presupuesto_max": -5}) == {}
    assert _sanitizar({"min_dormitorios": float("nan")}) == {}
    assert _sanitizar({"presupuesto_max": "mucho"}) == {}


def test_sanitizar_numerico_string_coacciona():
    assert _sanitizar({"presupuesto_max": " 800 "}) == {"presupuesto_max": 800.0}


def test_sanitizar_rechaza_bool_e_infinito_como_numero():
    # bool no es un número declarado (True==1) y ±inf no es un tope real → se descartan.
    assert _sanitizar({"min_dormitorios": True}) == {}
    assert _sanitizar({"presupuesto_max": float("inf")}) == {}
    assert _sanitizar({"presupuesto_max": "inf"}) == {}


def test_sanitizar_no_dict_es_vacio():
    assert _sanitizar(None) == {}
    assert _sanitizar("familia con hijos") == {}
    assert _sanitizar(["tranquilidad"]) == {}


def test_sanitizar_mezcla_realista():
    bruto = {"tranquilidad": True, "presupuesto_max": 700, "min_dormitorios": 2,
             "acepta_mascotas": True, "area_verde": True, "transporte": True, "caminable": True,
             "raza": "x", "edad": 30}  # los 2 últimos son ruido protegido
    limpio = _sanitizar(bruto)
    assert "raza" not in limpio and "edad" not in limpio
    assert limpio["presupuesto_max"] == 700 and limpio["min_dormitorios"] == 2
    assert limpio["tranquilidad"] and limpio["acepta_mascotas"]


# ── Degradación (nunca rompe el chat) ────────────────────────────────────────────────
def test_sin_api_key_devuelve_vacio(monkeypatch):
    monkeypatch.setattr(preferencias.settings, "anthropic_api_key", "")
    assert asyncio.run(extraer_preferencias(["quiero algo tranquilo y barato"])) == {}


def test_sin_mensajes_devuelve_vacio(monkeypatch):
    # Con key presente pero sin mensajes útiles → {} antes de tocar la red.
    monkeypatch.setattr(preferencias.settings, "anthropic_api_key", "sk-fake")
    assert asyncio.run(extraer_preferencias([])) == {}
    assert asyncio.run(extraer_preferencias(["", "   "])) == {}
    assert asyncio.run(extraer_preferencias(None)) == {}
