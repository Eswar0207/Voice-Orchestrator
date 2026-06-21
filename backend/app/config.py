"""
Application settings, loaded from environment variables.

DATABASE_URL is the single source of truth for the DB connection in both
local (docker-compose postgres) and production (GCP Cloud SQL) environments.
"""
import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@localhost:5432/voice_orchestrator",
    )

    # Simulation
    SIMULATION_MODE: bool = os.getenv("SIMULATION_MODE", "false").lower() in ("true", "1", "yes")

    # Vapi
    VAPI_PRIVATE_KEY: str = os.getenv("VAPI_PRIVATE_KEY", "")
    VAPI_ASSISTANT_ID: str = os.getenv("VAPI_ASSISTANT_ID", "")
    VAPI_PHONE_NUMBER_ID: str = os.getenv("VAPI_PHONE_NUMBER_ID", "")
    VAPI_WEBHOOK_SECRET: str = os.getenv("VAPI_WEBHOOK_SECRET", "")
    VAPI_API_BASE: str = os.getenv("VAPI_API_BASE", "https://api.vapi.ai")

    # LLM providers (evaluation node picks whichever key is present)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # App
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "local")  # local | production
    CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "*").split(",")
    PORT: int = int(os.getenv("PORT", "8000"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
