---
title: "XSP Killer super-audit synthesis v3 (variant soak + strategy math)"
type: brief
tags: [super-audit, xsp-killer, variant-soak, ops, xsp_lane_a_v2]
created: 2026-06-21
updated: 2026-06-21
---

## Executive verdict (7/8 auditors; consensus)

| Environment | Consensus | Split |
|---|---|---|
| **Paper soak (now)** | **WARN / OPERATIONAL** | 3× OPERATIONAL (Grok, Gemini cursor, Sonnet), 4× WARN (GLM 5.2, GPT cursor, Google API, Gemini API). **All agree:** continue paper; P0 code bugs from v2 are fixed; **do not trust cross-variant PnL until mark-by-strike bug fixed.** |
| **Live RH flip** | **FAIL (7/7)** | Unanimous — no execution path, no kill switch, no conductor shadow, XSP wiki gaps, yfinance-only chains. |
| **Variant promotion** | **WAIT (7/7)** | 2–3 trades/variant vs ≥20 gate; 0% win rate; green-day variants 0 trades; **do not change production baseline.** |

**Skipped / failed legs:**
- `claude-opus-4-8-thinking-high` (Cursor) — resource exhausted
- `openrouter/fusion` — JSON parse error (0-byte/malformed body)

**Audit legs completed:**

| Slot | Model | Report |
|---|---|---|
| OpenRouter #1 | `z-ai/glm-5.2` | `reports/gap-audit/premium-xsp-killer-v3/glm-5.2-openrouter_20260621T1504Z.md` |
| OpenRouter #2 | `x-ai/grok-4.3` | `reports/gap-audit/premium-xsp-killer-v3/grok-4.3-openrouter_20260621T1504Z.md` |
| OpenRouter #3 | `google/gemini-2.5-pro-preview` | `reports/gap-audit/premium-xsp-killer-v3/google-gemini-2.5-pro_20260621T1504Z.md` |
| OpenRouter #4 | `anthropic/claude-sonnet-4` | `reports/gap-audit/premium-xsp-killer-v3/claude-sonnet-4-openrouter_20260621T1504Z.md` |
| Cursor #1 | `gemini-3.1-pro` | `reports/gap-audit/premium-xsp-killer-v3/gemini-3.1-pro-cursor_AUDIT.md` |
| Cursor #2 | `gpt-5.4-medium` | `reports/gap-audit/premium-xsp-killer-v3/gpt-5.4-medium-cursor_AUDIT.md` |
| Cursor #3 | `kimi-k2.5` | `reports/gap-audit/premium-xsp-killer-v3/kimi-k2.5-cursor_AUDIT.md` |

**Pack:** `reports/gap-audit/pack-xsp-killer-v3/` · **Prompt:** `prompts/xsp_killer_super_audit.md` (v3)

---

## Progress since v2 audit (2026-06-16/17)

| Area | v2 state | v3 state | Auditor agreement |
|---|---|---|---|
| P0 paper-trust bugs | Fixed in `8eece0b` | **Still fixed** — 46/46 tests (pack build) | 7/7 |
| DTE monitor drop | Fixed 2026-06-17 | Verified in soak | 7/7 |
| Variant soak | Not in v2 scope | **13 shadows live**, scoreboard wired to cron | 7/7 |
| Strategy economics | Unknown (broken holding period) | **All post-fix exits = `time_stop`, 0 wins** | 7/7 |
| Live RH | FAIL | **Still FAIL** | 7/7 |

**Net:** Infrastructure and paper-trust **improved**. Strategy edge **still unproven** — soak is now measuring real overnight holds, and the thesis is losing in the current window.

---

## Cross-auditor consensus — P0 findings (fix before trusting scoreboard)

### 1. Strike-invariant exit marks (NEW — GLM + GPT)

**Finding:** `v2_28dte_atm` (strike 7500) and `v2_28dte_otm` (strike 7505) report **identical** `last_exit.paper_pnl_usd: -352.6`.

**Evidence:** `briefs/xsp-lane-a-variants-scoreboard.json` — OTM position_id includes `:7505` but PnL matches ATM.

**Implication:** Strike-axis variant comparisons are **invalid** until monitor uses per-strike marks. `estimate_fallback_premium(spy_price, dte)` has no strike parameter.

**Votes:** GLM 5.2 (P0), GPT cursor (P1 fallback path), implied by identical PnL clusters across exit-tweak variants.

