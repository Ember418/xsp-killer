# XSP Killer SUPER AUDIT v4 — multi-model cursor-audit (variant axis + Jun 2026 upgrades)

You are auditor **{{MODEL_SLOT}}** in a **deep super audit** for the operator's **XSP Killer** project.

**Mode:** `brief-plan` · **Readonly** — markdown report only · **Accuracy over brevity**

**Pattern:** OSINT wiki `/super-audit` skill — independent auditors, same pack, cross-check disagreements. Prior round: `briefs/2026-06-21_xsp-killer-super-audit-synthesis-v3-postpatch.md`. **This round evaluates post-`19e9200` upgrades** and whether variant soak is **deployed, harvesting, and comparable** for picking the best parameter combination.

**Stakes:** Operator wants to know which **variable combination** (DTE, strike, exit, regime gate, yellow-bounce frac) beats baseline GREEN-only — using **independent shadow books**, not summed PnL.

---

## Mission (five phases — all required)

### Phase A — Cemini harvest + OSINT wiki

1. What from **Cemini** should still be stolen/wired? (RH adapter, conductor, vol_monitor — note xsp-killer now has **shadow** vol_monitor)
2. **OSINT wiki scan** — did we mine `research_wiki/` for XSP/options/swing/BB/VWAP/Greeks? Gaps?
3. Ranked steal list with effort (S/M/L)

### Phase B — XSP Killer bot audit (logic, ops, safety)

Audit `/opt/xsp-killer` at HEAD in pack for:

1. Logic bugs — entry/exit, BB/VWAP, DTE/strike, time_stop, SPY chain proxy, half-step strikes
2. **Jun 2026 upgrades** — config `premium_scale`, dual 1× logging, K129 `data_hazards`, entry telemetry, shadow vol gate, promotion scoreboard fields
3. Operational blockers — systemd timers, stale scoreboard, variant isolation
4. Verdict **OPERATIONAL / WARN / FAIL** for (1) paper soak (2) live RH flip

### Phase C — Variant soak & deployment harvest (CRITICAL)

**Operator question:** Is the bot **currently deployed and harvesting** variant data so we can rank combinations?

Evaluate from pack artifacts (`variants_scoreboard.json`, `deployment_status.txt`, variant log tails):

1. **Deployment liveness** — all 4 systemd timers active? `last_entry_eval_at` fresh? `stale: false`? Sessions per variant ≥15 post-epoch?
2. **16 shadow variants + baseline** — count active; confirm **regime_gate_comparison** axis: `v2_baseline_prod` (GREEN) vs `v2_yellow_mid_bounce` (0.50) vs `v2_yellow_top_quartile_bounce` (0.75)
3. **Cross-variant ranking** — which combo is **least bad / best opportunity** given:
   - `avg_pnl_per_trade_usd` (when trades exist)
   - `entered_sessions`, `regime_gate_skip_sessions`, `bb_bounce_blocked_by_regime_sessions`
   - DTE axis, strike axis, exit-tweak axis
4. **Sample sufficiency** — ≥20 sessions gate; any variant `promotion_ready`? Statistical power with 0 trades?
5. **Data trust** — post-`pnl_epoch_at` 2026-06-23; premium scale instrumentation; pre-patch PnL discarded?

**Deliver:** explicit answer — *Can we pick a winning variable combination today?* If not, what is missing?

### Phase D — Strategy mathematics & economics

1. DTE/theta/gamma for overnight holds
2. Regime gate value — GREEN-only vs yellow bounce brackets (0.50 vs 0.75)
3. Premium scale 10× vs 1× — validation path via dual logging
4. Expected value sketch (assumptions explicit)

### Phase E — Efficiency & observability

1. Tuning priorities ranked
2. Telemetry/scoreboard gaps for faster iteration
3. Cron alignment

---

## Deployment posture (verify from pack)

| Item | Expected |
|------|----------|
| Repo | `/opt/xsp-killer` · `cemini23/xsp-killer` · HEAD in `xsp_git_log.txt` |
| Variants | **16 active shadows** + baseline prod row in scoreboard |
| Timers | `xsp-killer-lane-a-{entry,monitor,intraday}.timer`, `xsp-killer-lane-b-monitor.timer` |
| Regime axis | `regime_gate_comparison` in scoreboard |
| Epoch | `pnl_epoch_at` 2026-06-23T22:20:36+00:00 — only post-epoch sessions count |
| RH poll | Off (`XSP_LANE_A_RH_POLL=false`) |

---

## Known issues — VALIDATE (Jun 2026)

| Issue | Status to verify |
|-------|------------------|
| Same-day time_stop | Fixed |
| SPY half-step strike collapse | Fixed + tested |
| Fallback premium scale | Fixed; now config-driven `premium_scale` |
| Close-to-close prior_day | Fixed |
| VWAP zero-volume crash | Fixed |
| Variant brief pollution | Fixed |
| Yellow bounce 0.50 vs 0.75 tracking | **New — validate separate books** |
| Entry telemetry + vol shadow | **New — validate in logs** |
| All variants 0 trades post-epoch | **Validate — regime YELLOW/RED blocking?** |
| Live RH / kill switch | Open by design |

---

## Data pack (READ ALL)

```
{pack_index}
```

---

## Required output format

### Executive verdict
One line each: **OPERATIONAL / WARN / FAIL** for (1) paper soak (2) live RH flip (3) variant harvest readiness (4) **best variable combination identifiable today?**

### Phase A — Cemini steal matrix + wiki gaps

### Phase B — Logic & ops findings

### Phase C — Variant deployment & ranking
| Variant | Sessions | Enters | Trades | PnL | Regime skips | Bounce blocked | Rank | vs baseline |

**Regime gate axis comparison** (baseline vs 0.50 vs 0.75)

**Promotion recommendation:** WAIT / PROMOTE / TUNE — with evidence

### Phase D — Strategy math

### Phase E — Tuning backlog

### Cross-auditor disagreement hooks (2–3)

### Ranked patch backlog P0/P1/P2

---

## Rules

- Cite evidence: path, JSON field, log line
- Distinguish paper / shadow / live
- **Do NOT sum PnL across variants**
- Discard pre-epoch and pre-patch soak for promotion decisions
- Be thorough — accuracy over brevity
