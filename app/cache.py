"""Optional Redis cache for redirect lookups.

Contract: every function degrades gracefully. If REDIS_URL is unset, the
client is missing, or any Redis call raises, callers get None and fall back
to the database — the API never fails because the cache is down.
"""
from __future__ import annotations

import logging

from .config import settings

log = logging.getLogger("snaplink.cache")
CACHE_TTL_SECONDS = 3600
_client = None


async def _get_client():
    global _client
    if not settings.REDIS_URL:
        return None
    try:
        import redis.asyncio as redis

        if _client is None:
            _client = redis.from_url(
                settings.REDIS_URL, socket_connect_timeout=2
            )
        await _client.ping()
        return _client
    except Exception as exc:  # noqa: BLE001 — cache must never break requests
        log.warning("redis unavailable, falling back to DB: %s", exc)
        return None


def _key(code: str) -> str:
    return f"snaplink:target:{code}"


async def get_target(code: str) -> str | None:
    client = await _get_client()
    if client is None:
        return None
    try:
        value = await client.get(_key(code))
        return value.decode() if isinstance(value, bytes) else value
    except Exception as exc:  # noqa: BLE001
        log.warning("redis get failed, falling back to DB: %s", exc)
        return None


async def set_target(code: str, target_url: str) -> None:
    client = await _get_client()
    if client is None:
        return
    try:
        await client.set(_key(code), target_url, ex=CACHE_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001
        log.warning("redis set failed (non-fatal): %s", exc)


async def invalidate_target(code: str) -> None:
    client = await _get_client()
    if client is None:
        return
    try:
        await client.delete(_key(code))
    except Exception as exc:  # noqa: BLE001
        log.warning("redis delete failed (non-fatal): %s", exc)


async def ping() -> str:
    """For /health: 'up', 'disabled' (no REDIS_URL), or 'down'."""
    if not settings.REDIS_URL:
        return "disabled"
    return "up" if await _get_client() is not None else "down"
