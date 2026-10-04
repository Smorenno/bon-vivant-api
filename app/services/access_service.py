from supabase._async.client import AsyncClient


async def _valid_pack_ids(client: AsyncClient, user_id: str) -> list[str]:
    """Pack ids of the user's valid (store-verified, not revoked) purchases."""
    purchases = (
        await client.table("user_purchases")
        .select("pack_id")
        .eq("user_id", user_id)
        .eq("is_valid", True)
        .execute()
    )
    return [row["pack_id"] for row in purchases.data]


async def is_city_unlocked(client: AsyncClient, user_id: str, city_id: str) -> bool:
    """Return True if the user has purchased a pack that contains this city."""
    pack_ids = await _valid_pack_ids(client, user_id)
    if not pack_ids:
        return False

    mapping = (
        await client.table("pack_cities")
        .select("pack_id")
        .eq("city_id", city_id)
        .in_("pack_id", pack_ids)
        .execute()
    )
    return len(mapping.data) > 0


async def unlocked_city_ids(client: AsyncClient, user_id: str) -> set[str]:
    """Every city id the user can open — 2 queries regardless of city count."""
    pack_ids = await _valid_pack_ids(client, user_id)
    if not pack_ids:
        return set()

    mapping = (
        await client.table("pack_cities")
        .select("city_id")
        .in_("pack_id", pack_ids)
        .execute()
    )
    return {str(row["city_id"]) for row in mapping.data}


async def has_active_pass(client: AsyncClient, user_id: str) -> bool:
    """Return True if the user holds a valid unlimited (Pass) pack."""
    unlimited = (
        await client.table("packs").select("id").eq("is_unlimited", True).execute()
    )
    unlimited_ids = [row["id"] for row in unlimited.data]
    if not unlimited_ids:
        return False

    purchases = (
        await client.table("user_purchases")
        .select("id")
        .eq("user_id", user_id)
        .eq("is_valid", True)
        .in_("pack_id", unlimited_ids)
        .execute()
    )
    return len(purchases.data) > 0
