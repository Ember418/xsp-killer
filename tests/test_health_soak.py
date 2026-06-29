"""Tests for health/soak reporting helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from xsp_killer.health_soak import (
    baseline_zero_sessions_after_grace,
    detect_strict_anomalies,
    scoreboard_report_metrics,
)


def _scoreboard_payload(
    *,
    stale: bool = False,
    soak_reset_at: str = "2026-06-20T00:00:00+00:00",
    baseline_sessions_evaluated: int = 0,
) -> dict:
    return {
        "stale": stale,
        "updated_at": "2026-06-26T12:00:00+00:00",
        "soak_reset_at": soak_reset_at,
        "last_entry_eval_at": "2026-06-26T11:45:00+00:00",
        "baseline_prod": {
            "variant_id": "v2_baseline_prod",
            "sessions_evaluated": baseline_sessions_evaluated,
        },
        "regime_gate_comparison": {
            "variants": [
                {"variant_id": "v2_baseline_prod"},
                {"variant_id": "v2_yellow_mid_bounce"},
                {"variant_id": "v2_yellow_top_quartile_bounce"},
            ]
        },
    }


def test_scoreboard_report_metrics_counts_regime_gate_variants():
    payload = _scoreboard_payload(stale=True)

    metrics = scoreboard_report_metrics(payload)

    assert metrics["stale"] is True
    assert metrics["baseline_sessions_evaluated"] == 0
    assert metrics["regime_gate_comparison_variant_count"] == 3
    assert metrics["strict_anomalies"] == [
        "scoreboard_stale",
        "baseline_zero_sessions_after_grace",
    ]


def test_baseline_zero_sessions_after_grace_requires_full_grace_period():
    payload = _scoreboard_payload(soak_reset_at="2026-06-24T00:00:00+00:00")

    assert (
        baseline_zero_sessions_after_grace(
            payload,
            now=datetime(2026, 6, 28, 23, 59, tzinfo=timezone.utc),
        )
        is False
    )
    assert (
        baseline_zero_sessions_after_grace(
            payload,
            now=datetime(2026, 6, 29, 0, 0, tzinfo=timezone.utc),
        )
        is True
    )


def test_detect_strict_anomalies_includes_pytest_failures():
    payload = _scoreboard_payload(baseline_sessions_evaluated=4)

    anomalies = detect_strict_anomalies(payload, pytest_failed=True)

    assert anomalies == ["pytest_failed"]
