"""K159 Fable Advisor orchestration spike — opt-in brief iteration token eval (Phase 0)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml

logger = logging.getLogger("xsp_killer.fable_advisor_spike")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_K159_CONFIG = ROOT / "config" / "k159_fable_advisor_spike.yaml"
DEFAULT_SPIKE_LOG = ROOT / "logs" / "k159_fable_advisor_spike.jsonl"

Verdict = Literal["GO", "NO_GO"]


@dataclass
class TokenSpikeMetrics:
    """Per-iteration Fable Advisor token spike telemetry."""

    task_id: str
    baseline_tokens: int = 0
    spike_tokens: int = 0
    reduction_pct: float = 0.0
    meets_threshold: bool = False
    cross_vendor_review_required: bool = False
    cross_vendor_review_done: bool = False
    diff_touches_prod: bool = False
    grok_lane_available: bool = False
    skipped: bool = False
    skip_reason: str | None = None


def fable_advisor_enabled() -> bool:
    """True when XSP_K159_FABLE_ADVISOR opt-in flag is set (default off)."""
    return os.getenv("XSP_K159_FABLE_ADVISOR", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def load_k159_config(path: Path | None = None) -> dict[str, Any]:
    """Load K159 spike config from YAML."""
    p = path or DEFAULT_K159_CONFIG
    if not p.is_file():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    block = data.get("k159")
    return dict(block) if isinstance(block, dict) else {}


def token_reduction_pct(baseline_tokens: int, spike_tokens: int) -> float:
    """Compute token reduction percentage vs baseline (0 if baseline is zero)."""
    if baseline_tokens <= 0:
        return 0.0
    return round((1.0 - (spike_tokens / baseline_tokens)) * 100.0, 2)


def meets_adopt_threshold(reduction_pct: float, threshold: float = 30.0) -> bool:
    """True when reduction meets or exceeds the adopt threshold (default 30%)."""
    return reduction_pct >= threshold


def cross_vendor_review_required(
    diff_touches_prod: bool,
    config: dict[str, Any] | None = None,
) -> bool:
    """True when prod-touching diffs require cross-vendor review per config."""
    cfg = config if config is not None else load_k159_config()
    if not bool(cfg.get("cross_vendor_review_required", True)):
        return False
    return diff_touches_prod


def grok_lane_available() -> bool:
    """True when Grok implementation lane is configured (XSP_K159_GROK_LANE)."""
    return os.getenv("XSP_K159_GROK_LANE", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def evaluate_go_nogo(
    samples: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> Verdict:
    """Evaluate spike GO/NO-GO criteria; default verdict is NO_GO."""
    cfg = config if config is not None else load_k159_config()
    gates = cfg.get("go_nogo") if isinstance(cfg.get("go_nogo"), dict) else {}
    default_verdict = str(gates.get("default_verdict") or "NO_GO")
    if default_verdict not in ("GO", "NO_GO"):
        default_verdict = "NO_GO"

    if not grok_lane_available():
        return "NO_GO"

    active = [s for s in samples if not s.get("skipped")]
    min_samples = int(gates.get("min_samples_for_verdict") or 1)
    if len(active) < min_samples:
        return default_verdict  # type: ignore[return-value]

    threshold = float(cfg.get("token_reduction_adopt_threshold_pct") or 30)
    for sample in active:
        reduction = sample.get("reduction_pct")
        if reduction is None:
            baseline = int(sample.get("baseline_tokens") or 0)
            spike = int(sample.get("spike_tokens") or 0)
            reduction = token_reduction_pct(baseline, spike)
        if not meets_adopt_threshold(float(reduction), threshold):
            return "NO_GO"
        if sample.get("diff_touches_prod") and not sample.get("cross_vendor_review_done"):
            return "NO_GO"

    return "GO"


def record_spike_sample(
    sample: dict[str, Any],
    *,
    log_path: Path | None = None,
) -> Path:
    """Append one NDJSON spike sample row."""
    path = log_path or DEFAULT_SPIKE_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now(timezone.utc).isoformat(), **sample}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return path


def run_brief_iteration_spike(
    task_id: str,
    *,
    baseline_tokens: int,
    spike_tokens: int,
    diff_touches_prod: bool = False,
    cross_vendor_review_done: bool = False,
    config: dict[str, Any] | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """Run one XSP brief iteration spike; log token metrics when enabled."""
    cfg = config if config is not None else load_k159_config()
    if not fable_advisor_enabled():
        metrics = TokenSpikeMetrics(
            task_id=task_id,
            skipped=True,
            skip_reason="not_enabled",
        )
        sample = asdict(metrics)
        record_spike_sample(sample, log_path=log_path)
        return {"skipped": True, "reason": "not_enabled", "metrics": metrics}

    reduction = token_reduction_pct(baseline_tokens, spike_tokens)
    threshold = float(cfg.get("token_reduction_adopt_threshold_pct") or 30)
    meets = meets_adopt_threshold(reduction, threshold)
    cvr_required = cross_vendor_review_required(diff_touches_prod, cfg)
    grok_ok = grok_lane_available()

    metrics = TokenSpikeMetrics(
        task_id=task_id,
        baseline_tokens=baseline_tokens,
        spike_tokens=spike_tokens,
        reduction_pct=reduction,
        meets_threshold=meets,
        cross_vendor_review_required=cvr_required,
        cross_vendor_review_done=cross_vendor_review_done,
        diff_touches_prod=diff_touches_prod,
        grok_lane_available=grok_ok,
        skipped=False,
    )
    sample = asdict(metrics)
    record_spike_sample(sample, log_path=log_path)

    if cvr_required and not cross_vendor_review_done:
        logger.info(
            "K159 cross-vendor review required for prod-touching diff (task=%s)",
            task_id,
        )

    return {
        "skipped": False,
        "task_id": task_id,
        "metrics": metrics,
        "reduction_pct": reduction,
        "meets_threshold": meets,
        "grok_lane_available": grok_ok,
        "cross_vendor_review_required": cvr_required,
    }
