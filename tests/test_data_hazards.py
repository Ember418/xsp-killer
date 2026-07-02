"""Tests for K129 data hazard classification."""

from __future__ import annotations

import xsp_killer.lane_a_entry as lane_a_entry
import xsp_killer.lane_a_monitor as lane_a_monitor
from xsp_killer.data_hazards import (
    EXECUTION_FAILURE,
    OUTPUT_DRIFT,
    classify_chain_hazard,
    classify_regime_hazard,
)


def test_empty_chain_is_execution_failure():
    assert classify_chain_hazard("empty_chain") == EXECUTION_FAILURE


def test_mark_jump_is_output_drift():
    assert classify_chain_hazard("mark_jump_25.0pct_vs_last_poll") == OUTPUT_DRIFT


def test_regime_insufficient_data_hazard():
    assert (
        classify_regime_hazard("Insufficient SPY data — defensive default")
        == EXECUTION_FAILURE
    )


def test_runtime_briefs_are_isolated_to_tmp_paths():
    assert "xsp_runtime" in str(lane_a_monitor.DEFAULT_PAPER_BRIEF)
    assert "xsp_runtime" in str(lane_a_entry.DEFAULT_TELEMETRY_BRIEF)
