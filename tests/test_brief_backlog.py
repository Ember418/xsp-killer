"""Brief backlog tests — regime gate experiment, entry_log fields, yellow bounce variants."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

from xsp_killer.lane_a_variants import (
    VariantSpec,
    build_scoreboard,
    load_variant_specs,
    merged_rules_path,
)
from xsp_killer.lane_a_entry import (
    EntryDecision,
    _finalize_entry,
)


def _write_variants_config(tmp_path: Path, variants: dict[str, dict]) -> Path:
    """Helper to write test variant config."""
    config_path = tmp_path / "lane_a_variants.yaml"
    config_path.write_text(
        yaml.safe_dump({"variants": variants}, sort_keys=False),
        encoding="utf-8",
    )
    return config_path


def _write_base_rules(tmp_path: Path) -> Path:
    """Write minimal base rules for testing."""
    rules = {
        "instrument": "XSP",
        "paper_entry": {
            "enabled": True,
            "max_open_positions": 1,
            "quantity": 1,
        },
        "entry": {
            "window_start_et": "15:45",
            "window_end_et": "16:00",
            "prior_day_spy_positive": False,
            "dte_pick": "min",
        },
        "exit": {
            "stop_loss_pct": 0.20,
            "take_profit_pct": 0.20,
            "sell_deadline_et": "10:00",
        },
        "logging": {
            "logic_version": "xsp_lane_a_v2",
        },
    }
    rules_path = tmp_path / "lane_a_rules.yaml"
    rules_path.write_text(yaml.safe_dump(rules, sort_keys=False), encoding="utf-8")
    return rules_path


class TestYellowBounceVariantSpecs:
    """TASK: Verify load_variant_specs includes both yellow bounce variants."""

    def test_yellow_variants_in_load_variant_specs(self):
        """Both yellow bounce variants should be present in config with distinct settings."""
        specs = load_variant_specs()
        ids = {s.variant_id for s in specs}

        assert "v2_yellow_mid_bounce" in ids
        assert "v2_yellow_top_quartile_bounce" in ids

        mid_spec = next(s for s in specs if s.variant_id == "v2_yellow_mid_bounce")
        top_spec = next(
            s for s in specs if s.variant_id == "v2_yellow_top_quartile_bounce"
        )

        # Distinct logic_version
        assert mid_spec.logic_version == "xsp_lane_a_v2_yellow_mid_bounce"
        assert (
            top_spec.logic_version == "xsp_lane_a_v2_yellow_top_quartile_bounce"
        )

        # Distinct regime_yellow_frac_min in overrides
        assert mid_spec.overrides["entry"]["regime_yellow_frac_min"] == 0.50
        assert top_spec.overrides["entry"]["regime_yellow_frac_min"] == 0.75

    def test_merged_rules_contain_regime_config(self, tmp_path: Path):
        """Merged rules should contain GREEN_OR_YELLOW_BOUNCE gate and frac_min."""
        specs = load_variant_specs()

        mid_spec = next(s for s in specs if s.variant_id == "v2_yellow_mid_bounce")
        top_spec = next(
            s for s in specs if s.variant_id == "v2_yellow_top_quartile_bounce"
        )

        mid_rules = yaml.safe_load(
            merged_rules_path(mid_spec, tmp_dir=tmp_path).read_text(encoding="utf-8")
        )
        top_rules = yaml.safe_load(
            merged_rules_path(top_spec, tmp_dir=tmp_path).read_text(encoding="utf-8")
        )

        assert mid_rules["entry"]["regime_gate"] == "GREEN_OR_YELLOW_BOUNCE"
        assert top_rules["entry"]["regime_gate"] == "GREEN_OR_YELLOW_BOUNCE"

        assert mid_rules["entry"]["regime_yellow_frac_min"] == 0.50
        assert top_rules["entry"]["regime_yellow_frac_min"] == 0.75


class TestRegimeGateComparison:
    """TASK: Verify scoreboard regime_gate_comparison includes baseline + both yellow variants."""

    def test_regime_gate_comparison_structure(self, tmp_path: Path):
        """Scoreboard should contain regime_gate_comparison with all three variants."""
        config_path = _write_variants_config(
            tmp_path,
            {
                "v2_yellow_mid_bounce": {
                    "active": True,
                    "description": "YELLOW mid-band bounce (frac>=0.50)",
                    "overrides": {
                        "logging": {
                            "logic_version": "xsp_lane_a_v2_yellow_mid_bounce"
                        },
                        "entry": {
                            "regime_gate": "GREEN_OR_YELLOW_BOUNCE",
                            "regime_yellow_frac_min": 0.50,
                        },
                    },
                },
                "v2_yellow_top_quartile_bounce": {
                    "active": True,
                    "description": "YELLOW top-quartile bounce (frac>=0.75)",
                    "overrides": {
                        "logging": {
                            "logic_version": "xsp_lane_a_v2_yellow_top_quartile_bounce"
                        },
                        "entry": {
                            "regime_gate": "GREEN_OR_YELLOW_BOUNCE",
                            "regime_yellow_frac_min": 0.75,
                        },
                    },
                },
            },
        )

        # Create variant state with entry logs for both variants
        variant_state = tmp_path / "variants-state.json"
        variant_state.write_text(
            json.dumps(
                {
                    "variants": {
                        "v2_yellow_mid_bounce": {
                            "entry_log": [
                                {
                                    "evaluated_at": "2026-06-26T19:45:00+00:00",
                                    "entered": False,
                                    "skip_reason": "regime YELLOW blocks new risk: yellow_frac 0.40 < 0.50",
                                    "regime": "YELLOW",
                                    "regime_frac": 0.4,
                                    "regime_gate": "GREEN_OR_YELLOW_BOUNCE",
                                    "bb_entry_ok": True,
                                }
                            ],
                            "paper_events": [],
                            "paper_positions": {},
                        },
                        "v2_yellow_top_quartile_bounce": {
                            "entry_log": [
                                {
                                    "evaluated_at": "2026-06-26T19:45:00+00:00",
                                    "entered": False,
                                    "skip_reason": "regime YELLOW blocks new risk: yellow_frac 0.40 < 0.75",
                                    "regime": "YELLOW",
                                    "regime_frac": 0.4,
                                    "regime_gate": "GREEN_OR_YELLOW_BOUNCE",
                                    "bb_entry_ok": True,
                                }
                            ],
                            "paper_events": [],
                            "paper_positions": {},
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        # Create baseline state
        baseline = tmp_path / "baseline-state.json"
        baseline.write_text(
            json.dumps(
                {
                    "entry_log": [
                        {
                            "evaluated_at": "2026-06-26T19:45:00+00:00",
                            "entered": False,
                            "skip_reason": "regime YELLOW blocks new risk",
                            "regime": "YELLOW",
                            "regime_gate": "GREEN",
                            "bb_entry_ok": True,
                        }
                    ],
                    "paper_events": [],
                    "paper_positions": {},
                }
            ),
            encoding="utf-8",
        )

        scoreboard_path = tmp_path / "scoreboard.json"
        build_scoreboard(
            config_path=config_path,
            state_path=variant_state,
            baseline_state_path=baseline,
            out_path=scoreboard_path,
        )

        payload = json.loads(scoreboard_path.read_text(encoding="utf-8"))

        # Verify regime_gate_comparison exists
        assert "regime_gate_comparison" in payload
        comparison = payload["regime_gate_comparison"]

        # Verify structure
        assert comparison["baseline_variant_id"] == "v2_baseline_prod"
        assert comparison["track_family"] == "yellow_bounce_frac_axis"
        assert "description" in comparison

        # Verify all three variants are present
        variant_ids = [v["variant_id"] for v in comparison["variants"]]
        assert "v2_baseline_prod" in variant_ids
        assert "v2_yellow_mid_bounce" in variant_ids
        assert "v2_yellow_top_quartile_bounce" in variant_ids

        # Verify variant metadata
        mid = next(
            v
            for v in comparison["variants"]
            if v["variant_id"] == "v2_yellow_mid_bounce"
        )
        top = next(
            v
            for v in comparison["variants"]
            if v["variant_id"] == "v2_yellow_top_quartile_bounce"
        )
        base = next(
            v for v in comparison["variants"] if v["variant_id"] == "v2_baseline_prod"
        )

        assert mid["regime_yellow_frac_min"] == 0.50
        assert top["regime_yellow_frac_min"] == 0.75
        assert base["regime_gate"] == "GREEN"
        assert mid["regime_gate"] == "GREEN_OR_YELLOW_BOUNCE"
        assert top["regime_gate"] == "GREEN_OR_YELLOW_BOUNCE"

        # Verify bb_bounce metrics
        assert "bb_bounce_signal_sessions" in mid
        assert "bb_bounce_blocked_by_regime_sessions" in mid


class TestEntryLogFields:
    """TASK: Verify entry_log fields regime_gate, regime_frac, bb_entry_ok present."""

    def test_finalize_entry_creates_entry_log_with_regime_fields(
        self, tmp_path: Path, monkeypatch
    ):
        """_finalize_entry should write regime_gate, regime_frac, bb_entry_ok to entry_log."""
        # Setup minimal state and decision
        state: dict[str, Any] = {
            "paper_positions": {},
            "entry_log": [],
            "paper_events": [],
        }
        state_path = tmp_path / "test-state.json"

        # Mock the save_state to avoid side effects
        def mock_save_state(path: Path, s: dict) -> None:
            state.update(s)

        monkeypatch.setattr("xsp_killer.lane_a_entry.save_state", mock_save_state)
        monkeypatch.setattr(
            "xsp_killer.lane_a_entry.append_entry_log", lambda *a, **k: None
        )
        monkeypatch.setattr(
            "xsp_killer.lane_a_entry.write_entry_brief", lambda *a, **k: tmp_path / "brief.json"
        )
        # IntelPublisher is imported locally in _finalize_entry
        monkeypatch.setattr(
            "xsp_killer.intel.IntelPublisher.publish", lambda *a, **k: None
        )

        decision = EntryDecision(
            entered=False,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            logic_version="xsp_lane_a_v2_test",
            in_window=False,
            regime="YELLOW",
            regime_ok=True,
            regime_frac=0.65,
            regime_gate="GREEN_OR_YELLOW_BOUNCE",
            prior_day_spy_return_pct=0.5,
            prior_day_ok=True,
            prior_day_spy_session="2026-06-25",
            skip_reason="regime YELLOW blocks new risk: yellow_frac 0.65 < 0.75",
            bb_entry_ok=True,
            errors=[],
        )

        _finalize_entry(
            state,
            state_path,
            decision,
            publish_intel=False,
        )

        # Verify entry_log was updated with required fields
        assert len(state["entry_log"]) == 1
        entry = state["entry_log"][0]

        assert entry["regime"] == "YELLOW"
        assert entry["regime_frac"] == 0.65
        assert entry["regime_gate"] == "GREEN_OR_YELLOW_BOUNCE"
        assert entry["bb_entry_ok"] is True
        assert entry["entered"] is False
        assert entry["skip_reason"] == "regime YELLOW blocks new risk: yellow_frac 0.65 < 0.75"
        assert entry["prior_day_spy_return_pct"] == 0.5
        assert entry["prior_day_spy_session"] == "2026-06-25"

    def test_entry_log_fields_present_in_actual_state(self, tmp_path: Path):
        """Verify that actual scoreboard parsing includes entry_log derived metrics."""
        config_path = _write_variants_config(
            tmp_path,
            {
                "v2_test_regime_fields": {
                    "active": True,
                    "description": "Test regime fields propagation",
                    "overrides": {},
                }
            },
        )

        # Create state with entry_log containing all regime fields
        variant_state = tmp_path / "variants-state.json"
        variant_state.write_text(
            json.dumps(
                {
                    "variants": {
                        "v2_test_regime_fields": {
                            "entry_log": [
                                {
                                    "evaluated_at": "2026-06-26T19:45:00+00:00",
                                    "entered": False,
                                    "regime": "YELLOW",
                                    "regime_frac": 0.45,
                                    "regime_gate": "GREEN_OR_YELLOW_BOUNCE",
                                    "bb_entry_ok": True,
                                    "skip_reason": "regime gate blocked",
                                },
                                {
                                    "evaluated_at": "2026-06-27T19:45:00+00:00",
                                    "entered": False,
                                    "regime": "GREEN",
                                    "regime_frac": None,
                                    "regime_gate": "GREEN_OR_YELLOW_BOUNCE",
                                    "bb_entry_ok": False,
                                    "skip_reason": "no BB bounce signal",
                                },
                            ],
                            "paper_events": [],
                            "paper_positions": {},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        baseline = tmp_path / "baseline-state.json"
        baseline.write_text(
            json.dumps({"entry_log": [], "paper_events": [], "paper_positions": {}}),
            encoding="utf-8",
        )

        scoreboard_path = tmp_path / "scoreboard.json"
        build_scoreboard(
            config_path=config_path,
            state_path=variant_state,
            baseline_state_path=baseline,
            out_path=scoreboard_path,
        )

        payload = json.loads(scoreboard_path.read_text(encoding="utf-8"))
        variant_row = next(
            r
            for r in payload["shadow_variants"]
            if r["variant_id"] == "v2_test_regime_fields"
        )

        # Verify entry_log-derived metrics are present
        assert "bb_bounce_signal_sessions" in variant_row
        assert "bb_bounce_blocked_by_regime_sessions" in variant_row
        assert variant_row["bb_bounce_signal_sessions"] == 1
        assert variant_row["bb_bounce_blocked_by_regime_sessions"] == 1


class TestSessionGate:
    """Verify promotion WAIT until >=20 post-epoch sessions."""

    def test_sessions_to_gate_calculation(self, tmp_path: Path):
        """sessions_to_gate should be 20 - sessions_evaluated until threshold met."""
        config_path = _write_variants_config(
            tmp_path,
            {
                "v2_test_sessions": {
                    "active": True,
                    "description": "Test sessions gate",
                    "overrides": {},
                }
            },
        )

        # Create state with 15 sessions evaluated
        variant_state = tmp_path / "variants-state.json"
        variant_state.write_text(
            json.dumps(
                {
                    "variants": {
                        "v2_test_sessions": {
                            "entry_log": [
                                {"evaluated_at": f"2026-06-{i:02d}T19:45:00+00:00"}
                                for i in range(15, 30)
                            ],
                            "paper_events": [],
                            "paper_positions": {},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        baseline = tmp_path / "baseline-state.json"
        baseline.write_text(
            json.dumps({"entry_log": [], "paper_events": [], "paper_positions": {}}),
            encoding="utf-8",
        )

        scoreboard_path = tmp_path / "scoreboard.json"
        build_scoreboard(
            config_path=config_path,
            state_path=variant_state,
            baseline_state_path=baseline,
            out_path=scoreboard_path,
        )

        payload = json.loads(scoreboard_path.read_text(encoding="utf-8"))
        variant_row = next(
            r
            for r in payload["shadow_variants"]
            if r["variant_id"] == "v2_test_sessions"
        )

        assert variant_row["sessions_evaluated"] == 15
        assert variant_row["sessions_to_gate"] == 5

    def test_zero_sessions_to_gate_when_threshold_met(self, tmp_path: Path):
        """sessions_to_gate should be 0 when >=20 sessions evaluated."""
        config_path = _write_variants_config(
            tmp_path,
            {
                "v2_test_sessions_25": {
                    "active": True,
                    "description": "Test sessions threshold met",
                    "overrides": {},
                }
            },
        )

        # Create state with 25 sessions evaluated
        variant_state = tmp_path / "variants-state.json"
        variant_state.write_text(
            json.dumps(
                {
                    "variants": {
                        "v2_test_sessions_25": {
                            "entry_log": [
                                {"evaluated_at": f"2026-06-{i:02d}T19:45:00+00:00"}
                                for i in range(5, 30)
                            ],
                            "paper_events": [],
                            "paper_positions": {},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        baseline = tmp_path / "baseline-state.json"
        baseline.write_text(
            json.dumps({"entry_log": [], "paper_events": [], "paper_positions": {}}),
            encoding="utf-8",
        )

        scoreboard_path = tmp_path / "scoreboard.json"
        build_scoreboard(
            config_path=config_path,
            state_path=variant_state,
            baseline_state_path=baseline,
            out_path=scoreboard_path,
        )

        payload = json.loads(scoreboard_path.read_text(encoding="utf-8"))
        variant_row = next(
            r
            for r in payload["shadow_variants"]
            if r["variant_id"] == "v2_test_sessions_25"
        )

        assert variant_row["sessions_evaluated"] == 25
        assert variant_row["sessions_to_gate"] == 0
