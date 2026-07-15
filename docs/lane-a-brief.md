# XSP Lane A — Mentor Playbook v2

## Entry (automated at close)
- **When:** 15:45–16:00 ET, Mon–Fri
- **DTE:** ≥14 days (2 weeks minimum)
- **Strike:** Cheapest premium among near-ATM strikes (±5 SPX points)
- **Regime:** GREEN required (macro_regime fallback when Redis intel absent)
- **No BB gate** at entry — mentor: hardest part is timing; automate buy at close

## Exit (anytime XSP session is open)
- **Session gate only:** Cboe XSP GTH (20:15–09:25), RTH (09:30–16:15), or Curb (16:15–17:00) ET
- **No clock sell / no-sell window** — if TP/SL/BB conditions hit while tradeable, sell
- **Stop loss:** −20% from entry mid
- **Take profit:** +20% only when upper Bollinger band touched or rejection signal
- **No daily morning time_stop** — exit on conditions, not the clock
- **Patience:** If +20% but no upper BB touch → hold (wait for real run)
- **Inherited by all shadow variants** via `lane_a_rules.yaml` deep-merge

## Paper economics
- Slippage: 1.5% of premium
- Commission: $0.65/contract (entry + exit)

## Logic version
`xsp_lane_a_v2`
