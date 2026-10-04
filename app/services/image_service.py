from __future__ import annotations

from storage3.exceptions import StorageApiError

from supabase._async.client import AsyncClient

BUCKET_NAME = "guides"
BASE_PREFIX = "media/media-guias"

# Slots with a single photo per city (no numeric suffix).
SINGLE_SLOTS = [
    "cover",
    "preview",
    "overview",
    "key_historical_context",
    "attraction_cover",
    "gourmet_cover",
    "port_cover",
    "itineraries_cover",
    "tips_cover",
]

# Gallery slots — each has its own numbering convention confirmed against
# the real uploaded filenames. Do not assume a single global format.
GALLERY_SLOTS: dict[str, dict[str, bool]] = {
    "attraction": {"zero_padded": False},
    "gourmet": {"zero_padded": False},
    "overview_highlight": {"zero_padded": True},
    "port": {"zero_padded": True},
}


def build_storage_path(city_slug: str, slot: str, index: int | None = None) -> str:
    """Build the Storage path for a slot, following the per-slot naming convention."""
    if index is None:
        filename = f"{city_slug}_{slot}.jpg"
    else:
        zero_padded = GALLERY_SLOTS[slot]["zero_padded"]
        suffix = f"{index:02d}" if zero_padded else str(index)
        filename = f"{city_slug}_{slot}_{suffix}.jpg"
    return f"{BASE_PREFIX}/{city_slug}/{filename}"


# Guide photos are non-sensitive marketing content; a week-long expiry keeps
# the URLs inside a cached offline bundle usable between refreshes.
SIGNED_URL_TTL_SECONDS = 7 * 24 * 3600


async def sign_paths(
    db: AsyncClient, paths: list[str], expires_in: int = SIGNED_URL_TTL_SECONDS
) -> dict[str, str]:
    """Sign many Storage paths in ONE request; return {path: url} for those that exist.

    Missing files are simply absent from the result — a missing photo must never
    break the rest of the guide. A failed request yields no URLs at all.
    """
    unique_paths = list(dict.fromkeys(paths))
    if not unique_paths:
        return {}
    try:
        items = await db.storage.from_(BUCKET_NAME).create_signed_urls(
            unique_paths, expires_in
        )
    except StorageApiError:
        return {}
    return {
        item["path"]: item["signedURL"]
        for item in items
        if item.get("signedURL") and not item.get("error")
    }


def gallery_paths(city_slug: str, slot: str, count: int) -> list[str]:
    """Storage paths for photos 1..count of a gallery slot."""
    return [build_storage_path(city_slug, slot, i) for i in range(1, count + 1)]


def pick_single(signed: dict[str, str], city_slug: str, slot: str) -> str | None:
    return signed.get(build_storage_path(city_slug, slot))


def pick_gallery(
    signed: dict[str, str], city_slug: str, slot: str, count: int
) -> list[str]:
    """Signed URLs of a gallery in order, skipping photos that don't exist."""
    paths = gallery_paths(city_slug, slot, count)
    return [signed[path] for path in paths if path in signed]


async def resolve_single(db: AsyncClient, city_slug: str, slot: str) -> str | None:
    signed = await sign_paths(db, [build_storage_path(city_slug, slot)])
    return pick_single(signed, city_slug, slot)


async def resolve_gallery(
    db: AsyncClient, city_slug: str, slot: str, count: int
) -> list[str]:
    """Resolve up to `count` gallery photos, skipping any that don't exist."""
    signed = await sign_paths(db, gallery_paths(city_slug, slot, count))
    return pick_gallery(signed, city_slug, slot, count)
