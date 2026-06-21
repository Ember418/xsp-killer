# XSP Killer SUPER AUDIT v3 — multi-model cursor-audit (Cemini harvest + bot + variant soak)

You are auditor **{{MODEL_SLOT}}** in a **deep super audit** for the operator's **XSP Killer** project.

**Mode:** `brief-plan` · **Readonly** — markdown report only · **Accuracy over brevity**

**Pattern:** OSINT wiki `/super-audit` skill — independent auditors, same pack, cross-check disagreements. Prior round: `briefs/2026-06-16_xsp-killer-super-audit-synthesis-v2.md` (post-P0 fixes). **This round evaluates progress since then**, including **13-variant shadow soak**, strategy math, and tuning efficiency.

**Stakes:** Operator wants XSP Killer to become an **operational, profitable** XSP/SPX overnight swing bot. Mentor playbook v2: **buy at close** (15:45–16:00 ET), DTE/strike per rules; **sell 09:30–10:00 ET**; **20% SL / 20% TP** (variants test alternatives). LEAPS core book (Lane B) is read-only hedge alerts.

---

## Mission (four phases — all required)

### Phase A — Cemini harvest for XSP Killer

Given Cemini modules, local OSINT wiki excerpts (`research_wiki/`), conductor, playbook, EMS, and prior audits in the pack:

1. What from **Cemini** should still be **stolen/wired** into XSP Killer?
2. Did we **fully mine local OSINT wiki** for XSP/options/swing/BB/VWAP/Greeks/prop-desk content? What's missing?
3. Can **Conductor**, **trading_playbook** macro_regime, **options_greeks/vol_monitor**, EMS RH adapter improve safety or edge?
4. Ranked **steal list** with effort (S/M/L) and profit impact.

### Phase B — XSP Killer bot audit (logic, ops, safety)

Audit `/opt/xsp-killer` for:

1. **Logic bugs** — entry/exit gates, BB/VWAP, DTE/strike pick modes, morning cut, time_stop entry-day guard, monitor DTE drop, SPY-vs-XSP proxy
2. **Operational blockers** — systemd, env, yfinance, RH auth, Redis intel, paper vs live
3. **Profitability blockers** — false signals, paper PnL trust, slippage/fees, timeframe alignment
4. **Security / capital safety** — accidental live orders, position caps, regime bypass
5. **Test gaps** — untested production paths

Deliver **verdict** OPERATIONAL / WARN / FAIL for (1) paper soak now (2) live RH flip.

### Phase C — Variant soak progress (NEW — critical)

Evaluate **13 active shadow variants** (`config/lane_a_variants.yaml`, scoreboard JSON, variant logs in pack):

1. **Progress vs gate** — need ≥20 post-fix sessions before promoting; how many do we have? Is data trustworthy after P0 time_stop + DTE monitor fixes?
2. **Cross-variant comparison** — which DTE/strike/exit/green-day params are **least bad**? Any variant with positive expectancy or better win rate?
3. **Green-day variants with 0 trades** — is prior-day SPY filter too strict or correctly blocking?
4. **Production baseline vs best variant** — should we change `lane_a_rules.yaml` now or wait?
5. **Variant infrastructure** — cron wiring, scoreboard accuracy, state isolation, RAM/runtime at 13 variants

### Phase D — Strategy mathematics & economics (NEW)

Analyze the **overnight long-call** thesis quantitatively:

1. **DTE / theta / gamma tradeoff** — why min-DTE (14) hurt; optimal DTE for overnight hold given mentor rules
2. **Strike selection math** — ATM vs OTM vs cheapest-near-ATM; delta/gamma exposure per $ premium
3. **Exit conjunction** — P(TP) vs P(time_stop) vs P(SL) given BB upper-band requirement; expected value of each exit path
4. **Premium scaling** — SPY→XSP 10× scale correctness; bid-ask slippage 1.5% adequacy
5. **Regime gating** — GREEN-only entries vs prior-day SPY filter; marginal value in backtest/soak evidence
6. **Sample size / significance** — is current soak statistically meaningful? Minimum trades for promotion?

### Phase E — Efficiency & tuning (NEW)

