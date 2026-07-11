## Target

CeminiSuite — XSP killer bot (Robinhood long-call lanes A/B).

## Summary

K159 **Integrate (operator spike)** — [DannyMac180/fable-advisor](https://github.com/DannyMac180/fable-advisor) (**MIT**): Claude Fable as **architect/reviewer only**; route implementation tokens to **Grok 4.5** / **GPT-5.6 Sol**; require cross-vendor review before any prod-touching diff merge. Phase 0 is **opt-in, log-only, NO-GO default**; does not change GREEN/YELLOW/RED gate logic or Lane A executor paths.

## Operator spike (one XSP brief iteration)

1. **Install** fable-advisor Claude Code plugin; run one brief iteration with Fable architect + Grok/GPT implementation lanes when `XSP_K159_FABLE_ADVISOR=1`.
2. **Measure** token spend vs baseline Fable-only session on the same task; adopt if **≥30% reduction** without quality regression on checklist edits.
3. **Cross-vendor review** — required before merging any diff that touches prod harness paths.
4. **Prereq** — Claude Code ≥2.1.170; configure Grok CLI headless via `XSP_K159_GROK_LANE=1` or document fallback model lane.
5. **NO-GO default** — keep current harness if Grok lane unavailable or Anthropic subagent API breaks.

## Config & code

- `config/k159_fable_advisor_spike.yaml` — repo, roles, token threshold, cross-vendor review, GO/NO-GO
- `xsp_killer/fable_advisor_spike.py` — `load_k159_config`, `fable_advisor_enabled`, `run_brief_iteration_spike`, metrics helpers
- `xsp_killer/macro_weather_notes.py` — optional `maybe_log_fable_spike` (log-only hook)
- `tests/test_k159_fable_advisor_spike.py` — unit tests (no plugin install)
- `scripts/adopt_k159_phase0.sh` — Phase 0 adoption manifest → `briefs/k159-ops-phase0-adopt-latest.json`

## Env opt-in

| Variable | Default | Purpose |
|----------|---------|---------|
| `XSP_K159_FABLE_ADVISOR` | off | Enable spike logging |
| `XSP_K159_GROK_LANE` | off | Grok implementation lane available |

## GO/NO-GO criteria (from config)

- `token_reduction_adopt_threshold_pct` — ≥30% reduction on active samples
- `cross_vendor_review_required` — prod-touching diffs must record `cross_vendor_review_done`
- Grok lane must be available (`XSP_K159_GROK_LANE=1`)
- `min_samples_for_verdict` — insufficient samples → keep default **NO_GO**
- `default_verdict: NO_GO` — keep existing orchestration until operator promotes

## Sources

- `/opt/cemini/briefs/xsp-2026-07-11_k159-fable-advisor-orchestration-steal.md`
- `@entities/tools/fable-advisor.md`
- `@sources/eval-multi-wiki-repo-evaluation-strategy-2026-07-11.md`
