# XSP Killer SUPER AUDIT v8 — multi-model cursor-audit (operator 45–60 DTE stagger)

You are auditor **{{MODEL_SLOT}}** in a **deep super audit** for the operator's **XSP Killer** project.

**Mode:** `brief-plan` · **Readonly** — markdown report only · **Accuracy over brevity**

**Pattern:** OSINT wiki `/super-audit` skill — independent auditors, same pack, cross-check disagreements.

**Prior rounds:** `briefs/2026-07-07_xsp-killer-super-audit-synthesis-v7.md` (v7 panel; P0 fixes landed in `ac6540d`).

**This round evaluates TODAY'S ADDS (2026-07-09, commit `e6bb155`):** the operator's **live Robinhood target profile** — staggered **45/50/55/60 DTE one-strike OTM** dip-swing variants at **2 contracts**, with raised live/RH caps (`max_loss_usd: 1200`, `max_contracts_per_order: 2`).

**Operator reference position (manual RH screenshot):** XSP **760 Call**, **+2** @ ~$11.85, underlying ~754, bought 7/7, exp ~8/31 (~55 DTE), breakeven ~772, +21% total / +28% day. The bot should aim for this profile — **not a fixed 55 DTE every time**, but **stagger across 45–60 DTE** and pick the best bucket from soak.

**Updated thesis:** On dips, buy **one-strike OTM XSP calls** with **~6–8 week runway**, **2-lot**, hold for multi-day recovery; sell into strength (+40% option target) or cut (−50%).

---

## Today's adds — PRIMARY AUDIT TARGET (`e6bb155`)

1. **Four operator-target variants** in `config/lane_a_variants.yaml`:
   - `v2_dip_swing_{45,50,55,60}dte_otm` — `dte_pick: target`, `strike_pick: otm_one`, `quantity: 2`, `max_open_positions: 1` each
   - Shared: `DIP_BOUNCE`, `bb_bounce` + VWAP reclaim, `swing_hold`, TP +40% / SL −50%, `max_hold_dte: 2`
2. **Live cap raise** — `lane_a_rules.yaml` `max_loss_usd: 1200` (2-lot × ~$12 × 50% SL)
3. **RH MCP cap** — `rh_mcp.yaml` `max_contracts_per_order: 2`
4. **Test** — `test_merged_rules_operator_target_dte_stagger`

---

## Re-validate v7 P0 fixes (`ac6540d`) — did they stick?

| v7 P0 | Fix claimed | Re-verify |
|-------|-------------|-----------|
| Mark-sanity guards inside TP/SL | widened to +90%/-80%; SL fires on stale | Still measurable for +40/-50? |
| Live fires all variants | `XSP_LANE_A_LIVE_VARIANT_ID` allowlist | Still fail-closed? |
| Live selector ≠ paper | `dte_target` / `otm_one` parity | Do 45–60 OTM variants match live path? |
| premium_scale 10× | dual-log 1× approx on scoreboard | Is $ PnL trustworthy for $1k? |
| $1k sizing = buying power only | max_loss / max_cost_frac gates | Does 2-lot ~$2.4k cost pass/fail correctly? |
| DIP_BOUNCE falling knife | VIX-spike veto | Still blocks on spike? |
| Never-exit on stale mark | SL/time-stop on clamped mark | Swing-hold 45–60 DTE safe? |

---

## Mission (five phases — all required)

### Phase A — Cemini harvest + OSINT wiki
1. What from **Cemini** still needed for **45–60 DTE OTM 2-lot** swings?
2. **OSINT wiki** — does longer-DTE OTM dip-buy match mean-reversion evidence? Theta at 45–60 vs 14 DTE?
3. Ranked steal list (S/M/L).

### Phase B — Bot audit (today's adds + v7 regression)
1. **45–60 DTE stagger grid** — does `dte_pick: target` pick nearest listed expiry correctly for each bucket? Any collision (same expiry for 50 vs 55)?
2. **OTM one-strike** — does paper `pick_strike(otm_one)` and live `select_entry_contract` produce strikes like **760C @ 754** (~one $5 step)?
3. **2-lot sizing** — paper economics, live reviewer, buying-power, `max_loss_usd: 1200` — can a 2× ~$12 contract trade actually pass all gates on a **$1k** account (note: manual position may be on a larger account)?
4. **Account sizing mismatch** — operator screenshot implies ~$2.4k deployed; is $1k still the right live cap or should ops doc say ~$3k?
5. **v7 P0 regression** — any reopen?

### Phase C — Dip-swing cluster harvest (now **11** dip variants incl. 4 new)
1. Does `dip_swing_cluster` include the 4 new members? Leader gate still ≥20 sessions **and** ≥20 trades + Wilson LB?
2. **DTE stagger attribution** — can the grid rank **which DTE bucket** (45/50/55/60) wins without confounding OTM vs DTE (older 21dte_otm still active)?
3. **Promotion path** — what must clear before `XSP_LANE_A_LIVE_VARIANT_ID=v2_dip_swing_55dte_otm` (or whichever wins)?
4. **Sample time** — dips are rare; estimate time-to-rank for 4 new buckets.

### Phase D — Strategy math (operator profile)
1. **45 vs 50 vs 55 vs 60 DTE OTM** — theta/day, gamma, breakeven SPX move for +40% option gain on **one-strike OTM** call.
2. Compare to operator's **760C @ 754, ~55 DTE** — which stagger bucket best matches?
3. **2-lot economics** — EV with 2× premium at risk; breakeven win rate unchanged but tail risk doubles.
4. Is **OTM + long DTE** closer to +EV than the old 14-DTE ATM flagship?

### Phase E — Efficiency & observability
1. Cron/load with **4 more intraday variants** (22 active total? verify pack).
2. Scoreboard gaps for comparing DTE buckets side-by-side.
3. Tuning priorities for operator-profile promotion.

---

## Deployment posture (verify from pack)

| Item | Expected |
|------|----------|
| Repo | `/opt/xsp-killer` · HEAD `e6bb155` or later |
| New variants | `v2_dip_swing_{45,50,55,60}dte_otm` active |
| Dip cluster | 11 dip-swing members (7 legacy + 4 operator) |
| Live caps | `max_loss_usd: 1200`, `max_contracts_per_order: 2` |
| Live | `LIVE_ENTRIES=false` until single variant promoted |

---

## Data pack (READ ALL)

```
{pack_index}
```

---

## Required output format

Title line: `# cursor-audit · {{MODEL_SLOT}} · xsp-killer · SUPER AUDIT v8`

### Executive verdict
One line each: **OPERATIONAL / WARN / FAIL** for (1) paper soak (2) live RH flip (3) operator DTE stagger harvest (4) **is 45–60 DTE OTM 2-lot thesis +EV / promotable?**

### Phase A — Cemini steal matrix + wiki gaps

### Phase B — Logic & ops findings (today's adds + v7 regression)

### Phase C — DTE stagger cluster readiness
**Promotion recommendation:** WAIT / PROMOTE / TUNE — which DTE bucket if any?

### Phase D — Strategy math (45/50/55/60 OTM, 2-lot)

### Phase E — Tuning backlog

### Cross-auditor disagreement hooks (2–3)

### Ranked patch backlog P0/P1/P2

---

## Rules
- Cite evidence: path, JSON field, log line, commit
- Distinguish paper / shadow / live
- **Do NOT sum PnL across variants**
- Judge **harvest path + math + v7 regression**, not just closed-trade count
- Be thorough — accuracy over brevity
