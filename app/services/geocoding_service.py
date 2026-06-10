from __future__ import annotations

from typing import Protocol

import httpx

from app.config import settings

_MAPBOX_BASE = "https://api.mapbox.com/geocoding/v5/mapbox.places"
_TIMEOUT = 5.0  # seconds — keep short; geocoding is best-effort


class Geocoder(Protocol):
    async def geocode(self, address: str) -> tuple[float, float] | None:
        """Return (lat, lng) for address, or None if not found / unreachable."""
        ...


class MapboxGeocoder:
    """Forward geocoder backed by the Mapbox Geocoding API v5."""

    def __init__(self, token: str) -> None:
        self._token = token

    async def geocode(self, address: str) -> tuple[float, float] | None:
        url = f"{_MAPBOX_BASE}/{httpx.URL(address)}.json"
        params = {"access_token": self._token, "limit": 1}
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
            features = data.get("features", [])
            if not features:
                return None
            # GeoJSON order is [longitude, latitude]
            lng, lat = features[0]["geometry"]["coordinates"]
            return float(lat), float(lng)
        except httpx.HTTPStatusError:
            return None
        except httpx.RequestError:
            return None
        except (KeyError, IndexError, ValueError):
            return None


class NullGeocoder:
    """Always returns None — used in dev/test when no Mapbox token is configured."""

    async def geocode(self, address: str) -> tuple[float, float] | None:  # noqa: ARG002
        return None


def get_geocoder() -> Geocoder:
    """Return the appropriate geocoder based on environment configuration."""
    if settings.mapbox_token:
        return MapboxGeocoder(settings.mapbox_token)
    return NullGeocoder()
