"""Helpers shared by routing adapters."""

from __future__ import annotations

import itertools
from collections import Counter
from collections.abc import Iterable, Sequence

from ..domain.entities import LatLon
from ..domain.geo import haversine_m


def segment_lengths(points: Sequence[LatLon]) -> list[float]:
    return [haversine_m(a, b) for a, b in itertools.pairwise(points)]


def distribute(total: float, weights: Sequence[float]) -> list[float]:
    """Split ``total`` proportionally to ``weights`` (evenly if all weights are zero)."""
    s = sum(weights)
    if not weights:
        return []
    if s <= 0:
        return [total / len(weights)] * len(weights)
    return [total * w / s for w in weights]


def main_roads(named_lengths: Iterable[tuple[str, float]], limit: int = 3) -> tuple[str, ...]:
    counter: Counter[str] = Counter()
    for name, length in named_lengths:
        if name:
            counter[name] += length
    return tuple(name for name, _ in counter.most_common(limit))
