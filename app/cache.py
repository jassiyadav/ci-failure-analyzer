"""Fingerprint -> analysis cache. Redis if REDIS_URL is set, in-memory otherwise."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class Cache:
    def __init__(self, redis_url: str = "") -> None:
        self._mem: dict[str, str] = {}
        self._redis = None
        if redis_url:
            import redis.asyncio as redis

            self._redis = redis.from_url(redis_url, decode_responses=True)

    async def get(self, key: str) -> str | None:
        if self._redis is not None:
            try:
                return await self._redis.get(key)
            except Exception:  # cache must never break the analysis
                log.warning("redis get failed, falling back to memory", exc_info=True)
        return self._mem.get(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        if self._redis is not None:
            try:
                await self._redis.set(key, value, ex=ttl)
                return
            except Exception:
                log.warning("redis set failed, falling back to memory", exc_info=True)
        self._mem[key] = value
