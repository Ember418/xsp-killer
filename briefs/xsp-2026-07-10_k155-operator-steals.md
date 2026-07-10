## Target

CeminiSuite — XSP killer bot (Robinhood long-call lanes A/B).

## Summary

K155 **operator steals** — consolidated checklist from Capital Flows (SOFR conviction framework) and Macro Charts (USDJPY / CPI / sentiment) livestreams. Log-only Phase 0: enriches Lane A monitor JSON; does **not** change GREEN/YELLOW/RED gate logic.

## Pre-Lane-A operator checklist

### Macro weather & rates (Capital Flows)

1. **SOFR curve read** — price-of-money anchor alongside macro weather GREEN/YELLOW; note cross-asset confirms (CADJPY/oil, Z6→ZN→ES).
2. **Conviction journal** — record evidence count + cross-asset confirms; **block size-up** when pro/con lists are balanced without sufficient conviction.
3. **July FOMC / CPI cluster** — align ZN/ES path assumptions with Z6 floor narrative before Lane A overnight adds.
4. **CME single-stock futures (Jul 27)** — overnight hedge flows for ORCL-type mega-cap earnings if xsp book overlaps.

### FX, events & sentiment (Macro Charts)

5. **USDJPY 162.25–50** — log in macro weather snapshot; yen-strength regime input for Lane B international context.
6. **CPI Tue 2026-07-15** — tighten Lane A overnight size into print; gold/GDX levels per upcoming MC report.
7. **SOX / KOSPI** — watch MC target-range short trigger; do not front-run without range hit.
8. **Fundsmith 51% H1 turnover** — sentiment extreme note only; no auto-trade.

## Config & code

- `config/k155_operator_notes.yaml` — static operator notes
- `xsp_killer/macro_weather_notes.py` — `load_k155_notes`, `build_macro_weather_extras`, `conviction_journal_fields`
- `xsp_killer/lane_a_monitor.py` — attaches `macro_weather_extras` to monitor JSON (log-only)
- `scripts/adopt_k155_ops_phase0.sh` — Phase 0 adoption manifest

## Split briefs (Jul 10 13:17 UTC)

- `briefs/2026-07-10_xsp-sofr-conviction-pre-lane-a-checklist.md` — SOFR + conviction journal (P0 ops, no prod code)
- `briefs/2026-07-10_xsp-macro-weather-usdjpy-cpi-operator.md` — USDJPY/CPI/sentiment overlay (P0 ops, no prod code)

## Sources

- `briefs/xsp-2026-07-10_capital-flows-sofr-conviction-framework-steal.md` (via `/opt/cemini/briefs/`)
- `briefs/xsp-2026-07-10_macro-charts-jpy-gold-cpi-steal.md` (via `/opt/cemini/briefs/`)
