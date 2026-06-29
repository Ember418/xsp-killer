---
title: XSP Robinhood Agentic MCP
type: concept
tags: [concept, xsp, robinhood, mcp, agentic-trading]
related:
  - concepts/xsp-index-options.md
  - concepts/xsp-lane-a-overnight-swing.md
  - briefs/2026-06-29_xsp-robinhood-agentic-mcp-connection-cemini-prod.md
maturity: validated
created: 2026-06-29
updated: 2026-06-29
---

## Relations

- Canonical brief: `briefs/2026-06-29_xsp-robinhood-agentic-mcp-connection-cemini-prod.md`
- Runbook: `docs/rh_mcp_runbook.md`
- Code: `xsp_killer/robinhood_mcp.py`, `xsp_killer/rh_broker.py`

## Narrative

Robinhood **Agentic Trading** (May 2026) exposes an official MCP at `https://agent.robinhood.com/mcp/trading`. XSP Killer uses a **headless Python adapter** (not Cursor-as-runtime) for systemd cron.

### Paper mode today

All RH paths **off by default**:

| Env | Default |
|-----|---------|
| `XSP_LANE_A_RH_MCP` | `false` |
| `XSP_LANE_A_RH_POLL` | `false` |
| `XSP_LANE_A_LIVE_EXITS` | `false` |

### When going live

1. Desktop OAuth → token in `.local/robinhood_mcp_token.json`
2. Fill `config/rh_mcp_audit.md` (options tool surface)
3. Phase 0: MCP reads only (`XSP_LANE_A_RH_MCP=true`)
4. Phase 1: `review_option_order` on exit signals (no place)
5. Phase 2: `XSP_LANE_A_LIVE_EXITS=true` + `RH_AGENTIC_ACCOUNT_ID` for sells in **Agentic account only**

### Safety

- Tool allowlist (no watchlist mutators)
- `max_contracts_per_order: 1` in `config/rh_mcp.yaml`
- Audit log: `logs/rh_mcp_audit.jsonl`
- Kill switch: env + Robinhood app disconnect

## Ops

```bash
PYTHONPATH=. python3 scripts/rh_mcp_health.py
```

## Snippets

- Legacy `robin_stocks` remains fallback until MCP read parity ≥2 weeks.
- Do not connect until paper soak + operator tool audit complete.
