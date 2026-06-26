"""Paper PnL economics — slippage and commission."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = ROOT / "config" / "lane_a_rules.yaml"

# SPY option chain mid → XSP notional premium (1/10th index, ~10× per-share premium).
SPY_TO_XSP_PREMIUM_SCALE = 10.0


@dataclass
class PaperEconomics:
    commission_usd_per_contract: float
    slippage_pct_of_premium: float
    slippage_usd_per_share: float
    slippage_max_pct_of_premium: float

    @classmethod
    def from_yaml(cls, path: Path | None = None) -> PaperEconomics:
        data = yaml.safe_load((path or DEFAULT_RULES).read_text(encoding="utf-8")) or {}
        cfg = data.get("paper_economics") or {}
        return cls(
            commission_usd_per_contract=float(
                cfg.get("commission_usd_per_contract", 0.65)
            ),
            slippage_pct_of_premium=float(cfg.get("slippage_pct_of_premium", 0.005)),
            slippage_usd_per_share=float(cfg.get("slippage_usd_per_share", 0.12)),
            slippage_max_pct_of_premium=float(
                cfg.get("slippage_max_pct_of_premium", 0.015)
            ),
        )


def _slippage_per_share(mid_premium: float, econ: PaperEconomics) -> float:
    pct_slip = mid_premium * econ.slippage_pct_of_premium
    capped_pct = min(pct_slip, mid_premium * econ.slippage_max_pct_of_premium)
    return max(econ.slippage_usd_per_share, capped_pct)


def entry_fill_premium(mid_premium: float, econ: PaperEconomics) -> float:
    """Effective premium paid per share (mid + slippage + commission/100)."""
    slip = _slippage_per_share(mid_premium, econ)
    return round(mid_premium + slip + econ.commission_usd_per_contract / 100.0, 4)


def exit_fill_premium(mid_premium: float, econ: PaperEconomics) -> float:
    """Effective premium received per share (mid - slippage - commission/100)."""
    slip = _slippage_per_share(mid_premium, econ)
    return round(
        max(0.0, mid_premium - slip - econ.commission_usd_per_contract / 100.0), 4
    )


def pnl_per_contract(
    *,
    entry_mid: float,
    exit_mid: float,
    econ: PaperEconomics,
) -> float:
    """Realized PnL per contract in USD when entry is a raw mid (applies both legs)."""
    if entry_mid <= 0:
        return 0.0
    entry = entry_fill_premium(entry_mid, econ)
    return pnl_from_entry_fill(entry_fill=entry, exit_mid=exit_mid, econ=econ)


def pnl_from_entry_fill(
    *,
    entry_fill: float,
    exit_mid: float,
    econ: PaperEconomics,
) -> float:
    """Realized PnL when entry economics are already baked into entry_fill."""
    if entry_fill <= 0:
        return 0.0
    exit_px = exit_fill_premium(exit_mid, econ)
    return round((exit_px - entry_fill) * 100.0, 2)


def pnl_pct(entry_mid: float, exit_mid: float) -> float | None:
    """Unadjusted return vs entry mid (for mentor 20% gates)."""
    if entry_mid <= 0 or exit_mid is None:
        return None
    return (exit_mid - entry_mid) / entry_mid
