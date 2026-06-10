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


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Dependency that enforces admin role.

    Checks both the top-level 'role' claim and app_metadata.role, since
    Supabase can place custom roles in either location depending on configuration.
    """
    app_role = (user.get("app_metadata") or {}).get("role")
    direct_role = user.get("role")
    if app_role != "admin" and direct_role != "admin":
        raise AppError(403, "Admin access required", "admin_required")
    return user


def get_db() -> AsyncClient:
    return get_supabase_client()
