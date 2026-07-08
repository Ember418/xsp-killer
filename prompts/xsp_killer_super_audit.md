# XSP Killer SUPER AUDIT v7 — multi-model cursor-audit (dip-buy swing + live-entry path)

You are auditor **{{MODEL_SLOT}}** in a **deep super audit** for the operator's **XSP Killer** project.

**Mode:** `brief-plan` · **Readonly** — markdown report only · **Accuracy over brevity**

**Pattern:** OSINT wiki `/super-audit` skill — independent auditors, same pack, cross-check disagreements. Prior rounds: `briefs/2026-07-02_xsp-killer-super-audit-synthesis-v6.md`. **This round evaluates TODAY'S ADDS (2026-07-07):** the operator's actual thesis finally implemented as a **dip-buy swing** strategy, deployed as a **7-variant intraday shadow grid**, plus the wired-but-gated **live-entry path** for a **$1,000** account.

**Operator's thesis (the reason for today's work):** *"On dips, buy near-the-money ~14-day XSP calls; then when it's green a decent amount (we have ~14 days for the market to recover), sell."* Previous config bought every green close and dumped next morning (a coin-flip losing to theta). Today's work makes the code actually express the thesis.

---

## Today's adds — PRIMARY AUDIT TARGET (commits `07765bc`, `6be3fbc`, `d0cc157`)

1. **`DIP_BOUNCE` regime gate** (`lane_a_monitor.py::regime_gate_allows`) — allows entry in **any regime** (incl. RED/YELLOW) *iff* a confirmed BB bounce (`ta_entry_ok`) is present. The bounce is the only safety.
2. **Swing-hold exit** (`lane_a_monitor.py::evaluate_exit_alerts`, `LaneRules.swing_hold`, `max_hold_dte`) — no forced next-morning cut; take-profit fires on **any** evaluation (intraday), stop-loss any time, and time_stop **only** when `dte <= max_hold_dte` (near expiry).
3. **`bb_bounce` intraday entry** (`lane_a_entry.py::entry_gates_ok`, `lane_a_ta.py::detect_bb_bounce_entry`) — dump to lower/mid band then bounce + optional VWAP reclaim.
4. **7-variant dip-swing grid** (`config/lane_a_variants.yaml`) — 14/21/30 DTE, TP +25/+40/+60%, SL −50/−60%, one OTM, one loose (no-VWAP), concurrency 2–4.
5. **Intraday variant execution** (`lane_a_variants.py::run_all_variant_{entries,monitors}` `intraday_only` filter; `scripts/lane_a_variants.py entry|monitor --intraday`; `scripts/lane_a_intraday_cron.sh`).
6. **Bar cache** (`lane_a_ta.py::fetch_intraday_bars` TTL cache) — dedupes SPY fetches across variants per cron cycle.
7. **Scoreboard `dip_swing_cluster`** (`lane_a_variants.py::_build_dip_swing_cluster`) — isolates + ranks the 7 dip variants; names a leader only when `low_sample=false`.
8. **Live-entry path (gated, dry-run)** — `XSP_LANE_A_LIVE_ENTRIES`/`LIVE_EXITS`, kill switch, buying-power fail-safe, `select_entry_contract`/`buy_to_open` in `robinhood_mcp.py`.

---

## Mission (five phases — all required)

### Phase A — Cemini harvest + OSINT wiki
1. What from **Cemini** should still be stolen/wired for a dip-buy swing (RH adapter, conductor, vol_monitor)?
2. **OSINT wiki scan** — does `research_wiki/` (SPY, Greeks, BB/VWAP, signal-fusion) support or contradict the dip-bounce + multi-day-hold thesis? Any evidence on mean-reversion after BB-lower touches?
3. Ranked steal list with effort (S/M/L).

### Phase B — XSP Killer bot audit (logic, ops, safety) — focus on today's adds
1. **`DIP_BOUNCE` safety** — can it catch a falling knife? Is requiring `ta_entry_ok` sufficient given `regime_ok` is bypassed? What if the bounce is a dead-cat in a RED regime?
2. **Swing-hold correctness** — any path where a position **never exits** (e.g., TP/SL never hit, `max_hold_dte` mis-set, no-sell window interaction)? Does dropping the daily time_stop risk holding losers to expiry? Is `max_hold_dte=1` safe for near-expiry decay?
3. **Bar cache correctness** — is sharing one SPY frame across variants safe given per-variant `TaRules` (all share symbol/timeframes/period today — verify)? Staleness vs 15m cadence? Cached-None handling?
4. **Intraday cadence** — `already_entered_today` (one entry/day/variant) × up-to-14-day holds × concurrency 2–4: does this produce enough sample? Any double-entry or state-race across entry vs monitor intraday passes?
5. **Live-entry readiness** — for **$1k**: buying-power fail-safe, idempotent `ref_id`, kill switch, entry/exit gate split. Verdict **OPERATIONAL / WARN / FAIL** for (a) paper soak (b) live RH flip.

