from __future__ import annotations

from storage3.exceptions import StorageApiError

from supabase._async.client import AsyncClient

BUCKET_NAME = "guias"
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


async def get_signed_url(
    db: AsyncClient, storage_path: str, expires_in: int = 86400
) -> str | None:
    """Return a signed URL for the given Storage path, or None if it doesn't exist.

    A missing photo must never break the rest of the guide.
    """
    try:
        response = await db.storage.from_(BUCKET_NAME).create_signed_url(
            storage_path, expires_in
        )
    except StorageApiError:
        return None
    return response.get("signedURL")


async def resolve_single(db: AsyncClient, city_slug: str, slot: str) -> str | None:
    path = build_storage_path(city_slug, slot)
    return await get_signed_url(db, path)


async def resolve_gallery(
    db: AsyncClient, city_slug: str, slot: str, count: int
) -> list[str]:
    """Resolve up to `count` gallery photos, skipping any that don't exist."""
    urls: list[str] = []
    for index in range(1, count + 1):
        path = build_storage_path(city_slug, slot, index)
        url = await get_signed_url(db, path)
        if url is not None:
            urls.append(url)
    return urls
