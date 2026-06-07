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
    latitude: float
    longitude: float
    distance_from_port_km: float
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
    title: LocalizedText | None = None  # Only when step has no spot
    description: LocalizedText
    bon_vivant_notes: LocalizedText
    distance_from_prev_km: float | None = None
    travel_mode: TravelMode | None = None
    time_on_site_min: int
    time_on_site_max: int


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


class CityListItem(BaseModel):
    id: UUID
    slug: str
    name: str
    country_code: str
    tagline: LocalizedText
    status: CityStatus
    is_unlocked: bool


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
    port_lat: float
    port_lng: float
    highlights: list[Highlight]
    transport_options: list[TransportOption]
    what_to_know: list[Note]
    status: CityStatus
    last_verified: datetime.date | None = None
    spots: list[Spot]
    itineraries: list[Itinerary]
    tips: list[Tip]
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
