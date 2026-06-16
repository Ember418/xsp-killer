"""Tests for XSP Lane A Bollinger/VWAP TA signals (synthetic bars)."""

from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd

from xsp_killer.lane_a_ta import (
    TaRules,
    BarSnapshot,
    detect_bb_bounce_entry,
    detect_upper_bb_exit,
    enrich_bars,
    evaluate_ta_signals,
    morning_cut_suppressed,
)

ET = ZoneInfo("America/New_York")

RULES = TaRules(
    symbol="SPY",
    primary_timeframe="1h",
    confirm_timeframe="15m",
    bb_period=5,
    bb_std=2.0,
    require_vwap_reclaim=False,
    upper_bb_touch_tolerance_pct=0.002,
    suppress_morning_cut_dte_gte=30,
    entry_mode="close_window_and_bb",
    intraday_entry_enabled=True,
)


def _snap(close: float, low: float, high: float, bb_l: float, bb_m: float, bb_u: float, vwap: float) -> BarSnapshot:
    return BarSnapshot(
        timeframe="1h",
        ts="2026-06-16T10:00:00-04:00",
        close=close,
        high=high,
        low=low,
        vwap=vwap,
        bb_lower=bb_l,
        bb_mid=bb_m,
        bb_upper=bb_u,
    )


def test_bb_bounce_off_lower_band():
    prev = _snap(close=98, low=95, high=99, bb_l=96, bb_m=100, bb_u=104, vwap=99)
    curr = _snap(close=101, low=97, high=102, bb_l=96, bb_m=100, bb_u=104, vwap=99)
    ok, detail = detect_bb_bounce_entry(prev, curr, require_vwap=False)
    assert ok is True
    assert "lower" in detail


def test_bb_bounce_rejected_without_vwap_reclaim():
    prev = _snap(close=98, low=95, high=99, bb_l=96, bb_m=100, bb_u=104, vwap=102)
    curr = _snap(close=101, low=97, high=102, bb_l=96, bb_m=100, bb_u=104, vwap=102)
    ok, _ = detect_bb_bounce_entry(prev, curr, require_vwap=True)
    assert ok is False


def test_upper_bb_rejection():
    prev = _snap(close=103, low=102, high=104, bb_l=96, bb_m=100, bb_u=104, vwap=100)
    curr = _snap(close=103, low=102, high=105, bb_l=96, bb_m=100, bb_u=104, vwap=100)
    ok, detail = detect_upper_bb_exit(prev, curr, tolerance_pct=0.002)
    assert ok is True
    assert "rejection" in detail.lower()


def test_morning_cut_suppressed_at_30_dte():
    assert morning_cut_suppressed(30, RULES) is True
    assert morning_cut_suppressed(29, RULES) is False


def test_evaluate_ta_signals_synthetic():
    n = 30
    closes = [100.0] * n
    closes[-2] = 96.0
    closes[-1] = 101.0
    lows = closes.copy()
    lows[-2] = 94.0
    highs = [c + 1 for c in closes]
    highs[-1] = 102.0
    idx = pd.date_range("2026-06-10", periods=n, freq="1h", tz=ET)
    df = pd.DataFrame({"close": closes, "low": lows, "high": highs, "volume": [1_000_000] * n}, index=idx)
    enriched = enrich_bars(df, period=5, std=2.0)
    ta = evaluate_ta_signals(RULES, bars_primary=enriched, bars_confirm=enriched)
    assert ta.primary is not None
