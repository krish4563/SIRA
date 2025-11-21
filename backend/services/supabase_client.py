# services/supabase_client.py

import logging
from typing import Optional

from config import settings
from supabase import Client, create_client  # pip install supabase

logger = logging.getLogger(__name__)

_supabase: Optional[Client] = None


def get_supabase() -> Client:
    """
    Lazily initialize a single Supabase client for the backend.
    Uses the service role key (server-side only).
    """
    global _supabase
    if _supabase is None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("Supabase URL or service role key missing in env")
        _supabase = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
        logger.info("[SUPABASE] Client initialized")
    return _supabase
