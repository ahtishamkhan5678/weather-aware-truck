"""Checkpoint placement along a route.

Checkpoints are placed at the origin, then every ``interval`` miles of *driven* distance,
and at the destination. Each checkpoint "represents" the stretch of road that is closer to
it than to its neighbours (half-way to the previous and next checkpoint), so the
represented miles of all checkpoints add up exactly to the route length. These are the
miles that feed the Severe / High mile totals used to rank routes.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

from .entities import LatLon, Route
from .geo import METERS_PER_MILE, cumulative_distances, lerp_point

ALLOWED_INTERVALS_MI = (10, 25, 50)


@dataclass(frozen=True, slots=True)
class SamplePosition:
    distance_m: float
    point: LatLon
    represented_m: float


class RouteSampler:
    def __init__(self, interval_mi: float) -> None:
        if interval_mi <= 0:
            raise ValueError("interval must be positive")
        self.interval_m = interval_mi * METERS_PER_MILE

    def positions(self, route: Route) -> list[SamplePosition]:
        # Use the provider's segment lengths so distances agree with the route summary.
        cum = [0.0]
        for d in route.segment_distances_m:
            cum.append(cum[-1] + d)
        total = cum[-1]
        if total <= 0:  # degenerate: fall back to geometry
            cum = cumulative_distances(route.points)
            total = cum[-1]

        marks: list[float] = []
        d = 0.0
        while d < total - 1e-6:
            marks.append(d)
            d += self.interval_m
        # Always finish at the destination; merge a tiny final stub into it.
        if marks and total - marks[-1] < self.interval_m * 0.05 and len(marks) > 1:
            marks[-1] = total
        else:
            marks.append(total)

        out: list[SamplePosition] = []
        for i, mark in enumerate(marks):
            lo = 0.0 if i == 0 else (marks[i - 1] + mark) / 2
            hi = total if i == len(marks) - 1 else (mark + marks[i + 1]) / 2
            out.append(SamplePosition(mark, point_at(route.points, cum, mark), hi - lo))
        return out


def point_at(points: tuple[LatLon, ...], cum: list[float], distance_m: float) -> LatLon:
    if distance_m <= 0:
        return points[0]
    if distance_m >= cum[-1]:
        return points[-1]
    i = bisect.bisect_right(cum, distance_m) - 1
    seg = cum[i + 1] - cum[i]
    t = 0.0 if seg <= 0 else (distance_m - cum[i]) / seg
    return lerp_point(points[i], points[i + 1], t)
