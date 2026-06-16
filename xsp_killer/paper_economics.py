"""Paper PnL economics — slippage and commission."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = ROOT / "config" / "lane_a_rules.yaml"


@dataclass
class PaperEconomics:
    commission_usd_per_contract: float
    slippage_pct_of_premium: float

    @classmethod
    def from_yaml(cls, path: Path | None = None) -> PaperEconomics:
        data = yaml.safe_load((path or DEFAULT_RULES).read_text(encoding="utf-8")) or {}
        cfg = data.get("paper_economics") or {}
        return cls(
            commission_usd_per_contract=float(cfg.get("commission_usd_per_contract", 0.65)),
            slippage_pct_of_premium=float(cfg.get("slippage_pct_of_premium", 0.005)),
        )


def entry_fill_premium(mid_premium: float, econ: PaperEconomics) -> float:
    """Effective premium paid per share (mid + slippage + commission/100)."""
    slip = mid_premium * econ.slippage_pct_of_premium
    return round(mid_premium + slip + econ.commission_usd_per_contract / 100.0, 4)


def exit_fill_premium(mid_premium: float, econ: PaperEconomics) -> float:
    """Effective premium received per share (mid - slippage - commission/100)."""
    slip = mid_premium * econ.slippage_pct_of_premium
    return round(max(0.0, mid_premium - slip - econ.commission_usd_per_contract / 100.0), 4)


def pnl_per_contract(
    *,
    entry_mid: float,
    exit_mid: float,
    econ: PaperEconomics,
) -> float:
    """Realized PnL per contract in USD (100 multiplier)."""
    if entry_mid <= 0:
        return 0.0
    entry = entry_fill_premium(entry_mid, econ)
    exit_px = exit_fill_premium(exit_mid, econ)
    return round((exit_px - entry) * 100.0, 2)


def pnl_pct(entry_mid: float, exit_mid: float) -> float | None:
    """Unadjusted return vs entry mid (for mentor 20% gates)."""
    if entry_mid <= 0 or exit_mid is None:
        return None
    return (exit_mid - entry_mid) / entry_mid
