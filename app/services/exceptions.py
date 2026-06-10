from __future__ import annotations

from app.exceptions import AppError

# Re-export so callers can import everything from one place.
__all__ = [
    "CitySlugExistsError",
    "PublishedCityReplaceError",
    "SpotRefNotFoundError",
    "GuideValidationError",
    "CityNotFoundError",
    "SpotNotFoundError",
]

# ---- re-export from the root exceptions module ----
from app.exceptions import CityNotFoundError  # noqa: F401


class CitySlugExistsError(AppError):
    def __init__(self, slug: str) -> None:
        super().__init__(
            409,
            f"A city with slug '{slug}' already exists. "
            "Use replace=true to overwrite a draft.",
            "city_slug_exists",
        )
        self.slug = slug


class PublishedCityReplaceError(AppError):
    """Raised when replace=True but the existing city is published.

    A published guide must be unpublished first before it can be reimported.
    This prevents an in-progress import from silently replacing live content.
    """

    def __init__(self, slug: str) -> None:
        super().__init__(
            409,
            f"City '{slug}' is published and cannot be replaced by an import. "
            "Unpublish it first.",
            "published_city_replace",
        )
        self.slug = slug


class SpotRefNotFoundError(AppError):
    def __init__(self, spot_ref: str, itinerary_theme: str, step_rank: int) -> None:
        super().__init__(
            422,
            f"spot_ref '{spot_ref}' does not match any attraction or gourmet in this "
            f"guide (itinerary '{itinerary_theme}', step {step_rank}).",
            "spot_ref_not_found",
        )
        self.spot_ref = spot_ref
        self.itinerary_theme = itinerary_theme
        self.step_rank = step_rank


class GuideValidationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(422, message, "guide_validation_error")


class SpotNotFoundError(AppError):
    def __init__(self, spot_id: str) -> None:
        super().__init__(404, f"Spot '{spot_id}' not found.", "spot_not_found")
        self.spot_id = spot_id
