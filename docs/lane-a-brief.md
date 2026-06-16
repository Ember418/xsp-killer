# XSP Lane A — Mentor Playbook v2

## Entry (automated at close)
- **When:** 15:45–16:00 ET, Mon–Fri
- **DTE:** ≥14 days (2 weeks minimum)
- **Strike:** Cheapest premium among near-ATM strikes (±5 SPX points)
- **Regime:** GREEN required (macro_regime fallback when Redis intel absent)
- **No BB gate** at entry — mentor: hardest part is timing; automate buy at close

## Exit (automated by 10:00 ET)
- **Sell window:** 09:30–10:00 ET only
- **No-sell zone:** 08:30–09:30 ET (premarket/residual volume — do not sell)
- **Stop loss:** −20% from entry mid
- **Take profit:** +20% only when upper Bollinger band touched or rejection signal
- **Time stop:** 10:00 ET if neither SL nor TP fired
- **Patience:** If +20% but no upper BB touch → hold (wait for real run)

## Paper economics
- Slippage: 1.5% of premium
- Commission: $0.65/contract (entry + exit)

## Logic version
`xsp_lane_a_v2`