### 2. DTE axis collapsed by yfinance expirations (NEW — GLM)

**Finding:** `v2_14dte_atm` and `v2_21dte_atm` both entered `paper:XSP:2026-07-10:7500`. `v2_45dte_atm` and `v2_60dte_atm` both entered `2026-07-31:7500`.

**Implication:** DTE grid tests **4 actual expiries**, not 6. Log `dte_actual` at entry; consider real SPX/XSP chain vendor.

**Votes:** GLM 5.2 (P0). Others noted min-DTE “least bad” but did not all catch collapse.

### 3. Latent upper-BB crash + stale TA bars (NEW — GPT cursor)

**Finding:** `detect_upper_bb_exit()` may access `curr.open` missing from `BarSnapshot`. Monitor accepts multi-day stale intraday bars.

**Votes:** GPT cursor (P0). **Not flagged** by API legs — **needs code review + test**.

### 4. Variant monitor pollutes baseline logs (NEW — GPT cursor)

**Finding:** `run_variant_monitor()` may write to shared baseline paper log/brief paths.

**Votes:** GPT cursor (P1). **Action:** thread variant log/brief paths through monitor.

### 5. Percent slippage punishes expensive legs (NEW — Gemini cursor)

**Finding:** `slippage_pct_of_premium: 0.015` on ~$61 premium ≈ **$183 round-trip friction** — likely overstated for SPY proxy; suppresses paper PnL.

**Votes:** Gemini cursor (Critical). GLM/Sonnet say 1.5% “adequate for paper” — **disagreement hook #1**.

---

## Cross-auditor consensus — strategy & economics

### Exit path dominated by `time_stop` (7/7)

Every closed post-fix trade across baseline + all traded variants exits via **`time_stop`**. No SL, no TP, no upper-BB exit observed.

| Interpretation | Auditors |
|---|---|
| Overnight move ~−10–12% on premium, below 20% SL | GLM, Grok |
| TP conjunction (+20% AND upper BB AND 30-min window) unreachable | Gemini, Grok, Sonnet |
| Directional loss (adverse overnight SPY), not pure theta | GLM |
| Long DTE pays more premium but same 10:00 cut → worse $ loss | Grok, GPT |

### Green-day filter (prior_day_spy_positive) — working but starves sample (6/7)

| Position | Auditors |
|---|---|
| **Correctly blocked** entries on red prior days; best capital preservation | Grok, Sonnet, GPT, Kimi, Gemini |
| **Too strict** — relax to ≥ −0.5% or enable in baseline after soak | Grok, Gemini (early baseline enable) |
| **Keep strict** until 10+ sessions | GLM |

**Disagreement hook #2:** Gemini would enable `prior_day_spy_positive: true` in baseline **now**; GLM/Grok say **WAIT** for 20-session gate but keep green variants.

### DTE recommendation — split (disagreement hook #3)

| View | Auditors | Rationale |
|---|---|---|
| **Raise to 28–35 DTE** (less gamma) | Grok, Gemini, Sonnet | Mentor overnight hold; min-DTE hurt in v2 diagnosis |
| **14 DTE “least bad” in $** | Sonnet, Grok (early read) | Scoreboard: v2_14dte_atm −$453 vs baseline −$1043 |
| **Long DTE worst** under same time_stop | GLM, Grok (math section) | 45/60 DTE −$916; forced exit kills long-dated thesis |
| **Cannot judge until mark bug + suppress_morning_cut_dte_gte wired** | GPT | Dead code for long-DTE morning-cut suppression |

**Synthesis:** Do **not** promote DTE changes to production until mark-by-strike fixed and `suppress_morning_cut_dte_gte` implemented (config exists, GPT found dead code). Continue soak; **valid inter-expiry buckets** today: Jul 10, Jul 17, Jul 24, Jul 31 only.

---

## Phase A — Cemini harvest (unanimous P0 trio)

| Asset | Votes | Status |
|---|---|---|
| `core/ems/adapters/robinhood.py` | 7/7 P0 | Not ported |
| `conductor/reviewer/` | 7/7 P0 | Not ported |
| `trading_playbook/kill_switch.py` + `risk_engine.py` | 7/7 P0 | Not ported |
| `options_greeks/vol_monitor.py` | 6/7 P1 | GLM upgraded to P1 (IV crush hypothesis) |
| `wiki_enforcement_gate.py` | 5/7 P1 | Not ported |

