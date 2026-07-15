"""Tests for DTE/strike pick helpers."""

from __future__ import annotations

from datetime import date

from xsp_killer.lane_a_entry import pick_expiration, pick_strike
from xsp_killer.lane_a_monitor import LaneRules


RULES = LaneRules(
    lane="A",
    dte_min=14,
    dte_max=60,
    exclude_expiry_month=("01",),
    chain_symbols=("SPX", "XSP"),
    stop_loss_pct=0.20,
    take_profit_pct=0.20,
    sell_eval_start_et=__import__("datetime").time(8, 0),
    sell_deadline_et=__import__("datetime").time(9, 30),
    no_sell_start_et=__import__("datetime").time(0, 0),
    no_sell_end_et=__import__("datetime").time(8, 0),
    require_upper_bb_for_take_profit=True,
    logic_version="xsp_lane_a_v2",
)


def test_pick_expiration_target(monkeypatch):
    exp_a = date(2026, 7, 1)
    exp_b = date(2026, 7, 18)
    exp_c = date(2026, 8, 15)

    monkeypatch.setattr(
        "xsp_killer.lane_a_entry.yf",
        None,
        raising=False,
    )

    def _fake_ticker(_sym):
        class T:
            options = [exp_a.isoformat(), exp_b.isoformat(), exp_c.isoformat()]

        return T()

    monkeypatch.setattr("yfinance.Ticker", _fake_ticker)
    out = pick_expiration(
        RULES, today=date(2026, 6, 14), dte_pick="target", dte_target=28
    )
    assert out == exp_b


def test_pick_strike_atm_only(monkeypatch):
    monkeypatch.setattr(
        "xsp_killer.lane_a_entry.fetch_spy_call_quote",
        lambda strike, exp: (2.5, 0.5),
    )
    strike, prem, delta = pick_strike(6012.0, date(2026, 7, 18), strike_pick="atm_only")
    assert strike == 6010.0
    assert prem == 25.0
    assert delta == 0.5
