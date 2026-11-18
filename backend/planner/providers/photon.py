"""Photon (OpenStreetMap) geocoder — designed for type-ahead search, no API key."""

from __future__ import annotations

import requests

from ..domain.entities import LatLon, Place
from .base import ProviderError


class PhotonGeocoder:
    name = "photon"

    def __init__(self, session: requests.Session, base_url: str, *, timeout_s: float = 8.0):
        self._session = session
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    def search(self, query: str, *, limit: int = 5, bias: LatLon | None = None) -> list[Place]:
        params: dict[str, str | int | float] = {"q": query, "limit": limit, "lang": "en"}
        if bias:
            params.update({"lat": bias.lat, "lon": bias.lon})
        return self._features(self._get("/api/", params))

    def reverse(self, point: LatLon) -> Place | None:
        places = self._features(self._get("/reverse", {"lat": point.lat, "lon": point.lon}))
        return places[0] if places else None

    def _get(self, path: str, params: dict) -> dict:
        try:
            resp = self._session.get(self._base + path, params=params, timeout=self._timeout)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError(f"Geocoding failed: {exc}", provider=self.name) from exc

    @staticmethod
    def _features(data: dict) -> list[Place]:
        places: list[Place] = []
        seen: set[str] = set()
        for f in data.get("features", []):
            lon, lat = f["geometry"]["coordinates"]
            label = _label(f.get("properties", {}))
            if label and label not in seen:
                seen.add(label)
                places.append(Place(label, LatLon(lat, lon)))
        return places


def _label(p: dict) -> str:
    name = p.get("name") or " ".join(x for x in (p.get("housenumber"), p.get("street")) if x)
    parts = [
        name,
        p.get("city") if p.get("city") != name else None,
        p.get("state"),
        p.get("countrycode", "").upper() or None,
    ]
    return ", ".join(x for x in parts if x)
