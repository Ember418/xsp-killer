---
title: "XSP Killer super-audit synthesis (Fusion + Grok 4.3 + DeepSeek Reasoner)"
type: brief
tags: [super-audit, xsp-killer, cemini-harvest, ops]
created: 2026-06-16
updated: 2026-06-16
---

## Executive verdict

| Environment | Verdict | Rationale |
|---|---|---|
| **Paper soak (now)** | **WARN** | Infra runs (33/33 tests, systemd cutover done) but economics and gates are not trustworthy until P0 fixes land |
| **Live RH flip** | **FAIL** | Thin RH adapter, no conductor gate, regime often null, no slippage/fees, live path untested |

**Audit legs run:** Grok 4.3 + DeepSeek Reasoner (full reports). OpenRouter Fusion attempted twice (`openrouter/fusion` default + custom panel) — HTTP 200 but empty/truncated JSON body (OpenRouter-side issue with ~260k-char pack). Synthesis below merges both successful legs + manual code verification.

---

## Phase A — What to steal from Cemini (consensus)

| Priority | Asset | Use in XSP Killer | Effort |
|---|---|---|---|
| **P0** | `trading_playbook/macro_regime.py` | Standalone GREEN/YELLOW/RED when Redis `intel:playbook_snapshot` is null (current default on extracted bot) | S |
| **P0** | `core/ems/adapters/robinhood.py` | Replace 50-line `xsp_killer/robinhood.py` before any live flip — idempotency, contract matching, timeout recovery | L |
| **P1** | `conductor/reviewer/` + `dispatch.py` | Shadow pre-trade review on every Lane A entry (8s timeout, fail-open) | M |
| **P1** | `core/wiki_enforcement_gate.py` | Block repeat mistakes once local wiki context exists | M |
| **P2** | `options_greeks/vol_monitor.py` | Strike sizing / vol-regime filter | M |
| **P2** | `conductor/escalation/cycle_detector.py` | Detect entry/exit doom loops | S |
| **Skip for now** | TradingView MCP (30 tools), signal-fusion engine, full orchestrator | Overkill for standalone swing bot until paper economics are fixed | — |

### Conductor — yes, but shadow-first

Conductor is **not wired today**. Both models agree: port **reviewer in shadow mode** before entries write to `paper_log`. Do **not** port full async dispatch middleware yet. Cycle detector is cheap insurance once intraday + close-window paths both fire.

### OSINT wiki — NOT fully mined for XSP strategy

| Topic | Local wiki? | In bot? | Gap |
|---|---|---|---|
| XSP lane framework / core book thesis | **No** — was on destroyed librarian (`@wiki/concepts/xsp-*`) | Partial (YAML + briefs only) | **Material gap** — recreate from `briefs/2026-06-14_xsp-lane-*.md` + mentor Discord |
| BB/VWAP mentor playbook | Briefs only | Coded in `lane_a_ta.py` | Rationale and edge cases missing from repo |
| SPY entity (liquidity, proxy role) | `research_wiki/entities/tickers/spy.md` | Used as TA symbol, not documented | Add `@concepts/spy-xsp-proxy` page |
| SMB Capital K79 (tape, blow-up flags, prop ops) | `briefs/2026-05-29_k79-smb-capital-*.md` | **None** | Steal P1: pre-trade risk plan, 3+ blow-up flags → halt, no averaging down |
| Trading playbook GREEN/YELLOW/RED | `trading-playbook-research.md` + `macro_regime.py` | Partial (regime gate reads Redis, often null) | Vendored macro_regime fixes this |
| Greeks / 0DTE research | `greeks-*.md` | None | Low priority for ≥14 DTE swing |
| Kalshi BB baseline | `kalshi-4-3-29.md` | None | Useful as TA null benchmark, not blocking |

**Wiki search hits for xsp/bollinger/vwap:** essentially **one file** (`kalshi-4-3-29.md`). The operator was right — OSINT was **not** fully examined for this strategy.

---

## Phase B — Confirmed bugs & logic issues (code-verified)

### P0 — blocks trustworthy paper / live

| # | Finding | Evidence | Fix |
|---|---|---|---|
| 1 | **Upper BB exit only when PnL ≥ 0** — losing positions won't exit on technical rejection | `lane_a_monitor.py:269` `if pnl_c is None or pnl_c > 0:` | Remove PnL guard for `upper_bb_rejection` |
| 2 | **`prior_day_spy_positive: true` conflicts with mentor dump-bounce** — valid red-day bounces blocked | `config/lane_a_rules.yaml:13` | Make optional or default `false`; mentor playbook wins |
| 3 | **Regime gate passes when intel null** — standalone bot has no Redis playbook | `read_regime()` returns `(None, True)` when intel missing | Vendored `macro_regime.py` fallback; fail-closed to YELLOW if unknown |
| 4 | **Both 1h + 15m BB required** — stricter than mentor "bounce off lower/mid" | `lane_a_ta.py` `entry_ok = entry_p and entry_c` | Add `ta.confirm_optional` config; default primary-only for mentor alignment |
| 5 | **Tests pollute production paper log** — pytest appends to `logs/xsp_lane_a_paper.jsonl` | `append_entry_log` defaults to `DEFAULT_PAPER_LOG`; pack build pytest left `"detail":"test bounce"` entries | Pass `log_path=tmp_path/"paper.jsonl"` in all tests |
| 6 | **No slippage / commission in paper PnL** | `lane_a_paper_pnl` + monitor MTM | Add $0.65/contract + half-spread slippage |

