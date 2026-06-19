from __future__ import annotations

from app.schemas.user import UserProfile, UserProfileUpdate
from app.services.exceptions import UserNotFoundError
from supabase._async.client import AsyncClient


async def get_user_profile(user_id: str, db: AsyncClient) -> UserProfile:
    response = (
        await db.table("profiles").select("*").eq("id", user_id).limit(1).execute()
    )
    if not response.data:
        raise UserNotFoundError(user_id)
    row = response.data[0]
    return _row_to_profile(row)


async def update_user_profile(
    user_id: str, patch: UserProfileUpdate, db: AsyncClient
) -> UserProfile:
    fields = patch.model_dump(exclude_unset=True)
    if fields:
        await db.table("profiles").update(fields).eq("id", user_id).execute()
    return await get_user_profile(user_id, db)


def _row_to_profile(row: dict) -> UserProfile:
    return UserProfile(
        id=str(row["id"]),
        email=row["email"],
        full_name=row.get("full_name"),
        cruise_departure_date=row.get("cruise_departure_date"),
        member_since=row["created_at"],
        onboarding_completed=bool(row.get("onboarding_completed", False)),
    )
