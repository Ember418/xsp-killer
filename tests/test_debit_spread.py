"""Tests for the debit-spread economics prototype."""

from __future__ import annotations

from xsp_killer.debit_spread import (
    build_debit_spread,
    select_short_strike,
    spread_return_pct,
    spread_value,
)


def test_select_short_strike_adds_width():
    assert select_short_strike(750.0, width_strikes=2) == 760.0
    assert select_short_strike(750.0, width_strikes=1) == 755.0


def test_build_debit_spread_happy_path_scaled():
    # 10x paper premiums: long $60, short $40 -> net debit $20 scaled = $2 real.
    s = build_debit_spread(
        long_strike=750.0,
        long_premium=60.0,
        short_strike=760.0,
        short_premium=40.0,
        premium_scale=10.0,
    )
    assert s is not None
    assert s.width_points == 10.0
    assert s.net_debit == 20.0
    assert s.net_debit_1x == 2.0
    assert s.max_value_1x == 10.0
    assert s.max_gain_1x == 8.0
    assert s.breakeven_underlying == 752.0
    assert round(s.cost_reduction_pct, 4) == round(40.0 / 60.0, 4)
    assert s.payoff_ratio == 4.0
    assert s.greek_drag_reduction_est_pct == s.cost_reduction_pct


def test_build_debit_spread_clamps_net_debit_to_width():
    # Incoherent-but-parseable: net debit/scale exceeds width -> clamp to width.
    s = build_debit_spread(
        long_strike=750.0,
        long_premium=80.0,
        short_strike=760.0,
        short_premium=40.0,
        premium_scale=1.0,
    )
    assert s is not None
    assert s.net_debit_1x == 10.0  # clamped to width
    assert s.max_gain_1x == 0.0
    assert s.payoff_ratio == 0.0


def test_build_debit_spread_rejects_incoherent_inputs():
    # width <= 0
    assert (
        build_debit_spread(
            long_strike=760.0,
            long_premium=60.0,
            short_strike=750.0,
            short_premium=40.0,
        )
        is None
    )
    # net debit <= 0 (short premium >= long)
    assert (
        build_debit_spread(
            long_strike=750.0,
            long_premium=40.0,
            short_strike=760.0,
            short_premium=40.0,
        )
        is None
    )
    # non-positive long premium
    assert (
        build_debit_spread(
            long_strike=750.0,
            long_premium=0.0,
            short_strike=760.0,
            short_premium=0.0,
        )
        is None
    )
    # missing premiums
    assert (
        build_debit_spread(
            long_strike=750.0,
            long_premium=None,
            short_strike=760.0,
            short_premium=40.0,
        )
        is None
    )


def test_spread_value_clamps_to_band():
    assert spread_value(long_mark=6.0, short_mark=4.0, width=10.0) == 2.0
    # Above width -> clamped to width.
    assert spread_value(long_mark=20.0, short_mark=5.0, width=10.0) == 10.0
    # Negative net -> clamped to zero.
    assert spread_value(long_mark=3.0, short_mark=5.0, width=10.0) == 0.0


def test_spread_return_pct():
    # entry net debit 2.0, now worth 4.0 -> +100%.
    r = spread_return_pct(net_debit=2.0, long_mark=8.0, short_mark=4.0, width=10.0)
    assert r == 1.0
    assert (
        spread_return_pct(net_debit=0.0, long_mark=8.0, short_mark=4.0, width=10.0)
        is None
    )
