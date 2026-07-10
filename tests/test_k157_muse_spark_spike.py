"""Tests for K157 Muse Spark orchestration spike (no live vals.ai calls)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from xsp_killer.muse_spark_spike import (
    MuseSparkClient,
    MuseSparkError,
    RateLimitStallError,
    SpikeMetrics,
    cost_gate_ok,
    evaluate_go_nogo,
    latency_percentiles,
    load_k157_config,
    muse_spark_enabled,
    record_spike_sample,
    run_macro_research_enrichment,
)


def test_muse_spark_enabled_default_off(monkeypatch):
    monkeypatch.delenv("XSP_K157_MUSE_SPARK", raising=False)
    assert muse_spark_enabled() is False


def test_muse_spark_enabled_on(monkeypatch):
    monkeypatch.setenv("XSP_K157_MUSE_SPARK", "1")
    assert muse_spark_enabled() is True
    monkeypatch.setenv("XSP_K157_MUSE_SPARK", "true")
    assert muse_spark_enabled() is True


def test_load_k157_config_from_yaml(tmp_path: Path):
    cfg = tmp_path / "k157.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "k157": {
                    "version": "test",
                    "model": "meta_muse-spark-1.1",
                    "go_nogo": {"default_verdict": "NO_GO"},
                }
            }
        ),
        encoding="utf-8",
    )
    loaded = load_k157_config(cfg)
    assert loaded["version"] == "test"
    assert loaded["model"] == "meta_muse-spark-1.1"


def test_load_k157_config_prod():
    cfg = load_k157_config()
    assert cfg.get("version") == "2026-07-10"
    assert cfg.get("model") == "meta_muse-spark-1.1"
    assert cfg["api"]["base_url"] == "https://api.vals.ai/v1"
    assert cfg["spike"]["window_days"] == 30
    assert cfg["go_nogo"]["default_verdict"] == "NO_GO"
    assert cfg["cost_gate"]["baseline_usd_per_loop"] == 0.12


def test_latency_percentiles_empty():
    assert latency_percentiles([]) == {"p50": None, "p95": None}


def test_latency_percentiles_computes_p50_p95():
    samples = [{"latency_ms": ms} for ms in (100, 200, 300, 400, 1000)]
    out = latency_percentiles(samples)
    assert out["p50"] == 300.0
    assert out["p95"] == pytest.approx(880.0, rel=0.01)


def test_latency_percentiles_skips_skipped_rows():
    samples = [
        {"latency_ms": 100},
        {"latency_ms": 200, "skipped": True},
        {"latency_ms": 300},
    ]
    out = latency_percentiles(samples)
    assert out["p50"] == 200.0


def test_cost_gate_ok_within_baseline():
    assert cost_gate_ok(0.10, 0.12) is True


def test_cost_gate_ok_exceeds_baseline():
    assert cost_gate_ok(0.13, 0.12) is False


def test_evaluate_go_nogo_default_insufficient_samples():
    cfg = {"go_nogo": {"default_verdict": "NO_GO", "min_samples_for_verdict": 10}}
    assert evaluate_go_nogo([{"latency_ms": 100}], cfg) == "NO_GO"


def test_evaluate_go_nogo_no_go_on_high_p95():
    cfg = {
        "go_nogo": {
            "default_verdict": "NO_GO",
            "min_samples_for_verdict": 3,
            "latency_p95_ms_max": 500,
        },
        "cost_gate": {"baseline_usd_per_loop": 0.12},
    }
    samples = [{"latency_ms": ms, "cost_usd": 0.05} for ms in range(100, 1100, 100)]
    assert evaluate_go_nogo(samples, cfg) == "NO_GO"


def test_evaluate_go_nogo_no_go_on_rate_limit_stalls():
    cfg = {
        "go_nogo": {
            "default_verdict": "NO_GO",
            "min_samples_for_verdict": 2,
            "rate_limit_stalls_max": 0,
            "latency_p95_ms_max": 50000,
        },
        "cost_gate": {"baseline_usd_per_loop": 0.12},
    }
    samples = [
        {"latency_ms": 100, "cost_usd": 0.05},
        {"latency_ms": 120, "cost_usd": 0.05, "rate_limit_stall": True},
    ]
    assert evaluate_go_nogo(samples, cfg) == "NO_GO"


def test_evaluate_go_nogo_go_when_thresholds_pass():
    cfg = {
        "go_nogo": {
            "default_verdict": "NO_GO",
            "min_samples_for_verdict": 3,
            "latency_p50_ms_max": 500,
            "latency_p95_ms_max": 500,
            "rate_limit_stalls_max": 0,
        },
        "cost_gate": {"baseline_usd_per_loop": 0.12},
    }
    samples = [
        {"latency_ms": 100, "cost_usd": 0.05},
        {"latency_ms": 110, "cost_usd": 0.06},
        {"latency_ms": 120, "cost_usd": 0.04},
    ]
    assert evaluate_go_nogo(samples, cfg) == "GO"


def test_record_spike_sample_appends_ndjson(tmp_path: Path):
    log_path = tmp_path / "spike.jsonl"
    record_spike_sample({"latency_ms": 42.0, "skipped": True}, log_path=log_path)
    record_spike_sample({"latency_ms": 99.0}, log_path=log_path)
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["latency_ms"] == 42.0
    assert "ts" in rows[0]


def test_muse_spark_client_complete_mocked():
    def fake_post(url: str, body: bytes, headers: dict[str, str]) -> dict:
        assert "/chat/completions" in url
        assert headers["Authorization"] == "Bearer test-key"
        payload = json.loads(body.decode("utf-8"))
        assert payload["model"] == "meta_muse-spark-1.1"
        return {
            "choices": [{"message": {"content": "- CPI cluster watch\n- SOFR flat"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }

    client = MuseSparkClient(
        {"model": "meta_muse-spark-1.1", "api": {"base_url": "https://api.vals.ai/v1"}},
        api_key="test-key",
        http_post=fake_post,
    )
    out = client.complete([{"role": "user", "content": "macro checklist"}])
    assert "CPI cluster" in out["text"]
    assert out["tokens_in"] == 100
    assert out["tokens_out"] == 50
    assert out["rate_limit_stall"] is False
    assert out["latency_ms"] >= 0


def test_muse_spark_client_rate_limit_stall():
    def rate_limited(url: str, body: bytes, headers: dict[str, str]) -> dict:
        raise RateLimitStallError("429")

    client = MuseSparkClient(
        {"model": "meta_muse-spark-1.1"},
        api_key="test-key",
        http_post=rate_limited,
    )
    out = client.complete([{"role": "user", "content": "x"}])
    assert out["rate_limit_stall"] is True
    assert out["aborted"] is True


def test_muse_spark_client_missing_api_key():
    client = MuseSparkClient({"model": "meta_muse-spark-1.1"}, api_key=None)
    with pytest.raises(MuseSparkError, match="API_KEY"):
        client.complete([{"role": "user", "content": "x"}])


def test_run_macro_research_enrichment_disabled(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("XSP_K157_MUSE_SPARK", raising=False)
    log_path = tmp_path / "spike.jsonl"
    out = run_macro_research_enrichment("test prompt", log_path=log_path)
    assert out["skipped"] is True
    assert out["reason"] == "not_enabled"
    assert isinstance(out["metrics"], SpikeMetrics)
    assert out["metrics"].skipped is True
    assert log_path.is_file()


def test_run_macro_research_enrichment_enabled_mocked(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XSP_K157_MUSE_SPARK", "1")

    def fake_post(url: str, body: bytes, headers: dict[str, str]) -> dict:
        return {
            "choices": [{"message": {"content": "enriched macro notes"}}],
            "usage": {"prompt_tokens": 80, "completion_tokens": 40},
        }

    client = MuseSparkClient(
        {
            "model": "meta_muse-spark-1.1",
            "cost_gate": {
                "baseline_usd_per_loop": 0.12,
                "max_cost_usd_per_loop": 0.15,
                "abort_on_breach": True,
            },
        },
        api_key="test-key",
        http_post=fake_post,
    )
    log_path = tmp_path / "spike.jsonl"
    out = run_macro_research_enrichment(
        "pre-Lane-A checklist",
        client=client,
        log_path=log_path,
    )
    assert out["skipped"] is False
    assert out["enrichment"] == "enriched macro notes"
    assert out["cost_gate_ok"] is True
    assert out["metrics"].latency_ms is not None
    assert log_path.read_text(encoding="utf-8").count("\n") == 1


def test_run_macro_research_enrichment_cost_gate_abort(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XSP_K157_MUSE_SPARK", "1")

    def expensive_post(url: str, body: bytes, headers: dict[str, str]) -> dict:
        return {
            "choices": [{"message": {"content": "too expensive"}}],
            "usage": {"prompt_tokens": 50000, "completion_tokens": 50000},
        }

    client = MuseSparkClient(
        {
            "model": "meta_muse-spark-1.1",
            "cost_gate": {
                "baseline_usd_per_loop": 0.12,
                "max_cost_usd_per_loop": 0.01,
                "abort_on_breach": True,
            },
        },
        api_key="test-key",
        http_post=expensive_post,
    )
    out = run_macro_research_enrichment("prompt", client=client, log_path=tmp_path / "s.jsonl")
    assert out["cost_gate_ok"] is False
    assert out["aborted"] is True


def test_maybe_enrich_with_muse_spark_disabled(monkeypatch):
    from xsp_killer.macro_weather_notes import maybe_enrich_with_muse_spark

    monkeypatch.delenv("XSP_K157_MUSE_SPARK", raising=False)
    assert maybe_enrich_with_muse_spark("macro prompt") is None


def test_maybe_enrich_with_muse_spark_enabled(monkeypatch, tmp_path: Path):
    from xsp_killer.macro_weather_notes import maybe_enrich_with_muse_spark
    from xsp_killer import muse_spark_spike as spike_mod

    monkeypatch.setenv("XSP_K157_MUSE_SPARK", "1")
    monkeypatch.setattr(spike_mod, "DEFAULT_SPIKE_LOG", tmp_path / "spike.jsonl")

    def fake_post(url: str, body: bytes, headers: dict[str, str]) -> dict:
        return {
            "choices": [{"message": {"content": "hook enrichment"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10},
        }

    monkeypatch.setattr(
        spike_mod.MuseSparkClient,
        "complete",
        lambda self, messages, max_tokens=1024: {
            "text": "hook enrichment",
            "model": "meta_muse-spark-1.1",
            "latency_ms": 5.0,
            "tokens_in": 10,
            "tokens_out": 10,
            "cost_usd": 0.001,
            "rate_limit_stall": False,
            "aborted": False,
        },
    )
    out = maybe_enrich_with_muse_spark("macro prompt")
    assert out is not None
    assert out["enrichment"] == "hook enrichment"
