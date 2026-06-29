"""Unified Robinhood read path — Agentic MCP (preferred) or legacy robin_stocks."""

from __future__ import annotations

import os
from typing import Any

from xsp_killer.robinhood_mcp import fetch_option_positions_via_mcp, rh_mcp_enabled


def rh_poll_enabled() -> bool:
    """Legacy robin_stocks poll — explicit opt-in."""
    return os.getenv("XSP_LANE_A_RH_POLL", "false").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def rh_read_enabled() -> bool:
    """Any Robinhood read path enabled (MCP preferred over legacy)."""
    return rh_mcp_enabled() or rh_poll_enabled()


def fetch_robinhood_option_positions() -> tuple[list[dict[str, Any]], str | None]:
    """Return open XSP/SPX option positions via MCP or robin_stocks."""
    if rh_mcp_enabled():
        return fetch_option_positions_via_mcp()
    if not rh_poll_enabled():
        return [], None
    return _fetch_via_robin_stocks()


def _fetch_via_robin_stocks() -> tuple[list[dict[str, Any]], str | None]:
    import asyncio

    user = (
        os.getenv("RH_USERNAME")
        or os.getenv("ROBINHOOD_USERNAME")
        or os.getenv("ROBINHOOD_USER")
    )
    pw = (
        os.getenv("RH_PASSWORD")
        or os.getenv("ROBINHOOD_PASSWORD")
        or os.getenv("ROBINHOOD_PASS")
    )
    if not user or not pw:
        return [], "missing RH_USERNAME/RH_PASSWORD"
    try:
        import robin_stocks.robinhood as r

        session = r.login(user, pw, store_session=True)
        if not session:
            return [], "robinhood login failed — check RH_USERNAME/RH_PASSWORD or MFA"

        from xsp_killer.robinhood import RobinhoodAdapter

        adapter = RobinhoodAdapter(user, pw)
        rows = asyncio.run(
            adapter.get_open_option_positions(chain_symbols=("SPX", "XSP"))
        )
        for row in rows:
            if isinstance(row, dict):
                row["_source"] = "robin_stocks"
        return rows, None
    except Exception as exc:
        return [], str(exc)
