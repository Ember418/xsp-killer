## Target

CeminiSuite — XSP killer bot (Robinhood long-call lanes A/B).

## Summary

K162 **Steal** from Macro Charts paid 2026-07-12: institutional/momentum **capitulation risk** in crowded semis; gold models turning up from capitulation; SOX relative weakness; long-yen hedge narrative. Do not chase SPMO-style concentrated semis momentum into Lane A overnight. **Log-only Phase 0**; does **not** change GREEN/YELLOW/RED gate logic. Pair with K161 CEV R/S mental model (no solvers).

## Operator checklist

1. **Regime gate:** treat crowded momentum/semis as elevated correlated-crash risk — tighten overnight hold criteria when SOX shows relative weakness / right-shoulder structure.
2. **Gold/metals:** sentiment-capitulation + model turn is supportive context for risk-off hedges — not a RH gold trade mandate.
3. **Yen:** note as FX hedge narrative only — Lane B LEAPS sizing unchanged unless operator adds FX sleeve.
4. **No chase:** do not chase SPMO-style concentrated semis momentum into Lane A overnight.
5. **No code:** update operator notes / playbook comments only.

## Config & code

- `config/k155_operator_notes.yaml` — `k162.sentiment_capitulation` section
- `xsp_killer/macro_weather_notes.py` — `load_k162_notes`, K162 passthrough in `build_monitor_macro_weather_extras`
- `xsp_killer/lane_a_monitor.py` — attaches `macro_weather_extras` to monitor JSON (log-only)
- `scripts/adopt_k162_xsp_ops_phase0.sh` — Phase 0 adoption manifest

## Sources

- `/opt/cemini/briefs/xsp-2026-07-13_k162-macro-charts-sentiment-capitulation-steal.md`
- `/opt/cemini/wiki/sources/macro-charts-paid-forward-2026-07-12-sentiment-capitulation.md`
- `/opt/cemini/wiki/concepts/macro-charts-regime-signals.md`
