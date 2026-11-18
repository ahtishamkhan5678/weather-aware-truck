"""Truck ETA model.

Routing engines (especially car profiles) are optimistic for a loaded tractor-trailer, so
two corrections are applied:

1. **Speed cap** — a segment can never be driven faster than ``max_speed_mph``.
2. **Hours of Service (FMCSA, property-carrying)** — a 30-minute break after 8 hours of
   cumulative driving, and a 10-hour off-duty rest after 11 hours of driving. The 14-hour
   duty window and the 70-hour/8-day cycle are not modelled (documented simplification).

The ETA at any checkpoint therefore reflects *when the truck will actually be there*,
which is what the weather lookup needs.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from .entities import RestStop, Route
from .geo import METERS_PER_MILE

HOUR = 3600.0


@dataclass(frozen=True, slots=True)
class HoursOfService:
    max_driving_before_break_s: float = 8 * HOUR
    break_s: float = 0.5 * HOUR
    max_driving_per_shift_s: float = 11 * HOUR
    off_duty_rest_s: float = 10 * HOUR

    def rest_stops(self, driving_s: float) -> list[RestStop]:
        """Stops required to drive ``driving_s`` seconds (none needed *at* a limit exactly)."""
        stops: list[RestStop] = []
        shift_start = 0.0
        while True:
            brk = shift_start + self.max_driving_before_break_s
            if driving_s > brk + 1e-9:
                stops.append(RestStop("break", brk, self.break_s))
            end = shift_start + self.max_driving_per_shift_s
            if driving_s > end + 1e-9:
                stops.append(RestStop("rest", end, self.off_duty_rest_s))
                shift_start = end
            else:
                return stops

    def elapsed_for(self, driving_s: float) -> float:
        """Wall-clock seconds needed to accumulate ``driving_s`` of driving."""
        return driving_s + sum(s.duration_s for s in self.rest_stops(driving_s))


class TruckEtaModel:
    def __init__(self, max_speed_mph: float = 65.0, hos: HoursOfService | None = None) -> None:
        self._max_speed_mps = max_speed_mph * METERS_PER_MILE / HOUR
        self._hos = hos

    def driving_profile(self, route: Route) -> tuple[list[float], list[float]]:
        """(cumulative distance m, cumulative driving s) at each vertex, speed-capped."""
        cum_d, cum_t = [0.0], [0.0]
        for dist, dur in zip(route.segment_distances_m, route.segment_durations_s, strict=True):
            capped = max(dur, dist / self._max_speed_mps) if dist > 0 else max(dur, 0.0)
            cum_d.append(cum_d[-1] + dist)
            cum_t.append(cum_t[-1] + capped)
        return cum_d, cum_t

    @staticmethod
    def driving_at(cum_d: list[float], cum_t: list[float], distance_m: float) -> float:
        if distance_m <= 0:
            return 0.0
        if distance_m >= cum_d[-1]:
            return cum_t[-1]
        i = bisect.bisect_right(cum_d, distance_m) - 1
        seg = cum_d[i + 1] - cum_d[i]
        t = 0.0 if seg <= 0 else (distance_m - cum_d[i]) / seg
        return cum_t[i] + (cum_t[i + 1] - cum_t[i]) * t

    def eta(self, departure: datetime, driving_s: float) -> datetime:
        elapsed = self._hos.elapsed_for(driving_s) if self._hos else driving_s
        return departure + timedelta(seconds=elapsed)

    def rest_stops(self, driving_s: float) -> list[RestStop]:
        return self._hos.rest_stops(driving_s) if self._hos else []


def floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def ceil_hour(dt: datetime) -> datetime:
    f = floor_hour(dt)
    return f if f == dt else f + timedelta(hours=1)


def hours_between(a: datetime, b: datetime) -> int:
    return math.ceil((b - a).total_seconds() / HOUR)
