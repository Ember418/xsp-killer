---
title: "XSP Killer super-audit synthesis v3 post-patch (105c4ed)"
type: brief
tags: [super-audit, xsp-killer, variant-soak, ops, xsp_lane_a_v2]
created: 2026-06-21
updated: 2026-06-21
---

## Executive verdict (8/8 auditors; post-`105c4ed` re-run)

| Environment | Consensus | Split |
|---|---|---|
| **Paper soak (now)** | **WARN / OPERATIONAL** | 5× **WARN** (GLM, Grok, Google, GPT cursor, Kimi stale read), 2× **OPERATIONAL** (Sonnet, Gemini cursor). **All agree:** continue paper; code fixes landed; **scoreboard still pre-patch / thin sample** — rerun variants before trusting strike-axis or long-DTE conclusions. |
| **Live RH flip** | **FAIL (8/8)** | Unanimous — no execution path, kill switch / conductor are stubs, XSP wiki gaps, yfinance-only chains. |
| **Variant promotion** | **WAIT (8/8)** | 2–3 trades/variant vs ≥20 gate; 0% win rate; do not change production baseline. |

**Patch commit audited:** `105c4ed` — per-strike marks, strike-aware fallback, `dte_actual`, TA freshness + upper-BB, variant isolation, hybrid slippage, chain cache, risk/conductor stubs. **50/50 tests pass.**

**Skipped / failed legs:**
- `openrouter/fusion` — JSON parse error (same as v3 first run)

**Audit legs completed (2026-06-21T1536Z re-run):**

| Slot | Model | Report |
|---|---|---|
| OpenRouter #1 | `z-ai/glm-5.2` | `reports/gap-audit/premium-xsp-killer-v3/glm-5.2-openrouter_20260621T1536Z.md` |
| OpenRouter #2 | `x-ai/grok-4.3` | `reports/gap-audit/premium-xsp-killer-v3/grok-4.3-openrouter_20260621T1536Z.md` |
| OpenRouter #3 | `google/gemini-2.5-pro-preview` | `reports/gap-audit/premium-xsp-killer-v3/google-gemini-2.5-pro_20260621T1536Z.md` |
| OpenRouter #4 | `anthropic/claude-sonnet-4` | `reports/gap-audit/premium-xsp-killer-v3/claude-sonnet-4-openrouter_20260621T1536Z.md` |
| Cursor #1 | `gemini-3.1-pro` | `reports/gap-audit/premium-xsp-killer-v3/gemini-3.1-pro-cursor_AUDIT.md` |
| Cursor #2 | `gpt-5.4-medium` | `reports/gap-audit/premium-xsp-killer-v3/gpt-5.4-medium-cursor_AUDIT.md` |
| Cursor #3 | `kimi-k2.5` | `reports/gap-audit/premium-xsp-killer-v3/kimi-k2.5-cursor_AUDIT.md` |

**Pack:** `reports/gap-audit/pack-xsp-killer-v3/` (rebuilt post-commit)

---

## Progress since first v3 audit (pre-patch)

| Area | Pre-patch v3 | Post-`105c4ed` | Auditor agreement |
|---|---|---|---|
| Strike-invariant exit marks | **OPEN P0** | **Partially fixed** — fallback path strike-aware; **SPY chain path may still collapse 7500/7505** via `round(750.5)→750` | GPT cursor P0; Gemini says fixed; GLM did not flag |
| Upper-BB crash + stale bars | **OPEN P0** | **Fixed in source** — `_bars_fresh`, `BarSnapshot.open`, tests | 7/8 |
| Variant log pollution | **OPEN P1** | **Fixed** — per-variant logs, `brief_path=False`, fcntl lock | 8/8 |
| Slippage 1.5% punishes expensive legs | **Disputed** | **Improved** — hybrid `0.12/share + 0.5%` cap 1.5%; ~$62 RT at $61 prem vs ~$184 old | 8/8 agree improved; calibration TBD |
| DTE axis collapsed | **OPEN P0 observability** | **`dte_actual` logged**; yfinance expiry collapse unchanged | 8/8 |
| Long-DTE forced time_stop | Not in v3 P0 | **Fixed in code** — `suppress_morning_cut_dte_gte`; scoreboard not rerun | GPT, Gemini |
| Live RH prerequisites | **FAIL** | **Still FAIL** — stubs only | 8/8 |

**Net:** Paper-trust **code improved materially**. Soak **data is stale** (pre-patch scoreboard). Strategy edge **still unproven** — all closed trades negative, dominated by `time_stop`.

---

## Cross-auditor consensus — NEW / remaining P0 findings

### 1. SPY quote path still collapses adjacent XSP strikes (GPT cursor — NEW)

