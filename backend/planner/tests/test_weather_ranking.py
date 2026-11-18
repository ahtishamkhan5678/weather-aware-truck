from datetime import timedelta

import pytest

from planner.domain.entities import LatLon, RiskLevel, RouteAnalysis
from planner.domain.geo import decode_polyline, haversine_m
from planner.domain.ranking import RouteRanker
from planner.domain.weather import ForecastSeries

from .conftest import straight_route


def test_series_interpolates_wind_and_buckets_precip(t0):
    s = ForecastSeries(
        LatLon(0, 0), t0, (10, 20, 30), (10, 20, 30), (0.0, 0.2, 0.6), (0.0, 0.0, 1.5)
    )
    mid = s.at(t0 + timedelta(minutes=30))
    assert mid.wind_mph == pytest.approx(15)
    assert mid.rain_in_hr == 0.2  # bucket (t0, t0+1h] is reported at t0+1h
    late = s.at(t0 + timedelta(hours=1, minutes=10))
    assert late.rain_in_hr == 0.6 and late.snow_in_hr == 1.5
    assert s.at(t0 + timedelta(hours=9)).wind_mph == 30  # clamped


def _analysis(rid, t0, *, severe=0.0, high=0.0, low=100.0, no_travel=0.0, hours=10.0):
    miles = {
        RiskLevel.LOW: low,
        RiskLevel.MODERATE: 0.0,
        RiskLevel.HIGH: high,
        RiskLevel.SEVERE: severe,
        RiskLevel.NO_TRAVEL: no_travel,
    }
    return RouteAnalysis(
        rid, straight_route(10), t0, t0 + timedelta(hours=hours), hours * 3600, (), (), miles
    )


def test_fewest_severe_beats_faster(t0):
    a = _analysis("A", t0, severe=20, hours=8)
    b = _analysis("B", t0, severe=0, high=50, hours=12)
    r = RouteRanker().rank([a, b])
    assert r.best.route_id == "B"
    assert r.decided_by == "severe_miles"
    assert "20 fewer Severe miles" in r.reasons[0]


def test_no_travel_ranks_below_severe(t0):
    a = _analysis("A", t0, no_travel=5)
    b = _analysis("B", t0, severe=60)
    assert RouteRanker().rank([a, b]).best.route_id == "B"


def test_high_then_average_then_time(t0):
    a = _analysis("A", t0, high=10, hours=5)
    b = _analysis("B", t0, high=2, hours=9)
    assert RouteRanker().rank([a, b]).best.route_id == "B"
    c = _analysis("C", t0, low=100, hours=9)
    d = _analysis("D", t0, low=100, hours=7)
    r = RouteRanker().rank([c, d])
    assert r.best.route_id == "D" and r.decided_by == "travel_time"


def test_tolerance_lets_time_break_near_ties(t0):
    a = _analysis("A", t0, severe=10.4, hours=6)
    b = _analysis("B", t0, severe=10.0, hours=9)
    assert RouteRanker().rank([a, b]).best.route_id == "A"


def test_all_blocked_flag(t0):
    r = RouteRanker().rank([_analysis("A", t0, no_travel=3), _analysis("B", t0, no_travel=1)])
    assert r.all_routes_blocked
    assert r.best.route_id == "B"


def test_polyline_decode_reference_example():
    # Google's documented example (precision 5); Valhalla uses the same scheme at 6.
    pts = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@", 5)
    assert pts[0] == LatLon(38.5, -120.2)
    assert pts[2].lat == pytest.approx(43.252) and pts[2].lon == pytest.approx(-126.453)


def test_haversine_one_degree_latitude():
    assert haversine_m(LatLon(0, 0), LatLon(1, 0)) == pytest.approx(111_195, rel=1e-3)
