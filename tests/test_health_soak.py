"""Tests for health/soak reporting helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from xsp_killer.health_soak import (
    baseline_zero_entries_after_grace,
    baseline_zero_sessions_after_grace,
    brief_consistency_anomalies,
    detect_strict_anomalies,
    promotion_proximity_summary,
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
            "entered_sessions": 0,
            "entry_evals_total": baseline_sessions_evaluated,
            "sessions_to_promotion_gate": max(0, 20 - baseline_sessions_evaluated),
            "entered_sessions_to_promotion_gate": 10,
            "realized_pnl_usd": -1582.45,
            "open_positions_mtm_usd": 0.0,
            "vol_shadow_latest_spy_rv": 0.1761,
            "vol_shadow_avg_spy_rv": 0.1763,
            "regime_gate_skip_sessions": 12,
            "bb_bounce_signal_sessions": 0,
            "entry_telemetry": {
                "skip_reason_counts": {"regime_gate": 12},
                "entered_sessions": 0,
                "evals_total": baseline_sessions_evaluated,
            },
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
        "promotion_summary": {
            "sessions_gate": 20,
            "variants_collecting": 16,
            "variants_eligible_review": [],
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


def test_baseline_zero_entries_after_grace_requires_sessions_and_no_enters():
    payload = _scoreboard_payload(
        soak_reset_at="2026-06-24T00:00:00+00:00",
        baseline_sessions_evaluated=15,
    )

    assert (
        baseline_zero_entries_after_grace(
            payload,
            now=datetime(2026, 6, 28, 23, 59, tzinfo=timezone.utc),
        )
        is False
    )
    assert (
        baseline_zero_entries_after_grace(
            payload,
            now=datetime(2026, 6, 29, 0, 0, tzinfo=timezone.utc),
        )
        is True
    )


def test_baseline_zero_entries_after_grace_cleared_when_enters_exist():
    payload = _scoreboard_payload(
        soak_reset_at="2026-06-24T00:00:00+00:00",
        baseline_sessions_evaluated=21,
    )
    payload["baseline_prod"]["entered_sessions"] = 1

    assert (
        baseline_zero_entries_after_grace(
            payload,
            now=datetime(2026, 6, 29, 0, 0, tzinfo=timezone.utc),
        )
        is False
    )


def test_scoreboard_report_metrics_flags_zero_entries_anomaly():
    payload = _scoreboard_payload(
        soak_reset_at="2026-06-24T00:00:00+00:00",
        baseline_sessions_evaluated=21,
    )

    metrics = scoreboard_report_metrics(payload)

    assert metrics["baseline_zero_entries_after_grace"] is True
    assert "baseline_zero_entries_after_grace" in metrics["strict_anomalies"]


def test_detect_strict_anomalies_includes_pytest_failures():
    payload = _scoreboard_payload(
        baseline_sessions_evaluated=4,
        soak_reset_at="2026-06-24T00:00:00+00:00",
    )
    payload["baseline_prod"]["entered_sessions"] = 1

    anomalies = detect_strict_anomalies(
        payload,
        pytest_failed=True,
        now=datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc),
    )

    assert anomalies == ["pytest_failed"]


def test_brief_consistency_anomalies_detect_brief_mismatches():
    payload = _scoreboard_payload(baseline_sessions_evaluated=12)
    anomalies = brief_consistency_anomalies(
        payload,
        paper_brief={
            "hypothetical_realized_pnl_usd": -75.0,
            "open_positions_mtm_usd": -10.0,
        },
        telemetry_brief={
            "sessions_evaluated": 0,
            "entered_sessions": 0,
            "evals_total": 0,
            "skip_reason_counts": {},
        },
    )
    assert anomalies == [
        "baseline_pnl_brief_mismatch",
        "baseline_open_mtm_brief_mismatch",
        "entry_telemetry_sessions_mismatch",
        "entry_telemetry_evals_total_mismatch",
        "entry_telemetry_skip_counts_mismatch",
    ]


def test_scoreboard_report_metrics_includes_brief_consistency_anomalies():
    payload = _scoreboard_payload(baseline_sessions_evaluated=12)
    metrics = scoreboard_report_metrics(
        payload,
        paper_brief={
            "hypothetical_realized_pnl_usd": -75.0,
            "open_positions_mtm_usd": -10.0,
        },
        telemetry_brief={
            "sessions_evaluated": 0,
            "entered_sessions": 0,
            "evals_total": 0,
            "skip_reason_counts": {},
        },
    )
    assert "baseline_pnl_brief_mismatch" in metrics["brief_consistency_anomalies"]
    assert "entry_telemetry_sessions_mismatch" in metrics["strict_anomalies"]


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
    assert metrics["promotion_proximity"]["baseline_near_gate"] is True


def test_promotion_proximity_summary_near_gate():
    payload = _scoreboard_payload(baseline_sessions_evaluated=18)
    payload["shadow_variants"] = [
        {
            "variant_id": "v2_28dte_atm",
            "sessions_to_promotion_gate": 2,
        }
    ]

    promo = promotion_proximity_summary(payload)

    assert promo["baseline_sessions_to_gate"] == 2
    assert promo["baseline_near_gate"] is True
    assert promo["variants_near_promotion_gate"] == ["v2_28dte_atm"]
