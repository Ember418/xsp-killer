"""Helpers for health/soak reporting."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from xsp_killer.lane_a_variants import PROMOTION_ENTERED_SESSIONS_GATE

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


def promotion_proximity_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Surface v4 brief promotion gate progress (informational only)."""
    promo = payload.get("promotion_summary")
    if not isinstance(promo, dict):
        promo = {}
    baseline = payload.get("baseline_prod")
    baseline_row = baseline if isinstance(baseline, dict) else {}
    shadow_rows = payload.get("shadow_variants")
    near_gate: list[str] = []
    if isinstance(shadow_rows, list):
        for row in shadow_rows:
            if not isinstance(row, dict):
                continue
            try:
                remaining = int(row.get("sessions_to_promotion_gate") or 0)
            except (TypeError, ValueError):
                remaining = 999
            if remaining <= 2:
                vid = row.get("variant_id")
                if vid:
                    near_gate.append(str(vid))
    baseline_remaining = baseline_row.get("sessions_to_promotion_gate")
    entered_remaining = baseline_row.get("entered_sessions_to_promotion_gate")
    try:
        baseline_to_gate = int(baseline_remaining)
    except (TypeError, ValueError):
        baseline_to_gate = None
    try:
        baseline_entered_to_gate = int(entered_remaining)
    except (TypeError, ValueError):
        baseline_entered_to_gate = None
    return {
        "sessions_gate": promo.get("sessions_gate", 20),
        "entered_sessions_gate": promo.get(
            "entered_sessions_gate", PROMOTION_ENTERED_SESSIONS_GATE
        ),
        "baseline_sessions_to_gate": baseline_to_gate,
        "baseline_entered_sessions_to_gate": baseline_entered_to_gate,
        "baseline_near_gate": baseline_to_gate is not None and baseline_to_gate <= 2,
        "baseline_near_entered_gate": (
            baseline_entered_to_gate is not None and baseline_entered_to_gate <= 2
        ),
        "variants_near_promotion_gate": near_gate,
        "variants_collecting": promo.get("variants_collecting"),
        "variants_eligible_review": promo.get("variants_eligible_review") or [],
    }


def brief_consistency_anomalies(
    payload: dict[str, Any],
    *,
    paper_brief: dict[str, Any] | None = None,
    telemetry_brief: dict[str, Any] | None = None,
) -> list[str]:
    anomalies: list[str] = []
    baseline = payload.get("baseline_prod")
    if not isinstance(baseline, dict):
        return anomalies

    epoch_values: list[str | None] = [payload.get("pnl_epoch_at")]
    if isinstance(paper_brief, dict):
        if "pnl_epoch_at" in paper_brief:
            epoch_values.append(paper_brief.get("pnl_epoch_at"))
    if isinstance(telemetry_brief, dict):
        if "pnl_epoch_at" in telemetry_brief:
            epoch_values.append(telemetry_brief.get("pnl_epoch_at"))
    if len(epoch_values) > 1 and len({str(value) for value in epoch_values}) > 1:
        anomalies.append("pnl_epoch_mismatch")

    active_variant_ids = {
        str(variant_id)
        for variant_id in (payload.get("active_variant_ids") or [])
        if variant_id
    }
    state_variant_ids = {
        str(variant_id)
        for variant_id in (payload.get("state_variant_ids") or [])
        if variant_id
    }
    if active_variant_ids.difference(state_variant_ids):
        anomalies.append("variant_missing_from_state")

    if isinstance(paper_brief, dict):
        if paper_brief.get("hypothetical_realized_pnl_usd") != baseline.get(
            "realized_pnl_usd"
        ):
            anomalies.append("baseline_pnl_brief_mismatch")
        if paper_brief.get("open_positions_mtm_usd") != baseline.get(
            "open_positions_mtm_usd"
        ):
            anomalies.append("baseline_open_mtm_brief_mismatch")

    if isinstance(telemetry_brief, dict):
        baseline_tel = baseline.get("entry_telemetry") or {}
        if telemetry_brief.get("sessions_evaluated") != baseline.get(
            "sessions_evaluated"
        ):
            anomalies.append("entry_telemetry_sessions_mismatch")
        if telemetry_brief.get("entered_sessions") != baseline.get("entered_sessions"):
            anomalies.append("entry_telemetry_entered_mismatch")
        if telemetry_brief.get("evals_total") != baseline.get("entry_evals_total"):
            anomalies.append("entry_telemetry_evals_total_mismatch")
        if (telemetry_brief.get("skip_reason_counts") or {}) != (
            baseline_tel.get("skip_reason_counts") or {}
        ):
            anomalies.append("entry_telemetry_skip_counts_mismatch")
    return anomalies


