---
title: XSP SPY chain proxy (quotes and marks)
type: concept
tags: [concept, xsp, spy, options, data-hazard]
related:
  - concepts/xsp-index-options.md
  - concepts/xsp-premium-scale.md
maturity: validated
created: 2026-06-29
updated: 2026-06-29
---

## Relations

- @concepts/xsp-index-options.md — strike notation (7500 vs 7505).
- K129 `data_hazards.py` in XSP Killer — documents proxy limits for auditors.

## Narrative

XSP Killer **does not** fetch CBOE XSP chains in paper mode. It proxies:

1. **TA / regime** — SPY OHLCV (yfinance) for Bollinger, VWAP, macro regime fraction.
2. **Option mids** — SPY call chain with strike mapping `xsp_strike / 10` → SPY strike (e.g. 7500 → 750.0).

### Half-step hazard (7500 vs 7505)

Adjacent XSP strikes map to SPY strikes **750.0** and **750.5**. Any code path that **`round()`s** SPY strike to integer **collapses** 7505 → 750, making ATM and one-step OTM quotes identical. Auditors flagged this as **P0 for live** — variant soak must show divergent marks for `v2_45dte_otm` vs ATM baseline before promotion.

**Mitigation in code:** prefer float SPY strikes through chain lookup; fallback premium path uses strike-aware OTM scaling.

### When proxy is acceptable

| Use | Proxy OK? | Notes |
|-----|-----------|-------|
| Relative PnL % (TP/SL) | Mostly | Depends on consistent mark source entry→exit |
| Absolute $ PnL leaderboard | Weak | Needs `premium_scale` + validated RH XSP |
| Strike selection (OTM-one) | Risky until half-step fix verified | Compare variant scoreboard entry marks |

### RH poll shadow mode

Set `XSP_LANE_A_RH_POLL=true` to log RH XSP quotes **without** placing orders. Compare jsonl `quotes` block vs SPY proxy on same session before live flip.

## Ops

- Entry quotes: `lane_a_entry.fetch_spy_call_quote`
- Monitor marks: `lane_a_monitor` (same proxy)
- Env: `XSP_LANE_A_RH_POLL`, `XSP_LANE_B_RH_POLL` (Lane B separate flag)

## Snippets

- Do **not** treat SPY-scaled mids as settlement truth for XSP notional sizing.
- Rebuild this page when first RH XSP shadow week completes.
