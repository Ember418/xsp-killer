"""XSP Lane A overnight swing monitor — Phase 0 alerts only (K116).

Polls Robinhood open SPX/XSP calls, evaluates exit rules, emits alerts.
No auto-close until Phase 1 gates pass.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import yaml

logger = logging.getLogger("xsp_killer.xsp_lane_a")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = ROOT / "config" / "lane_a_rules.yaml"
DEFAULT_STATE = ROOT / "briefs" / "xsp-lane-a-state.json"
DEFAULT_OUT = ROOT / "briefs" / "xsp-lane-a-monitor-latest.json"
DEFAULT_PAPER_LOG = ROOT / "logs" / "xsp_lane_a_paper.jsonl"
DEFAULT_PAPER_BRIEF = ROOT / "briefs" / "xsp-lane-a-paper-pnl-latest.json"

ET = ZoneInfo("America/New_York")
ExitReason = Literal[
    "stop_loss",
    "take_profit",
    "upper_bb_rejection",
    "time_stop",
    "manual",
]


@dataclass
class LaneRules:
    lane: str
    dte_min: int
    dte_max: int
    exclude_expiry_month: tuple[str, ...]
    chain_symbols: tuple[str, ...]
    stop_loss_pct: float
    take_profit_pct: float
    sell_eval_start_et: time
    sell_deadline_et: time
    no_sell_start_et: time
    no_sell_end_et: time
    require_upper_bb_for_take_profit: bool
    logic_version: str
    regime_gate: str = "GREEN"

    @classmethod
    def from_yaml(cls, path: Path) -> LaneRules:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        entry = data.get("entry") or {}
        exit_cfg = data.get("exit") or {}
        logging_cfg = data.get("logging") or {}

        def _parse_time(s: str) -> time:
            h, m = s.split(":")
            return time(int(h), int(m))

        return cls(
            lane=str(data.get("lane", "A")),
            dte_min=int(entry.get("dte_min", 14)),
            dte_max=int(entry.get("dte_max", 60)),
            exclude_expiry_month=tuple(str(x) for x in entry.get("exclude_expiry_month") or []),
            chain_symbols=tuple(str(x).upper() for x in entry.get("chain_symbols") or ["SPX", "XSP"]),
            stop_loss_pct=float(exit_cfg.get("stop_loss_pct", 0.20)),
            take_profit_pct=float(exit_cfg.get("take_profit_pct", 0.20)),
            sell_eval_start_et=_parse_time(str(exit_cfg.get("sell_eval_start_et", "09:30"))),
            sell_deadline_et=_parse_time(str(exit_cfg.get("sell_deadline_et", "10:00"))),
            no_sell_start_et=_parse_time(str(exit_cfg.get("no_sell_start_et", "08:30"))),
            no_sell_end_et=_parse_time(str(exit_cfg.get("no_sell_end_et", "09:30"))),
            require_upper_bb_for_take_profit=bool(
                exit_cfg.get("require_upper_bb_for_take_profit", True)
            ),
            logic_version=str(logging_cfg.get("logic_version", "xsp_lane_a_v2")),
            regime_gate=str(entry.get("regime_gate", "GREEN")),
        )


@dataclass
class LaneAPosition:
    position_id: str
    chain_symbol: str
    option_type: str
    strike: float
    expiration_date: date
    quantity: float
    average_price: float
    mark_price: float | None
    dte: int
    lane: str = "A"
    entry_ts: str | None = None
    delta_at_entry: float | None = None
    entry_mid_premium: float | None = None
    pnl_usd: float | None = None
    pnl_per_contract: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["expiration_date"] = self.expiration_date.isoformat()
        return d


@dataclass
class ExitAlert:
    position_id: str
    exit_reason: str
    message: str
    pnl_usd: float | None
    pnl_per_contract: float | None
    would_auto_close: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MonitorReport:
    evaluated_at: str
    phase: int
    logic_version: str
    regime: str | None
    regime_allows_new_risk: bool
    positions: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    rh_connected: bool = False
    rh_poll_skipped: bool = False
    paper_mode: str = "hypothetical"
    paper_mtm_usd: float | None = None
    paper_hypothetical_exits: list[dict[str, Any]] = field(default_factory=list)
    ta_snapshot: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _state_lock(path: Path):
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = lock_path.open("a+", encoding="utf-8")
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    return fh


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"positions": {}}
    lock = _state_lock(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"positions": {}}
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _state_lock(path)
    try:
        path.write_text(json.dumps(state, indent=2) + chr(10), encoding="utf-8")
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


def parse_expiration(raw: str) -> date | None:
    if not raw:
        return None
    s = str(raw)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def compute_dte(expiration: date, *, today: date | None = None) -> int:
    ref = today or datetime.now(ET).date()
    return (expiration - ref).days


def is_lane_a_contract(
    *,
    chain_symbol: str,
    option_type: str,
    expiration: date,
    rules: LaneRules,
    today: date | None = None,
) -> bool:
    sym = (chain_symbol or "").upper()
    if sym not in rules.chain_symbols:
        return False
    if (option_type or "").lower() != "call":
        return False
    month = f"{expiration.month:02d}"
    if month in rules.exclude_expiry_month:
        return False
    dte = compute_dte(expiration, today=today)
    return rules.dte_min <= dte <= rules.dte_max


def is_lane_a_monitor_contract(
    *,
    chain_symbol: str,
    option_type: str,
    expiration: date,
    rules: LaneRules,
    today: date | None = None,
) -> bool:
    """Exit monitoring — keep open holds even when DTE drops below entry dte_min."""
    sym = (chain_symbol or "").upper()
    if sym not in rules.chain_symbols:
        return False
    if (option_type or "").lower() != "call":
        return False
    month = f"{expiration.month:02d}"
    if month in rules.exclude_expiry_month:
        return False
    dte = compute_dte(expiration, today=today)
    return 0 <= dte <= rules.dte_max


def classify_position(
    raw: dict[str, Any],
    rules: LaneRules,
    *,
    for_monitor: bool = False,
    today: date | None = None,
) -> LaneAPosition | None:
    chain = str(raw.get("chain_symbol") or raw.get("symbol") or "").upper()
    opt_type = str(raw.get("type") or raw.get("option_type") or "").lower()
    exp = parse_expiration(str(raw.get("expiration_date") or raw.get("expiration") or ""))
    if exp is None:
        return None
    eligible = (
        is_lane_a_monitor_contract(
            chain_symbol=chain, option_type=opt_type, expiration=exp, rules=rules, today=today
        )
        if for_monitor
        else is_lane_a_contract(
            chain_symbol=chain, option_type=opt_type, expiration=exp, rules=rules, today=today
        )
    )
    if not eligible:
        return None
    qty = float(raw.get("quantity") or raw.get("qty") or 0)
    if qty <= 0:
        return None
    avg = float(raw.get("average_price") or raw.get("avg_price") or 0)
    mark_raw = raw.get("mark_price") or raw.get("mark") or raw.get("adjusted_mark_price")
    mark = float(mark_raw) if mark_raw is not None else None
    pos_id = str(raw.get("id") or raw.get("option_id") or raw.get("url") or f"{chain}:{exp}:{raw.get('strike_price')}")
    strike = float(raw.get("strike_price") or raw.get("strike") or 0)
    entry_mid = raw.get("entry_mid_premium")
    pos = LaneAPosition(
        position_id=pos_id,
        chain_symbol=chain,
        option_type=opt_type,
        strike=strike,
        expiration_date=exp,
        quantity=qty,
        average_price=avg,
        mark_price=mark,
        dte=compute_dte(exp),
        entry_mid_premium=float(entry_mid) if entry_mid is not None else (avg if avg > 0 else None),
        pnl_usd=None,
        pnl_per_contract=None,
    )
    _attach_economics_pnl(pos)
    return pos


def read_regime() -> tuple[str | None, bool]:
    """Read regime from intel bus, else local macro_regime fallback."""
    regime: str | None = None
    try:
        from xsp_killer.intel import IntelReader

        snap = IntelReader.read("intel:playbook_snapshot")
        if isinstance(snap, dict):
            regime = str(snap.get("regime") or snap.get("status") or "").upper() or None
        elif isinstance(snap, str):
            regime = snap.upper()
    except Exception as exc:
        logger.warning("playbook_snapshot read failed: %s", exc)

    if not regime:
        try:
            from xsp_killer.macro_regime import classify_regime

            state = classify_regime()
            regime = state.regime
            logger.info("macro_regime fallback: %s (%s)", regime, state.reason)
        except Exception as exc:
            logger.warning("macro_regime fallback failed: %s", exc)
            return "UNKNOWN", False

    if regime in ("YELLOW", "RED"):
        return regime, False
    if regime == "GREEN":
        return regime, True
    return regime, False


def in_no_sell_window(now: datetime, rules: LaneRules) -> bool:
    t = now.time()
    return rules.no_sell_start_et <= t < rules.no_sell_end_et


def in_sell_window(now: datetime, rules: LaneRules) -> bool:
    t = now.time()
    return rules.sell_eval_start_et <= t <= rules.sell_deadline_et


def _position_return_pct(pos: LaneAPosition) -> float | None:
    entry = pos.entry_mid_premium if pos.entry_mid_premium is not None else pos.average_price
    if entry <= 0 or pos.mark_price is None:
        return None
    return (pos.mark_price - entry) / entry


def _attach_economics_pnl(pos: LaneAPosition, *, rules_path: Path | None = None) -> None:
    if pos.mark_price is None or pos.average_price <= 0:
        return
    try:
        from xsp_killer.paper_economics import PaperEconomics, pnl_from_entry_fill, pnl_per_contract

        econ = PaperEconomics.from_yaml(rules_path or DEFAULT_RULES)
        entry_mid = pos.entry_mid_premium
        if entry_mid is not None and abs(pos.average_price - entry_mid) > 1e-6:
            pos.pnl_per_contract = pnl_from_entry_fill(
                entry_fill=pos.average_price,
                exit_mid=pos.mark_price,
                econ=econ,
            )
        elif entry_mid is not None:
            pos.pnl_per_contract = pnl_per_contract(
                entry_mid=entry_mid,
                exit_mid=pos.mark_price,
                econ=econ,
            )
        else:
            pos.pnl_per_contract = pnl_from_entry_fill(
                entry_fill=pos.average_price,
                exit_mid=pos.mark_price,
                econ=econ,
            )
        pos.pnl_usd = pos.pnl_per_contract * pos.quantity
    except Exception as exc:
        logger.warning("economics pnl failed: %s", exc)




def _entry_date_et(entry_ts: str | None) -> date | None:
    """Calendar entry date in America/New_York (for overnight hold logic)."""
    if not entry_ts:
        return None
    try:
        ts = datetime.fromisoformat(str(entry_ts).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(ET).date()
    except (ValueError, TypeError):
        return None


def evaluate_exit_alerts(
    pos: LaneAPosition,
    rules: LaneRules,
    *,
    now_et: datetime | None = None,
    ta_signal: Any | None = None,
    suppress_morning_cut_dte: int | None = None,
) -> list[ExitAlert]:
    """Mentor v2: no-sell 08:30–09:30; SL anytime after; TP in sell window; time-stop at 10:00."""
    _ = suppress_morning_cut_dte
    now = now_et or datetime.now(ET)
    alerts: list[ExitAlert] = []

    if in_no_sell_window(now, rules):
        return alerts

    ret_pct = _position_return_pct(pos)
    if ret_pct is None:
        return alerts

    pnl_c = pos.pnl_per_contract
    pnl = pos.pnl_usd

    if ret_pct <= -rules.stop_loss_pct:
        alerts.append(
            ExitAlert(
                position_id=pos.position_id,
                exit_reason="stop_loss",
                message=f"Stop loss {ret_pct * 100:.1f}% (limit -{rules.stop_loss_pct * 100:.0f}%)",
                pnl_usd=pnl,
                pnl_per_contract=pnl_c,
            )
        )
        return alerts

    in_sell = in_sell_window(now, rules)

    if in_sell and ret_pct >= rules.take_profit_pct:
        can_take = True
        if rules.require_upper_bb_for_take_profit and ta_signal is not None:
            touched = getattr(ta_signal, "upper_bb_touched", False)
            rejected = getattr(ta_signal, "exit_ok", False)
            if not touched and not rejected:
                can_take = False
        if can_take:
            reason: ExitReason = (
                "upper_bb_rejection"
                if ta_signal is not None and getattr(ta_signal, "exit_ok", False)
                else "take_profit"
            )
            detail = getattr(ta_signal, "detail", "") if ta_signal else ""
            alerts.append(
                ExitAlert(
                    position_id=pos.position_id,
                    exit_reason=reason,
                    message=(
                        f"Take profit {ret_pct * 100:.1f}% (target +{rules.take_profit_pct * 100:.0f}%)"
                        + (f" — {detail}" if detail else "")
                    ),
                    pnl_usd=pnl,
                    pnl_per_contract=pnl_c,
                )
            )
            return alerts

    entry_day = _entry_date_et(pos.entry_ts)
    if entry_day is not None and entry_day < now.date() and now.time() >= rules.sell_deadline_et:
        alerts.append(
            ExitAlert(
                position_id=pos.position_id,
                exit_reason="time_stop",
                message=(
                    f"Time stop at {rules.sell_deadline_et.strftime('%H:%M')} ET "
                    f"(return {ret_pct * 100:.1f}%)"
                ),
                pnl_usd=pnl,
                pnl_per_contract=pnl_c,
            )
        )

    return alerts


def merge_state_tags(positions: list[LaneAPosition], state: dict[str, Any]) -> None:
    tags = (state.get("positions") or {}) if isinstance(state, dict) else {}
    for pos in positions:
        tag = tags.get(pos.position_id) or {}
        if tag.get("lane"):
            pos.lane = str(tag["lane"])
        if tag.get("entry_ts"):
            pos.entry_ts = str(tag["entry_ts"])
        if tag.get("delta_at_entry") is not None:
            pos.delta_at_entry = float(tag["delta_at_entry"])


def paper_positions_to_lane(
    raw_positions: list[dict[str, Any]],
    rules: LaneRules,
    *,
    today: date | None = None,
) -> list[LaneAPosition]:
    """Convert persisted paper positions into LaneAPosition for exit evaluation."""
    out: list[LaneAPosition] = []
    for raw in raw_positions:
        exp = parse_expiration(str(raw.get("expiration_date") or ""))
        if exp is None:
            continue
        chain = str(raw.get("chain_symbol") or "XSP").upper()
        opt_type = str(raw.get("option_type") or "call").lower()
        if not is_lane_a_monitor_contract(
            chain_symbol=chain,
            option_type=opt_type,
            expiration=exp,
            rules=rules,
            today=today,
        ):
            continue
        qty = float(raw.get("quantity") or 0)
        if qty <= 0:
            continue
        avg = float(raw.get("average_price") or 0)
        mark_raw = raw.get("mark_price") or raw.get("mark")
        mark = float(mark_raw) if mark_raw is not None else None
        entry_mid_raw = raw.get("entry_mid_premium")
        entry_mid = float(entry_mid_raw) if entry_mid_raw is not None else (avg if avg > 0 else None)
        pos_id = str(raw.get("position_id") or "")
        strike = float(raw.get("strike") or 0)
        lane_pos = LaneAPosition(
                position_id=pos_id,
                chain_symbol=chain,
                option_type=opt_type,
                strike=strike,
                expiration_date=exp,
                quantity=qty,
                average_price=avg,
                mark_price=mark,
                dte=compute_dte(exp, today=today),
                lane=str(raw.get("lane") or "A"),
                entry_ts=raw.get("entry_ts"),
                delta_at_entry=raw.get("delta_at_entry"),
                entry_mid_premium=entry_mid,
                pnl_usd=None,
                pnl_per_contract=None,
            )
        _attach_economics_pnl(lane_pos)
        out.append(lane_pos)
    return out


def refresh_paper_marks(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Update mark_price on open paper positions via SPY chain proxy."""
    try:
        from xsp_killer.lane_a_entry import fetch_spy_call_quote
    except ImportError:
        return positions
    updated: list[dict[str, Any]] = []
    for raw in positions:
        pos = dict(raw)
        exp = parse_expiration(str(pos.get("expiration_date") or ""))
        strike = float(pos.get("strike") or 0)
        if exp is None or strike <= 0:
            updated.append(pos)
            continue
        from xsp_killer.paper_economics import SPY_TO_XSP_PREMIUM_SCALE

        mid, _ = fetch_spy_call_quote(strike / 10.0, exp)
        if mid is not None:
            pos["mark_price"] = round(mid * SPY_TO_XSP_PREMIUM_SCALE, 4)
        updated.append(pos)
    return updated


