"""Use case: 0–48 h weather/risk forecast on a grid covering the trip corridor."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ..domain.corridor import CorridorGrid, CorridorGridBuilder
from ..domain.entities import LatLon
from ..domain.eta import floor_hour
from ..domain.risk import RiskClassifier
from ..providers.base import WeatherProvider

HEATMAP_HOURS = 48


@dataclass(frozen=True, slots=True)
class HeatmapResult:
    grid: CorridorGrid
    start: datetime
    hours: int  # number of frames (49 → hours 0..48)
    # One flat list per layer, laid out [node0 h0..h48, node1 h0..h48, …] for active nodes.
    layers: dict[str, list[float]]


class HeatmapService:
    def __init__(
        self,
        weather: WeatherProvider,
        classifier: RiskClassifier,
        grid_builder: CorridorGridBuilder | None = None,
        clock=lambda: datetime.now(UTC),
    ) -> None:
        self._weather = weather
        self._classifier = classifier
        self._grid = grid_builder or CorridorGridBuilder()
        self._clock = clock

    def build(self, routes: Sequence[Sequence[LatLon]], load_weight_lb: float) -> HeatmapResult:
        grid = self._grid.build(routes)
        start = floor_hour(self._clock())
        end = start + timedelta(hours=HEATMAP_HOURS)
        nodes = [grid.node(i) for i in grid.active]
        series = self._weather.hourly(nodes, start, end)

        frames = HEATMAP_HOURS + 1
        risk: list[float] = []
        wind: list[float] = []
        rain: list[float] = []
        snow: list[float] = []
        for s in series:
            for h in range(frames):
                sample = s.hour(min(h, s.hours - 1))
                risk.append(int(self._classifier.assess(sample, load_weight_lb).level))
                wind.append(round(sample.wind_mph, 1))
                rain.append(round(sample.rain_in_hr, 3))
                snow.append(round(sample.snow_in_hr, 3))
        return HeatmapResult(
            grid, start, frames, {"risk": risk, "wind": wind, "rain": rain, "snow": snow}
        )
