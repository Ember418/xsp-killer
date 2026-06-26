"""Optional Redis intel bus — no-op when Cemini is not present."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger("xsp_killer.intel")

_REDIS = None
_REDIS_TRIED = False


def _redis():
    global _REDIS, _REDIS_TRIED
    if _REDIS_TRIED:
        return _REDIS
    _REDIS_TRIED = True
    if os.getenv("XSP_KILLER_INTEL_DISABLED", "false").lower() in ("1", "true", "yes"):
        return None
    host = os.getenv("REDIS_HOST", "127.0.0.1")
    port = int(os.getenv("REDIS_PORT", "6379"))
    try:
        import redis

        _REDIS = redis.Redis(
            host=host, port=port, decode_responses=True, socket_connect_timeout=2
        )
        _REDIS.ping()
    except Exception as exc:
        logger.debug("Redis intel unavailable: %s", exc)
        _REDIS = None
    return _REDIS


class IntelPublisher:
    @staticmethod
    def publish(
        key: str,
        value: Any,
        source_system: str,
        confidence: float = 1.0,
        ttl: Optional[int] = None,
    ) -> None:
        r = _redis()
        if r is None:
            return
        payload = {
            "key": key,
            "value": value,
            "source_system": source_system,
            "confidence": confidence,
        }
        try:
            data = json.dumps(payload)
            if ttl:
                r.setex(key, ttl, data)
            else:
                r.set(key, data)
        except Exception as exc:
            logger.debug("intel publish failed %s: %s", key, exc)


class IntelReader:
    @staticmethod
    def read(key: str) -> Any:
        r = _redis()
        if r is None:
            return None
        try:
            raw = r.get(key)
            if not raw:
                return None
            data = json.loads(raw)
            return data.get("value") if isinstance(data, dict) else data
        except Exception as exc:
            logger.debug("intel read failed %s: %s", key, exc)
            return None
