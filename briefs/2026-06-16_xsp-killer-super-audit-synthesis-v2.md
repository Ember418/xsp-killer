---
title: "XSP Killer super-audit synthesis v2 (post mentor playbook v2)"
type: brief
tags: [super-audit, xsp-killer, cemini-harvest, ops, xsp_lane_a_v2]
created: 2026-06-16
updated: 2026-06-17
---

## Executive verdict

| Environment | Verdict | Rationale |
|---|---|---|
| **Paper soak (now)** | **GO** | Audit P0 paper-trust bugs **shipped** in `8eece0b` (2026-06-16 14:18 UTC). **40/40 tests pass**. Jun 17 morning monitor verified open position → `time_stop` at 10:00 ET. Residual risk: SPY-chain proxy (not exchange XSP marks). |
| **Live RH flip** | **FAIL** | No order execution path, Cemini RH adapter not ported, no conductor shadow / daily loss cap |

> **Note:** Original audit text below (WARN) reflects **pre-patch** code at synthesis time (~13:45 UTC). See **Post-patch status** for current state.

**Audit legs run (wiki `/super-audit` pattern — fresh models, no DeepSeek/Grok reuse):**

| Slot | Model | Status |
|---|---|---|
| Cursor premium #1 | `kimi-k2.5` | Full report |
| Cursor premium #2 | `gpt-5.5-medium` | Full report |
| Cursor premium #3 | `claude-opus-4-8-thinking-high` (Fable slot) | Full report |
| OpenRouter #1 | `google/gemini-2.5-pro-preview` | Full report |
| OpenRouter #2 | `anthropic/claude-sonnet-4` | Full report |

**Skipped per operator:** DeepSeek Reasoner, Grok 4.3 (prior round).  
**Failed OpenRouter:** `openrouter/fusion`, `moonshotai/kimi-k2.6` — HTTP 200, 0-byte body even on slim 59k pack.

Raw reports: `/opt/xsp-killer/reports/gap-audit/premium-xsp-killer-v2/`

---

## Post-patch status (2026-06-17)

### Shipped — commit `8eece0b`

| Audit # | Finding | Status |
|---|---|---|
| 1 | SPY premium without 10× XSP scale | **FIXED** — `SPY_TO_XSP_PREMIUM_SCALE = 10.0` |
| 2 | Paper economics double-count | **FIXED** — `entry_mid_premium` + `pnl_from_entry_fill()` |
| 3 | `read_regime()` intel shape bug | **FIXED** — flat `regime`/`status` read |
| 4 | Stop loss only in TP window | **FIXED** — SL anytime after 08:30–09:30 no-sell |
| 6 | Missing 10:00 time-stop | **FIXED** — `time_stop` at `sell_deadline_et` |
| P1 #8 | `already_entered_today` over-blocking | **FIXED** — only `entered: true` |
| P1 #9 | State file race | **FIXED** — `fcntl` lock on state file |
| P1 #10 | Slippage 0.5% too low | **FIXED** — **1.5%** in `lane_a_rules.yaml` |
| — | Exit event dedup | **FIXED** |

### Shipped — 2026-06-17 follow-up (monitor soak bug)

| Finding | Status |
|---|---|
| Open paper positions **invisible to monitor** when DTE drops below entry `dte_min` (e.g. entered at 14 DTE, monitored at 13 DTE) | **FIXED** — `is_lane_a_monitor_contract()` (no lower DTE bound for exit path) |

### Jun 17 morning monitor verification

Replayed `--at-et` for `paper:XSP:2026-06-30:7520` (entered 2026-06-16 15:45 ET):

| Check (ET) | Positions | Alerts | Result |
|---|---|---|---|
| 09:35 | 1 | 0 | Position visible; regime GREEN; MTM −$552 (economics-adjusted) |
| 09:45 | 1 | 0 | No SL (−5.5% < −20%); no TP (no upper BB) |
| 10:00 | 1 | 1 | **`time_stop`** fired — paper position closed at −$552.10 |

Brief: `briefs/xsp-lane-a-monitor-latest.json` · State: position **closed** with `exit_reason=time_stop`.

