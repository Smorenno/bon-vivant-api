"""Tests for per-guide font resolution."""

from __future__ import annotations

import uuid

import pytest

from app.models.city import CityFonts
from app.services.font_service import resolve_city_fonts
from tests.fake_supabase import FakeSupabaseClient

_TITLE_ID = str(uuid.uuid4())
_BODY_ID = str(uuid.uuid4())
_EMPTY_ID = str(uuid.uuid4())

_TITLE_PATH = "media/fonts/pathos/pathos_400.otf"
_BODY_REGULAR = "media/fonts/inter/inter_400.ttf"
_BODY_BOLD = "media/fonts/inter/inter_700.ttf"
_BODY_MISSING = "media/fonts/inter/inter_400_italic.ttf"


@pytest.fixture
def font_db() -> FakeSupabaseClient:
    db = FakeSupabaseClient()
    db.seed(
        "fonts",
        [
            {"id": _TITLE_ID, "family": "Pathos"},
            {"id": _BODY_ID, "family": "Inter"},
            {"id": _EMPTY_ID, "family": "NoFiles"},
        ],
    )
    db.seed(
        "font_files",
        [
            {
                "font_id": _TITLE_ID,
                "weight": 400,
                "style": "normal",
                "format": "otf",
                "storage_path": _TITLE_PATH,
            },
            {
                "font_id": _BODY_ID,
                "weight": 700,
                "style": "normal",
                "format": "ttf",
                "storage_path": _BODY_BOLD,
            },
            {
                "font_id": _BODY_ID,
                "weight": 400,
                "style": "normal",
                "format": "ttf",
                "storage_path": _BODY_REGULAR,
            },
            {
                "font_id": _BODY_ID,
                "weight": 400,
                "style": "italic",
                "format": "ttf",
                "storage_path": _BODY_MISSING,
            },
        ],
    )
    db.storage.existing_paths.update({_TITLE_PATH, _BODY_REGULAR, _BODY_BOLD})
    return db


async def test_no_fonts_returns_defaults(font_db: FakeSupabaseClient) -> None:
    assert await resolve_city_fonts(font_db, None, None) == CityFonts()


async def test_resolves_title_and_body(font_db: FakeSupabaseClient) -> None:
    fonts = await resolve_city_fonts(font_db, _TITLE_ID, _BODY_ID)

    assert fonts.title is not None
    assert fonts.title.family == "Pathos"
    assert [f.url for f in fonts.title.files] == [
        f"https://signed.example.com/{_TITLE_PATH}"
    ]

    assert fonts.body is not None
    assert fonts.body.family == "Inter"
    # Sorted by weight; the italic file is missing from Storage and skipped.
    assert [(f.weight, f.style.value) for f in fonts.body.files] == [
        (400, "normal"),
        (700, "normal"),
    ]


async def test_same_font_for_title_and_body(font_db: FakeSupabaseClient) -> None:
    fonts = await resolve_city_fonts(font_db, _BODY_ID, _BODY_ID)
    assert fonts.title == fonts.body
    assert fonts.title is not None


async def test_font_without_files_falls_back(font_db: FakeSupabaseClient) -> None:
    fonts = await resolve_city_fonts(font_db, _EMPTY_ID, None)
    assert fonts.title is None


async def test_unknown_font_id_falls_back(font_db: FakeSupabaseClient) -> None:
    fonts = await resolve_city_fonts(font_db, str(uuid.uuid4()), None)
    assert fonts.title is None
