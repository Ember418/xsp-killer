"""Pytest isolation — keep soak/runtime artifacts out of production paths."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_runtime_artifacts(monkeypatch, tmp_path):
    runtime = tmp_path / "xsp_runtime"
    runtime.mkdir()

    paper_log = runtime / "xsp_lane_a_paper.jsonl"
    lane_b_log = runtime / "xsp_lane_b_paper.jsonl"
    state = runtime / "xsp-lane-a-state.json"
    entry_brief = runtime / "xsp-lane-a-entry-latest.json"
    monitor_brief = runtime / "xsp-lane-a-monitor-latest.json"
    intraday_brief = runtime / "xsp-lane-a-intraday-latest.json"

    targets = {
        "xsp_killer.lane_a_monitor.DEFAULT_PAPER_LOG": paper_log,
        "xsp_killer.lane_a_monitor.DEFAULT_STATE": state,
        "xsp_killer.lane_a_monitor.DEFAULT_OUT": monitor_brief,
        "xsp_killer.lane_a_entry.DEFAULT_PAPER_LOG": paper_log,
        "xsp_killer.lane_a_entry.DEFAULT_STATE": state,
        "xsp_killer.lane_a_entry.DEFAULT_OUT": entry_brief,
        "xsp_killer.lane_a_intraday.DEFAULT_INTRADAY_OUT": intraday_brief,
        "xsp_killer.lane_b_monitor.DEFAULT_PAPER_LOG": lane_b_log,
        "xsp_killer.risk_gates.DEFAULT_STATE": state,
    }
    for target, path in targets.items():
        monkeypatch.setattr(target, path, raising=False)

    monkeypatch.setenv("XSP_KILLER_TEST_ISOLATION", "1")
