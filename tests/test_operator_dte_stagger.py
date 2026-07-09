"""Operator 45–60 DTE stagger: pick_expiration collisions + paper/live parity."""

from __future__ import annotations

from datetime import date

import pytest

from xsp_killer.lane_a_entry import pick_expiration
from xsp_killer.lane_a_monitor import LaneRules
from xsp_killer.robinhood_mcp import RobinhoodMCPAdapter, RhMcpConfig


RULES = LaneRules(
    lane="A",
    dte_min=14,
    dte_max=60,
    exclude_expiry_month=("01",),
    chain_symbols=("SPX", "XSP"),
    stop_loss_pct=0.20,
    take_profit_pct=0.20,
    sell_eval_start_et=__import__("datetime").time(9, 30),
    sell_deadline_et=__import__("datetime").time(10, 0),
    no_sell_start_et=__import__("datetime").time(8, 30),
    no_sell_end_et=__import__("datetime").time(9, 30),
    require_upper_bb_for_take_profit=True,
    logic_version="xsp_lane_a_v2",
)

# Mock Friday calendar relative to 2026-07-07 (Tue):
#   45 DTE → 2026-08-21, 51 → 2026-08-27, 58 → 2026-09-03, 65 → 2026-09-10
# Note: 65 DTE is outside lane dte_max=60, so paper pick_expiration drops it.
TODAY = date(2026, 7, 7)
MOCK_FRIDAYS = (
    "2026-08-21",  # 45 DTE
    "2026-08-27",  # 51 DTE
    "2026-09-03",  # 58 DTE
    "2026-09-10",  # 65 DTE (above dte_max → excluded by paper filter)
)

# Nearest-target among eligible (14–60 DTE) Fridays:
#   45 → 45 exact (2026-08-21)
#   50 → 51 (abs 1) beats 45 (abs 5) → 2026-08-27
#   55 → 58 (abs 3) beats 51 (abs 4) → 2026-09-03
#   60 → 58 (abs 2); 65 excluded by dte_max → COLLISION with 55 on 2026-09-03
EXPECTED_PICKS = {
    45: date(2026, 8, 21),
    50: date(2026, 8, 27),
    55: date(2026, 9, 3),
    60: date(2026, 9, 3),  # collides with 55 — documented soak risk
}


@pytest.mark.parametrize(
    "dte_target,expected",
    [(45, EXPECTED_PICKS[45]), (50, EXPECTED_PICKS[50]), (55, EXPECTED_PICKS[55]), (60, EXPECTED_PICKS[60])],
    ids=["target_45", "target_50", "target_55", "target_60"],
)
def test_pick_expiration_operator_stagger_calendar(monkeypatch, dte_target, expected):
    monkeypatch.setattr(
        "xsp_killer.chain_cache.get_spy_expirations",
        lambda force=False: MOCK_FRIDAYS,
    )
    out = pick_expiration(
        RULES, today=TODAY, dte_pick="target", dte_target=dte_target
    )
    assert out == expected


def test_operator_stagger_documents_55_60_collision(monkeypatch):
    """55 and 60 targets resolve to the same Friday when 65 is outside dte_max."""
    monkeypatch.setattr(
        "xsp_killer.chain_cache.get_spy_expirations",
        lambda force=False: MOCK_FRIDAYS,
    )
    exp_55 = pick_expiration(RULES, today=TODAY, dte_pick="target", dte_target=55)
    exp_60 = pick_expiration(RULES, today=TODAY, dte_pick="target", dte_target=60)
    assert exp_55 == exp_60 == date(2026, 9, 3)
    distinct = {
        t: pick_expiration(RULES, today=TODAY, dte_pick="target", dte_target=t)
        for t in (45, 50, 55, 60)
    }
    assert len(set(distinct.values())) == 3  # 45, 50, and shared 55/60


def test_paper_live_target_dte_selector_parity(monkeypatch):
    """Paper pick_expiration and RH select_entry_contract share nearest-target logic."""
    monkeypatch.setattr(
        "xsp_killer.chain_cache.get_spy_expirations",
        lambda force=False: MOCK_FRIDAYS,
    )

    cfg = RhMcpConfig(agentic_account_id="agentic-1")
    adapter = RobinhoodMCPAdapter(config=cfg, http_post=lambda *a: {})

    def fake_call(name, args):
        if name == "get_option_chains":
            return {"symbol": "XSP", "expiration_dates": list(MOCK_FRIDAYS)}
        if name == "get_index_quotes":
            return {"results": [{"last_trade_price": "755.0"}]}
        if name == "get_option_instruments":
            return {
                "results": [
                    {
                        "id": f"inst-{args['expiration_dates']}-{args['strike_price']}",
                        "strike_price": args["strike_price"],
                        "type": "call",
                    }
                ]
            }
        if name == "get_option_quotes":
            return {
                "results": [
                    {
                        "instrument_id": iid,
                        "ask_price": "1.00",
                        "bid_price": "0.90",
                        "mark_price": "0.95",
                    }
                    for iid in args["instrument_ids"]
                ]
            }
        raise AssertionError(name)

    adapter.call_tool = fake_call  # type: ignore[method-assign]
    # Avoid real index/strike fan-out noise: stub instruments_for_strike path via
    # the fake_call above; select_entry_contract still needs a quotable ATM.

    for dte_target, expected in EXPECTED_PICKS.items():
        paper = pick_expiration(
            RULES, today=TODAY, dte_pick="target", dte_target=dte_target
        )
        live = adapter.select_entry_contract(
            dte_pick="target",
            dte_target=dte_target,
            dte_min=14,
            dte_max=60,
            strike_pick="atm_only",
            today=TODAY,
        )
        assert paper == expected
        assert date.fromisoformat(live["expiration_date"]) == expected
        assert live["dte"] == (expected - TODAY).days
