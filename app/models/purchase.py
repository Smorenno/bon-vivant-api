from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

StorePlatform = Literal["ios", "android"]


class PackSummary(BaseModel):
    id: UUID
    name: str
    is_unlimited: bool
    city_count: int | None  # None for unlimited packs


class PurchaseResponse(BaseModel):
    id: UUID
    pack_id: UUID
    purchased_at: datetime
    is_valid: bool
    pack: PackSummary


class PurchasesListResponse(BaseModel):
    purchases: list[PurchaseResponse]


class PurchaseValidationRequest(BaseModel):
    """Client-submitted purchase to be verified server-side.

    `receipt` carries the store's proof of purchase:
      - ios: the StoreKit 2 transaction id (`Transaction.id`)
      - android: the Play Billing purchase token
    Neither is trusted as-is — both are re-fetched from the store.
    """

    receipt: str = Field(min_length=1, max_length=4096)
    platform: StorePlatform
    product_id: str = Field(min_length=1, max_length=255)


class PurchaseValidationResponse(BaseModel):
    purchase: PurchaseResponse
    unlocked_city_ids: list[UUID]


class RestoreRequest(BaseModel):
    """Everything the store client reports as owned (StoreKit
    currentEntitlements / Play queryPurchases), re-submitted for sync."""

    purchases: list[PurchaseValidationRequest] = Field(
        default_factory=list, max_length=50
    )


class RestoreResponse(BaseModel):
    restored: int
    already_owned: int
    failed: int
    purchases: list[PurchaseResponse]
