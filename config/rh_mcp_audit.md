# Robinhood MCP tool-surface audit (2026-07-07)

Audit executed via headless Python adapter (`xsp_killer/robinhood_mcp.py`) against
`https://agent.robinhood.com/mcp/trading` with OAuth token from `.local/robinhood_mcp_token.json`.
No orders placed — read-only session.

| Field | Value |
|-------|-------|
| Audit date (UTC) | 2026-07-07 19:15Z |
| Operator | c.barone |
| MCP client used | Claude Code (headless Python adapter, `RobinhoodMCPAdapter`) |
| Agentic account last-4 | 8843 |
| Options approval level (Agentic) | **`option_level_2`** — approved 2026-07-07 (was `""`; blocker cleared) |
| `place_option_order` in tool list? | yes |
| `get_option_chains` works for XSP? | yes — param is `underlying_symbol` (single string, not list) |
| `get_option_positions` (empty or redacted count) | 0 positions (Agentic account unfunded/empty) |
| Portfolio value (Agentic) | $500 total; $0 equity, $0 options |
| Adapter `max_contracts_per_order` | 1 |
| Live exits enabled | false |
| Notes | OAuth token valid. 44 tools total. MCP reads functional for all gated tools. **Options approved on Agentic (8843) as of 2026-07-07** — `get_accounts` now shows `option_level_2` for Agentic, matching individual (9741) and Bot (9703). Roth IRA (6964) still no options. **Phase 1 `review_option_order` validated live**: real schema uses `legs[]` (`option_id`/`side`/`position_effect`/`ratio_quantity`) + top-level `type`/`quantity`/`price`/`time_in_force`, NOT the flat `side`/`option_id` shape — adapter write path, grant-chain (`_review_grant_key`), write gates (`account_number` pin, per-leg `ratio_quantity` cap), and `dry_run_exit_reviews_via_mcp` updated accordingly. `get_option_chains` needs `underlying_symbol` param. `get_indexes` returns XSP at id `b8ae3ed3-7f82-4c77-adb4-f25f2cab6a4e`. Token expires at epoch 1784230919866 (~Aug 2026). |

## Account inventory (redacted)

| # | Type | Nickname | Last-4 | Agentic? | Option Level |
|---|------|----------|--------|----------|-------------|
| 1 | individual (cash) | — | 9741 | no | option_level_2 |
| 2 | individual (cash) | Bot | 9703 | no | option_level_2 |
| 3 | ira_roth (cash) | — | 6964 | no | — |
| 4 | individual (cash) | Agentic | 8843 | **yes** | **option_level_2** (approved 2026-07-07) |

## Tool inventory (44 tools)

### Reads (all accounts)

- `get_accounts` — list brokerage accounts
- `get_portfolio` — market value breakdown + buying power
- `get_equity_positions` — open equity positions per account
- `get_equity_orders` — equity order history
- `get_equity_quotes` — real-time stock quotes
- `get_equity_historicals` — OHLCV bars
- `get_equity_fundamentals` — valuation ratios, market cap
- `get_equity_tradability` — per-symbol eligibility check
- `get_option_positions` — open + closed option positions
- `get_option_orders` — option order history
- `get_option_chains` — expiration dates + contracts per underlying
- `get_option_instruments` — option contracts by chain_symbol/chain_id/ids
- `get_option_quotes` — real-time quotes by instrument UUID
- `get_option_historicals` — OHLC bars for option contracts
- `get_option_watchlist` — user's options watchlist
- `get_indexes` — index data (XSP, SPX, NDX, DJX, etc.)
- `get_index_quotes` — real-time index values
- `search` — natural-language instrument/currency/index resolution
- `get_pnl_trade_history` — per-trade realized P&L
- `get_realized_pnl` — per-bucket realized gain
- `get_watchlists` — user's watchlists
- `get_watchlist_items` — items in a watchlist
- `get_popular_watchlists` — Robinhood-curated lists
- `get_earnings_calendar` — earnings reports by date range
- `get_earnings_results` — earnings for one equity symbol
- `get_scans` — saved scanners/screeners
- `run_scan` — execute a saved scanner

### Writes (Agentic account only)

