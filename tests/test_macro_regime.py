"""Tests for macro regime hazard tagging."""

from __future__ import annotations

from xsp_killer.macro_regime import RegimeState, classify_regime


def test_insufficient_spy_data_tags_execution_failure(monkeypatch):
    monkeypatch.setattr("xsp_killer.macro_regime._fetch_close", lambda _t: None)
    state = classify_regime()
    assert state.regime == "RED"
    assert state.data_hazard == "execution_failure"


def test_regime_state_serializes_data_hazard():
    state = RegimeState(
        regime="GREEN",
        spy_price=600.0,
        ema21=590.0,
        sma50=580.0,
        yellow_frac=None,
        jnk_tlt_flag=False,
        confidence=0.9,
        timestamp=1.0,
        reason="test",
        data_hazard=None,
    )
    assert state.to_dict()["data_hazard"] is None
