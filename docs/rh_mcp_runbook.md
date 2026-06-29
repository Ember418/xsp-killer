# Robinhood Agentic MCP runbook (XSP Killer)

Paper mode stays default. This runbook covers **readiness → connect → live exits** when the operator is ready.

Canonical plan: `briefs/2026-06-29_xsp-robinhood-agentic-mcp-connection-cemini-prod.md`

## Current posture (paper)

| Env | Default | Meaning |
|-----|---------|---------|
| `XSP_LANE_A_RH_POLL` | `false` | Legacy `robin_stocks` read poll |
| `XSP_LANE_A_RH_MCP` | `false` | Official Agentic MCP read adapter |
| `XSP_LANE_A_LIVE_EXITS` | `false` | Blocks `place_option_order` even if MCP connected |

Reads require **either** `XSP_LANE_A_RH_MCP=true` (preferred) **or** `XSP_LANE_A_RH_POLL=true` (legacy). Writes always require MCP + explicit live-exits flag.

## Phase 0 — Read-only MCP (operator + server)

1. Complete desktop OAuth (Robinhood Agentic Trading → MCP URL in Cursor).
2. Fill `config/rh_mcp_audit.md` — confirm options tools exist on your account.
3. Export token to `/opt/xsp-killer/.local/robinhood_mcp_token.json` (mode `600`, root-only).
4. Set `RH_AGENTIC_ACCOUNT_ID` in `.env` (Agentic account only).
5. Enable reads: `XSP_LANE_A_RH_MCP=true` (keep `XSP_LANE_A_RH_POLL=false`).
6. Health check:

```bash
cd /opt/xsp-killer
PYTHONPATH=. python3 scripts/rh_mcp_health.py
```

7. Compare MCP vs legacy poll (optional parallel week):

```bash
XSP_LANE_A_RH_MCP=true XSP_LANE_A_RH_POLL=true PYTHONPATH=. python3 scripts/rh_mcp_health.py --compare-legacy
```

8. Verify audit log: `logs/rh_mcp_audit.jsonl`

## Phase 1 — Review-only exit dry run

Lane A monitor will call `review_option_order` on exit signals when MCP is enabled. **No** `place_option_order` until Phase 2.

Gate: paper soak ≥1 entered+closed trade post-epoch (current regime blocker).

## Phase 2 — Live exits (operator GO)

1. Fund **Agentic account only** (isolated from primary RH book).
2. Set `XSP_LANE_A_LIVE_EXITS=true` and confirm `RH_AGENTIC_ACCOUNT_ID`.
3. Single-contract test sell; confirm push notification.
4. Rollback drill: set `XSP_LANE_A_LIVE_EXITS=false` **and** disconnect agent in Robinhood app (≤60s stop).

## Kill switches

| Action | Effect |
|--------|--------|
| `XSP_LANE_A_LIVE_EXITS=false` | Adapter rejects all `place_option_order` |
| Robinhood app → disconnect agent | OAuth revoked; reads fail until re-auth |
| systemd stop timers | No cron evaluation |

## Do not

- Commit `.local/robinhood_mcp_token.json` or paste passwords in chat
- Enable live exits before MCP tool audit + paper soak gates pass
- Route orders to non-Agentic accounts (adapter hard-rejects)