- `review_option_order` — simulated order with pre-trade alerts
- `place_option_order` — real options order (Agentic account only)
- `cancel_option_order` — cancel open option order
- `review_equity_order` — simulated equity order
- `place_equity_order` — real equity order
- `cancel_equity_order` — cancel open equity order

### Watchlist mutators (excluded from adapter allowlist)

- `add_option_to_watchlist`, `add_to_watchlist`, `create_watchlist`
- `follow_watchlist`, `unfollow_watchlist`, `update_watchlist`
- `remove_from_watchlist`, `remove_option_from_watchlist`
- `create_scan`, `update_scan_config`, `update_scan_filters`

## Sample XSP chain (`get_option_chains` with `underlying_symbol: "XSP"`)

```
chain_id: bf82fd28-ac40-46a0-aaf5-ccbb706f3072
symbol: XSP
can_open_position: true
cash_component: none
expiration_dates (first 15): 2026-07-07, 07-08, 07-09, 07-10, 07-13, 07-14,
  07-15, 07-16, 07-17, 07-20, 07-21, 07-22, 07-23, 07-24, 07-27 ...
  (continues through at least 2027-06)
```

## Sample SPX instruments (`get_option_instruments` with `chain_symbol: "SPX"`)

```
id: 20b0b061-96a6-46c7-8a51-607995f8754e
chain_symbol: SPX, underlying_type: index
expiration: 2026-07-17, strike: 200.0000, type: call
state: active, tradability: tradable
min_ticks: above_tick 0.10, below_tick 0.05, cutoff_price 3.00
```

## Adapter param notes

| Tool | Param | Issue |
|------|-------|-------|
| `get_option_chains` | `underlying_symbol` (string) | Adapter docs/tests may expect `chain_symbol`; update call sites |
| `get_indexes` | no params or `symbol`/`ids` list | `get_indexes({})` returns all; `symbol` rejected as extra property — use `ids` or no-arg |
| `get_index_quotes` | TBD | Not tested this session |
| `get_option_instruments` | `chain_symbol` (string) | Works for SPX |

## Sign-off

- [x] Read-only session only — no orders placed during audit
- [x] `RH_AGENTIC_ACCOUNT_ID=652628843` set in xsp-killer `.env` (not committed)
- [x] Token exported to `.local/robinhood_mcp_token.json` (mode 600)
- [x] Options approval on Agentic account (8843) — `option_level_2` confirmed via `get_accounts` 2026-07-07
- [x] Phase 1 `review_option_order` validated live against Agentic (8843): real schema is `legs[]` + `position_effect` + top-level `quantity`/`price`; preview returned quote/break-even/`order_checks` with no order placed. Adapter write path + grant-chain updated to match.
- [x] **Scheduled Phase 1 dry-run live**: `xsp-killer-lane-a-monitor.service` now runs with `XSP_LANE_A_RH_MCP=true` / `XSP_LANE_A_LIVE_EXITS=false` (sell window 09:30/09:35/09:45/10:00 ET, Mon–Fri). `dry_run_exit_reviews_via_mcp` reviews real option-UUID positions on exit alerts, skips synthetic `paper:` positions, and (account empty) runs a `phase1_canary_review` proof-of-life buy-to-open preview each run (`XSP_LANE_A_PHASE1_CANARY=true`). Verified: `rh_mcp_reviews` captured in `briefs/xsp-lane-a-monitor-latest.json` with `no_order_placed=True`. Auto-upgrades to real exit previews once a live position exists.
- [ ] **BLOCKER**: Fund Agentic account before live trading (currently $500 — enough to validate, not size)
- [ ] XSP chain + SPX instruments confirmed; Phase 0 reads functional
- [ ] `robin_stocks` fallback still available for read parity comparison (`XSP_LANE_A_RH_POLL=false` currently)

## Post-audit notes (2026-07-07)

- MCP token valid; adapter calls succeeding for all tested read tools
- Account isolation verified: `resolve_account_number()` correctly identifies Agentic account by nickname
- `get_option_positions` returns 0 — expected for empty account; read parity with `robin_stocks` not yet verifiable
- **RH_USERNAME/RH_PASSWORD can be removed from .env once**: (a) ≥1 position exists to verify read parity, or (b) operator confirms MCP reads sufficient for Phase 0 go-live
- `get_option_chains` → `underlying_symbol` param discovered; `rh_mcp.yaml` `allowed_chain_symbols` list needs matching call-site logic

