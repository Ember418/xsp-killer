---
title: XSP Killer — Robinhood Agentic Trading MCP connection plan
type: brief
target: cemini-prod /opt/xsp-killer
tags: [xsp-killer, robinhood, agentic-trading, mcp, lane-a, lane-b, k135]
created: 2026-06-29
updated: 2026-06-29
maturity: draft
readiness: phase_0_scaffold_shipped  # code ready; OAuth not connected
---

## Target

**cemini-prod** — `/opt/xsp-killer` operator + server Claude. Replaces unofficial `robin_stocks` credential path with Robinhood's official Agentic Trading MCP when options execution is enabled on the operator's Agentic account.

## Summary

Robinhood launched **Agentic Trading** (May 27, 2026): a dedicated **Agentic brokerage account** plus an official **Trading MCP** at `https://agent.robinhood.com/mcp/trading`. Agents connect via OAuth (no password in env), read all Robinhood accounts, but **place trades only in the funded Agentic account**. Options tools (`get_option_positions`, `review_option_order`, `place_option_order`, etc.) exist in the MCP schema but are **rolling out** — verify tool surface before any live flip.

**xsp-killer today:** paper-only systemd cron; optional `robin_stocks` position poll via `RH_USERNAME`/`RH_PASSWORD` (`XSP_LANE_A_RH_POLL=false`). Super-audit v4 (2026-06-29): **no execution path**. This brief is the canonical migration plan from paper + unofficial read poll → **official MCP adapter** for Lane A exits and (later) Lane B inventory sync.

**Recommended posture:** operator completes desktop MCP onboarding first; server Claude ships `RobinhoodMCPAdapter` (Python MCP HTTP client + token file); keep paper soak until ≥1 closed trade post-epoch **and** MCP options tools confirmed on operator account.

## Body

### 1. What Robinhood shipped