**Discard pre-fix paper logs** (entries before 2026-06-16 14:18 UTC and operator test cleanup rows).

### Still open (live flip / P1)

| Item | Status |
|---|---|
| No live RH order execution (#5) | Paper log-only — by design |
| Port Cemini `robinhood.py` adapter | Not done |
| Conductor shadow reviewer | Not done |
| Daily loss cap / kill switch | Not done |
| `xsp-*` wiki pages on host | Still missing |
| XSP strike notation vs RH chain | Operator confirm |
| yfinance → paid vendor | Not done |
| `cemini-xsp-lane-*` double-fire | **Verified inactive** on prod |

---

## Phase A — Cemini steal matrix (5-model consensus)

| Priority | Asset | Use in XSP Killer | Effort | Agreement |
|---|---|---|---|---|
| **P0** | `conductor/reviewer/` | Shadow pre-trade review on entry + RH close validation (8s timeout, fail-open) | M | 5/5 |
| **P0** | `core/ems/adapters/robinhood.py` | Replace thin `xsp_killer/robinhood.py` before live flip | L | 5/5 |
| **P0** | `trading_playbook/kill_switch.py` + `risk_engine.py` | Daily loss cap, position/notional limits | S–M | 3/5 (Opus, GPT, Sonnet) |
| **P1** | `options_greeks/vol_monitor.py` | Vol regime sizing, IV spike filter at entry | M | 4/5 |
| **P1** | `core/wiki_enforcement_gate.py` | Block trades against documented failure patterns | M | 4/5 |
| **P2** | `conductor/escalation/cycle_detector.py` | Doom-loop detection on paper events | S | 3/5 |
| **P2** | `orchestrator_wiki_context.py` | Attach wiki excerpts to alerts | L | 3/5 |
| **Done** | `macro_regime.py` | Vendored fallback when Redis intel null | S | Already in v2 |

### OSINT wiki — still a material gap

All five auditors confirm: **`@wiki/concepts/xsp-*` pages are missing** on the XSP Killer host (librarian destroyed). Local `research_wiki/` has fragments only (SPY entity, Kalshi BB baseline, Greeks, SMB briefs). **Action:** SCP or rebuild `xsp-*` concept pages from Cemini + mentor Discord into `/opt/xsp-killer/wiki/` or accept blind spots on liquidity/settlement/scaling.

### Conductor — shadow-first, not full dispatch

Consensus: port **reviewer only** before live; do not wire full async conductor middleware yet. Publish `macro_regime` to intel bus when Redis available.

---

## Phase B — Confirmed bugs (multi-model + code spot-check)

### P0 — blocks trustworthy paper / live

| # | Finding | Models | Evidence | Fix | Status |
|---|---|---|---|---|---|
| 1 | **SPY premium used as XSP premium without 10× scale** | Gemini, Sonnet, Kimi, Opus, GPT | `lane_a_entry.py` `fetch_spy_call_quote` → paper `average_price` ~$2.45 vs ~$24.50 expected | Multiply SPY proxy premium by 10 | **FIXED** `8eece0b` |
| 2 | **Paper economics double-count** | Opus, GPT | `lane_a_entry.py` + `paper_economics.py` | Single economics pass; exit dedup | **FIXED** `8eece0b` |
| 3 | **`read_regime()` Redis shape bug** | Opus, GPT | `lane_a_monitor.py` `read_regime()` vs `intel.py` | Read flat regime string | **FIXED** `8eece0b` |
| 4 | **Stop loss only inside 09:30–10:00 sell window** | Opus, GPT, Kimi | `evaluate_exit_alerts` | SL outside TP window | **FIXED** `8eece0b` |
| 5 | **No live order execution** | All | `robinhood.py`, monitor exit path | Wire Cemini RH adapter + conductor | **OPEN** |
| 6 | **Time-stop at 10:00 missing** | Kimi, Opus | `evaluate_exit_alerts` | Add time-stop at 10:00 ET | **FIXED** `8eece0b` — verified 2026-06-17 |

### P1 — profitability / operability

| # | Finding | Fix | Status |
|---|---|---|---|
| 7 | Take-profit requires +20% **and** upper BB **and** morning window | Document hold risk; time-stop OR-path | **Mitigated** by time-stop (#6) |
| 8 | `already_entered_today` blocks failed attempts | Gate on successful fill only | **FIXED** `8eece0b` |
| 9 | State file race | File lock or Redis state | **FIXED** `8eece0b` |
| 10 | Slippage 0.5% understates XSP spreads | Raise to ~1.5% | **FIXED** `8eece0b` |
| 11 | yfinance single-source fragility | Paid vendor or IBKR fallback | **OPEN** |
| 12 | Cemini + XSP systemd timers may both fire | Verify cemini timers disabled | **VERIFIED** inactive |
| 13 | Monitor drops open positions when DTE < entry min | `is_lane_a_monitor_contract()` | **FIXED** 2026-06-17 |

### Disputed / likely false positive

| Finding | Verdict |
|---|---|
| Kimi: truncated `return Fals` at `lane_a_entry.py:644` | **Not present** in current code — grep shows valid returns |
| XSP strike should be SPX/10 (600 vs 6000) | **Disputed** — XSP options may use SPX-index-point notation; operator must confirm vs CBOE/RH chain before changing scale |

---

## Phase B — What v2 got right (all auditors)

- Mentor playbook v2 encoded in YAML: close-only entry, ≥14 DTE, cheapest near-ATM, sell 09:30–10:00, no 08:30–09:30 sell, 20% SL/TP, BB patience on TP
- Mon–Fri systemd timers; monitor at 09:30/09:35/09:45/10:00 ET
- `macro_regime.py` + `paper_economics.py` vendored; `log_path=` test isolation
- **40/40 pytest green** on v2 logic version `xsp_lane_a_v2` (post-patch)

---

## Ranked patch backlog (post-v2)

### P0 (before meaningful paper soak) — **COMPLETE**

1. ~~Fix SPY→XSP premium scaling~~ ✓
2. ~~Fix paper economics double-count + exit event dedup~~ ✓
3. ~~Fix `read_regime()` intel payload shape~~ ✓
4. ~~Add 10:00 ET time-stop exit~~ ✓
5. ~~Extend stop-loss beyond sell window~~ ✓
6. ~~Monitor open positions below entry DTE min~~ ✓ (2026-06-17)

### P1 (before live flip)

7. Port Cemini `robinhood_adapter.py` + shadow `conductor_reviewer`
8. Daily loss cap / kill switch from Cemini `risk_engine`
9. Port `vol_monitor.py` for vol-aware sizing
10. Mirror destroyed `xsp-*` wiki pages locally
11. Confirm XSP strike notation with RH chain before any order code

### P2

12. Garrett/SMB conviction sizing scale
13. Log rotation for `paper_log_lane_a.jsonl`
14. IBKR/yfinance fallback for bars

---

## Test & soak plan (consensus)

**Before soak:** ~~add tests for SPY/XSP premium scale, economics single-pass PnL, 10:00 time-stop, entry window boundary~~ — **done**.  
**Soak:** minimum **4 weeks / 20 sessions** after P0 fixes; **discard pre-fix paper logs**. Clock started 2026-06-16 post-`8eece0b`.  
**Live gate:** conductor shadow green, RH adapter integration test, daily loss cap, operator confirms strike scale + data vendor.

---

## Questions blocking live flip

1. Production data vendor for XSP chains (yfinance has no XSP options)?
2. RH fee model — $0 PFOF vs passed-through exchange fees for paper economics?
3. XSP strike notation on RH — index points vs SPX/10?
4. Will `research_wiki/concepts/xsp-*` be mirrored to this host?
5. Is `DEEPSEEK_API_KEY` (or alternate) available for conductor reviewer on standalone bot?

---

*Synthesis merged from kimi-k2.5, gpt-5.5-medium, claude-opus-4-8-thinking-high (Cursor) + gemini-2.5-pro-preview, claude-sonnet-4 (OpenRouter). Post-patch addendum 2026-06-17.*
