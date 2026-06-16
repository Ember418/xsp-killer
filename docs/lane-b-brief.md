---
title: XSP Lane B — LEAPS core book inventory + put-hedge roll monitor (Robinhood prod)
type: brief
tags: [brief, cemini-prod, xsp, options, robinhood, lane-b, leaps, k116]
created: 2026-06-14
updated: 2026-06-14
---

## Target

CeminiSuite (`cemini-prod`)

## Summary

**Lane B** — the mentor **core book**: long-dated **XSP calls** (LEAPS, >180 DTE), accumulated manually on dips, hedged with **protective puts over time**. v1 ships **read-only inventory + hedge-gap alerts** on Robinhood; **no auto-buy** of calls or puts. Delta-adjusted risk-return scorecard for closed lots. Complements Lane A brief (`2026-06-14_xsp-lane-a-overnight-swing-monitor-cemini-prod.md`) — do not merge rule files.

## Body

### Strategy scope (Lane B only)

| Field | v1 default | Operator override |
|-------|------------|-------------------|
| Instrument | **XSP** long **calls** | RH chain; Mini-SPX |
| Tenor | **DTE > 180** (LEAPS) | January+ monthly expiries OK |
| Portfolio role | **Core sleeve** — mentor framing 30–50% options risk budget `[TENTATIVE]` | `core_sleeve_target_pct` in YAML |
| Entry | **Manual only** — dip accumulation ladder | Confirm-card v1.1 optional |
| Hedge | Long **protective puts** (separate legs), rolled over time | Not short put credit (SMB path) |
| Venue | **Robinhood** options | Same adapter as Lane A |
| Out of v1 | Auto LEAPS entry, collar auto-roll without confirm, Lane A/C/D rules |

### Thesis (wiki)

@wiki/concepts/xsp-hedge-fund-core-book-thesis.md — institutional long SPX/XSP call book + put hedge; delta-adjusted winners. @wiki/concepts/xsp-lane-trading-framework.md — lane separation.

### Operator rules YAML

```yaml
# /opt/cemini/config/xsp_lane_b_rules.yaml
lane: B
instrument: XSP
asset_class: option

calls:
  option_type: call
  dte_min: 180
  delta_target_min: 0.35
  delta_target_max: 0.55
  entry: manual_only
  regime_gate_new_lots: GREEN    # intel:playbook_snapshot
  dip_entry_rubric: null         # operator fills: e.g. -3% SPX from 20d high

hedge_puts:
  option_type: put
  direction: long                # protective — NOT short premium
  link_to: call_inventory        # by account + underlying
  roll_alert_triggers:
    call_delta_above: 0.65       # convexity high — review hedge strike
    portfolio_drawdown_pct: 8    # from lane-B mark-to-market peak
    hedge_dte_below: 45          # roll long puts before decay cliff
    regime_yellow: review        # alert only; no auto hedge
  roll_action: alert_only        # v1 — operator executes on RH

risk:
  max_lane_b_notional_pct: 50    # of options-approved account [TENTATIVE mentor]
  max_single_add_contracts: null # operator cap per dip
  kill_switch_daily_loss_usd: null

scorecard:
  metric: delta_adjusted_return  # PnL / (delta_at_entry * exposure_days)
  logic_version: xsp_lane_b_v1
  required_fields:
    - lane
    - leg_type          # call | hedge_put
    - entry_ts
    - exit_ts
    - dte_at_entry
    - delta_at_entry
    - contracts
    - pnl_usd
    - hedge_pair_id     # uuid linking call lot + put legs
```

### Position classification (prod)

Poll RH options positions; classify **Lane B call** when:

- `chain_symbol` ∈ {`XSP`, `SPX`} (confirm RH symbol)
- `option_type` = call
- `dte` > 180
- Local state `lane=B` tag (operator or ingest from `xsp_lane_b_state.json`)

Classify **hedge put** when:

- Same underlying, `option_type` = put, `quantity` > 0 (long)
- `hedge_pair_id` links to a Lane B call lot in state file

**Exclude** from Lane B: DTE 14–60 (Lane A), weeklies (Lane D), short puts / credit spreads.

### Hedge-gap alerts (Phase 0 — ship first)

Daily cron **08:00 ET** + on-demand after RH position poll:

