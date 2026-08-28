import os

from dotenv import dotenv_values
from pydantic_settings import BaseSettings, SettingsConfigDict

# pydantic-settings prioriza variables del shell sobre .env por diseño.
# Si el shell tiene ANTHROPIC_API_KEY vacía (ej. configurada por otro programa),
# sobreescribirá el .env. Cargamos el .env explícitamente primero para
# garantizar que las claves del proyecto siempre tienen precedencia.
_env_file_values = dotenv_values(".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_ignore_empty=True,   # ignora variables del shell que estén vacías
    )

    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-5-20250929"
    ssl_verify: str = "true"

    # E3.2b.4 · shadow wiring del Buyer Updater. APAGADO por defecto, y el default es la
    # decisión: la cadena entera —intérprete, guarda, reducer, orquestador— corre sin
    # autoridad sobre la conversación, pero corre contra la memoria durable de una persona
    # real. Encenderlo es un acto deliberado por entorno, no algo que llegue con un deploy.
    buyer_updater_shadow: bool = False

    # En producción (Render + Supabase) se puede pasar la DATABASE_URL completa
    # para evitar problemas de IPv6. Si está presente, tiene precedencia.
    database_url_override: str = ""

    # ── Conexiones a Postgres — TECHO COMPARTIDO, no dos presupuestos ──────────
    # El Session Pooler de Supabase corta en 15 clientes POR PROYECTO, y contra ese
    # mismo techo tiran DOS pools independientes: el de SQLAlchemy (datos) y el del
    # AsyncPostgresSaver de LangGraph (checkpointer, en app/agent/graph.py). Sumarlos
    # por encima de 15 no falla ruidosamente: el checkpointer NO abre y el grafo se
    # degrada a MemorySaver en silencio — la app responde 200 en todo, pero sin
    # historial (títulos genéricos, conversaciones que no abren). Pasó en el deploy
    # del 2026-08-18, ver docs/INCIDENTE_2026-08-18_Pools.md.
    # Suma por defecto: (4+2) + 6 = 12, con 3 de margen para el resto.
    # OJO: dev local ataca la MISMA Supabase que producción — con ambos arriba se
    # duplica el consumo. Bajar estos valores en el .env local si conviven.
    db_pool_size: int = 4
    db_max_overflow: int = 2
    checkpointer_pool_size: int = 6

    # Seguridad — Fase 3
    # ALLOWED_ORIGINS: lista separada por comas de orígenes permitidos
    # API_KEY: clave que el frontend debe enviar en header X-API-Key
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"
    api_key: str = ""  # si está vacío, el check se desactiva (dev local)

    # Embeddings — Voyage AI (Fase B3). Vacío hasta configurar la key.
    voyage_api_key: str = ""
    voyage_model: str = "voyage-multimodal-3"

    # Google Maps Places — enriquecimiento del entorno (en vivo). Si está vacío,
    # caemos automáticamente a OpenStreetMap (base persistible del catastro).
    google_maps_api_key: str = ""

    # Valhalla auto-hospedado — isócronas peatonales propias (Ladrillo #7 del foso).
    # Docker en :8002 con tiles de Ecuador. Si no responde, las isócronas degradan
    # (el mapa no las pinta; la búsqueda por ancla cae a radio euclidiano).
    valhalla_url: str = "http://localhost:8002"

    # URL pública del frontend (para los QR de los letreros inteligentes,
    # enlaces de "Mis publicaciones" y links de los emails). Dominio de marca.
    public_app_url: str = "https://contexxto.com"

    # Supabase Auth — URL del proyecto (pública). El backend deriva el endpoint
    # JWKS para validar los JWT (ECC P-256/ES256). Vacío = auth desactivada.
    supabase_url: str = ""

    # Anti-SSRF para /assets/ingest: lista de hosts permitidos separada por comas.
    # Vacío = se permite cualquier host (modo pruebas). En producción real, fijar
    # al bucket de Supabase Storage. Ej: "images.unsplash.com,xxxx.supabase.co"
    ingest_allowed_image_hosts: str = ""

    # Entorno de ejecución. Vacío = se infiere (ver es_produccion). Ponerlo a mano solo
    # para forzar: ENVIRONMENT=production o ENVIRONMENT=dev.
    environment: str = ""

    @property
    def es_produccion(self) -> bool:
        """Si esto corre sirviendo a gente real.

        Existe para que una configuración AUSENTE no abra una puerta. Sin esto,
        verify_api_key trata "API_KEY vacía" como dev local y deja pasar a cualquiera:
        basta borrar la variable en el panel para desproteger la escritura del catastro
        sin un solo error en los logs.

        La inferencia usa RENDER, que Render inyecta solo en todos sus servicios. Se
        prefiere a una variable propia justamente porque no hay que acordarse de
        ponerla: si algún día se despliega en otro sitio, lo peor que pasa es que haya
        que declarar ENVIRONMENT=production a mano — un fallo ruidoso al arrancar, no
        una puerta abierta en silencio.
        """
        declarado = (self.environment or "").strip().lower()
        if declarado:
            return declarado.startswith("prod")
        return os.getenv("RENDER", "").strip().lower() in ("true", "1", "yes")

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
