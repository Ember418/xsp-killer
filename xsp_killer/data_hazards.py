"""K129-style hazard tags for market data paths (observability only)."""

from __future__ import annotations

# Recoverable tool-reliability hazard classes (ToolBench-X rubric subset).
OUTPUT_DRIFT = "output_drift"
EXECUTION_FAILURE = "execution_failure"
CROSS_SOURCE_CONFLICT = "cross_source_conflict"


def classify_chain_hazard(stale_reason: str | None) -> str | None:
    """Map SPY chain quote stale_reason to a hazard class."""
    if not stale_reason:
        return None
    reason = stale_reason.lower()
    if reason == "empty_chain":
        return EXECUTION_FAILURE
    if "mark_jump" in reason or "implied_gain" in reason or "implied_loss" in reason:
        return OUTPUT_DRIFT
    if "timeout" in reason or "failed" in reason:
        return EXECUTION_FAILURE
    return EXECUTION_FAILURE


def classify_regime_hazard(reason: str | None) -> str | None:
    """Map macro regime fetch failures to hazard class."""
    if not reason:
        return None
    if "insufficient" in reason.lower() or "defensive default" in reason.lower():
        return EXECUTION_FAILURE
    return None