1. **Parameter tuning priorities** — ranked knobs (DTE target, strike_pick, TP/SL %, BB requirement, slippage, entry window)
2. **Compute efficiency** — 13 variants ~11s sequential; batching, shared chain fetch, caching opportunities
3. **Cron / timer alignment** — entry 15:45, monitor 09:35–10:00, intraday 15m; gaps or double-runs?
4. **Observability** — what metrics/dashboards would accelerate iteration?

---

## Deployment posture (verify from pack)

| Item | Value |
|------|-------|
| XSP Killer repo | `/opt/xsp-killer` · GitHub `cemini23/xsp-killer` |
| Lane A prod | `config/lane_a_rules.yaml` + systemd `xsp-killer-lane-a-*` |
| Lane A variants | 13 shadows · `scripts/lane_a_variants.py` · scoreboard JSON |
| Lane B | LEAPS hedge alerts only (08:00 ET) |
| RH poll | Off by default (`XSP_LANE_A_RH_POLL=false`) |
| OSINT wiki | Local `research_wiki/` only; remote librarian **destroyed** |

---

## Known issues — VALIDATE status (fixed vs open)

| Issue | Status to verify |
|-------|------------------|
| Same-day time_stop (entry closed seconds later) | Fixed — entry_date_et < today guard |
| Monitor drops position when DTE < entry dte_min | Fixed — `is_lane_a_monitor_contract()` |
| SPY premium without 10× XSP scale | Fixed — `SPY_TO_XSP_PREMIUM_SCALE` |
| Paper economics double-count | Fixed — entry_mid_premium |
| DTE always minimum (14) — high gamma | Variants test target/max DTE |
| TP requires +20% AND upper BB AND morning window | Variants test `require_upper_bb_for_take_profit: false` |
| prior_day_spy_positive off | Green-day variants test filter |
| All variants still negative PnL post-fix | **Validate from scoreboard** |
| No live RH execution | Open by design |
| No conductor / daily loss cap | Open for live flip |

---

## OSINT / wiki concepts to cross-check (pack excerpts)

- SMB Capital / prop desk ops (K79)
- SPY entity — liquidity, options chain, macro beta proxy
- Greeks research — delta/gamma for overnight holds
- trading_playbook macro_regime GREEN/YELLOW/RED
- K117 low-vol / regime gating (Cemini brief if in pack)
- Bollinger baseline — BB as signal vs null benchmark

**Explicit question:** Any `@wiki/concepts/xsp-*` content still missing locally?

---

## Data pack (READ ALL)

```
{pack_index}
```

---

## Required output format

### Executive verdict
One line each: **OPERATIONAL / WARN / FAIL** for (1) paper soak now (2) live RH flip (3) variant soak readiness (promote baseline?)

### Phase A — Cemini steal matrix
| Priority | Cemini asset | XSP Killer use | Effort | Profit impact | Risk if skipped |

### Phase A — OSINT wiki gap analysis
| Topic | In wiki? | In bot? | Gap | Recommended ingest |

### Phase B — Logic & bug findings
| Severity | Component | Finding | Evidence (file:line or log) | Fix |

### Phase B — Profitability findings
| Severity | Finding | Evidence | Fix |

### Phase C — Variant soak analysis
| Variant | Trades | Realized PnL | Win rate | Verdict | vs prod baseline |

**Promotion recommendation:** WAIT / PROMOTE variant X / TUNE parameter Y — with evidence

### Phase D — Strategy mathematics
| Topic | Analysis | Implication for rules |

Expected value sketch for baseline vs recommended variant (show assumptions)

### Phase E — Efficiency & tuning backlog
| Priority | Knob | Current | Recommended | Expected impact |

### Cross-auditor disagreement hooks
List 2–3 topics where reasonable auditors might disagree — state your position and why

### Ranked patch backlog
**P0** · **P1** · **P2**

### Questions blocking live flip

---

## Rules

- Cite evidence: path, log line, brief JSON field — not vibes
- Distinguish **paper**, **shadow variant**, **live**
- Call out **SPY vs XSP vs SPX** proxy errors explicitly
- **Discard pre-2026-06-16 14:18 UTC paper logs** for PnL conclusions
- If mentor playbook conflicts with coded rules, say which should win
- Be thorough — operator cares about accuracy, not token count
