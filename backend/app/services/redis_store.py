"""
Redis-backed rolling window counters (optional — falls back to in-memory SlidingWindowState).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from app.config import settings

try:
    import redis

    _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    _redis_client.ping()
    REDIS_AVAILABLE = True
except Exception:
    _redis_client = None
    REDIS_AVAILABLE = False


def record_event(key: str, user_id: str, ts: datetime, ttl_sec: int = 3600) -> None:
    if not REDIS_AVAILABLE or _redis_client is None:
        return
    member = json.dumps({"u": user_id, "t": ts.isoformat()})
    pipe = _redis_client.pipeline()
    pipe.zadd(key, {member: ts.timestamp()})
    pipe.expire(key, ttl_sec)
    pipe.execute()


def count_since(key: str, since: datetime) -> int:
    if not REDIS_AVAILABLE or _redis_client is None:
        return 0
    return _redis_client.zcount(key, since.timestamp(), "+inf")


def distinct_users_since(key: str, since: datetime) -> int:
    if not REDIS_AVAILABLE or _redis_client is None:
        return 0
    members = _redis_client.zrangebyscore(key, since.timestamp(), "+inf")
    users = {json.loads(m)["u"] for m in members}
    return len(users)


def redis_status() -> dict[str, Any]:
    return {"available": REDIS_AVAILABLE, "url": settings.redis_url if REDIS_AVAILABLE else None}
