from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.graph import setup_checkpointer
from app.routers import assets, chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Contexto AI API iniciando...")
    await setup_checkpointer()
    print("  Checkpointer de sesiones activo (Supabase)")
    yield
    print("Contexto AI API apagando...")


app = FastAPI(
    title="Contexto AI",
    description="Catastro Vivo e Inmutable — API de Inteligencia Inmobiliaria",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assets.router)
app.include_router(chat.router)


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "healthy", "service": "Contexto AI V2"}
