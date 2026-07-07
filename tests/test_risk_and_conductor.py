"""Tests for paper risk gates and conductor shadow reviewer."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from xsp_killer.conductor_shadow import shadow_review_entry
from xsp_killer.lane_a_monitor import DEFAULT_RULES
from xsp_killer.risk_gates import (
    entry_allowed_by_risk,
    realized_pnl_today,
    risk_gate_snapshot,
)

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


def test_shadow_allows_small_prior_day_drop():
    ok, reason = shadow_review_entry(
        regime="GREEN",
        prior_day_spy_return_pct=-0.5,
        ta_detail=None,
        position={"dte": 28},
    )
    assert ok is True
    assert reason is None


def test_shadow_blocks_at_1_5_pct_threshold():
    ok, _ = shadow_review_entry(
        regime="GREEN",
        prior_day_spy_return_pct=-1.51,
        ta_detail=None,
        position={"dte": 28},
    )
    assert ok is False

    ok, reason = shadow_review_entry(
        regime="GREEN",
        prior_day_spy_return_pct=-1.5,
        ta_detail=None,
        position={"dte": 28},
    )
    assert ok is True
    assert reason is None


def test_shadow_passes_green_tape():
    ok, reason = shadow_review_entry(
        regime="GREEN",
        prior_day_spy_return_pct=0.5,
        ta_detail="bb bounce",
        position={"dte": 28},
    )
    assert ok is True
    assert reason is None


def test_risk_gate_snapshot_structure(monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_DAILY_LOSS_CAP_USD", "500")
    monkeypatch.setenv("XSP_LANE_A_PREMIUM_SCALE", "1")
    state = {"paper_events": []}
    snap = risk_gate_snapshot(state)
    assert snap["enabled"] is True
    assert snap["allowed"] is True
    assert snap["scale"] == 1.0
    assert snap["effective_cap_usd"] == 500.0


def test_daily_loss_cap_blocks_entry(monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_DAILY_LOSS_CAP_USD", "100")
    monkeypatch.setenv("XSP_LANE_A_PREMIUM_SCALE", "1")
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
    monkeypatch.setenv("XSP_LANE_A_PREMIUM_SCALE", "1")
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


def test_daily_loss_cap_scales_from_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_DAILY_LOSS_CAP_USD", "100")
    monkeypatch.delenv("XSP_LANE_A_PREMIUM_SCALE", raising=False)
    rules = tmp_path / "rules.yaml"
    rules.write_text("paper_economics:\n  premium_scale: 2.0\n", encoding="utf-8")
    state = {
        "paper_events": [
            {
                "evaluated_at": datetime.now(ET).replace(hour=14).isoformat(),
                "paper_pnl_usd": -150.0,
            }
        ]
    }
    ok, reason = entry_allowed_by_risk(state, rules_path=rules)
    assert ok is True
    assert reason is None


def test_daily_loss_cap_reason_shows_scale(tmp_path, monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_DAILY_LOSS_CAP_USD", "100")
    monkeypatch.delenv("XSP_LANE_A_PREMIUM_SCALE", raising=False)
    rules = tmp_path / "rules.yaml"
    rules.write_text("paper_economics:\n  premium_scale: 2.0\n", encoding="utf-8")
    state = {
        "paper_events": [
            {
                "evaluated_at": datetime.now(ET).replace(hour=14).isoformat(),
                "paper_pnl_usd": -250.0,
            }
        ]
    }
    ok, reason = entry_allowed_by_risk(state, rules_path=rules)
    assert ok is False
    assert "scale=2.00x" in (reason or "")


def test_daily_loss_cap_respects_session_premium_scale_override(monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_DAILY_LOSS_CAP_USD", "100")
    state = {
        "paper_events": [
            {
                "evaluated_at": datetime.now(ET).replace(hour=14).isoformat(),
                "paper_pnl_usd": -510.0,
            }
        ]
    }
    ok, reason = entry_allowed_by_risk(state, premium_scale=5.0)
    assert ok is False
    assert "scale=5.00x" in (reason or "")


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


def test_consecutive_loss_streak_respects_reset_marker(monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_MAX_CONSECUTIVE_LOSSES", "3")
    state = {
        "risk_streak_reset_at": "2026-06-16T14:00:00+00:00",
        "paper_events": [
            {
                "evaluated_at": "2026-06-16T13:00:00+00:00",
                "paper_pnl_usd": -10.0,
            },
            {
                "evaluated_at": "2026-06-16T13:30:00+00:00",
                "paper_pnl_usd": -20.0,
            },
            {
                "evaluated_at": "2026-06-16T14:30:00+00:00",
                "paper_pnl_usd": -5.0,
            },
            {
                "evaluated_at": "2026-06-16T15:00:00+00:00",
                "paper_pnl_usd": -6.0,
            },
        ],
    }
    ok, reason = entry_allowed_by_risk(state)
    assert ok is True
    assert reason is None


def test_daily_loss_cap_respects_scale_regression(monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_DAILY_LOSS_CAP_USD", "500")
    monkeypatch.delenv("XSP_LANE_A_PREMIUM_SCALE", raising=False)
    state = {
        "paper_events": [
            {
                "evaluated_at": datetime.now(ET).replace(hour=14).isoformat(),
                "paper_pnl_usd": -1582.45,
            }
        ]
    }

    ok, reason = entry_allowed_by_risk(state, rules_path=DEFAULT_RULES)
    assert ok is True
    assert reason is None

    monkeypatch.setenv("XSP_LANE_A_PREMIUM_SCALE", "1")
    ok, reason = entry_allowed_by_risk(state, rules_path=DEFAULT_RULES)
    assert ok is False
    assert "scale=1.00x" in (reason or "")