def close_paper_positions_on_exit(
    state: dict[str, Any],
    alerts: list[ExitAlert],
    *,
    evaluated_at: str,
    logic_version: str,
) -> list[dict[str, Any]]:
    """Mark paper positions closed on first exit alert of the session."""
    paper = state.get("paper_positions") or {}
    if not isinstance(paper, dict):
        return []
    closed: list[dict[str, Any]] = []
    seen_ids = {a.position_id for a in alerts}
    for pos_id, raw in list(paper.items()):
        if not isinstance(raw, dict) or raw.get("status") != "open":
            continue
        if pos_id not in seen_ids:
            continue
        alert = next((a for a in alerts if a.position_id == pos_id), None)
        raw = dict(raw)
        raw["status"] = "closed"
        raw["exit_ts"] = evaluated_at
        raw["exit_reason"] = alert.exit_reason if alert else "manual"
        raw["exit_pnl_usd"] = alert.pnl_usd if alert else None
        raw["exit_pnl_per_contract"] = alert.pnl_per_contract if alert else None
        paper[pos_id] = raw
        closed.append(raw)
        events = list(state.get("paper_events") or [])
        day_key = evaluated_at[:10]
        seen = {
            (e.get("position_id"), e.get("exit_reason"), (e.get("evaluated_at") or "")[:10])
            for e in events
        }
        evt_key = (pos_id, raw["exit_reason"], day_key)
        if evt_key not in seen:
            events.append(
                {
                    "evaluated_at": evaluated_at,
                    "position_id": pos_id,
                    "exit_reason": raw["exit_reason"],
                    "paper_pnl_usd": raw.get("exit_pnl_usd"),
                    "paper_pnl_per_contract": raw.get("exit_pnl_per_contract"),
                    "logic_version": logic_version,
                    "paper_mode": "automated_paper_close",
                    "entry_ts": raw.get("entry_ts"),
                }
            )
            state["paper_events"] = events[-500:]
    state["paper_positions"] = paper
    return closed


