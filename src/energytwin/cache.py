from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode


REDIS_URL_ENV = "ENERGYTWIN_REDIS_URL"
REDIS_TTL_ENV = "ENERGYTWIN_REDIS_TTL_SECONDS"
DEFAULT_CACHE_TTL_SECONDS = 60
CACHEABLE_API_PATHS = {
    "/api/forecast",
    "/api/simulate",
    "/api/optimize",
    "/api/model-status",
    "/api/forecast-evaluation",
    "/api/data-health",
    "/api/district-forecast",
    "/api/district-optimize",
}


def api_cache_key(path: str, query: dict[str, list[str]]) -> str | None:
    if path not in CACHEABLE_API_PATHS or not redis_enabled():
        return None
    parts: list[tuple[str, str]] = []
    for key in sorted(query):
        for value in sorted(query[key]):
            parts.append((key, value))
    suffix = urlencode(parts)
    return f"energytwin:v1:{path}?{suffix}"


def cache_get_json(key: str | None) -> dict[str, Any] | None:
    if not key:
        return None
    client = _redis_client()
    if client is None:
        return None
    raw = client.get(key)
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def cache_set_json(key: str | None, payload: dict[str, Any]) -> None:
    if not key:
        return
    client = _redis_client()
    if client is None:
        return
    client.setex(key, _cache_ttl_seconds(), json.dumps(payload, separators=(",", ":"), sort_keys=True))


def cache_status() -> dict[str, str | int | bool]:
    url = os.getenv(REDIS_URL_ENV)
    return {
        "enabled": bool(url),
        "backend": "redis" if url else "none",
        "target": _redacted_redis_url(url) if url else "",
        "ttl_seconds": _cache_ttl_seconds(),
    }


def redis_enabled() -> bool:
    return bool(os.getenv(REDIS_URL_ENV))


def _cache_ttl_seconds() -> int:
    raw = os.getenv(REDIS_TTL_ENV, str(DEFAULT_CACHE_TTL_SECONDS))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_CACHE_TTL_SECONDS


def _redis_client():
    url = os.getenv(REDIS_URL_ENV)
    if not url:
        return None
    try:
        import redis  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Redis cache requires the optional production dependency: "
            "python3 -m pip install redis"
        ) from exc
    return redis.Redis.from_url(url)


def _redacted_redis_url(url: str | None) -> str:
    if not url:
        return ""
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    host = rest.split("@", 1)[1]
    return f"{scheme}://***@{host}"
