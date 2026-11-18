"""Rate limiting, circuit breaking, long-haul truck chaining, weather caching, corridor grid."""

import itertools
import time
from datetime import timedelta

import pytest
from django.core.cache.backends.locmem import LocMemCache

from planner.domain.corridor import CorridorGridBuilder
from planner.domain.entities import LatLon, TruckProfile
from planner.domain.geo import haversine_m
from planner.providers.base import ProviderError, RateLimited
from planner.providers.cache import CachedWeatherProvider
from planner.providers.http import CircuitBreaker, HostThrottle
from planner.providers.long_haul import ChainedTruckRoutingProvider, stitch
from planner.services.planner import MAX_WEATHER_POINTS, choose_snap

from .conftest import FakeWeather, straight_route

TRUCK = TruckProfile(30_000, 33_000)


def test_host_throttle_spaces_requests():
    throttle = HostThrottle(0.05)
    t0 = time.monotonic()
    for _ in range(4):
        throttle.wait()
    assert time.monotonic() - t0 >= 0.15  # 3 enforced gaps of 50 ms


def test_circuit_breaker_opens_and_resets():
    breaker = CircuitBreaker(cooldown_s=60)
    assert not breaker.is_open
    breaker.trip()
    assert breaker.is_open
    breaker.reset()
    assert not breaker.is_open


class FakeTruck:
    """Stands in for Valhalla: short trips direct, legs straight between points."""

    name = "valhalla"
    max_distance_m = 1_000_000

    def __init__(self, fail_leg: int | None = None):
        self.legs = []
        self.fail_leg = fail_leg

    def routes(self, origin, destination, truck, *, alternatives, via=()):
        return [straight_route(haversine_m(origin, destination) / 1609.344, start=origin)]

    def leg(self, a, b, truck, *, start_heading=None, end_heading=None):
        self.legs.append((a, b, start_heading, end_heading))
        if self.fail_leg is not None and len(self.legs) == self.fail_leg:
            raise ProviderError("leg failed", provider="valhalla")
        from planner.domain.entities import Route

        d = haversine_m(a, b)
        return Route((a, b), (d,), (d / 25,), ("I 80",), "valhalla")


class FakeSkeleton:
    name = "osrm"

    def routes(self, origin, destination, truck, *, alternatives, via=()):
        return [straight_route(2000, start=origin, n=200, provider="osrm")]


def test_long_trip_is_truck_routed_in_legs():
    truck = FakeTruck()
    provider = ChainedTruckRoutingProvider(truck, FakeSkeleton(), leg_km=1000)
    far = LatLon(35.0, -60.0)  # well beyond the fake truck engine's limit
    routes = provider.routes(LatLon(35, -100), far, TRUCK, alternatives=2)
    assert len(routes) == 1
    assert routes[0].provider == "valhalla"
    assert len(truck.legs) == 3  # ~3,219 km / 1,000 km
    # Legs may run concurrently: order them by start longitude (route runs east).
    legs = sorted(truck.legs, key=lambda leg: leg[0].lon)
    # Interior joins carry travel headings, the trip's ends do not.
    assert legs[0][2] is None and legs[0][3] is not None
    assert legs[-1][3] is None and legs[-1][2] is not None
    # Legs are continuous.
    for (_, b, _, _), (a2, _, _, _) in itertools.pairwise(legs):
        assert haversine_m(b, a2) < 1


def test_failed_leg_drops_corridor_not_mix_providers():
    provider = ChainedTruckRoutingProvider(FakeTruck(fail_leg=2), FakeSkeleton(), leg_km=1000)
    with pytest.raises(ProviderError):
        provider.routes(LatLon(35, -100), LatLon(35, -60), TRUCK, alternatives=2)


def test_short_trip_goes_straight_to_truck_engine():
    truck = FakeTruck()
    provider = ChainedTruckRoutingProvider(truck, FakeSkeleton())
    provider.routes(LatLon(35, -100), LatLon(35, -99), TRUCK, alternatives=2)
    assert truck.legs == []


def test_stitch_joins_without_duplicate_vertices():
    a = straight_route(10, start=LatLon(35, -100), n=5)
    b = straight_route(10, start=a.points[-1], n=5)
    s = stitch([a, b])
    assert len(s.points) == 11
    assert s.distance_m == pytest.approx(a.distance_m + b.distance_m)


def test_weather_cache_reuses_day_chunks(t0):
    inner = FakeWeather()
    cached = CachedWeatherProvider(inner, LocMemCache("t", {}), ttl_s=600)
    p = [LatLon(35, -100)]
    first = cached.hourly(p, t0, t0 + timedelta(hours=5))
    assert first[0].start == t0 and first[0].hours == 6
    # A different window on the same day is served from cache.
    second = cached.hourly(p, t0 + timedelta(hours=2), t0 + timedelta(hours=8))
    assert inner.calls == 1
    assert second[0].start == t0 + timedelta(hours=2) and second[0].hours == 7


def test_snap_keeps_weather_lookups_within_budget():
    route = straight_route(2000, n=2000)
    points = [route.points[i] for i in range(0, 2001, 8)]  # ~1 per 8 mi on one route
    step = choose_snap(points * 3)
    assert len({p.rounded(step) for p in points}) <= MAX_WEATHER_POINTS
    assert choose_snap(points[:20]) == 0.05  # short trips keep full resolution


def test_corridor_grid_respects_budget_and_covers_route():
    route = list(straight_route(600, n=300).points)
    grid = CorridorGridBuilder(max_active_nodes=200).build([route])
    assert len(grid.active) <= 200
    nodes = [grid.node(i) for i in grid.active]
    for p in route[::30]:  # every sampled route point has an active node nearby
        assert min(haversine_m(p, n) for n in nodes) < grid.step_deg * 111_320


def test_rate_limited_is_a_provider_error_with_retry_hint():
    exc = RateLimited("busy", provider="open-meteo")
    assert isinstance(exc, ProviderError) and exc.retry_after_s == 60


def test_cache_slot_throttle_allows_one_request_per_slot_across_instances():
    from planner.providers.http import CacheSlotThrottle

    shared = LocMemCache("slots", {})
    a = CacheSlotThrottle(shared, "host", 0.05)
    b = CacheSlotThrottle(shared, "host", 0.05)  # a second "instance" sharing the cache
    t0 = time.monotonic()
    for throttle in (a, b, a, b):
        throttle.wait()
    assert time.monotonic() - t0 >= 0.1  # 4 requests need at least 3 slot boundaries
