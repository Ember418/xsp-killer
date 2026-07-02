---
title: "XSP Killer super-audit synthesis v5 (first trade + loss cap)"
type: brief
tags: [super-audit, xsp-killer, variant-soak, first-trade, risk-gate, cursor-audit]
created: 2026-07-01
updated: 2026-07-01
---

## Executive verdict (2/2 auditors; v5 pack `3ccf58c`)

| Environment | Consensus | Split |
|---|---|---|
| **Paper soak (now)** | **OPERATIONAL / WARN (2/2)** | Infra + timers healthy; **first closed trade** (−$1,582 time_stop); loss cap froze re-entry; brief-sync bugs |
| **Variant harvest** | **YES (2/2)** | 16 shadows + baseline evaluating; DTE axis first hint (21-DTE −$1,051 vs 17-DTE −$1,582) but **n=1** |
| **Best variable combination today?** | **NO (2/2)** | One entry event, one adverse move; yellow axis still 0 enters |
| **Live RH flip** | **FAIL (2/2)** | No execution path; premium scale unvalidated at 1× XSP |

**Patch commit audited:** `3ccf58c` — promotion entered_sessions gate, regime_skip_breakdown, dual 1× MTM brief, K79 loss cap + consecutive-loss halt. **130/130 tests pass.**

**Audit legs (2026-07-01T23:16Z, cursor-audit — no OpenRouter):**

| Slot | Model | Report |
|---|---|---|
| Cursor #1 | `claude-fable-5-thinking-max` | `reports/gap-audit/premium-xsp-killer-v5-cursor/claude-fable-5-thinking-max_AUDIT.md` |
| Cursor #2 | `claude-opus-4-8-thinking-high` | `reports/gap-audit/premium-xsp-killer-v5-cursor/claude-opus-4-8-thinking-high_AUDIT.md` |

**Pack:** `reports/gap-audit/pack-xsp-killer-v5/` · **Prompt:** `prompts/xsp_killer_super_audit.md` (v4 template, v5 delta in pack)

---

## What changed since v4 (unanimous)

| Event | Detail |
|---|---|
| **First enter** | 2026-06-30 close — XSP 7500C Jul-17, GREEN, ~$79 @ 10× scale |
| **First exit** | 2026-07-01 10:00 ET **time_stop** — **−$1,582.45** (−19.2%) |
| **Re-entry blocked** | Jul 1 close: `daily paper loss cap hit (-1582.45 <= -500)` |
| **Sessions** | 24 evals (~6 trading days; see inflation issue below) |
| **Promotion** | `insufficient_enters` — 1/10 entered_sessions |

---

## Cross-auditor consensus — NEW P0 findings

### 1. Daily loss cap vs 10× premium scale (2/2 P0)

`risk_gates.py` defaults **$500** cap; PnL logged at **premium_scale 10**. One −20% stop ≈ **−$1,582** → cap trips immediately and blocks all GREEN-axis books next session. Paper risk behavior ≠ live 1× behavior.

**Fix:** scale-aware cap (`cap × premium_scale`) or evaluate on dual-logged 1× PnL.

### 2. Session counting inflated (Fable P0; Opus implicit)

`sessions_evaluated: 24` counts **cron fires** (3/day + weekend persistent catch-up), not unique ET trading sessions (~6). ≥20-session gate met too early.

**Fix:** dedupe by ET trading date; exclude non-RTH evals from promotion counters.

### 3. Variant ranking invalid at n=1 (2/2)

All GREEN-axis books share the **same Jun 30 entry**. Four shorter-DTE books closed; ten ≥28-DTE books still **holding** (suppress_morning_cut_dte_gte: 30). Per-variant loss cap creates divergent skip profiles (`risk_gate` vs `max_positions`) — not apples-to-apples unless annotated.

**Only hint:** `v2_21dte_atm` −$1,051 vs baseline −$1,582 (+$531 on same move) — directional, not significant.

### 4. Operator brief integrity (Opus P1; Fable P2)

