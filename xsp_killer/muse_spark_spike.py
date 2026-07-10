"""K157 Muse Spark orchestration spike — opt-in macro research enrichment (Phase 0)."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

import yaml

logger = logging.getLogger("xsp_killer.muse_spark_spike")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_K157_CONFIG = ROOT / "config" / "k157_muse_spark_spike.yaml"
DEFAULT_SPIKE_LOG = ROOT / "logs" / "k157_muse_spark_spike.jsonl"

Verdict = Literal["GO", "NO_GO"]


@dataclass
class SpikeMetrics:
    """Per-call Muse Spark spike telemetry."""

    latency_ms: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    aborted: bool = False
    rate_limit_stall: bool = False
    skipped: bool = False
    skip_reason: str | None = None
    model: str | None = None
    enrichment: str | None = None


def muse_spark_enabled() -> bool:
    """True when XSP_K157_MUSE_SPARK opt-in flag is set (default off)."""
    return os.getenv("XSP_K157_MUSE_SPARK", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def load_k157_config(path: Path | None = None) -> dict[str, Any]:
    """Load K157 spike config from YAML."""
    p = path or DEFAULT_K157_CONFIG
    if not p.is_file():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    block = data.get("k157")
    return dict(block) if isinstance(block, dict) else {}


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        raise ValueError("empty sample set")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    k = (len(sorted_values) - 1) * pct / 100.0
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    if lo == hi:
        return float(sorted_values[lo])
    return float(sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo))


def latency_percentiles(samples: list[dict[str, Any]]) -> dict[str, float | None]:
    """Compute latency p50/p95 from spike sample dicts."""
    latencies = [
        float(s["latency_ms"])
        for s in samples
        if s.get("latency_ms") is not None and not s.get("skipped")
    ]
    if not latencies:
        return {"p50": None, "p95": None}
    latencies.sort()
    return {"p50": _percentile(latencies, 50), "p95": _percentile(latencies, 95)}


def cost_gate_ok(cost_usd: float, baseline_usd: float) -> bool:
    """True when per-loop cost does not exceed the baseline reference."""
    return cost_usd <= baseline_usd


def evaluate_go_nogo(
    samples: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> Verdict:
    """Evaluate spike GO/NO-GO criteria; default verdict is NO_GO."""
    cfg = config if config is not None else load_k157_config()
    gates = cfg.get("go_nogo") if isinstance(cfg.get("go_nogo"), dict) else {}
    default_verdict = str(gates.get("default_verdict") or "NO_GO")
    if default_verdict not in ("GO", "NO_GO"):
        default_verdict = "NO_GO"

    active = [s for s in samples if not s.get("skipped")]
    min_samples = int(gates.get("min_samples_for_verdict") or 10)
    if len(active) < min_samples:
        return default_verdict  # type: ignore[return-value]

    percentiles = latency_percentiles(active)
    p50_max = gates.get("latency_p50_ms_max")
    p95_max = gates.get("latency_p95_ms_max")
    if p50_max is not None and percentiles["p50"] is not None:
        if percentiles["p50"] > float(p50_max):
            return "NO_GO"
    if p95_max is not None and percentiles["p95"] is not None:
        if percentiles["p95"] > float(p95_max):
            return "NO_GO"

    stall_max = int(gates.get("rate_limit_stalls_max") or 0)
    stall_count = sum(1 for s in active if s.get("rate_limit_stall"))
    if stall_count > stall_max:
        return "NO_GO"

    cost_gate = cfg.get("cost_gate") if isinstance(cfg.get("cost_gate"), dict) else {}
    baseline = float(cost_gate.get("baseline_usd_per_loop") or 0.12)
    for sample in active:
        cost = sample.get("cost_usd")
        if cost is not None and not cost_gate_ok(float(cost), baseline):
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


def _resolve_api_key() -> str | None:
    return os.getenv("XSP_K157_VALS_API_KEY") or os.getenv("VALS_API_KEY")


def _resolve_base_url(config: dict[str, Any]) -> str:
    override = os.getenv("XSP_K157_VALS_BASE_URL")
    if override:
        return override.rstrip("/")
    api = config.get("api") if isinstance(config.get("api"), dict) else {}
    return str(api.get("base_url") or "https://api.vals.ai/v1").rstrip("/")


def _estimate_cost_usd(tokens_in: int, tokens_out: int) -> float:
    # vals.ai published ballpark for Muse Spark; spike uses consistent estimate.
    return round((tokens_in * 0.000003) + (tokens_out * 0.000015), 6)


class MuseSparkClient:
    """vals.ai OpenAI-compatible client for meta_muse-spark-1.1 (mock-friendly)."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        api_key: str | None = None,
        http_post: Callable[[str, bytes, dict[str, str]], dict[str, Any]] | None = None,
    ) -> None:
        self.config = config if config is not None else load_k157_config()
        self.api_key = api_key if api_key is not None else _resolve_api_key()
        self._http_post = http_post

    def _chat_url(self) -> str:
        api = self.config.get("api") if isinstance(self.config.get("api"), dict) else {}
        base = _resolve_base_url(self.config)
        path = str(api.get("chat_completions_path") or "/chat/completions")
        return f"{base}{path}"

    def _default_http_post(
        self, url: str, body: bytes, headers: dict[str, str]
    ) -> dict[str, Any]:
        try:
            import httpx

            response = httpx.post(url, content=body, headers=headers, timeout=120.0)
            if response.status_code == 429:
                raise RateLimitStallError("vals.ai rate limit (429)")
            response.raise_for_status()
            return response.json()
        except ImportError:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:  # nosec B310
                    raw = resp.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    raise RateLimitStallError("vals.ai rate limit (429)") from exc
                detail = exc.read().decode("utf-8", errors="replace")
                raise MuseSparkError(f"vals.ai HTTP {exc.code}: {detail[:500]}") from exc
            except urllib.error.URLError as exc:
                raise MuseSparkError(f"vals.ai network error: {exc}") from exc
            return json.loads(raw)

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise MuseSparkError("VALS_API_KEY or XSP_K157_VALS_API_KEY required")

        model = str(self.config.get("model") or "meta_muse-spark-1.1")
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        http_post = self._http_post or self._default_http_post
        started = time.perf_counter()
        try:
            data = http_post(self._chat_url(), body, headers)
        except RateLimitStallError:
            latency_ms = (time.perf_counter() - started) * 1000.0
            return {
                "text": "",
                "model": model,
                "latency_ms": latency_ms,
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_usd": 0.0,
                "rate_limit_stall": True,
                "aborted": True,
            }
        latency_ms = (time.perf_counter() - started) * 1000.0
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        tokens_in = int(usage.get("prompt_tokens") or 0)
        tokens_out = int(usage.get("completion_tokens") or 0)
        choices = data.get("choices") or []
        text = ""
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            if isinstance(message, dict):
                text = str(message.get("content") or "")
        cost_usd = _estimate_cost_usd(tokens_in, tokens_out)
        return {
            "text": text,
            "model": model,
            "latency_ms": latency_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "rate_limit_stall": False,
            "aborted": False,
        }


