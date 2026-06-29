"""Tests for XSP Lane A paper entry (no live yfinance/RH)."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from xsp_killer.lane_a_entry import (
    EntryDecision,
    EntryRules,
    _bucket_skip_reason,
    _finalize_entry,
    _write_entry_telemetry_brief,
    already_entered_today,
    entry_logs_for_epoch,
    in_entry_window,
    open_paper_positions,
    pick_cheapest_atm_strike,
    round_xsp_strike,
    run_paper_entry,
    summarize_entry_telemetry_from_logs,
)
from xsp_killer.lane_a_monitor import LaneRules
from xsp_killer.lane_a_ta import TaSignal

ET = ZoneInfo("America/New_York")

ENTRY_RULES = EntryRules(
    window_start_et=time(15, 45),
    window_end_et=time(16, 0),
    prior_day_spy_positive=False,
    max_open_positions=1,
    quantity=1.0,
    enabled=True,
)

LANE_RULES = LaneRules(
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


def test_in_entry_window_weekday():
    inside = datetime(2026, 6, 16, 15, 47, tzinfo=ET)
    outside = datetime(2026, 6, 16, 15, 30, tzinfo=ET)
    weekend = datetime(2026, 6, 14, 15, 47, tzinfo=ET)
    assert in_entry_window(inside, ENTRY_RULES) is True
    assert in_entry_window(outside, ENTRY_RULES) is False
    assert in_entry_window(weekend, ENTRY_RULES) is False


def test_round_xsp_strike():
    assert round_xsp_strike(6012.3) == 6010.0


def test_pick_cheapest_atm_strike(monkeypatch):
    exp = date(2026, 7, 18)

    def _quote(strike, expiration):
        return (2.0 if strike == 601.0 else 2.5, 0.5)

    monkeypatch.setattr("xsp_killer.lane_a_entry.fetch_spy_call_quote", _quote)
    strike, prem, _ = pick_cheapest_atm_strike(6012.0, exp, max_steps_from_atm=1)
    assert strike == 6010.0
    assert prem == 20.0


def test_open_paper_positions_filters_closed():
    state = {
        "paper_positions": {
            "a": {"status": "open", "position_id": "a"},
            "b": {"status": "closed", "position_id": "b"},
        }
    }
    assert len(open_paper_positions(state)) == 1


def test_already_entered_today():
    state = {
        "entry_log": [
            {
                "entered": True,
                "evaluated_at": "2026-06-16T19:45:00+00:00",
                "position_id": "paper:XSP:2026-07-18:6010",
            },
        ]
    }
    assert already_entered_today(state, date(2026, 6, 16)) is True
    assert already_entered_today(state, date(2026, 6, 17)) is False


def _mock_ta_entry_ok(monkeypatch):
    fake = TaSignal(
        signal="none",
        primary=None,
        confirm=None,
        entry_ok=False,
        exit_ok=False,
        upper_bb_touched=False,
        detail="not used in close_window_only",
    )
    monkeypatch.setattr(
        "xsp_killer.lane_a_entry.evaluate_ta_signals", lambda rules, now_et=None: fake
    )


def test_run_paper_entry_outside_window(tmp_path, monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_PAPER_ENTRY", "true")
    _mock_ta_entry_ok(monkeypatch)
    decision = run_paper_entry(
        state_path=tmp_path / "state.json",
        log_path=tmp_path / "paper.jsonl",
        now_et=datetime(2026, 6, 16, 10, 0, tzinfo=ET),
        publish_intel=False,
    )
    assert decision.entered is False
    assert decision.skip_reason is not None


def test_run_paper_entry_success_mocked(tmp_path, monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_PAPER_ENTRY", "true")
    _mock_ta_entry_ok(monkeypatch)

    def _regime():
        return "GREEN", True, None, None

    monkeypatch.setattr("xsp_killer.lane_a_entry.read_regime_detail", _regime)
    monkeypatch.setattr(
        "xsp_killer.lane_a_entry.fetch_spy_ohlcv",
        lambda: (600.0, 595.0, 0.5, "2026-06-17"),
    )
    monkeypatch.setattr("xsp_killer.lane_a_entry.fetch_spx_proxy", lambda: 6010.0)
    monkeypatch.setattr(
        "xsp_killer.lane_a_entry.pick_expiration",
        lambda rules, today=None, dte_pick="min", dte_target=None: date(2026, 7, 18),
    )
    monkeypatch.setattr(
        "xsp_killer.lane_a_entry.pick_strike",
        lambda spx, exp, strike_pick="cheapest_near_atm", max_steps_from_atm=1: (
            6010.0,
            2.45,
            0.52,
        ),
    )

    decision = run_paper_entry(
        state_path=tmp_path / "state.json",
        log_path=tmp_path / "paper.jsonl",
        now_et=datetime(2026, 6, 16, 15, 47, tzinfo=ET),
        publish_intel=False,
    )
    assert decision.entered is True
    assert decision.position is not None
    assert decision.position["strike"] == 6010.0
    assert decision.position["average_price"] > 2.45


def test_run_paper_entry_blocks_when_open_position(tmp_path, monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_PAPER_ENTRY", "true")
    _mock_ta_entry_ok(monkeypatch)
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"paper_positions":{"p1":{"status":"open","position_id":"p1"}}}\n',
        encoding="utf-8",
    )
    decision = run_paper_entry(
        state_path=state_path,
        log_path=tmp_path / "paper.jsonl",
        now_et=datetime(2026, 6, 16, 15, 47, tzinfo=ET),
        force=True,
        publish_intel=False,
    )
    assert decision.entered is False
    assert "max open" in (decision.skip_reason or "").lower()


def test_already_entered_skips_failed_attempt():
    state = {
        "entry_log": [
            {
                "entered": False,
                "evaluated_at": "2026-06-16T19:45:00+00:00",
                "skip_reason": "regime",
            },
            {"entered": True, "evaluated_at": "2026-06-16T19:45:00+00:00"},
        ]
    }
    assert already_entered_today(state, date(2026, 6, 16)) is False


def test_spy_to_xsp_premium_scale_in_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_PAPER_ENTRY", "true")
    _mock_ta_entry_ok(monkeypatch)
    monkeypatch.setattr(
        "xsp_killer.lane_a_entry.read_regime_detail",
        lambda: ("GREEN", True, None, None),
    )
    monkeypatch.setattr(
        "xsp_killer.lane_a_entry.fetch_spy_ohlcv",
        lambda: (600.0, 595.0, 0.5, "2026-06-17"),
    )
    monkeypatch.setattr("xsp_killer.lane_a_entry.fetch_spx_proxy", lambda: 6010.0)
    monkeypatch.setattr(
        "xsp_killer.lane_a_entry.pick_expiration",
        lambda rules, today=None, dte_pick="min", dte_target=None: date(2026, 7, 18),
    )
    monkeypatch.setattr(
        "xsp_killer.lane_a_entry.pick_strike",
        lambda spx, exp, strike_pick="cheapest_near_atm", max_steps_from_atm=1: (
            6010.0,
            24.5,
            0.52,
        ),
    )
    decision = run_paper_entry(
        state_path=tmp_path / "state.json",
        log_path=tmp_path / "paper.jsonl",
        now_et=datetime(2026, 6, 16, 15, 47, tzinfo=ET),
        publish_intel=False,
    )
    assert decision.entered is True
    pos = decision.position
    assert pos["entry_mid_premium"] == 24.5
    assert pos["average_price"] > pos["entry_mid_premium"]


def test_bucket_skip_reason_regime():
    assert _bucket_skip_reason("regime YELLOW blocks new risk") == "regime_gate"


def test_entry_telemetry_counts_skips_and_regime(tmp_path):
    state: dict = {"entry_log": []}
    decision = EntryDecision(
        entered=False,
        evaluated_at="2026-06-26T19:45:00+00:00",
        logic_version="test",
        in_window=True,
        regime="YELLOW",
        regime_ok=False,
        prior_day_spy_return_pct=None,
        prior_day_ok=True,
        skip_reason="regime YELLOW blocks new risk",
    )
    _finalize_entry(
        state,
        tmp_path / "state.json",
        decision,
        publish_intel=False,
        brief_path=False,
        log_path=tmp_path / "paper.jsonl",
    )
    tel = state["entry_telemetry"]
    assert tel["regime_counts"]["YELLOW"] == 1
    assert tel["skip_reason_counts"]["regime_gate"] == 1
    assert tel["sessions_evaluated"] == 1
    assert tel["entered_sessions"] == 0


def test_entry_telemetry_respects_pnl_epoch(tmp_path):
    epoch = "2026-06-23T22:20:36+00:00"
    state = {
        "pnl_epoch_at": epoch,
        "entry_log": [
            {
                "evaluated_at": "2026-06-22T19:45:00+00:00",
                "entered": True,
                "regime": "GREEN",
                "skip_reason": None,
            },
            {
                "evaluated_at": "2026-06-26T19:45:00+00:00",
                "entered": False,
                "regime": "YELLOW",
                "skip_reason": "regime YELLOW blocks new risk",
            },
        ],
    }
    logs = entry_logs_for_epoch(state)
    assert len(logs) == 1
    tel = summarize_entry_telemetry_from_logs(logs)
    assert tel["entered_sessions"] == 0
    assert tel["sessions_evaluated"] == 1
    assert tel["skip_reason_counts"] == {"regime_gate": 1}
    assert tel["regime_counts"] == {"YELLOW": 1}

    brief_path = tmp_path / "telemetry.json"
    _write_entry_telemetry_brief(state, out_path=brief_path)
    import json

    payload = json.loads(brief_path.read_text(encoding="utf-8"))
    assert payload["pnl_epoch_at"] == epoch
    assert payload["entered_sessions"] == 0
    assert payload["sessions_evaluated"] == 1
    assert "entered" not in payload["skip_reason_counts"]
