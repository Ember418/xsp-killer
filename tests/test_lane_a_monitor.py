"""Unit tests for XSP Lane A Phase 0 monitor (no live Robinhood)."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from xsp_killer.lane_a_monitor import (
    ExitAlert,
    LaneRules,
    classify_position,
    compute_dte,
    evaluate_exit_alerts,
    is_lane_a_contract,
    load_state,
    record_paper_exit_signals,
    rh_poll_enabled,
    run_monitor,
    save_state,
)
from xsp_killer.lane_a_ta import TaSignal

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


def test_stop_loss_20pct_alert():
    pos = classify_position(_raw(avg=2.00, mark=1.50), RULES)
    assert pos is not None
    now = datetime(2026, 6, 14, 9, 45, tzinfo=ET)
    alerts = evaluate_exit_alerts(pos, RULES, now_et=now)
    assert any(a.exit_reason == "stop_loss" for a in alerts)


def test_no_sell_during_830_930():
    pos = classify_position(_raw(avg=2.00, mark=1.50), RULES)
    assert pos is not None
    now = datetime(2026, 6, 14, 9, 0, tzinfo=ET)
    alerts = evaluate_exit_alerts(pos, RULES, now_et=now)
    assert alerts == []


def test_take_profit_waits_without_upper_bb():
    pos = classify_position(_raw(avg=2.00, mark=2.50), RULES)
    assert pos is not None
    ta = TaSignal("none", None, None, False, False, False, "")
    now = datetime(2026, 6, 14, 9, 45, tzinfo=ET)
    alerts = evaluate_exit_alerts(pos, RULES, now_et=now, ta_signal=ta)
    assert alerts == []


def test_take_profit_fires_with_upper_bb_touch():
    pos = classify_position(_raw(avg=2.00, mark=2.50), RULES)
    assert pos is not None
    ta = TaSignal("upper_bb_exit", None, None, False, True, True, "upper touch")
    now = datetime(2026, 6, 14, 9, 45, tzinfo=ET)
    alerts = evaluate_exit_alerts(pos, RULES, now_et=now, ta_signal=ta)
    assert any(a.exit_reason in ("take_profit", "upper_bb_rejection") for a in alerts)


def test_time_stop_at_deadline():
    pos = classify_position(_raw(avg=2.00, mark=2.10), RULES)
    assert pos is not None
    pos.entry_ts = "2026-06-13T19:45:00+00:00"
    now = datetime(2026, 6, 14, 10, 0, tzinfo=ET)
    alerts = evaluate_exit_alerts(pos, RULES, now_et=now)
    assert any(a.exit_reason == "time_stop" for a in alerts)


def test_time_stop_skips_same_entry_day():
    pos = classify_position(_raw(avg=2.00, mark=2.10), RULES)
    assert pos is not None
    pos.entry_ts = "2026-06-14T19:45:00+00:00"
    now = datetime(2026, 6, 14, 15, 45, tzinfo=ET)
    alerts = evaluate_exit_alerts(pos, RULES, now_et=now)
    assert not any(a.exit_reason == "time_stop" for a in alerts)


def test_stop_loss_outside_tp_window():
    pos = classify_position(_raw(avg=2.00, mark=1.50), RULES)
    assert pos is not None
    now = datetime(2026, 6, 14, 10, 30, tzinfo=ET)
    alerts = evaluate_exit_alerts(pos, RULES, now_et=now)
    assert any(a.exit_reason == "stop_loss" for a in alerts)


def test_rh_poll_skipped_by_default(monkeypatch):
    monkeypatch.delenv("XSP_LANE_A_RH_POLL", raising=False)
    assert rh_poll_enabled() is False


def test_run_monitor_with_fixture(tmp_path):
    fixture = [_raw()]
    report = run_monitor(
        state_path=tmp_path / "state.json",
        positions_override=fixture,
        now_et=datetime(2026, 6, 14, 9, 45, tzinfo=ET),
        publish_intel=False,
    )
    assert report.phase == 0
    assert report.logic_version == "xsp_lane_a_v2"
    assert len(report.positions) == 1
    assert report.rh_connected is True
    assert report.paper_mtm_usd is not None


def test_paper_exit_dedup(tmp_path):
    state = load_state(tmp_path / "state.json")
    alerts = [ExitAlert("p1", "stop_loss", "red", -50.0, -50.0)]
    new1 = record_paper_exit_signals(
        state, alerts, evaluated_at="2026-06-14T14:00:00+00:00", logic_version="xsp_lane_a_v2"
    )
    new2 = record_paper_exit_signals(
        state, alerts, evaluated_at="2026-06-14T14:30:00+00:00", logic_version="xsp_lane_a_v2"
    )
    assert len(new1) == 1
    assert len(new2) == 0
    save_state(tmp_path / "state.json", state)


def test_upper_bb_exit_in_sell_window():
    pos = classify_position(_raw(avg=2.00, mark=2.50), RULES)
    assert pos is not None
    ta = TaSignal(
        signal="upper_bb_exit",
        primary=None,
        confirm=None,
        entry_ok=False,
        exit_ok=True,
        upper_bb_touched=True,
        detail="upper BB rejection",
    )
    alerts = evaluate_exit_alerts(
        pos, RULES, now_et=datetime(2026, 6, 14, 9, 45, tzinfo=ET), ta_signal=ta
    )
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

def test_read_regime_from_intel_dict(monkeypatch):
    from xsp_killer import intel

    monkeypatch.setattr(intel.IntelReader, "read", lambda key: {"regime": "GREEN"})
    from xsp_killer.lane_a_monitor import read_regime

    regime, ok = read_regime()
    assert regime == "GREEN"
    assert ok is True


def test_pnl_uses_entry_fill_not_double_count():
    from xsp_killer.paper_economics import PaperEconomics, entry_fill_premium, pnl_from_entry_fill

    econ = PaperEconomics(commission_usd_per_contract=0.65, slippage_pct_of_premium=0.005, slippage_usd_per_share=0.12, slippage_max_pct_of_premium=0.015)
    entry_mid = 24.5
    entry_fill = entry_fill_premium(entry_mid, econ)
    pnl = pnl_from_entry_fill(entry_fill=entry_fill, exit_mid=29.4, econ=econ)
    assert pnl < (29.4 - 24.5) * 100.0
    assert pnl > 0

def test_open_paper_position_monitored_below_entry_dte_min(tmp_path):
    """Hold entered at dte_min must still get exit monitoring when DTE drops."""
    from xsp_killer.lane_a_monitor import paper_positions_to_lane

    state = {
        "paper_positions": {
            "paper:XSP:2026-06-30:7520": {
                "position_id": "paper:XSP:2026-06-30:7520",
                "lane": "A",
                "chain_symbol": "XSP",
                "option_type": "call",
                "strike": 7520.0,
                "expiration_date": "2026-06-30",
                "quantity": 1.0,
                "average_price": 66.39,
                "mark_price": 61.8,
                "entry_mid_premium": 65.4,
                "status": "open",
            }
        }
    }
    today = __import__("datetime").date(2026, 6, 17)
    rows = [state["paper_positions"]["paper:XSP:2026-06-30:7520"]]
    classified = paper_positions_to_lane(rows, RULES, today=today)
    assert len(classified) == 1
    assert classified[0].dte == 13



def test_stale_mark_skips_exit_alerts():
    from xsp_killer.lane_a_monitor import LaneAPosition, evaluate_exit_alerts

    pos = LaneAPosition(
        position_id="paper:XSP:2026-07-17:7505",
        chain_symbol="XSP",
        option_type="call",
        strike=7505.0,
        expiration_date=date(2026, 7, 17),
        quantity=1.0,
        average_price=6.0,
        mark_price=5.5,
        dte=28,
        entry_ts="2026-06-16T19:45:00+00:00",
        entry_mid_premium=5.8,
        mark_quote_stale=True,
    )
    pos.pnl_per_contract = -50.0
    pos.pnl_usd = -50.0
    now = datetime(2026, 6, 17, 10, 0, tzinfo=ET)
    alerts = evaluate_exit_alerts(pos, RULES, now_et=now)
    assert alerts == []


def test_suppress_morning_cut_for_long_dte():
    from xsp_killer.lane_a_monitor import LaneAPosition, evaluate_exit_alerts

    pos = LaneAPosition(
        position_id="paper:XSP:2026-07-31:7500",
        chain_symbol="XSP",
        option_type="call",
        strike=7500.0,
        expiration_date=date(2026, 7, 31),
        quantity=1.0,
        average_price=6.0,
        mark_price=5.9,
        dte=35,
        entry_ts="2026-06-16T19:45:00+00:00",
        entry_mid_premium=5.8,
    )
    pos.pnl_per_contract = -10.0
    pos.pnl_usd = -10.0
    now = datetime(2026, 6, 17, 10, 0, tzinfo=ET)
    alerts = evaluate_exit_alerts(pos, RULES, now_et=now, suppress_morning_cut_dte=30)
    assert alerts == []
