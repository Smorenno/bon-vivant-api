from __future__ import annotations

import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.city import (
    SpotCategory,
    TimeOfDay,
    TransportMethod,
    TravelMode,
)

# ============================================================
# LocalizedText for import (es required; en/fr optional)
# ============================================================


class LocalizedTextIn(BaseModel):
    es: str
    en: str | None = None
    fr: str | None = None

    @field_validator("es")
    @classmethod
    def es_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("'es' must not be empty or whitespace")
        return v

    def to_jsonb(self) -> dict:
        return self.model_dump(exclude_none=True)


# ============================================================
# City jsonb sub-objects
# ============================================================


class HighlightIn(BaseModel):
    label: LocalizedTextIn
    description: LocalizedTextIn

    def to_jsonb(self) -> dict:
        return {
            "label": self.label.to_jsonb(),
            "description": self.description.to_jsonb(),
        }


class TransportOptionIn(BaseModel):
    method: TransportMethod
    time_label: str
    tips: LocalizedTextIn

    def to_jsonb(self) -> dict:
        return {
            "method": self.method.value,
            "time_label": self.time_label,
            "tips": self.tips.to_jsonb(),
        }


class NoteIn(BaseModel):
    heading: LocalizedTextIn
    text: LocalizedTextIn

    def to_jsonb(self) -> dict:
        return {
            "heading": self.heading.to_jsonb(),
            "text": self.text.to_jsonb(),
        }


# ============================================================
# Spots
# ============================================================


class AttractionIn(BaseModel):
    name: str
    address: str
    latitude: float | None = None
    longitude: float | None = None
    distance_from_port_km: float | None = None
    rank_order: int
    website: str | None = None
    manuel_quote: LocalizedTextIn
    reservation: LocalizedTextIn | None = None
    what_it_is: LocalizedTextIn | None = None
    why_it_matters: LocalizedTextIn | None = None
    good_to_know: LocalizedTextIn | None = None


class GourmetIn(BaseModel):
    name: str
    address: str
    latitude: float | None = None
    longitude: float | None = None
    category: SpotCategory  # required for food spots
    distance_from_port_km: float | None = None
    rank_order: int
    website: str | None = None
    manuel_quote: LocalizedTextIn
    reservation: LocalizedTextIn | None = None
    cuisine_type: LocalizedTextIn | None = None
    category_label: LocalizedTextIn | None = None
    must_try: LocalizedTextIn | None = None
    best_time: LocalizedTextIn | None = None


# ============================================================
# Tips
# ============================================================


class TipIn(BaseModel):
    title: LocalizedTextIn
    body: LocalizedTextIn
    rank_order: int


# ============================================================
# Itinerary steps and itineraries
# ============================================================


class ItineraryStepIn(BaseModel):
    rank_order: int
    spot_ref: str | None = None  # Exact name of an attraction or gourmet in this guide
    title: LocalizedTextIn | None = None  # Only when no spot_ref
    address: str | None = None
    description: LocalizedTextIn
    bon_vivant_notes: LocalizedTextIn
    must_try: LocalizedTextIn | None = None
    reservation: LocalizedTextIn | None = None
    website: str | None = None
    distance_from_prev_km: float | None = None
    travel_mode: TravelMode | None = None
    time_on_site_min: int
    time_on_site_max: int


class ItineraryIn(BaseModel):
    theme: str
    time_of_day: TimeOfDay
    title: LocalizedTextIn
    catchy_phrase: LocalizedTextIn
    best_for: LocalizedTextIn
    duration_min_hrs: float
    duration_max_hrs: float
    total_walk_km: float
    total_transit_km: float | None = None
    flex_note: LocalizedTextIn
    is_recommended: bool = False
    is_premium: bool = False
    rank_order: int
    steps: list[ItineraryStepIn]

    @field_validator("steps")
    @classmethod
    def at_least_one_step(cls, v: list[ItineraryStepIn]) -> list[ItineraryStepIn]:
        if not v:
            raise ValueError("each itinerary must have at least one step")
        return v


# ============================================================
# Top-level import sections
# ============================================================


