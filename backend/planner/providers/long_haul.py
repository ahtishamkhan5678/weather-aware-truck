"""Truck routing for trips longer than the truck engine accepts in one request.

The public Valhalla server rejects paths over ~1,500 km. For longer trips:

1. a *skeleton* engine (OSRM) proposes the corridors (main route + alternatives);
2. each skeleton is cut into legs of ``leg_km`` of road distance;
3. every leg is routed by Valhalla's **truck** costing (weight-aware), with headings
   at the joins so the truck continues straight through instead of U-turning;
4. the legs are stitched into one ``Route``.

The result follows the same corridor as the skeleton but with truck-legal roads and truck
travel times end-to-end. If any leg fails, that corridor is dropped (never mixed).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

from ..domain.entities import LatLon, Route, TruckProfile
from ..domain.geo import cumulative_distances, haversine_m, initial_bearing_deg
from ..domain.sampling import point_at
from .base import NoRouteFound, ProviderError, RoutingProvider
from .valhalla import ValhallaRoutingProvider

log = logging.getLogger(__name__)


class ChainedTruckRoutingProvider:
    name = "valhalla"

    def __init__(
        self,
        truck: ValhallaRoutingProvider,
        skeleton: RoutingProvider,
        *,
        leg_km: float = 1050.0,
        max_workers: int = 2,
    ) -> None:
        self._truck = truck
        self._skeleton = skeleton
        self._leg_m = leg_km * 1000
        self._workers = max_workers

    def routes(
        self,
        origin: LatLon,
        destination: LatLon,
        truck: TruckProfile,
        *,
        alternatives: int,
        via: Sequence[LatLon] = (),
    ) -> list[Route]:
        if haversine_m(origin, destination) * 1.25 <= self._truck.max_distance_m:
            return self._truck.routes(
                origin, destination, truck, alternatives=alternatives, via=via
            )
        skeletons = self._skeleton.routes(
            origin, destination, truck, alternatives=alternatives, via=via
        )
        plans = [self._legs(s) for s in skeletons]
        jobs = [(i, a, b, ha, hb) for i, legs in enumerate(plans) for (a, b, ha, hb) in legs]
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            results = list(pool.map(lambda j: self._safe_leg(j, truck), jobs))
        out: list[Route] = []
        for i in range(len(plans)):
            legs = [r for (j, *_), r in zip(jobs, results, strict=True) if j == i]
            if legs and all(leg is not None for leg in legs):
                out.append(stitch(legs))
            else:
                log.info("dropping corridor %s: a truck leg failed", i)
        if not out:
            raise NoRouteFound("No truck route found for this long trip", provider=self.name)
        return out

    def _legs(self, skeleton: Route) -> list[tuple[LatLon, LatLon, float | None, float | None]]:
        """Split points every ``leg_m`` metres along the skeleton, with travel headings."""
        cum = cumulative_distances(skeleton.points)
        total = cum[-1]
        n = max(1, round(total / self._leg_m))
        marks = [total * k / n for k in range(n + 1)]
        pts = [point_at(skeleton.points, cum, m) for m in marks]

        def heading(m: float) -> float:
            a = point_at(skeleton.points, cum, max(0.0, m - 300))
            b = point_at(skeleton.points, cum, min(total, m + 300))
            return initial_bearing_deg(a, b)

        headings = [None, *[heading(m) for m in marks[1:-1]], None]
        return [(pts[k], pts[k + 1], headings[k], headings[k + 1]) for k in range(n)]

    def _safe_leg(self, job, truck: TruckProfile) -> Route | None:
        _, a, b, ha, hb = job
        try:
            return self._truck.leg(a, b, truck, start_heading=ha, end_heading=hb)
        except ProviderError as exc:
            log.info("truck leg failed: %s", exc)
            return None


def stitch(legs: Sequence[Route]) -> Route:
    points: list[LatLon] = []
    distances: list[float] = []
    durations: list[float] = []
    roads: list[str] = []
    for leg in legs:
        pts = list(leg.points)
        if points:
            if points[-1] == pts[0]:
                pts = pts[1:]
            else:  # zero-cost connector between snapped leg ends
                distances.append(haversine_m(points[-1], pts[0]))
                durations.append(0.0)
        points.extend(pts)
        distances.extend(leg.segment_distances_m)
        durations.extend(leg.segment_durations_s)
        roads.extend(r for r in leg.roads if r not in roads)
    return Route(
        tuple(points), tuple(distances), tuple(durations), tuple(roads[:3]), legs[0].provider
    )