def load_open_paper_positions(state: dict[str, Any]) -> list[dict[str, Any]]:
    raw = state.get("paper_positions") or {}
    if not isinstance(raw, dict):
        return []
    open_rows = [p for p in raw.values() if isinstance(p, dict) and p.get("status", "open") == "open"]
    return refresh_paper_marks(open_rows)


def rh_poll_enabled() -> bool:
    """Poll Robinhood only when explicitly enabled (no positions → skip auth)."""
    return os.getenv("XSP_LANE_A_RH_POLL", "false").strip().lower() in ("1", "true", "yes")


def fetch_robinhood_option_positions() -> tuple[list[dict[str, Any]], str | None]:
    """Return raw RH open option positions via RobinhoodAdapter."""
    if not rh_poll_enabled():
        return [], None
    import asyncio

    user = os.getenv("RH_USERNAME") or os.getenv("ROBINHOOD_USERNAME") or os.getenv("ROBINHOOD_USER")
    pw = os.getenv("RH_PASSWORD") or os.getenv("ROBINHOOD_PASSWORD") or os.getenv("ROBINHOOD_PASS")
    if not user or not pw:
        return [], "missing RH_USERNAME/RH_PASSWORD"
    try:
        import robin_stocks.robinhood as r

        session = r.login(user, pw, store_session=True)
        if not session:
            return [], "robinhood login failed — check RH_USERNAME/RH_PASSWORD or MFA"

        from xsp_killer.robinhood import RobinhoodAdapter

        adapter = RobinhoodAdapter(user, pw)
        rows = asyncio.run(adapter.get_open_option_positions(chain_symbols=("SPX", "XSP")))
        return rows, None
    except Exception as exc:
        return [], str(exc)


