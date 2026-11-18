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


class CacheSlotThrottle:
    """Distributed version of :class:`HostThrottle` for multi-instance hosting (Vercel).

    With Redis, each request must create a key that expires after ``min_interval_s``
    (``SET NX PX``). While the key lives, every other instance waits — so consecutive
    requests to the host are *always* at least the interval apart, deployment-wide.
    Without Redis (tests/local), it falls back to the cache's atomic ``add``.
    """

    def __init__(self, cache, key: str, min_interval_s: float, max_wait_s: float = 30.0):
        self._cache = cache
        self._key = f"thr:{key}"
        self._interval = min_interval_s
        self._max_wait = max_wait_s
        client_factory = getattr(getattr(cache, "_cache", None), "get_client", None)
        self._redis = client_factory(write=True) if callable(client_factory) else None

    def _claim(self) -> bool:
        if self._redis is not None:
            return bool(self._redis.set(self._key, 1, nx=True, px=int(self._interval * 1000)))
        return bool(self._cache.add(self._key, 1, timeout=self._interval))

    def wait(self) -> None:
        if self._interval <= 0:
            return
        deadline = time.monotonic() + self._max_wait
        while not self._claim():
            if time.monotonic() > deadline:
                raise TimeoutError(f"Throttle wait exceeded {self._max_wait}s for {self._key}")
            time.sleep(0.05)
