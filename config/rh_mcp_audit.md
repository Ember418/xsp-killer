# Robinhood MCP tool-surface audit (operator — desktop OAuth)

Fill after Step C in `briefs/2026-06-29_xsp-robinhood-agentic-mcp-connection-cemini-prod.md`.
Do **not** commit OAuth tokens or full account numbers.

| Field | Value |
|-------|-------|
| Audit date (UTC) | |
| Operator | |
| MCP client used (Cursor / Claude Code) | |
| Agentic account last-4 | |
| Options approval level (Agentic) | |
| `place_option_order` in tool list? | yes / no / rolling |
| `get_option_chains` works for XSP? | yes / no |
| `get_option_positions` (empty or redacted count) | |
| Notes | |

## Tool inventory (paste redacted list)

```
(list every MCP tool name available in your session)
```

## Sample chain excerpt (redact balances)

```
(paste one XSP chain snippet — strikes/DTE only)
```

## Sign-off

- [ ] Read-only session only — no orders placed during audit
- [ ] `RH_AGENTIC_ACCOUNT_ID` set in prod `.env` (full ID, not in git)
- [ ] Token exported to `.local/robinhood_mcp_token.json` on prod (mode 600)
