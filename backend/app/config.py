"""
Application settings, loaded from environment variables.

DATABASE_URL is the single source of truth for the DB connection in both
local (docker-compose postgres) and production (GCP Cloud SQL) environments.
"""
import os
from functools import lru_cache
from dotenv import load_dotenv
from pathlib import Path

# Load dotenv relative to this config file (looks for .env in the parent backend directory)
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./voice_orchestrator.db",
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
