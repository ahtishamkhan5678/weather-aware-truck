"""Regular lat/lon grid that covers the trip corridor (used by the forecast heatmap)."""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass

from .entities import LatLon
from .geo import METERS_PER_MILE, cumulative_distances, simplify

M_PER_DEG = 111_320.0


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
    """Grid sized by the *corridor*, not the bounding box.

    The node budget (weather lookups) is spent only along the routes: the spacing is the
    finest multiple of ``quantum_deg`` whose corridor fits ``max_active_nodes``. A
    600-mile trip gets ~0.2° spacing; a 2,000-mile trip ~0.35° instead of the ~1° a
    bounding-box grid would need. A node is active within ``corridor_mi`` of a route plus
    ~¾ of a grid step, so bilinear interpolation inside the corridor always has data.
    Nodes are found by rasterising the routes (cost ∝ route length, not map area), and
    the lattice is aligned to the step so repeated searches reuse cached forecasts.
    """

    def __init__(
        self,
        corridor_mi: float = 30.0,
        min_step_deg: float = 0.2,
        quantum_deg: float = 0.05,
        max_active_nodes: int = 280,
    ) -> None:
        self.corridor_m = corridor_mi * METERS_PER_MILE
        self.min_step = min_step_deg
        self.quantum = quantum_deg
        self.budget = max_active_nodes

    def build(self, routes: Sequence[Sequence[LatLon]]) -> CorridorGrid:
        lines = [simplify(r, 1500.0) for r in routes if len(r) >= 2]
        if not lines:
            raise ValueError("At least one route is required")
        length = max(cumulative_distances(line)[-1] for line in lines)
        area = length * 2 * self.corridor_m * min(len(lines), 2)  # alternatives overlap
        step = max(self.min_step, math.sqrt(area / self.budget) / M_PER_DEG)
        step = self._quantise(step)
        while True:
            grid = self._grid(lines, step)
            if len(grid.active) <= self.budget:
                return grid
            step = self._quantise(step + self.quantum)

    def _quantise(self, step: float) -> float:
        return round(math.ceil(step / self.quantum - 1e-9) * self.quantum, 6)

    def _grid(self, lines: list[list[LatLon]], step: float) -> CorridorGrid:
        # Half a diagonal beyond the corridor is enough for every interior pixel to have
        # its 4 interpolation neighbours (the renderer also tolerates missing nodes).
        reach = self.corridor_m + step * M_PER_DEG * 0.75
        marked: set[tuple[int, int]] = set()
        for line in lines:
            for p in _densify(line, step * M_PER_DEG / 3):
                cos = max(math.cos(math.radians(p.lat)), 0.2)
                r_lat = math.ceil(reach / (step * M_PER_DEG))
                r_lon = math.ceil(reach / (step * M_PER_DEG * cos))
                row0, col0 = round(p.lat / step), round(p.lon / step)
                for dr in range(-r_lat, r_lat + 1):
                    for dc in range(-r_lon, r_lon + 1):
                        lat, lon = (row0 + dr) * step, (col0 + dc) * step
                        dy = (lat - p.lat) * M_PER_DEG
                        dx = (lon - p.lon) * M_PER_DEG * cos
                        if dx * dx + dy * dy <= reach * reach:
                            marked.add((row0 + dr, col0 + dc))
        rmin = min(r for r, _ in marked)
        cmin = min(c for _, c in marked)
        rows = max(r for r, _ in marked) - rmin + 1
        cols = max(c for _, c in marked) - cmin + 1
        active = tuple(sorted((r - rmin) * cols + (c - cmin) for r, c in marked))
        return CorridorGrid(round(rmin * step, 6), round(cmin * step, 6), step, rows, cols, active)


def _densify(line: Sequence[LatLon], spacing_m: float) -> list[LatLon]:
    out = [line[0]]
    for a, b in itertools.pairwise(line):
        d = math.hypot(
            (b.lat - a.lat) * M_PER_DEG,
            (b.lon - a.lon) * M_PER_DEG * math.cos(math.radians((a.lat + b.lat) / 2)),
        )
        n = max(1, math.ceil(d / spacing_m))
        out.extend(
            LatLon(a.lat + (b.lat - a.lat) * k / n, a.lon + (b.lon - a.lon) * k / n)
            for k in range(1, n + 1)
        )
    return out
