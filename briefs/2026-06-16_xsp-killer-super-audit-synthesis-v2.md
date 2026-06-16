---
title: "XSP Killer super-audit synthesis v2 (post mentor playbook v2)"
type: brief
tags: [super-audit, xsp-killer, cemini-harvest, ops, xsp_lane_a_v2]
created: 2026-06-16
updated: 2026-06-16
---

## Executive verdict

| Environment | Verdict | Rationale |
|---|---|---|
| **Paper soak (now)** | **WARN** | v2 mentor playbook is wired and **34/34 tests pass**, but paper PnL is still untrustworthy (SPY/XSP premium proxy, double-counted economics, regime read shape bug) |
| **Live RH flip** | **FAIL** | No order execution path, stop only evaluated 09:30–10:00 ET, RH adapter untested, no kill switch / daily loss cap |

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

| # | Finding | Models | Evidence | Fix |
|---|---|---|---|---|
| 1 | **SPY premium used as XSP premium without 10× scale** | Gemini, Sonnet, Kimi, Opus, GPT | `lane_a_entry.py` `fetch_spy_call_quote` → paper `average_price` ~$2.45 vs ~$24.50 expected | Multiply SPY proxy premium by 10 (or document SPY-side PnL-only mode explicitly) |
| 2 | **Paper economics double-count** — slippage/commission at entry fill, then `_attach_economics_pnl()` again on exit | Opus, GPT | `lane_a_entry.py` + `paper_economics.py` | Single economics pass; dedupe exit events (`record_paper_exit_signals` vs `close_paper_positions_on_exit`) |
| 3 | **`read_regime()` Redis shape bug** — double-unwrap of `value` → always falls through to yfinance | Opus, GPT | `lane_a_monitor.py` `read_regime()` vs `intel.py` | Read flat regime string from intel payload |
| 4 | **Stop loss only inside 09:30–10:00 sell window** — not a true intraday stop | Opus, GPT, Kimi | `lane_a_monitor.py` `evaluate_exit_alerts` | Separate always-on SL path or extend monitor cadence |
| 5 | **No live order execution** — all alerts `would_auto_close=False` | All | `robinhood.py`, monitor exit path | Wire Cemini RH adapter + conductor gate before flip |
| 6 | **Time-stop at 10:00 missing** — mentor "sell by 10am" not enforced if neither SL nor TP fires | Kimi, Opus | `evaluate_exit_alerts` | Add `breakeven_or_time_stop` at 10:00 ET |

### P1 — profitability / operability

| # | Finding | Fix |
|---|---|---|
| 7 | Take-profit requires +20% **and** upper BB **and** morning window — conjunction rarely true | Document hold risk; consider OR-path for hard 10:00 time stop |
| 8 | `already_entered_today` blocks after any entry log row (including failed attempts) | Gate on open position + successful fill only |
| 9 | State file race — intraday + monitor timers overlap 09:45/10:00 | File lock or Redis state |
| 10 | Slippage 0.5% understates XSP spreads | Raise to ~1.5% or derive from SPY bid-ask |
| 11 | yfinance single-source fragility | Paid vendor or IBKR fallback for live |
| 12 | Cemini + XSP systemd timers may both fire | Verify `cemini-xsp-lane-*` disabled on prod |

### Disputed / likely false positive

| Finding | Verdict |
|---|---|
| Kimi: truncated `return Fals` at `lane_a_entry.py:644` | **Not present** in current code — grep shows valid returns |
| XSP strike should be SPX/10 (600 vs 6000) | **Disputed** — XSP options may use SPX-index-point notation; operator must confirm vs CBOE/RH chain before changing scale |

---

## Phase B — What v2 got right (all auditors)

- Mentor playbook v2 encoded in YAML: close-only entry, ≥14 DTE, cheapest near-ATM, sell 09:30–10:00, no 08:30–09:30 sell, 20% SL/TP, BB patience on TP
- Mon–Fri systemd timers; monitor at 09:35/09:45/10:00
- `macro_regime.py` + `paper_economics.py` vendored; `log_path=` test isolation
- 34/34 pytest green on v2 logic version `xsp_lane_a_v2`

---

## Ranked patch backlog (post-v2)

### P0 (before meaningful paper soak)
1. Fix SPY→XSP premium scaling (or explicitly label paper as SPY-notional)
2. Fix paper economics double-count + exit event dedup
3. Fix `read_regime()` intel payload shape
4. Add 10:00 ET time-stop exit
5. Extend stop-loss beyond sell window OR document accepted gap risk

### P1 (before live flip)
6. Port Cemini `robinhood_adapter.py` + shadow `conductor_reviewer`
7. Daily loss cap / kill switch from Cemini `risk_engine`
8. Port `vol_monitor.py` for vol-aware sizing
9. Mirror destroyed `xsp-*` wiki pages locally
10. Confirm XSP strike notation with RH chain before any order code

### P2
11. Garrett/SMB conviction sizing scale
12. Log rotation for `paper_log_lane_a.jsonl`
13. IBKR/yfinance fallback for bars

---

## Test & soak plan (consensus)

**Before soak:** add tests for SPY/XSP premium scale, economics single-pass PnL, 10:00 time-stop, entry window boundary (15:45–16:00).  
**Soak:** minimum **4 weeks / 20 sessions** after P0 fixes; discard pre-fix paper logs.  
**Live gate:** conductor shadow green, RH adapter integration test, daily loss cap, operator confirms strike scale + data vendor.

---

## Questions blocking live flip

1. Production data vendor for XSP chains (yfinance has no XSP options)?
2. RH fee model — $0 PFOF vs passed-through exchange fees for paper economics?
3. XSP strike notation on RH — index points vs SPX/10?
4. Will `research_wiki/concepts/xsp-*` be mirrored to this host?
5. Is `DEEPSEEK_API_KEY` (or alternate) available for conductor reviewer on standalone bot?

---

*Synthesis merged from kimi-k2.5, gpt-5.5-medium, claude-opus-4-8-thinking-high (Cursor) + gemini-2.5-pro-preview, claude-sonnet-4 (OpenRouter). Prior round (Grok + DeepSeek) superseded for v2 code.*
