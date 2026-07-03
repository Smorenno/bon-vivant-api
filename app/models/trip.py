from __future__ import annotations

from datetime import date, time
from uuid import UUID

from pydantic import BaseModel


class TripDayResponse(BaseModel):
    id: UUID
    day_number: int
    date: date
    city_slug: str | None
    time_arrival: time | None
    time_departure: time | None
    departure_next_day: bool
    has_guide: bool  # derived: city_slug is not None


class TripResponse(BaseModel):
    id: UUID
    title: str
    cruise_line: str
    ship_name: str
    start_date: date
    end_date: date
    total_days: int  # derived: (end_date - start_date).days + 1
    total_ports: int  # derived: count of days where city_slug is not None
    days: list[TripDayResponse]


class TripsListResponse(BaseModel):
    trips: list[TripResponse]


class TripDayInput(BaseModel):
    day_number: int
    date: date
    city_slug: str | None = None
    time_arrival: time | None = None
    time_departure: time | None = None
    departure_next_day: bool = False


class CreateTripInput(BaseModel):
    title: str
    cruise_line: str
    ship_name: str
    start_date: date
    end_date: date
    days: list[TripDayInput]
