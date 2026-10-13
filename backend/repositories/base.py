from typing import Optional, Any
from backend.core.config import get_settings
from backend.core.logging import get_logger

logger = get_logger("ThothRepositories")

class SupabaseClientProvider:
    def __init__(self):
        self._client: Optional[Any] = None
        self._checked: bool = False

    def get_client(self) -> Optional[Any]:
        if not self._checked and self._client is None:
            settings = get_settings()
            url = settings.SUPABASE_URL
            key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY

            if url and key:
                try:
                    from supabase import create_client, Client
                    self._client = create_client(url, key)
                    logger.info(f"Supabase client initialized for URL: {url}")
                except Exception as e:
                    logger.warning(f"Could not initialize Supabase client: {e}. Falling back to SQLite.")
                    self._client = None
            else:
                logger.debug("Supabase URL or Key not set. Operating in SQLite/local mode.")
            self._checked = True

        return self._client

    def is_available(self) -> bool:
        return self.get_client() is not None

supabase_provider = SupabaseClientProvider()
