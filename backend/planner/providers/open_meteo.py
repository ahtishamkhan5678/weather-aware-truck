"""Open-Meteo hourly forecast adapter (multi-location requests, concurrent chunks)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import requests

from ..domain.entities import LatLon
from ..domain.weather import ForecastSeries
from .base import ProviderError

log = logging.getLogger(__name__)
HOURLY_VARS = "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall"


class OpenMeteoWeatherProvider:
    name = "open-meteo"

    def __init__(
        self,
        session: requests.Session,
        base_url: str,
        *,
        api_key: str = "",
        timeout_s: float = 25.0,
        chunk_size: int = 100,
        max_workers: int = 4,
    ) -> None:
        self._session = session
        base = base_url.rstrip("/")
        if api_key and "customer-" not in base:
            base = base.replace("://api.", "://customer-api.")
        self._url = base + "/v1/forecast"
        self._api_key = api_key
        self._timeout = timeout_s
        self._chunk = chunk_size
        self._workers = max_workers

    def hourly(
        self, points: Sequence[LatLon], start: datetime, end: datetime
    ) -> list[ForecastSeries]:
        if not points:
            return []
        chunks = [points[i : i + self._chunk] for i in range(0, len(points), self._chunk)]
        with ThreadPoolExecutor(max_workers=min(self._workers, len(chunks))) as pool:
            results = list(pool.map(lambda c: self._fetch(c, start, end), chunks))
        return [series for chunk in results for series in chunk]

    def _fetch(
        self, points: Sequence[LatLon], start: datetime, end: datetime
    ) -> list[ForecastSeries]:
        params = {
            "latitude": ",".join(f"{p.lat:.4f}" for p in points),
            "longitude": ",".join(f"{p.lon:.4f}" for p in points),
            "hourly": HOURLY_VARS,
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",  # rain *and* snowfall in inches
            "timezone": "GMT",
            "start_hour": start.astimezone(UTC).strftime("%Y-%m-%dT%H:00"),
            "end_hour": end.astimezone(UTC).strftime("%Y-%m-%dT%H:00"),
        }
        if self._api_key:
            params["apikey"] = self._api_key
        try:
            resp = self._session.get(self._url, params=params, timeout=self._timeout)
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError(f"Weather service unreachable: {exc}", provider=self.name) from exc
        if resp.status_code != 200 or (isinstance(data, dict) and data.get("error")):
            reason = (
                data.get("reason", resp.status_code) if isinstance(data, dict) else resp.status_code
            )
            raise ProviderError(
                f"Weather service error: {reason}",
                provider=self.name,
                retryable=resp.status_code in (429, 500, 502, 503),
            )
        items = data if isinstance(data, list) else [data]
        if len(items) != len(points):
            raise ProviderError("Weather response size mismatch", provider=self.name)
        return [self._parse(p, item) for p, item in zip(points, items, strict=True)]

    @staticmethod
    def _parse(point: LatLon, item: dict) -> ForecastSeries:
        h = item["hourly"]
        first = datetime.fromisoformat(h["time"][0]).replace(tzinfo=UTC)

        def col(name: str) -> tuple[float, ...]:
            return tuple(float(v) if v is not None else 0.0 for v in h[name])

        rain = tuple(r + s for r, s in zip(col("rain"), col("showers"), strict=True))
        return ForecastSeries(
            point=point,
            start=first,
            wind_mph=col("wind_speed_10m"),
            gust_mph=col("wind_gusts_10m"),
            rain_in=rain,
            snow_in=col("snowfall"),
        )
