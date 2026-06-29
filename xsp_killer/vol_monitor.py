"""Shadow volatility gate — logged only, never blocks paper entry."""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger("xsp_killer.vol_monitor")

DEFAULT_LOOKBACK_DAYS = 21
DEFAULT_RV_BLOCK_THRESHOLD = 0.28  # annualized; shadow-only


@dataclass
class ShadowVolGate:
    spy_rv_annualized: float | None
    lookback_days: int
    rv_threshold: float
    shadow_would_block: bool
    reason: str
    enforcing: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _fetch_spy_closes(lookback_days: int) -> list[float]:
    try:
        import yfinance as yf

        period = "3mo" if lookback_days > 42 else "2mo"
        df = yf.Ticker("SPY").history(period=period, timeout=10)
        if df.empty:
            return []
        closes = [float(v) for v in df["Close"].dropna().tolist()]
        return closes[-(lookback_days + 1) :]
    except Exception as exc:
        logger.warning("vol_monitor SPY fetch failed: %s", exc)
        return []


def spy_realized_vol_annualized(*, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> float | None:
    """Close-to-close log-return realized vol, annualized."""
    closes = _fetch_spy_closes(lookback_days)
    if len(closes) < lookback_days + 1:
        return None
    log_rets: list[float] = []
    for i in range(1, len(closes)):
        if closes[i - 1] <= 0 or closes[i] <= 0:
            continue
        log_rets.append(math.log(closes[i] / closes[i - 1]))
    if len(log_rets) < max(5, lookback_days // 2):
        return None
    mean = sum(log_rets) / len(log_rets)
    var = sum((r - mean) ** 2 for r in log_rets) / max(1, len(log_rets) - 1)
    return round(math.sqrt(var * 252), 4)


def evaluate_shadow_vol_gate(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    rv_threshold: float = DEFAULT_RV_BLOCK_THRESHOLD,
) -> ShadowVolGate:
    """Shadow IV/regime gate — records whether entry *would* block on high RV."""
    rv = spy_realized_vol_annualized(lookback_days=lookback_days)
    if rv is None:
        return ShadowVolGate(
            spy_rv_annualized=None,
            lookback_days=lookback_days,
            rv_threshold=rv_threshold,
            shadow_would_block=False,
            reason="insufficient_spy_history_for_rv",
        )
    would_block = rv >= rv_threshold
    reason = (
        f"spy_rv_{rv:.2%}_gte_threshold_{rv_threshold:.2%}"
        if would_block
        else f"spy_rv_{rv:.2%}_below_threshold_{rv_threshold:.2%}"
    )
    return ShadowVolGate(
        spy_rv_annualized=rv,
        lookback_days=lookback_days,
        rv_threshold=rv_threshold,
        shadow_would_block=would_block,
        reason=reason,
    )
