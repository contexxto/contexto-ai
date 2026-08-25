"""
Tests de verify_api_key (gate X-API-Key del backend).

Cubre: dev sin llave (permite todo), llave correcta (pasa), llave
incorrecta/ausente (401). La comparación es en tiempo constante.
"""
import pytest
from fastapi import HTTPException

from app import config
from app.routers.chat import verify_api_key


def test_sin_llave_configurada_permite_todo_en_dev(monkeypatch):
    monkeypatch.setattr(config.settings, "api_key", "")
    monkeypatch.setattr(type(config.settings), "es_produccion", property(lambda _s: False))
    assert verify_api_key(None) is None
    assert verify_api_key("lo-que-sea") is None


@pytest.mark.parametrize("enviada", [None, "", "lo-que-sea"])
def test_sin_llave_configurada_en_produccion_rechaza(monkeypatch, enviada):
    """E0.1 del Trust Gate: una variable ausente no puede abrir una puerta.

    Antes, API_KEY vacía se trataba como dev local SIEMPRE. Vaciarla en el panel
    desprotegía todas las rutas con esta guardia —incluida la escritura del catastro—
    en silencio. Ahora en producción se rechaza.

    503 y no 401: el cliente no hizo nada mal, el servidor está mal configurado.
    """
    monkeypatch.setattr(config.settings, "api_key", "")
    monkeypatch.setattr(type(config.settings), "es_produccion", property(lambda _s: True))
    with pytest.raises(HTTPException) as exc:
        verify_api_key(enviada)
    assert exc.value.status_code == 503


def test_es_produccion_se_infiere_de_render(monkeypatch):
    """Render inyecta RENDER=true solo. No depender de una variable propia significa
    que no hay que acordarse de ponerla para estar protegido."""
    monkeypatch.setattr(config.settings, "environment", "")
    monkeypatch.setenv("RENDER", "true")
    assert config.settings.es_produccion is True
    monkeypatch.delenv("RENDER", raising=False)
    assert config.settings.es_produccion is False


@pytest.mark.parametrize("declarado,esperado", [
    ("production", True), ("prod", True), ("PRODUCTION", True),
    ("dev", False), ("local", False),
])
def test_environment_declarado_manda_sobre_la_inferencia(monkeypatch, declarado, esperado):
    monkeypatch.setattr(config.settings, "environment", declarado)
    monkeypatch.setenv("RENDER", "true")  # se ignora: lo declarado gana
    assert config.settings.es_produccion is esperado


def test_llave_correcta_pasa(monkeypatch):
    monkeypatch.setattr(config.settings, "api_key", "secreta-123")
    assert verify_api_key("secreta-123") is None


@pytest.mark.parametrize("enviada", [None, "", "otra", "secreta-124"])
def test_llave_incorrecta_o_ausente_401(monkeypatch, enviada):
    monkeypatch.setattr(config.settings, "api_key", "secreta-123")
    with pytest.raises(HTTPException) as exc:
        verify_api_key(enviada)
    assert exc.value.status_code == 401
