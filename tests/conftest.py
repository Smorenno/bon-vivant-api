"""Shared fixtures for all test modules."""

from __future__ import annotations

import pytest

from app.schemas.import_guide import (
    AttractionIn,
    CityGuideImport,
    ItineraryIn,
    ItineraryStepIn,
    LocalizedTextIn,
    MetaIn,
    OverviewIn,
    PortIn,
    TipIn,
)
from app.services.geocoding_service import NullGeocoder
from tests.fake_supabase import FakeSupabaseClient


@pytest.fixture
def null_geocoder() -> NullGeocoder:
    return NullGeocoder()


@pytest.fixture
def fake_db() -> FakeSupabaseClient:
    return FakeSupabaseClient()


@pytest.fixture
def minimal_guide() -> CityGuideImport:
    """Minimal valid CityGuideImport with one attraction, one itinerary, one tip."""
    return CityGuideImport(
        meta=MetaIn(
            slug="test-city",
            name="Test City",
            country_code="JP",
            tagline=LocalizedTextIn(es="La ciudad de prueba"),
        ),
        overview=OverviewIn(
            intro=LocalizedTextIn(es="Introducción a la ciudad"),
            historical_context=LocalizedTextIn(es="Historia"),
            highlights=[],
        ),
        port=PortIn(
            port_description=LocalizedTextIn(es="Puerto principal"),
            distance_to_center=LocalizedTextIn(es="5 minutos en taxi"),
            port_facilities=LocalizedTextIn(es="Básico"),
            port_recommendation=LocalizedTextIn(es="Tomar taxi"),
            transport_options=[],
        ),
        attractions=[
            AttractionIn(
                name="Templo Central",
                address="1-1 Templo St, Test City",
                rank_order=1,
                manuel_quote=LocalizedTextIn(es="El templo más visitado"),
            )
        ],
        gourmet=[],
        what_to_know=[],
        tips=[
            TipIn(
                title=LocalizedTextIn(es="Consejo útil"),
                body=LocalizedTextIn(es="Lleva efectivo"),
                rank_order=1,
            )
        ],
        itineraries=[
            ItineraryIn(
                theme="4h",
                time_of_day="day",
                title=LocalizedTextIn(es="Mañana esencial"),
                catchy_phrase=LocalizedTextIn(es="Descubre lo más importante"),
                best_for=LocalizedTextIn(es="Primera visita"),
                duration_min_hrs=3.5,
                duration_max_hrs=4.5,
                total_walk_km=2.0,
                flex_note=LocalizedTextIn(es="Puedes acortar"),
                rank_order=1,
                steps=[
                    ItineraryStepIn(
                        rank_order=1,
                        spot_ref="Templo Central",
                        description=LocalizedTextIn(es="El templo principal"),
                        bon_vivant_notes=LocalizedTextIn(es="Llega temprano"),
                        time_on_site_min=30,
                        time_on_site_max=60,
                    )
                ],
            )
        ],
    )
