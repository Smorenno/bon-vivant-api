from __future__ import annotations

import asyncio

from app.models.city import CityFonts, FontFile, FontFormat, FontStyle, GuideFont
from app.services.image_service import sign_paths
from supabase._async.client import AsyncClient


async def _fetch_families(client: AsyncClient, font_ids: list[str]) -> dict[str, str]:
    """Return {font_id: family} for the given font ids."""
    response = (
        await client.table("fonts").select("id, family").in_("id", font_ids).execute()
    )
    return {str(row["id"]): row["family"] for row in response.data}


async def _fetch_files(
    client: AsyncClient, font_ids: list[str]
) -> dict[str, list[dict]]:
    """Return font_files rows grouped by font_id."""
    response = (
        await client.table("font_files")
        .select("font_id, weight, style, format, storage_path")
        .in_("font_id", font_ids)
        .execute()
    )
    grouped: dict[str, list[dict]] = {}
    for row in response.data:
        grouped.setdefault(str(row["font_id"]), []).append(row)
    return grouped


def _build_files(rows: list[dict], signed: dict[str, str]) -> list[FontFile]:
    """FontFiles for the rows whose Storage path was signed (missing files skipped)."""
    return [
        FontFile(
            weight=row["weight"],
            style=FontStyle(row["style"]),
            format=FontFormat(row["format"]),
            url=signed[row["storage_path"]],
        )
        for row in sorted(rows, key=lambda r: (r["weight"], r["style"]))
        if row["storage_path"] in signed
    ]


async def resolve_city_fonts(
    client: AsyncClient, title_font_id: str | None, body_font_id: str | None
) -> CityFonts:
    """Build a guide's typography. A font with no available file resolves to None
    so the client falls back to the app default instead of breaking."""
    font_ids = [fid for fid in {title_font_id, body_font_id} if fid is not None]
    if not font_ids:
        return CityFonts()

    families, files_by_font = await asyncio.gather(
        _fetch_families(client, font_ids), _fetch_files(client, font_ids)
    )
    all_paths = [row["storage_path"] for rows in files_by_font.values() for row in rows]
    signed = await sign_paths(client, all_paths)

    resolved: dict[str, GuideFont] = {}
    for font_id, family in families.items():
        files = _build_files(files_by_font.get(font_id, []), signed)
        if files:
            resolved[font_id] = GuideFont(family=family, files=files)

    return CityFonts(
        title=resolved.get(str(title_font_id)) if title_font_id else None,
        body=resolved.get(str(body_font_id)) if body_font_id else None,
    )
