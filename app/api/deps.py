from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_jwt
from app.db.supabase import get_supabase_client
from app.exceptions import AppError
from supabase._async.client import AsyncClient

# auto_error=False so we can raise 401 (not the default 403) when the header
# is absent — HTTP spec: 401 = unauthenticated, 403 = authenticated but forbidden.
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if credentials is None:
        raise AppError(401, "Authentication required", "unauthenticated")
    try:
        return decode_jwt(credentials.credentials)
    except ValueError as exc:
        raise AppError(401, "Invalid or expired token", str(exc)) from exc


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Dependency that enforces the admin role.

    The ONLY authoritative source is app_metadata.role, which is set
    server-side via the Supabase Admin API and cannot be forged by the client:

        PATCH https://<project>.supabase.co/auth/v1/admin/users/<user_id>
        Authorization: Bearer <service_role_key>
        { "app_metadata": { "role": "admin" } }

    Until at least one user has that claim, /admin/* endpoints are inaccessible
    to everyone — which is the correct secure default.

    The top-level `role` claim is deliberately NOT trusted: in Supabase JWTs it
    carries the Postgres role ("authenticated"), which is not an application role
    and must never grant admin access.
    """
    app_role = (user.get("app_metadata") or {}).get("role")
    if app_role != "admin":
        raise AppError(403, "Admin access required", "admin_required")
    return user


def get_db() -> AsyncClient:
    return get_supabase_client()
