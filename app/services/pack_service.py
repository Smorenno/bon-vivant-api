from __future__ import annotations

from app.models.pack import PackCity, PackDetail, PacksListResponse
from supabase._async.client import AsyncClient


def _build_pack_detail(pack_row: dict, cities: list[PackCity]) -> PackDetail:
    return PackDetail(
        id=pack_row["id"],
        name=pack_row["name"],
        price_eur=pack_row.get("price_eur"),
        city_count=pack_row.get("city_count"),
        is_unlimited=bool(pack_row.get("is_unlimited", False)),
        store_product_id=pack_row.get("store_product_id"),
        cities=cities,
    )


async def get_packs(client: AsyncClient) -> PacksListResponse:
    """Store listing: the 4 packs with their published cities.

    Public data by design (migration 006 §5) — shown before purchase,
    so no access computation is involved.
    """
    packs_response = await client.table("packs").select("*").execute()
    if not packs_response.data:
        return PacksListResponse(packs=[])

    links_response = await client.table("pack_cities").select("*").execute()
    city_ids = list({str(row["city_id"]) for row in links_response.data})

    cities_by_id: dict[str, dict] = {}
    if city_ids:
        cities_response = (
            await client.table("cities")
            .select("id, slug, name, status")
            .in_("id", city_ids)
            .eq("status", "published")
            .execute()
        )
        cities_by_id = {str(row["id"]): row for row in cities_response.data}

    cities_by_pack: dict[str, list[PackCity]] = {}
    for link in links_response.data:
        city_row = cities_by_id.get(str(link["city_id"]))
        if city_row is None:  # unpublished cities stay out of the storefront
            continue
        cities_by_pack.setdefault(str(link["pack_id"]), []).append(
            PackCity(id=city_row["id"], slug=city_row["slug"], name=city_row["name"])
        )

    # Cheapest first — matches the store presentation order.
    sorted_packs = sorted(
        packs_response.data, key=lambda row: float(row.get("price_eur") or 0)
    )
    packs = [
        _build_pack_detail(row, cities_by_pack.get(str(row["id"]), []))
        for row in sorted_packs
    ]
    return PacksListResponse(packs=packs)
