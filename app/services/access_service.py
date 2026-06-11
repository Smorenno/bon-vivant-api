from supabase._async.client import AsyncClient


async def is_city_unlocked(client: AsyncClient, user_id: str, city_id: str) -> bool:
    """Return True if the user has purchased a pack that contains this city."""
    purchases = (
        await client.table("user_purchases")
        .select("pack_id")
        .eq("user_id", user_id)
        .eq("is_valid", True)
        .execute()
    )
    pack_ids = [row["pack_id"] for row in purchases.data]
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


async def _user_has_pass(client: AsyncClient, user_id: str) -> bool:
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


async def is_itinerary_locked(
    client: AsyncClient,
    user_id: str,
    itinerary_is_premium: bool,
) -> bool:
    """Return True when a premium (night) itinerary requires the Pass the user lacks."""
    if not itinerary_is_premium:
        return False
    return not await _user_has_pass(client, user_id)
