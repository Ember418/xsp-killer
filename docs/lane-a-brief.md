# XSP Lane A — Mentor Playbook v2

## Entry (automated at close)
- **When:** 15:45–16:00 ET, Mon–Fri
- **DTE:** ≥14 days (2 weeks minimum)
- **Strike:** Cheapest premium among near-ATM strikes (±5 SPX points)
- **Regime:** GREEN required (macro_regime fallback when Redis intel absent)
- **No BB gate** at entry — mentor: hardest part is timing; automate buy at close

## Exit (sell into premarket spike, by 09:30 ET)
- **Sell window:** 08:00–09:30 ET (indexes often spike here — sell when exit conditions met)
- **No-sell zone:** before 08:00 ET only
- **Stop loss:** −20% from entry mid
- **Take profit:** +20% only when upper Bollinger band touched or rejection signal
- **Time stop:** 09:30 ET if neither SL nor TP fired
- **Patience:** If +20% but no upper BB touch → hold (wait for real run)
- **Inherited by all shadow variants** via `lane_a_rules.yaml` deep-merge

## Paper economics
- Slippage: 1.5% of premium
- Commission: $0.65/contract (entry + exit)

## Logic version
`xsp_lane_a_v2`
