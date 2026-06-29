# Lane A strategy diagnosis (2026-06-29)

## Post-patch fixes

| Issue | Fix | Code location |
|-------|-----|---------------|
| same-day `time_stop` | Only fire when `entry_date_et < today` and `now >= sell_deadline_et` | `lane_a_monitor.evaluate_exit_alerts` |
| half-step OTM strikes | `pick_strike` mode `otm_one` uses `atm + 5.0` (one XSP strike step) | `lane_a_entry.py` |
| fallback premium scale | `estimate_fallback_premium` scales OTM by `0.55–1.0` based on steps from ATM | `lane_a_entry.py` |
| prior-day SPY filter | `fetch_spy_ohlcv` returns prior-day close-to-close return; variants can require `prior_day_spy_positive: true` | `lane_a_entry.py` |

## What was going wrong (original issues)

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

## Regime gate experiment (yellow bounce axis)

Side-by-side comparison of baseline GREEN-only vs YELLOW bounce brackets.

| Variant | Regime gate | Yellow frac min | Track family |
|---------|-------------|-----------------|--------------|
| `v2_baseline_prod` | `GREEN` | N/A | `baseline_green` |
| `v2_yellow_mid_bounce` | `GREEN_OR_YELLOW_BOUNCE` | 0.50 | `yellow_bounce_frac_axis` |
| `v2_yellow_top_quartile_bounce` | `GREEN_OR_YELLOW_BOUNCE` | 0.75 | `yellow_bounce_frac_axis` |

**Metrics tracked per variant:**
- `regime_gate_comparison` — scoreboard section comparing baseline + both yellow variants
- `bb_bounce_signal_sessions` — sessions where BB bounce signal was present
- `bb_bounce_blocked_by_regime_sessions` — sessions where bounce was blocked by regime filter
- `vol_shadow_would_block_sessions` — shadow SPY RV gate would block (log-only, not enforcing)
- `vol_shadow_latest_spy_rv` / `vol_shadow_avg_spy_rv` — shadow vol telemetry on scoreboard rows

**Promotion policy:** WAIT until ≥20 post-epoch sessions per variant before considering production promotion.

## Soak gate

Compare `realized_pnl_usd` and win rate per variant after **≥20 sessions** before changing production baseline.

## Stale TA data behavior

When evaluation runs outside market hours (weekend, holiday) or when data feed is stale:
- `ta_snapshot.errors` includes `"stale primary bar (timestamp)"`
- `ta_snapshot.detail` shows `"stale primary TA data"`
- Entry is blocked by `in_window` / `in_rth` checks before TA freshness is evaluated
- This is expected behavior — do not enter on stale data
