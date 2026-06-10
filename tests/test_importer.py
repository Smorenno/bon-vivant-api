"""Tests for the city guide importer and admin edit services."""

from __future__ import annotations

import copy
import uuid

import pytest

from app.schemas.import_guide import (
    CityGuideImport,
    CityUpdate,
    ItineraryStepIn,
    LocalizedTextIn,
    SpotUpdate,
)
from app.services import city_service
from app.services.exceptions import (
    CitySlugExistsError,
    PublishedCityReplaceError,
    SpotNotFoundError,
    SpotRefNotFoundError,
)
from app.services.import_service import import_city_guide
from tests.fake_supabase import FakeSupabaseClient


# ============================================================
# Helpers
# ============================================================


def _deep_copy_guide(guide: CityGuideImport) -> CityGuideImport:
    return CityGuideImport.model_validate(guide.model_dump(by_alias=True))


# ============================================================
# 1. Valid import inserts all rows and returns correct result
# ============================================================


@pytest.mark.asyncio
async def test_import_valid_guide_inserts_all_rows(
    fake_db: FakeSupabaseClient,
    minimal_guide: CityGuideImport,
    null_geocoder: object,
) -> None:
    result = await import_city_guide(minimal_guide, null_geocoder, fake_db)

    assert result.slug == "test-city"
    assert result.status == "draft"
    assert result.replaced is False
    assert result.counts.attractions == 1
    assert result.counts.gourmet == 0
    assert result.counts.itineraries == 1
    assert result.counts.steps == 1
    assert result.counts.tips == 1

    assert len(fake_db.get_table("cities")) == 1
    assert fake_db.get_table("cities")[0]["slug"] == "test-city"
    assert fake_db.get_table("cities")[0]["status"] == "draft"

    assert len(fake_db.get_table("spots")) == 1
    assert fake_db.get_table("spots")[0]["name"] == "Templo Central"

    assert len(fake_db.get_table("itineraries")) == 1
    assert len(fake_db.get_table("itinerary_steps")) == 1
    assert len(fake_db.get_table("tips")) == 1


# ============================================================
# 2. spot_ref mismatch — SpotRefNotFoundError, no DB writes
# ============================================================


@pytest.mark.asyncio
async def test_invalid_spot_ref_raises_and_leaves_db_clean(
    fake_db: FakeSupabaseClient,
    minimal_guide: CityGuideImport,
    null_geocoder: object,
) -> None:
    minimal_guide.itineraries[0].steps[0].spot_ref = "Templo Inexistente"

    with pytest.raises(SpotRefNotFoundError) as exc_info:
        await import_city_guide(minimal_guide, null_geocoder, fake_db)

    assert exc_info.value.spot_ref == "Templo Inexistente"
    # Validation happens before any DB writes
    assert fake_db.get_table("cities") == []
    assert fake_db.get_table("spots") == []


# ============================================================
# 3. Duplicate slug with replace=False → CitySlugExistsError
# ============================================================


@pytest.mark.asyncio
async def test_duplicate_slug_no_replace_raises(
    fake_db: FakeSupabaseClient,
    minimal_guide: CityGuideImport,
    null_geocoder: object,
) -> None:
    await import_city_guide(minimal_guide, null_geocoder, fake_db)

    with pytest.raises(CitySlugExistsError):
        await import_city_guide(minimal_guide, null_geocoder, fake_db)

    # Only one city in the DB
    assert len(fake_db.get_table("cities")) == 1


# ============================================================
# 4. Replace existing draft — replaced=True, row count correct
# ============================================================


@pytest.mark.asyncio
async def test_replace_draft_succeeds(
    fake_db: FakeSupabaseClient,
    minimal_guide: CityGuideImport,
    null_geocoder: object,
) -> None:
    await import_city_guide(minimal_guide, null_geocoder, fake_db)

    result = await import_city_guide(
        minimal_guide, null_geocoder, fake_db, replace=True
    )

    assert result.replaced is True
    # After replace: exactly one city, one spot, one itinerary, one step, one tip
    assert len(fake_db.get_table("cities")) == 1
    assert len(fake_db.get_table("spots")) == 1
    assert len(fake_db.get_table("itineraries")) == 1
    assert len(fake_db.get_table("itinerary_steps")) == 1
    assert len(fake_db.get_table("tips")) == 1


# ============================================================
# 5. Replace published city → PublishedCityReplaceError
# ============================================================


@pytest.mark.asyncio
async def test_replace_published_city_fails(
    fake_db: FakeSupabaseClient,
    minimal_guide: CityGuideImport,
    null_geocoder: object,
) -> None:
    await import_city_guide(minimal_guide, null_geocoder, fake_db)

    # Simulate the city being published
    cities = fake_db.get_table("cities")
    fake_db.seed("cities", [{**cities[0], "status": "published"}])

    with pytest.raises(PublishedCityReplaceError) as exc_info:
        await import_city_guide(
            minimal_guide, null_geocoder, fake_db, replace=True
        )

    assert exc_info.value.slug == "test-city"
    # Published city is untouched
    assert fake_db.get_table("cities")[0]["status"] == "published"


