"""HTTP contract tests — the container is patched with fake adapters."""

from datetime import UTC, datetime, timedelta

import pytest
from rest_framework.test import APIClient

from planner.domain.entities import LatLon, Place
from planner.domain.eta import TruckEtaModel
from planner.domain.ranking import RouteRanker
from planner.domain.risk import RiskClassifier
from planner.services import container
from planner.services.heatmap import HeatmapService
from planner.services.planner import TripPlanner

from .conftest import FakeFinder, FakeWeather, straight_route


class FakeGeocoder:
    def search(self, q, *, limit=5, bias=None):
        return [Place(f"{q}, TX, US", LatLon(32.7, -96.8))] if q != "nowhere" else []


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    weather = FakeWeather(wind_fn=lambda p, t: 38.0)
    tp = TripPlanner(
        FakeFinder([straight_route(80), straight_route(90, mph=55)]),
        weather,
        RiskClassifier(),
        TruckEtaModel(),
        RouteRanker(),
        tare_weight_lb=33_000,
    )
    monkeypatch.setattr(container, "trip_planner", lambda: tp)
    monkeypatch.setattr(
        container, "heatmap_service", lambda: HeatmapService(weather, RiskClassifier())
    )
    monkeypatch.setattr(container, "geocoder", lambda: FakeGeocoder())


@pytest.fixture
def client():
    return APIClient()


def plan_body(**overrides):
    body = {
        "origin": {"label": "Austin", "lat": 30.27, "lon": -97.74},
        "destination": "Dallas",
        "departure_time": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "load_weight_lb": 42_000,
        "interval_miles": 25,
    }
    body.update(overrides)
    return body


def test_plan_contract(client):
    res = client.post("/api/plan", plan_body(), format="json")
    assert res.status_code == 200, res.content
    data = res.json()
    assert data["destination"]["label"] == "Dallas, TX, US"  # geocoded server-side
    assert len(data["routes"]) == 2
    rec = data["recommendation"]
    assert rec["route_id"] in {"A", "B"}
    route = data["routes"][0]
    assert {"geometry", "checkpoints", "risk", "arrival", "roads"} <= route.keys()
    cp = route["checkpoints"][1]
    assert cp["level"] == "severe"  # 38 mph + 42,000 lb → Severe (load rule)
    assert cp["hazards"][0]["note"].startswith("Wind 35–44")
    assert sum(route["risk"]["miles_by_level"].values()) == pytest.approx(80, abs=0.2)


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"interval_miles": 30}, "interval_miles"),
        ({"load_weight_lb": -5}, "load_weight_lb"),
        ({"departure_time": "2020-01-01T00:00:00Z"}, "departure_time"),
        ({"origin": {"lat": 120, "lon": 0}}, "origin"),
    ],
)
def test_plan_validation(client, override, field):
    res = client.post("/api/plan", plan_body(**override), format="json")
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_request"
    assert field in res.json()["error"]["details"]


def test_unknown_place_is_422(client):
    res = client.post("/api/plan", plan_body(destination="nowhere"), format="json")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "no_route"


def test_heatmap_contract(client):
    line = [[-100.0, 35.0], [-99.0, 35.2], [-98.0, 35.0]]
    res = client.post("/api/heatmap", {"routes": [line], "load_weight_lb": 45_000}, format="json")
    assert res.status_code == 200, res.content
    data = res.json()
    assert data["hours"] == 49
    n = len(data["active"])
    assert n > 0 and len(data["layers"]["risk"]) == n * 49
    assert set(data["layers"]["risk"]) == {3}  # 38 mph + 45,000 lb → Severe


def test_rules_and_geocode(client):
    assert client.get("/api/rules").json()["hazards"][0]["hazard"] == "wind"
    res = client.get("/api/geocode", {"q": "Dallas"})
    assert res.json()["results"][0]["lat"] == 32.7
    assert client.get("/api/geocode", {"q": "D"}).status_code == 400
