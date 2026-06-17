"""CLI to compress and upload city guide photos to Supabase Storage.

Usage:
    python scripts/upload_photos.py <photos-dir> <city-slug> [--dry-run]

Options:
    --dry-run   Compress and validate each file but do NOT upload to Storage.
                Useful to preview sizes and catch naming issues before committing.

The script connects with service_role (no JWT, no admin login required).
Every file must follow the naming convention expected by image_service.py:
    {city_slug}_{slot}.jpg           — single-photo slots
    {city_slug}_{slot}_{n}.jpg       — gallery slots (n without leading zero)
    {city_slug}_{slot}_{nn}.jpg      — gallery slots (nn with leading zero)
Unrecognized names are reported as rejected without stopping the rest.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload city guide photos to Supabase Storage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "photos_dir", type=Path, help="Folder containing the .jpg files"
    )
    parser.add_argument("city_slug", type=str, help="City slug (e.g. yokohama)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Compress and validate without uploading to Storage",
    )
    return parser.parse_args()


def _print_result(result: object, dry_run: bool) -> None:
    from app.schemas.image_upload import PhotoUploadResult

    assert isinstance(result, PhotoUploadResult)
    label = "[DRY RUN] " if dry_run else ""

    print()
    print(f"=== {label}Photo upload — {result.city_slug} ===")

    saved_bytes = sum(
        u.original_size_bytes - u.compressed_size_bytes for u in result.uploaded
    )
    total_original = sum(u.original_size_bytes for u in result.uploaded)
    total_compressed = sum(u.compressed_size_bytes for u in result.uploaded)

    print(f"\n  {'Would upload' if dry_run else 'Uploaded'} ({len(result.uploaded)}):")
    for u in result.uploaded:
        ratio = (1 - u.compressed_size_bytes / u.original_size_bytes) * 100
        orig_kb = u.original_size_bytes / 1024
        comp_kb = u.compressed_size_bytes / 1024
        size_info = f"{orig_kb:.0f}KB → {comp_kb:.0f}KB  ({ratio:.0f}% smaller)"
        print(f"  ✓ {u.filename}  {size_info}")
        print(f"      → {u.storage_path}")

    if total_original:
        saved_kb = saved_bytes / 1024
        overall = (1 - total_compressed / total_original) * 100
        print(f"\n  Total compression saving: {saved_kb:.0f} KB ({overall:.0f}%)")

    if result.rejected:
        print(f"\n  Rejected ({len(result.rejected)}):")
        for r in result.rejected:
            print(f"  ✗ {r.filename}  [{r.reason}]")

    if result.failed:
        print(f"\n  Failed ({len(result.failed)}):")
        for f in result.failed:
            print(f"  ✗ {f.filename}  [{f.reason}]")

    print()


async def _run(args: argparse.Namespace) -> None:
    from app.db.supabase import close_supabase, get_supabase_client, init_supabase
    from app.services.image_upload_service import UploadedPhoto, upload_guide_photos

    # Validate photos directory
    photos_dir: Path = args.photos_dir
    if not photos_dir.is_dir():
        print(
            f"Error: '{photos_dir}' is not a directory or does not exist.",
            file=sys.stderr,
        )
        sys.exit(1)

    jpg_files = sorted(
        p
        for p in photos_dir.iterdir()
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg")
    )
    if not jpg_files:
        print(f"Error: no .jpg/.jpeg files found in '{photos_dir}'.", file=sys.stderr)
        sys.exit(1)

    # Read files into memory before touching the DB
    photos: list[UploadedPhoto] = []
    for path in jpg_files:
        try:
            photos.append(UploadedPhoto(filename=path.name, content=path.read_bytes()))
        except OSError as exc:
            print(f"Error reading '{path.name}': {exc}", file=sys.stderr)
            sys.exit(1)

    await init_supabase()
    try:
        db = get_supabase_client()

        # Verify city exists (any status — can upload to a draft city)
        city_check = (
            await db.table("cities")
            .select("id")
            .eq("slug", args.city_slug)
            .limit(1)
            .execute()
        )
        if not city_check.data:
            print(
                f"\nError: city '{args.city_slug}' does not exist in the database.\n"
                "Import the guide JSON first with scripts/import_guide.py.",
                file=sys.stderr,
            )
            sys.exit(1)

        if args.dry_run:
            # Compress + validate in process, but swap out the real Storage upload
            # by running upload_guide_photos against a no-op Storage stub.
            result = await _dry_run_upload(args.city_slug, photos)
        else:
            result = await upload_guide_photos(db, args.city_slug, photos)

        _print_result(result, dry_run=args.dry_run)

        if result.failed:
            sys.exit(1)

    finally:
        await close_supabase()


async def _dry_run_upload(city_slug: str, photos: list) -> object:
    """Run compression + slot validation without touching Storage."""
    from app.schemas.image_upload import (
        FailedPhoto,
        PhotoUploadResult,
        RejectedPhoto,
        UploadedPhotoInfo,
    )
    from app.services.image_compression_service import (
        ImageCompressionError,
        compress_image,
    )
    from app.services.image_service import build_storage_path
    from app.services.image_upload_service import (
        MAX_UPLOAD_SIZE_BYTES,
        UploadedPhoto,
        _match_slot,
    )

    uploaded: list[UploadedPhotoInfo] = []
    rejected: list[RejectedPhoto] = []
    failed: list[FailedPhoto] = []

    for photo in photos:
        assert isinstance(photo, UploadedPhoto)

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

        try:
            compressed = compress_image(photo.content, photo.filename)
        except ImageCompressionError as exc:
            failed.append(FailedPhoto(filename=photo.filename, reason=exc.reason))
            continue

        uploaded.append(
            UploadedPhotoInfo(
                filename=photo.filename,
                original_size_bytes=len(photo.content),
                compressed_size_bytes=len(compressed),
                storage_path=build_storage_path(city_slug, slot, index),
            )
        )

    return PhotoUploadResult(
        city_slug=city_slug, uploaded=uploaded, rejected=rejected, failed=failed
    )


def main() -> None:
    args = _parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
