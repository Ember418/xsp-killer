"""SPY chain proxy strike mapping for XSP half-steps."""

from __future__ import annotations

from datetime import date

import pandas as pd

from xsp_killer.lane_a_entry import estimate_fallback_premium, fetch_spy_ohlcv
from xsp_killer.spy_quote import (
    _select_spy_call_row,
    fetch_spy_call_quote_legacy as fetch_spy_call_quote,
    xsp_strike_to_spy_chain_strike,
)
from xsp_killer.paper_economics import SPY_TO_XSP_PREMIUM_SCALE


def _chain(strikes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "strike": strikes,
            "bid": [s * 0.01 for s in strikes],
            "ask": [s * 0.01 + 0.05 for s in strikes],
            "lastPrice": [s * 0.01 + 0.02 for s in strikes],
            "delta": [0.5] * len(strikes),
        }
    )


def test_half_step_xsp_strikes_map_to_distinct_spy_rows():
    calls = _chain([748.0, 749.0, 750.0, 751.0, 752.0])
    row_atm = _select_spy_call_row(calls, 750.0)
    row_otm = _select_spy_call_row(calls, 750.5)
    assert float(row_atm["strike"]) == 750.0
    assert float(row_otm["strike"]) == 751.0


def test_fetch_spy_call_quote_distinguishes_7500_and_7505(monkeypatch):
    exp = date(2026, 7, 18)
    chain = _chain([749.0, 750.0, 751.0, 752.0])

    class FakeChain:
        calls = chain

    monkeypatch.setattr(
        "xsp_killer.chain_cache.get_spy_option_chain",
        lambda _exp: FakeChain(),
    )
    mid_7500, _ = fetch_spy_call_quote(xsp_strike_to_spy_chain_strike(7500.0), exp)
    mid_7505, _ = fetch_spy_call_quote(xsp_strike_to_spy_chain_strike(7505.0), exp)
    assert mid_7500 is not None and mid_7505 is not None
    assert mid_7500 != mid_7505


def test_estimate_fallback_premium_scales_to_xsp():
    spy = 600.0
    atm = estimate_fallback_premium(spy, 28, xsp_strike=6000.0, spx_level=6000.0)
    otm = estimate_fallback_premium(spy, 28, xsp_strike=6005.0, spx_level=6000.0)
    spy_only = estimate_fallback_premium(spy, 28, scale_to_xsp=False)
    assert atm > otm
    assert atm >= spy_only * SPY_TO_XSP_PREMIUM_SCALE * 0.99


def test_fetch_spy_ohlcv_close_to_close(monkeypatch):
    idx = pd.date_range("2026-06-16", periods=3, freq="D")
    hist = pd.DataFrame(
        {
            "Open": [590.0, 592.0, 595.0],
            "Close": [591.0, 594.0, 593.0],
        },
        index=idx,
    )

    class Ticker:
        def history(self, **_kwargs):
            return hist

    monkeypatch.setattr("yfinance.Ticker", lambda _sym: Ticker())
    _close, _open, ret, session = fetch_spy_ohlcv()
    assert _close == 594.0
    assert ret is not None
    assert session == "2026-06-17"
    # close-to-close: (594 - 591) / 591 * 100
    assert abs(ret - ((594.0 - 591.0) / 591.0 * 100.0)) < 0.01
