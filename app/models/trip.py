from __future__ import annotations

from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base model matching the mobile contract: camelCase on the wire,
    snake_case in Python. FastAPI serializes responses by_alias by default."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TripDayResponse(CamelModel):
    id: UUID
    day_number: int
    date: date
    city_slug: str | None
    time_arrival: time | None
    time_departure: time | None
    departure_next_day: bool
    has_guide: bool  # derived: city_slug is not None


class TripResponse(CamelModel):
    id: UUID
    title: str
    cruise_line: str
    ship_name: str
    start_date: date
    end_date: date
    total_days: int  # derived: (end_date - start_date).days + 1
    total_ports: int  # derived: count of days where city_slug is not None
    days: list[TripDayResponse]


class TripsListResponse(CamelModel):
    trips: list[TripResponse]


class TripDayInput(CamelModel):
    day_number: int
    date: date
    city_slug: str | None = None
    time_arrival: time | None = None
    time_departure: time | None = None
    departure_next_day: bool = False


class CreateTripInput(CamelModel):
    title: str
    cruise_line: str
    ship_name: str
    start_date: date
    end_date: date
    days: list[TripDayInput]