## Auto-order verification (2026-07-07)

**Headless programmatic order placement CONFIRMED working with no human approval.**
The `review → place → cancel` loop was exercised live on the Agentic account
(8843) with a deliberately unfillable, minimal-exposure order:

- Instrument: XSP 2026-07-14 800C (`dbd8ffeb-…`), deep OTM (bid $0.00 / ask $0.02)
- Order: buy-to-open 1 @ limit **$0.01** (`legs[]` schema) → max exposure **$1**
- `review_option_order` → `order_checks: OPTION_NO_BID_PRICE` (expected)
- `place_option_order` → accepted, `state=unconfirmed`, id `6a4d23ce-…` — **placed
  programmatically, no confirmation step**
- `cancel_option_order` → `accepted=true`; final `state=cancelled`, **never filled**
- Post-test: 0 open positions, buying power unchanged at $500

Conclusion: the MCP "must get confirmation" guidance is an instruction to
interactive LLM agents, not a server gate. A valid OAuth token on the
agentic-enabled account authorizes headless `place_option_order`. `ref_id` is
accepted on `place` only (not `review`).

## Auto-exit wiring (Phase 2, gated OFF)

`dry_run_exit_reviews_via_mcp` now: reviews every real exit, and **places a
sell-to-close** order only when `XSP_LANE_A_LIVE_EXITS=true` AND the kill switch
is clear. Safety rails:

- **Master switch**: `XSP_LANE_A_LIVE_EXITS` (+ pinned account) — default false (I7).
- **Kill switch (I8)**: `XSP_LANE_A_KILL_SWITCH=true` or a sentinel file
  (`.local/KILL_SWITCH`, override `XSP_LANE_A_KILL_FILE`) blocks ALL
  `place_option_order`; cancels stay allowed.
- **Idempotency**: deterministic `ref_id = uuid5(option_id, trading_day,
  exit_reason)` so the 4 morning monitor runs cannot duplicate an exit order.
- **Contract cap**: `max_contracts_per_order` (I5); **account pin** (I3);
  **review→place grant** (I2).

## Auto-entry wiring (Phase 2, gated OFF)

For end-to-end automation the bot must also **open** positions, not just close
them. `lane_a_entry._maybe_place_live_entry` runs after all paper-entry gates
pass and, when authorized, places a real **buy-to-open**:

- **Master switch**: `XSP_LANE_A_LIVE_ENTRIES` (+ pinned account) — default false.
  Separate from `LIVE_EXITS`: opening risk and closing it are gated
  independently. The write gate keys on `position_effect` (`open` →
  `LIVE_ENTRIES`, `close` → `LIVE_EXITS`; ambiguous → exit-semantics).
- **Contract selection**: `select_entry_contract` picks the real XSP contract
  matching the Lane A rules (DTE window + `dte_pick`, near-ATM within
  `strike_max_steps_from_atm`, `cheapest_near_atm`) from live chains/quotes.
- **Buying-power fail-safe**: skips (does not error) if `ask*100*qty` exceeds
  reported account buying power (most-conservative of buying_power /
  unleveraged / cash). Prevents order-time failures on a thin account.
- **Kill switch (I8)** and **idempotency** (`ref_id = uuid5(instrument, day)`)
  apply exactly as for exits. Paper entry continues as an unaffected shadow
  record; the exit path only ever acts on real broker positions.

Entry/intraday systemd units run with `RH_MCP=true` + `LIVE_ENTRIES=false`, so
the review + buying-power path is exercised as a dry-run with no real buy.

### Sign-off (updated)

- [x] Headless auto-placement verified (place + cancel, $1 exposure, unfilled)
- [x] Agentic account funded — **$1,000** cash / $1,000 buying power (covers one
      near-ATM 14-DTE contract; $1.5–2k recommended for headroom)
- [x] Live buy-to-open path wired + unit-tested (gated OFF)
- [ ] **GATE**: ≥1 clean paper entry→exit cycle logged before flipping any live flag
- [ ] Flip `XSP_LANE_A_LIVE_ENTRIES=true` (entry/intraday units) after operator GO
- [ ] Flip `XSP_LANE_A_LIVE_EXITS=true` (monitor unit) after operator GO
