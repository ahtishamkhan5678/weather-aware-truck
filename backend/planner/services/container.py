"""Composition root: the only place that knows which concrete adapters are used."""

from __future__ import annotations

from functools import lru_cache

from django.conf import settings
from django.core.cache import cache

from ..domain.corridor import CorridorGridBuilder
from ..domain.eta import HoursOfService, TruckEtaModel
from ..domain.ranking import RouteRanker
from ..domain.risk import DEFAULT_POLICY, RiskClassifier
from ..providers.cache import CachedRouteFinder, CachedWeatherProvider
from ..providers.http import CacheSlotThrottle, CircuitBreaker, HostThrottle, build_session
from ..providers.long_haul import ChainedTruckRoutingProvider
from ..providers.open_meteo import OpenMeteoWeatherProvider
from ..providers.osrm import OsrmRoutingProvider
from ..providers.photon import PhotonGeocoder
from ..providers.routing import AlternativeRouteService
from ..providers.valhalla import ValhallaRoutingProvider
from .heatmap import HeatmapService
from .planner import TripPlanner


@lru_cache(maxsize=1)
def _session():
    return build_session()


def _throttle(key: str, interval: float):
    """Shared (Redis) throttle when a shared cache exists, else an in-process one."""
    if settings.PLANNER["SHARED_CACHE"]:
        return CacheSlotThrottle(cache, key, interval)
    return HostThrottle(interval)


@lru_cache(maxsize=1)
def classifier() -> RiskClassifier:
    return RiskClassifier(DEFAULT_POLICY)


@lru_cache(maxsize=1)
def weather_provider():
    cfg = settings.PLANNER
    inner = OpenMeteoWeatherProvider(
        _session(),
        cfg["OPEN_METEO_BASE_URL"],
        api_key=cfg["OPEN_METEO_API_KEY"],
        timeout_s=cfg["HTTP_TIMEOUT_S"],
    )
    return CachedWeatherProvider(inner, cache, cfg["WEATHER_CACHE_TTL_S"])


@lru_cache(maxsize=1)
def trip_planner() -> TripPlanner:
    cfg = settings.PLANNER
    valhalla = ValhallaRoutingProvider(
        _session(),
        cfg["VALHALLA_BASE_URL"],
        timeout_s=cfg["HTTP_TIMEOUT_S"],
        max_distance_km=cfg["VALHALLA_MAX_KM"],
        top_speed_kph=cfg["TRUCK_MAX_SPEED_MPH"] * 1.609344,
        throttle=_throttle("valhalla", cfg["VALHALLA_MIN_INTERVAL_S"]),
        breaker=CircuitBreaker(cooldown_s=300),
    )
    osrm = OsrmRoutingProvider(
        _session(),
        cfg["OSRM_BASE_URL"],
        timeout_s=cfg["HTTP_TIMEOUT_S"],
        throttle=_throttle("osrm", cfg["OSRM_MIN_INTERVAL_S"]),
    )
    # Truck routing for every trip length (long trips: OSRM corridor → truck-routed legs);
    # plain OSRM only if the truck engine is unavailable.
    providers = [ChainedTruckRoutingProvider(valhalla, osrm), osrm]
    finder = CachedRouteFinder(
        AlternativeRouteService(providers, count=cfg["ROUTE_OPTIONS"]),
        cache,
        cfg["ROUTE_CACHE_TTL_S"],
    )
    eta = TruckEtaModel(
        max_speed_mph=cfg["TRUCK_MAX_SPEED_MPH"],
        hos=HoursOfService() if cfg["TRUCK_APPLY_HOS"] else None,
    )
    return TripPlanner(
        finder,
        weather_provider(),
        classifier(),
        eta,
        RouteRanker(),
        tare_weight_lb=cfg["TRUCK_TARE_WEIGHT_LB"],
    )


@lru_cache(maxsize=1)
def heatmap_service() -> HeatmapService:
    return HeatmapService(
        weather_provider(),
        classifier(),
        CorridorGridBuilder(max_active_nodes=settings.PLANNER["HEATMAP_MAX_NODES"]),
    )


@lru_cache(maxsize=1)
def geocoder() -> PhotonGeocoder:
    return PhotonGeocoder(_session(), settings.PLANNER["PHOTON_BASE_URL"])
