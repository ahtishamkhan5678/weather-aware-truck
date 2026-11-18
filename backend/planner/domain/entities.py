"""Immutable domain entities shared by every layer."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum


@dataclass(frozen=True, slots=True)
class LatLon:
    lat: float
    lon: float

    def rounded(self, step_deg: float) -> LatLon:
        """Snap to a grid — used to de-duplicate weather lookups for nearby points."""
        return LatLon(round(self.lat / step_deg) * step_deg, round(self.lon / step_deg) * step_deg)

    def as_list(self) -> list[float]:
        """[lon, lat] — GeoJSON order."""
        return [round(self.lon, 6), round(self.lat, 6)]


@dataclass(frozen=True, slots=True)
class Place:
    label: str
    point: LatLon


class RiskLevel(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()

    @property
    def key(self) -> str:
        return self.name.lower()


@dataclass(frozen=True, slots=True)
class TruckProfile:
    """What the routing engine needs to know about the vehicle."""

    load_weight_lb: float
    tare_weight_lb: float

    @property
    def gross_weight_lb(self) -> float:
        return self.load_weight_lb + self.tare_weight_lb


@dataclass(frozen=True, slots=True)
class Route:
    """A provider-agnostic route: a polyline plus per-segment distance and duration.

    ``segment_distances_m[i]`` / ``segment_durations_s[i]`` describe the segment
    ``points[i] -> points[i + 1]`` so both lists have ``len(points) - 1`` items.
    """

    points: tuple[LatLon, ...]
    segment_distances_m: tuple[float, ...]
    segment_durations_s: tuple[float, ...]
    roads: tuple[str, ...] = ()
    provider: str = "unknown"

    def __post_init__(self) -> None:
        n = len(self.points) - 1
        if n < 1:
            raise ValueError("A route needs at least two points")
        if len(self.segment_distances_m) != n or len(self.segment_durations_s) != n:
            raise ValueError("Segment arrays must have len(points) - 1 entries")

    @property
    def distance_m(self) -> float:
        return math.fsum(self.segment_distances_m)

    @property
    def duration_s(self) -> float:
        return math.fsum(self.segment_durations_s)


@dataclass(frozen=True, slots=True)
class WeatherSample:
    """Weather at a point/time. Rates are per hour."""

    wind_mph: float
    gust_mph: float
    rain_in_hr: float
    snow_in_hr: float
    forecast_time: datetime | None = None


@dataclass(frozen=True, slots=True)
class HazardAssessment:
    """Classification of one hazard (wind / rain / snow)."""

    hazard: str
    value: float
    level: RiskLevel
    note: str | None = None


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    level: RiskLevel
    hazards: tuple[HazardAssessment, ...]

    @property
    def drivers(self) -> tuple[HazardAssessment, ...]:
        """Hazards responsible for the overall level (empty when Low)."""
        if self.level == RiskLevel.LOW:
            return ()
        return tuple(h for h in self.hazards if h.level == self.level)


@dataclass(frozen=True, slots=True)
class Checkpoint:
    index: int
    point: LatLon
    distance_m: float
    eta: datetime
    represented_m: float
    weather: WeatherSample
    risk: RiskAssessment


@dataclass(frozen=True, slots=True)
class RestStop:
    kind: str  # "break" (30 min) or "rest" (10 h)
    after_driving_s: float
    duration_s: float


@dataclass(frozen=True, slots=True)
class RouteAnalysis:
    route_id: str
    route: Route
    departure: datetime
    arrival: datetime
    driving_s: float
    checkpoints: tuple[Checkpoint, ...]
    rest_stops: tuple[RestStop, ...]
    miles_by_level: dict[RiskLevel, float] = field(default_factory=dict)

    @property
    def distance_mi(self) -> float:
        from .geo import METERS_PER_MILE

        return self.route.distance_m / METERS_PER_MILE

    @property
    def trip_s(self) -> float:
        return (self.arrival - self.departure).total_seconds()

    def miles_at(self, level: RiskLevel) -> float:
        return self.miles_by_level.get(level, 0.0)

    @property
    def average_risk(self) -> float:
        """Distance-weighted mean risk score on the 0 (Low) … 4 (No Travel) scale."""
        total = sum(self.miles_by_level.values())
        if total <= 0:
            return 0.0
        return sum(int(level) * miles for level, miles in self.miles_by_level.items()) / total

    @property
    def max_level(self) -> RiskLevel:
        return max((c.risk.level for c in self.checkpoints), default=RiskLevel.LOW)
