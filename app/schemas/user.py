from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, field_validator


class UserProfile(BaseModel):
    id: str
    email: str
    full_name: str | None
    cruise_departure_date: date | None
    member_since: datetime
    onboarding_completed: bool


class UserProfileUpdate(BaseModel):
    full_name: str | None = None
    cruise_departure_date: date | None = None

    @field_validator("full_name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("full_name must not be blank")
        return v
