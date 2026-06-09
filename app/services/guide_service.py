from __future__ import annotations

from app.exceptions import CityLockedError, CityNotFoundError
from app.models.city import (
    CityGuide,
    CityGuidePreview,
    CityListItem,
    CityStatus,
    Highlight,
    Itinerary,
    ItineraryStep,
    LocalizedText,
    Note,
    Spot,
    Tip,
    TransportOption,
)
from app.services.access_service import is_city_unlocked, is_itinerary_locked
from supabase import AsyncClient

# ============================================================
# Low-level fetch helpers (one responsibility each)
# ============================================================


async def _fetch_city_row(client: AsyncClient, slug: str) -> dict:
    """Fetch a single published city row by slug; raise CityNotFoundError if absent."""
    response = (
        await client.table("cities")
        .select("*")
        .eq("slug", slug)
        .eq("status", "published")
        .maybe_single()
        .execute()
    )
    if response.data is None:
        raise CityNotFoundError(slug)
    return response.data


async def _fetch_all_published_cities(client: AsyncClient) -> list[dict]:
    response = (
        await client.table("cities")
        .select("id, slug, name, country_code, tagline, status")
        .eq("status", "published")
        .execute()
    )
    return response.data


async def _fetch_spots(client: AsyncClient, city_id: str) -> list[dict]:
    response = (
        await client.table("spots")
        .select("*")
        .eq("city_id", city_id)
        .order("rank_order")
        .execute()
    )
    return response.data


async def _fetch_itineraries_with_steps(
    client: AsyncClient, city_id: str
) -> list[dict]:
    response = (
        await client.table("itineraries")
        .select("*, itinerary_steps(*)")
        .eq("city_id", city_id)
        .order("rank_order")
        .execute()
    )
    return response.data


async def _fetch_city_tips(client: AsyncClient, city_id: str) -> list[dict]:
    response = (
        await client.table("tips")
        .select("*")
        .eq("city_id", city_id)
        .order("rank_order")
        .execute()
    )
    return response.data


# ============================================================
# Row → model parsers
# ============================================================


def _parse_localized(raw: dict) -> LocalizedText:
    return LocalizedText(**raw)


def _opt(row: dict, key: str) -> LocalizedText | None:
    """Parse a nullable LocalizedText jsonb field from a DB row."""
    value = row.get(key)
    return _parse_localized(value) if value else None


