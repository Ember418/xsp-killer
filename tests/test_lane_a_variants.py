"""Tests for Lane A variant soak."""

from __future__ import annotations

import json
from pathlib import Path

from xsp_killer.lane_a_variants import (
    build_scoreboard,
    load_variant_specs,
    merged_rules_path,
    reset_soak,
    run_variant_entry,
)


def test_load_variant_specs():
    specs = load_variant_specs()
    assert len(specs) >= 10
    ids = {s.variant_id for s in specs}
    assert "v2_28dte_atm" in ids
    assert "v2_21dte_atm" in ids


def test_merged_rules_dte_target(tmp_path):
    specs = load_variant_specs()
    spec = next(s for s in specs if s.variant_id == "v2_28dte_atm")
    path = merged_rules_path(spec, tmp_dir=tmp_path)
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["entry"]["dte_pick"] == "target"
    assert data["entry"]["dte_target"] == 28
    assert data["entry"]["strike_pick"] == "atm_only"


def test_build_scoreboard(tmp_path, monkeypatch):
    state = tmp_path / "variants-state.json"
    state.write_text(
        json.dumps(
            {
                "variants": {
                    "v2_28dte_atm": {
                        "paper_events": [
                            {"paper_pnl_usd": 10.0},
                            {"paper_pnl_usd": -5.0},
                        ],
                        "paper_positions": {},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    out = build_scoreboard(state_path=state, out_path=tmp_path / "scoreboard.json")
    payload = json.loads(out.read_text(encoding="utf-8"))
    row = next(r for r in payload["variants"] if r["variant_id"] == "v2_28dte_atm")
    assert row["realized_pnl_usd"] == 5.0
    assert row["trades_closed"] == 2


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
                            {"paper_pnl_usd": -10.0, "evaluated_at": "2026-06-20T14:00:00+00:00"},
                            {"paper_pnl_usd": 7.0, "evaluated_at": "2026-06-21T14:00:00+00:00"},
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
    assert payload["soak_reset_at"] == reset_at


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
                        "paper_events": [{"paper_pnl_usd": -1.0, "evaluated_at": "2026-06-20T14:00:00+00:00"}],
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
