"""Tests for image path convention, signed URL resolution and guide integration."""

from __future__ import annotations

import uuid

from app.services import guide_service, image_service
from tests.fake_supabase import FakeSupabaseClient

# ============================================================
# 1. build_storage_path — exact filename convention per slot
# ============================================================


def test_build_storage_path_single_slot_has_no_index() -> None:
    path = image_service.build_storage_path("yokohama", "key_historical_context")
    assert path == "media/media-guias/yokohama/yokohama_key_historical_context.jpg"


def test_build_storage_path_gallery_without_zero_padding() -> None:
    path = image_service.build_storage_path("yokohama", "attraction", 1)
    assert path == "media/media-guias/yokohama/yokohama_attraction_1.jpg"


def test_build_storage_path_gourmet_without_zero_padding() -> None:
    path = image_service.build_storage_path("yokohama", "gourmet", 6)
    assert path == "media/media-guias/yokohama/yokohama_gourmet_6.jpg"


def test_build_storage_path_gallery_with_zero_padding() -> None:
    path = image_service.build_storage_path("yokohama", "overview_highlight", 1)
    assert path == "media/media-guias/yokohama/yokohama_overview_highlight_01.jpg"


def test_build_storage_path_port_with_zero_padding() -> None:
    path = image_service.build_storage_path("yokohama", "port", 1)
    assert path == "media/media-guias/yokohama/yokohama_port_01.jpg"


# ============================================================
# 2. get_signed_url / resolve_single — mocked Storage client
# ============================================================


async def test_resolve_single_returns_url_when_file_exists() -> None:
    db = FakeSupabaseClient()
    path = image_service.build_storage_path("yokohama", "overview")
    db.storage.existing_paths.add(path)

    url = await image_service.resolve_single(db, "yokohama", "overview")

    assert url == f"https://signed.example.com/{path}"


async def test_resolve_single_returns_none_when_file_missing() -> None:
    db = FakeSupabaseClient()

    url = await image_service.resolve_single(db, "yokohama", "cover")

    assert url is None


# ============================================================
# 3. resolve_gallery — partial galleries omit missing entries
# ============================================================


async def test_resolve_gallery_omits_missing_entries() -> None:
    db = FakeSupabaseClient()
    db.storage.existing_paths.add(
        image_service.build_storage_path("yokohama", "attraction", 1)
    )
    db.storage.existing_paths.add(
        image_service.build_storage_path("yokohama", "attraction", 3)
    )
    # index 2 is intentionally missing

    urls = await image_service.resolve_gallery(db, "yokohama", "attraction", count=3)

    assert len(urls) == 2


async def test_resolve_gallery_empty_when_nothing_exists() -> None:
    db = FakeSupabaseClient()

    urls = await image_service.resolve_gallery(db, "yokohama", "port", count=2)

    assert urls == []


# ============================================================
# 4. guide_service integration — images attached to CityGuide
# ============================================================

_CITY_ID = str(uuid.uuid4())
_SPOT1_ID = str(uuid.uuid4())
_SPOT2_ID = str(uuid.uuid4())
CITY_SLUG = "test-city"
USER_ID = "user-1"


def _city_row() -> dict:
    return {
        "id": _CITY_ID,
        "slug": CITY_SLUG,
        "name": "Test City",
        "country_code": "JP",
        "tagline": {"es": "Tagline"},
        "intro": {"es": "Intro"},
        "historical_context": {"es": "Historia"},
        "highlights": [],
        "port_description": {"es": "Puerto"},
        "distance_to_center": {"es": "5 min"},
        "port_facilities": {"es": "Básico"},
        "port_recommendation": {"es": "Taxi"},
        "transport_options": [],
        "what_to_know": [],
        "port_lat": None,
        "port_lng": None,
        "status": "published",
        "last_verified": None,
    }


def _spot_row(spot_id: str, kind: str, rank: int) -> dict:
    return {
        "id": spot_id,
        "city_id": _CITY_ID,
        "kind": kind,
        "category": None,
        "name": f"Spot {rank}",
        "address": "Some address",
        "latitude": None,
        "longitude": None,
        "distance_from_port_km": None,
        "rank_order": rank,
        "website": None,
        "manuel_quote": {"es": "Quote"},
        "reservation": None,
        "what_it_is": None,
        "why_it_matters": None,
        "good_to_know": None,
        "cuisine_type": None,
        "category_label": None,
        "must_try": None,
        "best_time": None,
    }


async def test_get_city_guide_attraction_gallery_matches_existing_files() -> None:
    db = FakeSupabaseClient()
    db.seed("cities", [_city_row()])
    db.seed(
        "spots",
        [
            _spot_row(_SPOT1_ID, "attraction", 1),
            _spot_row(_SPOT2_ID, "attraction", 2),
        ],
    )
    db.seed("itineraries", [])
    db.seed("itinerary_steps", [])
    db.seed("tips", [])
    db.seed("user_purchases", [])
    db.seed("pack_cities", [])
    db.seed("packs", [])

    # Only the first attraction photo exists in Storage.
    db.storage.existing_paths.add(
        image_service.build_storage_path(CITY_SLUG, "attraction", 1)
    )

    result = await guide_service.get_city_guide(
        db, CITY_SLUG, USER_ID, require_access=False
    )

    assert len(result.spots) == 2
    assert len(result.images.attraction_gallery) == 1


async def test_get_city_guide_missing_photos_leave_fields_none() -> None:
    db = FakeSupabaseClient()
    db.seed("cities", [_city_row()])
    db.seed("spots", [])
    db.seed("itineraries", [])
    db.seed("itinerary_steps", [])
    db.seed("tips", [])
    db.seed("user_purchases", [])
    db.seed("pack_cities", [])
    db.seed("packs", [])

    result = await guide_service.get_city_guide(
        db, CITY_SLUG, USER_ID, require_access=False
    )

    assert result.images.cover is None
    assert result.images.overview is None
    assert result.images.attraction_gallery == []
