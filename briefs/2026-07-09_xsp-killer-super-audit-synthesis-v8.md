---
title: XSP Killer — SUPER AUDIT v8 Synthesis (operator 45–60 DTE stagger)
type: brief
tags: [super-audit, xsp-killer, cursor-audit, operator-profile, dip-swing]
created: 2026-07-09
updated: 2026-07-09
---

# XSP Killer — SUPER AUDIT v8 Synthesis (operator 45–60 DTE stagger)

**Date:** 2026-07-09 · **HEAD audited:** `e6bb155` · **Pack:** `reports/gap-audit/pack-xsp-killer-v8/`
**Scope:** commit `e6bb155` — operator 45/50/55/60 DTE OTM stagger grid, 2-lot sizing, live/RH caps raised; re-validate v7 P0 fixes in `ac6540d`.

**Panel (3 auditors, cursor-audit — no OpenRouter):**
- **GPT SOL** — `gpt-5.6-sol-medium`
- **Grok 4.5** — `grok-4.5-fast-xhigh`
- **Opus** — `claude-opus-4-8-thinking-high`

Reports: `reports/gap-audit/premium-xsp-killer-v8-cursor/*_AUDIT.md`

> All 3 auditors complete. **GPT SOL** found the **#1 paper-side blocker the others partially missed**: with production `XSP_LANE_A_RH_MCP=true`, variant paper books are **never evaluated for exits** — explaining `dip_swing_cluster.total_trades_closed: 0` despite open paper positions. This subsumes "soak is just immature."

---

## Executive verdict (panel consensus)

| # | Question | Verdict | Basis |
|---|----------|---------|-------|
| 1 | Paper soak | **FAIL until patched** | v7 measurement fixes **stuck** (+90%/−80% guards; SL on stale mark). **New P0:** MCP-on monitor path skips paper exit lifecycle (`lane_a_monitor.py:1154-1226`; systemd `XSP_LANE_A_RH_MCP=true`). |
| 2 | Live RH flip (2-lot operator profile) | **FAIL (unanimous)** | v7 entry allowlist / selector / VIX / reviewer **stuck**. 2×~$12 ≈ **$2,370 debit** fails $1k BP; `max_cost_frac:0.5` needs **~$4.7k BP**. Caps internally inconsistent. **Do not** set `LIVE_ENTRIES=true`. |
| 3 | Operator DTE stagger harvest | **WARN / WAIT** | Four variants wired + tested (`test_merged_rules_operator_target_dte_stagger`). Cluster has **12** `v2_dip_swing_*` members (incl. spread). **0 closed trades**; DTE-collision risk; `max_open_positions:1` + 6–8 week holds → ~6 trades/yr/bucket → ≥20-trade gate unreachable in reasonable horizon. |
| 4 | Is 45–60 DTE OTM 2-lot +EV / promotable? | **NOT YET PROVEN — WAIT** | Theta ~3–4× softer than 14-DTE ATM; profile matches operator 760C@754 screenshot. Breakeven still **~55.6% pre-cost / ~60% post-cost**. Prior `v2_45dte_otm` pruned net-negative under old path; DIP_BOUNCE overlay unmeasured. |

---

## P0 — blockers (ship fixes this session)

### 0. Paper exits dead when RH MCP read is on (GPT SOL — new; **#1 paper blocker**)

Production systemd sets `XSP_LANE_A_RH_MCP=true`. `run_monitor()` fetches RH positions when MCP on; paper positions load only when `rh_poll_skipped` (MCP **off**). Variant soak uses isolated per-variant `paper_positions` slices — **never marked or closed** under prod posture. `close_paper_positions_on_exit` gated on `paper_positions_active = rh_poll_skipped`.

**Fix:** Always refresh/evaluate/close paper positions when `state.paper_positions` non-empty, regardless of RH read path. RH positions and paper books are separate collections.

### 1. Live cap inconsistency for 2-lot operator profile (unanimous)

`max_loss_usd:1200` bounds stop-loss estimate (`cost × SL%`) but **not full debit** (~$2,370). `max_cost_frac:0.5` requires **~$4.7k BP** — contradicts "$1k account" docs. `est_max_loss` understates tail (gap-through = full premium).

