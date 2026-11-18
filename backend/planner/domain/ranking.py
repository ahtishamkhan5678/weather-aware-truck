"""Route recommendation.

Order of preference (from the brief):

1. Fewest Severe miles
2. Fewest High miles
3. Lowest average risk
4. Shortest travel time

"No Travel" is strictly worse than Severe, so No-Travel miles are compared *before*
Severe miles (a route with 5 No-Travel miles never beats one with 5 Severe miles).

Exact floating-point comparisons would make travel time irrelevant (two routes never
tie on average risk to 15 decimals), so every criterion uses a small tolerance: routes
within the tolerance of the best value are considered tied and the next criterion
decides. This is what "balancing weather risk and travel time" means in practice:
risk dominates, time breaks ties between routes that are equally safe.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .entities import RiskLevel, RouteAnalysis


@dataclass(frozen=True, slots=True)
class Criterion:
    key: str
    label: str
    value: Callable[[RouteAnalysis], float]
    tolerance: float
    unit: str


@dataclass(frozen=True, slots=True)
class RankingConfig:
    miles_tolerance: float = 1.0  # one mile ≈ less than one checkpoint's resolution
    avg_risk_tolerance: float = 0.05  # on the 0–4 scale
    time_tolerance_s: float = 60.0


@dataclass(frozen=True, slots=True)
class Ranking:
    ordered: tuple[RouteAnalysis, ...]
    reasons: tuple[str, ...]
    decided_by: str
    all_routes_blocked: bool

    @property
    def best(self) -> RouteAnalysis:
        return self.ordered[0]


class RouteRanker:
    def __init__(self, config: RankingConfig | None = None) -> None:
        cfg = config or RankingConfig()
        self.criteria: tuple[Criterion, ...] = (
            Criterion(
                "no_travel_miles",
                "No-Travel miles",
                lambda a: a.miles_at(RiskLevel.NO_TRAVEL),
                cfg.miles_tolerance,
                "mi",
            ),
            Criterion(
                "severe_miles",
                "Severe miles",
                lambda a: a.miles_at(RiskLevel.SEVERE),
                cfg.miles_tolerance,
                "mi",
            ),
            Criterion(
                "high_miles",
                "High miles",
                lambda a: a.miles_at(RiskLevel.HIGH),
                cfg.miles_tolerance,
                "mi",
            ),
            Criterion(
                "average_risk", "average risk", lambda a: a.average_risk, cfg.avg_risk_tolerance, ""
            ),
            Criterion("travel_time", "travel time", lambda a: a.trip_s, cfg.time_tolerance_s, "s"),
        )

    def _pick_best(self, pool: Sequence[RouteAnalysis]) -> tuple[RouteAnalysis, str]:
        candidates = list(pool)
        decided_by = "travel_time"
        for criterion in self.criteria:
            best = min(criterion.value(a) for a in candidates)
            narrowed = [a for a in candidates if criterion.value(a) - best <= criterion.tolerance]
            if len(narrowed) < len(candidates):
                decided_by = criterion.key
            candidates = narrowed
            if len(candidates) == 1:
                return candidates[0], decided_by
        # Still tied on everything → strictly shortest trip, then stable id order.
        winner = min(candidates, key=lambda a: (a.trip_s, a.route_id))
        return winner, decided_by

    def rank(self, analyses: Sequence[RouteAnalysis]) -> Ranking:
        if not analyses:
            raise ValueError("Nothing to rank")
        remaining = list(analyses)
        ordered: list[RouteAnalysis] = []
        decided_by = "travel_time"
        while remaining:
            best, why = self._pick_best(remaining)
            if not ordered:
                decided_by = why
            ordered.append(best)
            remaining.remove(best)
        best = ordered[0]
        reasons = tuple(self._explain(best, other) for other in ordered[1:])
        blocked = all(a.miles_at(RiskLevel.NO_TRAVEL) > 0 for a in analyses)
        return Ranking(tuple(ordered), reasons, decided_by, blocked)

    def _explain(self, best: RouteAnalysis, other: RouteAnalysis) -> str:
        """First criterion (in priority order) where ``best`` is meaningfully better."""
        for c in self.criteria:
            b, o = c.value(best), c.value(other)
            if o - b > c.tolerance:
                return f"vs Route {other.route_id}: {_describe(c, o - b)}"
        return f"vs Route {other.route_id}: equally safe and no slower"


def _describe(c: Criterion, delta: float) -> str:
    if c.unit == "mi":
        return f"{delta:.0f} fewer {c.label}"
    if c.unit == "s":
        minutes = round(delta / 60)
        if minutes >= 60:
            return f"{minutes // 60} h {minutes % 60:02d} min faster with equal risk"
        return f"{minutes} min faster with equal risk"
    return f"{delta:.2f} lower {c.label}"
