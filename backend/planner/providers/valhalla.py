"""Valhalla adapter — truck costing that honours the truck's gross weight."""

from __future__ import annotations

import logging
from collections.abc import Sequence

import requests

from ..domain.entities import LatLon, Route, TruckProfile
from ..domain.geo import METERS_PER_MILE, decode_polyline, haversine_m
from ._route_utils import distribute, main_roads, segment_lengths
from .base import NoRouteFound, ProviderError

log = logging.getLogger(__name__)
LB_TO_TONNES = 0.000453592
NO_PATH_CODES = {442, 443, 171, 170}


class ValhallaRoutingProvider:
    name = "valhalla"

    def __init__(
        self,
        session: requests.Session,
        base_url: str,
        *,
        timeout_s: float = 25.0,
        max_distance_km: float = 1150.0,
        top_speed_kph: float = 105.0,
    ) -> None:
        self._session = session
        self._url = base_url.rstrip("/") + "/route"
        self._timeout = timeout_s
        self._max_distance_m = max_distance_km * 1000
        self._top_speed_kph = top_speed_kph

    def routes(
        self,
        origin: LatLon,
        destination: LatLon,
        truck: TruckProfile,
        *,
        alternatives: int,
        via: Sequence[LatLon] = (),
    ) -> list[Route]:
        # Road distance is typically 1.2–1.4× straight line; avoid a guaranteed 400.
        if haversine_m(origin, destination) * 1.25 > self._max_distance_m:
            raise ProviderError(
                "Trip exceeds Valhalla distance limit", provider=self.name, retryable=False
            )
        locations = [{"lat": origin.lat, "lon": origin.lon, "type": "break"}]
        locations += [{"lat": p.lat, "lon": p.lon, "type": "through"} for p in via]
        locations.append({"lat": destination.lat, "lon": destination.lon, "type": "break"})
        body = {
            "locations": locations,
            "costing": "truck",
            "costing_options": {
                "truck": {
                    "weight": round(truck.gross_weight_lb * LB_TO_TONNES, 2),
                    "top_speed": self._top_speed_kph,
                }
            },
            "units": "miles",
            "directions_type": "maneuvers",
        }
        if alternatives and not via:  # Valhalla only supports alternates without vias
            body["alternates"] = alternatives
        try:
            resp = self._session.post(self._url, json=body, timeout=self._timeout)
        except requests.RequestException as exc:
            raise ProviderError(f"Valhalla unreachable: {exc}", provider=self.name) from exc
        data = _json(resp)
        if resp.status_code != 200:
            code = data.get("error_code")
            msg = data.get("error", resp.text[:200])
            if code in NO_PATH_CODES:
                raise NoRouteFound(f"No truck route found: {msg}", provider=self.name)
            raise ProviderError(
                f"Valhalla error {code}: {msg}",
                provider=self.name,
                retryable=resp.status_code >= 500,
            )
        trips = [data, *list(data.get("alternates") or [])]
        return [self._parse_trip(t["trip"]) for t in trips if "trip" in t]

    def _parse_trip(self, trip: dict) -> Route:
        points: list[LatLon] = []
        distances: list[float] = []
        durations: list[float] = []
        roads: list[tuple[str, float]] = []
        for leg in trip["legs"]:
            shape = decode_polyline(leg["shape"], 6)
            lengths = segment_lengths(shape)
            leg_dist = list(lengths)
            leg_dur = [0.0] * len(lengths)
            for m in leg.get("maneuvers", []):
                b, e = m.get("begin_shape_index", 0), m.get("end_shape_index", 0)
                if e <= b:
                    continue
                weights = lengths[b:e]
                leg_dur[b:e] = distribute(float(m.get("time", 0.0)), weights)
                leg_dist[b:e] = distribute(float(m.get("length", 0.0)) * METERS_PER_MILE, weights)
                if m.get("highway") and m.get("street_names"):
                    roads.append((m["street_names"][0], float(m.get("length", 0.0))))
            if points and shape and points[-1] == shape[0]:
                shape = shape[1:]
            elif points and shape:  # bridge legs with a zero-cost connector
                distances.append(haversine_m(points[-1], shape[0]))
                durations.append(0.0)
            points.extend(shape)
            distances.extend(leg_dist)
            durations.extend(leg_dur)
        if len(points) < 2:
            raise ProviderError("Valhalla returned an empty shape", provider=self.name)
        return Route(
            tuple(points), tuple(distances), tuple(durations), main_roads(roads), self.name
        )


def _json(resp: requests.Response) -> dict:
    try:
        return resp.json()
    except ValueError:
        return {}
