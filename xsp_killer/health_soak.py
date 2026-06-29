"""Helpers for health/soak reporting."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

BASELINE_ZERO_SESSIONS_GRACE_DAYS = 5


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


def scoreboard_report_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    baseline = payload.get("baseline_prod")
    baseline_sessions = None
    if isinstance(baseline, dict):
        baseline_sessions = baseline.get("sessions_evaluated")

    comparison = payload.get("regime_gate_comparison")
    comparison_variants = []
    if isinstance(comparison, dict):
        raw_variants = comparison.get("variants")
        if isinstance(raw_variants, list):
            comparison_variants = [row for row in raw_variants if isinstance(row, dict)]

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
