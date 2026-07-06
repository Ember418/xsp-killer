"""Shadow volatility gate — logged only, never blocks paper entry.

GREEN/YELLOW/RED macro regime comes from ``intel:playbook_snapshot`` (not VIX
spike = buy). Moontower K147 (Jul 2026): naive VIX-spike sizing is shadow-only
here — halve-size signal when VIX ≥2× 20d median without downtrend confirm.
"""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("xsp_killer.vol_monitor")

DEFAULT_LOOKBACK_DAYS = 21
DEFAULT_RV_BLOCK_THRESHOLD = 0.28  # annualized; shadow-only
DEFAULT_VIX_MEDIAN_LOOKBACK = 20
DEFAULT_VIX_SPIKE_RATIO_HALVE = 2.0
DEFAULT_VIX_TREND_CONFIRM_DAYS = 5


@dataclass
class ShadowVolGate:
    spy_rv_annualized: float | None
    lookback_days: int
    rv_threshold: float
    shadow_would_block: bool
    reason: str
    enforcing: bool = False
    vix_level: float | None = None
    vix_median_20d: float | None = None
    vix_spike_ratio: float | None = None
    vix_trending_down: bool | None = None
    shadow_would_halve_size: bool = False
    shadow_premium_scale_multiplier: float = 1.0
    vix_shadow_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_vol_shadow_config(rules_path: Path | None) -> dict[str, Any]:
    cfg = {
        "lookback_days": DEFAULT_LOOKBACK_DAYS,
        "rv_threshold": DEFAULT_RV_BLOCK_THRESHOLD,
        "vix_median_lookback_days": DEFAULT_VIX_MEDIAN_LOOKBACK,
        "vix_spike_ratio_halve": DEFAULT_VIX_SPIKE_RATIO_HALVE,
        "vix_trend_confirm_days": DEFAULT_VIX_TREND_CONFIRM_DAYS,
    }
    if rules_path is None or not rules_path.is_file():
        return cfg
    try:
        import yaml

        data = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
        raw = data.get("vol_shadow") or {}
        if not isinstance(raw, dict):
            return cfg
        for key in cfg:
            if key in raw and raw[key] is not None:
                cfg[key] = raw[key]
    except Exception as exc:
        logger.warning("vol_shadow config load failed: %s", exc)
    return cfg


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


def _fetch_vix_closes(lookback_days: int) -> list[float]:
    try:
        import yfinance as yf

        period = "3mo" if lookback_days > 42 else "2mo"
        df = yf.Ticker("^VIX").history(period=period, timeout=10)
        if df.empty:
            return []
        closes = [float(v) for v in df["Close"].dropna().tolist()]
        return closes[-(lookback_days + 1) :]
    except Exception as exc:
        logger.warning("vol_monitor VIX fetch failed: %s", exc)
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


def evaluate_vix_spike_shadow(
    *,
    median_lookback_days: int = DEFAULT_VIX_MEDIAN_LOOKBACK,
    spike_ratio_halve: float = DEFAULT_VIX_SPIKE_RATIO_HALVE,
    trend_confirm_days: int = DEFAULT_VIX_TREND_CONFIRM_DAYS,
) -> dict[str, Any]:
    """Moontower shadow: flag spike-buy sizing when VIX doubled vs median."""
    need = median_lookback_days + trend_confirm_days + 1
    closes = _fetch_vix_closes(need)
    if len(closes) < median_lookback_days + 1:
        return {
            "vix_level": None,
            "vix_median_20d": None,
            "vix_spike_ratio": None,
            "vix_trending_down": None,
            "shadow_would_halve_size": False,
            "shadow_premium_scale_multiplier": 1.0,
            "vix_shadow_reason": "insufficient_vix_history",
        }

    current = closes[-1]
    prior_window = closes[-(median_lookback_days + 1) : -1]
    median_vix = statistics.median(prior_window)
    ratio = round(current / median_vix, 3) if median_vix > 0 else None
    trend_ref_idx = -(trend_confirm_days + 1)
    trend_ref = closes[trend_ref_idx] if len(closes) > trend_confirm_days else None
    trending_down = (
        bool(current < trend_ref) if trend_ref is not None else None
    )

    would_halve = (
        ratio is not None
        and ratio >= spike_ratio_halve
        and trending_down is not True
    )
    if ratio is None:
        vix_reason = "vix_median_unavailable"
    elif would_halve:
        vix_reason = (
            f"vix_spike_{ratio:.2f}x_gte_{spike_ratio_halve:.2f}x"
            "_no_downtrend_confirm"
        )
    elif ratio >= spike_ratio_halve and trending_down:
        vix_reason = (
            f"vix_spike_{ratio:.2f}x_with_downtrend_confirm_ok"
        )
    else:
        vix_reason = f"vix_spike_{ratio:.2f}x_below_halve_threshold"

    return {
        "vix_level": round(current, 3),
        "vix_median_20d": round(median_vix, 3),
        "vix_spike_ratio": ratio,
        "vix_trending_down": trending_down,
        "shadow_would_halve_size": would_halve,
        "shadow_premium_scale_multiplier": 0.5 if would_halve else 1.0,
        "vix_shadow_reason": vix_reason,
    }


def evaluate_shadow_vol_gate(
    *,
    lookback_days: int | None = None,
    rv_threshold: float | None = None,
    rules_path: Path | None = None,
) -> ShadowVolGate:
    """Shadow IV/VIX gates — records whether entry *would* block or halve size."""
    cfg = _load_vol_shadow_config(rules_path)
    lb = int(lookback_days if lookback_days is not None else cfg["lookback_days"])
    threshold = float(
        rv_threshold if rv_threshold is not None else cfg["rv_threshold"]
    )

    rv = spy_realized_vol_annualized(lookback_days=lb)
    if rv is None:
        rv_gate = ShadowVolGate(
            spy_rv_annualized=None,
            lookback_days=lb,
            rv_threshold=threshold,
            shadow_would_block=False,
            reason="insufficient_spy_history_for_rv",
        )
    else:
        would_block = rv >= threshold
        reason = (
            f"spy_rv_{rv:.2%}_gte_threshold_{threshold:.2%}"
            if would_block
            else f"spy_rv_{rv:.2%}_below_threshold_{threshold:.2%}"
        )
        rv_gate = ShadowVolGate(
            spy_rv_annualized=rv,
            lookback_days=lb,
            rv_threshold=threshold,
            shadow_would_block=would_block,
            reason=reason,
        )

    vix = evaluate_vix_spike_shadow(
        median_lookback_days=int(cfg["vix_median_lookback_days"]),
        spike_ratio_halve=float(cfg["vix_spike_ratio_halve"]),
        trend_confirm_days=int(cfg["vix_trend_confirm_days"]),
    )
    rv_gate.vix_level = vix["vix_level"]
    rv_gate.vix_median_20d = vix["vix_median_20d"]
    rv_gate.vix_spike_ratio = vix["vix_spike_ratio"]
    rv_gate.vix_trending_down = vix["vix_trending_down"]
    rv_gate.shadow_would_halve_size = bool(vix["shadow_would_halve_size"])
    rv_gate.shadow_premium_scale_multiplier = float(
        vix["shadow_premium_scale_multiplier"]
    )
    rv_gate.vix_shadow_reason = vix["vix_shadow_reason"]
    return rv_gate
