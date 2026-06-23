"""Shadow exit brackets — log prod cut vs counterfactual hold scenarios."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


@dataclass
class ShadowBracket:
    bracket_id: str
    label: str
    would_exit: bool
    exit_reason: str | None = None
    ret_pct: float | None = None
    pnl_usd: float | None = None
    thresholds_to_continue: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


@dataclass
class ShadowExitRecord:
    evaluated_at: str
    position_id: str
    actual_exit_reason: str
    actual_pnl_usd: float | None
    entry_mid_premium: float | None
    mark_at_exit: float | None
    mark_quote_stale: bool
    dte: int | None
    sessions_held: int
    brackets: list[ShadowBracket] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["brackets"] = [asdict(b) for b in self.brackets]
        return d


def _sessions_since_entry(entry_day: date | None, today: date) -> int:
    if entry_day is None:
        return 0
    return max(0, (today - entry_day).days)


def _recovery_pct_to_target(entry: float, mark: float | None, target_mult: float) -> float | None:
    if mark is None or entry <= 0 or mark <= 0:
        return None
    target = entry * target_mult
    if mark >= target:
        return 0.0
    return round((target - mark) / mark * 100.0, 2)


def evaluate_shadow_brackets(
    pos: Any,
    rules: Any,
    *,
    now_et: datetime,
    ta_signal: Any | None,
    suppress_morning_cut_dte: int | None,
    actual_alert: Any,
    evaluate_fn: Any,
) -> list[ShadowBracket]:
    """Compare prod exit to alternate rule brackets at the same mark snapshot."""
    from xsp_killer.lane_a_monitor import LaneRules, _entry_date_et, _position_return_pct

    entry = pos.entry_mid_premium if pos.entry_mid_premium is not None else pos.average_price
    mark = pos.mark_price
    ret = _position_return_pct(pos)
    entry_day = _entry_date_et(pos.entry_ts)
    today = now_et.date()
    sessions = _sessions_since_entry(entry_day, today)

    brackets: list[ShadowBracket] = []

    def _eval_with(**kwargs: Any) -> list[Any]:
        r = kwargs.pop("rules_override", rules)
        return evaluate_fn(
            pos,
            r,
            now_et=now_et,
            ta_signal=ta_signal,
            suppress_morning_cut_dte=kwargs.pop("suppress_morning_cut_dte", suppress_morning_cut_dte),
            **kwargs,
        )

    prod_alerts = _eval_with()
    prod_exit = prod_alerts[0].exit_reason if prod_alerts else None
    brackets.append(
        ShadowBracket(
            bracket_id="prod",
            label="Production rules (active)",
            would_exit=bool(prod_alerts),
            exit_reason=prod_exit,
            ret_pct=round(ret * 100, 2) if ret is not None else None,
            pnl_usd=pos.pnl_usd,
            notes=f"Actual fired: {actual_alert.exit_reason}",
        )
    )

    wide_rules = LaneRules(
        lane=rules.lane,
        dte_min=rules.dte_min,
        dte_max=rules.dte_max,
        exclude_expiry_month=rules.exclude_expiry_month,
        chain_symbols=rules.chain_symbols,
        stop_loss_pct=0.30,
        take_profit_pct=rules.take_profit_pct,
        sell_eval_start_et=rules.sell_eval_start_et,
        sell_deadline_et=rules.sell_deadline_et,
        no_sell_start_et=rules.no_sell_start_et,
        no_sell_end_et=rules.no_sell_end_et,
        require_upper_bb_for_take_profit=rules.require_upper_bb_for_take_profit,
        logic_version=rules.logic_version,
        regime_gate=rules.regime_gate,
    )
    wide_alerts = evaluate_fn(
        pos, wide_rules, now_et=now_et, ta_signal=ta_signal, suppress_morning_cut_dte=suppress_morning_cut_dte
    )
    sl_remaining = None
    if ret is not None and ret > -0.30:
        sl_remaining = round((0.30 + ret) * 100, 2)
    brackets.append(
        ShadowBracket(
            bracket_id="wide_sl_30",
            label="Wide stop 30% (variant-style)",
            would_exit=bool(wide_alerts),
            exit_reason=wide_alerts[0].exit_reason if wide_alerts else None,
            ret_pct=round(ret * 100, 2) if ret is not None else None,
            pnl_usd=pos.pnl_usd if not wide_alerts else wide_alerts[0].pnl_usd,
            thresholds_to_continue={
                "stop_loss_pct_remaining": sl_remaining,
                "need_premium_recovery_to_breakeven_pct": _recovery_pct_to_target(entry, mark, 1.0),
            },
            notes="Would survive today's cut if stop were 30% instead of 20%" if not wide_alerts else "",
        )
    )

    no_cut_alerts = evaluate_fn(
        pos,
        rules,
        now_et=now_et,
        ta_signal=ta_signal,
        suppress_morning_cut_dte=14,
    )
    brackets.append(
        ShadowBracket(
            bracket_id="no_morning_cut_14dte",
            label="Suppress 10:00 time_stop for DTE≥14",
            would_exit=bool(no_cut_alerts),
            exit_reason=no_cut_alerts[0].exit_reason if no_cut_alerts else None,
            ret_pct=round(ret * 100, 2) if ret is not None else None,
            thresholds_to_continue={
                "would_skip_time_stop": pos.dte is not None and pos.dte >= 14,
                "need_premium_recovery_to_breakeven_pct": _recovery_pct_to_target(entry, mark, 1.0),
                "need_premium_recovery_to_tp_20pct": _recovery_pct_to_target(entry, mark, 1.20),
            },
            notes="Hold through morning cut; exit only on SL/TP/BB" if not no_cut_alerts else "",
        )
    )

    for defer_days in (1, 3, 5):
        if entry_day is None:
            continue
        defer_until = entry_day + timedelta(days=defer_days)
        still_inside_hold = today < defer_until or (
            today == defer_until and now_et.time() < rules.sell_deadline_et
        )
        deferred_now = still_inside_hold and actual_alert.exit_reason == "time_stop"
        brackets.append(
            ShadowBracket(
                bracket_id=f"defer_morning_cut_{defer_days}d",
                label=f"Defer time_stop until entry+{defer_days} sessions",
                would_exit=not still_inside_hold and actual_alert.exit_reason == "time_stop",
                exit_reason=None if still_inside_hold else actual_alert.exit_reason,
                ret_pct=round(ret * 100, 2) if ret is not None else None,
                thresholds_to_continue={
                    "sessions_held": sessions,
                    "sessions_remaining": max(0, defer_days - sessions),
                    "calendar_days_until_cut": max(0, (defer_until - today).days),
                    "need_premium_recovery_to_breakeven_pct": _recovery_pct_to_target(entry, mark, 1.0),
                    "need_premium_recovery_to_tp_20pct": _recovery_pct_to_target(entry, mark, 1.20),
                    "need_spy_overnight_bounce_note": (
                        "Red day cut may be premature; bracket keeps position open to test recovery"
                    ),
                },
                notes=(
                    "Would NOT time-stop yet under deferred hold"
                    if deferred_now or still_inside_hold
                    else f"Would time-stop after {defer_days}d hold window"
                ),
            )
        )

    return brackets


def build_shadow_exit_record(
    pos: Any,
    rules: Any,
    *,
    now_et: datetime,
    ta_signal: Any | None,
    suppress_morning_cut_dte: int | None,
    actual_alert: Any,
    evaluated_at: str,
    evaluate_fn: Any,
) -> ShadowExitRecord:
    from xsp_killer.lane_a_monitor import _entry_date_et

    entry_day = _entry_date_et(pos.entry_ts)
    today = now_et.date()
    sessions = max(0, (today - entry_day).days) if entry_day else 0

    return ShadowExitRecord(
        evaluated_at=evaluated_at,
        position_id=pos.position_id,
        actual_exit_reason=actual_alert.exit_reason,
        actual_pnl_usd=actual_alert.pnl_usd,
        entry_mid_premium=pos.entry_mid_premium,
        mark_at_exit=pos.mark_price,
        mark_quote_stale=bool(pos.mark_quote_stale),
        dte=pos.dte,
        sessions_held=sessions,
        brackets=evaluate_shadow_brackets(
            pos,
            rules,
            now_et=now_et,
            ta_signal=ta_signal,
            suppress_morning_cut_dte=suppress_morning_cut_dte,
            actual_alert=actual_alert,
            evaluate_fn=evaluate_fn,
        ),
    )


def append_shadow_exit_log(
    record: ShadowExitRecord,
    *,
    state: dict[str, Any],
    log_path: Any | None = None,
) -> None:
    import json
    from pathlib import Path

    payload = record.to_dict()
    events = list(state.get("paper_shadow_events") or [])
    events.append(payload)
    state["paper_shadow_events"] = events[-300:]

    path = log_path or Path(__file__).resolve().parents[1] / "logs" / "xsp_lane_a_shadow_exits.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")