**Finding:** Main chain path maps XSP strike → SPY strike then `round()` — `7505 → 750.5 → 750`, same as `7500 → 750`. Pack scoreboard still shows identical entry/exit marks for ATM vs OTM.

**Votes:** GPT cursor (P0). Gemini cursor says per-strike marks fixed (fallback path).

**Action:** Fix half-step rounding in `lane_a_entry.py` / `lane_a_monitor.py`; invalidate strike-axis soak; rerun variants.

### 2. Fallback premium missing 10× scale (GLM — NEW)

**Finding:** `estimate_fallback_premium()` returns SPY-scale ~$6–9; chain path applies `SPY_TO_XSP_PREMIUM_SCALE`. Fallback entries incomparable in absolute $ PnL.

**Votes:** GLM (P0).

**Action:** Multiply fallback by scale at call site; verify no fallback entries in current scoreboard.

### 3. `prior_day_spy_positive` uses open-to-close, not close-to-close (GLM — NEW)

**Finding:** Green-day gate may block gap-up-then-selloff days incorrectly.

**Votes:** GLM (P0). Others did not flag.

**Action:** Switch to close-to-close return; log calendar date used.

### 4. `SPY_TO_XSP_PREMIUM_SCALE = 10.0` still disputed (GLM — carry-forward)

**Finding:** XSP (~750) and SPY (~750) may be 1:1 premium, not 10×. All absolute $ PnL may be wrong.

**Votes:** GLM (P1→P0 for live). GPT cursor says scale is consistent in code.

**Action:** Pull actual XSP chain from RH/CBOE before live sizing.

### 5. Scoreboard predates patch — rerun required (GPT, GLM — consensus)

**Finding:** Variant scoreboard built from pre-`105c4ed` runs. Long-DTE suppression, strike marks, slippage model not reflected in closed-trade history.

**Votes:** GPT cursor, GLM, Google API.

**Action:** Reset or tag pre-patch trades; accumulate ≥20 post-patch sessions.

---

## Cross-auditor consensus — strategy & economics (unchanged)

### Exit path dominated by `time_stop` (7/8)

All variant closed trades in pack still exit via `time_stop`. Fresh baseline brief shows `stop_loss` can fire post-patch — mixed code versions in evidence.

### Green-day filter — working, starves sample (7/8)

`v2_*_green_day` variants: 0 trades. Capital preservation vs sample starvation — disagreement on early baseline enable persists.

### DTE recommendation — split + stale data

14 DTE “least bad” in $ on old sample. Long DTE worse under old forced morning cut — **must rerun** with `suppress_morning_cut_dte_gte` before DTE promotion.

### Promotion

**WAIT (8/8)** — no baseline or variant rule changes until post-patch scoreboard reaches ≥20 sessions.

---

## Verdict table by auditor

| Auditor | Paper soak | Live RH | Variant promo |
|---|---|---|---|
| GLM 5.2 | WARN | FAIL | WAIT |
| Grok 4.3 | WARN | FAIL | WAIT |
| Google Gemini 2.5 Pro | WARN | FAIL | WARN/WAIT |
| Claude Sonnet 4 | OPERATIONAL | FAIL | WARN/WAIT |
| Gemini 3.1 Pro (cursor) | OPERATIONAL | FAIL | WAIT |
| GPT 5.4 (cursor) | WARN | FAIL | WAIT |
| Kimi K2.5 (cursor) | WARN* | FAIL | WAIT |

*Kimi report predates cursor re-run; treated as WARN based on pre-patch synthesis.

---

## Ranked patch backlog (post re-run)

| Priority | Item | Owner |
|---|---|---|
| **P0** | Fix SPY strike half-step rounding (7500 vs 7505) | entry + monitor |
| **P0** | Scale fallback premium by `SPY_TO_XSP_PREMIUM_SCALE` | entry |
| **P0** | Rerun variant soak / regenerate scoreboard post-patch | ops |
| **P1** | Close-to-close for `prior_day_spy_positive` | entry |
| **P1** | Confirm XSP premium scale vs RH chain | research |
| **P1** | Port RH adapter + kill switch + conductor reviewer | Cemini harvest |
| **P2** | Port `vol_monitor.py` IV gate | Cemini harvest |
| **P2** | Rebuild local `@wiki/concepts/xsp-*` | OSINT |

---

## Operator next actions

1. **Ship P0 quote/fallback fixes** above, then **reset variant scoreboard clock**.
2. **Continue paper soak** — target 20 post-patch sessions per variant.
3. **Do not live flip** — unanimous FAIL until Cemini execution + risk stack ported.
4. **Do not promote baseline** — WAIT on all variant knobs.

**Prior synthesis (pre-patch):** `briefs/2026-06-21_xsp-killer-super-audit-synthesis-v3.md`
