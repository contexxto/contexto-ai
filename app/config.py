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

    # En producción (Render + Supabase) se puede pasar la DATABASE_URL completa
    # para evitar problemas de IPv6. Si está presente, tiene precedencia.
    database_url_override: str = ""

    # Seguridad — Fase 3
    # ALLOWED_ORIGINS: lista separada por comas de orígenes permitidos
    # API_KEY: clave que el frontend debe enviar en header X-API-Key
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"
    api_key: str = ""  # si está vacío, el check se desactiva (dev local)

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
