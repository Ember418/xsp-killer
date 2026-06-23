"""Tests for Lane A variant soak."""

from __future__ import annotations

import json

from xsp_killer.lane_a_variants import (
    build_scoreboard,
    clear_pnl_epoch,
    load_variant_specs,
    merged_rules_path,
    reset_soak,
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
    out = build_scoreboard(
        state_path=state,
        baseline_state_path=tmp_path / "missing-baseline.json",
        out_path=tmp_path / "scoreboard.json",
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    row = next(r for r in payload["variants"] if r["variant_id"] == "v2_28dte_atm")
    assert row["realized_pnl_usd"] == 5.0
    assert row["trades_closed"] == 2
    assert row["avg_pnl_per_trade_usd"] == 2.5
    assert payload["baseline_prod"] is None
    assert len(payload["shadow_variants"]) == 1
    assert "Do NOT sum PnL" in payload["comparison_guidance"]


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
                        "paper_events": [{"paper_pnl_usd": -100.0, "evaluated_at": "2026-06-23T14:00:00+00:00"}],
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
    monkeypatch.setattr("xsp_killer.lane_a_variants.load_variant_specs", lambda _path=None: [])

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
