"""Caching decorators for providers (decorator pattern — same interface, added behaviour)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime

from django.core.cache import BaseCache

from ..domain.entities import LatLon, Route, TruckProfile
from ..domain.weather import ForecastSeries
from .base import WeatherProvider


class CachedWeatherProvider:
    """Caches each point's series individually so overlapping trips share lookups."""

    def __init__(self, inner: WeatherProvider, cache: BaseCache, ttl_s: int) -> None:
        self._inner = inner
        self._cache = cache
        self._ttl = ttl_s

    @staticmethod
    def _key(p: LatLon, start: datetime, end: datetime) -> str:
        return f"wx:{p.lat:.4f}:{p.lon:.4f}:{start:%Y%m%d%H}:{end:%Y%m%d%H}"

    def hourly(
        self, points: Sequence[LatLon], start: datetime, end: datetime
    ) -> list[ForecastSeries]:
        keys = [self._key(p, start, end) for p in points]
        cached = self._cache.get_many(keys)
        missing = [p for p, k in zip(points, keys, strict=True) if k not in cached]
        if missing:
            fresh = self._inner.hourly(missing, start, end)
            new = {self._key(s.point, start, end): s for s in fresh}
            self._cache.set_many(new, self._ttl)
            cached.update(new)
        return [cached[k] for k in keys]


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