**OSINT wiki:** `@wiki/concepts/xsp-*` still **missing** on xsp-killer host (7/7). Local `research_wiki/` has SPY + Greeks fragments only. **Action:** SCP from Cemini or rebuild before live.

---

## Variant scoreboard snapshot (post-fix, 2026-06-21)

| Variant | Trades | Realized PnL | Notes |
|---|---:|---:|---|
| v2_baseline_prod | 3 | −$1043.02 | Worst aggregate |
| v2_14dte_atm | 2 | −$453.16 | Least $ loss; **same contract as v2_21dte** |
| v2_28dte_atm | 2 | −$654.45 | Valid Jul 17 bucket |
| v2_28dte_otm | 2 | −$624.00 | **Invalid strike compare** (same mark as ATM) |
| v2_*_green_day | 0 | $0 | Filter blocked — capital preserved |

**Promotion:** **WAIT** — 0/7 auditors dissent.

---

## Ranked patch backlog (synthesized)

### P0 — before trusting variant scoreboard or live flip

1. **Per-strike exit marks** — no fallback exit PnL without strike-specific quote
2. **Fix `lane_a_ta.py` upper-BB crash path** + stale bar freshness guard (GPT)
3. **Isolate variant logs/briefs** from baseline artifacts (GPT)
4. **Add `fcntl` lock** to variants state file (GLM)
5. **Log `dte_actual`** at entry; document yfinance expiry collapse
6. Port **RH adapter + kill switch + conductor reviewer** (live flip blockers)

### P1 — strategy iteration (after P0)

1. Implement **`suppress_morning_cut_dte_gte`** (dead code today)
2. Revisit **slippage model** — fixed $/share vs % of premium (Gemini vs others)
3. **`require_upper_bb_for_take_profit: false`** in baseline only after 20-session variant evidence
4. **`prior_day_spy_positive`** — keep in green variants; consider baseline enable after mark fix
5. Port **vol_monitor** for IV spike filter at close
6. **Cache SPY chain** once per variant cron (13× fetch → 1×)

### P2 — efficiency

1. Cron fault isolation (`set -e` baseline should not skip variants)
2. `PYTHONPATH`/packaging for hermetic pytest
3. VWAP session reset (GPT)
4. Variant rules cache cleanup

---

## Efficiency & tuning summary

| Knob | Current | Synthesized recommendation |
|---|---|---|
| DTE pick | min (14) prod | **WAIT** — soak valid buckets; implement long-DTE suppress before judging 45/60 |
| TP / BB | +20% AND upper BB | Variants already test no-BB; **TP never fires** — consider 8–10% TP **after** TA fix |
| Green-day gate | off (prod) | **Keep in variants**; 0 trades is feature not bug in red tape |
| Slippage | 1.5% of premium | **Investigate** — Gemini says materially overstated; run sensitivity |
| Variant runtime | ~11s / 13 variants | Share chain fetch → target <3s |
| Soak gate | ≥20 sessions | **~10% complete** — continue through July |

---

## Questions blocking live flip (merged)

1. RH **XSP strike notation** vs code (7500 = SPX/10?) — operator confirm on live chain
2. **Data vendor** for XSP/SPX options (yfinance has no XSP)
3. RH **fee model** for index mini options vs ETF options
4. **Slippage realism** — paper 1.5% vs live XSP spread
5. Mirror **`xsp-*` wiki** pages from Cemini

---

## Operator next actions

1. **Fix P0 mark-by-strike + TA freshness** — highest leverage for valid soak
2. **Continue variant cron** — do not promote; target 20 sessions post-fix
3. **Do not live flip** — unanimous FAIL
4. Re-run super-audit v3 legs after P0 patches (reuse pack builder + API runner)

---

## Artifacts

| Item | Path |
|---|---|
| Prompt v3 | `prompts/xsp_killer_super_audit.md` |
| Pack builder | `scripts/build_xsp_killer_super_audit_pack.py` |
| API runner (GLM 5.2 replaces DeepSeek) | `scripts/run_xsp_killer_super_audit_api.py` |
| Raw reports | `reports/gap-audit/premium-xsp-killer-v3/` |
| Meta | `reports/gap-audit/premium-xsp-killer-v3/meta_20260621T1504Z.json` |
| Prior synthesis | `briefs/2026-06-16_xsp-killer-super-audit-synthesis-v2.md` |
