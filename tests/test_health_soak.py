"""Tests for health/soak reporting helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from xsp_killer.health_soak import (
    baseline_zero_sessions_after_grace,
    detect_strict_anomalies,
    regime_axis_comparison_summary,
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
            "vol_shadow_latest_spy_rv": 0.1761,
            "vol_shadow_avg_spy_rv": 0.1763,
            "regime_gate_skip_sessions": 12,
            "bb_bounce_signal_sessions": 0,
        },
        "regime_gate_comparison": {
            "baseline_variant_id": "v2_baseline_prod",
            "variants": [
                {
                    "variant_id": "v2_baseline_prod",
                    "regime_gate": "GREEN",
                    "sessions_evaluated": 18,
                    "entered_sessions": 0,
                    "regime_gate_skip_sessions": 12,
                    "bb_bounce_signal_sessions": 0,
                    "bb_bounce_blocked_by_regime_sessions": 0,
                    "vol_shadow_would_block_sessions": 0,
                    "vol_shadow_latest_spy_rv": 0.1761,
                    "vol_shadow_avg_spy_rv": 0.1763,
                },
                {
                    "variant_id": "v2_yellow_mid_bounce",
                    "regime_gate": "GREEN_OR_YELLOW_BOUNCE",
                    "regime_yellow_frac_min": 0.5,
                    "sessions_evaluated": 9,
                    "entered_sessions": 0,
                    "regime_gate_skip_sessions": 0,
                    "bb_bounce_signal_sessions": 0,
                    "bb_bounce_blocked_by_regime_sessions": 0,
                    "vol_shadow_would_block_sessions": 0,
                    "vol_shadow_latest_spy_rv": 0.1759,
                    "vol_shadow_avg_spy_rv": 0.1763,
                },
                {
                    "variant_id": "v2_yellow_top_quartile_bounce",
                    "regime_gate": "GREEN_OR_YELLOW_BOUNCE",
                    "regime_yellow_frac_min": 0.75,
                    "sessions_evaluated": 9,
                    "entered_sessions": 0,
                    "regime_gate_skip_sessions": 0,
                    "bb_bounce_signal_sessions": 0,
                    "bb_bounce_blocked_by_regime_sessions": 0,
                    "vol_shadow_would_block_sessions": 0,
                },
            ],
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


def test_regime_axis_comparison_summary_flags_session_divergence():
    payload = _scoreboard_payload()

    axis = regime_axis_comparison_summary(payload)

    assert axis["has_counter_divergence"] is True
    mid = next(v for v in axis["variants"] if v["variant_id"] == "v2_yellow_mid_bounce")
    assert mid["diff_vs_baseline"]["sessions_evaluated"] == {
        "baseline": 18,
        "variant": 9,
    }


def test_scoreboard_report_metrics_includes_vol_shadow_and_regime_axis():
    payload = _scoreboard_payload(baseline_sessions_evaluated=18)

    metrics = scoreboard_report_metrics(payload)

    assert metrics["vol_shadow_latest_spy_rv"] == 0.1761
    assert metrics["regime_axis_summary"]["has_counter_divergence"] is True
