import pytest

from planner.domain.entities import RiskLevel as L
from planner.domain.entities import WeatherSample
from planner.domain.risk import DEFAULT_POLICY, RiskClassifier

clf = RiskClassifier()


def wx(wind=0.0, rain=0.0, snow=0.0):
    return WeatherSample(wind, wind, rain, snow)


@pytest.mark.parametrize(
    ("mph", "level"),
    [
        (0, L.LOW),
        (24.9, L.LOW),
        (25, L.MODERATE),
        (34.9, L.MODERATE),
        (35, L.HIGH),
        (44.9, L.HIGH),
        (45, L.SEVERE),
        (54.9, L.SEVERE),
        (55, L.NO_TRAVEL),
        (80, L.NO_TRAVEL),
    ],
)
def test_wind_thresholds_light_load(mph, level):
    assert clf.assess(wx(wind=mph), load_lb=10_000).level == level


@pytest.mark.parametrize(
    ("rate", "level"),
    [
        (0.0, L.LOW),
        (0.099, L.LOW),
        (0.10, L.MODERATE),
        (0.249, L.MODERATE),
        (0.25, L.HIGH),
        (0.499, L.HIGH),
        (0.50, L.SEVERE),
        (1.00, L.SEVERE),
        (1.001, L.NO_TRAVEL),
    ],
)
def test_rain_thresholds(rate, level):
    assert clf.assess(wx(rain=rate), 0).level == level


@pytest.mark.parametrize(
    ("rate", "level"),
    [
        (0.49, L.LOW),
        (0.5, L.MODERATE),
        (0.99, L.MODERATE),
        (1.0, L.HIGH),
        (1.99, L.HIGH),
        (2.0, L.SEVERE),
        (3.0, L.SEVERE),
        (3.01, L.NO_TRAVEL),
    ],
)
def test_snow_thresholds(rate, level):
    assert clf.assess(wx(snow=rate), 0).level == level


@pytest.mark.parametrize(
    ("mph", "load", "level"),
    [
        (55, 0, L.NO_TRAVEL),  # ≥55 → No Travel for any load
        (60, 5_000, L.NO_TRAVEL),
        (45, 30_000, L.SEVERE),  # exactly 30,000 is not ">30,000"
        (45, 30_001, L.NO_TRAVEL),
        (54.9, 45_000, L.NO_TRAVEL),
        (35, 40_000, L.HIGH),  # exactly 40,000 is not ">40,000"
        (35, 40_001, L.SEVERE),
        (44.9, 60_000, L.SEVERE),
        (34.9, 60_000, L.MODERATE),  # below 35 mph load does not matter
    ],
)
def test_load_rules(mph, load, level):
    result = clf.assess(wx(wind=mph), load)
    assert result.level == level


def test_load_rule_note_is_reported():
    wind = clf.assess(wx(wind=40), 42_000).hazards[0]
    assert wind.level == L.SEVERE
    assert "40,000" in wind.note


def test_overall_is_worst_hazard_and_drivers():
    r = clf.assess(wx(wind=30, rain=0.3, snow=0.6), 0)
    assert r.level == L.HIGH
    assert [h.hazard for h in r.drivers] == ["rain"]


def test_policy_serialises():
    d = DEFAULT_POLICY.to_dict()
    assert [h["hazard"] for h in d["hazards"]] == ["wind", "rain", "snow"]
    assert len(d["load_rules"]) == 3
