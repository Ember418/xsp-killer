## Target

CeminiSuite — XSP killer bot (Robinhood long-call lanes A/B).

## Summary

K158 **operator steals** — Capital Flows Jul 11 SOFR livestream: Z6 record OI, Jul 29 FOMC coin-flip (66/34 hold/hike), Z6/Z7 spread as daily front-end read, subdued rate vol → equities drift into CPI; Japan negative real 2y funding deficit. **Extends K155** (log-only Phase 0); does **not** change GREEN/YELLOW/RED gate logic.

## Pre-Lane-A operator checklist (K158 additions)

### SOFR front-end (Capital Flows Jul 11)

1. **Z6/Z7 and Z6/Z8 calendar spreads** — log levels in macro weather / conviction journal daily. Front-end repricing risk if disinflation + overtighten narrative wins (~6bp cuts on Z6/Z7 as of Jul 11).
2. **Jul 29 FOMC** — binary catalyst (66/34 hold/hike); tighten Lane A overnight size per K155 checklist until post-meeting.
3. **CPI next week** — Capital Flows skew: disinflation print → drift higher between catalysts; **do not front-run** without cross-asset confirms.

### Cross-asset overlays

4. **CME single-stock futures (Jul 27)** — overnight hedge flow risk on NVDA, MSFT, ORCL, PLTR mega-cap earnings windows overlapping XSP book.
5. **Japan yen** — negative real short-end funding overlay input; complements K155 USDJPY 162.25–50 zone.

## K155 baseline (unchanged)

- SOFR curve conviction journal, USDJPY zone, CPI 2026-07-15 overnight posture, Fundsmith sentiment, SOX/KOSPI watch — see `briefs/xsp-2026-07-10_k155-operator-steals.md`.

## Config & code

- `config/k155_operator_notes.yaml` — K155 baseline + `k158` section (SOFR front-end, FOMC Jul 29, CPI skew, Japan yen; CME SSF tickers extended)
- `xsp_killer/macro_weather_notes.py` — `load_k158_notes`, K158 passthrough in `build_monitor_macro_weather_extras`
- `xsp_killer/lane_a_monitor.py` — attaches `macro_weather_extras` to monitor JSON (log-only)
- `scripts/adopt_k158_xsp_ops_phase0.sh` — Phase 0 adoption manifest

## Sources

- `/opt/cemini/briefs/xsp-2026-07-11_capital-flows-sofr-front-end-operator-steal.md`
- `briefs/xsp-2026-07-10_k155-operator-steals.md` (K155 baseline)