| Item | Detail |
|------|--------|
| Launch | May 27, 2026 — [newsroom](https://robinhood.com/us/en/newsroom/robinhood-is-now-open-to-agents/) |
| Product page | [robinhood.com/us/en/agentic-trading](https://robinhood.com/us/en/agentic-trading) |
| MCP endpoint | `https://agent.robinhood.com/mcp/trading` (Streamable HTTP) |
| Auth | OAuth via Robinhood login in browser — agent never sees password |
| Trade boundary | **Agentic account only** — primary/legacy accounts are read-only for order placement |
| Account cap | Up to 10 self-directed individual accounts including Agentic |
| Rollout | Feature + options both gated — Robinhood emails when eligible |
| Onboarding | **Desktop browser required** for Agentic account open + MCP auth (mobile: copy URL to desktop) |

**Why this matters for xsp-killer:** Cemini prod `.env` already lists `RH_USERNAME`/`RH_PASSWORD` for unofficial API access (@concepts/api-credential-registry.md notes 2FA-incompatible automation). Agentic MCP is the first **official** Robinhood path for programmatic agent trading — eliminates brittle session login, aligns with Robinhood ToS, and exposes structured options tools instead of scraping `robin_stocks`.

### 2. MCP tool surface (XSP-relevant subset)

Full inventory: [Trading with your agent](https://robinhood.com/us/en/support/articles/trading-with-your-agent/) (ref 5580019).

#### Reads (all accounts — use to cross-check primary vs Agentic)

| Tool | xsp-killer use |
|------|----------------|
| `get_accounts` | Identify Agentic account ID; never trade non-Agentic |
| `get_portfolio` | Buying power + total value gate before entries |
| `get_option_positions` | Replace `RobinhoodAdapter.get_open_option_positions()` poll |
| `get_option_orders` | Reconcile fills vs paper ledger |
| `get_option_chains` | Lane A strike selection at close window |
| `get_option_instruments` | Filter XSP by DTE/strike/type |
| `get_option_quotes` | Mark for exit rules (−20% SL, +20% TP, BB touch) |
| `get_equity-historicals` | Optional — SPY/OHLC if Polygon fallback fails |
| `get_indexes` / `get_indexes_quotes` | SPX index level for strike context |
| `search` | Resolve "XSP" / Mini-SPX symbol |

#### Writes (Agentic account only)

| Tool | xsp-killer use |
|------|----------------|
| `review_option_order` | **Mandatory preflight** — pre-trade warnings before any live order |
| `place_option_order` | Lane A exit sells; future Lane A entries (currently manual) |
| `cancel_option_order` | Abort stale GTC / partial fills |

**Not in v1 scope:** watchlist mutators (`create_watchlist`, `add_to_watchlist`, …) — real account mutations with no xsp-killer benefit; disable in adapter allowlist.

**Options status (2026-06-29):** Robinhood docs say long equity + options orders supported; also say options "rolling out." Treat as **[NEEDS VERIFICATION]** — first prod step is a tool-surface audit on the operator's authenticated session.

### 3. Current xsp-killer baseline

| Component | Path | Notes |
|-----------|------|-------|
| Repo | `/opt/xsp-killer` | Standalone since 2026-06-21 pivot |
| RH adapter | `xsp_killer/robinhood.py` | `robin_stocks` read-only; no orders |
| Env | `RH_USERNAME`, `RH_PASSWORD`, `XSP_LANE_A_RH_POLL=false` | 2FA breaks automation |
| Lanes | A (overnight swing exits), B (LEAPS hedge alerts) | Paper default |
| Schedulers | 4 systemd timers (intraday, entry, monitor, lane-b) | Active on prod |
| Audit | v4 WARN — 0 enters post-epoch; live RH **FAIL** | No execution stub |

Lane A exit rules (prod): sell window 09:30–10:00 ET; −20% SL; +20% TP w/ upper BB; 10:00 ET time stop. See `/opt/xsp-killer/docs/lane-a-brief.md`.

### 4. Architecture — MCP adapter for deterministic cron

Robinhood docs target **conversational agent platforms** (Cursor, Claude Code, ChatGPT). xsp-killer is **headless systemd Python**. Bridge pattern:

```
systemd timer → lane_a_monitor.py
                    ↓
              RobinhoodMCPAdapter  ← NEW (xsp_killer/robinhood_mcp.py)
                    ↓ HTTP Streamable MCP + OAuth token file
              https://agent.robinhood.com/mcp/trading
                    ↓
              Robinhood Agentic account (XSP options only)
```

**Do not** run Cursor/Claude Code on prod as the execution runtime. Ship a **Python MCP client** (`mcp` SDK ≥1.27, already on operator laptop) with:

1. **Token store** — `/opt/xsp-killer/.local/robinhood_mcp_token.json` (mode 600, root-only). Populated after one-time OAuth on desktop; document refresh/re-auth cadence when Robinhood expires tokens.
2. **Account pin** — env `RH_AGENTIC_ACCOUNT_ID` — adapter rejects any `place_option_order` targeting a different account.
3. **Tool allowlist** — reads + `review_option_order` + `place_option_order` + `cancel_option_order` only.
4. **Kill switch** — env `XSP_LANE_A_LIVE_EXITS=false` (default) gates `place_option_order`; reads always allowed when MCP connected.
5. **Dual-write audit** — log every MCP call + `review_option_order` payload to `logs/rh_mcp_audit.jsonl`.

Keep `robinhood.py` (`robin_stocks`) as **fallback read path** until MCP read parity verified; remove credentials from `.env` once MCP reads stable ≥2 weeks.

### 5. Operator setup (desktop — do this before server work)

Prerequisite: Robinhood primary individual account in good standing; Agentic Trading invite received (or product visible in app).

#### Step A — Enable Agentic Trading access

1. Confirm email invite or see **Agentic Trading** in Robinhood app/web.
2. If missing: wait for rollout — MCP auth will fail without product access.

#### Step B — Connect MCP (pick one platform for initial OAuth)

**Cursor (recommended — matches Cemini stack):**

1. Cursor → Settings → Tools & MCP → Connect
2. MCP URL: `https://agent.robinhood.com/mcp/trading`
3. Complete Robinhood OAuth in browser (desktop).
4. When prompted, **open Agentic account** and fund with Lane A budget (operator decision — suggest starting ≤ existing paper notional cap).

**Claude Code alternative:**

```bash
claude mcp add robinhood-trading --transport http https://agent.robinhood.com/mcp/trading
# /mcp → select robinhood-trading → authenticate
```

#### Step C — Tool-surface audit (mandatory before prod token export)

In the connected client, run a read-only session:

```
List every Robinhood MCP tool you can call.
Call get_accounts and show which account is the Agentic account.
Call get_option_positions and get_option_chains for XSP.
Do not place any orders.
```

**Record in** `/opt/xsp-killer/config/rh_mcp_audit.md`:

- Agentic account number (last 4 ok in wiki; full ID in prod config only)
- Options approval level on Agentic account
- Whether `place_option_order` appears in tool list
- Sample `get_option_chains` response for XSP (1 chain, redact balances)

#### Step D — Fund + isolate

| Rule | Rationale |
|------|-----------|
| Fund **Agentic account only** for bot capital | MCP cannot place orders elsewhere |
| Do **not** migrate primary RH long-call book automatically | Lanes A/B thesis assumes existing RH book — operator manually mirrors or runs Agentic as parallel sleeve |
| Enable Robinhood push notifications | Every agent trade notifies per Robinhood |
| Know disconnect path | Robinhood app → disconnect agent (instant kill) |

#### Step E — Export OAuth for headless prod (server Claude implements)

Robinhood MCP OAuth tokens are bound to the connecting client. Server Claude must:

1. Research Robinhood MCP token refresh semantics (official docs sparse as of 2026-06-29).
2. Implement either:
   - **(Preferred)** Official refresh flow into `/opt/xsp-killer/.local/robinhood_mcp_token.json`, or
   - **(Interim)** Scheduled re-auth reminder + manual token paste from Cursor session until refresh documented.
3. Never commit tokens; add path to `.gitignore`.

### 6. Server implementation plan (phased)

#### Phase 0 — Read-only MCP parity (1–2 days)

| Task | Acceptance |
|------|------------|
| Add `xsp_killer/robinhood_mcp.py` with MCP HTTP transport | Unit tests mock MCP responses |
| Wire `get_option_positions` + `get_option_quotes` | Matches `robin_stocks` position count ±0 |
| Env `XSP_LANE_A_RH_MCP=true` switches adapter | Default false |
| Audit log jsonl | Every tool call timestamped |

#### Phase 1 — Review-only exit dry run (3–5 days)

| Task | Acceptance |
|------|------------|
| On Lane A exit signal, call `review_option_order` (sell-to-close) | Log warnings; no `place_option_order` |
| Compare review est. proceeds vs paper economics | Slippage within configured band |
| Gate: `intel:playbook_snapshot` GREEN unchanged | @concepts/xsp-lane-trading-framework.md |

#### Phase 2 — Live exits (operator GO only)

| Task | Acceptance |
|------|------------|
| `XSP_LANE_A_LIVE_EXITS=true` + `RH_AGENTIC_ACCOUNT_ID` set | Single-contract sell test in Agentic account |
| Max contracts per exit = 1 (config) | Hard cap in adapter |
| Post-trade: `get_option_orders` reconcile | Discord/Telegram alert on fill |
| Rollback: flip env false + disconnect MCP in app | ≤60s stop |

#### Phase 3 — Lane B inventory sync (read-only)

| Task | Acceptance |
|------|------------|
| Lane B monitor reads LEAPS via MCP | Hedge-gap alerts use live delta from quotes |
| Entry remains manual | Per framework — no auto LEAPS buy |

**Out of scope v1:** Lane A automated entries via MCP (mentor playbook still paper-validating variants); LangGraph brain; moving primary RH book.

### 7. Config additions (proposed)

```yaml
# config/rh_mcp.yaml (new)
agentic_account_id: ""          # from get_accounts — REQUIRED for writes
mcp_url: "https://agent.robinhood.com/mcp/trading"
token_path: ".local/robinhood_mcp_token.json"
allowed_chain_symbols: ["XSP"]
live_exits: false               # master kill switch
max_contracts_per_order: 1
require_review_before_place: true
audit_log: "logs/rh_mcp_audit.jsonl"
```

```bash
# .env additions
XSP_LANE_A_RH_MCP=false          # use MCP adapter for reads
XSP_LANE_A_LIVE_EXITS=false
RH_AGENTIC_ACCOUNT_ID=
# Deprecate after MCP stable:
# RH_USERNAME=
# RH_PASSWORD=
```

### 8. Risk gates (non-negotiable)

| Gate | Owner |
|------|-------|
| Agentic account only for `place_option_order` | Adapter hard reject |
| `review_option_order` before every place | Code path — no bypass flag |
| `XSP_LANE_A_LIVE_EXITS=false` default | Env |
| Regime GREEN for new risk | Existing `risk_gates.py` — @concepts/xsp-lane-trading-framework.md |
| Super-audit PASS on execution path | Before Phase 2 GO |
| Operator disconnect tested | Runbook in `docs/rh_mcp_runbook.md` |
| No credentials in chat/logs | Ops |

Robinhood disclosure (paraphrased): **you** are liable for agent trades; Robinhood does not supervise third-party agents; data shared with AI provider leaves Robinhood security boundary. [Source: agentic-trading-overview ref 5527723]

### 9. Migration from robin_stocks

| Stage | robin_stocks | MCP |
|-------|--------------|-----|
| Now | Optional read poll | Not connected |
| Phase 0 | Parallel read compare | MCP read primary |
| Phase 1+ | Disabled | Sole RH interface |
| Credentials | Remove from `.env` | Token file only |

**Why migrate:** unofficial API breaks on 2FA, ToS gray area, no structured `review_option_order`, no account isolation.

### 10. Verification checklist (operator + server Claude)

- [ ] Agentic Trading enabled on RH account
- [ ] Agentic account opened + funded (desktop)
- [ ] MCP connected in Cursor; OAuth complete
- [ ] Tool audit doc filled — options tools present
- [ ] `get_option_positions` returns XSP positions (or empty) on Agentic account
- [ ] Phase 0 MCP adapter deployed; parallel read matches robin_stocks
- [ ] Phase 1 review-only exits logged ≥5 sessions
- [ ] Super-audit on execution diff
- [ ] Operator GO for single-contract live exit test
- [ ] Push notification received on test fill
- [ ] Disconnect/kill switch drill

### 11. Open questions [NEEDS VERIFICATION 2026-06-29]

1. **OAuth token lifetime + refresh** for headless systemd — not documented in RH support articles; server Claude must probe or ask RH support.
2. **Options rollout** — confirm `place_option_order` on operator account before Phase 2.
3. **Agentic vs primary book** — operator decision: mirror existing XSP long calls into Agentic or run parallel paper-to-live sleeve.
4. **Order types** — docs say "different available order types"; confirm market vs limit for 09:30–10:00 exit window.
5. **XSP symbol** — verify MCP `search("XSP")` / chain symbol matches `robin_stocks` `chain_symbol` casing.

### 12. Do not

- Paste `RH_PASSWORD` into Cursor chat or commit to git
- Enable live exits before paper soak produces ≥1 entered+closed trade post-epoch (current blocker: regime gate)
- Use MCP watchlist write tools from cron
- Route Lane A entries to MCP before variant promotion scoreboard clears
- Assume Sherwood/third-party MCP wrappers — use official endpoint only

## 13. Readiness status (2026-06-29 — server)

**Paper posture unchanged** — no OAuth, no live orders. Product scaffold shipped:

| Brief item | Status |
|------------|--------|
| `xsp_killer/robinhood_mcp.py` | ✅ Adapter + allowlist + audit log + write gates |
| `xsp_killer/rh_broker.py` | ✅ Unified read path (MCP preferred, legacy fallback) |
| `config/rh_mcp.yaml` | ✅ Defaults: live_exits false, max 1 contract |
| `config/rh_mcp_audit.md` | ✅ Operator template |
| `docs/rh_mcp_runbook.md` | ✅ Phases 0–2 + kill switches |
| `scripts/rh_mcp_health.py` | ✅ Readiness check (no orders) |
| Lane A monitor | ✅ `dry_run_exit_reviews_via_mcp` when MCP enabled |
| systemd | ✅ `XSP_LANE_A_RH_MCP=false`, `XSP_LANE_A_LIVE_EXITS=false` |

**Operator next (when ready — not now):** desktop OAuth, fill audit doc, export token, run `rh_mcp_health.py`.

**Still WAIT:** paper soak ≥1 closed trade; Phase 2 live exits require operator GO.


## Sources

- [Agentic Trading overview](https://robinhood.com/us/en/support/articles/agentic-trading-overview/) — ref 5527723 (retrieved 2026-06-29)
- [Trading with your agent](https://robinhood.com/us/en/support/articles/trading-with-your-agent/) — ref 5580019 (retrieved 2026-06-29)
- [Robinhood is Now Open to Agents](https://robinhood.com/us/en/newsroom/robinhood-is-now-open-to-agents/) — May 27, 2026
- [Agentic Trading product page](https://robinhood.com/us/en/agentic-trading)
- @concepts/xsp-lane-trading-framework.md
- @concepts/api-credential-registry.md — Robinhood row
- `/opt/xsp-killer/README.md`, `xsp_killer/robinhood.py`, `briefs/2026-06-29_xsp-killer-super-audit-synthesis-v4.md` (prod)
- [Treeship Robinhood integration guide](https://docs.treeship.dev/integrations/robinhood-agentic-trading) — audit/receipt patterns (reference only)
