"""registrar_intencion no puede fallar en silencio (docs/AUDITORIA_Fallos_Silenciosos_2026-07-31.md §1).

Es el ÚNICO camino de escritura de intencion_sesion e intencion_evento — las dos tablas de la
North Star. Debe seguir siendo no bloqueante (el chat nunca se rompe), pero un fallo suyo tiene
que dejar rastro: sin log, un registro que falla es indistinguible de menos demanda, y el reporte
semanal leería "no está llegando gente" cuando la causa real es un bug.

Estos tests fijan esa propiedad para que nadie la deshaga limpiando el except.
"""
import logging

import pytest

from app.routers import chat


class _Captura(logging.Handler):
    def __init__(self):
        super().__init__()
        self.registros: list[logging.LogRecord] = []

    def emit(self, record):
        self.registros.append(record)


@pytest.fixture
def intencion_rota(monkeypatch):
    """Rompe lo primero que hace registrar_intencion y captura el logger 'intencion'."""
    def revienta(*a, **k):
        raise ValueError("boom simulado (CheckConstraint / DB caída)")

    monkeypatch.setattr(chat, "analizar_intencion", revienta)
    handler = _Captura()
    logger = logging.getLogger("intencion")
    logger.addHandler(handler)
    monkeypatch.setattr(logger, "level", logging.ERROR, raising=False)
    yield handler
    logger.removeHandler(handler)


async def test_no_propaga_la_excepcion(intencion_rota):
    """Sigue siendo best-effort: un fallo de instrumentación jamás rompe el chat."""
    await chat.registrar_intencion("qr-sesion-prueba", [])


async def test_deja_rastro_con_la_sesion(intencion_rota):
    """Best-effort NO es lo mismo que silencioso: tiene que haber un log.error identificable."""
    await chat.registrar_intencion("qr-sesion-prueba", [])

    errores = [r for r in intencion_rota.registros if r.levelno >= logging.ERROR]
    assert errores, "registrar_intencion falló sin dejar rastro (fallo silencioso)"

    mensaje = errores[0].getMessage()
    assert "qr-sesion-prueba" in mensaje, "el log no identifica la sesión afectada"
    assert errores[0].exc_info, "el log no incluye traceback (exc_info)"
