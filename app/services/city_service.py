from __future__ import annotations

from app.models.city import CityStatus
from app.schemas.import_guide import CityUpdate, SpotUpdate
from app.services.exceptions import CityNotFoundError, SpotNotFoundError
from supabase._async.client import AsyncClient


def _serialize_patch(raw: dict) -> dict:
    """Recursively convert Pydantic sub-models inside a model_dump to plain dicts.

    model_dump() already converts nested models to dicts in Pydantic v2, but
    LocalizedTextIn's to_jsonb() excludes None keys for cleaner jsonb storage.
    We re-serialize (L) fields using to_jsonb() when available.
    """
    result: dict = {}
    for key, value in raw.items():
        if hasattr(value, "to_jsonb"):
            result[key] = value.to_jsonb()
        elif isinstance(value, list):
            result[key] = [
                item.to_jsonb() if hasattr(item, "to_jsonb") else item for item in value
            ]
        elif key == "last_verified" and isinstance(value, str) and len(value) == 7:
            # JSON format is YYYY-MM; Postgres date column requires YYYY-MM-DD
            result[key] = f"{value}-01"
        else:
            result[key] = value
    return result


async def update_city(city_id: str, patch: CityUpdate, db: AsyncClient) -> dict:
    """Apply a partial update to a city; return the updated row.

    Only fields present in the PATCH body are written. Raises CityNotFoundError
    if no city with the given ID exists.
    """
    # Collect only explicitly-set fields from the Pydantic model
    raw = patch.model_dump(exclude_unset=True)
    if not raw:
        raise ValueError("No fields provided in patch")

    patch_data = _serialize_patch(raw)

    response = await db.table("cities").update(patch_data).eq("id", city_id).execute()
    if not response.data:
        raise CityNotFoundError(city_id)

    return response.data[0]


async def update_spot(spot_id: str, patch: SpotUpdate, db: AsyncClient) -> dict:
    """Apply a partial update to a spot; return the updated row."""
    raw = patch.model_dump(exclude_unset=True)
    if not raw:
        raise ValueError("No fields provided in patch")

    patch_data = _serialize_patch(raw)

    response = await db.table("spots").update(patch_data).eq("id", spot_id).execute()
    if not response.data:
        raise SpotNotFoundError(spot_id)

    return response.data[0]


async def set_city_status(city_id: str, status: CityStatus, db: AsyncClient) -> dict:
    """Change a city's publication status; return the updated row."""
    response = (
        await db.table("cities")
        .update({"status": status.value})
        .eq("id", city_id)
        .execute()
    )
    if not response.data:
        raise CityNotFoundError(city_id)

    return response.data[0]
