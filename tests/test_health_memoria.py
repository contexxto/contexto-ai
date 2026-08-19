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
import asyncio
import time
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
    """Llama a /health con el checkpointer que se le indique (None = degradado a memoria).

    SIN `with`, a propósito: usar TestClient como gestor de contexto ejecuta el lifespan
    de la app, que monta el checkpointer REAL contra la Supabase de producción — pool de
    conexiones incluido, contra un techo de 15 que se comparte con el servicio en vivo.
    Estas pruebas no necesitan nada de eso: falsean la sesión y el checkpointer. Sin
    lifespan son herméticas, instantáneas, y no le quitan conexiones a producción.
    """
    monkeypatch.setattr(main, "get_checkpointer", lambda: checkpointer)
    return TestClient(main.app).get("/health")


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


# ══ El sondeo va acotado ══════════════════════════════════════════════════════════════
# Una base que CUELGA (no que falla) dejaría a /health esperando el timeout del pool —
# 30 s por defecto — y Render acabaría reiniciando por health check vencido: el mismo
# bucle que se evita devolviendo 200, entrando por la otra puerta.
def test_una_base_colgada_no_cuelga_el_chequeo(monkeypatch):
    """El caso que motiva el corte: la base no responde nunca."""
    async def _nunca_responde():
        # 5 s, no 3600: si alguien quita el corte, esta prueba debe FALLAR (tarda de más),
        # no COLGARSE. Un test que cuelga en CI se ve como un timeout opaco; uno que falla
        # dice qué se rompió.
        await asyncio.sleep(5)

    monkeypatch.setattr(main, "_sondear_db", _nunca_responde)
    monkeypatch.setattr(main, "TIMEOUT_SONDEO_DB_S", 0.05)  # el test no espera 3 s

    t0 = time.monotonic()
    r = _health(monkeypatch, checkpointer=object())
    tardanza = time.monotonic() - t0

    assert r.status_code == 200, "aun con la base colgada debe contestar, no vencer"
    assert tardanza < 2.0, f"el sondeo no se corto: tardo {tardanza:.1f}s"


def test_una_base_colgada_se_reporta_como_saturada_no_como_caida(monkeypatch):
    """`timeout` y `down` llevan a diagnósticos distintos: saturada vs inalcanzable.
    Distinguirlas es justo lo que faltó el 2026-08-18."""
    async def _nunca_responde():
        # 5 s, no 3600: si alguien quita el corte, esta prueba debe FALLAR (tarda de más),
        # no COLGARSE. Un test que cuelga en CI se ve como un timeout opaco; uno que falla
        # dice qué se rompió.
        await asyncio.sleep(5)

    monkeypatch.setattr(main, "_sondear_db", _nunca_responde)
    monkeypatch.setattr(main, "TIMEOUT_SONDEO_DB_S", 0.05)
    cuerpo = _health(monkeypatch, checkpointer=object()).json()
    assert cuerpo["database"] == "timeout"
    assert cuerpo["status"] == "degraded"


def test_una_base_inalcanzable_se_reporta_como_caida(monkeypatch):
    async def _explota():
        raise OSError("connection refused")

    monkeypatch.setattr(main, "_sondear_db", _explota)
    cuerpo = _health(monkeypatch, checkpointer=object()).json()
    assert cuerpo["database"] == "down"
    assert cuerpo["status"] == "degraded"


def test_el_timeout_es_muy_menor_que_el_del_pool(monkeypatch):
    """Si alguien lo sube a 30 s, el sondeo vuelve a poder colgarse tanto como el pool y
    esta protección deja de existir. 5 s ya es demasiado para un `SELECT 1`."""
    assert 0 < main.TIMEOUT_SONDEO_DB_S <= 5.0
