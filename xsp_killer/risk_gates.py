"""Paper-trading risk gates — daily loss cap before new entries.

Invariants:
- Daily paper loss cap is scale-aware via ``load_premium_scale``
  (effective_cap = cap × scale).
- Gates paper entries only — never places or routes live Robinhood orders.
- Consecutive losing paper exits halt new entries (streak ≥ max_consecutive_losses).
- Risk snapshot must include scale in cap-hit reason strings for soak diagnostics.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from xsp_killer.paper_economics import load_premium_scale

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


def _event_marker_ts(evt: dict[str, Any]) -> str:
    return str(evt.get("evaluated_at") or evt.get("exit_ts") or "")


def consecutive_losing_paper_exits(state: dict[str, Any]) -> int:
    """Count trailing consecutive losing paper exits (K79 blow-up flag)."""
    streak = 0
    reset_at = str(state.get("risk_streak_reset_at") or "")
    events = [e for e in (state.get("paper_events") or []) if isinstance(e, dict)]
    for evt in reversed(events):
        evt_ts = _event_marker_ts(evt)
        if reset_at and (not evt_ts or evt_ts < reset_at):
            break
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


def risk_gate_snapshot(
    state: dict[str, Any],
    *,
    rules_path: Path | None = None,
    premium_scale: float | None = None,
) -> dict[str, Any]:
    """Structured risk-gate diagnostic for entry logs and health soak."""
    if os.getenv("XSP_LANE_A_RISK_GATE", "true").strip().lower() in (
        "0",
        "false",
        "no",
    ):
        return {"enabled": False, "allowed": True, "reason": None}

    if premium_scale is not None:
        scale = premium_scale
    else:
        scale = load_premium_scale(rules_path)
    cap = _daily_loss_cap_usd()
    effective_cap = round(cap * scale, 2)
    pnl = realized_pnl_today(state)
    max_losses = _max_consecutive_losses()
    streak = consecutive_losing_paper_exits(state)
    allowed = True
    reason: str | None = None
    if pnl <= -effective_cap:
        allowed = False
        reason = (
            "daily paper loss cap hit "
            f"({pnl:.2f} <= -{effective_cap:.0f}; scale={scale:.2f}x)"
        )
    elif streak >= max_losses:
        allowed = False
        reason = f"consecutive paper losses halt ({streak} >= {max_losses})"
    return {
        "enabled": True,
        "allowed": allowed,
        "reason": reason,
        "scale": round(scale, 4),
        "cap_usd": cap,
        "effective_cap_usd": effective_cap,
        "pnl_today_usd": pnl,
        "consecutive_losses": streak,
        "max_consecutive_losses": max_losses,
    }


def entry_allowed_by_risk(
    state: dict[str, Any],
    *,
    rules_path: Path | None = None,
    premium_scale: float | None = None,
) -> tuple[bool, str | None]:
    snap = risk_gate_snapshot(state, rules_path=rules_path, premium_scale=premium_scale)
    if not snap.get("enabled", True):
        return True, None
    if snap.get("allowed"):
        return True, None
    return False, snap.get("reason")
