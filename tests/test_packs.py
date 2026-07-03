"""Tests for pack service — GET /packs."""

from __future__ import annotations

import uuid

from app.services import pack_service
from tests.fake_supabase import FakeSupabaseClient

_PACK_STARTER = str(uuid.uuid4())
_PACK_UNLIMITED = str(uuid.uuid4())
_CITY_PUBLISHED = str(uuid.uuid4())
_CITY_DRAFT = str(uuid.uuid4())


def _make_db() -> FakeSupabaseClient:
    db = FakeSupabaseClient()
    db.seed(
        "packs",
        [
            {
                "id": _PACK_UNLIMITED,
                "name": "Unlimited",
                "price_eur": 49.99,
                "city_count": None,
                "is_unlimited": True,
                "store_product_id": "com.bonvivant.pack.unlimited",
            },
            {
                "id": _PACK_STARTER,
                "name": "Starter",
                "price_eur": 9.99,
                "city_count": 3,
                "is_unlimited": False,
                "store_product_id": "com.bonvivant.pack.starter",
            },
        ],
    )
    db.seed(
        "cities",
        [
            {
                "id": _CITY_PUBLISHED,
                "slug": "barcelona",
                "name": "Barcelona",
                "status": "published",
            },
            {
                "id": _CITY_DRAFT,
                "slug": "marseille",
                "name": "Marseille",
                "status": "draft",
            },
        ],
    )
    db.seed(
        "pack_cities",
        [
            {"pack_id": _PACK_STARTER, "city_id": _CITY_PUBLISHED},
            {"pack_id": _PACK_STARTER, "city_id": _CITY_DRAFT},
            {"pack_id": _PACK_UNLIMITED, "city_id": _CITY_PUBLISHED},
        ],
    )
    return db


async def test_get_packs_sorted_by_price_with_published_cities_only() -> None:
    db = _make_db()

    result = await pack_service.get_packs(db)

    assert [p.name for p in result.packs] == ["Starter", "Unlimited"]

    starter = result.packs[0]
    # Draft city is excluded from the storefront.
    assert [c.slug for c in starter.cities] == ["barcelona"]
    assert starter.store_product_id == "com.bonvivant.pack.starter"
    assert result.packs[1].is_unlimited is True
    assert result.packs[1].city_count is None


async def test_get_packs_empty_db_returns_empty_list() -> None:
    db = FakeSupabaseClient()
    result = await pack_service.get_packs(db)
    assert result.packs == []