def risk_gate_diag_anomalies(baseline_state: dict[str, Any] | None) -> list[str]:
    """Flag stale cap messaging or inconsistent scale-aware risk diagnostics."""
    if not isinstance(baseline_state, dict):
        return []
    log = baseline_state.get("entry_log") or []
    if not isinstance(log, list) or not log:
        return []
    latest = log[-1]
    if not isinstance(latest, dict):
        return []
    risk_gate = latest.get("risk_gate")
    if isinstance(risk_gate, dict):
        cap = risk_gate.get("cap_usd")
        scale = risk_gate.get("scale")
        effective = risk_gate.get("effective_cap_usd")
        if cap is not None and scale is not None and effective is not None:
            try:
                expected = round(float(cap) * float(scale), 2)
                if abs(float(effective) - expected) > 0.01:
                    return ["risk_gate_effective_cap_mismatch"]
            except (TypeError, ValueError):
                return ["risk_gate_effective_cap_mismatch"]
        return []

    skip = str(latest.get("skip_reason") or "")
    if "daily paper loss cap" in skip and "scale=" not in skip:
        return ["risk_gate_scale_diag_missing"]
    return []


def scoreboard_report_metrics(
    payload: dict[str, Any],
    *,
    paper_brief: dict[str, Any] | None = None,
    telemetry_brief: dict[str, Any] | None = None,
    baseline_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    promotion = promotion_proximity_summary(payload)
    baseline_zero_sessions = baseline_zero_sessions_after_grace(payload)
    baseline_zero_entries = baseline_zero_entries_after_grace(payload)
    brief_anomalies = brief_consistency_anomalies(
        payload,
        paper_brief=paper_brief,
        telemetry_brief=telemetry_brief,
    )
    risk_anomalies = risk_gate_diag_anomalies(baseline_state)
    anomalies: list[str] = []
    if payload.get("stale"):
        anomalies.append("scoreboard_stale")
    if baseline_zero_sessions:
        anomalies.append("baseline_zero_sessions_after_grace")
    if baseline_zero_entries:
        anomalies.append("baseline_zero_entries_after_grace")
    anomalies.extend(brief_anomalies)
    anomalies.extend(risk_anomalies)

    return {
        "stale": bool(payload.get("stale")),
        "last_entry_eval_at": payload.get("last_entry_eval_at"),
        "updated_at": payload.get("updated_at"),
        "soak_reset_at": payload.get("soak_reset_at"),
        "baseline_sessions_evaluated": baseline_sessions,
        "baseline_entered_sessions": (
            baseline.get("entered_sessions") if isinstance(baseline, dict) else None
        ),
        "regime_gate_comparison_variant_count": len(comparison_variants),
        "regime_axis_summary": regime_axis,
        "promotion_proximity": promotion,
        "vol_shadow_latest_spy_rv": vol_shadow_latest_spy_rv,
        "vol_shadow_avg_spy_rv": vol_shadow_avg_spy_rv,
        "baseline_zero_sessions_after_grace": baseline_zero_sessions,
        "baseline_zero_entries_after_grace": baseline_zero_entries,
        "brief_consistency_anomalies": brief_anomalies,
        "risk_gate_anomalies": risk_anomalies,
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


def baseline_zero_entries_after_grace(
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
    grace_days: int = BASELINE_ZERO_SESSIONS_GRACE_DAYS,
) -> bool:
    """Flag when baseline has sessions but zero enters past grace (GLM v4 P1)."""
    baseline = payload.get("baseline_prod")
    if not isinstance(baseline, dict):
        return False

    try:
        sessions_evaluated = int(baseline.get("sessions_evaluated") or 0)
        entered_sessions = int(baseline.get("entered_sessions") or 0)
    except (TypeError, ValueError):
        return False
    if sessions_evaluated <= 0 or entered_sessions > 0:
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
    paper_brief: dict[str, Any] | None = None,
    telemetry_brief: dict[str, Any] | None = None,
) -> list[str]:
    anomalies: list[str] = []
    if payload.get("stale"):
        anomalies.append("scoreboard_stale")
    if baseline_zero_sessions_after_grace(payload, now=now):
        anomalies.append("baseline_zero_sessions_after_grace")
    if baseline_zero_entries_after_grace(payload, now=now):
        anomalies.append("baseline_zero_entries_after_grace")
    anomalies.extend(
        brief_consistency_anomalies(
            payload,
            paper_brief=paper_brief,
            telemetry_brief=telemetry_brief,
        )
    )
    if pytest_failed:
        anomalies.append("pytest_failed")
    return anomalies
