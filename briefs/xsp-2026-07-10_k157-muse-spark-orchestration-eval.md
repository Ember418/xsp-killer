## Target

CeminiSuite — XSP killer bot (Robinhood long-call lanes A/B).

## Summary

K157 **Integrate (operator spike)** — Meta **Muse Spark 1.1** via [vals.ai](https://www.vals.ai/models/meta_muse-spark-1.1) (commercial ToS). Eval claims superior multi-agent orchestration + context compaction for long research loops — **spike before any prod harness swap**. Phase 0 is **opt-in, log-only, NO-GO default**; does not change GREEN/YELLOW/RED gate logic or Lane A executor paths.

## Operator spike (30 days)

1. **Route one non-critical subagent** — pre-Lane-A macro-research checklist enrichment (K155 extras path) through Muse Spark when `XSP_K157_MUSE_SPARK=1`.
2. **Cost gate** — cap token spend per research loop; abort and log when `$/loop` exceeds YAML baseline (`cost_gate.baseline_usd_per_loop`) or `max_cost_usd_per_loop`.
3. **Latency logging** — append NDJSON samples to `logs/k157_muse_spark_spike.jsonl`; track p50/p95 vs current orchestration.
4. **GO/NO-GO** — require stable subagent delegation without rate-limit stalls during market hours; default verdict **NO_GO** until thresholds pass with sufficient samples.
5. **Out of scope** — replacing CeminiSuite Lane A executor or live signal generation without a separate brief.

## Config & code

- `config/k157_muse_spark_spike.yaml` — model, vals.ai base URL, 30-day window, cost cap, GO/NO-GO thresholds
- `xsp_killer/muse_spark_spike.py` — `load_k157_config`, `muse_spark_enabled`, `MuseSparkClient`, `run_macro_research_enrichment`, metrics helpers
- `xsp_killer/macro_weather_notes.py` — optional `maybe_enrich_with_muse_spark` (log-only hook)
- `tests/test_k157_muse_spark_spike.py` — unit tests (no live vals.ai calls)
- `scripts/adopt_k157_phase0.sh` — Phase 0 adoption manifest → `briefs/k157-ops-phase0-adopt-latest.json`

## Env opt-in

| Variable | Default | Purpose |
|----------|---------|---------|
| `XSP_K157_MUSE_SPARK` | off | Enable spike enrichment |
| `VALS_API_KEY` / `XSP_K157_VALS_API_KEY` | — | vals.ai auth (required when enabled) |
| `XSP_K157_VALS_BASE_URL` | yaml | Optional API base override |

## GO/NO-GO criteria (from config)

- `latency_p50_ms_max` / `latency_p95_ms_max` — latency ceilings on active samples
- `rate_limit_stalls_max` — zero tolerance during market-hours eval window
- `min_samples_for_verdict` — insufficient samples → keep default **NO_GO**
- `default_verdict: NO_GO` — keep existing orchestration until operator promotes

## Sources

- `/opt/cemini/briefs/xsp-2026-07-10_k157-muse-spark-orchestration-eval.md`
- [Meta Muse Spark 1.1 eval report — ai.meta.com (retrieved 2026-07-10)]
