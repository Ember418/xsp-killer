"""Thin adapter: XSP killer → Cemini K37 reviewer v2 shadow (log-only).

Does NOT alter strategy gates (conductor_shadow RED / prior-day, live flags,
lane_a_rules regime_gate). Never blocks place/close — Phase 2 enforce stays off.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger("xsp_killer.k37_reviewer_shadow")

_CEMINI_ROOT = Path("/opt/cemini")
if str(_CEMINI_ROOT) not in sys.path:
    sys.path.insert(0, str(_CEMINI_ROOT))


def shadow_review_order(
    tool_name: str,
    tool_args: Mapping[str, Any] | None = None,
    *,
    lane_id: str = "lane_a",
    trajectory_id: str | None = None,
) -> dict[str, Any] | None:
    """Best-effort shadow review. Always returns None on import/runtime failure."""
    try:
        from conductor.reviewer.shadow_middleware import (
            shadow_review_provisional_call,
        )
    except Exception as exc:  # noqa: BLE001 — fail-open; never block EMS
        logger.debug("k37 shadow import failed (fail-open): %s", exc)
        return None

    try:
        return shadow_review_provisional_call(
            tool_name,
            tool_args,
            lane_id=lane_id,
            trajectory_id=trajectory_id,
            source="xsp-killer",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("k37 shadow call failed (fail-open): %s", exc)
        return None
