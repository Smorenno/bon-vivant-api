from __future__ import annotations

import asyncio

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
from app.services.access_service import (
    has_active_pass,
    is_city_unlocked,
    unlocked_city_ids,
)
from app.services.font_service import resolve_city_fonts
from app.services.image_service import (
    SINGLE_SLOTS,
    build_storage_path,
    gallery_paths,
    pick_gallery,
    pick_single,
    sign_paths,
)
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


async def _fetch_itineraries_with_steps(
    client: AsyncClient, city_id: str
) -> tuple[list[dict], dict[str, list[dict]]]:
    """Itinerary rows plus their steps keyed by itinerary_id (2 chained queries)."""
    itin_rows = await _fetch_itineraries(client, city_id)
    itin_ids = [str(row["id"]) for row in itin_rows]
    return itin_rows, await _fetch_steps_for_itineraries(client, itin_ids)


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
        # Locked → no steps in the payload; hiding them only in the client
        # would leave the premium route readable in the raw response.
        steps=[] if is_locked else [_parse_step(s, spot_map) for s in sorted_steps],
        step_count=len(sorted_steps),
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
    """Sign every guide photo in a single Storage request."""
    gallery_counts = {
        "overview_highlight": len(highlights),
        "attraction": sum(1 for r in spots_rows if r["kind"] == "attraction"),
        "gourmet": sum(1 for r in spots_rows if r["kind"] == "food"),
        "port": len(transport_options) or 1,
    }
    paths = [build_storage_path(slug, slot) for slot in SINGLE_SLOTS]
    for slot, count in gallery_counts.items():
        paths.extend(gallery_paths(slug, slot, count))
    signed = await sign_paths(client, paths)

    def single(slot: str) -> str | None:
        return pick_single(signed, slug, slot)

    def gallery(slot: str) -> list[str]:
        return pick_gallery(signed, slug, slot, gallery_counts[slot])

    return CityImages(
        cover=single("cover"),
        preview=single("preview"),
        overview=single("overview"),
        key_historical_context=single("key_historical_context"),
        overview_highlights=gallery("overview_highlight"),
        attraction_cover=single("attraction_cover"),
        attraction_gallery=gallery("attraction"),
        gourmet_cover=single("gourmet_cover"),
        gourmet_gallery=gallery("gourmet"),
        port_cover=single("port_cover"),
        port_gallery=gallery("port"),
        itineraries_cover=single("itineraries_cover"),
        tips_cover=single("tips_cover"),
    )


# ============================================================
# Public service functions
# ============================================================


async def list_cities(client: AsyncClient, user_id: str) -> list[CityListItem]:
    rows, unlocked_ids = await asyncio.gather(
        _fetch_all_published_cities(client), unlocked_city_ids(client, user_id)
    )
    cover_slots = ("cover", "port_cover")
    signed = await sign_paths(
        client,
        [build_storage_path(r["slug"], slot) for r in rows for slot in cover_slots],
    )
    return [
        CityListItem(
            id=row["id"],
            slug=row["slug"],
            name=row["name"],
            country_code=row["country_code"],
            tagline=_parse_localized(row["tagline"]),
            status=CityStatus(row["status"]),
            is_unlocked=str(row["id"]) in unlocked_ids,
            cover=pick_single(signed, row["slug"], "cover"),
            port_cover_url=pick_single(signed, row["slug"], "port_cover"),
        )
        for row in rows
    ]


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

    unlocked, has_pass = await asyncio.gather(
        is_city_unlocked(client, user_id, city_id), has_active_pass(client, user_id)
    )
    if require_access and not unlocked:
        raise CityLockedError(slug)

    # Independent reads run concurrently: one round trip instead of one each.
    spots_rows, (itin_rows, steps_by_itin), tip_rows, fonts = await asyncio.gather(
        _fetch_spots(client, city_id),
        _fetch_itineraries_with_steps(client, city_id),
        _fetch_city_tips(client, city_id),
        resolve_city_fonts(
            client, city_row.get("title_font_id"), city_row.get("body_font_id")
        ),
    )

    spot_map = {str(row["id"]): row for row in spots_rows}

    # Premium (night) itineraries require the Pass.
    itineraries = [
        _parse_itinerary(
            row,
            steps_by_itin.get(str(row["id"]), []),
            is_locked=bool(row["is_premium"]) and not has_pass,
            spot_map=spot_map,
        )
        for row in itin_rows
    ]

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
        fonts=fonts,
        is_unlocked=unlocked,
    )


async def get_city_preview(
    client: AsyncClient, slug: str, user_id: str
) -> CityGuidePreview:
    """Return a lightweight preview with the first tip (no access gate)."""
    city_row = await _fetch_city_row(client, slug)
    city_id = str(city_row["id"])

    unlocked, tip_rows = await asyncio.gather(
        is_city_unlocked(client, user_id, city_id), _fetch_city_tips(client, city_id)
    )
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
