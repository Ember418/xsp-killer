# Lane A strategy diagnosis (2026-06-18)

## What was going wrong

### P0 — same-day time_stop (fixed)
`evaluate_exit_alerts` fired `time_stop` whenever `now >= 10:00 ET` with **no check that entry was on a prior day**. A 3:45 PM entry was closed 23s later at −$202 (economics) despite only −0.3% underlying move.

**Fix:** `time_stop` only when `entry_date_et < today` and `now >= sell_deadline_et`.

### P1 — DTE always minimum (14)
`pick_expiration` sorted ascending and took the **shortest** eligible expiry. That maximizes gamma/theta — bad for overnight holds. Recent trades: 14 DTE, ~$61 premium, essentially ATM.

### P1 — strike selection
`cheapest_near_atm` scans ATM ±5 index points. Recent SPY ~747 → strike 7500 (ATM). Not clearly too far OTM or ITM; the bigger issue was **holding period never happened** due to time_stop bug.

### P1 — exit conjunction
Take-profit needs +20% **and** upper BB touch **and** morning window. Most exits will be `time_stop` or `stop_loss`. Variants test `require_upper_bb_for_take_profit: false`.

### P1 — prior-day filter off
`prior_day_spy_positive: false` — entries on red prior days (e.g. −1.37% SPY) still allowed.

## Variant soak (parallel shadows)

Config: `config/lane_a_variants.yaml`

| Variant | DTE | Strike | Exit tweaks |
|---------|-----|--------|-------------|
| `v2_28dte_atm` | target 28 | ATM only | no BB required for TP |
| `v2_45dte_otm` | target 45 | 1-step OTM | 25% SL / 15% TP |
| `v2_14dte_green_day` | min 14 | cheapest near ATM | prior-day SPY green required |
| `v2_60dte_atm` | max 60 | ATM only | 15% SL / 10% TP |

Production baseline unchanged (`lane_a_rules.yaml` + existing briefs).

**Run:**
```bash
python3 scripts/lane_a_variants.py entry    # after close (also in entry cron)
python3 scripts/lane_a_variants.py monitor  # morning (also in monitor cron)
python3 scripts/lane_a_variants.py scoreboard
```

Scoreboard: `briefs/xsp-lane-a-variants-scoreboard.json`

## Soak gate

Compare `realized_pnl_usd` and win rate per variant after **≥20 sessions** before changing production baseline.
