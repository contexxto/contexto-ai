"""Tests offline del cron de reenganche (app/reenganche_cron.py) — config y helpers puros.

El barrido con DB (escanear_reenganches) se valida en el piloto vía el endpoint
POST /assets/reenganche/scan; aquí cubrimos la configuración y el cálculo de tiempo,
y —al importar el módulo— que no haya errores de import/sintaxis."""
from datetime import datetime, timezone, timedelta

import app.reenganche_cron as cron


def test_habilitado_por_defecto(monkeypatch):
    monkeypatch.delenv("REENGANCHE_CRON_ENABLED", raising=False)
    assert cron.habilitado() is True


def test_deshabilitado_con_valores_falsy(monkeypatch):
    for v in ("0", "false", "No", ""):
        monkeypatch.setenv("REENGANCHE_CRON_ENABLED", v)
        assert cron.habilitado() is False


def test_auto_lead_por_defecto(monkeypatch):
    monkeypatch.delenv("REENGANCHE_AUTO_LEAD", raising=False)
    assert cron.auto_lead() is True


def test_auto_lead_deshabilitado(monkeypatch):
    monkeypatch.setenv("REENGANCHE_AUTO_LEAD", "0")
    assert cron.auto_lead() is False


def test_intervalo_default(monkeypatch):
    monkeypatch.delenv("REENGANCHE_CRON_INTERVAL", raising=False)
    assert cron._intervalo() == 21600


def test_intervalo_clamp_minimo(monkeypatch):
    monkeypatch.setenv("REENGANCHE_CRON_INTERVAL", "10")
    assert cron._intervalo() == 300


def test_intervalo_invalido_cae_al_default(monkeypatch):
    monkeypatch.setenv("REENGANCHE_CRON_INTERVAL", "abc")
    assert cron._intervalo() == 21600


def test_limite_default_y_minimo(monkeypatch):
    monkeypatch.delenv("REENGANCHE_CRON_LIMITE", raising=False)
    assert cron._limite() == 200
    monkeypatch.setenv("REENGANCHE_CRON_LIMITE", "0")
    assert cron._limite() == 1


def test_horas_inactividad_naive_se_asume_utc():
    naive = datetime.utcnow() - timedelta(hours=2)
    h = cron._horas_inactividad(naive)
    assert h is not None and 1.8 < h < 2.3


def test_horas_inactividad_aware():
    aware = datetime.now(timezone.utc) - timedelta(hours=3)
    h = cron._horas_inactividad(aware)
    assert h is not None and 2.8 < h < 3.3


def test_horas_inactividad_none():
    assert cron._horas_inactividad(None) is None
