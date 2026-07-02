---
title: "XSP Killer super-audit synthesis v6 (post-fix validation)"
type: brief
tags: [super-audit, xsp-killer, variant-soak, cursor-audit, post-patch]
created: 2026-07-02
updated: 2026-07-02
---

## Executive verdict (2/2 auditors; v6 pack `dd8c1f3`)

| Environment | Consensus | Split |
|---|---|---|
| **Paper soak (now)** | **OPERATIONAL / WARN (2/2)** | v5 P0 code fixes landed; session dedupe working (6 sessions); brief/epoch desync persists |
| **Variant harvest** | **YES (2/2)** | 15/16 books accumulating; `v2_28dte_atm_stack3` silently dead (GLM only) |
| **Best variable combination today?** | **NO (2/2)** | `ranking_reliable: false`; n=1 closed trade; 21-DTE hint only |
| **Live RH flip** | **FAIL (2/2)** | `place_option_order` exists but never called; no token/account |
| **Promotion** | **WAIT (2/2)** | 1/10 entered_sessions; 14 sessions to gate |

**Patch commits audited:** `2e2b609` (v5 backlog) + `dd8c1f3` (conductor threshold). **151/151 tests pass.**

**Audit legs (2026-07-02, cursor-audit — no OpenRouter):**

| Slot | Model | Report |
|---|---|---|
| Cursor #1 | `glm-5.2-high` | `reports/gap-audit/premium-xsp-killer-v6-cursor/glm-5.2-high_AUDIT.md` |
| Cursor #2 | `kimi-k2.7-code` | `reports/gap-audit/premium-xsp-killer-v6-cursor/kimi-k2.7-code_AUDIT.md` |

**Pack:** `reports/gap-audit/pack-xsp-killer-v6/` · **Prior synthesis:** `briefs/2026-07-01_xsp-killer-super-audit-synthesis-v5.md`

---

## What changed since v5 audit (unanimous)

| v5 finding | v6 status | Auditors |
|---|---|---|
| Scale-aware daily loss cap | **Fixed in code; not yet observed live** | 2/2 |
| ET session dedupe | **Fixed and working** (24 → 6 sessions) | 2/2 |
| conductor_shadow unit bug | **Fixed** (`-0.015` → `-1.5`) | 2/2 |
| Brief sync / telemetry | **NOT fixed** — epoch divergence + zeroed telemetry brief | 2/2 |
| pytest brief pollution | **Fixed** (conftest isolation) | 2/2 |
| Scoreboard telemetry | **Fixed** (open MTM, clusters, exit_shadow, ranking_reliable) | 2/2 |
| Yellow bounce close_window_only | **Fixed in yaml**; axis still 0 enters (no BB bounce) | 2/2 |

---

## Cross-auditor consensus — remaining issues

### 1. Brief / epoch incoherence (2/2 P1)

`entry_telemetry_latest.json` is zeroed with `pnl_epoch_at: 2026-07-01T23:11:03` while scoreboard retains `pnl_epoch_at: 2026-06-23T22:20:36`. Health soak reports 5 strict anomalies (sessions, evals, skip counts, open MTM). Self-check detects mismatches but does not repair.

**Fix:** resync epoch across baseline + variants state, regen scoreboard + telemetry; extend health check to assert epoch parity.

### 2. Scale-aware cap unobserved (2/2 P0 watch)

Code allows re-entry at −$1,582 (cap now $5,000 at 10×). Last eval still shows old message `(-1582.45 <= -500)` from pre-deploy logs. Confirm on next GREEN day or synthetic test.

### 3. Variant ranking still invalid (2/2 P0)

One shared Jun-30 entry; 3 books closed, 10+ holding. Only hint: `v2_21dte_atm` −$1,051 vs baseline −$1,582 (+$531, n=1).

### 4. stack3 variant dead (GLM P1; Kimi silent)

`v2_28dte_atm_stack3` in yaml but absent from `variants_state.json` — never accumulated sessions.

### 5. Live flip blocked (2/2 P0)

No execution path wired; Cemini `robinhood_adapter.py` not ported; premium scale unvalidated at 1× XSP.

---

## Promotion recommendation

**WAIT (2/2)** — do not promote any variant or change baseline rules.

Continue soak until:
1. ≥10 **entered_sessions** (currently 1/10)
2. Brief/epoch sync repaired and stable
3. Scale-aware loss cap observed in live telemetry
4. ≥5 closed trades on ≥2 variants with `ranking_reliable: true`

---

## Ranked backlog (v6 consensus)

| Priority | Item | Auditors |
|---|---|---|
| **P0** | Do not live flip; do not promote | 2/2 |
| **P0** | Confirm scale-aware loss cap on next GREEN eval | 2/2 |
| **P1** | Fix pnl_epoch sync (baseline ↔ variants ↔ scoreboard ↔ telemetry) | 2/2 |
| **P1** | Register `v2_28dte_atm_stack3` in variants state | GLM |
| **P1** | Port Cemini `robinhood_adapter.py` before live flip | Kimi |
| **P1** | exit_shadow forward MTM for would_hold counterfactuals | GLM |
| **P1** | Yellow bounce axis structurally starved — relax or retire | GLM |
| **P2** | NYSE holiday filter for session dedupe | GLM |
| **P2** | Validate premium_scale against real RH chain | Kimi |

---

## Operator next actions

1. **Resync epoch** — run coordinated `clear_pnl_epoch` + scoreboard regen so briefs match scoreboard
2. **Watch next GREEN close** — confirm loss cap no longer blocks at −$1,582
3. **Read scoreboard**, not telemetry brief alone, until epoch sync fixed
4. **Do not promote** — WAIT unanimous

**Prior synthesis:** `briefs/2026-07-01_xsp-killer-super-audit-synthesis-v5.md`

---

## Implementation addendum (2026-07-02)

All v6 backlog items implemented. **162/162 tests pass.**

| Priority | Item | Status |
|---|---|---|
| **P1** | Epoch resync (`lane_a_variants.py sync`) + health epoch parity | ✅ |
| **P1** | Auto-register yaml variants (`ensure_variant_slices`) | ✅ stack3 live |
| **P1** | exit_shadow forward MTM (`shadow_virtual_holds`) | ✅ |
| **P1** | Yellow mid-bounce close window without BB | ✅ yaml |
| **P0** | Scale-aware cap regression test (−1582 @ 10×) | ✅ |
| **P2** | Paper brief logic_version from rules | ✅ |
| **P2** | NYSE holiday session dedupe | ✅ |

**Post-deploy:** `python3 scripts/lane_a_variants.py sync` — telemetry/scoreboard epoch aligned at 6 sessions.
