"""Tests for XSP Lane A Bollinger/VWAP TA signals (synthetic bars)."""

from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from xsp_killer.lane_a_ta import (
    TaRules,
    BarSnapshot,
    compute_vwap,
    detect_bb_bounce_entry,
    detect_upper_bb_exit,
    enrich_bars,
    evaluate_ta_signals,
    evaluate_timeframe,
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
    intraday_entry_enabled=False,
    confirm_optional=True,
)


def _snap(close: float, low: float, high: float, bb_l: float, bb_m: float, bb_u: float, vwap: float, *, open_: float | None = None) -> BarSnapshot:
    return BarSnapshot(
        timeframe="1h",
        ts="2026-06-16T10:00:00-04:00",
        open=open_ if open_ is not None else close,
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
    prev = _snap(close=103, low=102, high=104, bb_l=96, bb_m=100, bb_u=104, vwap=100, open_=102)
    curr = _snap(close=102, low=101, high=105, bb_l=96, bb_m=100, bb_u=104, vwap=100, open_=104)
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


def test_upper_bb_rejection_uses_close_not_missing_open():
    prev = _snap(close=103, low=102, high=104, bb_l=96, bb_m=100, bb_u=104, vwap=100, open_=103)
    curr = _snap(close=102, low=101, high=105, bb_l=96, bb_m=100, bb_u=104, vwap=100, open_=104)
    ok, _ = detect_upper_bb_exit(prev, curr, tolerance_pct=0.002)
    assert ok is True


def test_compute_vwap_zero_volume_session_start():
    idx = pd.date_range("2026-06-23 09:30", periods=3, freq="15min", tz=ET)
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [0, 0, 1_000_000],
        },
        index=idx,
    )
    vwap = compute_vwap(df)
    assert not vwap.isna().any()
    assert vwap.iloc[0] == pytest.approx((99.0 + 101.0 + 100.5) / 3.0)


def test_evaluate_timeframe_with_zero_volume_session_start():
    n = 30
    closes = [100.0 + (i * 0.1) for i in range(n)]
    idx = pd.date_range("2026-06-23 09:30", periods=n, freq="15min", tz=ET)
    vol = [0, 0] + [1_000_000] * (n - 2)
    df = pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.5 for c in closes],
            "low": [c - 0.5 for c in closes],
            "close": closes,
            "volume": vol,
        },
        index=idx,
    )
    prev, curr = evaluate_timeframe(df, "15m", RULES)
    assert prev is not None
    assert curr is not None
    assert curr.vwap > 0
