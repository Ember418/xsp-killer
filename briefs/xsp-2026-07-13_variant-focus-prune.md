# XSP Lane A variant focus prune — 2026-07-13

Operator note: prune shadow capacity from 23 active toward ~12 keepers. Baseline prod is untouched.

## Baseline note

**`+679` is `v2_baseline_prod`** (paper Lane A), not a shadow. It stays on systemd / `lane_a_rules.yaml` and is not in the YAML keep/kill lists below. Still `low_sample` / `promotion_status: collecting` (6 entered sessions; gate is 10 entered / 20 sessions). Keep running as-is.

## Keep (~12) — concentrate sample

| Variant | Why |
|---|---|
| `v2_dip_swing_14dte` | Flagship dip thesis; 2W/0L |
| `v2_dip_swing_14dte_tp25` | TP lever vs flagship |
| `v2_dip_swing_14dte_tp60` | TP/SL lever |
| `v2_dip_swing_21dte` | DTE runway lever |
| `v2_dip_swing_21dte_otm` | Strike lever (best 1-trade avg so far) |
| `v2_dip_swing_14dte_spread` | Spread instrumentation (still naked call) |
| `v2_28dte_atm_stack3` | Best sample among winners (7 closes, +avg) |
| `v2_14dte_atm` | Strong short-DTE ATM (5 closes) |
| `v2_28dte_atm` | 28 DTE control |
| `v2_28dte_easy_tp` | Keep one exit-axis probe |
| `v2_yellow_mid_bounce` | Keep one yellow gate (5 closes, +avg) |
| `v2_28dte_green_day` | Keep one prior-day green filter (still +; low n) |

## Kill (`active: false`)

### Obvious / starved

| Variant | Why |
|---|---|
| `v2_14dte_green_day` | Only net-negative active (−$19 / −$6 avg) |
| `v2_dip_swing_45dte_otm` … `60dte_otm` | 0 entries / 64 evals each (starved; mirror Jul-7 long-DTE prune) |

### Near-duplicates (identical realized/avg/W-L — burning capacity)

| Variant | Why |
|---|---|
| `v2_dip_swing_14dte_loose` | Same book as `14dte` |
| `v2_dip_swing_30dte` | Thin; collapse DTE axis to 14 vs 21 for now |
| `v2_yellow_top_quartile_bounce` | Clone of mid |
| `v2_28dte_cheapest` | Clone of `28dte_atm` |
| `v2_28dte_wide_sl` | Clone of `easy_tp` |
| `v2_21dte_atm` | Below keep-set priority; 14 + 28 cover DTE axis |

## Guardrails

- Do **not** sum shadow PnL across variants.
- Wait for scoreboard `edge_confirmed` before treating rankings as reliable.
- No baseline promotion of any shadow yet — gates unmet.
- Open paper positions on pruned variants still monitor/exit via existing state; only **new** entries stop.
- Next review when any keep variant hits **≥10 entered sessions** or scoreboard `edge_confirmed`.