class MuseSparkError(RuntimeError):
    """vals.ai client failure."""


class RateLimitStallError(MuseSparkError):
    """Rate-limit stall during Muse Spark call."""


def run_macro_research_enrichment(
    prompt: str,
    *,
    baseline_fn: Callable[[str], dict[str, Any]] | None = None,
    client: MuseSparkClient | None = None,
    config: dict[str, Any] | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """Run optional Muse Spark macro-research enrichment; log metrics when enabled."""
    cfg = config if config is not None else load_k157_config()
    if not muse_spark_enabled():
        metrics = SpikeMetrics(skipped=True, skip_reason="not_enabled")
        sample = asdict(metrics)
        sample["prompt_len"] = len(prompt)
        record_spike_sample(sample, log_path=log_path)
        return {"skipped": True, "reason": "not_enabled", "metrics": metrics}

    cost_gate = cfg.get("cost_gate") if isinstance(cfg.get("cost_gate"), dict) else {}
    baseline_usd = float(cost_gate.get("baseline_usd_per_loop") or 0.12)
    max_cost = float(cost_gate.get("max_cost_usd_per_loop") or baseline_usd)
    abort_on_breach = bool(cost_gate.get("abort_on_breach", True))

    if baseline_fn is not None:
        baseline = baseline_fn(prompt)
        baseline_cost = float(baseline.get("cost_usd") or baseline_usd)
        baseline_usd = min(baseline_usd, baseline_cost) if baseline_cost > 0 else baseline_usd

    spark = client or MuseSparkClient(cfg)
    messages = [
        {
            "role": "system",
            "content": (
                "You are a macro-research subagent for XSP pre-Lane-A checklist enrichment. "
                "Return concise bullet notes only."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    try:
        result = spark.complete(messages)
    except MuseSparkError as exc:
        metrics = SpikeMetrics(aborted=True, skip_reason=str(exc))
        sample = asdict(metrics)
        sample["prompt_len"] = len(prompt)
        record_spike_sample(sample, log_path=log_path)
        logger.warning("K157 Muse Spark enrichment failed: %s", exc)
        return {"skipped": False, "error": str(exc), "metrics": metrics}

    cost_usd = float(result.get("cost_usd") or 0.0)
    gate_ok = cost_gate_ok(cost_usd, max_cost)
    aborted = bool(result.get("aborted")) or (abort_on_breach and not gate_ok)

    metrics = SpikeMetrics(
        latency_ms=float(result.get("latency_ms") or 0.0),
        tokens_in=int(result.get("tokens_in") or 0),
        tokens_out=int(result.get("tokens_out") or 0),
        cost_usd=cost_usd,
        aborted=aborted,
        rate_limit_stall=bool(result.get("rate_limit_stall")),
        skipped=False,
        model=str(result.get("model") or cfg.get("model") or ""),
        enrichment=str(result.get("text") or "") or None,
    )
    sample = asdict(metrics)
    sample["prompt_len"] = len(prompt)
    sample["cost_gate_ok"] = gate_ok
    record_spike_sample(sample, log_path=log_path)

    if aborted and not result.get("rate_limit_stall"):
        logger.info(
            "K157 cost gate breach: cost_usd=%.4f max=%.4f",
            cost_usd,
            max_cost,
        )

    return {
        "skipped": False,
        "enrichment": metrics.enrichment,
        "metrics": metrics,
        "cost_gate_ok": gate_ok,
        "aborted": aborted,
    }
