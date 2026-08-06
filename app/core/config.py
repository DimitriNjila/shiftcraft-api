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
    GROQ_VISION_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"

    # Observability
    SENTRY_DSN: Optional[str] = None

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
