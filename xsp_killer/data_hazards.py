"""K129-style hazard tags and MCP confidence wrapper (observability only)."""

from __future__ import annotations

from typing import Any

# Recoverable tool-reliability hazard classes (ToolBench-X rubric subset).
OUTPUT_DRIFT = "output_drift"
EXECUTION_FAILURE = "execution_failure"
CROSS_SOURCE_CONFLICT = "cross_source_conflict"

# MCP confidence contract (Robust-TO / prod-mcp checklist).
HAZARD_NONE = "none"
HAZARD_SPEC_DRIFT = "spec_drift"
HAZARD_EXEC_FAIL = "exec_fail"
HAZARD_OUTPUT_DRIFT = "output_drift"
HAZARD_CONFLICT = "conflict"

CONFIDENCE_TIER_HIGH = 0.85
CONFIDENCE_TIER_LOW = 0.35


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


def wrap_tool_result(
    result: Any,
    *,
    confidence: float,
    signals: list[str] | None = None,
    hazard_class: str = HAZARD_NONE,
) -> dict[str, Any]:
    """Robust-TO wrapper: {result, confidence, signals, hazard_class}."""
    return {
        "result": result,
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
        "signals": list(signals or []),
        "hazard_class": hazard_class,
    }


def unwrap_tool_result(payload: Any) -> Any:
    """Return inner result when payload is a confidence wrapper."""
    if isinstance(payload, dict) and "result" in payload and "confidence" in payload:
        return payload["result"]
    return payload


def fusion_tier(confidence: float) -> str:
    """Map confidence to HIGH / MEDIUM / LOW synthesis tier."""
    if confidence >= CONFIDENCE_TIER_HIGH:
        return "HIGH"
    if confidence >= CONFIDENCE_TIER_LOW:
        return "MEDIUM"
    return "LOW"


def mcp_read_trusted(wrapped: dict[str, Any] | None) -> bool:
    """LOW-tier MCP reads must not drive monitor decisions."""
    if not wrapped:
        return False
    return fusion_tier(float(wrapped.get("confidence") or 0.0)) != "LOW"


def classify_mcp_read_confidence(
    result: Any,
    *,
    tool: str,
    error: str | None = None,
) -> tuple[float, str, list[str]]:
    """Calibrate MCP read-path confidence before fusion."""
    signals = [f"tool:{tool}"]
    if error:
        return 0.15, HAZARD_EXEC_FAIL, signals + ["error"]
    if result is None:
        return 0.2, HAZARD_EXEC_FAIL, signals + ["null_result"]

    if tool == "get_option_positions":
        rows: list[Any]
        if isinstance(result, list):
            rows = result
        elif isinstance(result, dict):
            raw = result.get("results") or result.get("positions") or result.get("data")
            rows = list(raw.values()) if isinstance(raw, dict) else (raw or [])
        else:
            return 0.4, HAZARD_OUTPUT_DRIFT, signals + ["unexpected_type"]
        if not rows:
            return 0.65, HAZARD_NONE, signals + ["empty_positions"]
        schema_ok = all(
            isinstance(row, dict)
            and str(row.get("chain_symbol") or row.get("underlying_symbol") or "")
            for row in rows
        )
        if not schema_ok:
            return 0.45, HAZARD_OUTPUT_DRIFT, signals + ["schema_incomplete"]
        return 0.92, HAZARD_NONE, signals + ["schema_ok"]

    if isinstance(result, (list, dict)):
        return 0.85, HAZARD_NONE, signals + ["structured_ok"]
    return 0.5, HAZARD_OUTPUT_DRIFT, signals + ["unexpected_type"]
