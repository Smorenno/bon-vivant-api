"""CLI to import a city guide JSON file into the database.

Usage:
    python -m scripts.import_guide path/to/guide.json [--replace]

Options:
    --replace   Replace an existing draft city with the same slug.
                Fails with a clear message if the existing city is published.

The script uses the same import_service logic as the admin API endpoint,
so every validation and geocoding rule applies identically.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Ensure the repo root is on the path so `app` is importable when the script
# is run directly (e.g. `python scripts/import_guide.py ...`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a city guide JSON file into the Bon Vivant database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("file", type=Path, help="Path to the guide JSON file")
    parser.add_argument(
        "--replace",
        action="store_true",
        default=False,
        help="Replace an existing draft (fails if the city is already published)",
    )
    return parser.parse_args()


def _print_result(result: object) -> None:  # result is ImportResult
    from app.schemas.import_guide import ImportResult

    assert isinstance(result, ImportResult)
    print()
    print("=== Import complete ===")
    print(f"  city_id : {result.city_id}")
    print(f"  slug    : {result.slug}")
    print(f"  status  : {result.status}")
    print(f"  replaced: {result.replaced}")
    print()
    print("Counts:")
    print(f"  attractions : {result.counts.attractions}")
    print(f"  gourmet     : {result.counts.gourmet}")
    print(f"  itineraries : {result.counts.itineraries}")
    print(f"  steps       : {result.counts.steps}")
    print(f"  tips        : {result.counts.tips}")

    if result.geocoded:
        print()
        print(f"Geocoded ({len(result.geocoded)}):")
        for name in result.geocoded:
            print(f"  ✓ {name}")

    if result.geocode_failed:
        print()
        print(f"Geocoding failed — coords null ({len(result.geocode_failed)}):")
        for name in result.geocode_failed:
            print(f"  ✗ {name}")

    if result.review_notes:
        print()
        print("Review notes (from _review.unverified):")
        for note in result.review_notes:
            print(f"  • {note}")

    print()


async def _run(args: argparse.Namespace) -> None:
    # Parse JSON
    try:
        raw = json.loads(args.file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error reading {args.file}: {exc}", file=sys.stderr)
        sys.exit(1)

    # Validate with Pydantic
    from app.schemas.import_guide import CityGuideImport

    try:
        guide = CityGuideImport.model_validate(raw)
    except ValidationError as exc:
        print("Validation error — guide JSON does not match the expected schema:")
        for error in exc.errors():
            loc = " → ".join(str(p) for p in error["loc"])
            print(f"  [{loc}] {error['msg']}")
        sys.exit(1)

    # Initialise Supabase and run import
    from app.db.supabase import close_supabase, get_supabase_client, init_supabase
    from app.services.exceptions import (
        CitySlugExistsError,
        GuideValidationError,
        PublishedCityReplaceError,
        SpotRefNotFoundError,
    )
    from app.services.geocoding_service import get_geocoder
    from app.services.import_service import import_city_guide

    await init_supabase()
    try:
        db = get_supabase_client()
        geocoder = get_geocoder()
        result = await import_city_guide(guide, geocoder, db, replace=args.replace)
        _print_result(result)
    except CitySlugExistsError:
        print(
            f"\nError: slug '{guide.meta.slug}' already exists.\n"
            "Use --replace to overwrite a draft.",
            file=sys.stderr,
        )
        sys.exit(1)
    except PublishedCityReplaceError:
        print(
            f"\nError: city '{guide.meta.slug}' is published and cannot be replaced "
            "by an import.\nUnpublish it first via the admin API.",
            file=sys.stderr,
        )
        sys.exit(1)
    except SpotRefNotFoundError as exc:
        print(
            f"\nError: spot_ref '{exc.spot_ref}' not found "
            f"(itinerary '{exc.itinerary_theme}', step {exc.step_rank}).",
            file=sys.stderr,
        )
        sys.exit(1)
    except GuideValidationError as exc:
        print(f"\nValidation error: {exc.detail}", file=sys.stderr)
        sys.exit(1)
    finally:
        await close_supabase()


def main() -> None:
    args = _parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
