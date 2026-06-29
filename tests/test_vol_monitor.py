"""Tests for shadow vol gate."""

from __future__ import annotations

from xsp_killer.vol_monitor import evaluate_shadow_vol_gate, spy_realized_vol_annualized


def test_spy_rv_computes_from_closes(monkeypatch):
    closes = [100.0 + i * 0.1 for i in range(30)]

    def _fake_fetch(_days):
        return closes

    monkeypatch.setattr("xsp_killer.vol_monitor._fetch_spy_closes", _fake_fetch)
    rv = spy_realized_vol_annualized(lookback_days=21)
    assert rv is not None
    assert rv > 0


def test_shadow_gate_never_enforces(monkeypatch):
    monkeypatch.setattr(
        "xsp_killer.vol_monitor.spy_realized_vol_annualized",
        lambda **_: 0.99,
    )
    gate = evaluate_shadow_vol_gate(rv_threshold=0.28)
    assert gate.shadow_would_block is True
    assert gate.enforcing is False


def test_shadow_gate_insufficient_history(monkeypatch):
    monkeypatch.setattr(
        "xsp_killer.vol_monitor.spy_realized_vol_annualized",
        lambda **_: None,
    )
    gate = evaluate_shadow_vol_gate()
    assert gate.shadow_would_block is False
    assert "insufficient" in gate.reason
