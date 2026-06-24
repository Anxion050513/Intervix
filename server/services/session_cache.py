"""Redis-backed interview session cache with anti-pattern protections.

Strategies implemented:
    - **Cache penetration**: short-TTL empty markers for non-existent sessions
    - **Cache breakdown**: SETNX-based mutex for hot-key concurrent loads
    - **Cache avalanche**: TTL ±20% random jitter to avoid simultaneous expiry
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

import redis.asyncio as aioredis

from server.config import settings

logger = logging.getLogger(__name__)

# Default session TTL: 2 hours
DEFAULT_SESSION_TTL = 7200

# Empty-result TTL: 30 seconds (penetration guard)
EMPTY_TTL = 30

# Avalanche jitter: ±20% random offset on base TTL
AVALANCHE_JITTER = 0.2


def _jittered_ttl(base_ttl: int = DEFAULT_SESSION_TTL) -> int:
    """Return *base_ttl* ± up to 20% random offset."""
    offset = int(base_ttl * AVALANCHE_JITTER * (random.random() * 2 - 1))
    return max(base_ttl + offset, 60)  # floor at 1 minute


class SessionCache:
    """Async Redis cache for interview session state.

    Usage::

        cache = await SessionCache.create()
        await cache.set("sess_123", {"state": "warmup", ...})
        data = await cache.get("sess_123")       # → dict | None
        await cache.delete("sess_123")
    """

    _instance: SessionCache | None = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(self, redis_client: aioredis.Redis):
        self._redis = redis_client

    # ── Singleton factory ───────────────────────────────────────────

    @classmethod
    async def create(cls) -> SessionCache:
        """Get or create the singleton SessionCache (lazy Redis connect)."""
        if cls._instance is not None:
            return cls._instance

        async with cls._lock:
            if cls._instance is not None:
                return cls._instance

            try:
                # protocol=2 (RESP2) avoids the HELLO command that fails on
                # Redis < 6.0 or password-protected servers where RESP3
                # negotiation runs before AUTH.
                client = aioredis.from_url(
                    settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=3,
                    protocol=2,
                )
                await client.ping()
                logger.info("SessionCache connected to Redis (RESP2): %s", settings.redis_url)
            except Exception as exc:
                logger.warning(
                    "Redis unavailable (%s) — falling back to in-memory-only mode", exc
                )
                client = None  # type: ignore[assignment]

            cls._instance = cls(client)
            return cls._instance

    @property
    def enabled(self) -> bool:
        return self._redis is not None

    # ── Public API ──────────────────────────────────────────────────

    def _session_key(self, session_id: str) -> str:
        return f"interview:session:{session_id}"

    def _empty_key(self, session_id: str) -> str:
        """Marker key for non-existent sessions (penetration guard)."""
        return f"interview:empty:{session_id}"

    async def get(self, session_id: str) -> dict | None:
        """Retrieve session data from Redis.

        Returns ``None`` when the session does not exist or Redis is unavailable.
        """
        if not self.enabled:
            return None

        key = self._session_key(session_id)

        try:
            # Check for empty marker first (penetration guard)
            empty = await self._redis.get(self._empty_key(session_id))
            if empty is not None:
                logger.debug("Session %s: empty marker hit", session_id)
                return None

            raw = await self._redis.get(key)
            if raw is None:
                return None

            return json.loads(raw)
        except Exception as exc:
            logger.warning("SessionCache.get(%s) failed: %s", session_id, exc)
            return None

    async def set(
        self,
        session_id: str,
        data: dict,
        ttl: int | None = None,
    ) -> bool:
        """Store session data in Redis with jittered TTL (avalanche guard).

        Returns ``True`` on success.
        """
        if not self.enabled:
            return False

        key = self._session_key(session_id)
        effective_ttl = ttl if ttl is not None else _jittered_ttl()

        try:
            raw = json.dumps(data, ensure_ascii=False, default=str)
            await self._redis.setex(key, effective_ttl, raw)
            # Clear any empty marker that may exist
            await self._redis.delete(self._empty_key(session_id))
            return True
        except Exception as exc:
            logger.warning("SessionCache.set(%s) failed: %s", session_id, exc)
            return False

    async def delete(self, session_id: str) -> bool:
        """Remove session data from Redis."""
        if not self.enabled:
            return False

        key = self._session_key(session_id)
        try:
            await self._redis.delete(key, self._empty_key(session_id))
            return True
        except Exception as exc:
            logger.warning("SessionCache.delete(%s) failed: %s", session_id, exc)
            return False

    async def mark_empty(self, session_id: str):
        """Mark a session ID as non-existent (penetration guard).

        Subsequent ``get()`` calls for this ID will return ``None`` without
        hitting the main key, for EMPTY_TTL seconds.
        """
        if not self.enabled:
            return

        try:
            await self._redis.setex(
                self._empty_key(session_id),
                EMPTY_TTL,
                "1",
            )
        except Exception as exc:
            logger.debug("SessionCache.mark_empty(%s) failed: %s", session_id, exc)

    async def extend_ttl(self, session_id: str, ttl: int | None = None):
        """Refresh the TTL on a session (called on each interaction)."""
        if not self.enabled:
            return

        key = self._session_key(session_id)
        effective_ttl = ttl if ttl is not None else _jittered_ttl()
        try:
            await self._redis.expire(key, effective_ttl)
        except Exception:
            pass

    # ── Hot-key mutex (cache breakdown guard) ────────────────────────

    async def load_or_compute(
        self,
        session_id: str,
        factory: callable,
        ttl: int | None = None,
    ) -> dict | None:
        """Get session from cache, or call *factory* to build and cache it.

        Uses a Redis SETNX lock so only one caller runs *factory* when the
        key is cold (breakdown guard).
        """
        # Fast path: already cached
        data = await self.get(session_id)
        if data is not None:
            return data

        # Check empty marker (penetration guard)
        if self.enabled:
            try:
                empty = await self._redis.get(self._empty_key(session_id))
                if empty is not None:
                    return None
            except Exception:
                pass

        # Try to acquire hot-key mutex
        lock_key = f"interview:lock:{session_id}"
        acquired = False
        if self.enabled:
            try:
                acquired = await self._redis.setnx(lock_key, "1")
                if acquired:
                    await self._redis.expire(lock_key, 5)  # lock TTL = 5s
            except Exception:
                pass

        if not acquired:
            # Another caller is building — wait briefly and retry
            await asyncio.sleep(0.1)
            return await self.get(session_id)

        try:
            # Double-check (another caller may have finished)
            data = await self.get(session_id)
            if data is not None:
                return data

            # Build
            if asyncio.iscoroutinefunction(factory):
                data = await factory()
            else:
                data = factory()

            if data is not None:
                await self.set(session_id, data, ttl=ttl)
            else:
                await self.mark_empty(session_id)

            return data
        finally:
            if self.enabled and acquired:
                try:
                    await self._redis.delete(lock_key)
                except Exception:
                    pass

    # ── Health ──────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Check Redis connectivity."""
        if not self.enabled:
            return False
        try:
            return await self._redis.ping() == True  # noqa: E712
        except Exception:
            return False

    async def close(self):
        """Close the Redis connection (for graceful shutdown)."""
        if self.enabled:
            try:
                await self._redis.aclose()  # type: ignore[union-attr]
            except Exception:
                pass
            SessionCache._instance = None
