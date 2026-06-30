"""Helpers for health/soak reporting."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

BASELINE_ZERO_SESSIONS_GRACE_DAYS = 5

REGIME_AXIS_VARIANT_IDS = (
    "v2_baseline_prod",
    "v2_yellow_mid_bounce",
    "v2_yellow_top_quartile_bounce",
)

REGIME_AXIS_COUNTERS = (
    "sessions_evaluated",
    "entered_sessions",
    "regime_gate_skip_sessions",
    "bb_bounce_signal_sessions",
    "bb_bounce_blocked_by_regime_sessions",
    "vol_shadow_would_block_sessions",
    "vol_shadow_latest_spy_rv",
    "vol_shadow_avg_spy_rv",
)


def _parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def regime_axis_comparison_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Counter-only comparison for regime-gate experiment (v4 brief P1)."""
    comparison = payload.get("regime_gate_comparison")
    if not isinstance(comparison, dict):
        return {
            "baseline_variant_id": None,
            "variants": [],
            "has_counter_divergence": False,
        }

    baseline_id = str(comparison.get("baseline_variant_id") or "v2_baseline_prod")
    raw_variants = comparison.get("variants")
    by_id: dict[str, dict[str, Any]] = {}
    if isinstance(raw_variants, list):
        for row in raw_variants:
            if isinstance(row, dict) and row.get("variant_id"):
                by_id[str(row["variant_id"])] = row

    baseline = by_id.get(baseline_id)
    rows: list[dict[str, Any]] = []
    has_divergence = False
    for variant_id in REGIME_AXIS_VARIANT_IDS:
        row = by_id.get(variant_id)
        if row is None:
            continue
        counters = {key: row.get(key) for key in REGIME_AXIS_COUNTERS}
        diff: dict[str, dict[str, Any]] | None = None
        if variant_id != baseline_id and baseline is not None:
            diff = {}
            for key in REGIME_AXIS_COUNTERS:
                b_val = baseline.get(key)
                v_val = row.get(key)
                if b_val != v_val:
                    diff[key] = {"baseline": b_val, "variant": v_val}
            if not diff:
                diff = None
            elif diff:
                has_divergence = True
        rows.append(
            {
                "variant_id": variant_id,
                "regime_gate": row.get("regime_gate"),
                "regime_yellow_frac_min": row.get("regime_yellow_frac_min"),
                "counters": counters,
                "diff_vs_baseline": diff,
            }
        )

    return {
        "baseline_variant_id": baseline_id,
        "variants": rows,
        "has_counter_divergence": has_divergence,
    }


def scoreboard_report_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    baseline = payload.get("baseline_prod")
    baseline_sessions = None
    vol_shadow_latest_spy_rv = None
    vol_shadow_avg_spy_rv = None
    if isinstance(baseline, dict):
        baseline_sessions = baseline.get("sessions_evaluated")
        vol_shadow_latest_spy_rv = baseline.get("vol_shadow_latest_spy_rv")
        vol_shadow_avg_spy_rv = baseline.get("vol_shadow_avg_spy_rv")

    comparison = payload.get("regime_gate_comparison")
    comparison_variants = []
    if isinstance(comparison, dict):
        raw_variants = comparison.get("variants")
        if isinstance(raw_variants, list):
            comparison_variants = [row for row in raw_variants if isinstance(row, dict)]

    regime_axis = regime_axis_comparison_summary(payload)
    baseline_zero_sessions = baseline_zero_sessions_after_grace(payload)
    anomalies: list[str] = []
    if payload.get("stale"):
        anomalies.append("scoreboard_stale")
    if baseline_zero_sessions:
        anomalies.append("baseline_zero_sessions_after_grace")

    return {
        "stale": bool(payload.get("stale")),
        "last_entry_eval_at": payload.get("last_entry_eval_at"),
        "updated_at": payload.get("updated_at"),
        "soak_reset_at": payload.get("soak_reset_at"),
        "baseline_sessions_evaluated": baseline_sessions,
        "regime_gate_comparison_variant_count": len(comparison_variants),
        "regime_axis_summary": regime_axis,
        "vol_shadow_latest_spy_rv": vol_shadow_latest_spy_rv,
        "vol_shadow_avg_spy_rv": vol_shadow_avg_spy_rv,
        "baseline_zero_sessions_after_grace": baseline_zero_sessions,
        "strict_anomalies": anomalies,
    }


def baseline_zero_sessions_after_grace(
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
    grace_days: int = BASELINE_ZERO_SESSIONS_GRACE_DAYS,
) -> bool:
    baseline = payload.get("baseline_prod")
    if not isinstance(baseline, dict):
        return False

    try:
        sessions_evaluated = int(baseline.get("sessions_evaluated") or 0)
    except (TypeError, ValueError):
        return False
    if sessions_evaluated != 0:
        return False

    epoch_at = _parse_timestamp(
        payload.get("soak_reset_at")
        or payload.get("pnl_epoch_at")
        or payload.get("updated_at")
    )
    if epoch_at is None:
        return False

    reference_now = now or datetime.now(timezone.utc)
    return reference_now - epoch_at >= timedelta(days=grace_days)


def detect_strict_anomalies(
    payload: dict[str, Any],
    *,
    pytest_failed: bool = False,
    now: datetime | None = None,
) -> list[str]:
    anomalies: list[str] = []
    if payload.get("stale"):
        anomalies.append("scoreboard_stale")
    if baseline_zero_sessions_after_grace(payload, now=now):
        anomalies.append("baseline_zero_sessions_after_grace")
    if pytest_failed:
        anomalies.append("pytest_failed")
    return anomalies
