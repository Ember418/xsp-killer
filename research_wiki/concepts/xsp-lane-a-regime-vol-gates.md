---
title: XSP Lane A regime and vol gates
type: concept
tags: [concept, xsp, lane-a, regime, volatility, shadow]
related:
  - concepts/xsp-lane-a-overnight-swing.md
  - briefs/2026-06-15_k117-regime-vol-gating-equity-signals-cemini-prod.md
maturity: validated
created: 2026-06-29
updated: 2026-06-29
---

## Relations

- @concepts/xsp-lane-a-overnight-swing.md — entry/exit playbook.
- Cemini K117 brief — regime/vol gating patterns (donor for shadow vol design).
- Code: `lane_a_entry.py` (regime), `vol_monitor.py` (shadow only).

## Narrative

### Macro regime gate (enforcing in prod)

Production baseline requires **GREEN** macro regime before new overnight risk. Variants may override:

| Variant | Gate | Yellow frac min |
|---------|------|-----------------|
| `v2_baseline_prod` | `GREEN` | — |
| `v2_yellow_mid_bounce` | `GREEN_OR_YELLOW_BOUNCE` | 0.50 |
| `v2_yellow_top_quartile_bounce` | `GREEN_OR_YELLOW_BOUNCE` | 0.75 |

When YELLOW, entry allowed only if **regime_frac ≥ yellow_frac_min** *and* BB bounce signal fires.

### Scoreboard metrics (variant soak)

Per variant row and `regime_gate_comparison`:

- `bb_bounce_signal_sessions` — BB bounce true at eval
- `bb_bounce_blocked_by_regime_sessions` — bounce present but regime skip
- `regime_gate_skip_sessions` — any regime block
- `vol_shadow_would_block_sessions` — shadow vol would have blocked (not enforcing)
- `vol_shadow_latest_spy_rv` / `vol_shadow_latest_would_block` — last session snapshot
- `vol_shadow_avg_spy_rv` — mean SPY 21d realized vol when logged

### Shadow vol gate (log-only)

`evaluate_shadow_vol_gate()` computes **SPY 21d annualized realized vol**. If RV ≥ **28%** threshold, sets `shadow_would_block=true`. **Never blocks paper entry** — for counterfactual analysis before enabling live vol gate.

Logged on `EntryDecision.vol_shadow` → jsonl + in-memory `entry_log` for scoreboard aggregation.

### Promotion policy

`promotion_ready: false` until ≥20 sessions **and** trades closed per variant. Regime/vol shadow stats inform **whether** to tighten prod gate — not auto-promotion triggers.

## Ops

- Threshold tweak: constants in `vol_monitor.py` (shadow) vs `lane_a_rules.yaml` entry (regime source).
- Audit pack includes wiki + scoreboard for blind-spot review before live flip.

## Snippets

- Enforcing vol gate for live: **not implemented** — requires conductor/kill-switch + RH path first.
