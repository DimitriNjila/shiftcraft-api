from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: Literal["development", "production"] = "development"

    # Database
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
