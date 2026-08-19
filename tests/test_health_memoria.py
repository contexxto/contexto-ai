"""
`/health` distingue "vivo" de "vivo pero amnésico".

EL FALLO QUE LO ORIGINA (2026-08-18): el checkpointer Postgres no logró abrir su pool al
arrancar (`pool initialization incomplete after 10 sec`, por el techo de 15 del Session
Pooler) y el grafo quedó con MemorySaver. La app siguió respondiendo **200 en todo** —
`/health` incluido — pero sin historial: conversaciones sin título que no abrían. Corrió
así 1h26m en producción y se detectó de casualidad, revisando logs a mano por otra cosa.
Ver docs/INCIDENTE_2026-08-18_Pools.md.

Lo que estos tests fijan:
  - el CUERPO delata la memoria rota (`status: degraded`, `memoria: volatil`);
  - el CÓDIGO HTTP sigue siendo 200 aun degradado, a propósito: `render.yaml` apunta su
    healthCheckPath aquí, y fallar reiniciaría en bucle justo cuando faltan conexiones.
    Si alguien "arregla" eso devolviendo 503, el segundo test se cae y obliga a leer por qué.

Sin base de datos: se mockea tanto la sesión como el checkpointer.
"""
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def db_arriba(monkeypatch):
    """La base responde; así el único eje que varía en los tests es la memoria."""
    class _Sesion:
        async def execute(self, *_a, **_k):
            return None

    @asynccontextmanager
    async def _fake():
        yield _Sesion()

    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: _fake())


def _health(monkeypatch, *, checkpointer):
    """Llama a /health con el checkpointer que se le indique (None = degradado a memoria)."""
    monkeypatch.setattr(main, "get_checkpointer", lambda: checkpointer)
    with TestClient(main.app) as cliente:
        return cliente.get("/health")


def test_con_checkpointer_postgres_reporta_memoria_persistente(db_arriba, monkeypatch):
    r = _health(monkeypatch, checkpointer=object())  # cualquier saver activo
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["memoria"] == "postgres"
    assert cuerpo["status"] == "healthy"


def test_sin_checkpointer_el_cuerpo_delata_la_memoria_rota(db_arriba, monkeypatch):
    """El corazón del asunto: esto es lo que el 2026-08-18 nadie pudo ver."""
    cuerpo = _health(monkeypatch, checkpointer=None).json()
    assert cuerpo["memoria"] == "volatil"
    assert cuerpo["status"] == "degraded", "un monitor externo alerta sobre este campo"


def test_degradado_sigue_devolviendo_200_a_proposito(db_arriba, monkeypatch):
    """NO cambiar a 503 sin pensarlo: render.yaml usa /health como healthCheckPath, y
    fallar aquí reinicia el servicio en bucle justo cuando escasean las conexiones —
    que es la causa del problema. Degradado-pero-sirviendo > caído."""
    assert _health(monkeypatch, checkpointer=None).status_code == 200
