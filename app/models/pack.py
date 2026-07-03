from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class PackCity(BaseModel):
    """Minimal city info shown in the store before purchase."""

    id: UUID
    slug: str
    name: str


class PackDetail(BaseModel):
    id: UUID
    name: str
    price_eur: Decimal | None
    city_count: int | None  # None for the unlimited pack
    is_unlimited: bool
    store_product_id: str | None
    cities: list[PackCity]


class PacksListResponse(BaseModel):
    packs: list[PackDetail]
