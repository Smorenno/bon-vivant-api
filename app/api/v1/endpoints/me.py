from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_db
from app.models.city import ErrorResponse
from app.schemas.user import UserProfile, UserProfileUpdate
from app.services import user_service
from app.services.exceptions import UserNotFoundError
from supabase._async.client import AsyncClient

router = APIRouter(prefix="/me", tags=["me"])

_ERR = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


@router.get("", response_model=UserProfile, responses=_ERR)
async def get_me(
    user: dict = Depends(get_current_user),
    db: AsyncClient = Depends(get_db),
) -> UserProfile:
    try:
        return await user_service.get_user_profile(user["sub"], db)
    except UserNotFoundError:
        raise


@router.patch("", response_model=UserProfile, responses=_ERR)
async def patch_me(
    patch: UserProfileUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncClient = Depends(get_db),
) -> UserProfile:
    try:
        return await user_service.update_user_profile(user["sub"], patch, db)
    except UserNotFoundError:
        raise
