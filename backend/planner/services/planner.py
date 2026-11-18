"""Use case: plan a weather-aware truck trip.

Pipeline
    routes (3 options) → checkpoints every N miles → truck ETA at each checkpoint
    → hourly forecast at (checkpoint, ETA) → risk per checkpoint (load-aware)
    → miles per risk level per route → recommendation

The service depends only on *interfaces* (route finder, weather provider) which are
injected by ``container.py`` — tests swap in fakes, production wires real adapters.
"""

from __future__ import annotations

import logging
import string
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from ..domain.entities import (
    Checkpoint,
    LatLon,
    Place,
    RiskLevel,
    Route,
    RouteAnalysis,
    TruckProfile,
)
from ..domain.eta import TruckEtaModel, ceil_hour, floor_hour
from ..domain.geo import METERS_PER_MILE
from ..domain.ranking import Ranking, RouteRanker
from ..domain.risk import RiskClassifier
from ..domain.sampling import RouteSampler
from ..domain.weather import ForecastSeries
from ..providers.base import WeatherProvider

log = logging.getLogger(__name__)

# Weather lookups snap checkpoints to a lattice to de-duplicate nearby points. The finest
# step that keeps a plan within the weather budget is used: ~5 km for regional trips,
# up to ~25 km (≈ global-model resolution) for cross-country trips at 10-mile sampling.
WEATHER_SNAP_STEPS = (0.05, 0.1, 0.15, 0.2, 0.25)
MAX_WEATHER_POINTS = 260
FORECAST_HORIZON = timedelta(days=15)


class RouteFinder(Protocol):
    def find(self, origin: LatLon, destination: LatLon, truck: TruckProfile) -> list[Route]: ...


class PlanningError(Exception):
    """Request is valid but cannot be planned (e.g. outside forecast horizon)."""


@dataclass(frozen=True, slots=True)
class PlanRequest:
    origin: Place
    destination: Place
    departure: datetime
    load_weight_lb: float
    interval_mi: int


@dataclass(frozen=True, slots=True)
class PlanResult:
    request: PlanRequest
    analyses: tuple[RouteAnalysis, ...]  # in route-id order (A, B, C)
    ranking: Ranking
    generated_at: datetime
    warnings: tuple[str, ...] = field(default=())


class TripPlanner:
    def __init__(
        self,
        route_finder: RouteFinder,
        weather: WeatherProvider,
        classifier: RiskClassifier,
        eta_model: TruckEtaModel,
        ranker: RouteRanker,
        tare_weight_lb: float,
        clock=lambda: datetime.now(UTC),
    ) -> None:
        self._routes = route_finder
        self._weather = weather
        self._classifier = classifier
        self._eta = eta_model
        self._ranker = ranker
        self._tare = tare_weight_lb
        self._clock = clock

    def plan(self, req: PlanRequest) -> PlanResult:
        truck = TruckProfile(req.load_weight_lb, self._tare)
        routes = self._routes.find(req.origin.point, req.destination.point, truck)
        sampler = RouteSampler(req.interval_mi)

        # 1) Where and when the truck will be at every checkpoint.
        timelines = [self._timeline(route, sampler, req.departure) for route in routes]

        # 2) One batched weather request for all checkpoints of all routes.
        all_etas = [eta for tl in timelines for (_, eta, _) in tl.stops]
        start, end = floor_hour(min(all_etas)), ceil_hour(max(all_etas)) + timedelta(hours=1)
        now = self._clock()
        if end > now + FORECAST_HORIZON:
            raise PlanningError(
                "This trip ends beyond the 15-day forecast horizon — choose an earlier departure."
            )
        snap = choose_snap([p.point for tl in timelines for (p, _, _) in tl.stops])
        snapped = sorted(
            {p.point.rounded(snap) for tl in timelines for (p, _, _) in tl.stops},
            key=lambda q: (q.lat, q.lon),
        )
        series = dict(zip(snapped, self._weather.hourly(snapped, start, end), strict=True))

        # 3) Assess, aggregate, rank.
        analyses = [
            self._analyse(route_id, tl, series, req, snap)
            for route_id, tl in zip(string.ascii_uppercase, timelines, strict=False)
        ]
        ranking = self._ranker.rank(analyses)
        warnings = []
        if len(analyses) < 3:
            warnings.append(
                f"Only {len(analyses)} distinct route(s) exist for this trip on the road network."
            )
        if ranking.all_routes_blocked:
            warnings.append(
                "Every route crosses No-Travel conditions. Consider delaying departure."
            )
        return PlanResult(req, tuple(analyses), ranking, now, tuple(warnings))

    # ------------------------------------------------------------------ helpers

    @dataclass(frozen=True, slots=True)
    class _Timeline:
        route: Route
        stops: list  # (SamplePosition, eta, driving_s)
        driving_s: float
        arrival: datetime

    def _timeline(self, route: Route, sampler: RouteSampler, departure: datetime) -> _Timeline:
        cum_d, cum_t = self._eta.driving_profile(route)
        stops = []
        for pos in sampler.positions(route):
            driving = self._eta.driving_at(cum_d, cum_t, pos.distance_m)
            stops.append((pos, self._eta.eta(departure, driving), driving))
        total_driving = cum_t[-1]
        return self._Timeline(route, stops, total_driving, self._eta.eta(departure, total_driving))

    def _analyse(
        self,
        route_id: str,
        tl: _Timeline,
        series: dict[LatLon, ForecastSeries],
        req: PlanRequest,
        snap: float,
    ) -> RouteAnalysis:
        checkpoints: list[Checkpoint] = []
        miles: dict[RiskLevel, float] = defaultdict(float)
        for i, (pos, eta, _) in enumerate(tl.stops):
            weather = series[pos.point.rounded(snap)].at(eta)
            risk = self._classifier.assess(weather, req.load_weight_lb)
            checkpoints.append(
                Checkpoint(i, pos.point, pos.distance_m, eta, pos.represented_m, weather, risk)
            )
            miles[risk.level] += pos.represented_m / METERS_PER_MILE
        return RouteAnalysis(
            route_id=route_id,
            route=tl.route,
            departure=req.departure,
            arrival=tl.arrival,
            driving_s=tl.driving_s,
            checkpoints=tuple(checkpoints),
            rest_stops=tuple(self._eta.rest_stops(tl.driving_s)),
            miles_by_level={lvl: miles.get(lvl, 0.0) for lvl in RiskLevel},
        )


def choose_snap(points: Sequence[LatLon]) -> float:
    """Finest lattice step whose de-duplicated point count fits the weather budget."""
    for step in WEATHER_SNAP_STEPS:
        if len({p.rounded(step) for p in points}) <= MAX_WEATHER_POINTS:
            return step
    return WEATHER_SNAP_STEPS[-1]


def route_lines(analyses: Sequence[RouteAnalysis]) -> list[list[LatLon]]:
    return [list(a.route.points) for a in analyses]
