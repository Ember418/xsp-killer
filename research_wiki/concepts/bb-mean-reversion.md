---
title: Bollinger-band mean reversion (bounce base rates)
type: concept
tags: [concept, bollinger, mean-reversion, base-rate, dip-swing, edge]
related:
  - concepts/xsp-lane-a-dip-swing.md
  - concepts/xsp-lane-a-regime-vol-gates.md
maturity: experimental
created: 2026-07-08
updated: 2026-07-08
---

## Relations

- @concepts/xsp-lane-a-dip-swing.md — the strategy this base rate underwrites; the `DIP_BOUNCE` entry buys a confirmed lower/mid BB bounce and holds for recovery.
- @concepts/xsp-lane-a-regime-vol-gates.md — the VIX-spike veto and RED-regime handling that condition when the base rate applies.
- Standalone bot: `/opt/xsp-killer` (paper-only soak).

## What this is

The dip-swing thesis rests on a single empirical claim: **after price tags the
lower Bollinger band and turns back up, the near-term forward return is
positive often enough to beat the option's TP/SL breakeven.** This note records
what we believe about that base rate and, crucially, what we have **not** yet
measured — so the strategy is not promoted on faith.

The bot does not yet compute this base rate from data. Until it does, treat the
numbers below as priors to be confirmed by the paper soak (`dip_swing_cluster`
scoreboard) and by a dedicated backtest.

## Why a bounce *can* have edge

- **Volatility clustering + short-horizon mean reversion.** Index ETFs (SPY/XSP)
  show weak but persistent 1–5 day mean reversion after stretched down-moves;
  the reversion is strongest when the down-move is an over-reaction rather than
  a regime change.
- **The bounce filter is the safety, not the dip.** Buying the lower band while
  price is still falling is a falling knife. Requiring a *confirmed* turn (BB
  bounce + VWAP reclaim) conditions entry on weakness that has already stopped,
  which is where the positive forward skew lives.

## Why the edge is fragile

- **Theta is one-sided.** A long call bleeds ~1.7–3.6%/day (30→14 DTE). Every
  flat day after entry pushes toward the −50% stop while the +40% hurdle
  widens. The bounce must pay off *quickly* (see dip-swing note: ≈ +0.5% SPX
  drift within ~5 days to flip +EV at 14 DTE).
- **Vega crush on recovery.** Dips buy elevated IV; the recovery deflates IV,
  an unmodeled headwind on a long option that partially offsets the delta gain.
- **Regime dependence.** The mean-reversion base rate is materially different in
  GREEN/YELLOW (positive drift) vs RED (bounces are often dead-cats inside a
  downtrend). `DIP_BOUNCE` deliberately stops checking regime, which is exactly
  why the VIX-spike veto and the live RED-regime veto exist as overlays.

## Breakeven the base rate must beat

For an all-or-nothing bracket, breakeven win rate = `SL / (TP + SL)`:

| TP / SL | Breakeven (pre-cost) | Note |
|---------|----------------------|------|
| +40 / −50 | 55.6% | flagship |
| +25 / −50 | 66.7% | strictly harder — avoid |
| +60 / −60 | 50.0% | lowest breakeven, more time in decay/vega |

Post-cost (slippage + commission) adds ~3–4 points. The scoreboard's
`breakeven_win_rate_pct` is computed per variant from its own TP/SL, and a
variant is only crowned `edge_confirmed` when its **Wilson lower-bound** win
rate clears that breakeven (small-n-honest — a lucky 5/5 does not qualify).

## Open questions (to resolve empirically)

1. **Unconditional base rate:** P(forward 1–5d return > 0 | lower-BB tag + turn),
   for SPY, 2015–present, split by regime.
2. **Conditional on VWAP reclaim:** does the reclaim filter actually lift the
   base rate, or just cut trade count? (`v2_dip_swing_14dte_loose` is the A/B.)
3. **Best hold horizon:** where does the reversion signal decay into noise —
   is it exhausted by day 3, or does the 14-day runway genuinely help?
4. **DTE interaction:** 14 DTE maximizes gamma/$1k-fit but pays the most theta;
   21–30 DTE trades runway for cost. The soak's DTE axis answers this once
   variants clear the sample gate.

## Bottom line

Mean reversion after a confirmed BB bounce is a *real but small* edge that is
roughly the same size as the theta it must overcome. Do not promote a variant
to live until its paper `edge_confirmed` is true (Wilson-LB win rate above
breakeven with ≥20 trades) — the win rate must clear ~60% net of costs.
