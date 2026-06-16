"""Tests for image compression and the batch photo upload endpoint."""

from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api import deps
from app.main import app
from app.services import image_upload_service
from app.services.image_compression_service import (
    ImageCompressionError,
    compress_image,
    is_cover_like,
)
from app.services.image_service import build_storage_path
from app.services.image_upload_service import UploadedPhoto, upload_guide_photos
from tests.fake_supabase import FakeSupabaseClient

CITY_SLUG = "test-city"


def _jpeg_bytes(width: int, height: int, exif: object = None) -> bytes:
    img = Image.new("RGB", (width, height), color=(200, 50, 50))
    buf = io.BytesIO()
    if exif is not None:
        img.save(buf, format="JPEG", exif=exif)
    else:
        img.save(buf, format="JPEG")
    return buf.getvalue()


# ============================================================
# 1. is_cover_like
# ============================================================


def test_is_cover_like_matches_cover_suffix() -> None:
    assert is_cover_like("yokohama_attraction_cover.jpg") is True


def test_is_cover_like_matches_preview_suffix() -> None:
    assert is_cover_like("yokohama_preview.jpg") is True


def test_is_cover_like_matches_exact_preview_filename() -> None:
    assert is_cover_like("preview.jpg") is True


def test_is_cover_like_false_for_regular_slot() -> None:
    assert is_cover_like("yokohama_attraction_1.jpg") is False


# ============================================================
# 2. compress_image
# ============================================================


def test_compress_image_resizes_to_default_max_width() -> None:
    raw = _jpeg_bytes(2000, 1000)
    result = compress_image(raw, "yokohama_overview.jpg")

    out = Image.open(io.BytesIO(result))
    assert out.width == 1600
    assert len(result) <= len(raw)


def test_compress_image_resizes_cover_to_smaller_max_width() -> None:
    raw = _jpeg_bytes(2000, 1000)
    result = compress_image(raw, "yokohama_attraction_cover.jpg")

    out = Image.open(io.BytesIO(result))
    assert out.width == 800


def test_compress_image_does_not_upscale_small_images() -> None:
    raw = _jpeg_bytes(300, 200)
    result = compress_image(raw, "yokohama_overview.jpg")

    out = Image.open(io.BytesIO(result))
    assert out.size == (300, 200)


def test_compress_image_applies_exif_rotation() -> None:
    img = Image.new("RGB", (600, 400), color=(10, 200, 10))
    exif = img.getexif()
    exif[0x0112] = 6  # Orientation: rotate 90 CW
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)

    result = compress_image(buf.getvalue(), "yokohama_overview.jpg")

    out = Image.open(io.BytesIO(result))
    assert out.size == (400, 600)


def test_compress_image_raises_image_compression_error_for_garbage_bytes() -> None:
    with pytest.raises(ImageCompressionError):
        compress_image(b"not a real image", "yokohama_overview.jpg")


# ============================================================
# 3. upload_guide_photos — service level, mocked Storage
# ============================================================


async def test_upload_guide_photos_valid_file_is_uploaded() -> None:
    db = FakeSupabaseClient()
    raw = _jpeg_bytes(100, 100)
    photos = [UploadedPhoto(filename=f"{CITY_SLUG}_overview.jpg", content=raw)]

    result = await upload_guide_photos(db, CITY_SLUG, photos)

    assert len(result.uploaded) == 1
    assert result.uploaded[0].storage_path == build_storage_path(CITY_SLUG, "overview")
    assert result.rejected == []
    assert result.failed == []


async def test_upload_guide_photos_unrecognized_name_is_rejected() -> None:
    db = FakeSupabaseClient()
    photos = [UploadedPhoto(filename="random_name.jpg", content=_jpeg_bytes(50, 50))]

    result = await upload_guide_photos(db, CITY_SLUG, photos)

    assert result.uploaded == []
    assert len(result.rejected) == 1
    assert result.rejected[0].reason == "unrecognized_slot_pattern"


async def test_upload_guide_photos_storage_failure_does_not_abort_batch() -> None:
    db = FakeSupabaseClient()
    failing_path = build_storage_path(CITY_SLUG, "overview")
    db.storage.fail_upload_paths.add(failing_path)

    photos = [
        UploadedPhoto(
            filename=f"{CITY_SLUG}_overview.jpg", content=_jpeg_bytes(100, 100)
        ),
        UploadedPhoto(
            filename=f"{CITY_SLUG}_attraction_1.jpg", content=_jpeg_bytes(100, 100)
        ),
    ]

    result = await upload_guide_photos(db, CITY_SLUG, photos)

    assert len(result.failed) == 1
    assert result.failed[0].filename == f"{CITY_SLUG}_overview.jpg"
    assert len(result.uploaded) == 1
    assert result.uploaded[0].filename == f"{CITY_SLUG}_attraction_1.jpg"


async def test_upload_guide_photos_oversized_file_is_rejected() -> None:
    db = FakeSupabaseClient()
    photos = [
        UploadedPhoto(
            filename=f"{CITY_SLUG}_overview.jpg",
            content=b"0" * (image_upload_service.MAX_UPLOAD_SIZE_BYTES + 1),
        )
    ]

    result = await upload_guide_photos(db, CITY_SLUG, photos)

    assert result.rejected[0].reason == "file_too_large"
    assert result.uploaded == []


# ============================================================
# 4. Endpoint — auth, existence, happy path
# ============================================================

_CITY_ID = str(uuid.uuid4())


def _guide_db() -> FakeSupabaseClient:
    db = FakeSupabaseClient()
    db.seed(
        "cities",
        [{"id": _CITY_ID, "slug": CITY_SLUG, "status": "draft"}],
    )
    return db


def _http_upload(
    db: FakeSupabaseClient,
    user: dict,
    slug: str,
    files: list[tuple[str, bytes]],
    monkeypatch: pytest.MonkeyPatch,
) -> object:
    async def _noop() -> None:
        pass

    monkeypatch.setattr("app.main.init_supabase", _noop)
    monkeypatch.setattr("app.main.close_supabase", _noop)
    app.dependency_overrides[deps.get_current_user] = lambda: user
    app.dependency_overrides[deps.get_db] = lambda: db
    upload_files = [
        ("files", (filename, content, "image/jpeg")) for filename, content in files
    ]
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/admin/cities/{slug}/photos/upload", files=upload_files
        )
    app.dependency_overrides.clear()
    return response


def test_upload_endpoint_requires_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _guide_db()
    response = _http_upload(
        db,
        {"sub": "user-1"},
        CITY_SLUG,
        [(f"{CITY_SLUG}_overview.jpg", _jpeg_bytes(50, 50))],
        monkeypatch,
    )
    assert response.status_code == 403


def test_upload_endpoint_nonexistent_city_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeSupabaseClient()
    db.seed("cities", [])
    response = _http_upload(
        db,
        {"app_metadata": {"role": "admin"}},
        "does-not-exist",
        [(f"{CITY_SLUG}_overview.jpg", _jpeg_bytes(50, 50))],
        monkeypatch,
    )
    assert response.status_code == 404


def test_upload_endpoint_success_returns_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _guide_db()
    response = _http_upload(
        db,
        {"app_metadata": {"role": "admin"}},
        CITY_SLUG,
        [
            (f"{CITY_SLUG}_overview.jpg", _jpeg_bytes(2000, 1000)),
            ("garbage_name.jpg", _jpeg_bytes(50, 50)),
        ],
        monkeypatch,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["city_slug"] == CITY_SLUG
    assert len(body["uploaded"]) == 1
    assert len(body["rejected"]) == 1
