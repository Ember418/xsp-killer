"""Tests for K155 macro weather operator notes."""

from __future__ import annotations

from pathlib import Path

import yaml

from xsp_killer.macro_weather_notes import (
    USDJPY_ZONE,
    build_macro_weather_extras,
    build_monitor_macro_weather_extras,
    conviction_journal_fields,
    load_k155_notes,
)


def test_usdjpy_zone_constants():
    assert USDJPY_ZONE == (162.25, 162.50)


def test_build_macro_weather_extras_in_zone():
    extras = build_macro_weather_extras(
        usdjpy=162.35,
        sofr_curve_note="SOFR anchor",
        event_cluster="July FOMC / CPI cluster",
    )
    assert extras["usdjpy_in_zone"] is True
    assert extras["usdjpy_zone_lo"] == 162.25
    assert extras["sofr_curve_note"] == "SOFR anchor"


def test_build_macro_weather_extras_outside_zone():
    extras = build_macro_weather_extras(
        usdjpy=160.0,
        sofr_curve_note=None,
        event_cluster=None,
    )
    assert extras["usdjpy_in_zone"] is False


def test_conviction_journal_blocks_size_up_on_balanced_pro_con():
    blocked = conviction_journal_fields(
        evidence_count=1,
        cross_asset_confirms=0,
        pro_con_balanced=True,
    )
    assert blocked["block_size_up"] is True
    assert blocked["conviction_sufficient"] is False

    allowed = conviction_journal_fields(
        evidence_count=2,
        cross_asset_confirms=1,
        pro_con_balanced=True,
    )
    assert allowed["block_size_up"] is False
    assert allowed["conviction_sufficient"] is True


def test_conviction_journal_no_block_when_not_balanced():
    fields = conviction_journal_fields(
        evidence_count=0,
        cross_asset_confirms=0,
        pro_con_balanced=False,
    )
    assert fields["block_size_up"] is False


def test_load_k155_notes_from_yaml(tmp_path: Path):
    cfg = tmp_path / "k155.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "k155": {
                    "version": "test",
                    "event_cluster": "CPI cluster",
                    "sofr_curve": {"note": "anchor"},
                }
            }
        ),
        encoding="utf-8",
    )
    notes = load_k155_notes(cfg)
    assert notes["version"] == "test"
    assert notes["sofr_curve"]["note"] == "anchor"


def test_build_monitor_macro_weather_extras_merges_k155(tmp_path: Path):
    cfg = tmp_path / "k155.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "k155": {
                    "version": "2026-07-10",
                    "event_cluster": "July FOMC / CPI cluster",
                    "sofr_curve": {"note": "SOFR anchor"},
                    "events": {"cpi": {"date": "2026-07-15"}},
                    "cme_ssf": {"date": "2026-07-27"},
                }
            }
        ),
        encoding="utf-8",
    )
    notes = load_k155_notes(cfg)
    extras = build_monitor_macro_weather_extras(notes, usdjpy=162.40)
    assert extras is not None
    assert extras["usdjpy_in_zone"] is True
    assert extras["events"]["cpi"]["date"] == "2026-07-15"
    assert extras["cme_ssf"]["date"] == "2026-07-27"


def test_load_k155_notes_prod_config():
    notes = load_k155_notes()
    assert notes.get("version") == "2026-07-10"
    assert notes["events"]["cpi"]["date"] == "2026-07-15"
    assert notes["cme_ssf"]["date"] == "2026-07-27"


def test_run_monitor_attaches_macro_weather_extras(tmp_path, monkeypatch):
    from xsp_killer.lane_a_monitor import run_monitor

    monkeypatch.setattr(
        "xsp_killer.lane_a_monitor.rh_read_enabled",
        lambda: False,
    )
    report = run_monitor(
        state_path=tmp_path / "state.json",
        positions_override=[],
        publish_intel=False,
        write_paper_brief=False,
    )
    assert report.macro_weather_extras is not None
    assert report.macro_weather_extras["k155_version"] == "2026-07-10"
    assert "events" in report.macro_weather_extras
