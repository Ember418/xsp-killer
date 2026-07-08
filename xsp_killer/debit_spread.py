"""Debit call-spread economics (prototype) — quantify a long-call replacement.

The dip-swing thesis pays theta/vega on a naked long call. A call *debit
spread* (long a near-ATM call, short a higher-strike call, same expiry) trades
capped upside for a lower net debit and materially lower theta/vega drag. This
module models that structure from real chain premiums so the soak can measure
whether it is worth wiring into the full paper/live lifecycle.

Scale note: the two leg premiums must be in the SAME scale (the paper book's
SPY->XSP ``premium_scale``). Cost/greek-reduction metrics are ratios (scale
invariant); absolute payoff (net debit, breakeven, max value) is reported in
real 1x points via ``premium_scale`` so it lines up with index-point width.

Invariants:
- Pure functions: no I/O, no order placement; callers supply leg premiums.
- Call debit spread requires long_strike < short_strike (width > 0).
- Net debit is positive and, in 1x terms, bounded above by the width; the
  clamp is enforced so a bad quote can't imply a free/over-wide spread.
- Shadow/analysis only: this module never trades.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

XSP_STRIKE_STEP = 5.0


def select_short_strike(
    long_strike: float,
    *,
    width_strikes: int = 2,
    strike_step: float = XSP_STRIKE_STEP,
) -> float:
    """Higher call strike for the short leg: long + width * step (index points)."""
    return long_strike + max(1, int(width_strikes)) * strike_step


@dataclass
class DebitSpread:
    long_strike: float
    short_strike: float
    width_points: float
    long_premium: float
    short_premium: float
    net_debit: float
    premium_scale: float
    net_debit_1x: float
    max_value_1x: float
    max_gain_1x: float
    breakeven_underlying: float
    cost_reduction_pct: float
    payoff_ratio: float
    greek_drag_reduction_est_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_debit_spread(
    *,
    long_strike: float,
    long_premium: float,
    short_strike: float,
    short_premium: float,
    premium_scale: float = 1.0,
) -> DebitSpread | None:
    """Model a call debit spread from two leg premiums (same scale).

    Returns None when inputs are incoherent (non-positive premiums, width<=0,
    or a short premium >= long premium so the net debit is not positive).
    """
    if long_premium is None or short_premium is None:
        return None
    if long_premium <= 0 or short_premium < 0:
        return None
    width = round(short_strike - long_strike, 4)
    if width <= 0:
        return None
    net_debit = round(long_premium - short_premium, 4)
    if net_debit <= 0:
        return None
    scale = premium_scale if premium_scale and premium_scale > 0 else 1.0
    # Convert the premium-scaled net debit to real 1x points so it is
    # comparable with the index-point width; clamp into (0, width].
    net_debit_1x = round(min(net_debit / scale, width), 4)
    max_value_1x = round(width, 4)
    max_gain_1x = round(max_value_1x - net_debit_1x, 4)
    breakeven = round(long_strike + net_debit_1x, 4)
    cost_reduction_pct = round(short_premium / long_premium, 4)
    payoff_ratio = round(max_gain_1x / net_debit_1x, 4) if net_debit_1x > 0 else 0.0
    # First-order estimate: the short leg offsets theta/vega roughly in
    # proportion to the fraction of the long premium it recovers.
    greek_drag_reduction_est_pct = cost_reduction_pct
    return DebitSpread(
        long_strike=round(long_strike, 4),
        short_strike=round(short_strike, 4),
        width_points=width,
        long_premium=round(long_premium, 4),
        short_premium=round(short_premium, 4),
        net_debit=net_debit,
        premium_scale=round(scale, 4),
        net_debit_1x=net_debit_1x,
        max_value_1x=max_value_1x,
        max_gain_1x=max_gain_1x,
        breakeven_underlying=breakeven,
        cost_reduction_pct=cost_reduction_pct,
        payoff_ratio=payoff_ratio,
        greek_drag_reduction_est_pct=greek_drag_reduction_est_pct,
    )


def spread_value(*, long_mark: float, short_mark: float, width: float) -> float:
    """Net mark of the spread, clamped to [0, width] (for future exit logic)."""
    v = long_mark - short_mark
    return min(max(v, 0.0), width)


def spread_return_pct(
    *,
    net_debit: float,
    long_mark: float,
    short_mark: float,
    width: float,
) -> float | None:
    """Return vs entry net debit; None when net debit is non-positive."""
    if net_debit <= 0:
        return None
    value = spread_value(long_mark=long_mark, short_mark=short_mark, width=width)
    return (value - net_debit) / net_debit