`xsp-lane-a-paper-pnl-latest.json` may show stale phantom position (−$75 on 6000 strike) while real loss is in scoreboard. `entry_telemetry_latest.json` zeroed while scoreboard populated.

**Fix:** single source of truth from scoreboard/state; consistency self-check.

---

## Regime axis (unchanged from v4)

| Variant | Sessions | Enters | Bounce signals |
|---|---|---|---|
| `v2_baseline_prod` | 24 | 1 | 0 |
| `v2_yellow_mid_bounce` | 15 | 0 | 0 |
| `v2_yellow_top_quartile_bounce` | 15 | 0 | 0 |

Yellow books require BB bounce even on GREEN days → structurally starved vs baseline (Fable P1).

---

## Promotion recommendation

**WAIT (2/2)** — do not promote any variant or change baseline rules.

Continue soak until:
1. ≥10 **entered_sessions** (currently 1/10)
2. ≥5 closed trades on ≥2 variants **after** P0 cap/scale fix
3. Session dedupe fix applied before trusting promotion gate

---

## Ranked backlog (v5 consensus)

| Priority | Item | Auditors |
|---|---|---|
| **P0** | Scale-align daily loss cap with premium_scale / 1× PnL | 2/2 |
| **P0** | Dedupe sessions_evaluated by ET trading date | Fable; implied Opus |
| **P0** | Do not live flip; keep soak running | 2/2 |
| **P0** | Do not rank variants on n=1 scoreboard | 2/2 |
| **P1** | Fix baseline PnL + telemetry brief sync (phantom/zeroed rows) | Opus; Fable |
| **P1** | Yellow bounce: allow baseline close-window entry on GREEN days | Fable |
| **P1** | Per-variant open MTM on scoreboard; contract cluster tags | Fable |
| **P1** | Summarize exit_shadow morning-cut counterfactuals on scoreboard | Opus |
| **P2** | Reap stale paper_positions; document consecutive-loss reset | Both |
| **P2** | Optional shadow force_entry_on_green for faster sampling | Opus |

---

## Operator next actions

1. **Fix P0 loss-cap scale** before next GREEN day — otherwise every losing exit freezes the book
2. **Read scoreboard**, not baseline PnL brief alone, until brief-sync fixed
3. **Watch ≥28-DTE open books** — first multi-day exits when they close
4. **Do not promote** — WAIT unanimous

**Prior synthesis:** `briefs/2026-06-29_xsp-killer-super-audit-synthesis-v4.md`

---

## Implementation addendum (2026-07-01)

All v5 backlog items implemented per Fable 5 plan (Batch A + B). **149/149 tests pass.**

| Priority | Item | Status |
|---|---|---|
| **P0** | Scale-align daily loss cap (`cap × premium_scale`) | ✅ `risk_gates.py` |
| **P0** | Dedupe `sessions_evaluated` by ET trading date | ✅ `lane_a_entry.py`, `lane_a_variants.py` |
| **P1** | Brief sync self-check (PnL + telemetry) | ✅ `health_soak.py` |
| **P1** | Yellow bounce `close_window_only` on GREEN days | ✅ `lane_a_variants.yaml` |
| **P1** | Open MTM, contract clusters, `ranking_reliable` | ✅ scoreboard |
| **P1** | Exit-shadow summary on scoreboard | ✅ scoreboard |
| **P2** | Reap expired paper positions | ✅ `lane_a_monitor.py` |
| **P2** | Consecutive-loss reset CLI | ✅ `scripts/lane_a_risk_reset.py` |
| **P2** | Exit precedence wiki | ✅ `research_wiki/concepts/xsp-lane-a-exit-precedence.md` |
| **P2** | pytest brief isolation (`DEFAULT_PAPER_BRIEF`, telemetry) | ✅ `tests/conftest.py` |
| **P2** | `v2_28dte_atm_stack3` shadow variant | ✅ yaml |

**Post-deploy ops:** `sudo bash scripts/install_systemd.sh && sudo systemctl daemon-reload` (Mon..Fri timers); regen briefs via `python3 scripts/lane_a_paper_pnl.py`.
