"""Tests for Trip Planner service."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.exceptions import AppError
from app.models.trip import CreateTripInput, TripDayInput
from app.services import trips_service
from tests.fake_supabase import FakeSupabaseClient

_CITY_SLUG = "barcelona"
_USER_A = "user-a"
_USER_B = "user-b"

_START = date(2026, 7, 1)
_END = date(2026, 7, 3)  # 3-day trip


_PASS_PACK_ID = str(uuid.uuid4())


def _make_db(*, with_city: bool = True, with_pass: bool = True) -> FakeSupabaseClient:
    db = FakeSupabaseClient()
    if with_city:
        db.seed(
            "cities",
            [{"id": str(uuid.uuid4()), "slug": _CITY_SLUG, "status": "published"}],
        )
    if with_pass:
        # The trip planner is Pass-gated; grant both test users the unlimited Pass.
        db.seed(
            "packs",
            [{"id": _PASS_PACK_ID, "name": "Pass", "is_unlimited": True}],
        )
        db.seed(
            "user_purchases",
            [
                {
                    "id": str(uuid.uuid4()),
                    "user_id": _USER_A,
                    "pack_id": _PASS_PACK_ID,
                    "is_valid": True,
                },
                {
                    "id": str(uuid.uuid4()),
                    "user_id": _USER_B,
                    "pack_id": _PASS_PACK_ID,
                    "is_valid": True,
                },
            ],
        )
    return db


def _make_days(start: date, end: date, port_day: int | None = 1) -> list[TripDayInput]:
    """Generate consecutive TripDayInput list for the given range.

    If port_day is set, that day_number gets city_slug; all others are at sea.
    """
    total = (end - start).days + 1
    return [
        TripDayInput(
            day_number=i + 1,
            date=date.fromordinal(start.toordinal() + i),
            city_slug=_CITY_SLUG if (i + 1) == port_day else None,
        )
        for i in range(total)
    ]


def _valid_input(
    start: date = _START,
    end: date = _END,
    port_day: int | None = 1,
) -> CreateTripInput:
    return CreateTripInput(
        title="Mediterranean Cruise",
        cruise_line="MSC",
        ship_name="Bellissima",
        start_date=start,
        end_date=end,
        days=_make_days(start, end, port_day=port_day),
    )


# ============================================================
# 1. get_trips — empty list when user has no trips
# ============================================================


async def test_get_trips_returns_empty_list_when_no_trips() -> None:
    db = _make_db()
    result = await trips_service.get_trips(db, _USER_A)
    assert result.trips == []


# ============================================================
# 2. get_trips — returns only the authenticated user's trips
# ============================================================


async def test_get_trips_returns_only_own_trips() -> None:
    db = _make_db()
    await trips_service.create_trip(db, _valid_input(), _USER_A)
    await trips_service.create_trip(db, _valid_input(), _USER_B)

    result_a = await trips_service.get_trips(db, _USER_A)
    result_b = await trips_service.get_trips(db, _USER_B)

    assert len(result_a.trips) == 1
    assert len(result_b.trips) == 1
    # Each user's trip is theirs
    assert result_a.trips[0].title == "Mediterranean Cruise"


# ============================================================
# 3. get_trip — another user's trip returns 403
# ============================================================


async def test_get_trip_other_user_returns_403() -> None:
    db = _make_db()
    trip = await trips_service.create_trip(db, _valid_input(), _USER_A)

    with pytest.raises(AppError) as exc_info:
        await trips_service.get_trip(db, str(trip.id), _USER_B)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "trip_access_denied"


# ============================================================
# 3b. create_trip — user without the Pass returns 403
# ============================================================


async def test_create_trip_without_pass_returns_403() -> None:
    db = _make_db(with_pass=False)

    with pytest.raises(AppError) as exc_info:
        await trips_service.create_trip(db, _valid_input(), _USER_A)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "pass_required"


# ============================================================
# 4. get_trip — nonexistent trip_id returns 404
# ============================================================


async def test_get_trip_nonexistent_returns_404() -> None:
    db = _make_db()

    with pytest.raises(AppError) as exc_info:
        await trips_service.get_trip(db, str(uuid.uuid4()), _USER_A)

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "trip_not_found"


# ============================================================
# 5. create_trip — end_date <= start_date returns 400 invalid_dates
# ============================================================


async def test_create_trip_invalid_dates_returns_400() -> None:
    db = _make_db()

    with pytest.raises(AppError) as exc_info:
        await trips_service.create_trip(
            db,
            CreateTripInput(
                title="Bad Trip",
                cruise_line="MSC",
                ship_name="Bellissima",
                start_date=date(2026, 7, 5),
                end_date=date(2026, 7, 1),
                days=[],
            ),
            _USER_A,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "invalid_dates"


# ============================================================
# 6. create_trip — nonexistent city_slug returns 400 city_not_found
# ============================================================


async def test_create_trip_nonexistent_city_slug_returns_400() -> None:
    db = _make_db(with_city=False)
    start = date(2026, 7, 1)
    end = date(2026, 7, 2)  # valid range: must be strictly after start

    with pytest.raises(AppError) as exc_info:
        await trips_service.create_trip(
            db,
            CreateTripInput(
                title="Bad Trip",
                cruise_line="MSC",
                ship_name="Bellissima",
                start_date=start,
                end_date=end,
                days=[
                    TripDayInput(day_number=1, date=start, city_slug="does-not-exist"),
                    TripDayInput(day_number=2, date=end),
                ],
            ),
            _USER_A,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "city_not_found"


# ============================================================
# 7. create_trip — partial days: missing dates auto-filled as at-sea days
# ============================================================


async def test_create_trip_partial_days_autofills_sea_days() -> None:
    db = _make_db()
    # 3-day trip but the client only sends the single port call (day 2).
    result = await trips_service.create_trip(
        db,
        CreateTripInput(
            title="Mediterranean Cruise",
            cruise_line="MSC",
            ship_name="Bellissima",
            start_date=_START,
            end_date=_END,
            days=[
                TripDayInput(day_number=1, date=date(2026, 7, 2), city_slug=_CITY_SLUG)
            ],
        ),
        _USER_A,
    )

    assert result.total_days == 3
    assert result.total_ports == 1
    assert len(result.days) == 3

    # day_number is derived from the date, not from the client
    assert [d.day_number for d in result.days] == [1, 2, 3]
    assert [d.date for d in result.days] == [
        date(2026, 7, 1),
        date(2026, 7, 2),
        date(2026, 7, 3),
    ]

    port_day = result.days[1]
    assert port_day.city_slug == _CITY_SLUG
    assert port_day.has_guide is True

    for sea_day in (result.days[0], result.days[2]):
        assert sea_day.city_slug is None
        assert sea_day.has_guide is False
        assert sea_day.time_arrival is None
        assert sea_day.time_departure is None
        assert sea_day.departure_next_day is False


# ============================================================
# 7b. create_trip — day date outside trip range returns 400
# ============================================================


async def test_create_trip_day_outside_range_returns_400() -> None:
    db = _make_db()

    with pytest.raises(AppError) as exc_info:
        await trips_service.create_trip(
            db,
            CreateTripInput(
                title="Bad Trip",
                cruise_line="MSC",
                ship_name="Bellissima",
                start_date=_START,
                end_date=_END,
                days=[
                    TripDayInput(
                        day_number=1, date=date(2026, 7, 9), city_slug=_CITY_SLUG
                    )
                ],
            ),
            _USER_A,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "invalid_day_date"


# ============================================================
# 7c. create_trip — duplicate dates in sent days returns 400
# ============================================================


async def test_create_trip_duplicate_day_date_returns_400() -> None:
    db = _make_db()

    with pytest.raises(AppError) as exc_info:
        await trips_service.create_trip(
            db,
            CreateTripInput(
                title="Bad Trip",
                cruise_line="MSC",
                ship_name="Bellissima",
                start_date=_START,
                end_date=_END,
                days=[
                    TripDayInput(day_number=1, date=date(2026, 7, 2)),
                    TripDayInput(day_number=2, date=date(2026, 7, 2)),
                ],
            ),
            _USER_A,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "duplicate_day_date"


# ============================================================
# 8. create_trip — valid input returns correct TripResponse
# ============================================================


async def test_create_trip_valid_returns_correct_response() -> None:
    db = _make_db()
    # 3-day trip: day 1 = Barcelona port, days 2-3 = at sea
    result = await trips_service.create_trip(db, _valid_input(), _USER_A)

    assert result.title == "Mediterranean Cruise"
    assert result.cruise_line == "MSC"
    assert result.ship_name == "Bellissima"
    assert result.start_date == _START
    assert result.end_date == _END
    assert result.total_days == 3
    assert result.total_ports == 1
    assert len(result.days) == 3

    port_day = result.days[0]
    assert port_day.day_number == 1
    assert port_day.city_slug == _CITY_SLUG
    assert port_day.has_guide is True

    sea_day = result.days[1]
    assert sea_day.city_slug is None
    assert sea_day.has_guide is False
