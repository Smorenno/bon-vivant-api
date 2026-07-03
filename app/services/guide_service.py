from __future__ import annotations

from app.exceptions import CityLockedError, CityNotFoundError
from app.models.city import (
    CityGuide,
    CityGuidePreview,
    CityImages,
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
from app.services.image_service import resolve_gallery, resolve_single
from supabase._async.client import AsyncClient

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
        .limit(1)
        .execute()
    )
    if not response.data:
        raise CityNotFoundError(slug)
    return response.data[0]


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


async def _fetch_itineraries(client: AsyncClient, city_id: str) -> list[dict]:
    response = (
        await client.table("itineraries")
        .select("*")
        .eq("city_id", city_id)
        .order("rank_order")
        .execute()
    )
    return response.data


async def _fetch_steps_for_itineraries(
    client: AsyncClient, itinerary_ids: list[str]
) -> dict[str, list[dict]]:
    """Return steps keyed by itinerary_id, each list ordered by rank_order."""
    if not itinerary_ids:
        return {}
    response = (
        await client.table("itinerary_steps")
        .select("*")
        .in_("itinerary_id", itinerary_ids)
        .order("rank_order")
        .execute()
    )
    grouped: dict[str, list[dict]] = {}
    for step in response.data:
        grouped.setdefault(str(step["itinerary_id"]), []).append(step)
    return grouped


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
        latitude=row.get("latitude"),
        longitude=row.get("longitude"),
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


def _parse_step(row: dict, spot_map: dict[str, dict]) -> ItineraryStep:
    # If the step links to a spot, name/address/website are resolved from the spot row.
    spot = spot_map.get(str(row["spot_id"])) if row.get("spot_id") else None
    return ItineraryStep(
        id=row["id"],
        itinerary_id=row["itinerary_id"],
        rank_order=row["rank_order"],
        spot_id=row.get("spot_id"),
        name=spot["name"] if spot else None,
        title=_parse_localized(row["title"]) if row.get("title") else None,
        address=spot["address"] if spot else row.get("address"),
        description=_parse_localized(row["description"]),
        bon_vivant_notes=_opt(row, "bon_vivant_notes"),
        must_try=_opt(row, "must_try"),
        reservation=_opt(row, "reservation"),
        website=spot.get("website") if spot else row.get("website"),
        distance_from_prev_km=row.get("distance_from_prev_km"),
        travel_mode=row.get("travel_mode"),
        time_on_site_min=row.get("time_on_site_min"),
        time_on_site_max=row.get("time_on_site_max"),
    )


def _parse_itinerary(
    row: dict,
    steps: list[dict],
    is_locked: bool,
    spot_map: dict[str, dict],
) -> Itinerary:
    sorted_steps = sorted(steps, key=lambda s: s["rank_order"])
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
        steps=[_parse_step(s, spot_map) for s in sorted_steps],
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


async def _resolve_city_images(
    client: AsyncClient,
    slug: str,
    spots_rows: list[dict],
    highlights: list[Highlight],
    transport_options: list[TransportOption],
) -> CityImages:
    attraction_count = sum(1 for r in spots_rows if r["kind"] == "attraction")
    gourmet_count = sum(1 for r in spots_rows if r["kind"] == "food")

    return CityImages(
        cover=await resolve_single(client, slug, "cover"),
        preview=await resolve_single(client, slug, "preview"),
        overview=await resolve_single(client, slug, "overview"),
        key_historical_context=await resolve_single(
            client, slug, "key_historical_context"
        ),
        overview_highlights=await resolve_gallery(
            client, slug, "overview_highlight", count=len(highlights)
        ),
        attraction_cover=await resolve_single(client, slug, "attraction_cover"),
        attraction_gallery=await resolve_gallery(
            client, slug, "attraction", count=attraction_count
        ),
        gourmet_cover=await resolve_single(client, slug, "gourmet_cover"),
        gourmet_gallery=await resolve_gallery(
            client, slug, "gourmet", count=gourmet_count
        ),
        port_cover=await resolve_single(client, slug, "port_cover"),
        port_gallery=await resolve_gallery(
            client, slug, "port", count=len(transport_options) or 1
        ),
        itineraries_cover=await resolve_single(client, slug, "itineraries_cover"),
        tips_cover=await resolve_single(client, slug, "tips_cover"),
    )


# ============================================================
# Public service functions
# ============================================================


async def list_cities(client: AsyncClient, user_id: str) -> list[CityListItem]:
    rows = await _fetch_all_published_cities(client)
    items: list[CityListItem] = []
    for row in rows:
        unlocked = await is_city_unlocked(client, user_id, str(row["id"]))
        slug = row["slug"]
        cover = await resolve_single(client, slug, "cover")
        port_cover_url = await resolve_single(client, slug, "port_cover")
        items.append(
            CityListItem(
                id=row["id"],
                slug=slug,
                name=row["name"],
                country_code=row["country_code"],
                tagline=_parse_localized(row["tagline"]),
                status=CityStatus(row["status"]),
                is_unlocked=unlocked,
                cover=cover,
                port_cover_url=port_cover_url,
            )
        )
    return items


async def get_city_guide(
    client: AsyncClient,
    slug: str,
    user_id: str,
    require_access: bool = True,
) -> CityGuide:
    """Assemble a full CityGuide from DB rows.

    Raises CityLockedError (403) when require_access=True and the user lacks a purchase.
    Raises CityNotFoundError (404) when the city does not exist or is not published.
    """
    city_row = await _fetch_city_row(client, slug)
    city_id = str(city_row["id"])

    unlocked = await is_city_unlocked(client, user_id, city_id)
    if require_access and not unlocked:
        raise CityLockedError(slug)

    spots_rows = await _fetch_spots(client, city_id)
    itin_rows = await _fetch_itineraries(client, city_id)
    itin_ids = [str(row["id"]) for row in itin_rows]
    steps_by_itin = await _fetch_steps_for_itineraries(client, itin_ids)
    tip_rows = await _fetch_city_tips(client, city_id)

    spot_map = {str(row["id"]): row for row in spots_rows}

    itineraries: list[Itinerary] = []
    for row in itin_rows:
        steps = steps_by_itin.get(str(row["id"]), [])
        locked = await is_itinerary_locked(client, user_id, row["is_premium"])
        itineraries.append(
            _parse_itinerary(row, steps, is_locked=locked, spot_map=spot_map)
        )

    highlights = _parse_highlights(city_row.get("highlights") or [])
    transport_options = _parse_transport_options(
        city_row.get("transport_options") or []
    )
    images = await _resolve_city_images(
        client, slug, spots_rows, highlights, transport_options
    )

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
        port_lat=city_row.get("port_lat"),
        port_lng=city_row.get("port_lng"),
        highlights=highlights,
        transport_options=transport_options,
        what_to_know=_parse_what_to_know(city_row.get("what_to_know") or []),
        status=CityStatus(city_row["status"]),
        last_verified=city_row.get("last_verified"),
        spots=[_parse_spot(r) for r in spots_rows],
        itineraries=itineraries,
        tips=[_parse_tip(r) for r in tip_rows],
        images=images,
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
        highlights=_parse_highlights(city_row.get("highlights") or []),
        tips=first_tip,
        is_unlocked=unlocked,
    )
