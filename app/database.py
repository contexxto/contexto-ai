"""
El engine de SQLAlchemy, con DOS configuraciones según a qué pooler de Supabase apunte
la URL. No es una preferencia de estilo: mezclarlas rompe de formas distintas.

  · 5432 — Session Pooler. Cada cliente ocupa una conexión real mientras viva, y Supabase
    corta en 15 CLIENTES POR PROYECTO. Aquí el pooling del lado cliente es lo correcto, y
    su tamaño es un presupuesto que se comparte con el pool del checkpointer de LangGraph
    (ver app/config.py). Es lo que usa PRODUCCIÓN.

  · 6543 — Transaction Pooler. PgBouncer multiplexa: una conexión real se reparte entre
    muchos clientes, transacción a transacción, así que el techo de 15 deja de aplicar.
    A cambio pierdes el estado de sesión, y los prepared statements de asyncpg —que se
    nombran por orden numérico— colisionan entre clientes que creen tener la conexión
    para ellos solos. El síntoma no aparece al arrancar: aparece más tarde, intermitente,
    como `prepared statement "__asyncpg_stmt_3__" does not exist`.

Por eso el modo transacción exige los tres ajustes de abajo, que son la receta oficial
del dialecto asyncpg de SQLAlchemy (ver su docstring, sección "Prepared Statement Name
with PGBouncer"): NullPool, cache de statements en 0, y nombres únicos por statement.

Motivación (2026-08-19): desarrollo y producción comparten proyecto de Supabase, así que
levantar el backend local le quita conexiones a producción — con la app respondiendo 200
en todo pero sin historial. Apuntando el .env local al 6543, esa competencia desaparece
de raíz en vez de repartirse un techo que no da. Ver docs/INCIDENTE_2026-08-18_Pools.md.
"""
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings

_PUERTO_TRANSACCION = 6543


def es_pooler_de_transaccion(url: str) -> bool:
    """True si la URL apunta al Transaction Pooler de Supabase (puerto 6543).

    Se decide por PUERTO y no por una variable aparte a propósito: así no puede quedar
    desincronizado. Cambiar el puerto en el .env es la única acción necesaria; el modo se
    deduce solo y no hay forma de apuntar al 6543 con la configuración del 5432.
    """
    try:
        return urlparse(url).port == _PUERTO_TRANSACCION
    except ValueError:          # URL malformada: asume el modo conservador (sesión)
        return False


def opciones_de_engine(url: str) -> dict:
    """Los kwargs de `create_async_engine` que corresponden a esa URL.

    Función aparte —y no un `if` incrustado en la llamada— para poder probar la decisión
    sin abrir una conexión: ver tests/test_database_pooler.py.
    """
    if es_pooler_de_transaccion(url):
        return {
            "echo": False,
            # PgBouncer YA agrupa; agrupar otra vez encima acumula prepared statements
            # inútiles en el servidor. La advertencia del dialecto es explícita en esto.
            "poolclass": NullPool,
            "connect_args": {
                # ── HAY DOS CACHÉS, y hacen falta los dos en 0. Aprendido a golpes el
                # 2026-08-19: con solo el primero, asyncpg sigue preparando statements por
                # su cuenta y PgBouncer devuelve su error clásico ("if you have no option
                # of avoiding the use of pgbouncer, set statement_cache_size to 0").
                # No falla al arrancar: falla al primer uso real de la app.
                "prepared_statement_cache_size": 0,   # el caché de SQLAlchemy — lo saca
                                                      # AsyncAdapt_asyncpg_dbapi.connect
                "statement_cache_size": 0,            # el caché INTERNO de asyncpg —
                                                      # sigue de largo hasta asyncpg.connect
                # Y aun con los cachés apagados, los nombres se enumeran: únicos por
                # statement para que dos clientes multiplexados no reclamen el mismo.
                "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
            },
        }
    # Session Pooler (producción): pooling del lado cliente, con presupuesto acotado.
    return {
        "echo": False,
        "pool_pre_ping": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_recycle": 3600,
    }


engine = create_async_engine(settings.database_url, **opciones_de_engine(settings.database_url))

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
