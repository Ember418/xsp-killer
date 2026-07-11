"""Tests for K159 Fable Advisor orchestration spike (no plugin install)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from xsp_killer.fable_advisor_spike import (
    TokenSpikeMetrics,
    cross_vendor_review_required,
    evaluate_go_nogo,
    fable_advisor_enabled,
    grok_lane_available,
    load_k159_config,
    meets_adopt_threshold,
    record_spike_sample,
    run_brief_iteration_spike,
    token_reduction_pct,
)


def test_fable_advisor_enabled_default_off(monkeypatch):
    monkeypatch.delenv("XSP_K159_FABLE_ADVISOR", raising=False)
    assert fable_advisor_enabled() is False


def test_fable_advisor_enabled_on(monkeypatch):
    monkeypatch.setenv("XSP_K159_FABLE_ADVISOR", "1")
    assert fable_advisor_enabled() is True
    monkeypatch.setenv("XSP_K159_FABLE_ADVISOR", "true")
    assert fable_advisor_enabled() is True


def test_grok_lane_available_default_off(monkeypatch):
    monkeypatch.delenv("XSP_K159_GROK_LANE", raising=False)
    assert grok_lane_available() is False


def test_grok_lane_available_on(monkeypatch):
    monkeypatch.setenv("XSP_K159_GROK_LANE", "yes")
    assert grok_lane_available() is True


def test_load_k159_config_from_yaml(tmp_path: Path):
    cfg = tmp_path / "k159.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "k159": {
                    "version": "test",
                    "repo": "DannyMac180/fable-advisor",
                    "token_reduction_adopt_threshold_pct": 30,
                    "go_nogo": {"default_verdict": "NO_GO"},
                }
            }
        ),
        encoding="utf-8",
    )
    loaded = load_k159_config(cfg)
    assert loaded["version"] == "test"
    assert loaded["repo"] == "DannyMac180/fable-advisor"


def test_load_k159_config_prod():
    cfg = load_k159_config()
    assert cfg.get("version") == "2026-07-11"
    assert cfg.get("repo") == "DannyMac180/fable-advisor"
    assert cfg.get("license") == "MIT"
    assert cfg["roles"]["fable"] == "architect_reviewer_only"
    assert "grok-4.5" in cfg["roles"]["implementation_models"]
    assert "gpt-5.6-sol" in cfg["roles"]["implementation_models"]
    assert cfg["token_reduction_adopt_threshold_pct"] == 30
    assert cfg["cross_vendor_review_required"] is True
    assert cfg["prereq"]["claude_code_min_version"] == "2.1.170"
    assert cfg["go_nogo"]["default_verdict"] == "NO_GO"
    assert cfg["spike"]["iterations"] == 1


def test_token_reduction_pct_basic():
    assert token_reduction_pct(1000, 700) == 30.0
    assert token_reduction_pct(1000, 500) == 50.0
    assert token_reduction_pct(1000, 1000) == 0.0


def test_token_reduction_pct_zero_baseline():
    assert token_reduction_pct(0, 500) == 0.0


def test_meets_adopt_threshold_at_boundary():
    assert meets_adopt_threshold(30.0, 30) is True
    assert meets_adopt_threshold(29.99, 30) is False
    assert meets_adopt_threshold(40.0) is True


def test_cross_vendor_review_required_prod_only():
    cfg = {"cross_vendor_review_required": True}
    assert cross_vendor_review_required(True, cfg) is True
    assert cross_vendor_review_required(False, cfg) is False


def test_cross_vendor_review_required_disabled_in_config():
    cfg = {"cross_vendor_review_required": False}
    assert cross_vendor_review_required(True, cfg) is False


def test_evaluate_go_nogo_no_grok_lane(monkeypatch):
    monkeypatch.delenv("XSP_K159_GROK_LANE", raising=False)
    cfg = {"go_nogo": {"default_verdict": "NO_GO", "min_samples_for_verdict": 1}}
    samples = [{"baseline_tokens": 1000, "spike_tokens": 500, "reduction_pct": 50.0}]
    assert evaluate_go_nogo(samples, cfg) == "NO_GO"


def test_evaluate_go_nogo_default_insufficient_samples(monkeypatch):
    monkeypatch.setenv("XSP_K159_GROK_LANE", "1")
    cfg = {"go_nogo": {"default_verdict": "NO_GO", "min_samples_for_verdict": 3}}
    assert evaluate_go_nogo([{"baseline_tokens": 1000, "spike_tokens": 500}], cfg) == "NO_GO"


def test_evaluate_go_nogo_no_go_below_threshold(monkeypatch):
    monkeypatch.setenv("XSP_K159_GROK_LANE", "1")
    cfg = {
        "token_reduction_adopt_threshold_pct": 30,
        "go_nogo": {"default_verdict": "NO_GO", "min_samples_for_verdict": 1},
    }
    samples = [{"baseline_tokens": 1000, "spike_tokens": 800, "reduction_pct": 20.0}]
    assert evaluate_go_nogo(samples, cfg) == "NO_GO"


def test_evaluate_go_nogo_no_go_missing_cross_vendor_review(monkeypatch):
    monkeypatch.setenv("XSP_K159_GROK_LANE", "1")
    cfg = {
        "token_reduction_adopt_threshold_pct": 30,
        "cross_vendor_review_required": True,
        "go_nogo": {"default_verdict": "NO_GO", "min_samples_for_verdict": 1},
    }
    samples = [
        {
            "baseline_tokens": 1000,
            "spike_tokens": 600,
            "reduction_pct": 40.0,
            "diff_touches_prod": True,
            "cross_vendor_review_done": False,
        }
    ]
    assert evaluate_go_nogo(samples, cfg) == "NO_GO"


def test_evaluate_go_nogo_go_when_thresholds_pass(monkeypatch):
    monkeypatch.setenv("XSP_K159_GROK_LANE", "1")
    cfg = {
        "token_reduction_adopt_threshold_pct": 30,
        "go_nogo": {"default_verdict": "NO_GO", "min_samples_for_verdict": 1},
    }
    samples = [
        {
            "baseline_tokens": 1000,
            "spike_tokens": 650,
            "reduction_pct": 35.0,
            "diff_touches_prod": True,
            "cross_vendor_review_done": True,
        }
    ]
    assert evaluate_go_nogo(samples, cfg) == "GO"


def test_evaluate_go_nogo_skips_skipped_rows(monkeypatch):
    monkeypatch.setenv("XSP_K159_GROK_LANE", "1")
    cfg = {"go_nogo": {"default_verdict": "NO_GO", "min_samples_for_verdict": 1}}
    samples = [{"skipped": True, "baseline_tokens": 1000, "spike_tokens": 100}]
    assert evaluate_go_nogo(samples, cfg) == "NO_GO"


def test_record_spike_sample_appends_ndjson(tmp_path: Path):
    log_path = tmp_path / "spike.jsonl"
    record_spike_sample(
        {"task_id": "brief-1", "baseline_tokens": 1000, "spike_tokens": 700},
        log_path=log_path,
    )
    record_spike_sample({"task_id": "brief-2", "reduction_pct": 30.0}, log_path=log_path)
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["task_id"] == "brief-1"
    assert "ts" in rows[0]


def test_run_brief_iteration_spike_disabled(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("XSP_K159_FABLE_ADVISOR", raising=False)
    log_path = tmp_path / "spike.jsonl"
    out = run_brief_iteration_spike(
        "task-a",
        baseline_tokens=1000,
        spike_tokens=700,
        log_path=log_path,
    )
    assert out["skipped"] is True
    assert out["reason"] == "not_enabled"
    assert isinstance(out["metrics"], TokenSpikeMetrics)
    assert out["metrics"].skipped is True
    assert log_path.is_file()


def test_run_brief_iteration_spike_enabled(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XSP_K159_FABLE_ADVISOR", "1")
    monkeypatch.setenv("XSP_K159_GROK_LANE", "1")
    log_path = tmp_path / "spike.jsonl"
    out = run_brief_iteration_spike(
        "k159-brief-iter",
        baseline_tokens=10000,
        spike_tokens=6500,
        diff_touches_prod=False,
        log_path=log_path,
    )
    assert out["skipped"] is False
    assert out["task_id"] == "k159-brief-iter"
    assert out["reduction_pct"] == 35.0
    assert out["meets_threshold"] is True
    assert out["grok_lane_available"] is True
    assert out["cross_vendor_review_required"] is False
    assert out["metrics"].baseline_tokens == 10000
    assert log_path.read_text(encoding="utf-8").count("\n") == 1


def test_run_brief_iteration_spike_prod_requires_review(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XSP_K159_FABLE_ADVISOR", "1")
    monkeypatch.delenv("XSP_K159_GROK_LANE", raising=False)
    out = run_brief_iteration_spike(
        "prod-touch",
        baseline_tokens=1000,
        spike_tokens=600,
        diff_touches_prod=True,
        cross_vendor_review_done=False,
        log_path=tmp_path / "s.jsonl",
    )
    assert out["cross_vendor_review_required"] is True
    assert out["grok_lane_available"] is False
    assert out["metrics"].cross_vendor_review_required is True


def test_maybe_log_fable_spike_disabled(monkeypatch):
    from xsp_killer.macro_weather_notes import maybe_log_fable_spike

    monkeypatch.delenv("XSP_K159_FABLE_ADVISOR", raising=False)
    assert maybe_log_fable_spike("task-x", baseline_tokens=1000, spike_tokens=700) is None


def test_maybe_log_fable_spike_enabled(monkeypatch, tmp_path: Path):
    from xsp_killer.macro_weather_notes import maybe_log_fable_spike
    from xsp_killer import fable_advisor_spike as spike_mod

    monkeypatch.setenv("XSP_K159_FABLE_ADVISOR", "1")
    monkeypatch.setattr(spike_mod, "DEFAULT_SPIKE_LOG", tmp_path / "spike.jsonl")
    out = maybe_log_fable_spike("hook-task", baseline_tokens=2000, spike_tokens=1200)
    assert out is not None
    assert out["reduction_pct"] == 40.0
    assert out["meets_threshold"] is True
