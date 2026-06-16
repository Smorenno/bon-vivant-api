from __future__ import annotations

import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel

# ============================================================
# Enums (mirror Postgres enum types)
# ============================================================


class SpotKind(str, Enum):
    attraction = "attraction"
    food = "food"


class SpotCategory(str, Enum):
    restaurant = "restaurant"
    cafe = "cafe"
    bar = "bar"


class TimeOfDay(str, Enum):
    day = "day"
    night = "night"


class TravelMode(str, Enum):
    walk = "walk"
    transit = "transit"
    taxi = "taxi"


class CityStatus(str, Enum):
    draft = "draft"
    published = "published"


class TransportMethod(str, Enum):
    walk = "walk"
    metro = "metro"
    tram = "tram"
    taxi = "taxi"
    train = "train"
    ferry = "ferry"


class ImageSlot(str, Enum):
    cover = "cover"
    overview_1 = "overview_1"
    overview_2 = "overview_2"
    spot = "spot"


# ============================================================
# LocalizedText — the i18n container.
# The backend serialises it as-is; the client resolves the language.
# ============================================================


class LocalizedText(BaseModel):
    es: str
    en: str | None = None
    fr: str | None = None


# ============================================================
# Structured jsonb sub-objects (used inside city jsonb arrays)
# ============================================================


class Highlight(BaseModel):
    label: LocalizedText
    description: LocalizedText


class TransportOption(BaseModel):
    method: TransportMethod
    time_label: str
    tips: LocalizedText


class Note(BaseModel):
    heading: LocalizedText
    text: LocalizedText


class Image(BaseModel):
    id: UUID
    city_id: UUID
    spot_id: UUID | None = None
    slot: ImageSlot
    storage_path: str
    alt_text: LocalizedText | None = None


# ============================================================
# Spot
# ============================================================


class Spot(BaseModel):
    id: UUID
    city_id: UUID
    kind: SpotKind
    category: SpotCategory | None = None
    name: str
    address: str
    latitude: float | None = None
    longitude: float | None = None
    distance_from_port_km: float | None = None
    rank_order: int
    website: str | None = None
    manuel_quote: LocalizedText
    reservation: LocalizedText | None = None
    # Attraction-only fields
    what_it_is: LocalizedText | None = None
    why_it_matters: LocalizedText | None = None
    good_to_know: LocalizedText | None = None
    # Food-only fields
    cuisine_type: LocalizedText | None = None
    category_label: LocalizedText | None = None
    must_try: LocalizedText | None = None
    best_time: LocalizedText | None = None


# ============================================================
# Itinerary + steps
# ============================================================


class ItineraryStep(BaseModel):
    id: UUID
    itinerary_id: UUID
    rank_order: int
    spot_id: UUID | None = None
    name: str | None = None  # Resolved from linked spot when spot_id is set
    title: LocalizedText | None = None  # Only when step has no linked spot
    address: str | None = None
    description: LocalizedText
    bon_vivant_notes: LocalizedText | None = None
    must_try: LocalizedText | None = None
    reservation: LocalizedText | None = None
    website: str | None = None
    distance_from_prev_km: float | None = None
    travel_mode: TravelMode | None = None
    time_on_site_min: int | None = None
    time_on_site_max: int | None = None


class Itinerary(BaseModel):
    id: UUID
    city_id: UUID
    theme: str
    time_of_day: TimeOfDay
    title: LocalizedText
    catchy_phrase: LocalizedText
    best_for: LocalizedText
    duration_min_hrs: float
    duration_max_hrs: float
    total_walk_km: float
    total_transit_km: float | None = None
    flex_note: LocalizedText
    is_recommended: bool
    is_premium: bool
    rank_order: int
    steps: list[ItineraryStep]
    is_locked: bool  # Computed by access_service; never stored in DB


# ============================================================
# Tip
# ============================================================


class Tip(BaseModel):
    id: UUID
    city_id: UUID | None = None  # None = home carousel
    title: LocalizedText
    body: LocalizedText
    rank_order: int


# ============================================================
# City response shapes
# ============================================================


class CityImages(BaseModel):
    cover: str | None = None
    preview: str | None = None
    overview: str | None = None
    key_historical_context: str | None = None
    overview_highlights: list[str]
    attraction_cover: str | None = None
    attraction_gallery: list[str]
    gourmet_cover: str | None = None
    gourmet_gallery: list[str]
    port_cover: str | None = None
    port_gallery: list[str]
    itineraries_cover: str | None = None
    tips_cover: str | None = None


class CityListItem(BaseModel):
    id: UUID
    slug: str
    name: str
    country_code: str
    tagline: LocalizedText
    status: CityStatus
    is_unlocked: bool
    cover: str | None = None


class CityGuide(BaseModel):
    id: UUID
    slug: str
    name: str
    country_code: str
    tagline: LocalizedText
    intro: LocalizedText
    historical_context: LocalizedText
    port_description: LocalizedText
    distance_to_center: LocalizedText
    port_facilities: LocalizedText
    port_recommendation: LocalizedText
    port_lat: float | None = None
    port_lng: float | None = None
    highlights: list[Highlight]
    transport_options: list[TransportOption]
    what_to_know: list[Note]
    status: CityStatus
    last_verified: datetime.date | None = None
    spots: list[Spot]
    itineraries: list[Itinerary]
    tips: list[Tip]
    images: CityImages
    is_unlocked: bool


class CityGuidePreview(BaseModel):
    id: UUID
    slug: str
    name: str
    country_code: str
    tagline: LocalizedText
    intro: LocalizedText
    highlights: list[Highlight]
    tips: list[Tip]  # First tip only
    is_unlocked: bool


# ============================================================
# Error schema — used by all endpoints
# ============================================================


class ErrorResponse(BaseModel):
    detail: str
    code: str
