from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.agent.graph import setup_checkpointer, shutdown_checkpointer
from app.config import settings
from app.limiter import limiter
from app.routers import assets, chat


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
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(assets.router)
app.include_router(chat.router)


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "healthy", "service": "Contexto AI V2"}
