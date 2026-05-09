from functools import lru_cache
from supabase import create_client, Client


@lru_cache()
def get_supabase() -> Client:
    """
    Get the Supabase client singleton — lazy-loaded on first access so that
    environment variables are guaranteed to be set by the time we read them.
    Cached for the lifetime of the process via lru_cache.
    """
    # Import inside the function to avoid reading env vars at module-import time
    # (critical for serverless cold-start reliability).
    from app.core.config import settings
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
