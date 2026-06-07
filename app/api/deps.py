from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_jwt
from app.db.supabase import get_supabase_client
from app.exceptions import AppError
from supabase import AsyncClient

_bearer = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    try:
        return decode_jwt(credentials.credentials)
    except ValueError as exc:
        raise AppError(401, "Invalid or expired token", str(exc)) from exc


def get_db() -> AsyncClient:
    return get_supabase_client()