# ============================================================
# 6. LocalizedText with empty 'es' → Pydantic ValidationError
# ============================================================


def test_localized_text_empty_es_raises() -> None:
    with pytest.raises(Exception) as exc_info:
        LocalizedTextIn(es="")
    msg = str(exc_info.value).lower()
    assert "es" in msg or "empty" in msg or "whitespace" in msg


def test_localized_text_whitespace_es_raises() -> None:
    with pytest.raises(Exception) as exc_info:
        LocalizedTextIn(es="   ")
    msg = str(exc_info.value).lower()
    assert "es" in msg or "empty" in msg or "whitespace" in msg


# ============================================================
# 7. Generic step (no spot_ref) inserts with title/address
# ============================================================


@pytest.mark.asyncio
async def test_generic_step_no_spot_ref(
    fake_db: FakeSupabaseClient,
    minimal_guide: CityGuideImport,
    null_geocoder: object,
) -> None:
    minimal_guide.itineraries[0].steps.append(
        ItineraryStepIn(
            rank_order=2,
            spot_ref=None,
            title=LocalizedTextIn(es="Paseo por el puerto"),
            address="Puerto principal, Test City",
            description=LocalizedTextIn(es="Un paseo tranquilo"),
            bon_vivant_notes=LocalizedTextIn(es="Disfrutar las vistas"),
            time_on_site_min=20,
            time_on_site_max=30,
        )
    )

    result = await import_city_guide(minimal_guide, null_geocoder, fake_db)
    assert result.counts.steps == 2

    steps = fake_db.get_table("itinerary_steps")
    generic = next(s for s in steps if s["rank_order"] == 2)
    assert generic["spot_id"] is None
    assert generic["address"] == "Puerto principal, Test City"


# ============================================================
# 8. spot_ref resolves to the correct spot_id
# ============================================================


@pytest.mark.asyncio
async def test_step_spot_ref_resolves_to_correct_id(
    fake_db: FakeSupabaseClient,
    minimal_guide: CityGuideImport,
    null_geocoder: object,
) -> None:
    await import_city_guide(minimal_guide, null_geocoder, fake_db)

    spots = fake_db.get_table("spots")
    steps = fake_db.get_table("itinerary_steps")

    assert len(spots) == 1
    assert len(steps) == 1
    assert steps[0]["spot_id"] == spots[0]["id"]


# ============================================================
# 9. PATCH /admin/cities/{id} — updates only sent fields
# ============================================================


@pytest.mark.asyncio
async def test_patch_city_updates_only_sent_fields(
    fake_db: FakeSupabaseClient,
    null_geocoder: object,
    minimal_guide: CityGuideImport,
) -> None:
    await import_city_guide(minimal_guide, null_geocoder, fake_db)
    city = fake_db.get_table("cities")[0]
    city_id = city["id"]
    original_intro = city["intro"]

    patch = CityUpdate(tagline=LocalizedTextIn(es="Nueva tagline"))
    updated = await city_service.update_city(city_id, patch, fake_db)

    assert updated["tagline"] == {"es": "Nueva tagline"}
    # intro must be unchanged
    assert updated["intro"] == original_intro


@pytest.mark.asyncio
async def test_patch_city_not_found_raises(fake_db: FakeSupabaseClient) -> None:
    from app.services.exceptions import CityNotFoundError

    patch = CityUpdate(tagline=LocalizedTextIn(es="Algo"))
    with pytest.raises(CityNotFoundError):
        await city_service.update_city(str(uuid.uuid4()), patch, fake_db)


# ============================================================
# 10. POST .../publish changes status to published
# ============================================================


@pytest.mark.asyncio
async def test_publish_city_changes_status(
    fake_db: FakeSupabaseClient,
    null_geocoder: object,
    minimal_guide: CityGuideImport,
) -> None:
    from app.models.city import CityStatus

    await import_city_guide(minimal_guide, null_geocoder, fake_db)
    city_id = fake_db.get_table("cities")[0]["id"]

    updated = await city_service.set_city_status(city_id, CityStatus.published, fake_db)
    assert updated["status"] == "published"

    # Verify in the store
    assert fake_db.get_table("cities")[0]["status"] == "published"


# ============================================================
# 11. PATCH /admin/spots/{id} — updates only sent fields
# ============================================================


@pytest.mark.asyncio
async def test_patch_spot_updates_field(
    fake_db: FakeSupabaseClient,
    null_geocoder: object,
    minimal_guide: CityGuideImport,
) -> None:
    await import_city_guide(minimal_guide, null_geocoder, fake_db)
    spot = fake_db.get_table("spots")[0]
    spot_id = spot["id"]

    patch = SpotUpdate(address="2-2 New Address St")
    updated = await city_service.update_spot(spot_id, patch, fake_db)

    assert updated["address"] == "2-2 New Address St"
    assert updated["name"] == "Templo Central"  # unchanged


@pytest.mark.asyncio
async def test_patch_spot_not_found_raises(fake_db: FakeSupabaseClient) -> None:
    patch = SpotUpdate(address="X")
    with pytest.raises(SpotNotFoundError):
        await city_service.update_spot(str(uuid.uuid4()), patch, fake_db)
