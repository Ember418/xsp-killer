"""Tests for paper risk gates and conductor shadow reviewer."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from xsp_killer.conductor_shadow import shadow_review_entry
from xsp_killer.risk_gates import entry_allowed_by_risk, realized_pnl_today

ET = ZoneInfo("America/New_York")


def test_shadow_blocks_red_regime():
    ok, reason = shadow_review_entry(
        regime="RED",
        prior_day_spy_return_pct=0.5,
        ta_detail=None,
        position=None,
    )
    assert ok is False
    assert "RED" in (reason or "")


def test_shadow_blocks_large_prior_day_drop():
    ok, reason = shadow_review_entry(
        regime="GREEN",
        prior_day_spy_return_pct=-2.0,
        ta_detail=None,
        position={"dte": 28},
    )
    assert ok is False
    assert "prior-day" in (reason or "")


def test_shadow_passes_green_tape():
    ok, reason = shadow_review_entry(
        regime="GREEN",
        prior_day_spy_return_pct=0.5,
        ta_detail="bb bounce",
        position={"dte": 28},
    )
    assert ok is True
    assert reason is None


def test_daily_loss_cap_blocks_entry(monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_DAILY_LOSS_CAP_USD", "100")
    state = {
        "paper_events": [
            {
                "evaluated_at": datetime.now(ET).replace(hour=14).isoformat(),
                "paper_pnl_usd": -150.0,
            }
        ]
    }
    assert realized_pnl_today(state) == -150.0
    ok, reason = entry_allowed_by_risk(state)
    assert ok is False
    assert "daily paper loss cap" in (reason or "")


def test_daily_loss_cap_allows_when_under(monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_DAILY_LOSS_CAP_USD", "500")
    state = {
        "paper_events": [
            {
                "evaluated_at": datetime.now(ET).replace(hour=14).isoformat(),
                "paper_pnl_usd": -50.0,
            }
        ]
    }
    ok, reason = entry_allowed_by_risk(state)
    assert ok is True
    assert reason is None


def test_consecutive_losses_halt_entry(monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_MAX_CONSECUTIVE_LOSSES", "3")
    state = {
        "paper_events": [
            {"paper_pnl_usd": -10.0},
            {"paper_pnl_usd": -20.0},
            {"paper_pnl_usd": -5.0},
        ]
    }
    ok, reason = entry_allowed_by_risk(state)
    assert ok is False
    assert "consecutive paper losses" in (reason or "")


def test_consecutive_losses_reset_after_win(monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_MAX_CONSECUTIVE_LOSSES", "3")
    state = {
        "paper_events": [
            {"paper_pnl_usd": -10.0},
            {"paper_pnl_usd": 5.0},
            {"paper_pnl_usd": -20.0},
            {"paper_pnl_usd": -5.0},
        ]
    }
    ok, reason = entry_allowed_by_risk(state)
    assert ok is True
    assert reason is None
