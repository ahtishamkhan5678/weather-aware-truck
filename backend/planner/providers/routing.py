"""Routing composition: provider fallback + a guaranteed number of distinct alternatives."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

from ..domain.entities import LatLon, Route, TruckProfile
from ..domain.geo import (
    destination_point,
    haversine_m,
    initial_bearing_deg,
    point_polyline_distance_m,
    simplify,
)
from .base import NoRouteFound, ProviderError, RoutingProvider

log = logging.getLogger(__name__)


class AlternativeRouteService:
    """Returns exactly ``count`` *distinct* routes whenever the road network allows it.

    Engines often return fewer alternatives than requested (OSRM's public server commonly
    returns one). Missing options are synthesised by forcing the route through a via point
    offset perpendicular to the trip at its midpoint (left/right, then wider). Candidates
    that overlap an existing option by more than ``max_overlap`` are discarded.
    """

    def __init__(
        self,
        providers: Sequence[RoutingProvider],
        *,
        count: int = 3,
        max_overlap: float = 0.85,
        offsets: Sequence[float] = (0.12, -0.12, 0.25, -0.25),
        overlap_buffer_m: float = 1500.0,
    ) -> None:
        if not providers:
            raise ValueError("At least one routing provider is required")
        self._providers = list(providers)
        self._count = count
        self._max_overlap = max_overlap
        self._offsets = offsets
        self._buffer = overlap_buffer_m

    def find(self, origin: LatLon, destination: LatLon, truck: TruckProfile) -> list[Route]:
        """Fallback chain: the first provider that can route the trip produces *all* options,
        so durations are always comparable (never a Valhalla truck time vs an OSRM car time).
        """
        last: ProviderError | None = None
        for provider in self._providers:
            try:
                return self._find_with(provider, origin, destination, truck)
            except ProviderError as exc:
                log.info("routing provider %s failed: %s", provider.name, exc)
                last = exc
        if isinstance(last, NoRouteFound):
            raise last
        raise last or NoRouteFound("No route found", provider="routing")

    def _find_with(
        self, provider: RoutingProvider, origin: LatLon, destination: LatLon, truck: TruckProfile
    ) -> list[Route]:
        routes = provider.routes(origin, destination, truck, alternatives=self._count - 1)
        if not routes:
            raise NoRouteFound("No route found", provider=provider.name)
        distinct: list[Route] = []
        for r in routes:
            self._add_if_distinct(distinct, r)
        if len(distinct) >= self._count:
            return distinct[: self._count]

        vias = self._via_points(origin, destination)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self._safe_route, provider, origin, destination, truck, v) for v in vias
            ]
            for f in futures:
                route = f.result()
                if route is not None:
                    self._add_if_distinct(distinct, route)
                if len(distinct) >= self._count:
                    break
        # Keep the engine's primary route first, then the shortest-duration alternatives.
        head, tail = distinct[:1], sorted(distinct[1:], key=lambda r: r.duration_s)
        return (head + tail)[: self._count]

    def _safe_route(self, provider, origin, destination, truck, via) -> Route | None:
        try:
            found = provider.routes(origin, destination, truck, alternatives=0, via=[via])
            return found[0] if found else None
        except ProviderError as exc:
            log.info("via-point alternative failed: %s", exc)
            return None

    def _via_points(self, origin: LatLon, destination: LatLon) -> list[LatLon]:
        dist = haversine_m(origin, destination)
        bearing = initial_bearing_deg(origin, destination)
        mid = destination_point(origin, bearing, dist / 2)
        out = []
        for frac in self._offsets:
            side = 90 if frac > 0 else -90
            out.append(destination_point(mid, bearing + side, abs(frac) * dist))
        return out

    def _add_if_distinct(self, accepted: list[Route], candidate: Route) -> None:
        sample = simplify(candidate.points, 500.0)[::2] or list(candidate.points)
        for existing in accepted:
            line = simplify(existing.points, 500.0)
            shared = sum(1 for p in sample if point_polyline_distance_m(p, line) < self._buffer)
            if shared / len(sample) > self._max_overlap:
                return
        # Reject absurd detours (> 60 % longer than the best route).
        if accepted and candidate.distance_m > accepted[0].distance_m * 1.6:
            return
        accepted.append(candidate)
