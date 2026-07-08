"""Tests for the deterministic live-order pre-trade reviewer gate."""

from __future__ import annotations

from typing import Any

from xsp_killer.conductor_reviewer import (
    live_reviewer_enabled,
    review_live_order,
)


def _contract(**over: Any) -> dict[str, Any]:
    base = {
        "instrument_id": "abc",
        "strike": 750.0,
        "expiration_date": "2026-07-27",
        "dte": 20,
        "bid": 6.0,
        "ask": 6.2,
        "mark": 6.1,
    }
    base.update(over)
    return base


def _kw(**over: Any) -> dict[str, Any]:
    base = {
        "contract": _contract(),
        "limit_price": 6.2,
        "quantity": 1,
        "cost": 620.0,
        "est_max_loss": 124.0,
        "buying_power": 2000.0,
        "max_loss_usd": 150.0,
        "max_cost_frac": 0.5,
        "dte_min": 14,
        "dte_max": 60,
    }
    base.update(over)
    return base


def test_reviewer_approves_clean_order():
    d = review_live_order(**_kw())
    assert d.approved is True
    assert d.decision == "approve"
    assert d.checks["spread_frac"] <= 0.25


def test_reviewer_vetoes_wide_spread():
    d = review_live_order(**_kw(contract=_contract(bid=4.0, ask=6.2)))
    assert d.decision == "veto"
    assert "spread" in d.reason


def test_reviewer_vetoes_crossed_market():
    d = review_live_order(**_kw(contract=_contract(bid=6.5, ask=6.2)))
    assert d.decision == "veto"
    assert "crossed" in d.reason


def test_reviewer_vetoes_missing_ask():
    d = review_live_order(**_kw(contract=_contract(ask=0.0)))
    assert d.decision == "veto"
    assert "ask" in d.reason


def test_reviewer_vetoes_limit_above_ask_fat_finger():
    d = review_live_order(**_kw(limit_price=7.0))
    assert d.decision == "veto"
    assert "fat-finger" in d.reason


def test_reviewer_vetoes_quantity_out_of_band():
    d = review_live_order(**_kw(quantity=6))
    assert d.decision == "veto"
    assert "quantity" in d.reason


def test_reviewer_vetoes_cost_mismatch():
    d = review_live_order(**_kw(cost=999.0))
    assert d.decision == "veto"
    assert "cost mismatch" in d.reason


def test_reviewer_vetoes_insufficient_buying_power():
    d = review_live_order(**_kw(buying_power=100.0))
    assert d.decision == "veto"
    assert "buying power" in d.reason


def test_reviewer_vetoes_cost_fraction_exceeded():
    d = review_live_order(**_kw(buying_power=1000.0))
    assert d.decision == "veto"
    assert "of BP" in d.reason


def test_reviewer_vetoes_est_max_loss_exceeded():
    d = review_live_order(**_kw(est_max_loss=200.0))
    assert d.decision == "veto"
    assert "max loss" in d.reason


def test_reviewer_vetoes_dte_out_of_band():
    d = review_live_order(**_kw(contract=_contract(dte=5)))
    assert d.decision == "veto"
    assert "DTE" in d.reason


def test_reviewer_vetoes_unknown_dte():
    d = review_live_order(**_kw(contract=_contract(dte=None)))
    assert d.decision == "veto"
    assert "DTE unknown" in d.reason


def test_live_reviewer_enabled_toggle(monkeypatch):
    monkeypatch.delenv("XSP_LANE_A_LIVE_REVIEWER", raising=False)
    assert live_reviewer_enabled() is True
    monkeypatch.setenv("XSP_LANE_A_LIVE_REVIEWER", "false")
    assert live_reviewer_enabled() is False
    monkeypatch.setenv("XSP_LANE_A_LIVE_REVIEWER", "true")
    assert live_reviewer_enabled() is True
