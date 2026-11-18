"""Ports (interfaces) the application layer depends on — implementations live beside this."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from ..domain.entities import LatLon, Place, Route, TruckProfile
from ..domain.weather import ForecastSeries


class ProviderError(Exception):
    """An upstream service failed or returned something unusable."""

    def __init__(self, message: str, *, provider: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class NoRouteFound(ProviderError):
    def __init__(self, message: str, *, provider: str) -> None:
        super().__init__(message, provider=provider, retryable=False)


@runtime_checkable
class RoutingProvider(Protocol):
    name: str

    def routes(
        self,
        origin: LatLon,
        destination: LatLon,
        truck: TruckProfile,
        *,
        alternatives: int,
        via: Sequence[LatLon] = (),
    ) -> list[Route]:
        """Up to ``alternatives + 1`` routes (best first). ``via`` forces intermediate points."""
        ...


@runtime_checkable
class GeocodingProvider(Protocol):
    def search(self, query: str, *, limit: int = 5, bias: LatLon | None = None) -> list[Place]: ...

    def reverse(self, point: LatLon) -> Place | None: ...


@runtime_checkable
class WeatherProvider(Protocol):
    def hourly(
        self, points: Sequence[LatLon], start: datetime, end: datetime
    ) -> list[ForecastSeries]:
        """Hourly series for each point (same order) covering [start, end] UTC whole hours."""
        ...
