"""Adapter parsing + alternative-route synthesis (no network: fake sessions/providers)."""

import pytest

from planner.domain.entities import LatLon, TruckProfile
from planner.providers.base import ProviderError
from planner.providers.osrm import OsrmRoutingProvider
from planner.providers.routing import AlternativeRouteService
from planner.providers.valhalla import ValhallaRoutingProvider

from .conftest import straight_route

TRUCK = TruckProfile(30_000, 33_000)


class FakeResponse:
    def __init__(self, data, status=200):
        self._data, self.status_code, self.text = data, status, str(data)

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, data, status=200):
        self.data, self.status, self.calls = data, status, []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        return FakeResponse(self.data, self.status)

    post = get


def test_osrm_parses_geometry_and_annotations():
    data = {
        "code": "Ok",
        "routes": [
            {
                "distance": 2000.0,
                "duration": 100.0,
                "geometry": {"coordinates": [[-97.0, 30.0], [-97.0, 30.01], [-97.0, 30.02]]},
                "legs": [
                    {
                        "annotation": {"distance": [1000.0, 1000.0], "duration": [40.0, 60.0]},
                        "steps": [{"ref": "I 35", "distance": 2000.0}],
                    }
                ],
            }
        ],
    }
    routes = OsrmRoutingProvider(FakeSession(data), "http://osrm").routes(
        LatLon(30, -97), LatLon(30.02, -97), TRUCK, alternatives=2
    )
    r = routes[0]
    assert r.points[1] == LatLon(30.01, -97.0)
    assert r.segment_durations_s == (40.0, 60.0)
    assert r.roads == ("I 35",) and r.provider == "osrm"


def test_valhalla_distributes_maneuver_time_and_sends_weight():
    # polyline6 for (30,-97) → (30.01,-97) → (30.02,-97)
    shape = "_c`|y@~hokwD_pR?_pR?"
    data = {
        "trip": {
            "legs": [
                {
                    "shape": shape,
                    "maneuvers": [
                        {
                            "begin_shape_index": 0,
                            "end_shape_index": 2,
                            "time": 120.0,
                            "length": 1.4,
                            "highway": True,
                            "street_names": ["I 35"],
                        }
                    ],
                }
            ]
        }
    }
    session = FakeSession(data)
    routes = ValhallaRoutingProvider(session, "http://v").routes(
        LatLon(30, -97), LatLon(30.02, -97), TRUCK, alternatives=2
    )
    r = routes[0]
    assert len(r.points) == 3
    assert sum(r.segment_durations_s) == pytest.approx(120.0)
    assert abs(r.segment_durations_s[0] - 60.0) < 0.5
    body = session.calls[0][1]["json"]
    assert body["costing"] == "truck" and body["alternates"] == 2
    assert body["costing_options"]["truck"]["weight"] == round(63_000 * 0.000453592, 2)


def test_valhalla_rejects_trips_beyond_limit_without_calling():
    session = FakeSession({})
    provider = ValhallaRoutingProvider(session, "http://v", max_distance_km=500)
    try:
        provider.routes(LatLon(34, -118), LatLon(41.8, -87.6), TRUCK, alternatives=2)
        raise AssertionError("expected ProviderError")
    except ProviderError:
        assert session.calls == []


class ScriptedProvider:
    """Primary call returns one route; via calls return a distinct or duplicate route."""

    def __init__(self, name="p", fail=False):
        self.name, self.fail, self.via_calls = name, fail, 0

    def routes(self, origin, destination, truck, *, alternatives, via=()):
        if self.fail:
            raise ProviderError("down", provider=self.name)
        if not via:
            return [straight_route(100, start=LatLon(35, -100), provider=self.name)]
        self.via_calls += 1
        if self.via_calls == 1:  # duplicate of the primary → must be discarded
            return [straight_route(100, start=LatLon(35, -100), provider=self.name)]
        lat = 35 + 0.3 * self.via_calls
        return [straight_route(110, start=LatLon(lat, -100), provider=self.name)]


def test_alternatives_fill_to_three_and_drop_duplicates():
    provider = ScriptedProvider()
    routes = AlternativeRouteService([provider], count=3).find(
        LatLon(35, -100), LatLon(35, -98), TRUCK
    )
    assert len(routes) == 3
    starts = {round(r.points[0].lat, 1) for r in routes}
    assert len(starts) == 3  # all distinct


def test_fallback_uses_one_provider_for_all_options():
    routes = AlternativeRouteService(
        [ScriptedProvider("valhalla", fail=True), ScriptedProvider("osrm")], count=3
    ).find(LatLon(35, -100), LatLon(35, -98), TRUCK)
    assert {r.provider for r in routes} == {"osrm"}
