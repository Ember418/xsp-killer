---
title: XSP Lane A exit precedence
type: concept
tags: [concept, xsp, lane-a, exits, precedence]
related:
  - concepts/xsp-lane-a-overnight-swing.md
  - concepts/xsp-lane-a-regime-vol-gates.md
  - docs/lane-a-strategy-diagnosis.md
maturity: validated
created: 2026-07-01
updated: 2026-07-01
---

## Relations

- @concepts/xsp-lane-a-overnight-swing.md — entry/hold/exit lifecycle.
- @concepts/xsp-lane-a-regime-vol-gates.md — entry-side filters that reduce bad overnight holds.
- Code: `lane_a_monitor.py` for alert evaluation, `lane_a_entry.py` for paper position metadata.

## Narrative

Lane A can surface multiple exit conditions on the same morning. The production paper monitor does **not** try to scale out or blend reasons; it records the alerts generated for the current evaluation and then closes the paper position on the **first matched alert for that position** in monitor order.

That means effective precedence is driven by `evaluate_exit_alerts()` ordering:

1. `stop_loss`
2. `take_profit` / `upper_bb_rejection`
3. `time_stop`

If more than one condition is true at the same evaluation, the first alert written for that position becomes the closing `exit_reason`.

### Why precedence matters

- Exit attribution drives paper PnL review and risk streak accounting.
- Shadow analysis is only useful if the recorded reason is deterministic.
- Morning cut vs profit-take interpretation changes how later audits judge whether the system exited too early or too late.

### Paper-state fields

Paper positions now stamp:

- `spx_at_entry` on entry
- `spx_at_exit` on paper close
- `spy_drift_pct` as the percent move from `spx_at_entry` to `spx_at_exit`

These fields make it easier to separate option-premium path from underlying drift when reviewing paper exits.

## Ops

- If the consecutive-loss halt should ignore older exits after a manual review, set `risk_streak_reset_at` with `python3 scripts/lane_a_risk_reset.py`.
- Expired paper positions are reaped automatically by the paper monitor before normal alert evaluation.

## Snippets

- Paper close path: `run_monitor()` → `close_paper_positions_on_exit()`
- Audit question to ask: "Was the recorded exit reason the highest-priority rule that was active at evaluation time?"
