"""Minimal Robinhood options poll for XSP Killer (optional live RH)."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger("xsp_killer.robinhood")


class RobinhoodAdapter:
    def __init__(
        self, username: str | None = None, password: str | None = None
    ) -> None:
        self.username = (
            username or os.getenv("RH_USERNAME") or os.getenv("ROBINHOOD_USERNAME")
        )
        self.password = (
            password or os.getenv("RH_PASSWORD") or os.getenv("ROBINHOOD_PASSWORD")
        )

    async def get_open_option_positions(
        self,
        *,
        chain_symbols: tuple[str, ...] | None = None,
        enrich_mark: bool = True,
    ) -> list[dict[str, Any]]:
        import robin_stocks.robinhood as r

        rows = await asyncio.to_thread(r.options.get_open_option_positions) or []
        allowed = {s.upper() for s in chain_symbols} if chain_symbols else None
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            chain = str(row.get("chain_symbol") or "").upper()
            if allowed is not None and chain not in allowed:
                continue
            enriched = dict(row)
            if enrich_mark:
                oid = row.get("option_id") or row.get("id")
                if oid:
                    try:
                        md = await asyncio.to_thread(
                            r.options.get_option_market_data_by_id, oid
                        )
                        if isinstance(md, list) and md:
                            md = md[0]
                        if isinstance(md, dict):
                            mark = md.get("adjusted_mark_price") or md.get("mark_price")
                            if mark is not None:
                                enriched["mark_price"] = mark
                    except Exception as exc:
                        logger.debug("mark lookup failed %s: %s", oid, exc)
            out.append(enriched)
        return out