class MetaIn(BaseModel):
    slug: str
    name: str
    country_code: str
    tagline: LocalizedTextIn
    last_verified: str | None = None  # YYYY-MM format
    port_lat: float | None = None
    port_lng: float | None = None
    status: str = "draft"  # Always forced to draft regardless of input

    @field_validator("slug")
    @classmethod
    def slug_kebab_case(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", v):
            raise ValueError(
                "slug must be kebab-case (lowercase alphanumeric with hyphens)"
            )
        return v

    @field_validator("country_code")
    @classmethod
    def country_code_two_uppers(cls, v: str) -> str:
        if not re.match(r"^[A-Z]{2}$", v):
            raise ValueError("country_code must be exactly two uppercase letters")
        return v

    @field_validator("status", mode="before")
    @classmethod
    def force_draft(cls, _: object) -> str:
        return "draft"


class OverviewIn(BaseModel):
    intro: LocalizedTextIn
    historical_context: LocalizedTextIn
    highlights: list[HighlightIn] = []


class PortIn(BaseModel):
    port_description: LocalizedTextIn
    distance_to_center: LocalizedTextIn
    port_facilities: LocalizedTextIn
    port_recommendation: LocalizedTextIn
    transport_options: list[TransportOptionIn] = []


class ReviewIn(BaseModel):
    last_verified: str | None = None
    unverified: list[str] = []


# ============================================================
# Root import document
# ============================================================


class CityGuideImport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    meta: MetaIn
    overview: OverviewIn
    port: PortIn
    attractions: list[AttractionIn] = []
    gourmet: list[GourmetIn] = []
    what_to_know: list[NoteIn] = []
    tips: list[TipIn] = []
    itineraries: list[ItineraryIn]
    review: ReviewIn | None = Field(None, alias="_review")

    @field_validator("itineraries")
    @classmethod
    def at_least_one_itinerary(cls, v: list[ItineraryIn]) -> list[ItineraryIn]:
        if not v:
            raise ValueError("at least one itinerary is required")
        return v


# ============================================================
# Import result (returned by the service and import endpoint)
# ============================================================


class ImportCounts(BaseModel):
    attractions: int
    gourmet: int
    itineraries: int
    steps: int
    tips: int


class ImportResult(BaseModel):
    city_id: str
    slug: str
    status: str
    replaced: bool
    counts: ImportCounts
    geocoded: list[str]
    geocode_failed: list[str]
    review_notes: list[str]


# ============================================================
# Patch schemas for admin edits (all fields optional)
# ============================================================


class CityUpdate(BaseModel):
    tagline: LocalizedTextIn | None = None
    intro: LocalizedTextIn | None = None
    historical_context: LocalizedTextIn | None = None
    highlights: list[HighlightIn] | None = None
    port_description: LocalizedTextIn | None = None
    distance_to_center: LocalizedTextIn | None = None
    port_facilities: LocalizedTextIn | None = None
    port_recommendation: LocalizedTextIn | None = None
    transport_options: list[TransportOptionIn] | None = None
    what_to_know: list[NoteIn] | None = None
    port_lat: float | None = None
    port_lng: float | None = None
    last_verified: str | None = None


class SpotUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    distance_from_port_km: float | None = None
    rank_order: int | None = None
    website: str | None = None
    manuel_quote: LocalizedTextIn | None = None
    reservation: LocalizedTextIn | None = None
    what_it_is: LocalizedTextIn | None = None
    why_it_matters: LocalizedTextIn | None = None
    good_to_know: LocalizedTextIn | None = None
    cuisine_type: LocalizedTextIn | None = None
    category_label: LocalizedTextIn | None = None
    must_try: LocalizedTextIn | None = None
    best_time: LocalizedTextIn | None = None


# ============================================================
# City/spot detail responses for admin endpoints
# ============================================================


class CityAdminDetail(BaseModel):
    id: UUID
    slug: str
    name: str
    country_code: str
    status: str
    tagline: dict
    intro: dict
    historical_context: dict
    highlights: list
    port_description: dict
    distance_to_center: dict
    port_facilities: dict
    port_recommendation: dict
    transport_options: list
    what_to_know: list
    port_lat: float | None = None
    port_lng: float | None = None
    last_verified: str | None = None


class SpotAdminDetail(BaseModel):
    id: UUID
    city_id: UUID
    kind: str
    category: str | None = None
    name: str
    address: str
    latitude: float | None = None
    longitude: float | None = None
    distance_from_port_km: float | None = None
    rank_order: int
    website: str | None = None
    manuel_quote: dict
