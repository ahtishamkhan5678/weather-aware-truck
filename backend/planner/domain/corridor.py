"""Regular lat/lon grid that covers the trip corridor (used by the forecast heatmap)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .entities import LatLon
from .geo import METERS_PER_MILE, bounding_box, point_polyline_distance_m, simplify


@dataclass(frozen=True, slots=True)
class CorridorGrid:
    south: float
    west: float
    step_deg: float
    rows: int
    cols: int
    active: tuple[int, ...]  # flat indices (row * cols + col) of nodes inside the corridor

    def node(self, index: int) -> LatLon:
        row, col = divmod(index, self.cols)
        return LatLon(self.south + row * self.step_deg, self.west + col * self.step_deg)

    @property
    def north(self) -> float:
        return self.south + (self.rows - 1) * self.step_deg

    @property
    def east(self) -> float:
        return self.west + (self.cols - 1) * self.step_deg


class CorridorGridBuilder:
    """Builds a grid whose spacing adapts to the trip size and keeps only corridor nodes.

    A node is kept if it lies within ``corridor_mi`` of any route *plus one grid diagonal*,
    so bilinear interpolation inside the corridor always has its four neighbours.
    """

    def __init__(
        self,
        corridor_mi: float = 30.0,
        target_cells: int = 24,
        min_step_deg: float = 0.2,
        max_active_nodes: int = 240,
    ) -> None:
        self.corridor_m = corridor_mi * METERS_PER_MILE
        self.target_cells = target_cells
        self.min_step_deg = min_step_deg
        self.max_active_nodes = max_active_nodes

    def build(self, routes: Sequence[Sequence[LatLon]]) -> CorridorGrid:
        lines = [simplify(r, 1500.0) for r in routes if len(r) >= 2]
        if not lines:
            raise ValueError("At least one route is required")
        all_points = [p for line in lines for p in line]
        south, west, north, east = bounding_box(all_points)
        mid_lat = math.radians((south + north) / 2)
        pad_lat = self.corridor_m / 111_320
        pad_lon = pad_lat / max(math.cos(mid_lat), 0.2)
        south, north = south - pad_lat, north + pad_lat
        west, east = west - pad_lon, east + pad_lon

        span = max(north - south, (east - west) * math.cos(mid_lat))
        step = max(self.min_step_deg, span / self.target_cells)
        while True:
            grid = self._grid(lines, south, west, north, east, step)
            if len(grid.active) <= self.max_active_nodes:
                return grid
            step *= 1.15

    def _grid(self, lines, south, west, north, east, step) -> CorridorGrid:
        # Snap the origin to the step so repeated searches reuse cached forecasts.
        south = math.floor(south / step) * step
        west = math.floor(west / step) * step
        rows = math.ceil((north - south) / step) + 1
        cols = math.ceil((east - west) / step) + 1
        reach = self.corridor_m + step * 111_320 * math.sqrt(2)
        active: list[int] = []
        for row in range(rows):
            lat = south + row * step
            for col in range(cols):
                p = LatLon(lat, west + col * step)
                if any(point_polyline_distance_m(p, line) <= reach for line in lines):
                    active.append(row * cols + col)
        return CorridorGrid(south, west, step, rows, cols, tuple(active))
