"""Deterministic pre-trade second-opinion gate for live buy-to-open orders.

Ported in spirit from Cemini ``conductor/reviewer`` (an LLM approve/revise
reviewer) but re-cast as a *deterministic, fail-closed* gate: for a $1k live
account an LLM that fails **open** on timeout is the wrong safety model. This
reviewer re-derives sanity from the concrete contract quote + account state
(a genuine second opinion) so a bug in the entry pipeline's selection or
sizing cannot silently route a bad live order.

Invariants:
- Fail-closed: any required field that is missing/unparseable returns
  ``decision="veto"`` (never approve on uncertainty).
- Pure/read-only: never mutates the order or places anything; returns an
  approve/veto verdict plus per-check detail for the audit log.
- Independent second opinion: recomputes cost, spread, and price sanity from
  the contract's own bid/ask/mark rather than trusting upstream values.
- Advisory in paper: only the live buy-to-open path consults it; disabling it
  via ``XSP_LANE_A_LIVE_REVIEWER=false`` is an explicit operator choice.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

DEFAULT_MAX_SPREAD_FRAC = 0.25
DEFAULT_MAX_CONTRACTS = 5
DEFAULT_LIMIT_OVER_ASK_TOL = 0.01  # never pay more than ask + 1% (fat-finger guard)


@dataclass
class ReviewerDecision:
    decision: Literal["approve", "veto"]
    reason: str | None = None
    checks: dict[str, Any] = field(default_factory=dict)

    @property
    def approved(self) -> bool:
        return self.decision == "approve"

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "checks": self.checks,
        }


def live_reviewer_enabled() -> bool:
    """True unless explicitly disabled — the live gate is opt-out, not opt-in."""
    return os.getenv("XSP_LANE_A_LIVE_REVIEWER", "true").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def review_live_order(
    *,
    contract: dict[str, Any],
    limit_price: float,
    quantity: int,
    cost: float,
    est_max_loss: float,
    buying_power: float,
    max_loss_usd: float,
    max_cost_frac: float,
    dte_min: int,
    dte_max: int,
    max_spread_frac: float = DEFAULT_MAX_SPREAD_FRAC,
    max_contracts: int = DEFAULT_MAX_CONTRACTS,
) -> ReviewerDecision:
    """Approve/veto a concrete live buy-to-open, fail-closed on any bad input."""
    checks: dict[str, Any] = {}

    def veto(reason: str, **extra: Any) -> ReviewerDecision:
        checks.update(extra)
        return ReviewerDecision(decision="veto", reason=reason, checks=checks)

    bid = _to_float(contract.get("bid"))
    ask = _to_float(contract.get("ask"))
    mark = _to_float(contract.get("mark"))
    limit_price = _to_float(limit_price) or 0.0
    checks.update({"bid": bid, "ask": ask, "mark": mark, "limit_price": limit_price})

    # 1) Quote completeness / not crossed.
    if ask is None or ask <= 0:
        return veto("reviewer_veto: missing/invalid ask")
    if bid is None or bid < 0:
        return veto("reviewer_veto: missing/invalid bid")
    if ask < bid:
        return veto(f"reviewer_veto: crossed market (bid {bid} > ask {ask})")

    # 2) Mid + spread (liquidity) — reject illiquid, blown-out markets.
    mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else mark
    if mid is None or mid <= 0:
        return veto("reviewer_veto: no positive mid/mark")
    spread_frac = round((ask - bid) / mid, 4)
    checks["mid"] = round(mid, 4)
    checks["spread_frac"] = spread_frac
    if spread_frac > max_spread_frac:
        return veto(
            f"reviewer_veto: spread {spread_frac:.0%} > max {max_spread_frac:.0%}"
        )

    # 3) Limit-price sanity — never pay meaningfully above the ask (fat-finger).
    if limit_price <= 0:
        return veto("reviewer_veto: non-positive limit price")
    if limit_price > ask * (1.0 + DEFAULT_LIMIT_OVER_ASK_TOL):
        return veto(f"reviewer_veto: limit {limit_price} above ask {ask} (fat-finger)")
    checks["limit_over_mid_frac"] = round((limit_price - mid) / mid, 4)

    # 4) Quantity sanity.
    if quantity < 1 or quantity > max_contracts:
        return veto(f"reviewer_veto: quantity {quantity} outside [1, {max_contracts}]")

    # 5) Cost / loss re-derivation (defense-in-depth second opinion).
    recomputed_cost = round(limit_price * 100.0 * quantity, 2)
    checks["recomputed_cost"] = recomputed_cost
    checks["cost_estimate"] = round(cost, 2)
    if abs(recomputed_cost - cost) > max(0.01, 0.001 * recomputed_cost):
        return veto(
            f"reviewer_veto: cost mismatch (recomputed {recomputed_cost} "
            f"vs passed {round(cost, 2)})"
        )
    if buying_power is None or buying_power <= 0:
        return veto("reviewer_veto: non-positive buying power")
    if cost > buying_power:
        return veto(
            f"reviewer_veto: cost ${cost:,.0f} > buying power ${buying_power:,.0f}"
        )
    if max_cost_frac and cost > max_cost_frac * buying_power:
        return veto(
            f"reviewer_veto: cost ${cost:,.0f} exceeds {max_cost_frac:.0%} of BP"
        )
    if est_max_loss > max_loss_usd:
        return veto(
            f"reviewer_veto: est max loss ${est_max_loss:,.0f} "
            f"> cap ${max_loss_usd:,.0f}"
        )

    # 6) DTE band (the live contract must match the strategy's window).
    dte = contract.get("dte")
    dte_i = int(dte) if isinstance(dte, (int, float)) else None
    checks["dte"] = dte_i
    if dte_i is None:
        return veto("reviewer_veto: contract DTE unknown")
    if dte_i < dte_min or dte_i > dte_max:
        return veto(f"reviewer_veto: DTE {dte_i} outside [{dte_min}, {dte_max}]")

    return ReviewerDecision(decision="approve", reason=None, checks=checks)
