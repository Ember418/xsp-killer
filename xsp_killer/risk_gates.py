"""Paper-trading risk gates — daily loss cap before new entries."""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / "briefs" / "xsp-lane-a-state.json"


def _daily_loss_cap_usd() -> float:
    raw = os.getenv("XSP_LANE_A_DAILY_LOSS_CAP_USD", "500")
    try:
        return float(raw)
    except ValueError:
        return 500.0


def _max_consecutive_losses() -> int:
    raw = os.getenv("XSP_LANE_A_MAX_CONSECUTIVE_LOSSES", "3")
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


def consecutive_losing_paper_exits(state: dict[str, Any]) -> int:
    """Count trailing consecutive losing paper exits (K79 blow-up flag)."""
    streak = 0
    events = [e for e in (state.get("paper_events") or []) if isinstance(e, dict)]
    for evt in reversed(events):
        raw_pnl = evt.get("paper_pnl_usd")
        if raw_pnl is None:
            continue
        try:
            pnl = float(raw_pnl)
        except (TypeError, ValueError):
            continue
        if pnl < 0:
            streak += 1
        elif pnl > 0:
            break
    return streak


def realized_pnl_today(state: dict[str, Any], *, day: date | None = None) -> float:
    target = day or datetime.now(ET).date()
    total = 0.0
    for evt in state.get("paper_events") or []:
        if not isinstance(evt, dict):
            continue
        ts = str(evt.get("evaluated_at") or evt.get("exit_ts") or "")[:10]
        if not ts:
            continue
        try:
            evt_day = date.fromisoformat(ts)
        except ValueError:
            continue
        if evt_day == target:
            total += float(evt.get("paper_pnl_usd") or 0)
    return round(total, 2)


def entry_allowed_by_risk(state: dict[str, Any]) -> tuple[bool, str | None]:
    if os.getenv("XSP_LANE_A_RISK_GATE", "true").strip().lower() in (
        "0",
        "false",
        "no",
    ):
        return True, None
    cap = _daily_loss_cap_usd()
    pnl = realized_pnl_today(state)
    if pnl <= -cap:
        return False, f"daily paper loss cap hit ({pnl:.2f} <= -{cap:.0f})"
    max_losses = _max_consecutive_losses()
    streak = consecutive_losing_paper_exits(state)
    if streak >= max_losses:
        return False, (
            f"consecutive paper losses halt ({streak} >= {max_losses})"
        )
    return True, None
