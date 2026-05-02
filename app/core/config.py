from pydantic_settings import BaseSettings
from typing import Literal, Optional


class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: Literal["development", "production"] = "development"

    # Database
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str

    # AI
    ANTHROPIC_API_KEY: Optional[str] = None

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