def _parse_spot(row: dict) -> Spot:
    return Spot(
        id=row["id"],
        city_id=row["city_id"],
        kind=row["kind"],
        category=row.get("category"),
        name=row["name"],
        address=row["address"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        distance_from_port_km=row.get("distance_from_port_km"),
        rank_order=row["rank_order"],
        website=row.get("website"),
        manuel_quote=_parse_localized(row["manuel_quote"]),
        reservation=_opt(row, "reservation"),
        what_it_is=_opt(row, "what_it_is"),
        why_it_matters=_opt(row, "why_it_matters"),
        good_to_know=_opt(row, "good_to_know"),
        cuisine_type=_opt(row, "cuisine_type"),
        category_label=_opt(row, "category_label"),
        must_try=_opt(row, "must_try"),
        best_time=_opt(row, "best_time"),
    )


def _parse_step(row: dict) -> ItineraryStep:
    return ItineraryStep(
        id=row["id"],
        itinerary_id=row["itinerary_id"],
        rank_order=row["rank_order"],
        spot_id=row.get("spot_id"),
        title=_parse_localized(row["title"]) if row.get("title") else None,
        address=row.get("address"),
        description=_parse_localized(row["description"]),
        bon_vivant_notes=_parse_localized(row["bon_vivant_notes"]),
        must_try=_opt(row, "must_try"),
        reservation=_opt(row, "reservation"),
        website=row.get("website"),
        distance_from_prev_km=row.get("distance_from_prev_km"),
        travel_mode=row.get("travel_mode"),
        time_on_site_min=row["time_on_site_min"],
        time_on_site_max=row["time_on_site_max"],
    )


def _parse_itinerary(row: dict, is_locked: bool) -> Itinerary:
    steps = sorted(row.get("itinerary_steps", []), key=lambda s: s["rank_order"])
    return Itinerary(
        id=row["id"],
        city_id=row["city_id"],
        theme=row["theme"],
        time_of_day=row["time_of_day"],
        title=_parse_localized(row["title"]),
        catchy_phrase=_parse_localized(row["catchy_phrase"]),
        best_for=_parse_localized(row["best_for"]),
        duration_min_hrs=row["duration_min_hrs"],
        duration_max_hrs=row["duration_max_hrs"],
        total_walk_km=row["total_walk_km"],
        total_transit_km=row.get("total_transit_km"),
        flex_note=_parse_localized(row["flex_note"]),
        is_recommended=row["is_recommended"],
        is_premium=row["is_premium"],
        rank_order=row["rank_order"],
        steps=[_parse_step(s) for s in steps],
        is_locked=is_locked,
    )


def _parse_tip(row: dict) -> Tip:
    return Tip(
        id=row["id"],
        city_id=row.get("city_id"),
        title=_parse_localized(row["title"]),
        body=_parse_localized(row["body"]),
        rank_order=row["rank_order"],
    )


def _parse_highlights(raw: list[dict]) -> list[Highlight]:
    return [
        Highlight(
            label=_parse_localized(h["label"]),
            description=_parse_localized(h["description"]),
        )
        for h in raw
    ]


def _parse_transport_options(raw: list[dict]) -> list[TransportOption]:
    return [
        TransportOption(
            method=item["method"],
            time_label=item["time_label"],
            tips=_parse_localized(item["tips"]),
        )
        for item in raw
    ]


def _parse_what_to_know(raw: list[dict]) -> list[Note]:
    return [
        Note(
            heading=_parse_localized(n["heading"]),
            text=_parse_localized(n["text"]),
        )
        for n in raw
    ]


# ============================================================
# Public service functions
# ============================================================


async def list_cities(client: AsyncClient, user_id: str) -> list[CityListItem]:
    rows = await _fetch_all_published_cities(client)
    items: list[CityListItem] = []
    for row in rows:
        unlocked = await is_city_unlocked(client, user_id, str(row["id"]))
        items.append(
            CityListItem(
                id=row["id"],
                slug=row["slug"],
                name=row["name"],
                country_code=row["country_code"],
                tagline=_parse_localized(row["tagline"]),
                status=CityStatus(row["status"]),
                is_unlocked=unlocked,
            )
        )
    return items


async def get_city_guide(
    client: AsyncClient,
    slug: str,
    user_id: str,
    require_access: bool = True,
) -> CityGuide:
    """Assemble a full CityGuide.

    Raises CityLockedError when require_access=True and the user lacks a purchase.
    """
    city_row = await _fetch_city_row(client, slug)
    city_id = str(city_row["id"])

    unlocked = await is_city_unlocked(client, user_id, city_id)
    if require_access and not unlocked:
        raise CityLockedError(slug)

    spots_rows, itinerary_rows, tip_rows = (
        await _fetch_spots(client, city_id),
        await _fetch_itineraries_with_steps(client, city_id),
        await _fetch_city_tips(client, city_id),
    )

    itineraries: list[Itinerary] = []
    for row in itinerary_rows:
        locked = await is_itinerary_locked(client, user_id, row["is_premium"])
        itineraries.append(_parse_itinerary(row, is_locked=locked))

    return CityGuide(
        id=city_row["id"],
        slug=city_row["slug"],
        name=city_row["name"],
        country_code=city_row["country_code"],
        tagline=_parse_localized(city_row["tagline"]),
        intro=_parse_localized(city_row["intro"]),
        historical_context=_parse_localized(city_row["historical_context"]),
        port_description=_parse_localized(city_row["port_description"]),
        distance_to_center=_parse_localized(city_row["distance_to_center"]),
        port_facilities=_parse_localized(city_row["port_facilities"]),
        port_recommendation=_parse_localized(city_row["port_recommendation"]),
        port_lat=city_row["port_lat"],
        port_lng=city_row["port_lng"],
        highlights=_parse_highlights(city_row["highlights"]),
        transport_options=_parse_transport_options(city_row["transport_options"]),
        what_to_know=_parse_what_to_know(city_row["what_to_know"]),
        status=CityStatus(city_row["status"]),
        last_verified=city_row.get("last_verified"),
        spots=[_parse_spot(r) for r in spots_rows],
        itineraries=itineraries,
        tips=[_parse_tip(r) for r in tip_rows],
        is_unlocked=unlocked,
    )


async def get_city_preview(
    client: AsyncClient, slug: str, user_id: str
) -> CityGuidePreview:
    """Return a lightweight preview with the first tip (no access gate)."""
    city_row = await _fetch_city_row(client, slug)
    city_id = str(city_row["id"])

    unlocked = await is_city_unlocked(client, user_id, city_id)
    tip_rows = await _fetch_city_tips(client, city_id)
    first_tip = [_parse_tip(tip_rows[0])] if tip_rows else []

    return CityGuidePreview(
        id=city_row["id"],
        slug=city_row["slug"],
        name=city_row["name"],
        country_code=city_row["country_code"],
        tagline=_parse_localized(city_row["tagline"]),
        intro=_parse_localized(city_row["intro"]),
        highlights=_parse_highlights(city_row["highlights"]),
        tips=first_tip,
        is_unlocked=unlocked,
    )
