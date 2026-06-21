"""In-process SPY options chain cache — one fetch per cron / variant batch."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

logger = logging.getLogger("xsp_killer.chain_cache")

_TTL_SEC = 300.0
_expirations: tuple[str, ...] | None = None
_expirations_ts: float = 0.0
_chains: dict[str, tuple[Any, float]] = {}


def clear_chain_cache() -> None:
    global _expirations, _expirations_ts
    _expirations = None
    _expirations_ts = 0.0
    _chains.clear()


def get_spy_expirations(*, force: bool = False) -> tuple[str, ...] | None:
    global _expirations, _expirations_ts
    now = time.monotonic()
    if not force and _expirations is not None and (now - _expirations_ts) < _TTL_SEC:
        return _expirations
    try:
        import yfinance as yf

        raw = yf.Ticker("SPY").options
        _expirations = tuple(str(x) for x in (raw or ()))
        _expirations_ts = now
        return _expirations
    except Exception as exc:
        logger.warning("SPY expirations fetch failed: %s", exc)
        return _expirations


def get_spy_option_chain(expiration: date, *, force: bool = False) -> Any | None:
    key = expiration.isoformat()
    now = time.monotonic()
    cached = _chains.get(key)
    if not force and cached is not None and (now - cached[1]) < _TTL_SEC:
        return cached[0]
    try:
        import yfinance as yf

        chain = yf.Ticker("SPY").option_chain(key)
        _chains[key] = (chain, now)
        return chain
    except Exception as exc:
        logger.warning("SPY option chain failed %s: %s", key, exc)
        if cached is not None:
            return cached[0]
        return None
