"""Input validation, rate limiting and response hardening."""
from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
ROOM_NAME_RE = re.compile(r"[^A-Za-z0-9 _\-.!?'&]")
ROOM_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,16}$")
PASSWORD_MIN, PASSWORD_MAX = 8, 128


def valid_username(value: object) -> bool:
    return isinstance(value, str) and bool(USERNAME_RE.fullmatch(value))


def valid_password(value: object) -> bool:
    return isinstance(value, str) and PASSWORD_MIN <= len(value) <= PASSWORD_MAX


def clean_room_name(value: object, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    cleaned = " ".join(ROOM_NAME_RE.sub("", value).split())[:40]
    return cleaned or fallback


def valid_room_id(value: object) -> bool:
    return isinstance(value, str) and bool(ROOM_ID_RE.fullmatch(value))


def short_str(value: object, limit: int = 64) -> str | None:
    return value if isinstance(value, str) and 0 < len(value) <= limit else None


class RateLimiter:
    """Sliding-window limiter kept in memory. Good enough for a single process."""

    def __init__(self, limit: int, window: float):
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Record an attempt. Returns False when the key is over its limit."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            if len(self._hits) > 10_000:
                self._prune(now)
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def _prune(self, now: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
            del self._hits[key]


CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data:",
        "connect-src 'self' ws: wss:",
        "manifest-src 'self'",
        "worker-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ]
)


def apply_security_headers(response):
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    return response
