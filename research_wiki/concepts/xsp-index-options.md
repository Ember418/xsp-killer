---
title: XSP index options (Mini-SPX)
type: concept
tags: [concept, xsp, options, spx, index]
related:
  - concepts/xsp-spy-chain-proxy.md
  - concepts/xsp-premium-scale.md
  - concepts/xsp-lane-a-overnight-swing.md
maturity: validated
created: 2026-06-29
updated: 2026-06-29
---

## Relations

- @concepts/xsp-spy-chain-proxy.md — paper bot quotes SPY chain; strike mapping rules live there.
- @entities/tickers/spy.md — underlying proxy for TA and chain mids until RH XSP poll is live.
- XSP Killer repo: `/opt/xsp-killer` — standalone paper soak (Lane A overnight swing, Lane B LEAPS hedge alerts).

## Narrative

**XSP** (Mini-SPX, CBOE) is a **1/10th notional** version of SPX index options. Contract multiplier is **$1 per index point** (SPX is $100/point). Strikes are quoted in **SPX index points** — e.g. SPY ~747 → XSP ATM near **7500**, one OTM step **7505** (5-point strike grid).

Robinhood lists XSP under index options; ticker notation in ops briefs is often `XSP` with strikes like `7500C` (not SPY's ~750 strike scale).

### Why XSP vs SPY for the mentor playbook

| Aspect | XSP | SPY |
|--------|-----|-----|
| Underlying | SPX index (cash-settled) | ETF shares |
| Strike notation | Index points (7500) | Share price (~750) |
| Multiplier | $1/point | 100 shares |
| Overnight gap risk | Index open vs prior close | ETF open + dividends |

Lane A holds **overnight long calls** (close → next morning). Index product matches mentor's SPX-style swing framing; paper bot uses SPY chain as a **liquidity proxy** until live RH XSP marks validate economics.

### Live flip prerequisites (not paper)

1. RH XSP chain poll (`XSP_LANE_A_RH_POLL=true`) shadow period before any order path.
2. Confirm **7500 vs 7505** half-step marks differ on RH (SPY proxy can collapse adjacent strikes — see proxy concept).
3. Validate **premium scale** (10× config vs 1× RH mids) on ≥10 paired samples.

## Ops

- Production rules: `config/lane_a_rules.yaml`
- Variant soak: `config/lane_a_variants.yaml` + scoreboard `briefs/xsp-lane-a-variants-scoreboard.json`
- Code: `xsp_killer/lane_a_entry.py`, `lane_a_monitor.py`

## Snippets

- Strike step for OTM-one variant: `atm + 5.0` index points (one XSP strike increment).
- Paper mode only — no broker orders from XSP Killer timers today.