| Alert code | Condition | Action |
|------------|-----------|--------|
| `B_HEDGE_MISSING` | Lane B call lots with no linked long put in state | Notify — new core lot unhedged |
| `B_HEDGE_DTE_LOW` | Linked put DTE < 45 | Notify — roll window |
| `B_CALL_DELTA_HIGH` | Call Δ > 0.65 (NBBO greeks or broker) | Notify — strike/hedge review |
| `B_DRAWDOWN` | Lane B MTM off trailing peak > 8% | Notify — add/tighten hedge |
| `B_REGIME_YELLOW` | `intel:playbook_snapshot` YELLOW + open Lane B | Notify — no new lots; review hedges |
| `B_SLEEVE_OVER` | Lane B notional > `max_lane_b_notional_pct` | Notify — size discipline |

Emit to Redis `intel:xsp_lane_b_alert` + structured log. **No orders in Phase 0.**

### Implementation phases (server-Claude)

**Phase 0 — Inventory + alerts (P0)**

1. `xsp_killer/lane_b_monitor.py` — classify calls/puts, compute gaps, scorecard on closed trades.
2. `config/xsp_lane_b_state.json` — operator-maintained `hedge_pair_id` links until RH API exposes strategy tags.
3. `scripts/xsp_lane_b_cron.sh` — 08:00 ET daily + hook after RH position sync.
4. Reuse RH options poll from Lane A monitor; share `robinhood.py` read path only.

**Phase 1 — Confirm-card hedge roll (P1, after 4 weeks Phase 0)**

1. On `B_HEDGE_DTE_LOW` or `B_HEDGE_MISSING`, surface **proposed put roll** (strike/DTE template from rules).
2. Human confirm → single-leg put buy/close via `RobinhoodAdapter._execute_option_order`.
3. Bump `strategy_logic_versions.py`: `xsp_lane_b_v1`.

**Phase 2 — Dip-entry propose (P2, later)**

1. GREEN + dip rubric hit → propose **one** LEAPS call add; human confirm only.
2. Gate: ≥20 logged Phase 0 alert cycles with no false `B_HEDGE_*` fires.

**Out of scope v1**

- LangGraph / brain analyst entries
- SMB put **credit** structures
- HL SP500 perp as Lane B validation
- Auto LEAPS accumulation without confirm

### Prod files

| Path | Action |
|------|--------|
| `config/xsp_lane_b_rules.yaml` | New |
| `config/xsp_lane_b_state.json` | New — hedge links (gitignored on prod) |
| `xsp_killer/lane_b_monitor.py` | New |
| `scripts/xsp_lane_b_cron.sh` | New |
| `xsp_killer/lane_a_monitor.py` | Share RH poll helper — do not duplicate |
| `cemini_contracts/strategy_logic_versions.py` | Add `xsp_lane_b_v1` at Phase 1 |

### Gates

| Gate | Requirement |
|------|-------------|
| Lane separation | A monitor must not close B positions (DTE classifier) |
| Phase 0 soak | 20 trading days alerts-only; operator sign-off |
| Hedge discipline | No Phase 1 until ≥1 manual hedge roll logged with `hedge_pair_id` |
| Scorecard | Closed trades export CSV with delta-adjusted metric |
| Regime | Block **new** call lots suggestion in YELLOW/RED (alerts still fire) |

### Coordination with Lane A

| | Lane A | Lane B |
|---|--------|--------|
| DTE | 14–60 | >180 |
| Automation focus | **Exits** (morning cut) | **Hedge maintenance** |
| Hold style | Overnight–2 sessions | Months–years |
| Prod brief | `…_lane-a-overnight-swing-…` | This file |

Run both monitors on same RH poll; single `risk_governor` options daily loss cap aggregates lanes.

### Do not

- Merge `xsp_lane_a_rules.yaml` and `xsp_lane_b_rules.yaml`
- Treat mentor 30–50% as auto-size — it's a **cap alert**, not a target order size
- Short puts for "hedge" (that's a different strategy)
- Delete LEAPS on RED regime without operator rule (hold thesis is patient)

## Sources

[Source: operator mentor narrative — HF long SPX LEAPS + put hedge, 2026-06-14]
[Source: @wiki/concepts/xsp-hedge-fund-core-book-thesis.md — core book thesis]
[Source: @wiki/concepts/xsp-lane-trading-framework.md — Lane B definition]
[Source: briefs/2026-06-14_xsp-lane-a-overnight-swing-monitor-cemini-prod.md — shared RH adapter; lane separation]
[Source: @wiki/concepts/xsp-put-credit-spread-small-account-smb.md — contrast: not short put credit]
[Source: CeminiSuite `core/ems/adapters/robinhood.py` — options order path]
