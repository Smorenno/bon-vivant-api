from __future__ import annotations

import dataclasses

from app.schemas.import_guide import (
    AttractionIn,
    CityGuideImport,
    GourmetIn,
    ImportCounts,
    ImportResult,
)
from app.services.exceptions import (
    CitySlugExistsError,
    PublishedCityReplaceError,
    SpotRefNotFoundError,
)
from app.services.geocoding_service import Geocoder
from supabase._async.client import AsyncClient

# ============================================================
# Internal data structures
# ============================================================


@dataclasses.dataclass
class _GeoResult:
    port_lat: float | None
    port_lng: float | None
    spot_coords: dict[str, tuple[float, float]]
    geocoded: list[str]
    geocode_failed: list[str]


# ============================================================
# Slug / replace checks
# ============================================================


async def _check_slug(
    db: AsyncClient, slug: str, replace: bool
) -> tuple[str | None, bool]:
    """Return (existing_city_id_to_delete, is_replacing).

    Raises CitySlugExistsError or PublishedCityReplaceError when appropriate.
    """
    response = (
        await db.table("cities")
        .select("id, status")
        .eq("slug", slug)
        .limit(1)
        .execute()
    )
    existing: dict | None = response.data[0] if response.data else None
    if existing is None:
        return None, False

    if not replace:
        raise CitySlugExistsError(slug)

    if existing["status"] == "published":
        raise PublishedCityReplaceError(slug)

    return str(existing["id"]), True


# ============================================================
# spot_ref validation (pure Python — no DB)
# ============================================================


def _validate_spot_refs(guide: CityGuideImport) -> None:
    """Raise SpotRefNotFoundError if any step references an unknown spot name."""
    known: set[str] = {s.name for s in guide.attractions} | {
        s.name for s in guide.gourmet
    }
    for itin in guide.itineraries:
        for step in itin.steps:
            if step.spot_ref is not None and step.spot_ref not in known:
                raise SpotRefNotFoundError(step.spot_ref, itin.theme, step.rank_order)


# ============================================================
# Geocoding (best-effort — never raises)
# ============================================================


async def _geocode_guide(guide: CityGuideImport, geocoder: Geocoder) -> _GeoResult:
    geocoded: list[str] = []
    geocode_failed: list[str] = []
    spot_coords: dict[str, tuple[float, float]] = {}

    # Port coordinates
    port_lat = guide.meta.port_lat
    port_lng = guide.meta.port_lng
    if port_lat is None or port_lng is None:
        label = f"{guide.meta.name} port"
        result = await geocoder.geocode(label)
        if result is not None:
            port_lat, port_lng = result
            geocoded.append(label)
        else:
            geocode_failed.append(label)

    # Spots that have no coordinates in the JSON
    all_spots: list[tuple[str, str, float | None, float | None]] = [
        *((s.name, s.address, s.latitude, s.longitude) for s in guide.attractions),
        *((s.name, s.address, s.latitude, s.longitude) for s in guide.gourmet),
    ]
    for name, address, lat, lng in all_spots:
        if lat is None or lng is None:
            result = await geocoder.geocode(address)
            if result is not None:
                spot_coords[name] = result
                geocoded.append(name)
            else:
                geocode_failed.append(name)

    return _GeoResult(
        port_lat=port_lat,
        port_lng=port_lng,
        spot_coords=spot_coords,
        geocoded=geocoded,
        geocode_failed=geocode_failed,
    )


# ============================================================
# DB insert helpers
# ============================================================


