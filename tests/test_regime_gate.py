from __future__ import annotations

from xsp_killer.lane_a_monitor import regime_gate_allows


def test_green_gate_allows_green_only():
    ok, reason = regime_gate_allows(
        regime_gate="GREEN",
        regime="GREEN",
        regime_ok=True,
        yellow_frac=None,
        ta_entry_ok=False,
    )
    assert ok is True
    assert reason is None

    ok, reason = regime_gate_allows(
        regime_gate="GREEN",
        regime="YELLOW",
        regime_ok=False,
        yellow_frac=0.9,
        ta_entry_ok=True,
    )
    assert ok is False
    assert reason == "regime YELLOW blocks new risk"


def test_yellow_gate_allows_top_quartile_bounce():
    ok, reason = regime_gate_allows(
        regime_gate="GREEN_OR_YELLOW_BOUNCE",
        regime="YELLOW",
        regime_ok=False,
        yellow_frac=0.8,
        ta_entry_ok=True,
        yellow_frac_min=0.75,
    )
    assert ok is True
    assert reason is None


def test_yellow_gate_blocks_low_fraction():
    ok, reason = regime_gate_allows(
        regime_gate="GREEN_OR_YELLOW_BOUNCE",
        regime="YELLOW",
        regime_ok=False,
        yellow_frac=0.5,
        ta_entry_ok=True,
        yellow_frac_min=0.75,
    )
    assert ok is False
    assert reason == "regime YELLOW blocks new risk: yellow_frac 0.50 < 0.75"


def test_yellow_gate_allows_mid_fraction_at_half():
    ok, reason = regime_gate_allows(
        regime_gate="GREEN_OR_YELLOW_BOUNCE",
        regime="YELLOW",
        regime_ok=False,
        yellow_frac=0.5,
        ta_entry_ok=True,
        yellow_frac_min=0.50,
    )
    assert ok is True
    assert reason is None


def test_yellow_gate_blocks_below_mid_fraction():
    ok, reason = regime_gate_allows(
        regime_gate="GREEN_OR_YELLOW_BOUNCE",
        regime="YELLOW",
        regime_ok=False,
        yellow_frac=0.49,
        ta_entry_ok=True,
        yellow_frac_min=0.50,
    )
    assert ok is False
    assert reason == "regime YELLOW blocks new risk: yellow_frac 0.49 < 0.50"


def test_yellow_gate_blocks_red_regime():
    ok, reason = regime_gate_allows(
        regime_gate="GREEN_OR_YELLOW_BOUNCE",
        regime="RED",
        regime_ok=False,
        yellow_frac=None,
        ta_entry_ok=True,
        yellow_frac_min=0.75,
    )
    assert ok is False
    assert reason == "regime RED blocks new risk"
