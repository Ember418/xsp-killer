# XSP Killer SUPER AUDIT — multi-model cursor-audit (5 auditors) (Cemini harvest + bot operational review)

You are auditor **{{MODEL_SLOT}}** in a **deep super audit** for the operator's **XSP Killer** project.

**Mode:** `brief-plan` · **Readonly** — markdown report only · **Accuracy over brevity**

**Stakes:** Operator wants XSP Killer (standalone repo) to become an **operational, profitable** XSP/SPX options swing bot. Cemini Financial Suite is the **donor codebase** — steal working infra, discard pivot cruft. Mentor playbook v2 (`xsp_lane_a_v2`): **buy at close** (15:45–16:00 ET), ≥14 DTE, **cheapest near-ATM strike**; **sell 09:30–10:00 ET** only (no sell 08:30–09:30); **20% stop / 20% take-profit** with **BB patience** (hold +20% until upper BB touched). LEAPS core book (Lane B) held ≥30 DTE.

---

## Mission (two phases — both required)

### Phase A — Cemini harvest for XSP Killer

Given Cemini modules, OSINT wiki excerpts, conductor, playbook, EMS, and prior audits in the pack:

1. What from **Cemini** should be **stolen/wired** into XSP Killer for operational + profitable trading?
2. Did we **fully mine OSINT wiki** for XSP/options/swing/BB/VWAP/prop-desk content? What's missing (librarian destroyed — note gaps)?
3. Can **Conductor** (reviewer, doom-loop, audit/fitness, MCP) improve XSP Killer safety or iteration?
4. Can **trading_playbook** (macro_regime GREEN/YELLOW/RED, signal_catalog, vol_monitor) replace or augment current regime/TA?
5. Can **wiki enforcement / lesson registry / orchestrator wiki context** improve entry quality?
6. Any **TradingView MCP**, **options_greeks**, **EMS Robinhood adapter**, **intel bus**, **Alpaca ingest**, **pattern_matcher** worth porting?

Deliver a **ranked steal list** with effort (S/M/L) and profit impact.

### Phase B — XSP Killer bot audit

Audit `/opt/xsp-killer` (and prod state in pack) for:

1. **Logic bugs** — entry/exit gates, BB/VWAP detection, DTE hold, morning cut, strike selection, SPY-vs-XSP proxy errors
2. **Operational blockers** — systemd, env, yfinance fragility, RH auth, Redis intel, paper vs live path
3. **Profitability blockers** — false signals, paper PnL lies, missing slippage/fees, wrong timeframe alignment, confirm-bar requirements
4. **Security / capital safety** — accidental live orders, missing position caps, regime bypass
5. **Test gaps** — what production paths are untested?

Deliver **verdict** OPERATIONAL / WARN / FAIL for paper soak and for live RH.

---

## Deployment posture (verify from pack)

| Item | Value |
|------|-------|
| XSP Killer repo | `/opt/xsp-killer` · GitHub `cemini23/xsp-killer` |
| Cemini donor | `/opt/cemini` (XSP code still duplicated there) |
| Lane A | BB/VWAP paper entry + intraday 15m RTH + close window 15:45–16:00 ET |
| Lane B | LEAPS hedge alerts only (08:00 ET) |
| RH poll | Off by default (`XSP_LANE_A_RH_POLL=false`) |
| Librarian/OSINT wiki | **Destroyed** — local `research_wiki/` on Cemini only; lazy kb_search dead |

---

## Known issues to VALIDATE (may be fixed or worse)

| Issue | Where to check |
|-------|----------------|
| SPY chain used as XSP proxy — strike/premium scale wrong? | `lane_a_entry.py`, paper log strike 7430 |
| `prior_day_spy_positive` gate vs mentor BB entry — conflict? | rules + entry_gates_ok |
| Both Cemini + xsp-killer timers ran during migration? | systemd section |
| `already_entered_today` blocks intraday BB after failed close window | entry_log |
| Upper BB exit on green only — misses breakeven exits? | evaluate_exit_alerts |
| Regime reads `intel:playbook_snapshot` — often null on standalone | intel.py |
| Confirm timeframe requires BOTH 1h+15m BB — too strict? | lane_a_ta.py |
| Lane B shares RH poll from Lane A — untested live | lane_b_monitor.py |
| No slippage/commission in paper PnL | paper logs |
| No conductor pre-trade review on entries | architecture gap |

---

## OSINT / wiki concepts to cross-check (pack excerpts)

- SMB Capital synthesis (K79) — tape, prop desk ops, options structures, blow-up flags
- SPY entity — liquidity, options chain, macro beta proxy
- Greeks / options PDE research — dense Greeks for hedging
- Kalshi Bollinger baseline paper — BB as null-result benchmark
- Cemini `macro_regime` — GREEN/YELLOW/RED already used partially
- Mentor Discord playbook (in lane briefs) — four lanes, LEAPS hold ≥1mo DTE

**Explicit question:** Were `@wiki/concepts/xsp-*` pages on librarian ever ingested locally? If not, flag as **OSINT gap**.

---

## Data pack (READ ALL)

```
{pack_index}
```

---

## Required output format

### Executive verdict
One line: **OPERATIONAL / WARN / FAIL** for (1) paper soak now (2) live RH flip

### Phase A — Cemini steal matrix
| Priority | Cemini asset | XSP Killer use | Effort | Profit impact | Risk if skipped |

### Phase A — OSINT wiki gap analysis
| Topic | In wiki? | In bot? | Gap | Recommended ingest |

### Phase A — Conductor / infra integration
| Component | Steal? | How | Blocker |

### Phase B — Logic & bug findings
| Severity | Component | Finding | Evidence (file:line or log) | Fix |

### Phase B — Profitability findings
| Severity | Finding | Evidence | Fix |

### Phase B — Operational / systemd / data pipeline
| Severity | Finding | Evidence | Fix |

### Phase B — Test & soak plan
Minimum tests + paper soak duration before live

### Ranked patch backlog
**P0** (blocks operation / lies about PnL) · **P1** (profitability) · **P2** (nice)

### Questions blocking live flip
Only genuine unknowns

---

## Rules

- Cite evidence: path, log line, brief JSON field — not vibes
- Distinguish **paper**, **shadow**, **live**
- Call out **SPY vs XSP vs SPX** proxy errors explicitly — this is a common failure mode
- If mentor playbook conflicts with coded rules, say which should win and why
- Prefer smallest patch that fixes root cause
- Be thorough — operator cares about accuracy, not token count
