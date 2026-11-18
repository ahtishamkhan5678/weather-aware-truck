"""Use-case tests with fake providers: ETA-aware weather, mile aggregation, ranking."""

from datetime import timedelta

import pytest

from planner.domain.entities import LatLon, Place, RiskLevel
from planner.domain.eta import HoursOfService, TruckEtaModel
from planner.domain.ranking import RouteRanker
from planner.domain.risk import RiskClassifier
from planner.services.planner import PlanningError, PlanRequest, TripPlanner

from .conftest import FakeFinder, FakeWeather, straight_route


def planner(routes, weather, t0, hos=False):
    return TripPlanner(
        FakeFinder(routes),
        weather,
        RiskClassifier(),
        TruckEtaModel(65, HoursOfService() if hos else None),
        RouteRanker(),
        tare_weight_lb=33_000,
        clock=lambda: t0,
    )


def request(t0, load=20_000, interval=10):
    return PlanRequest(
        Place("O", LatLon(35, -100)), Place("D", LatLon(35, -98)), t0, load, interval
    )


def test_weather_is_sampled_at_truck_eta(t0):
    # Severe wind everywhere from 1 h after departure → only checkpoints reached later are hit.
    weather = FakeWeather(wind_fn=lambda p, t: 50.0 if t >= t0 + timedelta(hours=1) else 5.0)
    result = planner([straight_route(120, mph=60)], weather, t0).plan(request(t0))
    route = result.analyses[0]
    for cp in route.checkpoints:
        expected = RiskLevel.LOW if cp.eta < t0 + timedelta(hours=1) else RiskLevel.SEVERE
        # Wind is interpolated between hours, so allow the hour right at the switch.
        if abs((cp.eta - (t0 + timedelta(hours=1))).total_seconds()) > 3600:
            assert cp.risk.level == expected
    assert route.miles_at(RiskLevel.SEVERE) > 0
    total = sum(route.miles_by_level.values())
    assert total == pytest.approx(120, abs=0.01)
    assert weather.calls == 1  # one batched lookup for everything


def test_heavy_load_turns_high_wind_severe(t0):
    weather = FakeWeather(wind_fn=lambda p, t: 40.0)
    light = planner([straight_route(50)], weather, t0).plan(request(t0, load=20_000))
    heavy = planner([straight_route(50)], weather, t0).plan(request(t0, load=45_000))
    assert light.analyses[0].max_level == RiskLevel.HIGH
    assert heavy.analyses[0].max_level == RiskLevel.SEVERE


def test_recommends_route_avoiding_storm(t0):
    north = straight_route(100, mph=60, start=LatLon(37, -100))
    south = straight_route(130, mph=60, start=LatLon(33, -100))
    weather = FakeWeather(wind_fn=lambda p, t: 48.0 if p.lat > 36 else 8.0)
    result = planner([north, south], weather, t0).plan(request(t0, load=10_000))
    assert [a.route_id for a in result.analyses] == ["A", "B"]
    assert result.ranking.best.route_id == "B"
    assert result.ranking.decided_by == "severe_miles"


def test_fastest_wins_when_equally_safe(t0):
    slow = straight_route(100, mph=45)
    fast = straight_route(100, mph=60)
    result = planner([slow, fast], FakeWeather(), t0).plan(request(t0))
    assert result.ranking.best.route_id == "B"
    assert result.ranking.decided_by == "travel_time"


def test_hos_shifts_late_checkpoint_etas(t0):
    route = straight_route(650, mph=65)  # 10 h of driving → one 30-min break
    result = planner([route], FakeWeather(), t0, hos=True).plan(request(t0, interval=50))
    a = result.analyses[0]
    assert [s.kind for s in a.rest_stops] == ["break"]
    assert a.arrival == t0 + timedelta(hours=10.5)
    assert a.checkpoints[-1].eta == a.arrival


def test_beyond_forecast_horizon_is_rejected(t0):
    with pytest.raises(PlanningError):
        planner([straight_route(50)], FakeWeather(), t0 - timedelta(days=20)).plan(request(t0))


def test_warns_when_fewer_than_three_routes(t0):
    result = planner([straight_route(50)], FakeWeather(), t0).plan(request(t0))
    assert any("distinct route" in w for w in result.warnings)
