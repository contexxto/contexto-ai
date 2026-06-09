"""
Tests de verify_api_key (gate X-API-Key del backend).

Cubre: dev sin llave (permite todo), llave correcta (pasa), llave
incorrecta/ausente (401). La comparación es en tiempo constante.
"""
import pytest
from fastapi import HTTPException

from app import config
from app.routers.chat import verify_api_key


def test_sin_llave_configurada_permite_todo(monkeypatch):
    monkeypatch.setattr(config.settings, "api_key", "")
    assert verify_api_key(None) is None
    assert verify_api_key("lo-que-sea") is None


def test_llave_correcta_pasa(monkeypatch):
    monkeypatch.setattr(config.settings, "api_key", "secreta-123")
    assert verify_api_key("secreta-123") is None


@pytest.mark.parametrize("enviada", [None, "", "otra", "secreta-124"])
def test_llave_incorrecta_o_ausente_401(monkeypatch, enviada):
    monkeypatch.setattr(config.settings, "api_key", "secreta-123")
    with pytest.raises(HTTPException) as exc:
        verify_api_key(enviada)
    assert exc.value.status_code == 401
