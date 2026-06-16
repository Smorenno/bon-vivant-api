from __future__ import annotations

from pydantic import BaseModel
from storage3.exceptions import StorageApiError

from app.schemas.image_upload import (
    FailedPhoto,
    PhotoUploadResult,
    RejectedPhoto,
    UploadedPhotoInfo,
)
from app.services.image_compression_service import ImageCompressionError, compress_image
from app.services.image_service import (
    BUCKET_NAME,
    GALLERY_SLOTS,
    SINGLE_SLOTS,
    build_storage_path,
)
from supabase._async.client import AsyncClient

MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024


class UploadedPhoto(BaseModel):
    """A single file read into memory by the endpoint, ready for processing."""

    filename: str
    content: bytes


def _match_slot(city_slug: str, filename: str) -> tuple[str, int | None] | None:
    """Match an uploaded filename against the known slot naming convention.

    Returns (slot, index) — index is None for single slots. Returns None
    when the filename doesn't follow the {city_slug}_{slot}[_{n}].jpg pattern
    for any known slot.
    """
    if not filename.lower().endswith(".jpg"):
        return None
    stem = filename[: -len(".jpg")]

    prefix = f"{city_slug}_"
    if not stem.startswith(prefix):
        return None
    remainder = stem[len(prefix) :]

    if remainder in SINGLE_SLOTS:
        return remainder, None

    for slot in GALLERY_SLOTS:
        gallery_prefix = f"{slot}_"
        if remainder.startswith(gallery_prefix):
            index_part = remainder[len(gallery_prefix) :]
            if index_part.isdigit():
                return slot, int(index_part)

    return None


async def upload_guide_photos(
    db: AsyncClient, city_slug: str, files: list[UploadedPhoto]
) -> PhotoUploadResult:
    """Compress and upload each photo; a single failure never aborts the batch."""
    uploaded: list[UploadedPhotoInfo] = []
    rejected: list[RejectedPhoto] = []
    failed: list[FailedPhoto] = []

    for photo in files:
        if len(photo.content) > MAX_UPLOAD_SIZE_BYTES:
            rejected.append(
                RejectedPhoto(filename=photo.filename, reason="file_too_large")
            )
            continue

        match = _match_slot(city_slug, photo.filename)
        if match is None:
            rejected.append(
                RejectedPhoto(
                    filename=photo.filename, reason="unrecognized_slot_pattern"
                )
            )
            continue
        slot, index = match
        storage_path = build_storage_path(city_slug, slot, index)

        try:
            compressed = compress_image(photo.content, photo.filename)
        except ImageCompressionError as exc:
            failed.append(FailedPhoto(filename=photo.filename, reason=exc.reason))
            continue

        try:
            await db.storage.from_(BUCKET_NAME).upload(
                storage_path,
                compressed,
                {"content-type": "image/jpeg", "upsert": "true"},
            )
        except StorageApiError as exc:
            failed.append(FailedPhoto(filename=photo.filename, reason=exc.message))
            continue

        uploaded.append(
            UploadedPhotoInfo(
                filename=photo.filename,
                original_size_bytes=len(photo.content),
                compressed_size_bytes=len(compressed),
                storage_path=storage_path,
            )
        )

    return PhotoUploadResult(
        city_slug=city_slug, uploaded=uploaded, rejected=rejected, failed=failed
    )
