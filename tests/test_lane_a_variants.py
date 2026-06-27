"""Tests for Lane A variant soak."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import xsp_killer.lane_a_entry as lane_a_entry

from xsp_killer.lane_a_variants import (
    VariantSpec,
    build_scoreboard,
    clear_pnl_epoch,
    load_variant_specs,
    merged_rules_path,
    reset_soak,
    run_variant_entry,
)
from xsp_killer.lane_a_ta import TaSignal


def _write_variants_config(tmp_path, variants: dict[str, dict]) -> None:
    import yaml

    (tmp_path / "lane_a_variants.yaml").write_text(
        yaml.safe_dump({"variants": variants}, sort_keys=False),
        encoding="utf-8",
    )


def test_load_variant_specs():
    specs = load_variant_specs()
    assert len(specs) >= 10
    ids = {s.variant_id for s in specs}
    assert "v2_28dte_atm" in ids
    assert "v2_21dte_atm" in ids
    assert "v2_yellow_top_quartile_bounce" in ids
    assert "v2_yellow_mid_bounce" in ids


def test_merged_rules_dte_target(tmp_path):
    specs = load_variant_specs()
    spec = next(s for s in specs if s.variant_id == "v2_28dte_atm")
    path = merged_rules_path(spec, tmp_dir=tmp_path)
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["entry"]["dte_pick"] == "target"
    assert data["entry"]["dte_target"] == 28
    assert data["entry"]["strike_pick"] == "atm_only"


def test_merged_rules_yellow_bounce_variant(tmp_path):
    specs = load_variant_specs()
    spec = next(s for s in specs if s.variant_id == "v2_yellow_top_quartile_bounce")
    path = merged_rules_path(spec, tmp_dir=tmp_path)
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["entry"]["regime_gate"] == "GREEN_OR_YELLOW_BOUNCE"
    assert data["entry"]["regime_yellow_frac_min"] == 0.75
    assert data["ta"]["entry"]["mode"] == "close_window_and_bb"


def test_merged_rules_yellow_mid_bounce_variant(tmp_path):
    specs = load_variant_specs()
    spec = next(s for s in specs if s.variant_id == "v2_yellow_mid_bounce")
    path = merged_rules_path(spec, tmp_dir=tmp_path)
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["entry"]["regime_gate"] == "GREEN_OR_YELLOW_BOUNCE"
    assert data["entry"]["regime_yellow_frac_min"] == 0.50
    assert data["logging"]["logic_version"] == "xsp_lane_a_v2_yellow_mid_bounce"
    assert data["ta"]["entry"]["mode"] == "close_window_and_bb"


def test_build_scoreboard(tmp_path):
    _write_variants_config(
        tmp_path,
        {
            "v2_28dte_atm": {
                "active": True,
                "description": "Test scoreboard variant",
                "overrides": {},
            }
        },
    )
    state = tmp_path / "variants-state.json"
    state.write_text(
        json.dumps(
            {
                "variants": {
                    "v2_28dte_atm": {
                        "paper_events": [
                            {
                                "paper_pnl_usd": 10.0,
                                "position_id": "paper:XSP:2026-07-18:6010",
                            },
                            {
                                "paper_pnl_usd": -5.0,
                                "position_id": "paper:XSP:2026-07-18:6010",
                            },
                        ],
                        "paper_positions": {
                            "paper:XSP:2026-07-18:6010": {
                                "position_id": "paper:XSP:2026-07-18:6010",
                                "status": "closed",
                                "dte_actual": 23,
                                "expiration_date": "2026-07-18",
                            }
                        },
                        "entry_log": [
                            {
                                "evaluated_at": "2026-06-21T19:45:00+00:00",
                                "entered": False,
                            }
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    out = build_scoreboard(
        config_path=tmp_path / "lane_a_variants.yaml",
        state_path=state,
        baseline_state_path=tmp_path / "missing-baseline.json",
        out_path=tmp_path / "scoreboard.json",
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    row = next(r for r in payload["variants"] if r["variant_id"] == "v2_28dte_atm")
    assert row["realized_pnl_usd"] == 5.0
    assert row["trades_closed"] == 2
    assert row["avg_pnl_per_trade_usd"] == 2.5
    assert row["sessions_evaluated"] == 1
    assert row["sessions_to_gate"] == 19
    assert row["last_exit"]["dte_actual"] == 23
    assert row["last_exit"]["expiration"] == "2026-07-18"
    assert payload["baseline_prod"] is None
    assert len(payload["shadow_variants"]) == 1
    assert payload["last_entry_eval_at"] == "2026-06-21T19:45:00+00:00"
    assert "Do NOT sum PnL" in payload["comparison_guidance"]


def test_build_scoreboard_includes_stateless_active_spec(tmp_path):
    _write_variants_config(
        tmp_path,
        {
            "v2_test_a": {
                "active": True,
                "description": "Active with state",
                "overrides": {},
            },
            "v2_new_variant": {
                "active": True,
                "description": "Active without state",
                "overrides": {},
            },
            "v2_test_b": {
                "active": False,
                "description": "Inactive with stale state",
                "overrides": {},
            },
        },
    )
    state = tmp_path / "variants-state.json"
    state.write_text(
        json.dumps(
            {
                "variants": {
                    "v2_test_a": {
                        "entry_log": [
                            {
                                "evaluated_at": "2026-06-21T19:45:00+00:00",
                                "entered": False,
                            }
                        ],
                        "paper_events": [{"paper_pnl_usd": 4.0}],
                        "paper_positions": {},
                    },
                    "v2_test_b": {
                        "entry_log": [
                            {
                                "evaluated_at": "2026-06-21T20:00:00+00:00",
                                "entered": True,
                            }
                        ],
                        "paper_events": [{"paper_pnl_usd": 9.0}],
                        "paper_positions": {},
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    payload = json.loads(
        build_scoreboard(
            config_path=tmp_path / "lane_a_variants.yaml",
            state_path=state,
            baseline_state_path=tmp_path / "missing-baseline.json",
            out_path=tmp_path / "scoreboard.json",
        ).read_text(encoding="utf-8")
    )

    variants = {row["variant_id"]: row for row in payload["shadow_variants"]}
    assert set(variants) == {"v2_test_a", "v2_new_variant"}
    assert variants["v2_test_a"]["sessions_evaluated"] == 1
    assert variants["v2_test_a"]["realized_pnl_usd"] == 4.0
    assert variants["v2_new_variant"]["sessions_evaluated"] == 0
    assert variants["v2_new_variant"]["trades_closed"] == 0
    assert variants["v2_new_variant"]["description"] == "Active without state"


def test_build_scoreboard_respects_soak_reset(tmp_path):
    reset_at = "2026-06-21T12:00:00+00:00"
    state = tmp_path / "variants-state.json"
    state.write_text(
        json.dumps(
            {
                "soak_reset_at": reset_at,
                "variants": {
                    "v2_28dte_atm": {
                        "paper_events": [
                            {
                                "paper_pnl_usd": -10.0,
                                "evaluated_at": "2026-06-20T14:00:00+00:00",
                            },
                            {
                                "paper_pnl_usd": 7.0,
                                "evaluated_at": "2026-06-21T14:00:00+00:00",
                            },
                        ],
                        "entry_log": [
                            {
                                "evaluated_at": "2026-06-20T19:45:00+00:00",
                                "entered": False,
                            },
                            {
                                "evaluated_at": "2026-06-21T19:45:00+00:00",
                                "entered": False,
                            },
                            {
                                "evaluated_at": "2026-06-22T19:45:00+00:00",
                                "entered": True,
                            },
                        ],
                        "paper_positions": {},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    out = build_scoreboard(state_path=state, out_path=tmp_path / "scoreboard.json")
    payload = json.loads(out.read_text(encoding="utf-8"))
    row = next(r for r in payload["variants"] if r["variant_id"] == "v2_28dte_atm")
    assert row["realized_pnl_usd"] == 7.0
    assert row["trades_closed"] == 1
    assert row["sessions_evaluated"] == 2
    assert row["sessions_to_gate"] == 18
    assert payload["soak_reset_at"] == reset_at


def test_run_variant_entry_regime_skip_does_not_write_default_entry_brief(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("XSP_LANE_A_PAPER_ENTRY", "true")
    monkeypatch.setattr(
        "xsp_killer.lane_a_entry.read_regime_detail", lambda: ("RED", False, None, None)
    )
    monkeypatch.setattr(
        "xsp_killer.lane_a_entry.evaluate_ta_signals",
        lambda rules, now_et=None: TaSignal(
            signal="bb_bounce",
            primary=None,
            confirm=None,
            entry_ok=True,
            exit_ok=False,
            upper_bb_touched=False,
            detail="forced test signal",
        ),
    )
    lane_a_entry.DEFAULT_OUT.unlink(missing_ok=True)

    decision = run_variant_entry(
        VariantSpec(
            variant_id="brief_regression",
            description="brief path regression",
            active=True,
            overrides={},
        ),
        root_state={"variants": {}},
        state_path=tmp_path / "variants-state.json",
        now_et=datetime(2026, 6, 16, 19, 47, tzinfo=timezone.utc),
        force=True,
    )

    assert decision.entered is False
    assert decision.skip_reason == "regime RED blocks new risk"
    assert lane_a_entry.DEFAULT_OUT.exists() is False


def test_build_scoreboard_sets_liveness_from_latest_entry_eval(tmp_path):
    recent_variant_eval = (
        (datetime.now(timezone.utc) - timedelta(hours=4))
        .replace(microsecond=0)
        .isoformat()
    )
    recent_baseline_eval = (
        (datetime.now(timezone.utc) - timedelta(hours=2))
        .replace(microsecond=0)
        .isoformat()
    )
    backdated_eval = (
        (datetime.now(timezone.utc) - timedelta(hours=40))
        .replace(microsecond=0)
        .isoformat()
    )

    state = tmp_path / "variants-state.json"
    baseline = tmp_path / "baseline-state.json"

    state.write_text(
        json.dumps(
            {
                "variants": {
                    "v2_28dte_atm": {
                        "entry_log": [
                            {"evaluated_at": recent_variant_eval, "entered": False}
                        ],
                        "paper_events": [],
                        "paper_positions": {},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    baseline.write_text(
        json.dumps(
            {
                "entry_log": [{"evaluated_at": recent_baseline_eval, "entered": True}],
                "paper_events": [],
                "paper_positions": {},
            }
        ),
        encoding="utf-8",
    )

    payload = json.loads(
        build_scoreboard(
            state_path=state,
            baseline_state_path=baseline,
            out_path=tmp_path / "scoreboard-recent.json",
        ).read_text(encoding="utf-8")
    )
    assert payload["last_entry_eval_at"] == recent_baseline_eval
    assert payload["stale"] is False

    state.write_text(
        json.dumps(
            {
                "variants": {
                    "v2_28dte_atm": {
                        "entry_log": [
                            {"evaluated_at": backdated_eval, "entered": False}
                        ],
                        "paper_events": [],
                        "paper_positions": {},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    baseline.write_text(
        json.dumps(
            {
                "entry_log": [{"evaluated_at": backdated_eval, "entered": False}],
                "paper_events": [],
                "paper_positions": {},
            }
        ),
        encoding="utf-8",
    )

    stale_payload = json.loads(
        build_scoreboard(
            state_path=state,
            baseline_state_path=baseline,
            out_path=tmp_path / "scoreboard-stale.json",
        ).read_text(encoding="utf-8")
    )
    assert stale_payload["last_entry_eval_at"] == backdated_eval
    assert stale_payload["stale"] is True


def test_reset_soak_archives_and_clears(tmp_path, monkeypatch):
    state = tmp_path / "variants-state.json"
    baseline = tmp_path / "baseline-state.json"
    scoreboard = tmp_path / "scoreboard.json"
    archive = tmp_path / "archive"
    state.write_text(
        json.dumps(
            {
                "variants": {
                    "v2_28dte_atm": {
                        "paper_events": [
                            {
                                "paper_pnl_usd": -1.0,
                                "evaluated_at": "2026-06-20T14:00:00+00:00",
                            }
                        ],
                        "entry_log": [{"entered": True}],
                        "paper_positions": {},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    baseline.write_text(
        json.dumps({"paper_events": [{"paper_pnl_usd": -2.0}], "paper_positions": {}}),
        encoding="utf-8",
    )
    scoreboard.write_text('{"variants": []}\n', encoding="utf-8")

    monkeypatch.setattr(
        "xsp_killer.lane_a_variants.load_variant_specs",
        lambda _path=None: [],
    )

    meta = reset_soak(
        commit="abc1234",
        state_path=state,
        baseline_state_path=baseline,
        scoreboard_path=scoreboard,
        archive_dir=archive,
    )
    root = json.loads(state.read_text(encoding="utf-8"))
    base = json.loads(baseline.read_text(encoding="utf-8"))
    assert root["variants"]["v2_28dte_atm"]["paper_events"] == []
    assert root["variants"]["v2_28dte_atm"]["entry_log"] == []
    assert base["paper_events"] == []
    assert meta["soak_reset_commit"] == "abc1234"
    assert len(list(archive.glob("*pre-reset*"))) >= 2


def test_clear_pnl_keeps_entry_log(tmp_path, monkeypatch):
    state = tmp_path / "variants-state.json"
    baseline = tmp_path / "baseline-state.json"
    scoreboard = tmp_path / "scoreboard.json"
    archive = tmp_path / "archive"
    state.write_text(
        json.dumps(
            {
                "variants": {
                    "v2_28dte_atm": {
                        "paper_events": [
                            {
                                "paper_pnl_usd": -100.0,
                                "evaluated_at": "2026-06-23T14:00:00+00:00",
                            }
                        ],
                        "entry_log": [{"entered": True}],
                        "paper_positions": {},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    baseline.write_text(
        json.dumps({"paper_events": [{"paper_pnl_usd": -50.0}], "paper_positions": {}}),
        encoding="utf-8",
    )
    scoreboard.write_text('{"variants": []}\n', encoding="utf-8")
    monkeypatch.setattr(
        "xsp_killer.lane_a_variants.load_variant_specs", lambda _path=None: []
    )

    meta = clear_pnl_epoch(
        commit="abc",
        state_path=state,
        baseline_state_path=baseline,
        scoreboard_path=scoreboard,
        archive_dir=archive,
    )
    root = json.loads(state.read_text(encoding="utf-8"))
    assert root["variants"]["v2_28dte_atm"]["paper_events"] == []
    assert root["variants"]["v2_28dte_atm"]["entry_log"] == [{"entered": True}]
    assert meta["pnl_epoch_commit"] == "abc"
    sb = json.loads(scoreboard.read_text(encoding="utf-8"))
    row = sb["shadow_variants"][0]
    assert row["variant_id"] == "v2_28dte_atm"
    assert row["trades_closed"] == 0
    assert row["realized_pnl_usd"] == 0.0
    assert sb["baseline_prod"]["trades_closed"] == 0


def test_build_scoreboard_regime_gate_comparison(tmp_path):
    _write_variants_config(
        tmp_path,
        {
            "v2_yellow_mid_bounce": {
                "active": True,
                "description": "Mid bounce test",
                "overrides": {
                    "logging": {"logic_version": "xsp_lane_a_v2_yellow_mid_bounce"},
                    "entry": {
                        "regime_gate": "GREEN_OR_YELLOW_BOUNCE",
                        "regime_yellow_frac_min": 0.50,
                    },
                },
            },
            "v2_yellow_top_quartile_bounce": {
                "active": True,
                "description": "Top quartile bounce test",
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
    state = tmp_path / "variants-state.json"
    baseline = tmp_path / "baseline-state.json"
    state.write_text(
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

    payload = json.loads(
        build_scoreboard(
            config_path=tmp_path / "lane_a_variants.yaml",
            state_path=state,
            baseline_state_path=baseline,
            out_path=tmp_path / "scoreboard.json",
        ).read_text(encoding="utf-8")
    )

    mid = next(
        r for r in payload["shadow_variants"] if r["variant_id"] == "v2_yellow_mid_bounce"
    )
    top = next(
        r
        for r in payload["shadow_variants"]
        if r["variant_id"] == "v2_yellow_top_quartile_bounce"
    )
    assert mid["track_family"] == "yellow_bounce_frac_axis"
    assert mid["regime_yellow_frac_min"] == 0.50
    assert top["regime_yellow_frac_min"] == 0.75
    assert mid["bb_bounce_signal_sessions"] == 1
    assert mid["bb_bounce_blocked_by_regime_sessions"] == 1
    assert payload["baseline_prod"]["track_family"] == "baseline_green"
    assert payload["baseline_prod"]["regime_gate"] == "GREEN"

    comparison = payload["regime_gate_comparison"]
    assert comparison["baseline_variant_id"] == "v2_baseline_prod"
    assert [v["variant_id"] for v in comparison["variants"]] == [
        "v2_baseline_prod",
        "v2_yellow_mid_bounce",
        "v2_yellow_top_quartile_bounce",
    ]
    assert comparison["variants"][1]["regime_yellow_frac_min"] == 0.50
    assert comparison["variants"][2]["regime_yellow_frac_min"] == 0.75
