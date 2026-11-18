"""Shared HTTP session: connection pooling, retries with back-off, sane timeouts."""

from __future__ import annotations

import threading
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "WeatherAwareTruckRouting/1.0 (+https://github.com/)"


def build_session(total_retries: int = 1, pool_size: int = 16) -> requests.Session:
    retry = Retry(
        total=total_retries,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=pool_size, pool_maxsize=pool_size)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return session


class HostThrottle:
    """Process-wide minimum interval between requests to one host (thread-safe).

    The public FOSSGIS Valhalla and OSRM demo servers allow at most 1 request/second per
    client; exceeding it gets the client IP blocked. Every adapter for such a host shares
    one throttle so concurrent user requests queue politely instead of tripping the ban.
    """

    def __init__(self, min_interval_s: float) -> None:
        self._interval = min_interval_s
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next)
            self._next = slot + self._interval
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)


class CircuitBreaker:
    """After a connection failure, skip the host for ``cooldown_s`` (fail fast → fallback)."""

    def __init__(self, cooldown_s: float = 300.0) -> None:
        self._cooldown = cooldown_s
        self._open_until = 0.0
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        return time.monotonic() < self._open_until

    def trip(self) -> None:
        with self._lock:
            self._open_until = time.monotonic() + self._cooldown

    def reset(self) -> None:
        with self._lock:
            self._open_until = 0.0
