"""Geometry helpers on WGS84 coordinates (small-distance approximations where noted)."""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence

from .entities import LatLon

EARTH_RADIUS_M = 6_371_008.8
METERS_PER_MILE = 1609.344


def haversine_m(a: LatLon, b: LatLon) -> float:
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat = lat2 - lat1
    dlon = math.radians(b.lon - a.lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def cumulative_distances(points: Sequence[LatLon]) -> list[float]:
    """Cumulative distance in metres at every vertex (first = 0)."""
    out = [0.0]
    for prev, cur in itertools.pairwise(points):
        out.append(out[-1] + haversine_m(prev, cur))
    return out


def lerp_point(a: LatLon, b: LatLon, t: float) -> LatLon:
    return LatLon(a.lat + (b.lat - a.lat) * t, a.lon + (b.lon - a.lon) * t)


def destination_point(origin: LatLon, bearing_deg: float, distance_m: float) -> LatLon:
    """Point reached by travelling `distance_m` from `origin` on an initial bearing."""
    delta = distance_m / EARTH_RADIUS_M
    theta = math.radians(bearing_deg)
    lat1, lon1 = math.radians(origin.lat), math.radians(origin.lon)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(delta) + math.cos(lat1) * math.sin(delta) * math.cos(theta)
    )
    lon2 = lon1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(lat1),
        math.cos(delta) - math.sin(lat1) * math.sin(lat2),
    )
    return LatLon(math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180)


def initial_bearing_deg(a: LatLon, b: LatLon) -> float:
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlon = math.radians(b.lon - a.lon)
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _to_xy(p: LatLon, ref_lat_rad: float) -> tuple[float, float]:
    """Local equirectangular projection in metres (fine for distances < a few hundred km)."""
    return (
        math.radians(p.lon) * math.cos(ref_lat_rad) * EARTH_RADIUS_M,
        math.radians(p.lat) * EARTH_RADIUS_M,
    )


def point_segment_distance_m(p: LatLon, a: LatLon, b: LatLon) -> float:
    ref = math.radians(p.lat)
    px, py = _to_xy(p, ref)
    ax, ay = _to_xy(a, ref)
    bx, by = _to_xy(b, ref)
    dx, dy = bx - ax, by - ay
    seg_len2 = dx * dx + dy * dy
    t = 0.0 if seg_len2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def point_polyline_distance_m(p: LatLon, line: Sequence[LatLon]) -> float:
    if len(line) == 1:
        return haversine_m(p, line[0])
    return min(point_segment_distance_m(p, a, b) for a, b in itertools.pairwise(line))


def simplify(points: Sequence[LatLon], tolerance_m: float) -> list[LatLon]:
    """Iterative Douglas–Peucker simplification (keeps first & last vertex)."""
    n = len(points)
    if n <= 2:
        return list(points)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        start, end = stack.pop()
        max_d, idx = 0.0, -1
        for i in range(start + 1, end):
            d = point_segment_distance_m(points[i], points[start], points[end])
            if d > max_d:
                max_d, idx = d, i
        if idx != -1 and max_d > tolerance_m:
            keep[idx] = True
            stack.append((start, idx))
            stack.append((idx, end))
    return [p for p, k in zip(points, keep, strict=True) if k]


def decode_polyline(encoded: str, precision: int = 6) -> list[LatLon]:
    """Decode a Google-style encoded polyline (Valhalla uses precision 6)."""
    factor = 10**precision
    coords: list[LatLon] = []
    index = lat = lon = 0
    length = len(encoded)
    while index < length:
        for is_lat in (True, False):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_lat:
                lat += delta
            else:
                lon += delta
        coords.append(LatLon(lat / factor, lon / factor))
    return coords


def bounding_box(points: Sequence[LatLon]) -> tuple[float, float, float, float]:
    """(south, west, north, east)."""
    lats = [p.lat for p in points]
    lons = [p.lon for p in points]
    return min(lats), min(lons), max(lats), max(lons)
