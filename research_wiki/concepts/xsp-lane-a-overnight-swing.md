---
title: XSP Lane A overnight swing (mentor playbook)
type: concept
tags: [concept, xsp, lane-a, swing, bollinger, vwap]
related:
  - concepts/xsp-lane-a-regime-vol-gates.md
  - concepts/xsp-index-options.md
  - docs/lane-a-strategy-diagnosis.md
maturity: validated
created: 2026-06-29
updated: 2026-06-29
---

## Relations

- @concepts/xsp-lane-a-regime-vol-gates.md — GREEN-only prod vs yellow bounce variants + shadow vol.
- Cemini archive briefs: `briefs/archive/pivot-2026-06/xsp-cemini-superseded/2026-06-14_xsp-lane-a-overnight-swing-monitor-cemini-prod.md`
- Standalone bot: `/opt/xsp-killer` (systemd timers, paper-only).

## Narrative

**Lane A** implements the mentor's **close-to-open long call** swing on XSP:

1. **Entry window** — last ~15 minutes before US cash close (eval ~19:45 UTC).
2. **Signal** — Bollinger lower-band bounce (+ optional VWAP reclaim); regime must allow new risk.
3. **Hold** — overnight; exit next morning via take-profit, stop-loss, or **time stop** (sell by deadline ET).
4. **Paper economics** — commission + slippage from `lane_a_rules.yaml`.

### Production baseline (`v2_baseline_prod`)

- Regime gate: **GREEN only**
- DTE/strike/exit from `config/lane_a_rules.yaml`
- State: `briefs/xsp-lane-a-entry-latest.json`, `logs/xsp_lane_a_paper.jsonl`

### Variant soak (shadow)

Parallel variants in `lane_a_variants.yaml` — DTE targets (28/45/60), OTM strike, prior-day SPY green filter, exit tweaks. **Do not promote** until ≥20 post-epoch sessions and non-zero trade sample (`promotion_ready` on scoreboard).

### Timers (VPS)

- `xsp-killer-lane-a-entry.timer` — close eval
- `xsp-killer-lane-a-monitor.timer` — morning exits
- `xsp-killer-lane-a-intraday.timer` — optional intraday checks

### Known fixed bugs (2026-06)

- Same-day `time_stop` — now requires entry on **prior** ET date.
- Stale TA outside RTH — blocked by window checks (expected).

## Ops

```bash
python3 scripts/lane_a_variants.py entry|monitor|scoreboard
python3 scripts/health_soak_check.sh
```

Scoreboard: `regime_gate_comparison`, `bb_bounce_*`, `vol_shadow_*` session stats.

## Snippets

- Logic version prod: `xsp_lane_a_v1` / variants `xsp_lane_a_v2_*`
- Live RH execution: **not wired** — soak paper only.
