"""Tests for shadow vol gate."""

from __future__ import annotations

from pathlib import Path

from xsp_killer.vol_monitor import (
    evaluate_shadow_vol_gate,
    evaluate_vix_spike_shadow,
    session_premium_scale,
    spy_realized_vol_annualized,
    vix_spike_entry_veto,
    vix_spike_veto_enabled,
)


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
    monkeypatch.setattr(
        "xsp_killer.vol_monitor.evaluate_vix_spike_shadow",
        lambda **_: {
            "vix_level": 15.0,
            "vix_median_20d": 14.0,
            "vix_spike_ratio": 1.07,
            "vix_trending_down": True,
            "shadow_would_halve_size": False,
            "shadow_premium_scale_multiplier": 1.0,
            "vix_shadow_reason": "ok",
        },
    )
    gate = evaluate_shadow_vol_gate(rv_threshold=0.28)
    assert gate.shadow_would_block is True
    assert gate.enforcing is False


def test_shadow_gate_insufficient_history(monkeypatch):
    monkeypatch.setattr(
        "xsp_killer.vol_monitor.spy_realized_vol_annualized",
        lambda **_: None,
    )
    monkeypatch.setattr(
        "xsp_killer.vol_monitor.evaluate_vix_spike_shadow",
        lambda **_: {
            "vix_level": None,
            "vix_median_20d": None,
            "vix_spike_ratio": None,
            "vix_trending_down": None,
            "shadow_would_halve_size": False,
            "shadow_premium_scale_multiplier": 1.0,
            "vix_shadow_reason": "insufficient_vix_history",
        },
    )
    gate = evaluate_shadow_vol_gate()
    assert gate.shadow_would_block is False
    assert "insufficient" in gate.reason


def test_vix_spike_halve_without_downtrend(monkeypatch):
    closes = [10.0] * 24 + [18.0, 32.0]

    monkeypatch.setattr("xsp_killer.vol_monitor._fetch_vix_closes", lambda _d: closes)
    snap = evaluate_vix_spike_shadow()
    assert snap["shadow_would_halve_size"] is True
    assert snap["shadow_premium_scale_multiplier"] == 0.5
    assert snap["vix_spike_ratio"] >= 2.0


def test_vix_spike_ok_with_downtrend_confirm(monkeypatch):
    closes = [10.0] * 20 + [40.0, 35.0, 30.0, 28.0, 26.0, 24.0]

    monkeypatch.setattr("xsp_killer.vol_monitor._fetch_vix_closes", lambda _d: closes)
    snap = evaluate_vix_spike_shadow()
    assert snap["vix_trending_down"] is True
    assert snap["shadow_would_halve_size"] is False
    assert snap["shadow_premium_scale_multiplier"] == 1.0


def test_session_premium_scale_halve_when_enforced(tmp_path):
    rules = tmp_path / "rules.yaml"
    rules.write_text(
        "vol_shadow:\n  enforce_vix_halve_on_sizing: true\n",
        encoding="utf-8",
    )
    vol_shadow = {"shadow_premium_scale_multiplier": 0.5}
    assert (
        session_premium_scale(base_scale=10.0, vol_shadow=vol_shadow, rules_path=rules)
        == 5.0
    )


def test_session_premium_scale_unchanged_when_not_enforced(tmp_path):
    rules = tmp_path / "rules.yaml"
    rules.write_text(
        "vol_shadow:\n  enforce_vix_halve_on_sizing: false\n",
        encoding="utf-8",
    )
    vol_shadow = {"shadow_premium_scale_multiplier": 0.5}
    assert (
        session_premium_scale(base_scale=10.0, vol_shadow=vol_shadow, rules_path=rules)
        == 10.0
    )


def test_vol_shadow_config_from_rules_yaml(tmp_path, monkeypatch):
    rules = tmp_path / "rules.yaml"
    rules.write_text(
        "vol_shadow:\n  vix_spike_ratio_halve: 3.0\n  rv_threshold: 0.35\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "xsp_killer.vol_monitor.spy_realized_vol_annualized",
        lambda **_: 0.10,
    )

    def _fake_vix(**kwargs):
        assert kwargs["spike_ratio_halve"] == 3.0
        return {
            "vix_level": 12.0,
            "vix_median_20d": 11.0,
            "vix_spike_ratio": 1.1,
            "vix_trending_down": False,
            "shadow_would_halve_size": False,
            "shadow_premium_scale_multiplier": 1.0,
            "vix_shadow_reason": "ok",
        }

    monkeypatch.setattr(
        "xsp_killer.vol_monitor.evaluate_vix_spike_shadow",
        _fake_vix,
    )
    gate = evaluate_shadow_vol_gate(rules_path=Path(rules))
    assert gate.rv_threshold == 0.35


def _veto_rules(tmp_path, enabled: bool) -> Path:
    rules = tmp_path / "rules.yaml"
    rules.write_text(
        f"vol_shadow:\n  veto_entry_on_vix_spike: {str(enabled).lower()}\n",
        encoding="utf-8",
    )
    return rules


def test_vix_spike_veto_disabled_by_default(tmp_path):
    rules = tmp_path / "rules.yaml"
    rules.write_text("vol_shadow: {}\n", encoding="utf-8")
    assert vix_spike_veto_enabled(rules_path=rules) is False
    spiking = {"shadow_would_halve_size": True, "vix_spike_ratio": 2.4}
    assert vix_spike_entry_veto(spiking, rules_path=rules) is None


def test_vix_spike_veto_blocks_when_enabled_and_spiking(tmp_path):
    rules = _veto_rules(tmp_path, True)
    assert vix_spike_veto_enabled(rules_path=rules) is True
    spiking = {
        "shadow_would_halve_size": True,
        "vix_spike_ratio": 2.4,
        "vix_shadow_reason": "vix_spike_2.40x_gte_2.00x_no_downtrend_confirm",
    }
    reason = vix_spike_entry_veto(spiking, rules_path=rules)
    assert reason is not None
    assert reason.startswith("vix_spike_veto:")
    assert "2.40x" in reason


def test_vix_spike_veto_allows_when_no_spike(tmp_path):
    rules = _veto_rules(tmp_path, True)
    calm = {"shadow_would_halve_size": False, "vix_spike_ratio": 1.1}
    assert vix_spike_entry_veto(calm, rules_path=rules) is None
    assert vix_spike_entry_veto(None, rules_path=rules) is None
