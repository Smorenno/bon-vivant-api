from app.config import settings
from supabase import AsyncClient, acreate_client

_client: AsyncClient | None = None


async def init_supabase() -> None:
    global _client
    _client = await acreate_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )


async def close_supabase() -> None:
    global _client
    _client = None


def get_supabase_client() -> AsyncClient:
    if _client is None:
        raise RuntimeError("Supabase client not initialised — check lifespan setup")
    return _client
