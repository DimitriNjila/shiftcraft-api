from pydantic_settings import BaseSettings
from typing import List, Literal, Optional


class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: Literal["development", "production"] = "development"

    # Database
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str

    # CORS origins
    CORS_ORIGINS: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        """Convert comma-separated string to list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    # AI
    ANTHROPIC_API_KEY: Optional[str] = None

    # Observability
    SENTRY_DSN: Optional[str] = None

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
