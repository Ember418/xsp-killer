"""Tests for XSP Lane B monitor (no live RH)."""

from __future__ import annotations

from datetime import date

from xsp_killer.lane_b_monitor import (
    LaneBRules,
    classify_hedge_put,
    classify_lane_b_call,
    evaluate_lane_b_alerts,
    run_monitor,
)

RULES = LaneBRules(
    lane="B",
    dte_min=180,
    chain_symbols=("SPX", "XSP"),
    call_delta_above=0.65,
    portfolio_drawdown_pct=8.0,
    hedge_dte_below=45,
    max_lane_b_notional_pct=50.0,
    logic_version="xsp_lane_b_v1",
)


def _call(exp: str = "2027-06-18", dte_ok: bool = True) -> dict:
    return {
        "id": f"leaps-{exp}",
        "chain_symbol": "XSP",
        "type": "call",
        "expiration_date": exp,
        "strike_price": 5500.0,
        "quantity": 2.0,
        "average_price": 120.0,
        "mark_price": 125.0,
        "delta": 0.45,
    }


def _put(exp: str = "2026-12-18", dte: int = 30) -> dict:
    return {
        "id": f"put-{exp}",
        "chain_symbol": "XSP",
        "type": "put",
        "expiration_date": exp,
        "strike_price": 5000.0,
        "quantity": 1.0,
        "average_price": 80.0,
        "mark_price": 75.0,
    }


def test_lane_b_call_requires_leaps_dte():
    assert classify_lane_b_call(_call(exp="2026-07-18"), RULES) is None
    pos = classify_lane_b_call(_call(exp="2027-06-18"), RULES)
    assert pos is not None
    assert pos.leg_type == "call"
    assert pos.dte > 180


def test_lane_b_excludes_lane_a_dte_band():
    assert classify_lane_b_call(_call(exp="2026-07-18"), RULES) is None


def test_hedge_missing_alert():
    call = classify_lane_b_call(_call(), RULES)
    assert call is not None
    call.lane = "B"
    alerts = evaluate_lane_b_alerts(
        [call], [], RULES, {},
        regime=None, drawdown_pct=None, portfolio_notional_usd=0,
    )
    assert any(a.alert_code == "B_HEDGE_MISSING" for a in alerts)


def test_hedge_dte_low_alert():
    call = classify_lane_b_call(_call(), RULES)
    assert call is not None
    call.lane = "B"
    call.hedge_pair_id = "pair-1"
    put = classify_hedge_put(_put(exp="2026-07-20"), RULES)
    assert put is not None
    put.hedge_pair_id = "pair-1"
    if put.dte >= 45:
        put.dte = 30
    alerts = evaluate_lane_b_alerts(
        [call], [put], RULES, {},
        regime=None, drawdown_pct=None, portfolio_notional_usd=0,
    )
    assert any(a.alert_code == "B_HEDGE_DTE_LOW" for a in alerts)


def test_run_monitor_fixture(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(
        '{"positions":{"leaps-2027-06-18":{"lane":"B"}},"hedge_links":{},"closed_trades":[]}\n'
    )
    report = run_monitor(
        state_path=state,
        positions_override=[_call()],
        publish_intel=False,
    )
    assert report.logic_version == "xsp_lane_b_v1"
    assert len(report.calls) == 1
