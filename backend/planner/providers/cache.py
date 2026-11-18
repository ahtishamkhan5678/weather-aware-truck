"""Caching decorators for providers (decorator pattern — same interface, added behaviour)."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Sequence
from datetime import datetime, timedelta

from django.core.cache import BaseCache

from ..domain.entities import LatLon, Route, TruckProfile
from ..domain.weather import ForecastSeries
from .base import WeatherProvider

DAY = timedelta(days=1)
log = logging.getLogger(__name__)


class FailSafeCache:
    """Wraps a Django cache so an unreachable cache server degrades to "always miss".

    Caching is an optimisation: if Redis is down, plans still work (just uncached).
    """

    def __init__(self, inner: BaseCache) -> None:
        self._inner = inner

    def _safe(self, op: str, default, *args, **kwargs):
        try:
            return getattr(self._inner, op)(*args, **kwargs)
        except Exception as exc:
            log.warning("cache %s failed, continuing without cache: %s", op, exc)
            return default

    def get(self, key, default=None):
        return self._safe("get", default, key, default)

    def get_many(self, keys):
        return self._safe("get_many", {}, keys)

    def set(self, key, value, timeout=None):
        self._safe("set", None, key, value, timeout)

    def set_many(self, data, timeout=None):
        self._safe("set_many", [], data, timeout)


def _day_floor(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


class CachedWeatherProvider:
    """Caches forecasts per (point, UTC day).

    Day-sized chunks make the cache reusable across *different* requests: the heatmap
    (now…+48 h), a trip plan (departure…arrival) and a repeat search with another
    departure time all hit the same entries. Only points missing a day are fetched,
    in one batched call covering the whole span of days needed.
    """

    def __init__(self, inner: WeatherProvider, cache: BaseCache, ttl_s: int) -> None:
        self._inner = inner
        self._cache = cache
        self._ttl = ttl_s

    @staticmethod
    def _key(p: LatLon, day: datetime) -> str:
        return f"wx2:{p.lat:.4f}:{p.lon:.4f}:{day:%Y%m%d}"

    def hourly(
        self, points: Sequence[LatLon], start: datetime, end: datetime
    ) -> list[ForecastSeries]:
        if not points:
            return []
        days = []
        d = _day_floor(start)
        while d <= end:
            days.append(d)
            d += DAY
        keys = {(p, day): self._key(p, day) for p in points for day in days}
        cached = self._cache.get_many(list(keys.values()))
        missing = [
            p for p in dict.fromkeys(points) if any(keys[(p, day)] not in cached for day in days)
        ]
        if missing:
            span_end = days[-1] + timedelta(hours=23)
            fresh = self._inner.hourly(missing, days[0], span_end)
            new: dict[str, ForecastSeries] = {}
            for p, series in zip(missing, fresh, strict=True):
                for day in days:
                    new[self._key(p, day)] = series.window(day, day + timedelta(hours=23))
            self._cache.set_many(new, self._ttl)
            cached.update(new)
        return [
            ForecastSeries.concat([cached[keys[(p, day)]] for day in days]).window(start, end)
            for p in points
        ]


class CachedRouteFinder:
    """Caches the (expensive, multi-request) alternative-route search per trip and weight."""

    def __init__(self, inner, cache: BaseCache, ttl_s: int) -> None:
        self._inner = inner
        self._cache = cache
        self._ttl = ttl_s

    def find(self, origin: LatLon, destination: LatLon, truck: TruckProfile) -> list[Route]:
        raw = json.dumps(
            [
                round(origin.lat, 4),
                round(origin.lon, 4),
                round(destination.lat, 4),
                round(destination.lon, 4),
                round(truck.gross_weight_lb, -3),
            ]
        )
        key = "routes:" + hashlib.sha1(raw.encode()).hexdigest()
        routes = self._cache.get(key)
        if routes is None:
            routes = self._inner.find(origin, destination, truck)
            self._cache.set(key, routes, self._ttl)
        return routes
