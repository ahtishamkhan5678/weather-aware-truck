"""OSRM adapter (car profile — the truck ETA model corrects speeds afterwards)."""

from __future__ import annotations

from collections.abc import Sequence

import requests

from ..domain.entities import LatLon, Route, TruckProfile
from ._route_utils import main_roads
from .base import NoRouteFound, ProviderError
from .http import HostThrottle


class OsrmRoutingProvider:
    name = "osrm"

    def __init__(
        self,
        session: requests.Session,
        base_url: str,
        *,
        timeout_s: float = 25.0,
        throttle: HostThrottle | None = None,
    ):
        self._session = session
        self._throttle = throttle
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    def routes(
        self,
        origin: LatLon,
        destination: LatLon,
        truck: TruckProfile,
        *,
        alternatives: int,
        via: Sequence[LatLon] = (),
    ) -> list[Route]:
        coords = ";".join(f"{p.lon:.6f},{p.lat:.6f}" for p in (origin, *via, destination))
        params = {
            "alternatives": str(alternatives) if alternatives and not via else "false",
            "overview": "full",
            "geometries": "geojson",
            "annotations": "distance,duration",
            "steps": "true",
        }
        if self._throttle:
            self._throttle.wait()
        try:
            resp = self._session.get(
                f"{self._base}/route/v1/driving/{coords}", params=params, timeout=self._timeout
            )
        except requests.RequestException as exc:
            raise ProviderError(f"OSRM unreachable: {exc}", provider=self.name) from exc
        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError(
                f"OSRM returned HTTP {resp.status_code}", provider=self.name
            ) from exc
        code = data.get("code")
        if code in {"NoRoute", "NoSegment"}:
            raise NoRouteFound(data.get("message", "No route found"), provider=self.name)
        if code != "Ok":
            raise ProviderError(
                f"OSRM error: {code} {data.get('message', '')}",
                provider=self.name,
                retryable=resp.status_code >= 500,
            )
        return [self._parse(r) for r in data.get("routes", [])]

    def _parse(self, r: dict) -> Route:
        points = tuple(LatLon(lat, lon) for lon, lat in r["geometry"]["coordinates"])
        distances: list[float] = []
        durations: list[float] = []
        roads: list[tuple[str, float]] = []
        for leg in r["legs"]:
            ann = leg.get("annotation") or {}
            distances.extend(float(x) for x in ann.get("distance", []))
            durations.extend(float(x) for x in ann.get("duration", []))
            for step in leg.get("steps", []):
                name = step.get("ref") or step.get("name") or ""
                roads.append((name.split(";")[0].strip(), float(step.get("distance", 0))))
        n = len(points) - 1
        if len(distances) != n or len(durations) != n:
            # Geometry/annotation mismatch (should not happen) → spread totals by length.
            from ._route_utils import distribute, segment_lengths

            lengths = segment_lengths(points)
            distances = distribute(float(r["distance"]), lengths)
            durations = distribute(float(r["duration"]), lengths)
        return Route(points, tuple(distances), tuple(durations), main_roads(roads), self.name)