**Fix:** Add `max_debit_usd` gate on full premium at risk; document `documented_min_buying_power_usd: 5000` for 2-lot live; align `reviewer_max_contracts` with `max_contracts_per_order: 2`.

### 2. Live allowlist fuzzy `endswith` (Opus)

`_live_variant_allowed` matches `current.endswith(allowed)` — a short env value like `dte_otm` could fire **all** OTM variants.

**Fix:** Exact match only on `variant_id` / `logic_version`.

### 3. Live exit fan-out (GPT SOL — live-side, keep gated)

No exit-side `XSP_LANE_A_LIVE_VARIANT_ID`. If live exits enabled, every variant monitor can review the same RH position under different rules.

**Fix (P1 defer if live exits stay off):** Skip RH exit MCP reviews on variant monitor passes; baseline/promoted variant only. Document until live position ledger ships.

---

## P1 — before trustworthy DTE-bucket rank

| Item | Auditors | Action |
|------|----------|--------|
| DTE collision (55/60 → same expiry) | Grok, Opus | Log `dte_actual` + `expiration` per entry; parity test across 45/50/55/60 calendar |
| Sample starvation (`max_open_positions:1`) | Opus | Raise operator buckets to `max_open_positions: 2` for paper soak throughput |
| MCP canary spam | Opus | Skip canary exit reviews on variant monitors when no RH positions |
| Wiki stale | All | Document 45–60 OTM 2-lot profile + ~$5k BP floor |
| Prior 45 DTE prune | Grok | Treat `v2_dip_swing_45dte_otm` as hypothesis retest, not refute |

---

## v7 regression matrix @ `e6bb155`

| v7 P0 | Status |
|-------|--------|
| Mark guards inside TP/SL | ✅ **CLOSED** (`ac6540d`) |
| Live entry fires all variants | ✅ **CLOSED** (allowlist fail-closed) |
| Live selector ≠ paper | ✅ **CLOSED** (`dte_target` / `otm_one`) |
| premium_scale 10× | ✅ **CLOSED live**; WARN paper raw $ (use `*_1x_approx`) |
| $1k sizing = BP only | ⚠️ **REOPENED** — gates work but 2-lot needs ~$5k |
| DIP_BOUNCE falling knife | ✅ **CLOSED** (VIX-spike veto) |
| Never-exit stale mark | ✅ **CLOSED** in code; **broken in prod** by P0 #0 |

---

## Phase D — operator profile math (consensus)

| DTE | Theta/day (≈) | Move for +40% OTM | Notes |
|-----|---------------|-------------------|-------|
| 45  | ~1.2%/day | ~+1.3% index | Softest theta in grid |
| 50  | ~1.1%/day | ~+1.35% | |
| 55  | ~1.0%/day | ~+1.4% | Matches operator screenshot |
| 60  | ~0.9%/day | ~+1.45% | Weakest gamma |

- Breakeven win rate unchanged: **55.6% pre-cost / ~60% post-cost** for TP+40/SL−50.
- **2-lot** doubles absolute PnL/tail, not breakeven %.
- Long-DTE OTM is **directionally better** than 14-DTE ATM on theta; **vega crush** on recovery is the unmodeled headwind.
- **Promote:** none until paper exits run + `edge_confirmed` on one bucket.

---

## Implementation plan (this session)

| Batch | Owner | Deliverable |
|-------|-------|-------------|
| **A** | subagent | Paper monitor fix + test (`RH_MCP=true` still closes paper) |
| **B** | subagent | Live safety: exact allowlist, `max_debit_usd`, cap docs, reviewer align |
| **C** | subagent | Operator soak: `max_open_positions:2`, DTE resolution logging + test |

**Post-fix gate:** `pytest` green → scoreboard regen → keep `LIVE_ENTRIES=false` until one operator bucket hits `edge_confirmed`.

---

## Audit legs

- `reports/gap-audit/premium-xsp-killer-v8-cursor/gpt-5.6-sol-medium_AUDIT.md`
- `reports/gap-audit/premium-xsp-killer-v8-cursor/grok-4.5-fast-xhigh_AUDIT.md`
- `reports/gap-audit/premium-xsp-killer-v8-cursor/claude-opus-4-8-thinking-high_AUDIT.md`

**Prior synthesis:** `briefs/2026-07-07_xsp-killer-super-audit-synthesis-v7.md`