### Phase C — Dip-swing cluster harvest & ranking (CRITICAL)
**Operator question:** Once dips arrive, will the cluster produce **rankable, trustworthy** data to pick a winner to promote to live?
1. **Deployment liveness** — intraday timer active? dip variants running intraday (`entry --intraday`/`monitor --intraday`)? scoreboard `stale`?
2. **Cluster instrumentation** — `dip_swing_cluster` present, 7 members, `leader` gated on `low_sample`? Is `avg_pnl_per_trade_usd` the right ranking metric here vs. total P&L / expectancy?
3. **Sample sufficiency** — with one-entry/day and dips being rare, how many sessions to a statistically meaningful rank? Is the `low_sample` gate (≥20 sessions, ≥2 trades) appropriate for a dip-triggered strategy that may skip most days?
4. **Attribution** — do the 7 variants isolate the intended levers (DTE, TP, SL, strike, entry looseness, concurrency) cleanly, or are levers confounded?
**Deliver:** explicit answer — *what must be true before we promote a dip-swing variant to the $1k live account?*

### Phase D — Strategy mathematics & economics (the crux)
1. **Is the thesis +EV?** Buy ATM ~14-DTE call on a BB-lower-bounce dip, hold up to expiry, TP +40% / SL −50%. Model: theta bleed over a multi-day hold vs. probability/magnitude of the recovery needed to hit +40% option premium.
2. What underlying SPY move (%) is needed for +40% on a 14/21/30-DTE ATM call? Which DTE gives the best recovery-vs-decay tradeoff?
3. TP +25 vs +40 vs +60 and SL −50 vs −60 — expected-value sketch (assumptions explicit).
4. OTM (`otm_one`) vs ATM and loose (no-VWAP) entry — edge vs. noise.

### Phase E — Efficiency & observability
1. Tuning priorities ranked.
2. Telemetry/scoreboard gaps for judging the dip-swing cluster faster.
3. Cron alignment (intraday load with 7 extra variants + bar cache).

---

## Deployment posture (verify from pack)

| Item | Expected |
|------|----------|
| Repo | `/opt/xsp-killer` · `cemini23/xsp-killer` · HEAD in `xsp_git_log.txt` (`d0cc157` or later) |
| Variants | **18 active** = 11 close-window + **7 dip-swing** + baseline prod row |
| Dip cluster | `dip_swing_cluster` in scoreboard (7 members, leader gated) |
| Timers | `xsp-killer-lane-a-{entry,monitor,intraday}.timer`, `xsp-killer-lane-b-monitor.timer` |
| Intraday | dip variants run every 15m via `intraday_cron.sh` (`entry|monitor --intraday`) |
| Funding | **$1,000** live account; live entries/exits gated OFF (dry-run) |
| RH | LIVE_ENTRIES=false, LIVE_EXITS=false, kill switch armed |

---

## Known issues — VALIDATE (2026-07-07)

| Issue | Status to verify |
|-------|------------------|
| Base strategy = coin flip vs theta | Root cause = code didn't express thesis; **dip-swing is the fix — validate** |
| DIP_BOUNCE buys weakness in any regime | **New — validate falling-knife safety** |
| Swing-hold never-exit / hold-loser-to-expiry | **New — validate exit completeness** |
| Bar cache shared frame across variants | **New — validate correctness/staleness** |
| Dip cluster 0 trades (just deployed today) | **Expected — validate harvest path, not results** |
| Live entry/exit path | Wired + gated OFF; validate safety before flip |

---

## Data pack (READ ALL)

```
{pack_index}
```

---

## Required output format

### Executive verdict
One line each: **OPERATIONAL / WARN / FAIL** for (1) paper soak (2) live RH flip (3) dip-swing harvest readiness (4) **is the dip-buy-swing thesis +EV / promotable?**

### Phase A — Cemini steal matrix + wiki gaps

### Phase B — Logic & ops findings (today's adds first)

### Phase C — Dip-swing cluster deployment & ranking readiness
**Promotion recommendation:** WAIT / PROMOTE / TUNE — with evidence and the gate that must clear.

### Phase D — Strategy math (is the thesis +EV? which DTE/TP/SL?)

### Phase E — Tuning backlog

### Cross-auditor disagreement hooks (2–3)

### Ranked patch backlog P0/P1/P2

---

## Rules
- Cite evidence: path, JSON field, log line
- Distinguish paper / shadow / live
- **Do NOT sum PnL across variants**
- Dip cluster has ~0 trades (deployed today) — judge the **harvest + math**, not results
- Be thorough — accuracy over brevity
