---
title: "XSP Killer super-audit synthesis v4 (19e9200 + variant harvest)"
type: brief
tags: [super-audit, xsp-killer, variant-soak, ops, regime-gate, xsp_lane_a_v2]
created: 2026-06-29
updated: 2026-06-29
---

## Executive verdict (3/4 auditors; v4 pack `19e9200`)

| Environment | Consensus | Split |
|---|---|---|
| **Paper soak (now)** | **WARN (3/3)** | Code + timers OPERATIONAL; **0 trades / 0 enters** post-epoch across all tracks |
| **Variant harvest deployed?** | **YES (3/3)** | 4 systemd timers active; scoreboard `stale: false`; 15 sessions (GREEN-axis variants), 6 sessions (yellow bounce variants started later) |
| **Best variable combination today?** | **NO (3/3)** | All `avg_pnl_per_trade_usd: null`; identical skip profile — cannot rank DTE/strike/exit/regime axes |
| **Live RH flip** | **FAIL (3/3)** | No execution path; RH adapter + conductor + kill switch still stubs |

**Patch commit audited:** `19e9200` — premium_scale config, dual 1× logging, data_hazards, entry telemetry, shadow vol gate, promotion scoreboard, yellow bounce 0.50/0.75 axis. **106/106 tests pass.**

**Audit legs (2026-06-29T1255Z):**

| Slot | Model | Report |
|---|---|---|
| OpenRouter #1 | `z-ai/glm-5.2` | `reports/gap-audit/premium-xsp-killer-v4/glm-5.2-openrouter_20260629T1255Z.md` |
| OpenRouter #2 | `x-ai/grok-4.3` | `reports/gap-audit/premium-xsp-killer-v4/grok-4.3-openrouter_20260629T1255Z.md` |
| OpenRouter #3 | `google/gemini-2.5-pro-preview` | **FAILED** — empty response |
| OpenRouter #4 | `anthropic/claude-sonnet-4` | `reports/gap-audit/premium-xsp-killer-v4/claude-sonnet-4-openrouter_20260629T1255Z.md` |

**Pack:** `reports/gap-audit/pack-xsp-killer-v4/` · **Prompt:** `prompts/xsp_killer_super_audit.md` (v4)

---

## Deployment & harvest status (operator)

| Check | Status |
|---|---|
| `xsp-killer-lane-a-entry.timer` | active — next Mon–Fri ~19:45 UTC |
| `xsp-killer-lane-a-monitor.timer` | active |
| `xsp-killer-lane-a-intraday.timer` | active |
| `xsp-killer-lane-b-monitor.timer` | active |
| `last_entry_eval_at` | 2026-06-28T19:55:35Z |
| Scoreboard `stale` | false |
| Post-epoch since | 2026-06-23T22:20:36Z |
| Active shadow variants | **16** + baseline prod row |
| `regime_gate_comparison` | baseline GREEN vs 0.50 vs 0.75 — **tracking correctly** |

**Harvest is working** — every close cron evaluates all variants and appends to per-variant jsonl logs. The soak is collecting **skip telemetry**, not trade PnL, because macro regime has blocked entries.

---

## Why we cannot rank variable combinations yet

All auditors agree on root cause:

1. **`entered_sessions: 0`** and **`trades_closed: 0`** on every variant post-epoch
2. **`regime_gate_skip_sessions: 9`** on GREEN-gated variants (60% of 15 sessions)
3. **`bb_bounce_signal_sessions: 0`** on yellow bounce variants — BB bounce never fired in-window post-epoch, or regime was RED (not YELLOW)
4. **15/20 sessions** toward promotion gate — still 5 short on older variants; yellow bounce tracks at **6/20** (added after epoch)

**Regime gate axis (no differentiation yet):**

| Variant | Sessions | Regime gate | Enters | Bounce signals |
|---|---|---|---|---|
| `v2_baseline_prod` | 15 | GREEN | 0 | 0 |
| `v2_yellow_mid_bounce` | 6 | YELLOW bounce ≥0.50 | 0 | 0 |
| `v2_yellow_top_quartile_bounce` | 6 | YELLOW bounce ≥0.75 | 0 | 0 |

When YELLOW + BB bounce eventually align, **0.50 should enter more often than 0.75** — that is the experiment. No data yet.

**DTE / strike / exit axes:** All GREEN-gated variants share identical skip counts — **no axis has produced a trade to compare**.

---

## Jun 2026 upgrades — auditor validation (3/3)

| Upgrade | Status |
|---|---|
| Config `premium_scale` + env override | ✅ Shipped |
| Dual 1× notional logging | ✅ Shipped |
| K129 `data_hazards` on chain/regime | ✅ Shipped |
| Entry telemetry + telemetry brief | ✅ Shipped |
| Shadow `vol_monitor` (non-enforcing) | ✅ Shipped |
| Promotion fields + `promotion_summary` | ✅ Shipped |
| Yellow bounce 0.50 / 0.75 isolated books | ✅ Shipped |
| Health soak script | ✅ Shipped |

---

## OSINT wiki scan (Phase A)

Local `research_wiki/` has SPY entity, Greeks sources, playbook research, Kalshi BB baseline — **no dedicated `@wiki/concepts/xsp-*` pages** (librarian destroyed). Auditors unanimous: rebuild XSP liquidity/strike-notation reference before live flip.

**Cemini steal list (paper partial):** RH MCP Phase 0 ✅; conductor_shadow stub ✅; daily loss cap + consecutive-loss halt ✅; full RH execution still FAIL.

---

## Promotion recommendation

**WAIT (3/3)** — do not promote any variant or change baseline rules.

**Continue soak until:**
1. ≥20 post-epoch sessions per variant
2. ≥5 closed trades on at least 2 variants **or** clear divergence in `entered_sessions` / `bb_bounce_blocked_by_regime_sessions` on regime axis
3. GREEN or YELLOW+bounce market window produces actual entries

---

## Ranked backlog (post-v4 consensus)

| Priority | Item |
|---|---|
| **P0** | Keep soak running — tonight's Mon close is first post-`19e9200` eval with vol_shadow + premium_scale in logs |
| **P0** | Do not live flip — RH adapter + risk stack |
| ~~**P1**~~ | ~~After 5 more sessions, compare regime axis counters~~ | ✅ health_soak `regime_axis_summary` |
| ~~**P1**~~ | ~~Rebuild local `xsp-*` wiki concepts~~ | ✅ `a34c6fa` |
| ~~**P1**~~ | Lane B separate `XSP_LANE_B_RH_POLL` | ✅ rh_broker |
| **P2** | Consider shadow vol gate promotion only after trade sample exists |

---

## Operator next actions

1. **Tonight ~19:45 UTC** — entry cron fires; verify new fields in variant jsonl (`vol_shadow`, `premium_scale_used`)
2. **After 5 sessions** — re-run `python3 scripts/build_xsp_killer_super_audit_pack.py` + scoreboard compare
3. **Do not change production baseline** — unanimous WAIT
4. **Watch for GREEN day** — first trade sample unlocks DTE/strike/exit ranking

**Prior synthesis:** `briefs/2026-06-21_xsp-killer-super-audit-synthesis-v3-postpatch.md`
