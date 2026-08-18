from pydantic_settings import BaseSettings
from typing import List, Literal, Optional


class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: Literal["development", "production"] = "development"

    # Database
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str

    # CORS origins
    CORS_ORIGINS: str

    @property
    def cors_origins_list(self) -> List[str]:
        """Convert comma-separated string to list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    # AI
    GROQ_API_KEY: Optional[str] = None
    # Vision-capable Groq model for image-based template import. Groq's model
    # catalog changes over time — override here (env var) if this ID is
    # retired; no code change needed for a same-provider model swap.
    # meta-llama/llama-4-scout-17b-16e-instruct was shut down by Groq on
    # 2026-07-17; qwen/qwen3.6-27b is their documented vision replacement.
    GROQ_VISION_MODEL: str = "qwen/qwen3.6-27b"
    # Text-only Groq model for schedule analysis. Was llama-3.3-70b-versatile
    # until Groq discontinued it; gpt-oss-120b is the current, larger open
    # replacement and honours response_format=json_object cleanly.
    # Env-overridable so a future retirement is one .env line, not a deploy.
    GROQ_TEXT_MODEL: str = "openai/gpt-oss-120b"

    # Observability
    SENTRY_DSN: Optional[str] = None

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
