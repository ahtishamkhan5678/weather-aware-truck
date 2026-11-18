"""Weather-risk classification.

The thresholds and load rules from the brief are encoded as *data* (``Threshold`` and
``WindLoadRule`` instances) and evaluated by small, single-purpose classes. Adding a new
hazard or rule means adding data — not editing the classifier (open/closed principle).

Boundary interpretation (the brief's ranges share their end points, e.g. "0.10–0.25" and
"0.25–0.50"): every band is *lower-bound inclusive*, so 0.25 in/hr rain is High. The
brief writes the top band with a strict ">" for rain (>1.00) and snow (>3.0) and "≥" for
wind (≥55), so exactly 1.00 in/hr rain is Severe while exactly 55 mph wind is No Travel.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from .entities import HazardAssessment, RiskAssessment, RiskLevel, WeatherSample


@dataclass(frozen=True, slots=True)
class Threshold:
    """Values at/above ``minimum`` reach ``level`` (strictly above when not ``inclusive``)."""

    level: RiskLevel
    minimum: float
    inclusive: bool = True

    def matches(self, value: float) -> bool:
        return value >= self.minimum if self.inclusive else value > self.minimum


@dataclass(frozen=True, slots=True)
class HazardScale:
    hazard: str
    unit: str
    thresholds: tuple[Threshold, ...]  # ascending by level

    def classify(self, value: float) -> RiskLevel:
        level = RiskLevel.LOW
        for threshold in self.thresholds:
            if threshold.matches(value):
                level = threshold.level
        return level


class LoadRule(Protocol):
    """Escalates a wind classification depending on the truck's load."""

    def apply(
        self, wind_mph: float, load_lb: float, level: RiskLevel
    ) -> tuple[RiskLevel, str | None]: ...


@dataclass(frozen=True, slots=True)
class WindLoadRule:
    """Raise to ``result`` if ``min_wind <= wind < max_wind`` and load > ``load_over_lb``.

    ``max_wind=None`` means unbounded; ``load_over_lb=None`` means any load.
    """

    min_wind_mph: float
    max_wind_mph: float | None
    load_over_lb: float | None
    result: RiskLevel
    description: str

    def apply(
        self, wind_mph: float, load_lb: float, level: RiskLevel
    ) -> tuple[RiskLevel, str | None]:
        in_band = wind_mph >= self.min_wind_mph and (
            self.max_wind_mph is None or wind_mph < self.max_wind_mph
        )
        heavy = self.load_over_lb is None or load_lb > self.load_over_lb
        if in_band and heavy and self.result > level:
            return self.result, self.description
        return level, None


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    wind: HazardScale
    rain: HazardScale
    snow: HazardScale
    load_rules: tuple[WindLoadRule, ...]

    def to_dict(self) -> dict:
        """Serialisable view (served by /api/rules so the UI never duplicates the rules)."""

        def scale(s: HazardScale) -> dict:
            return {
                "hazard": s.hazard,
                "unit": s.unit,
                "thresholds": [
                    {"level": t.level.key, "minimum": t.minimum, "inclusive": t.inclusive}
                    for t in s.thresholds
                ],
            }

        return {
            "levels": [
                {"key": lvl.key, "label": lvl.label, "score": int(lvl)} for lvl in RiskLevel
            ],
            "hazards": [scale(self.wind), scale(self.rain), scale(self.snow)],
            "load_rules": [
                {
                    "min_wind_mph": r.min_wind_mph,
                    "max_wind_mph": r.max_wind_mph,
                    "load_over_lb": r.load_over_lb,
                    "result": r.result.key,
                    "description": r.description,
                }
                for r in self.load_rules
            ],
        }


L = RiskLevel
DEFAULT_POLICY = RiskPolicy(
    wind=HazardScale(
        "wind",
        "mph",
        (
            Threshold(L.MODERATE, 25),
            Threshold(L.HIGH, 35),
            Threshold(L.SEVERE, 45),
            Threshold(L.NO_TRAVEL, 55),
        ),
    ),
    rain=HazardScale(
        "rain",
        "in/hr",
        (
            Threshold(L.MODERATE, 0.10),
            Threshold(L.HIGH, 0.25),
            Threshold(L.SEVERE, 0.50),
            Threshold(L.NO_TRAVEL, 1.00, inclusive=False),
        ),
    ),
    snow=HazardScale(
        "snow",
        "in/hr",
        (
            Threshold(L.MODERATE, 0.5),
            Threshold(L.HIGH, 1.0),
            Threshold(L.SEVERE, 2.0),
            Threshold(L.NO_TRAVEL, 3.0, inclusive=False),
        ),
    ),
    load_rules=(
        WindLoadRule(55, None, None, L.NO_TRAVEL, "Wind ≥55 mph: no travel for any load"),
        WindLoadRule(45, 55, 30_000, L.NO_TRAVEL, "Wind 45–54 mph with load >30,000 lb"),
        WindLoadRule(35, 45, 40_000, L.SEVERE, "Wind 35–44 mph with load >40,000 lb"),
    ),
)


class RiskClassifier:
    """Turns a weather sample + load into a risk assessment (max of all hazards)."""

    def __init__(self, policy: RiskPolicy = DEFAULT_POLICY) -> None:
        self._policy = policy

    @property
    def policy(self) -> RiskPolicy:
        return self._policy

    def wind_level(self, wind_mph: float, load_lb: float) -> tuple[RiskLevel, str | None]:
        level = self._policy.wind.classify(wind_mph)
        note = None
        for rule in self._policy.load_rules:
            level, applied = rule.apply(wind_mph, load_lb, level)
            note = applied or note
        return level, note

    def assess(self, weather: WeatherSample, load_lb: float) -> RiskAssessment:
        wind_level, note = self.wind_level(weather.wind_mph, load_lb)
        hazards = (
            HazardAssessment("wind", weather.wind_mph, wind_level, note),
            HazardAssessment(
                "rain", weather.rain_in_hr, self._policy.rain.classify(weather.rain_in_hr)
            ),
            HazardAssessment(
                "snow", weather.snow_in_hr, self._policy.snow.classify(weather.snow_in_hr)
            ),
        )
        return RiskAssessment(level=max(h.level for h in hazards), hazards=hazards)

    def levels(self, samples: Iterable[WeatherSample], load_lb: float) -> Sequence[RiskLevel]:
        return [self.assess(s, load_lb).level for s in samples]
