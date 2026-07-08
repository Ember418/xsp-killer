# XSP Killer — SUPER AUDIT v7 Synthesis (dip-buy swing + live-entry path)

**Date:** 2026-07-07 / 2026-07-08 · **HEAD:** `d0cc157` · **Pack:** `reports/gap-audit/pack-xsp-killer-v7/`
**Scope:** today's adds (commits `07765bc`, `6be3fbc`, `d0cc157`) — DIP_BOUNCE gate, swing-hold exit, bb_bounce intraday entry, 7-variant dip grid, intraday execution + bar cache, `dip_swing_cluster` scoreboard, gated live-entry path for a **$1,000** account.

**Panel (6 auditors, same pack, independent):**
- **Cursor:** `claude-fable-5-thinking-max`, `glm-5.2-high`, `kimi-k2.7-code`, `gpt-5.5-medium`
- **OpenRouter:** `openrouter/fusion` (panel: grok-4.3 / glm-5.2 / gemini-2.5-pro / claude-sonnet-4), `x-ai/grok-4.3`

Reports: `reports/gap-audit/premium-xsp-killer-v7-cursor/*_AUDIT.md`, `reports/gap-audit/premium-xsp-killer-v7/*.md`.

> All 6 auditors complete. `claude-fable-5-thinking-max` (deepest pass) found a **new top-severity issue the other 5 missed**: the paper mark-sanity guards sit *inside* the strategy's own TP/SL targets, so the 7-variant grid **cannot measure its own thesis** (see P0 #0). This is now the single most important finding on the paper side.

---

## Executive verdict (panel consensus)

| # | Question | Verdict | Basis |
|---|----------|---------|-------|
| 1 | Paper soak | **INVALID until patched** | Harvest *path* verified live today (all 7 dip variants entered at 15:55 ET on a BB-mid bounce; 230 tests pass), but the *measurement* is broken: mark-sanity guards clamp at ±35/45% — inside the +40/60% TP and −50/60% SL — so the grid can't record its own TP/SL outcomes (P0 #0, fable). |
| 2 | Live RH flip ($1k) | **FAIL (unanimous)** | Multiple hard blockers — see P0. Do **not** set `XSP_LANE_A_LIVE_ENTRIES=true` today. |
| 3 | Dip-swing harvest readiness | **WARN** | `dip_swing_cluster` correct (7 members, leader gated on `low_sample`), but 0 closed trades and the ≥2-trades gate is far too loose; ~2.5–4 months to a trustworthy rank. |
| 4 | Is the thesis +EV / promotable? | **NOT YET PROVEN — marginal; WAIT** | Breakeven ≈ 55.6% pre-cost / ~60% post-cost for TP+40/SL−50; theta (~3.6%/day @14DTE) is a one-sided drag that ~consumes the bounce edge. Needs live data showing >60% win rate. |

---

## P0 — blockers

0. **The paper experiment can't measure its own thesis (fable — new; #1 paper-side blocker).** The exit mark-sanity guards in `spy_quote.py:139-146` clamp/flag `stale` at **+35%** (caps mark to +5%) and **−45%** (floors to −45%) — *inside* the grid's TP (+40/+60%) and SL (−50/−60%) targets. Because `evaluate_exit_alerts` early-returns on `mark_quote_stale` **before** SL/TP/near-expiry checks, **TP is unreachable for 6 of 7 variants (all but tp25) and SL is unreachable for all 7**. Losers ride to expiry and are reaped at `pnl=None` → scored as **$0**, which simultaneously breaks risk control *and* erases the worst losses from the scoreboard (survivorship bias makes the strategy look better than it is). *Fix:* widen the guards well past the strategy's own targets, and make risk exits (SL / time-stop / DTE-cut) fire on the **clamped** mark instead of early-returning on `stale`. This subsumes the "never-exit on stale mark" item below.

1. **Live entry is NOT isolated to one variant (biggest live blocker).** `_maybe_place_live_entry` is called from `run_paper_entry` for *every* variant, so flipping `XSP_LANE_A_LIVE_ENTRIES=true` fires buy-to-open across **all 18 variants + baseline** at once. `ref_id` is per `(instrument_id, day)` and does **not** dedupe across variants; the buying-power fail-safe reads the portfolio per-place, so 2–3 fills can land before it chokes → **over $1k committed**. *Fix:* single-variant dispatch (steal Cemini `conductor_dispatch`) + a `LIVE_VARIANT_ID` allowlist. (glm, corroborated by gpt/kimi)

2. **Live RH selector does not match the paper variants.** `select_entry_contract` never receives `dte_target` and picks `dated[-1]` (max DTE) for `dte_pick="target"`, and treats anything but `cheapest_near_atm` as nearest-ATM — so `otm_one` is lost. Paper can crown a 21/30-DTE or OTM winner the live account would never actually trade. *Fix:* add `dte_target`/`otm_one` support + parity tests vs paper `pick_expiration`/`pick_strike`. (`robinhood_mcp.py:900-940`) (gpt)

