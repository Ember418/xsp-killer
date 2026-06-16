"""Unit tests for XSP Lane A Phase 0 monitor (no live Robinhood)."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from xsp_killer.lane_a_monitor import (
    ExitAlert,
    LaneAPosition,
    LaneRules,
    classify_position,
    compute_dte,
    evaluate_exit_alerts,
    is_lane_a_contract,
    run_monitor,
)
from xsp_killer.lane_a_ta import TaSignal

ET = ZoneInfo("America/New_York")

RULES = LaneRules(
    lane="A",
    dte_min=14,
    dte_max=60,
    exclude_expiry_month=("01",),
    chain_symbols=("SPX", "XSP"),
    hard_max_loss_usd_per_contract=75.0,
    morning_eval_start_et=time(9, 30),
    morning_cut_deadline_et=time(10, 30),
    rth_open_cut_minutes=30,
    logic_version="xsp_lane_a_v1",
)


def _raw(
    *,
    chain: str = "XSP",
    opt_type: str = "call",
    exp: str = "2026-07-18",
    strike: float = 6000.0,
    qty: float = 1.0,
    avg: float = 2.50,
    mark: float | None = 2.00,
) -> dict:
    return {
        "id": f"{chain}-{exp}-{strike}",
        "chain_symbol": chain,
        "type": opt_type,
        "expiration_date": exp,
        "strike_price": strike,
        "quantity": qty,
        "average_price": avg,
        "mark_price": mark,
    }


def test_lane_a_classify_call_dte_in_range():
    pos = classify_position(_raw(), RULES)
    assert pos is not None
    assert pos.chain_symbol == "XSP"
    assert 14 <= pos.dte <= 60


def test_lane_a_rejects_put():
    assert classify_position(_raw(opt_type="put"), RULES) is None


def test_lane_a_rejects_january_expiry():
    assert classify_position(_raw(exp="2027-01-15"), RULES) is None


def test_lane_a_rejects_short_dte():
    assert classify_position(_raw(exp="2026-06-20"), RULES) is None


def test_lane_a_rejects_non_spx_chain():
    assert classify_position(_raw(chain="AAPL"), RULES) is None


def test_max_loss_alert():
    pos = classify_position(_raw(avg=3.00, mark=1.50), RULES)
    assert pos is not None
    assert pos.pnl_per_contract == -150.0
    alerts = evaluate_exit_alerts(pos, RULES, now_et=datetime(2026, 6, 14, 9, 35, tzinfo=ET))
    reasons = {a.exit_reason for a in alerts}
    assert "max_loss" in reasons


def test_open_plus_30_red_when_still_negative():
    pos = classify_position(_raw(avg=2.50, mark=2.30), RULES)
    assert pos is not None
    now = datetime(2026, 6, 14, 10, 5, tzinfo=ET)
    alerts = evaluate_exit_alerts(pos, RULES, now_et=now)
    assert any(a.exit_reason == "open_plus_30_red" for a in alerts)


def test_morning_cut_at_deadline_when_red():
    pos = classify_position(_raw(avg=2.50, mark=2.40), RULES)
    assert pos is not None
    now = datetime(2026, 6, 14, 10, 30, tzinfo=ET)
    alerts = evaluate_exit_alerts(pos, RULES, now_et=now)
    assert any(a.exit_reason == "morning_cut" for a in alerts)


def test_no_alert_when_green():
    pos = classify_position(_raw(avg=2.00, mark=2.80), RULES)
    assert pos is not None
    now = datetime(2026, 6, 14, 10, 30, tzinfo=ET)
    alerts = evaluate_exit_alerts(pos, RULES, now_et=now)
    assert alerts == []


def test_rh_poll_skipped_by_default(monkeypatch):
    monkeypatch.delenv("XSP_LANE_A_RH_POLL", raising=False)
    from xsp_killer.lane_a_monitor import rh_poll_enabled

    assert rh_poll_enabled() is False


def test_run_monitor_with_fixture(tmp_path):
    fixture = [_raw()]
    report = run_monitor(
        state_path=tmp_path / "state.json",
        positions_override=fixture,
        now_et=datetime(2026, 6, 14, 10, 0, tzinfo=ET),
        publish_intel=False,
    )
    assert report.phase == 0
    assert report.logic_version == "xsp_lane_a_v1"
    assert len(report.positions) == 1
    assert report.rh_connected is True
    assert report.paper_mtm_usd is not None


def test_paper_exit_dedup(tmp_path):
    from xsp_killer.lane_a_monitor import ExitAlert, load_state, record_paper_exit_signals, save_state

    state = load_state(tmp_path / "state.json")
    alerts = [
        ExitAlert("p1", "morning_cut", "red", -50.0, -50.0),
    ]
    new1 = record_paper_exit_signals(
        state, alerts, evaluated_at="2026-06-14T14:00:00+00:00", logic_version="xsp_lane_a_v1"
    )
    new2 = record_paper_exit_signals(
        state, alerts, evaluated_at="2026-06-14T14:30:00+00:00", logic_version="xsp_lane_a_v1"
    )
    assert len(new1) == 1
    assert len(new2) == 0
    save_state(tmp_path / "state.json", state)


def test_morning_cut_suppressed_when_dte_30_plus():
    pos = classify_position(_raw(exp="2026-08-15"), RULES)
    assert pos is not None
    assert pos.dte >= 30
    now = datetime(2026, 6, 14, 10, 30, tzinfo=ET)
    ta = TaSignal("none", None, None, False, False, "")
    alerts = evaluate_exit_alerts(
        pos,
        RULES,
        now_et=now,
        ta_signal=ta,
        suppress_morning_cut_dte=30,
    )
    assert not any(a.exit_reason == "morning_cut" for a in alerts)


def test_upper_bb_exit_alert_when_green():
    pos = classify_position(_raw(avg=2.00, mark=2.80), RULES)
    assert pos is not None
    ta = TaSignal(
        signal="upper_bb_exit",
        primary=None,
        confirm=None,
        entry_ok=False,
        exit_ok=True,
        detail="upper BB rejection",
    )
    alerts = evaluate_exit_alerts(pos, RULES, now_et=datetime(2026, 6, 14, 14, 0, tzinfo=ET), ta_signal=ta)
    assert any(a.exit_reason == "upper_bb_rejection" for a in alerts)


def test_compute_dte():
    exp = date(2026, 7, 1)
    assert compute_dte(exp, today=date(2026, 6, 14)) == 17


def test_is_lane_a_contract_boundary():
    exp = date(2026, 7, 28)
    assert is_lane_a_contract(
        chain_symbol="SPX",
        option_type="call",
        expiration=exp,
        rules=RULES,
        today=date(2026, 6, 14),
    )
