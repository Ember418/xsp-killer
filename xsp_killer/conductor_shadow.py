"""Shadow pre-trade review hook (Cemini conductor pattern, paper-only)."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("xsp_killer.conductor_shadow")


def shadow_review_entry(
    *,
    regime: str | None,
    prior_day_spy_return_pct: float | None,
    ta_detail: str | None,
    position: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    """Fail-open shadow reviewer — logs WARN blocks only on explicit RED + bad tape."""
    if os.getenv("XSP_LANE_A_CONDUCTOR_SHADOW", "true").strip().lower() in (
        "0",
        "false",
        "no",
    ):
        return True, None

    if regime == "RED":
        return False, "conductor_shadow: macro regime RED"

    if prior_day_spy_return_pct is not None and prior_day_spy_return_pct < -0.015:
        return False, "conductor_shadow: prior-day SPY down >1.5%"

    if position is not None:
        dte = position.get("dte_actual") or position.get("dte")
        if dte is not None and int(dte) < 14:
            return False, "conductor_shadow: DTE below 14"

    logger.info(
        "conductor_shadow PASS regime=%s prior_spy=%s ta=%s",
        regime,
        prior_day_spy_return_pct,
        (ta_detail or "")[:80],
    )
    return True, None