3. **`premium_scale=10.0` inflates all dollar figures 10×.** Today's paper dip logged `entry_mid_premium=$63.25`; a real XSP call is ~$6–9. %-based TP/SL are scale-invariant (fine), but every reported `$ PnL` and every **dollar** risk gate is 10× wrong vs a $1k live account. *Fix:* `premium_scale=1.0` on the live path (dual-log), validated against a real RH/CBOE XSP chain. (glm, kimi)

4. **$1k sizing checks affordability, not risk.** The gate blocks only when `cost > buying_power`. One ATM 14-DTE XSP call ≈ **$700–880 (70–88% of the account)**; a −50% stop risks ~$400. 21/30-DTE (~$1,080 / $1,290) exceed the whole account and are silently skipped. *Fix:* add max-premium / max-loss / max-%-of-account gates before `buy_to_open`; treat 14-DTE as the only $1k-feasible live rung. (gpt, kimi, fusion)

5. **`DIP_BOUNCE` is a falling-knife path (unanimous).** Regime is fully bypassed; the only safety is a **single-bar** BB bounce with a weak VWAP-reclaim filter (VWAP is dragged down in a fast slide, so reclaim is easy), and `vol_monitor` is shadow-only (never blocks). A VIX-spike dead-cat in RED will enter and stack across variants. *Fix:* enforce a vol/VIX-spike block + RED-regime veto (or multi-bar/volume/ATR confirmation); keep RED entries shadow-only until proven. (`lane_a_monitor.py:405-411`, `lane_a_ta.py:212-239`)