async def _insert_city(db: AsyncClient, guide: CityGuideImport, geo: _GeoResult) -> str:
    meta = guide.meta
    overview = guide.overview
    port = guide.port

    row = {
        "slug": meta.slug,
        "name": meta.name,
        "country_code": meta.country_code,
        "tagline": meta.tagline.to_jsonb(),
        "intro": overview.intro.to_jsonb(),
        "historical_context": overview.historical_context.to_jsonb(),
        "highlights": [h.to_jsonb() for h in overview.highlights],
        "port_description": port.port_description.to_jsonb(),
        "distance_to_center": port.distance_to_center.to_jsonb(),
        "port_facilities": port.port_facilities.to_jsonb(),
        "port_recommendation": port.port_recommendation.to_jsonb(),
        "transport_options": [t.to_jsonb() for t in port.transport_options],
        "what_to_know": [n.to_jsonb() for n in guide.what_to_know],
        "port_lat": geo.port_lat,
        "port_lng": geo.port_lng,
        "status": "draft",
        "last_verified": f"{meta.last_verified}-01" if meta.last_verified else None,
    }

    response = await db.table("cities").insert(row).execute()
    return str(response.data[0]["id"])


def _spot_row(
    city_id: str,
    spot: AttractionIn | GourmetIn,
    geo: _GeoResult,
) -> dict:
    lat, lng = geo.spot_coords.get(spot.name, (spot.latitude, spot.longitude))
    row: dict = {
        "city_id": city_id,
        "kind": "food" if isinstance(spot, GourmetIn) else "attraction",
        "name": spot.name,
        "address": spot.address,
        "latitude": lat,
        "longitude": lng,
        "distance_from_port_km": spot.distance_from_port_km,
        "rank_order": spot.rank_order,
        "website": spot.website,
        "manuel_quote": spot.manuel_quote.to_jsonb(),
        "reservation": spot.reservation.to_jsonb() if spot.reservation else None,
    }
    if isinstance(spot, GourmetIn):
        row["category"] = spot.category.value
        row["cuisine_type"] = (
            spot.cuisine_type.to_jsonb() if spot.cuisine_type else None
        )
        row["category_label"] = (
            spot.category_label.to_jsonb() if spot.category_label else None
        )
        row["must_try"] = spot.must_try.to_jsonb() if spot.must_try else None
        row["best_time"] = spot.best_time.to_jsonb() if spot.best_time else None
    else:
        row["what_it_is"] = spot.what_it_is.to_jsonb() if spot.what_it_is else None
        row["why_it_matters"] = (
            spot.why_it_matters.to_jsonb() if spot.why_it_matters else None
        )
        row["good_to_know"] = (
            spot.good_to_know.to_jsonb() if spot.good_to_know else None
        )
    return row


async def _insert_spots(
    db: AsyncClient,
    city_id: str,
    guide: CityGuideImport,
    geo: _GeoResult,
) -> dict[str, str]:
    """Insert all spots and return a map of spot_name → spot_id."""
    rows = [
        *[_spot_row(city_id, s, geo) for s in guide.attractions],
        *[_spot_row(city_id, s, geo) for s in guide.gourmet],
    ]
    if not rows:
        return {}

    response = await db.table("spots").insert(rows).execute()
    return {row["name"]: str(row["id"]) for row in response.data}


async def _insert_itineraries_with_steps(
    db: AsyncClient,
    city_id: str,
    guide: CityGuideImport,
    spot_map: dict[str, str],
) -> int:
    """Insert itineraries + steps; returns total step count."""
    total_steps = 0
    for itin in guide.itineraries:
        itin_row = {
            "city_id": city_id,
            "theme": itin.theme,
            "time_of_day": itin.time_of_day.value,
            "title": itin.title.to_jsonb(),
            "catchy_phrase": itin.catchy_phrase.to_jsonb(),
            "best_for": itin.best_for.to_jsonb(),
            "duration_min_hrs": itin.duration_min_hrs,
            "duration_max_hrs": itin.duration_max_hrs,
            "total_walk_km": itin.total_walk_km,
            "total_transit_km": itin.total_transit_km,
            "flex_note": itin.flex_note.to_jsonb(),
            "is_recommended": itin.is_recommended,
            "is_premium": itin.is_premium,
            "rank_order": itin.rank_order,
        }
        itin_response = await db.table("itineraries").insert(itin_row).execute()
        itin_id = str(itin_response.data[0]["id"])

        step_rows = [
            {
                "itinerary_id": itin_id,
                "rank_order": step.rank_order,
                "spot_id": spot_map.get(step.spot_ref) if step.spot_ref else None,
                "title": step.title.to_jsonb() if step.title else None,
                "address": step.address,
                "description": step.description.to_jsonb(),
                "bon_vivant_notes": step.bon_vivant_notes.to_jsonb() if step.bon_vivant_notes else None,
                "must_try": step.must_try.to_jsonb() if step.must_try else None,
                "reservation": (
                    step.reservation.to_jsonb() if step.reservation else None
                ),
                "website": step.website,
                "distance_from_prev_km": step.distance_from_prev_km,
                "travel_mode": step.travel_mode.value if step.travel_mode else None,
                "time_on_site_min": step.time_on_site_min,
                "time_on_site_max": step.time_on_site_max,
            }
            for step in itin.steps
        ]
        if step_rows:
            await db.table("itinerary_steps").insert(step_rows).execute()
        total_steps += len(step_rows)

    return total_steps


