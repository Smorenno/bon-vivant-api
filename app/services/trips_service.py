from __future__ import annotations

from datetime import date, timedelta

from app.exceptions import AppError
from app.models.trip import (
    CreateTripInput,
    TripDayInput,
    TripDayResponse,
    TripResponse,
    TripsListResponse,
)
from app.services.access_service import has_active_pass
from supabase._async.client import AsyncClient

# ============================================================
# Row → model helpers
# ============================================================


def _parse_date(value: object) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _build_day(row: dict) -> TripDayResponse:
    return TripDayResponse(
        id=row["id"],
        day_number=row["day_number"],
        date=row["date"],
        city_slug=row.get("city_slug"),
        time_arrival=row.get("time_arrival"),
        time_departure=row.get("time_departure"),
        departure_next_day=bool(row.get("departure_next_day", False)),
        has_guide=row.get("city_slug") is not None,
    )


def _build_trip(trip_row: dict, day_rows: list[dict]) -> TripResponse:
    days = [_build_day(r) for r in sorted(day_rows, key=lambda r: r["day_number"])]
    start = _parse_date(trip_row["start_date"])
    end = _parse_date(trip_row["end_date"])
    return TripResponse(
        id=trip_row["id"],
        title=trip_row["title"],
        cruise_line=trip_row["cruise_line"],
        ship_name=trip_row["ship_name"],
        start_date=trip_row["start_date"],
        end_date=trip_row["end_date"],
        total_days=(end - start).days + 1,
        total_ports=sum(1 for d in days if d.city_slug is not None),
        days=days,
    )


# ============================================================
# Low-level fetch helpers
# ============================================================


async def _fetch_days(client: AsyncClient, trip_id: str) -> list[dict]:
    response = (
        await client.table("trip_days")
        .select("*")
        .eq("trip_id", trip_id)
        .order("day_number")
        .execute()
    )
    return response.data


async def _assert_city_slug_exists(client: AsyncClient, slug: str) -> None:
    response = (
        await client.table("cities").select("id").eq("slug", slug).limit(1).execute()
    )
    if not response.data:
        raise AppError(400, f"City not found: {slug}", "city_not_found")


# ============================================================
# Public service functions
# ============================================================


async def get_trips(client: AsyncClient, user_id: str) -> TripsListResponse:
    response = await client.table("trips").select("*").eq("user_id", user_id).execute()
    trips: list[TripResponse] = []
    for trip_row in response.data:
        day_rows = await _fetch_days(client, str(trip_row["id"]))
        trips.append(_build_trip(trip_row, day_rows))
    return TripsListResponse(trips=trips)


async def get_trip(client: AsyncClient, trip_id: str, user_id: str) -> TripResponse:
    response = (
        await client.table("trips").select("*").eq("id", trip_id).limit(1).execute()
    )
    if not response.data:
        raise AppError(404, "Trip not found", "trip_not_found")

    trip_row = response.data[0]
    # 403 when resource exists but belongs to another user — never 404
    if str(trip_row["user_id"]) != user_id:
        raise AppError(403, "Access denied", "trip_access_denied")

    day_rows = await _fetch_days(client, trip_id)
    return _build_trip(trip_row, day_rows)


async def create_trip(
    client: AsyncClient, data: CreateTripInput, user_id: str
) -> TripResponse:
    # The trip planner is a Pass-only feature. Enforce entitlement here on the
    # server — the client's blur overlay is presentation only and trivially
    # bypassed by calling this endpoint directly.
    if not await has_active_pass(client, user_id):
        raise AppError(403, "Trip planner requires the Pass", "pass_required")

    # Validate date range
    if data.end_date <= data.start_date:
        raise AppError(400, "end_date must be after start_date", "invalid_dates")

    # The mobile client only sends the days configured as port calls; sea days
    # are implicit. Index sent days by date, rejecting duplicates and dates
    # outside the trip range. day_number from the client is ignored — it is
    # derived from the date below.
    days_by_date: dict[date, TripDayInput] = {}
    for day in data.days:
        if day.date < data.start_date or day.date > data.end_date:
            raise AppError(
                400,
                f"Day date {day.date} is outside the trip range",
                "invalid_day_date",
            )
        if day.date in days_by_date:
            raise AppError(
                400,
                f"Duplicate day for date {day.date}",
                "duplicate_day_date",
            )
        days_by_date[day.date] = day

    # Validate any non-null city_slugs exist in the cities table
    seen_slugs: set[str] = set()
    for day in data.days:
        if day.city_slug is not None and day.city_slug not in seen_slugs:
            await _assert_city_slug_exists(client, day.city_slug)
            seen_slugs.add(day.city_slug)

    # Insert trip row
    trip_insert = (
        await client.table("trips")
        .insert(
            {
                "user_id": user_id,
                "title": data.title,
                "cruise_line": data.cruise_line,
                "ship_name": data.ship_name,
                "start_date": data.start_date.isoformat(),
                "end_date": data.end_date.isoformat(),
            }
        )
        .execute()
    )
    trip_row = trip_insert.data[0]
    trip_id = str(trip_row["id"])

    # Batch-insert trip_days: one row per calendar day. Dates the client sent
    # keep their port-call data; the rest are auto-filled as at-sea days.
    total_days = (data.end_date - data.start_date).days + 1
    days_payload = []
    for offset in range(total_days):
        current = data.start_date + timedelta(days=offset)
        sent = days_by_date.get(current)
        days_payload.append(
            {
                "trip_id": trip_id,
                "day_number": offset + 1,
                "date": current.isoformat(),
                "city_slug": sent.city_slug if sent else None,
                "time_arrival": (
                    sent.time_arrival.isoformat()
                    if sent and sent.time_arrival
                    else None
                ),
                "time_departure": (
                    sent.time_departure.isoformat()
                    if sent and sent.time_departure
                    else None
                ),
                "departure_next_day": sent.departure_next_day if sent else False,
            }
        )
    days_insert = await client.table("trip_days").insert(days_payload).execute()
    day_rows = sorted(days_insert.data, key=lambda r: r["day_number"])

    return _build_trip(trip_row, day_rows)
