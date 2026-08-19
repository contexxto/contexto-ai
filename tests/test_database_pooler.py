"""
La elección de configuración del engine según el pooler de Supabase.

POR QUÉ IMPORTA (2026-08-19): las dos configuraciones no son intercambiables y romper la
regla no falla al arrancar — falla después, intermitente. Con el Transaction Pooler (6543)
PgBouncer multiplexa una conexión real entre varios clientes; si asyncpg sigue nombrando
sus prepared statements por orden numérico, dos clientes reclaman el mismo nombre y salta
`prepared statement "__asyncpg_stmt_3__" does not exist` en producción, a horas de haber
desplegado. Y al revés: usar NullPool contra el Session Pooler (5432) tiraría una conexión
nueva por petición contra un techo de 15.

Estos tests fijan la decisión sin abrir una sola conexión.
"""
import asyncio

import pytest
from sqlalchemy.pool import NullPool

from app.database import es_pooler_de_transaccion, opciones_de_engine

SESION = "postgresql+asyncpg://u:p@aws-1-us-west-2.pooler.supabase.com:5432/postgres"
TRANSACCION = "postgresql+asyncpg://u:p@aws-1-us-west-2.pooler.supabase.com:6543/postgres"


# ══ La detección ══════════════════════════════════════════════════════════════════════
def test_el_6543_es_modo_transaccion():
    assert es_pooler_de_transaccion(TRANSACCION) is True


def test_el_5432_no_lo_es():
    assert es_pooler_de_transaccion(SESION) is False


def test_una_url_sin_puerto_no_lo_es():
    assert es_pooler_de_transaccion("postgresql+asyncpg://u:p@localhost/postgres") is False


def test_una_url_rota_no_revienta_y_asume_el_modo_conservador():
    """Ante una URL ilegible, mejor el modo sesión (funciona en ambos) que el otro."""
    assert es_pooler_de_transaccion("esto no es una url ::::") is False
    assert es_pooler_de_transaccion("") is False


# ══ Modo transacción (6543) ═══════════════════════════════════════════════════════════
def test_transaccion_no_agrupa_del_lado_cliente():
    """PgBouncer ya agrupa; hacerlo otra vez acumula prepared statements en el servidor."""
    assert opciones_de_engine(TRANSACCION)["poolclass"] is NullPool


def test_transaccion_apaga_el_cache_de_prepared_statements():
    ca = opciones_de_engine(TRANSACCION)["connect_args"]
    assert ca["prepared_statement_cache_size"] == 0


def test_transaccion_genera_nombres_unicos_por_statement():
    """La colisión de nombres es EL fallo del modo transacción: dos llamadas, dos nombres."""
    f = opciones_de_engine(TRANSACCION)["connect_args"]["prepared_statement_name_func"]
    a, b = f(), f()
    assert a != b
    assert a.startswith("__asyncpg_")


# ══ Modo sesión (5432) — producción ═══════════════════════════════════════════════════
def test_sesion_si_agrupa_y_con_presupuesto_acotado():
    o = opciones_de_engine(SESION)
    assert "poolclass" not in o, "el modo sesión NO debe usar NullPool"
    assert o["pool_size"] >= 1 and o["max_overflow"] >= 0
    assert o["pool_pre_ping"] is True


def test_sesion_no_toca_los_prepared_statements():
    """Contra el Session Pooler los prepared statements son válidos y convienen."""
    assert "connect_args" not in opciones_de_engine(SESION)


# ══ Lo que nunca puede mezclarse ══════════════════════════════════════════════════════
@pytest.mark.parametrize("url", [SESION, TRANSACCION])
def test_jamas_se_combina_nullpool_con_tamano_de_pool(url):
    """SQLAlchemy lanza TypeError si recibe pool_size junto a NullPool. Esta prueba evita
    que un futuro 'unifiquemos las dos ramas' produzca un engine que no se puede crear."""
    o = opciones_de_engine(url)
    if o.get("poolclass") is NullPool:
        assert "pool_size" not in o and "max_overflow" not in o
    else:
        assert "pool_size" in o


# ══ El checkpointer decide igual que el engine ════════════════════════════════════════
# Los dos pools atacan la MISMA base: si quedaran en modos distintos, uno de los dos
# rompería. Y `prepare_threshold` tiene semántica CONTRAINTUITIVA — 0 = preparar SIEMPRE,
# None = desactivar — que ya estuvo mal documentada en el código y costó un fallo real:
# `prepared statement "_pg3_0" already exists`, el checkpointer sin abrir y el grafo
# degradado a MemorySaver. Estos tests fijan la lectura correcta.
def _kwargs_del_checkpointer(monkeypatch, url):
    """Los kwargs REALES con que setup_checkpointer construye su pool, sin conectar.

    Se falsea AsyncConnectionPool: registra lo recibido y hace fallar `open`, así
    setup_checkpointer se va por su rama de degradación (que aquí da igual) y nos deja los
    kwargs. Comprueba COMPORTAMIENTO, no el texto del código.
    """
    import app.agent.graph as graph
    capturado = {}

    class _PoolFalso:
        def __init__(self, **kw):
            capturado.update(kw)

        async def open(self, **_kw):
            raise RuntimeError("no conectamos: solo queriamos los kwargs")

    monkeypatch.setattr(graph, "AsyncConnectionPool", _PoolFalso)
    monkeypatch.setattr(graph, "_checkpointer_conn_str", lambda: url.replace("+asyncpg", ""))
    asyncio.run(graph.setup_checkpointer())
    return capturado


def test_en_transaccion_el_checkpointer_DESACTIVA_los_prepared_statements(monkeypatch):
    """None = desactivados. Con 0 (preparar siempre) PgBouncer devuelve
    `prepared statement "_pg3_0" already exists` y el grafo cae a MemorySaver — reproducido
    el 2026-08-19 contra la base real."""
    kw = _kwargs_del_checkpointer(monkeypatch, TRANSACCION)
    assert kw["kwargs"]["prepare_threshold"] is None


def test_en_sesion_el_checkpointer_SI_prepara(monkeypatch):
    """Contra el Session Pooler la conexión es dedicada: preparar conviene. 0 = preparar
    desde la primera ejecución (semántica contraintuitiva de psycopg, cuidado al leerla)."""
    kw = _kwargs_del_checkpointer(monkeypatch, SESION)
    assert kw["kwargs"]["prepare_threshold"] == 0


def test_el_checkpointer_arranca_pidiendo_UNA_conexion(monkeypatch):
    """min_size=1: `open(wait=True)` bloquea hasta conseguir min_size. Con el default (4)
    produccion no las consiguio en 10 s el 2026-08-18 y arranco sin memoria."""
    kw = _kwargs_del_checkpointer(monkeypatch, SESION)
    assert kw["min_size"] == 1
