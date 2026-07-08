---
title: XSP Lane A dip-swing (multi-day hold, BB bounce)
type: concept
tags: [concept, xsp, lane-a, dip-swing, bollinger, swing, theta]
related:
  - concepts/xsp-lane-a-overnight-swing.md
  - concepts/xsp-lane-a-regime-vol-gates.md
  - concepts/xsp-lane-a-exit-precedence.md
  - concepts/xsp-index-options.md
maturity: experimental
created: 2026-07-07
updated: 2026-07-07
---

## Relations

- @concepts/xsp-lane-a-overnight-swing.md — the OLD morning-cut close-window strategy this supersedes for the dip-swing cluster.
- @concepts/xsp-lane-a-regime-vol-gates.md — `DIP_BOUNCE` regime gate bypasses the GREEN-only restriction.
- @concepts/xsp-lane-a-exit-precedence.md — TP / SL / time_stop precedence under `swing_hold`.
- Standalone bot: `/opt/xsp-killer` (systemd timers, paper-only).

## Narrative

The **dip-swing** cluster is the multi-day-hold evolution of Lane A. The
overnight-swing playbook (`xsp-lane-a-overnight-swing.md`) still describes the
OLD morning-cut strategy: enter near the close, hold overnight, time-stop out
next morning. The dip-swing variants instead buy an **intraday confirmed
bounce** and hold for **multi-day recovery**.

### Thesis

1. **Entry** — intraday `bb_bounce` mode: price taps the Bollinger lower / mid
   band, confirms a bounce, and reclaims VWAP (`require_vwap_reclaim: true`).
   Regime gate is `DIP_BOUNCE` (any regime) — the signal itself is the gate, not
   the GREEN/YELLOW overlay.
2. **Hold** — `swing_hold: true`; the position is carried across days rather
   than time-stopped at the next morning's deadline.
3. **Exits** — `take_profit_pct: 0.40` (+40%), `stop_loss_pct: 0.50` (−50%),
   `require_upper_bb_for_take_profit: false`. Near-expiry positions are cut at
   `max_hold_dte` so gamma/theta doesn't run away on a held contract.
4. **Paper economics** — commission + slippage from `lane_a_rules.yaml`, same
   as the rest of the soak.

### Variants (`config/lane_a_variants.yaml`, prefix `v2_dip_swing_*`)

- `v2_dip_swing_14dte` — ~14 DTE ATM, TP +40 / SL −50 (the gamma/$1k-fit point).
- `v2_dip_swing_21dte` / `v2_dip_swing_30dte` — more runway, less gamma, more
  theta to bleed.
- `v2_dip_swing_14dte_tp25` — fast scalp (+25% TP), higher turnover.
- `v2_dip_swing_14dte_tp60` — wider target (+60% TP).
- `v2_dip_swing_14dte_loose` — relaxed entry confirmation.
- `v2_dip_swing_21dte_otm` — OTM strike for cheaper gamma.

### Breakeven math (TP +40% / SL −50%)

- Pre-cost: `0.40·p − 0.50·(1−p) > 0` → `p > 0.50/0.90 ≈ 0.556` → **~55.6% win
  rate** to break even.
- Post-cost (commission + slippage + the bid/ask cross on a ~14 DTE ATM call):
  figure ~4–5% of premium per round trip, pushing the hurdle to **~60%**.
- Theta is a **one-sided drag** here: the position only loses to theta (no
  credit), and at ~14 DTE theta is roughly **~3.6%/day** of premium. A held
  position that doesn't recover quickly eats into the +40% target before any
  TP fires — which is why `max_hold_dte` exists as a near-expiry cut.

### DTE tradeoff

- **14 DTE** — best gamma per $1k of premium; the bounce translates fastest
  into option move, but theta burns hard and `max_hold_dte` bites sooner.
- **21–30 DTE** — more runway for the recovery to play out, softer theta/day,
  but weaker gamma (slower PnL response to the bounce) and a longer bleed if
  the bounce fails.

## Ops

```bash
python3 scripts/lane_a_variants.py entry|monitor|scoreboard
```

The dip-swing cluster is surfaced on the scoreboard as `dip_swing_cluster`
(ranked by `avg_pnl_per_trade_usd`, leader gated on `>=20 sessions and >=20
trades`). Intraday entries/monitors run on the offset
`xsp-killer-lane-a-intraday.timer` cadence (:02/:17/:32/:47) to avoid
colliding with the close-window entry (15:45) and morning monitor (10:00)
timers that share `variants_state.json`.

## Open questions

- **RED-regime safety** — `DIP_BOUNCE` ignores the GREEN/YELLOW/RED overlay. Is
  buying dips in RED (true trend-down) a bleed-out, or do bounce reversals
  still pay? Needs the RED slice of the soak to fill in.
- **Best DTE** — 14 (gamma/theta-fit) vs 21–30 (runway). No variant has cleared
  the tightened ≥20-trade gate yet.
- **Best TP/SL** — +40/−50 vs +25/−50 (scalp) vs +60/−50 (wide). The
  +40/−50 breakeven (~60% post-cost) is the bar to beat.

## Snippets

- Logic versions: `xsp_lane_a_v2_dip_swing_*`
- Regime gate: `DIP_BOUNCE` (signal-as-gate, not regime-overlay).
- Live RH execution: **not wired** — soak paper only.
