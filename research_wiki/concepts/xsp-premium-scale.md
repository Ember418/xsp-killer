---
title: XSP premium scale (SPY mid → XSP notional)
type: concept
tags: [concept, xsp, paper-economics, data-hazard]
related:
  - concepts/xsp-spy-chain-proxy.md
  - concepts/xsp-index-options.md
maturity: experimental
created: 2026-06-29
updated: 2026-06-29
---

## Relations

- @concepts/xsp-spy-chain-proxy.md — raw mids come from SPY chain.
- `config/lane_a_rules.yaml` → `paper_economics.premium_scale` (default **10.0**).
- Code: `xsp_killer/paper_economics.py`, `load_premium_scale()`.

## Narrative

SPY option premiums are **per-share** (×100 for contract notional). XSP premiums are **per index point** ($1 multiplier). The bot applies a configurable **`premium_scale`** when converting SPY chain mids into XSP-style dollar premiums for paper PnL.

### Default and override

```yaml
paper_economics:
  premium_scale: 10.0  # SPY chain mid → XSP notional; dual-log 1× in quotes for validation
```

Override via env `XSP_LANE_A_PREMIUM_SCALE` (see `.env.example`).

### Dual 1× logging (Jun 2026)

Each entry jsonl row includes:

- `premium_scale_used` — active scale for economics
- `quotes.spy_mid_1x` — unscaled SPY mid for side-by-side validation

Auditors disputed whether 10× is correct vs ~1× at equivalent moneyness. **Treat absolute $ PnL as unvalidated** until RH XSP samples confirm scale.

### Fallback path

When chain fetch fails, `estimate_fallback_premium()` uses SPY-scale heuristics; economics still apply `premium_scale`. Do not compare fallback vs chain entries on raw $ without checking `data_hazards` flags in brief.

## Ops

- Soak compare: variant scoreboard `realized_pnl_usd` is scale-dependent — rank variants on **win rate / %** until scale validated.
- Before live: pull 10+ RH XSP vs SPY-proxy pairs at entry DTE/strike.

## Snippets

- Module constant `SPY_TO_XSP_PREMIUM_SCALE` kept for backward compatibility; prefer `load_premium_scale()`.
