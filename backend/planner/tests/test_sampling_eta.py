import itertools
from datetime import timedelta

import pytest

from planner.domain.eta import HoursOfService, TruckEtaModel
from planner.domain.geo import METERS_PER_MILE
from planner.domain.sampling import RouteSampler

from .conftest import straight_route


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_checkpoints_every_interval_and_at_destination(interval):
    route = straight_route(132)
    pos = RouteSampler(interval).positions(route)
    miles = [p.distance_m / METERS_PER_MILE for p in pos]
    assert miles[0] == 0
    assert miles[-1] == pytest.approx(132, abs=1e-6)
    for a, b in itertools.pairwise(miles[:-1]):
        assert b - a == pytest.approx(interval)
    # Represented miles partition the route exactly.
    assert sum(p.represented_m for p in pos) == pytest.approx(route.distance_m)


def test_tiny_final_stub_is_merged():
    pos = RouteSampler(10).positions(straight_route(100.2))
    assert len(pos) == 11  # 0,10,…,90,100.2 — no extra point 0.2 mi after 100


def test_speed_cap_slows_fast_segments():
    route = straight_route(100, mph=80)
    _, cum_t = TruckEtaModel(max_speed_mph=65).driving_profile(route)
    assert cum_t[-1] == pytest.approx(100 / 65 * 3600, rel=1e-6)


def test_slow_segments_untouched_by_cap():
    route = straight_route(100, mph=50)
    _, cum_t = TruckEtaModel(max_speed_mph=65).driving_profile(route)
    assert cum_t[-1] == pytest.approx(2 * 3600, rel=1e-6)


def test_hos_breaks_and_rests():
    hos = HoursOfService()
    assert hos.rest_stops(8 * 3600) == []  # exactly at the limit → no stop needed
    kinds = [s.kind for s in hos.rest_stops(9 * 3600)]
    assert kinds == ["break"]
    stops = hos.rest_stops(30 * 3600)  # 11 + 11 + 8 h: the last shift ends exactly at 8 h
    assert [s.kind for s in stops] == ["break", "rest", "break", "rest"]
    assert hos.elapsed_for(30 * 3600) == 30 * 3600 + 2 * 1800 + 2 * 36000
    assert [s.kind for s in hos.rest_stops(31 * 3600)][-1] == "break"


def test_eta_applies_hos(t0):
    model = TruckEtaModel(hos=HoursOfService())
    assert model.eta(t0, 4 * 3600) == t0 + timedelta(hours=4)
    assert model.eta(t0, 10 * 3600) == t0 + timedelta(hours=10.5)
    assert model.eta(t0, 12 * 3600) == t0 + timedelta(hours=12 + 0.5 + 10)