### P1 — profitability / operational

| # | Finding | Evidence | Fix |
|---|---|---|---|
| 7 | SPY chain proxy — strike mapping uses `strike/10` for quote (intentional) but **marks in monitor also proxy** | `fetch_spy_call_quote(strike/10)` + monitor line 395 | Document proxy limits; shadow-compare RH XSP marks before live |
| 8 | yfinance single-attempt, no retry | All fetch paths `timeout=10` | 2× retry with backoff |
| 9 | Systemd timers fire weekends | Timer units lack `Mon..Fri` | Add weekday calendar to lane-a timers |
| 10 | Lane B shares Lane A RH poll env | `lane_b_monitor.py` | Separate `XSP_LANE_B_RH_POLL` flag |
| 11 | `already_entered_today` | Only blocks on `entered: true` — **correct** | No change (models over-flagged) |

### SPY premium scaling — nuance

Models claimed **10× premium error**. Code maps XSP strike 6010 → SPY strike 601 for quote; ~$2.45 SPY call premium is **plausible** for ~32 DTE ATM-ish call. XSP multiplier is $1/point vs SPY 100 shares — dollar premiums can be similar at equivalent moneyness. **Treat as unvalidated proxy**, not proven 10× bug — resolve with 10 live RH XSP vs SPY-scaled samples before live.

---

## Phase B — What is NOT broken (audit corrections)

- **`already_entered_today`** — correctly only blocks duplicate successful entries, not skips
- **Paper log `"test bounce"`** — from **pytest** during pack build writing to prod log path, not live TA fallback (production calls real `evaluate_ta_signals`)
- **Strike 6010** — correct XSP notation (SPX-index-point strikes), not "SPY strike used as XSP strike"

---

## Ranked patch backlog

### P0 (before trusting paper soak metrics)
1. Fix upper-BB PnL gate
2. Vendored `macro_regime.py` fallback when Redis null
3. Remove/demote `prior_day_spy_positive` or make config-driven
4. Fix test log isolation
5. Add slippage + commission to paper PnL
6. Optional: relax confirm timeframe (config flag)

### P1 (before live flip)
7. Conductor shadow reviewer on entries
8. Full Cemini RH adapter port
9. Ingest XSP wiki concepts locally (librarian dead)
10. SMB K79 blow-up flags as halt conditions
11. Systemd weekday filters + yfinance retry

### P2
12. vol_monitor for strike sizing
13. cycle_detector for doom loops
14. Separate Lane B RH poll

---

## Soak plan (minimum before live)

| Phase | Duration | Gate |
|---|---|---|
| P0 fixes merged | — | 33+ tests; no test pollution of prod logs |
| Realistic paper | 4 weeks | Real TA snapshots in log (primary/confirm bars populated); slippage on |
| Shadow RH poll | 2 weeks | `XSP_LANE_A_RH_POLL=true`, orders still paper |
| Conductor shadow | 2 weeks | Every entry gets review artifact |
| Live flip | 8+ weeks total | Positive expectancy on corrected paper PnL; operator sign-off |

---

## Artifacts

| Item | Path |
|---|---|
| Prompt | `/opt/xsp-killer/prompts/xsp_killer_super_audit.md` |
| Pack builder | `/opt/xsp-killer/scripts/build_xsp_killer_super_audit_pack.py` |
| API runner | `/opt/xsp-killer/scripts/run_xsp_killer_super_audit_api.py` |
| Pack | `/opt/xsp-killer/reports/gap-audit/pack-xsp-killer/` |
| Grok report | `/opt/xsp-killer/reports/gap-audit/premium-xsp-killer/grok-4.3-openrouter_20260616T1303Z.md` |
| DeepSeek report | `/opt/xsp-killer/reports/gap-audit/premium-xsp-killer/deepseek-reasoner_20260616T1303Z.md` |
| Fusion | Failed — empty JSON body at ~260k prompt size; retry after pack slimming |

---

## Questions blocking live flip

1. Confirm RH `chain_symbol` for mini-SPX (`XSP` vs `SPX`) on operator account
2. Empirical SPY-proxy vs RH XSP mark ratio (10 samples, same expiry/DTE)
3. Operator confirmation: mentor dump-bounce overrides `prior_day_spy_positive` gate
4. Options approval level on RH account for XSP
