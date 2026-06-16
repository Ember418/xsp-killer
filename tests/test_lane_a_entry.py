"""Tests for XSP Lane A paper entry (no live yfinance/RH)."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from xsp_killer.lane_a_entry import (
    EntryRules,
    already_entered_today,
    in_entry_window,
    open_paper_positions,
    round_xsp_strike,
    run_paper_entry,
)
from xsp_killer.lane_a_monitor import LaneRules
from xsp_killer.lane_a_ta import TaSignal

ET = ZoneInfo("America/New_York")

ENTRY_RULES = EntryRules(
    window_start_et=time(15, 45),
    window_end_et=time(16, 0),
    prior_day_spy_positive=True,
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
    hard_max_loss_usd_per_contract=75.0,
    morning_eval_start_et=time(9, 30),
    morning_cut_deadline_et=time(10, 30),
    rth_open_cut_minutes=30,
    logic_version="xsp_lane_a_v1",
)


def test_in_entry_window_weekday():
    inside = datetime(2026, 6, 16, 15, 47, tzinfo=ET)  # Tue
    outside = datetime(2026, 6, 16, 15, 30, tzinfo=ET)
    weekend = datetime(2026, 6, 14, 15, 47, tzinfo=ET)  # Sun
    assert in_entry_window(inside, ENTRY_RULES) is True
    assert in_entry_window(outside, ENTRY_RULES) is False
    assert in_entry_window(weekend, ENTRY_RULES) is False


def test_round_xsp_strike():
    assert round_xsp_strike(6012.3) == 6010.0


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
            {"entered": True, "evaluated_at": "2026-06-16T19:45:00+00:00"},
        ]
    }
    assert already_entered_today(state, date(2026, 6, 16)) is True
    assert already_entered_today(state, date(2026, 6, 17)) is False


def _mock_ta_entry_ok(monkeypatch):
    fake = TaSignal(
        signal="bb_bounce_entry",
        primary=None,
        confirm=None,
        entry_ok=True,
        exit_ok=False,
        detail="test bounce",
    )
    monkeypatch.setattr("xsp_killer.lane_a_entry.evaluate_ta_signals", lambda rules: fake)


def test_run_paper_entry_outside_window(tmp_path, monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_PAPER_ENTRY", "true")
    _mock_ta_entry_ok(monkeypatch)
    decision = run_paper_entry(
        state_path=tmp_path / "state.json",
        now_et=datetime(2026, 6, 16, 10, 0, tzinfo=ET),
        publish_intel=False,
    )
    assert decision.entered is False
    assert decision.skip_reason is not None


def test_run_paper_entry_success_mocked(tmp_path, monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_PAPER_ENTRY", "true")
    _mock_ta_entry_ok(monkeypatch)
    def _regime():
        return "GREEN", True

    monkeypatch.setattr("xsp_killer.lane_a_entry.read_regime", _regime)
    monkeypatch.setattr("xsp_killer.lane_a_entry.fetch_spy_ohlcv", lambda: (600.0, 595.0, 0.5))
    monkeypatch.setattr("xsp_killer.lane_a_entry.fetch_spx_proxy", lambda: 6010.0)
    monkeypatch.setattr(
        "xsp_killer.lane_a_entry.pick_expiration",
        lambda rules, today=None: date(2026, 7, 18),
    )
    monkeypatch.setattr(
        "xsp_killer.lane_a_entry.fetch_spy_call_quote",
        lambda strike, exp: (2.45, 0.52),
    )

    decision = run_paper_entry(
        state_path=tmp_path / "state.json",
        now_et=datetime(2026, 6, 16, 15, 47, tzinfo=ET),
        publish_intel=False,
    )
    assert decision.entered is True
    assert decision.position is not None
    assert decision.position["strike"] == 6010.0
    assert decision.position["average_price"] == 2.45


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
        now_et=datetime(2026, 6, 16, 15, 47, tzinfo=ET),
        force=True,
        publish_intel=False,
    )
    assert decision.entered is False
    assert "max open" in (decision.skip_reason or "").lower()
