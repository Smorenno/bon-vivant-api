from __future__ import annotations

from pydantic import BaseModel


class UploadedPhotoInfo(BaseModel):
    filename: str
    original_size_bytes: int
    compressed_size_bytes: int
    storage_path: str


class RejectedPhoto(BaseModel):
    filename: str
    reason: str  # e.g. "unrecognized_slot_pattern", "file_too_large"


class FailedPhoto(BaseModel):
    filename: str
    reason: str


class PhotoUploadResult(BaseModel):
    city_slug: str
    uploaded: list[UploadedPhotoInfo]
    rejected: list[RejectedPhoto]
    failed: list[FailedPhoto]
