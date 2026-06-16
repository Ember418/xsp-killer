---
title: XSP Lane A — overnight swing exit monitor (Robinhood prod, HL shadow)
type: brief
tags: [brief, cemini-prod, xsp, options, robinhood, lane-a, k116]
created: 2026-06-14
updated: 2026-06-14
---

## Target

CeminiSuite (`cemini-prod`)

## Summary

Operator discretionary **XSP long-call overnight swing** lane (Lane A). **Phase 1 ships exit automation only** on Robinhood: morning cut window, hard max-loss, regime gate for new risk. Hyperliquid **SP500 perp** is a **timing shadow lab only** — HL has no XSP/options; do not treat perp PnL as XSP validation. Entries remain manual or confirm-card until 20+ logged cycles pass exit replay.

## Body

### Strategy scope (Lane A only)

| Field | v1 default | Operator override |
|-------|------------|-------------------|
| Instrument | **XSP** (Mini-SPX calls, CBOE) | RH chain; 1/10 SPX notional |
| Direction | Long calls only | No puts in v1 |
| Tenor | Non-January; **DTE 14–60** | Exclude weeklies (Lane D) and LEAPS >180d (Lane B) |
| Thesis | Overnight hold for 1–2 session bullish continuance | Human entry reason required in log |
| Venue (prod) | **Robinhood** options | `core/ems/adapters/robinhood.py` |
| Venue (shadow) | **Hyperliquid SP500 perp** (HIP-3 / trade.xyz) | Timing rules only; not options PnL |

**Out of v1:** Lane B LEAPS accumulation, Lane C mid-dated 10:30 rule as primary sleeve, Lane D weeklies, auto-entry without confirm.

### Operator rules to codify (exit-first)

```yaml
# xsp_lane_a_rules.yaml (proposed prod path: /opt/cemini/config/xsp_lane_a_rules.yaml)
lane: A
instrument: XSP
asset_class: option
option_type: call

entry:
  manual_or_confirm: true
  regime_gate: GREEN          # intel:playbook_snapshot — SPY GREEN only for NEW risk
  dte_min: 14
  dte_max: 60
  exclude_expiry_month: [01]  # January LEAPS lane — not Lane A

exit:
  hard_max_loss_usd_per_contract: 75
  morning_eval_start_et: "09:30"
  morning_cut_deadline_et: "10:30"   # no discretionary hold of red past this on Lane A
  rth_open_cut_minutes: 30         # if still red at open+30m → CLOSE
  premarket_futures_red_pct: null    # optional v1.1 — ES/SPX fut -X% → alert

logging:
  logic_version: xsp_lane_a_v1
  required_fields: [lane, entry_ts, dte, strike, delta_at_entry, exit_reason, pnl_usd]
```

Exit reasons enum: `morning_cut`, `max_loss`, `open_plus_30_red`, `manual`, `target_hit`.

### Hyperliquid — shadow only (verify before wiring)

HL lists **SP500 perpetual** (licensed S&P 500 HIP-3 perp). It does **not** list XSP/SPX options.

| Use HL for | Do not use HL for |
|------------|-------------------|
| Rehearse overnight-long → morning-cut **clock discipline** | Validating theta / asymmetric drawdown thesis |
| Small size, low leverage (2–5×), USDC margin | Production XSP execution |
| Compare "would rule have fired?" vs RH options log | LEAPS or multi-week hold tests |

Before shadow: `get_stream_health` / HL meta — confirm `SP500` (or current trade.xyz slug) market active on prod stack.

### Implementation phases (server-Claude)

**Phase 0 — Read-only (ship first)**

1. Poll RH open **option** positions where `chain_symbol` ∈ {`SPX`, `XSP`} (confirm RH symbol for mini-SPX).
2. Classify Lane A: call + DTE 14–60 + tag `lane=A` in local state file (not in RH API).
3. Cron **09:35 / 09:45 / 10:00 / 10:30 ET**: compute mark PnL; emit alert (Slack/log/Redis `intel:xsp_lane_a_alert`) — **no auto-close**.

**Phase 1 — Auto-exit (after 10 paper alerts match operator intent)**

1. Wire `RobinhoodAdapter._execute_option_order` close path for tagged Lane A positions only.
2. Kill switch + `risk_governor` max daily options loss cap.
3. Bump `strategy_logic_versions.py`: `xsp_lane_a_v1`.
4. EMS: options close must use option orders API (`get_all_option_orders` idempotency — existing R7 pattern).

**Phase 2 — HL shadow monitor (optional parallel)**

1. Mirror clock rules on tiny SP500 perp long opened manually or via HL adapter.
2. Log divergence: RH option PnL vs HL perp PnL same window — expect **no** 1:1 match.

**Phase 3 — Semi-auto entry (later)**

- GREEN + prior-day SPX strength → propose single XSP call; human confirm card. Not in this brief.

### Prod files to add / touch

| Path | Action |
|------|--------|
| `config/xsp_lane_a_rules.yaml` | New — rules above |
| `xsp_killer/lane_a_monitor.py` | New — position classify + exit evaluator |
| `scripts/xsp_lane_a_cron.sh` | New — ET schedule wrapper |
| `core/ems/adapters/robinhood.py` | Extend — close-by-position-id, XSP chain match |
| `cemini_contracts/strategy_logic_versions.py` | Add `xsp_lane_a_v1` |
| `docker/compose.*` | Optional timer service; prefer systemd timer on host if lighter |

### Gates before live auto-close

| Gate | Requirement |
|------|-------------|
| Regime | Read `intel:playbook_snapshot`; block **new** entries if YELLOW/RED |
| Replay | 10 historical trades: rules would have improved or matched operator |
| Shadow | 5 sessions alerts-only; operator confirms no false fires |
| Versioning | All closes tagged `logic_version=xsp_lane_a_v1` |
| Reconciliation | RH option fill poll ≥ every 30s when position open |

### Wiki / OSINT handoff (laptop — not blocking prod Phase 0)

Canonical concept pages: `@wiki/concepts/xsp-lane-trading-framework.md`, `@wiki/concepts/xsp-hedge-fund-core-book-thesis.md`. SMB wiki covers **XSP put credit** (selling) — orthogonal to this **long-call** operator playbook.

### Do not

- Route Lane A through LangGraph brain or `brain_playbook_v2` equity fair-value path.
- Use Alpaca for XSP (equities-first; index options on RH).
- Promote HL perp results as XSP edge evidence.
- Auto-enter LEAPS (Lane B) while testing A — B needs weeks per cycle.

## Sources

[Source: operator Discord #stonks-yapping — XSP four-lane playbook, 2026-06-14]
[Source: Cboe XSP product spec — Mini-SPX 1/10 SPX, European exercise (retrieved 2026-06-14)]
[Source: S&P DJI / trade.xyz — SP500 HIP-3 perp on Hyperliquid, not options (2026-03-18)]
[Source: @wiki/concepts/xsp-lane-trading-framework.md — four-lane operator map]
[Source: @wiki/concepts/xsp-hedge-fund-core-book-thesis.md — institutional core book; Lane B weight]
[Source: @wiki/concepts/xsp-put-credit-spread-small-account-smb.md — XSP sizing reference only]
[Source: CeminiSuite ROADMAP — Robinhood options put fix Step 182; `robinhood.py` option order path]
