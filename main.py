from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.agent.graph import setup_checkpointer, shutdown_checkpointer, get_checkpointer
from app.config import settings
from app.database import AsyncSessionLocal
from app.limiter import limiter
from app.routers import alertas, assets, auth, chat, ingest, match, review, vision, visitas


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Contexto AI API iniciando...")
    await setup_checkpointer()
    # CRM Vivo: comparte el mismo checkpointer Postgres → el hilo del corredor persiste.
    from app.agent.crm_graph import setup_crm_checkpointer
    setup_crm_checkpointer(get_checkpointer())
    # Cron de reenganche: tarea de fondo DENTRO de la app (no un servicio aparte).
    # Barre leads dormidos y avisa al corredor por push+email. Ver app/reenganche_cron.
    from app.reenganche_cron import iniciar_cron, detener_cron
    from app.rescate_avisos import iniciar_rescate, detener_rescate
    iniciar_cron()
    # Rescate: el ÚNICO correo que genera una conversación, y solo si el aviso lleva
    # horas sin leer en la campana. Ver app/rescate_avisos.py.
    iniciar_rescate()
    # Los canales de aviso se comprueban AL ARRANCAR y se reporta al OPERADOR, no al
    # usuario: un corredor no puede arreglar una clave del servidor ni tiene a quién
    # reportarla. Ver app/notifications.revisar_canales.
    from app.notifications import revisar_canales, disparar as _disparar
    _disparar(revisar_canales())
    yield
    print("Contexto AI API apagando...")
    await detener_cron()
    await detener_rescate()
    await shutdown_checkpointer()


app = FastAPI(
    title="Contexto AI",
    description="Catastro Vivo e Inmutable — API de Inteligencia Inmobiliaria",
    version="2.0.0",
    lifespan=lifespan,
)

# Adjuntar limiter a la app para que los decoradores @limiter.limit() funcionen
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — solo orígenes explícitos en producción
_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

app.include_router(assets.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(vision.router)
app.include_router(ingest.router)
app.include_router(review.router)
app.include_router(match.router)
app.include_router(visitas.router)
app.include_router(alertas.router)


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt() -> PlainTextResponse:
    """Le dice a los crawlers que NO indexen la API (la data vive aquí)."""
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


@app.get("/health", tags=["System"])
async def health_check():
    """Responde la API + base alcanzable + MEMORIA (checkpointer) persistente.

    Lo tercero existe por el incidente del 2026-08-18: el checkpointer puede caer a
    MemorySaver al arrancar (típicamente por el techo de 15 del pooler) y la app sigue
    respondiendo 200 en TODO, pero sin historial — conversaciones sin título que no
    abren. Un chequeo que solo mira "¿responde?" no lo ve; corrió 1h26m sin detectarse.
    Ver docs/INCIDENTE_2026-08-18_Pools.md.

    Sigue devolviendo HTTP 200 aunque la memoria esté rota, A PROPÓSITO: `render.yaml`
    apunta su healthCheckPath aquí, y fallar haría que Render reinicie en bucle justo
    cuando faltan conexiones — empeorando la causa. Degradado-pero-sirviendo fue mejor
    que caído. El aviso va en el CUERPO: un monitor externo debe alertar sobre
    `status != "healthy"`, no sobre el código HTTP.
    """
    db_ok = False
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    # None = el pool Postgres no se montó y el grafo corre con MemorySaver.
    memoria_ok = get_checkpointer() is not None

    return {
        "status": "healthy" if (db_ok and memoria_ok) else "degraded",
        "service": "Contexto AI V2",
        "database": "up" if db_ok else "down",
        # "volatil" = las conversaciones NO persisten; reiniciar el servicio.
        "memoria": "postgres" if memoria_ok else "volatil",
    }