6. **Never-exit on a stale/missing mark** (root cause of P0 #0). `evaluate_exit_alerts` returns `[]` on `mark_quote_stale`/`ret_pct is None` **before** the SL/TP/near-expiry checks, so a swing-hold position can ride to expiry unmanaged (no test covers this). *Fix:* on a stale mark, still evaluate SL / time-stop / near-expiry cut on the clamped mark rather than bailing. (`lane_a_monitor.py:518-593`) (glm, fable)

---

## P1 — before a trustworthy rank / before live

- **No-sell window (08:30–09:30 ET) blocks the stop-loss** for swing-hold positions — a gap-down isn't cut for up to an hour. Allow SL in-window for `swing_hold` or explicitly accept+document. (consensus)
- **Timer collisions + unlocked state.** Entry and intraday timers both fire 15:45 ET; monitor and intraday both fire 10:00 ET. The full read-modify-write of `variants_state.json` is not locked (only the write is) → TOCTOU race can lose paper entries/exits. Stagger by ≥2 min or lock the whole cycle. (glm, kimi)
- **`low_sample` gate too weak.** `≥2 trades` tells you nothing about win rate. Require ≥20 **trades** per variant, gate on **entered** sessions (not evaluated), and require statistical separation (Wilson-LB win rate / bootstrap CI on `avg_pnl_per_trade`) before naming a leader. (gpt, kimi, glm)
- **`max_hold_dte=1`** cuts on the final trading day at peak theta — raise to **2–5** as a buffer (also covers a missed expiry-eve mark).
- **End-to-end live close unproven** — run one Phase-1 canary sell-to-close on a real fill before any size.
- **Attribution confounds** in the grid: `tp25` and `loose` also change concurrency (4 vs 3); `tp60` moves both TP and SL. De-confound (hold concurrency + SL constant across the TP axis). DTE and OTM-vs-ATM@21DTE axes are clean.

---

## Phase D — is the thesis +EV? (the crux)

Consensus math (ATM XSP, index ≈ 750, σ≈15–18%):

| DTE | Cost/contract | Theta/day | Underlying move for +40% |
|-----|---------------|-----------|--------------------------|
| 14  | ~$700–880 | ~3.6%/day | ~+0.9–1.3% (rises with hold days) |
| 21  | ~$1,080 | ~2.4%/day | ~+1.3–1.4% |
| 30  | ~$1,290 | ~1.7%/day | ~+1.6% |

- **Breakeven win rate** for TP+40/SL−50 ≈ **55.6% pre-cost, ~59–60% post-cost.** TP+25/SL−50 needs ~67% (too tight on the upside); TP+60/SL−60 has the lowest breakeven (~51%) but sits in decay/vega longer.
- **Theta is a one-sided drag** — every flat day pushes the option toward the −50% stop while the +40% hurdle widens. A **vega crush** on recovery (dips buy elevated IV) adds unmodeled headwind. Net: **the bounce edge is roughly consumed by theta; the thesis is marginal, not clearly +EV.** fable models it as **outright −EV at zero post-signal drift** (14-DTE +40/−50 ≈ **−12%/trade**, 45.7% win vs 55.6% breakeven); it turns +EV only if the bounce signal captures **≥ +0.5% SPX drift within ~5 days** — plausible in GREEN/YELLOW, historically negative in RED (exactly the regime `DIP_BOUNCE` stops checking).
- **Best DTE — genuine 3-way disagreement:** gpt/kimi prefer **21-DTE ATM**, fable finds **21–30 DTE dominates** (the 14-DTE flagship is dominated; TP+25% strictly dominated), while glm/grok/fusion prefer **14-DTE ATM** — *not* on math but because it is the **only rung that fits a $1k account**. Resolution: the math favors **21–30 DTE ATM, +40–50 / −50–60**; 14-DTE is only preferred as the $1k-feasible compromise. **Re-seed the grid toward 21–30 DTE** before spending 20 soak sessions on a dominated flagship.
- **TP/SL:** consensus best = **+40% / −50%** (`v2_dip_swing_14dte` baseline). OTM and loose(no-VWAP) are noise/experiments — don't promote; use `loose` to *measure* the VWAP filter's value.
- **Structural idea (fusion):** a **debit call spread** instead of a naked long call cuts theta + vega drag and pushes the trade closer to +EV — worth prototyping as a new variant.

---

## Phase A — steal list + wiki gaps

**Steal from Cemini (ranked):**
1. `conductor_dispatch.py` — single-variant live dispatch (directly fixes P0 #1). **M, P0**
2. `conductor_reviewer.py` — pre-trade reviewer/second-opinion gate before buy-to-open. **M, P0**
3. `vol_monitor.py` **enforce** (not shadow) — VIX-spike block for the falling-knife overlay. **S–M, P1**
4. RH adapter timeout / recent-order reconciliation pattern (harden the MCP `ref_id` path against timeouts). **S, P1**

**Wiki gaps (P1/P2):** the OSINT `research_wiki/concepts/` has no doc for the **multi-day hold** thesis — `xsp-lane-a-overnight-swing.md` still describes the *old* morning-cut strategy — and **no empirical BB mean-reversion base rate**. Add `concepts/xsp-lane-a-dip-swing.md` (thesis + theta-vs-recovery breakeven) and `concepts/bb-mean-reversion.md` (bounce statistics). Until then a `wiki_enforcement_gate` would correctly block live.

---

## Cross-auditor disagreement hooks

1. **Best DTE:** 14 (only $1k-feasible) vs 21 (gpt/kimi) vs **21–30 dominates on math** (fable). Resolve empirically with ≥20 trades/variant — but only after the measurement fix (P0 #0).
2. **Is the bounce sufficient safety?** Operator's design ("the bounce is the safety") vs the panel's P0 that RED needs a vol/regime overlay.
3. **Ranking metric:** `avg_pnl_per_trade_usd` alone (pack guidance) vs expectancy-per-session + Wilson/bootstrap CI (accounts for trade frequency + small-n noise).
4. **+EV on math or only on live proof?** Panel leans: not provable on math (theta ≈ eats the edge); needs live win rate >60%.

---

## Recommended next actions (operator)

1. **FIX THE MEASUREMENT FIRST (P0 #0).** Widen the `spy_quote.py` mark guards past ±60% and make SL/time/DTE-cut fire on the clamped mark — until this ships, **every soak session is wasted** (TP/SL can't register; losers score $0). Nothing else on the paper side matters until this is done.
2. **Keep the paper soak running but do NOT flip live**, and **add regime + VIX at entry** to the dip logs/scoreboard — the key question is whether `DIP_BOUNCE` loses in RED/YELLOW.
3. **Re-seed the grid toward 21–30 DTE ATM** (+40–50 / −50–60); the 14-DTE flagship is mathematically dominated and TP+25% is strictly dominated. Keep 14-DTE only as the $1k-feasible live compromise. Prototype a **debit-spread** variant to blunt theta/vega.
4. **Live patch order (P0):** single-variant dispatch + `LIVE_VARIANT_ID` allowlist → live selector parity (`dte_target`/`otm_one`) → `premium_scale=1.0` live path → max-loss sizing gate → falling-knife vol/RED overlay. **(P1)** no-sell-window SL, timer stagger/lock, tighten `low_sample` to ≥20 trades + Wilson/bootstrap CI, `max_hold_dte=2`, add cluster telemetry (entered-sessions, exit-reason breakdown, `dte_at_exit`, entry/exit IV, hold-time).
5. **When ready to live:** promote a single variant, one contract, after a canary sell-to-close and ≥20 clean dip trades with a statistically separable positive edge — and only if the (now-measurable) win rate clears ~60% net of costs.