def append_paper_pnl_log(
    *,
    report: MonitorReport,
    classified: list[LaneAPosition],
    alerts: list[ExitAlert],
    log_path: Path | None = None,
) -> None:
    """Append hypothetical paper PnL row (no RH capital required for logging)."""
    path = log_path or DEFAULT_PAPER_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    mtm = sum(p.pnl_usd or 0.0 for p in classified)
    report.paper_mtm_usd = mtm if classified else 0.0
    row = {
        "ts": report.evaluated_at,
        "event": "monitor_eval",
        "logic_version": report.logic_version,
        "phase": report.phase,
        "paper_mode": report.paper_mode,
        "positions_n": len(classified),
        "paper_mtm_usd": report.paper_mtm_usd,
        "alerts_n": len(alerts),
        "positions": [p.to_dict() for p in classified],
        "alerts": [a.to_dict() for a in alerts],
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def record_paper_exit_signals(
    state: dict[str, Any],
    alerts: list[ExitAlert],
    *,
    evaluated_at: str,
    logic_version: str,
) -> list[dict[str, Any]]:
    """First alert per position+reason per ET day → hypothetical paper exit."""
    events: list[dict[str, Any]] = list(state.get("paper_events") or [])
    seen = {
        (e.get("position_id"), e.get("exit_reason"), (e.get("evaluated_at") or "")[:10])
        for e in events
    }
    new_exits: list[dict[str, Any]] = []
    day_key = evaluated_at[:10]
    for alert in alerts:
        key = (alert.position_id, alert.exit_reason, day_key)
        if key in seen:
            continue
        evt = {
            "evaluated_at": evaluated_at,
            "position_id": alert.position_id,
            "exit_reason": alert.exit_reason,
            "paper_pnl_usd": alert.pnl_usd,
            "paper_pnl_per_contract": alert.pnl_per_contract,
            "logic_version": logic_version,
            "paper_mode": "hypothetical_would_close",
        }
        events.append(evt)
        new_exits.append(evt)
        seen.add(key)
    if new_exits:
        state["paper_events"] = events[-500:]
    return new_exits


def write_paper_pnl_brief(
    state: dict[str, Any],
    *,
    report: MonitorReport | None = None,
    out_path: Path | None = None,
) -> Path:
    """Roll up hypothetical paper exits + latest MTM into brief JSON."""
    events = list(state.get("paper_events") or [])
    resolved_pnl = sum(float(e.get("paper_pnl_usd") or 0) for e in events)
    path = out_path or DEFAULT_PAPER_BRIEF
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "logic_version": (report.logic_version if report else None) or "xsp_lane_a_v1",
        "paper_mode": "hypothetical",
        "note": "Paper lane — BB/VWAP mentor playbook + morning risk cuts; no RH orders",
        "open_positions_mtm_usd": report.paper_mtm_usd if report else None,
        "hypothetical_exits_n": len(events),
        "hypothetical_realized_pnl_usd": round(resolved_pnl, 2),
        "latest_evaluated_at": report.evaluated_at if report else None,
        "recent_exits": events[-10:],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def run_monitor(
    *,
    rules_path: Path | None = None,
    state_path: Path | None = None,
    positions_override: list[dict[str, Any]] | None = None,
    now_et: datetime | None = None,
    publish_intel: bool = True,
    ta_signal: Any | None = None,
    fetch_ta: bool = True,
) -> MonitorReport:
    rules = LaneRules.from_yaml(rules_path or DEFAULT_RULES)
    state = load_state(state_path or DEFAULT_STATE)
    regime, regime_ok = read_regime()

    suppress_dte: int | None = None
    if fetch_ta or ta_signal is not None:
        try:
            from xsp_killer.lane_a_ta import TaRules, evaluate_ta_signals

            ta_rules = TaRules.from_yaml(rules_path or DEFAULT_RULES)
            suppress_dte = ta_rules.suppress_morning_cut_dte_gte
            if ta_signal is None and fetch_ta:
                ta_signal = evaluate_ta_signals(ta_rules)
        except Exception as exc:
            ta_signal = None
            logger.warning("TA evaluation skipped: %s", exc)

    report = MonitorReport(
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        phase=0,
        logic_version=rules.logic_version,
        regime=regime,
        regime_allows_new_risk=regime_ok,
    )
    if ta_signal is not None and hasattr(ta_signal, "to_dict"):
        report.ta_snapshot = ta_signal.to_dict()

    raw_positions: list[dict[str, Any]]
    if positions_override is not None:
        raw_positions = positions_override
        report.rh_connected = True
    elif not rh_poll_enabled():
        raw_positions = []
        report.rh_poll_skipped = True
        paper_raw = load_open_paper_positions(state)
        if paper_raw:
            report.paper_mode = "automated_paper"
        for pr in paper_raw:
            # Persist refreshed marks back into state
            pid = pr.get("position_id")
            if pid and isinstance(state.get("paper_positions"), dict):
                state["paper_positions"][pid] = pr
    else:
        raw_positions, err = fetch_robinhood_option_positions()
        if err:
            report.errors.append(err)
        else:
            report.rh_connected = True

    today = (now_et or datetime.now(ET)).date()
    classified: list[LaneAPosition] = []
    for raw in raw_positions:
        pos = classify_position(raw, rules, for_monitor=True, today=today)
        if pos is not None:
            classified.append(pos)

    if not classified and report.rh_poll_skipped and not positions_override:
        classified = paper_positions_to_lane(load_open_paper_positions(state), rules, today=today)

    merge_state_tags(classified, state)
    report.positions = [p.to_dict() for p in classified]

    all_alerts: list[ExitAlert] = []
    for pos in classified:
        all_alerts.extend(
            evaluate_exit_alerts(
                pos,
                rules,
                now_et=now_et,
                ta_signal=ta_signal,
                suppress_morning_cut_dte=suppress_dte,
            )
        )

    report.alerts = [a.to_dict() for a in all_alerts]

    paper_positions_active = bool(state.get("paper_positions")) and report.rh_poll_skipped
    if paper_positions_active and not positions_override:
        closed_paper = close_paper_positions_on_exit(
            state,
            all_alerts,
            evaluated_at=report.evaluated_at,
            logic_version=rules.logic_version,
        )
        report.paper_hypothetical_exits = [
            {
                "evaluated_at": report.evaluated_at,
                "position_id": c.get("position_id"),
                "exit_reason": c.get("exit_reason"),
                "paper_pnl_usd": c.get("exit_pnl_usd"),
                "paper_pnl_per_contract": c.get("exit_pnl_per_contract"),
                "paper_mode": "automated_paper_close",
            }
            for c in closed_paper
        ]
    else:
        report.paper_hypothetical_exits = record_paper_exit_signals(
            state,
            all_alerts,
            evaluated_at=report.evaluated_at,
            logic_version=rules.logic_version,
        )
    append_paper_pnl_log(report=report, classified=classified, alerts=all_alerts)
    write_paper_pnl_brief(state, report=report)

    if publish_intel and all_alerts:
        try:
            from xsp_killer.intel import IntelPublisher

            IntelPublisher.publish(
                "intel:xsp_lane_a_alert",
                {
                    "evaluated_at": report.evaluated_at,
                    "alerts": report.alerts,
                    "positions_n": len(classified),
                    "logic_version": rules.logic_version,
                },
                source_system="xsp_lane_a_monitor",
                confidence=1.0,
                ttl=3600,
            )
        except Exception as exc:
            report.errors.append(f"intel publish failed: {exc}")

    # Persist state (position tags + paper_events)
    if classified:
        tags = state.setdefault("positions", {})
        for pos in classified:
            prev = tags.get(pos.position_id) or {}
            tags[pos.position_id] = {
                **prev,
                "lane": pos.lane,
                "last_seen": report.evaluated_at,
                "dte": pos.dte,
                "strike": pos.strike,
                "chain_symbol": pos.chain_symbol,
            }
    save_state(state_path or DEFAULT_STATE, state)

    return report


def write_report(report: MonitorReport, out_path: Path | None = None) -> Path:
    path = out_path or DEFAULT_OUT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path
