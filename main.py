from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.agent.graph import setup_checkpointer, shutdown_checkpointer
from app.config import settings
from app.database import AsyncSessionLocal
from app.limiter import limiter
from app.routers import assets, chat, ingest, match, review, vision


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Contexto AI API iniciando...")
    await setup_checkpointer()
    yield
    print("Contexto AI API apagando...")
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
app.include_router(chat.router)
app.include_router(vision.router)
app.include_router(ingest.router)
app.include_router(review.router)
app.include_router(match.router)


@app.get("/health", tags=["System"])
async def health_check():
    """Verifica que la API responde Y que la base de datos es alcanzable."""
    db_ok = False
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    status = "healthy" if db_ok else "degraded"
    return {
        "status": status,
        "service": "Contexto AI V2",
        "database": "up" if db_ok else "down",
    }
