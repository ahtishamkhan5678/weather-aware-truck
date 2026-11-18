from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from planner.domain.entities import LatLon, Route
from planner.domain.geo import METERS_PER_MILE, destination_point
from planner.domain.weather import ForecastSeries

T0 = datetime(2026, 11, 20, 12, tzinfo=UTC)
DEFAULT_START = LatLon(35.0, -100.0)


def straight_route(
    miles: float,
    mph: float = 60.0,
    n: int = 50,
    provider: str = "fake",
    start: LatLon = DEFAULT_START,
    bearing: float = 90.0,
) -> Route:
    """A straight eastbound route with evenly spaced vertices at constant speed."""
    seg_m = miles * METERS_PER_MILE / n
    pts = [start]
    for _ in range(n):
        pts.append(destination_point(pts[-1], bearing, seg_m))
    dur = seg_m / (mph * METERS_PER_MILE / 3600)
    return Route(tuple(pts), (seg_m,) * n, (dur,) * n, ("I 40",), provider)


def flat_series(
    point: LatLon, start: datetime, hours: int, *, wind=5.0, rain=0.0, snow=0.0, wind_fn=None
) -> ForecastSeries:
    winds = tuple(wind_fn(start + timedelta(hours=h)) if wind_fn else wind for h in range(hours))
    return ForecastSeries(point, start, winds, winds, (rain,) * hours, (snow,) * hours)


class FakeWeather:
    """Weather provider whose wind is a function of (point, time)."""

    def __init__(self, wind_fn=lambda p, t: 5.0, rain=0.0, snow=0.0):
        self.wind_fn = wind_fn
        self.rain = rain
        self.snow = snow
        self.calls = 0

    def hourly(self, points, start, end):
        self.calls += 1
        hours = int((end - start).total_seconds() // 3600) + 1
        return [
            flat_series(
                p,
                start,
                hours,
                rain=self.rain,
                snow=self.snow,
                wind_fn=lambda t, p=p: self.wind_fn(p, t),
            )
            for p in points
        ]


class FakeFinder:
    def __init__(self, routes):
        self.routes = routes

    def find(self, origin, destination, truck):
        return list(self.routes)


@pytest.fixture
def t0():
    return T0
