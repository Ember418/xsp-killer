"""Paper economics slippage model and premium scale."""

from __future__ import annotations

import yaml

from xsp_killer.paper_economics import (
    DEFAULT_PREMIUM_SCALE,
    PaperEconomics,
    dual_notional_from_spy_mid,
    entry_fill_premium,
    load_premium_scale,
    scale_spy_premium,
    _cached_premium_scale,
)


def test_slippage_capped_for_expensive_premium():
    econ = PaperEconomics(
        commission_usd_per_contract=0.65,
        slippage_pct_of_premium=0.005,
        slippage_usd_per_share=0.12,
        slippage_max_pct_of_premium=0.015,
    )
    fill = entry_fill_premium(61.0, econ)
    slip = fill - 61.0 - econ.commission_usd_per_contract / 100.0
    assert slip <= 61.0 * 0.015 + 0.001
    assert slip >= 0.12


def test_premium_scale_from_yaml(tmp_path, monkeypatch):
    monkeypatch.delenv("XSP_LANE_A_PREMIUM_SCALE", raising=False)
    rules = tmp_path / "lane_a_rules.yaml"
    rules.write_text(
        yaml.safe_dump(
            {"paper_economics": {"premium_scale": 7.5}},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    _cached_premium_scale.cache_clear()
    assert load_premium_scale(rules) == 7.5
    econ = PaperEconomics.from_yaml(rules)
    assert econ.premium_scale == 7.5


def test_premium_scale_env_override(tmp_path, monkeypatch):
    rules = tmp_path / "lane_a_rules.yaml"
    rules.write_text(
        yaml.safe_dump({"paper_economics": {"premium_scale": 7.5}}, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.setenv("XSP_LANE_A_PREMIUM_SCALE", "12.0")
    _cached_premium_scale.cache_clear()
    assert load_premium_scale(rules) == 12.0


def test_dual_notional_logs_primary_and_1x():
    dual = dual_notional_from_spy_mid(6.0, scale=10.0)
    assert dual["premium_scale_used"] == 10.0
    assert dual["mark_xsp_scaled"] == 60.0
    assert dual["mark_xsp_alt_1x"] == 6.0


def test_scale_spy_premium_default():
    assert scale_spy_premium(5.0, scale=DEFAULT_PREMIUM_SCALE) == 50.0