async def _insert_tips(db: AsyncClient, city_id: str, guide: CityGuideImport) -> None:
    if not guide.tips:
        return
    rows = [
        {
            "city_id": city_id,
            "title": tip.title.to_jsonb(),
            "body": tip.body.to_jsonb(),
            "rank_order": tip.rank_order,
        }
        for tip in guide.tips
    ]
    await db.table("tips").insert(rows).execute()


async def _delete_city(db: AsyncClient, city_id: str) -> None:
    await db.table("cities").delete().eq("id", city_id).execute()


# ============================================================
# Public import function
# ============================================================


async def import_city_guide(
    guide: CityGuideImport,
    geocoder: Geocoder,
    db: AsyncClient,
    *,
    replace: bool = False,
) -> ImportResult:
    """Import a city guide JSON into the database as a draft.

    Steps (in order):
    1. Check slug / replace policy — raises before any DB writes.
    2. Validate spot_refs — raises before any DB writes.
    3. Geocode addresses (best-effort; never raises).
    4. Perform DB inserts; on any failure, clean up the partial insert
       (delete the city — CASCADE handles all child rows) and re-raise.
    5. Return ImportResult with counts and geocoding summary.
    """
    # Step 1 — slug / replace check
    existing_id, is_replacing = await _check_slug(db, guide.meta.slug, replace)

    # Step 2 — spot_ref validation (pure Python, no DB)
    _validate_spot_refs(guide)

    # Step 3 — geocode (best-effort)
    geo = await _geocode_guide(guide, geocoder)

    # Step 4 — "atomic" inserts with manual rollback.
    # The Supabase PostgREST client does not support SQL transactions.
    # On any failure after the city row is created, we delete it so that
    # cascading deletes remove all child rows, leaving the DB clean.
    new_city_id: str | None = None
    try:
        if existing_id is not None:
            await _delete_city(db, existing_id)

        new_city_id = await _insert_city(db, guide, geo)
        spot_map = await _insert_spots(db, new_city_id, guide, geo)
        total_steps = await _insert_itineraries_with_steps(
            db, new_city_id, guide, spot_map
        )
        await _insert_tips(db, new_city_id, guide)

    except Exception:
        # Rollback: delete the partially-inserted city (CASCADE cleans children).
        # We re-raise immediately; this block only does cleanup.
        if new_city_id is not None:
            try:
                await _delete_city(db, new_city_id)
            except Exception:  # noqa: BLE001 — cleanup must not mask the original error
                pass
        raise

    # Step 5 — build result
    return ImportResult(
        city_id=new_city_id,
        slug=guide.meta.slug,
        status="draft",
        replaced=is_replacing,
        counts=ImportCounts(
            attractions=len(guide.attractions),
            gourmet=len(guide.gourmet),
            itineraries=len(guide.itineraries),
            steps=total_steps,
            tips=len(guide.tips),
        ),
        geocoded=geo.geocoded,
        geocode_failed=geo.geocode_failed,
        review_notes=guide.review.unverified if guide.review else [],
    )
