"""Hourly forecast series with ETA-aware lookups."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .entities import LatLon, WeatherSample


@dataclass(frozen=True, slots=True)
class ForecastSeries:
    """Hourly forecast for one location. ``start`` is a UTC whole hour; values are hourly.

    Open-Meteo semantics: wind is an *instantaneous* value at the timestamp, while rain and
    snowfall are *accumulations over the preceding hour* (i.e. an in/hr rate for the hour
    ending at the timestamp).
    """

    point: LatLon
    start: datetime
    wind_mph: tuple[float, ...]
    gust_mph: tuple[float, ...]
    rain_in: tuple[float, ...]
    snow_in: tuple[float, ...]

    @property
    def hours(self) -> int:
        return len(self.wind_mph)

    @property
    def end(self) -> datetime:
        return self.start + timedelta(hours=self.hours - 1)

    def covers(self, when: datetime) -> bool:
        return self.start <= when <= self.end

    def _offset(self, when: datetime) -> float:
        return (when.astimezone(UTC) - self.start).total_seconds() / 3600.0

    def at(self, when: datetime) -> WeatherSample:
        """Weather the truck experiences at ``when``.

        * wind/gust — linear interpolation between the surrounding hours
        * rain/snow — the hourly bucket whose window (T-1h, T] contains ``when``
        """
        x = min(max(self._offset(when), 0.0), self.hours - 1)
        i0 = math.floor(x)
        i1 = min(i0 + 1, self.hours - 1)
        frac = x - i0
        bucket = min(math.ceil(x), self.hours - 1)

        def lerp(values: tuple[float, ...]) -> float:
            return values[i0] + (values[i1] - values[i0]) * frac

        return WeatherSample(
            wind_mph=lerp(self.wind_mph),
            gust_mph=lerp(self.gust_mph),
            rain_in_hr=self.rain_in[bucket],
            snow_in_hr=self.snow_in[bucket],
            forecast_time=self.start + timedelta(hours=bucket),
        )

    def hour(self, index: int) -> WeatherSample:
        return WeatherSample(
            wind_mph=self.wind_mph[index],
            gust_mph=self.gust_mph[index],
            rain_in_hr=self.rain_in[index],
            snow_in_hr=self.snow_in[index],
            forecast_time=self.start + timedelta(hours=index),
        )
