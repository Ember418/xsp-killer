"""Tests for conservative SPY quote marks and shadow exit brackets."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from xsp_killer.exit_shadow import evaluate_shadow_brackets
from xsp_killer.lane_a_monitor import (
    ExitAlert,
    LaneAPosition,
    LaneRules,
    evaluate_exit_alerts,
)
from xsp_killer.spy_quote import _conservative_exit_mark_spy, fetch_spy_call_quote

ET = ZoneInfo("America/New_York")

RULES = LaneRules(
    lane="A",
    dte_min=14,
    dte_max=60,
    exclude_expiry_month=("01",),
    chain_symbols=("SPX", "XSP"),
    stop_loss_pct=0.20,
    take_profit_pct=0.20,
    sell_eval_start_et=time(9, 30),
    sell_deadline_et=time(10, 0),
    no_sell_start_et=time(8, 30),
    no_sell_end_et=time(9, 30),
    require_upper_bb_for_take_profit=True,
    logic_version="xsp_lane_a_v2",
)


def test_conservative_exit_mark_prefers_bid_on_wide_spread():
    mark = _conservative_exit_mark_spy(bid=7.4, ask=9.0, last=8.0, mid=8.2)
    assert mark == 7.4


def test_fetch_spy_call_quote_caps_implausible_overnight_gain(monkeypatch):
    class Row:
        strike = 746.0

        def get(self, k, default=None):
            return {"bid": 11.9, "ask": 12.1, "lastPrice": 12.0, "delta": 0.5}.get(
                k, default
            )

    class Calls:
        def __init__(self):
            import pandas as pd

            self.calls = pd.DataFrame(
                {"strike": [746.0], "bid": [11.9], "ask": [12.1], "lastPrice": [12.0]}
            )

    monkeypatch.setattr(
        "xsp_killer.chain_cache.get_spy_option_chain", lambda _e: Calls()
    )
    # Guards must sit beyond the strategy's max TP/SL; a legit +36% move is not
    # "implausible" anymore. Use a genuinely absurd implied gain (>90%) so the
    # sanity clamp still trips. exit mark = bid 11.9 x 10 (scale) = 119.0.
    q = fetch_spy_call_quote(746.0, date(2026, 7, 17), entry_mid_xsp=55.0)
    assert q.stale is True
    assert q.exit_mark_xsp is not None
    assert q.exit_mark_xsp <= 55.0 * 1.90


def test_shadow_brackets_show_wide_sl_would_hold():
    pos = LaneAPosition(
        position_id="paper:XSP:2026-07-17:7465",
        chain_symbol="XSP",
        option_type="call",
        strike=7465.0,
        expiration_date=date(2026, 7, 17),
        quantity=1.0,
        average_price=110.0,
        mark_price=84.0,
        dte=25,
        entry_ts="2026-06-22T19:45:00+00:00",
        entry_mid_premium=109.4,
    )
    pos.pnl_per_contract = -2540.0
    pos.pnl_usd = -2540.0
    now = datetime(2026, 6, 23, 9, 35, tzinfo=ET)
    actual = ExitAlert(
        position_id=pos.position_id,
        exit_reason="stop_loss",
        message="sl",
        pnl_usd=-2540.0,
        pnl_per_contract=-2540.0,
    )
    brackets = evaluate_shadow_brackets(
        pos,
        RULES,
        now_et=now,
        ta_signal=None,
        suppress_morning_cut_dte=30,
        actual_alert=actual,
        evaluate_fn=evaluate_exit_alerts,
    )
    by_id = {b.bracket_id: b for b in brackets}
    assert by_id["prod"].would_exit is True
    assert by_id["prod"].exit_reason == "stop_loss"
    assert by_id["wide_sl_30"].would_exit is False
    assert by_id["defer_morning_cut_3d"].thresholds_to_continue.get(
        "need_premium_recovery_to_breakeven_pct"
    )
