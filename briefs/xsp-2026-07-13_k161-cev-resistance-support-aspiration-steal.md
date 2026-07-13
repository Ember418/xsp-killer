## Target

CeminiSuite — XSP killer bot (Robinhood long-call lanes A/B).

## Summary

K161 **Steal (mental model)** from arXiv 2607.08531: resistance/support as hidden **aspiration levels** under **CEV** dynamics. Positive-drift regimes → optimal region is a **band** (two boundaries), not a one-sided GBM pivot. Elasticity shifts band geometry — do not treat static S/R lines as model-optimal when vol is level-dependent. **Log-only Phase 0**; does **not** change GREEN/YELLOW/RED gate logic. **No** integral-equation solver on prod.

## Operator checklist (Lane A overnight / Lane B LEAPS)

1. **Regime tag:** note whether overnight bias / index drift is positive or negative before hardening S/R alerts.
2. **Band thinking:** on positive-drift days, allow **interior** stop/take interest between lower and upper watch levels; do not force one-touch GBM logic.
3. **Elasticity awareness:** when spot moves into regimes where local vol sensitivity rises, **widen** watch bands; when beta-like sensitivity falls, bands may collapse toward GBM-style one-sided exits.
4. **No code port:** paper is free-boundary theory — update operator notes / playbook comments only.
5. **Pair with:** XSP lane trading framework + SOFR/macro gates already on prod (K155/K158).

## Out of scope

- Fitting CEV beta live from RH ticks
- Replacing proper-betting / conviction sizing (PM lane)
- Any integral solver or free-boundary numerics

## Config & code

- `config/k155_operator_notes.yaml` — `k161.cev_aspiration` section
- `xsp_killer/macro_weather_notes.py` — `load_k161_notes`, K161 passthrough in `build_monitor_macro_weather_extras`
- `xsp_killer/lane_a_monitor.py` — attaches `macro_weather_extras` to monitor JSON (log-only)
- `scripts/adopt_k161_xsp_ops_phase0.sh` — Phase 0 adoption manifest

## Sources

- `/opt/cemini/briefs/xsp-2026-07-13_k161-cev-resistance-support-aspiration-steal.md`
- `/opt/cemini/wiki/sources/arxiv-cev-resistance-support-prediction-2607.08531-2026-07-13.md`
- `/opt/cemini/wiki/concepts/cev-resistance-support-optimal-prediction.md`
