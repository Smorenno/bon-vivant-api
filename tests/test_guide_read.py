"""Tests for city guide read service and HTTP endpoints."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.exceptions import CityLockedError, CityNotFoundError
from app.main import app
from app.models.city import LocalizedText
from app.services import guide_service
from tests.fake_supabase import FakeSupabaseClient

# ============================================================
# Shared test data (module-level constants, evaluated once)
# ============================================================

_CITY_ID = str(uuid.uuid4())
_DRAFT_ID = str(uuid.uuid4())
_SPOT1_ID = str(uuid.uuid4())
_ITIN1_ID = str(uuid.uuid4())  # regular (day)
_ITIN2_ID = str(uuid.uuid4())  # premium (night)
_STEP1_ID = str(uuid.uuid4())  # linked to _SPOT1_ID
_STEP2_ID = str(uuid.uuid4())  # generic (no spot)
_TIP1_ID = str(uuid.uuid4())
_PACK_ID = str(uuid.uuid4())

CITY_SLUG = "test-city"
LOCKED_USER = "user-locked"
UNLOCKED_USER = "user-unlocked"


def _city_row(city_id: str, slug: str, status: str) -> dict:
    return {
        "id": city_id,
        "slug": slug,
        "name": "Test City",
        "country_code": "JP",
        "tagline": {"es": "La ciudad de prueba", "en": "The test city"},
        "intro": {"es": "Introducción"},
        "historical_context": {"es": "Historia"},
        "highlights": [],
        "port_description": {"es": "Puerto principal"},
        "distance_to_center": {"es": "5 min"},
        "port_facilities": {"es": "Básico"},
        "port_recommendation": {"es": "Taxi"},
        "transport_options": [],
        "what_to_know": [],
        "port_lat": None,
        "port_lng": None,
        "status": status,
        "last_verified": None,
    }


@pytest.fixture
def guide_db() -> FakeSupabaseClient:
    db = FakeSupabaseClient()

    db.seed(
        "cities",
        [
            _city_row(_CITY_ID, CITY_SLUG, "published"),
            _city_row(_DRAFT_ID, "draft-city", "draft"),
        ],
    )

    db.seed(
        "spots",
        [
            {
                "id": _SPOT1_ID,
                "city_id": _CITY_ID,
                "kind": "attraction",
                "category": None,
                "name": "Templo Central",
                "address": "1-1 Templo St",
                "latitude": None,
                "longitude": None,
                "distance_from_port_km": 2.0,
                "rank_order": 1,
                "website": "https://templo.example.com",
                "manuel_quote": {"es": "El templo más visitado"},
                "reservation": None,
                "what_it_is": None,
                "why_it_matters": None,
                "good_to_know": None,
                "cuisine_type": None,
                "category_label": None,
                "must_try": None,
                "best_time": None,
            }
        ],
    )

    db.seed(
        "itineraries",
        [
            {
                "id": _ITIN1_ID,
                "city_id": _CITY_ID,
                "theme": "4h",
                "time_of_day": "day",
                "title": {"es": "Mañana esencial"},
                "catchy_phrase": {"es": "Lo más importante"},
                "best_for": {"es": "Primera visita"},
                "duration_min_hrs": 3.5,
                "duration_max_hrs": 4.5,
                "total_walk_km": 2.0,
                "total_transit_km": None,
                "flex_note": {"es": "Puedes acortar"},
                "is_recommended": True,
                "is_premium": False,
                "rank_order": 1,
            },
            {
                "id": _ITIN2_ID,
                "city_id": _CITY_ID,
                "theme": "night",
                "time_of_day": "night",
                "title": {"es": "Noche premium"},
                "catchy_phrase": {"es": "La experiencia VIP"},
                "best_for": {"es": "Segunda visita"},
                "duration_min_hrs": 3.0,
                "duration_max_hrs": 5.0,
                "total_walk_km": 1.0,
                "total_transit_km": None,
                "flex_note": {"es": "Reserva con antelación"},
                "is_recommended": False,
                "is_premium": True,
                "rank_order": 2,
            },
        ],
    )

    db.seed(
        "itinerary_steps",
        [
            {
                "id": _STEP1_ID,
                "itinerary_id": _ITIN1_ID,
                "rank_order": 1,
                "spot_id": _SPOT1_ID,
                "title": None,
                "address": None,
                "description": {"es": "El templo principal de la ciudad"},
                "bon_vivant_notes": None,
                "must_try": None,
                "reservation": None,
                "website": None,
                "distance_from_prev_km": None,
                "travel_mode": None,
                "time_on_site_min": None,
                "time_on_site_max": None,
            },
            {
                "id": _STEP2_ID,
                "itinerary_id": _ITIN2_ID,
                "rank_order": 1,
                "spot_id": None,
                "title": {"es": "Vuelta al barco"},
                "address": "Puerto principal",
                "description": {"es": "Regreso"},
                "bon_vivant_notes": None,
                "must_try": None,
                "reservation": None,
                "website": None,
                "distance_from_prev_km": None,
                "travel_mode": "walk",
                "time_on_site_min": None,
                "time_on_site_max": None,
            },
        ],
    )

    db.seed(
        "tips",
        [
            {
                "id": _TIP1_ID,
                "city_id": _CITY_ID,
                "title": {"es": "Consejo útil"},
                "body": {"es": "Lleva efectivo"},
                "rank_order": 1,
            }
        ],
    )

    # UNLOCKED_USER has a valid purchase for a pack that includes the city.
    db.seed(
        "user_purchases",
        [
            {
                "id": str(uuid.uuid4()),
                "user_id": UNLOCKED_USER,
                "pack_id": _PACK_ID,
                "is_valid": True,
            }
        ],
    )
    db.seed(
        "pack_cities",
        [{"id": str(uuid.uuid4()), "pack_id": _PACK_ID, "city_id": _CITY_ID}],
    )
    # No unlimited packs → premium itineraries are always locked.
    db.seed("packs", [])

    return db


# ============================================================
# Helper for HTTP tests (overrides deps, skips lifespan)
# ============================================================


def _http_get(
    db: FakeSupabaseClient, user_id: str, path: str, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    """Return the response of a single GET request with mocked auth and DB."""

    async def _noop() -> None:
        pass

    monkeypatch.setattr("app.main.init_supabase", _noop)
    monkeypatch.setattr("app.main.close_supabase", _noop)
    app.dependency_overrides[deps.get_current_user] = lambda: {"sub": user_id}
    app.dependency_overrides[deps.get_db] = lambda: db
    with TestClient(app) as client:
        response = client.get(path)
    app.dependency_overrides.clear()
    return response


# ============================================================
# 1. list_cities — published only, is_unlocked per user
# ============================================================


async def test_list_cities_returns_only_published(guide_db: FakeSupabaseClient) -> None:
    result = await guide_service.list_cities(guide_db, LOCKED_USER)
    assert len(result) == 1
    assert result[0].slug == CITY_SLUG
    assert result[0].status.value == "published"


async def test_list_cities_is_unlocked_reflects_purchases(
    guide_db: FakeSupabaseClient,
) -> None:
    locked = await guide_service.list_cities(guide_db, LOCKED_USER)
    unlocked = await guide_service.list_cities(guide_db, UNLOCKED_USER)
    assert locked[0].is_unlocked is False
    assert unlocked[0].is_unlocked is True


# ============================================================
# 2. get_city_guide — full guide for unlocked user
# ============================================================


async def test_get_city_guide_unlocked_returns_full_guide(
    guide_db: FakeSupabaseClient,
) -> None:
    result = await guide_service.get_city_guide(guide_db, CITY_SLUG, UNLOCKED_USER)
    assert result.slug == CITY_SLUG
    assert result.is_unlocked is True
    assert len(result.spots) == 1
    assert len(result.itineraries) == 2
    assert len(result.tips) == 1


async def test_get_city_guide_step_resolves_spot_data(
    guide_db: FakeSupabaseClient,
) -> None:
    """Steps with spot_id must carry name/address/website from the linked spot."""
    result = await guide_service.get_city_guide(guide_db, CITY_SLUG, UNLOCKED_USER)
    regular = next(i for i in result.itineraries if not i.is_premium)
    step = regular.steps[0]

    assert step.spot_id is not None
    assert step.name == "Templo Central"
    assert step.address == "1-1 Templo St"
    assert step.website == "https://templo.example.com"


async def test_get_city_guide_generic_step_has_no_name(
    guide_db: FakeSupabaseClient,
) -> None:
    result = await guide_service.get_city_guide(guide_db, CITY_SLUG, UNLOCKED_USER)
    premium = next(i for i in result.itineraries if i.is_premium)
    step = premium.steps[0]

    assert step.spot_id is None
    assert step.name is None
    assert step.address == "Puerto principal"


# ============================================================
# 3. get_city_guide — access control
# ============================================================


async def test_get_city_guide_locked_raises_city_locked_error(
    guide_db: FakeSupabaseClient,
) -> None:
    with pytest.raises(CityLockedError):
        await guide_service.get_city_guide(guide_db, CITY_SLUG, LOCKED_USER)


async def test_get_city_guide_nonexistent_raises_city_not_found(
    guide_db: FakeSupabaseClient,
) -> None:
    with pytest.raises(CityNotFoundError):
        await guide_service.get_city_guide(guide_db, "does-not-exist", UNLOCKED_USER)


async def test_get_city_guide_draft_raises_city_not_found(
    guide_db: FakeSupabaseClient,
) -> None:
    with pytest.raises(CityNotFoundError):
        await guide_service.get_city_guide(guide_db, "draft-city", UNLOCKED_USER)


# ============================================================
# 4. get_city_preview — no access gate, first tip only
# ============================================================


async def test_get_city_preview_requires_no_access(
    guide_db: FakeSupabaseClient,
) -> None:
    result = await guide_service.get_city_preview(guide_db, CITY_SLUG, LOCKED_USER)
    assert result.slug == CITY_SLUG
    assert result.is_unlocked is False
    assert len(result.tips) == 1


async def test_get_city_preview_nonexistent_raises_city_not_found(
    guide_db: FakeSupabaseClient,
) -> None:
    with pytest.raises(CityNotFoundError):
        await guide_service.get_city_preview(guide_db, "does-not-exist", LOCKED_USER)


# ============================================================
# 5. Premium itinerary locking
# ============================================================


async def test_premium_itinerary_locked_without_pass(
    guide_db: FakeSupabaseClient,
) -> None:
    result = await guide_service.get_city_guide(guide_db, CITY_SLUG, UNLOCKED_USER)
    premium = next(i for i in result.itineraries if i.is_premium)
    regular = next(i for i in result.itineraries if not i.is_premium)

    # No unlimited pack seeded → premium is locked; regular is not.
    assert premium.is_locked is True
    assert regular.is_locked is False


async def test_premium_itinerary_present_in_response_even_when_locked(
    guide_db: FakeSupabaseClient,
) -> None:
    """Locked premium itineraries are included — the client decides what to show."""
    result = await guide_service.get_city_guide(guide_db, CITY_SLUG, UNLOCKED_USER)
    assert len(result.itineraries) == 2


# ============================================================
# 6. LocalizedText serialised as {es, en, fr} object (Variante C)
# ============================================================


async def test_localized_fields_are_objects_not_strings(
    guide_db: FakeSupabaseClient,
) -> None:
    result = await guide_service.get_city_guide(guide_db, CITY_SLUG, UNLOCKED_USER)
    assert isinstance(result.tagline, LocalizedText)
    assert result.tagline.es == "La ciudad de prueba"
    assert result.tagline.en == "The test city"
    assert isinstance(result.tips[0].title, LocalizedText)
    assert isinstance(result.spots[0].manuel_quote, LocalizedText)


# ============================================================
# 7. HTTP status codes (TestClient + dependency overrides)
# ============================================================


def test_http_locked_city_returns_403(
    guide_db: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = _http_get(guide_db, LOCKED_USER, f"/api/v1/cities/{CITY_SLUG}", monkeypatch)
    assert r.status_code == 403
    assert r.json()["code"] == "city_locked"


def test_http_nonexistent_city_returns_404(
    guide_db: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = _http_get(guide_db, UNLOCKED_USER, "/api/v1/cities/does-not-exist", monkeypatch)
    assert r.status_code == 404
    assert r.json()["code"] == "city_not_found"


def test_http_draft_city_returns_404(
    guide_db: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = _http_get(guide_db, UNLOCKED_USER, "/api/v1/cities/draft-city", monkeypatch)
    assert r.status_code == 404


def test_http_preview_returns_200_without_purchase(
    guide_db: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = _http_get(
        guide_db, LOCKED_USER, f"/api/v1/cities/{CITY_SLUG}/preview", monkeypatch
    )
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == CITY_SLUG
    assert body["is_unlocked"] is False
