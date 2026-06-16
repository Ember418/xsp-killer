"""XSP Lane A paper entry — automated log-only entries in 15:45–16:00 ET window.

No Robinhood orders. Uses SPY option chain as XSP premium proxy for paper marks.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from xsp_killer.lane_a_monitor import (
    DEFAULT_PAPER_LOG,
    DEFAULT_RULES,
    DEFAULT_STATE,
    LaneRules,
    compute_dte,
    is_lane_a_contract,
    load_state,
    read_regime,
    run_monitor,
    save_state,
)
from xsp_killer.lane_a_ta import TaRules, TaSignal, evaluate_ta_signals, in_rth

logger = logging.getLogger("xsp_killer.xsp_lane_a_entry")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "briefs" / "xsp-lane-a-entry-latest.json"
ET = ZoneInfo("America/New_York")


@dataclass
class EntryRules:
    window_start_et: time
    window_end_et: time
    prior_day_spy_positive: bool
    max_open_positions: int
    quantity: float
    enabled: bool
    chain_symbol: str = "XSP"

    @classmethod
    def from_yaml(cls, path: Path) -> EntryRules:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        entry = data.get("entry") or {}
        paper = data.get("paper_entry") or {}

        def _parse_time(s: str) -> time:
            h, m = s.split(":")
            return time(int(h), int(m))

        return cls(
            window_start_et=_parse_time(str(entry.get("window_start_et", "15:45"))),
            window_end_et=_parse_time(str(entry.get("window_end_et", "16:00"))),
            prior_day_spy_positive=bool(entry.get("prior_day_spy_positive", True)),
            max_open_positions=int(paper.get("max_open_positions", 1)),
            quantity=float(paper.get("quantity", 1)),
            enabled=bool(paper.get("enabled", True)),
            chain_symbol=str(data.get("instrument", "XSP")).upper(),
        )


@dataclass
class EntryDecision:
    entered: bool
    evaluated_at: str
    logic_version: str
    in_window: bool
    regime: str | None
    regime_ok: bool
    prior_day_spy_return_pct: float | None
    prior_day_ok: bool
    skip_reason: str | None = None
    position: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    ta_snapshot: dict[str, Any] | None = None
    bb_entry_ok: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def paper_entry_enabled() -> bool:
    return os.getenv("XSP_LANE_A_PAPER_ENTRY", "true").strip().lower() in ("1", "true", "yes")


def in_entry_window(now_et: datetime, rules: EntryRules) -> bool:
    if now_et.weekday() >= 5:
        return False
    t = now_et.time()
    return rules.window_start_et <= t < rules.window_end_et


def open_paper_positions(state: dict[str, Any]) -> list[dict[str, Any]]:
    raw = state.get("paper_positions") or {}
    if not isinstance(raw, dict):
        return []
    out: list[dict[str, Any]] = []
    for pos in raw.values():
        if isinstance(pos, dict) and pos.get("status", "open") == "open":
            out.append(pos)
    return out


def already_entered_today(state: dict[str, Any], today: date) -> bool:
    for evt in state.get("entry_log") or []:
        if not isinstance(evt, dict):
            continue
        if evt.get("entered") and str(evt.get("evaluated_at", ""))[:10] == today.isoformat():
            return True
    return False


def fetch_spy_ohlcv() -> tuple[float | None, float | None, float | None]:
    """Return (prior_close, prior_open, prior_return_pct) for last completed session."""
    try:
        import yfinance as yf

        hist = yf.Ticker("SPY").history(period="5d", interval="1d", timeout=10)
        if hist is None or len(hist) < 2:
            return None, None, None
        prev = hist.iloc[-2]
        o = float(prev["Open"])
        c = float(prev["Close"])
        ret = ((c - o) / o * 100.0) if o else None
        return c, o, ret
    except Exception as exc:
        logger.warning("SPY OHLCV fetch failed: %s", exc)
        return None, None, None


def fetch_spx_proxy() -> float | None:
    try:
        import yfinance as yf

        for sym in ("^GSPC", "SPY"):
            hist = yf.Ticker(sym).history(period="2d", interval="1d", timeout=10)
            if hist is not None and not hist.empty:
                px = float(hist["Close"].iloc[-1])
                return px * 10.0 if sym == "SPY" else px
    except Exception as exc:
        logger.warning("SPX proxy fetch failed: %s", exc)
    return None


def pick_expiration(rules: LaneRules, *, today: date) -> date | None:
    try:
        import yfinance as yf

        expirations = yf.Ticker("SPY").options
    except Exception as exc:
        logger.warning("SPY options list failed: %s", exc)
        return None
    candidates: list[tuple[int, date]] = []
    for raw in expirations or []:
        try:
            exp = date.fromisoformat(str(raw)[:10])
        except ValueError:
            continue
        if not is_lane_a_contract(
            chain_symbol="XSP",
            option_type="call",
            expiration=exp,
            rules=rules,
            today=today,
        ):
            continue
        candidates.append((compute_dte(exp, today=today), exp))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def round_xsp_strike(spx_level: float) -> float:
    step = 5.0
    return round(spx_level / step) * step


def fetch_spy_call_quote(strike_spy: float, expiration: date) -> tuple[float | None, float | None]:
    """Mid premium and delta proxy from SPY chain (XSP price proxy)."""
    try:
        import pandas as pd
        import yfinance as yf

        chain = yf.Ticker("SPY").option_chain(expiration.isoformat())
        calls = chain.calls
        if calls is None or calls.empty:
            return None, None
        target = round(strike_spy)
        row = calls.loc[(calls["strike"] - target).abs().idxmin()]

        def _pos_float(val: Any) -> float | None:
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return None
            try:
                v = float(val)
            except (TypeError, ValueError):
                return None
            return v if v > 0 else None

        bid = _pos_float(row.get("bid"))
        ask = _pos_float(row.get("ask"))
        last = _pos_float(row.get("lastPrice"))
        mid = None
        if bid is not None and ask is not None:
            mid = (bid + ask) / 2.0
        elif last is not None:
            mid = last
        elif ask is not None:
            mid = ask
        elif bid is not None:
            mid = bid

        delta = _pos_float(row.get("delta"))
        return mid, delta
    except Exception as exc:
        logger.warning("SPY call quote failed: %s", exc)
        return None, None


def estimate_fallback_premium(spy_price: float, dte: int) -> float:
    """Conservative ATM paper premium when live quote unavailable (e.g. after hours)."""
    base = max(0.35, spy_price * 0.012)
    scale = max(0.6, min(1.4, (dte / 30.0) ** 0.5))
    return round(base * scale, 4)


def build_paper_position(
    *,
    rules: LaneRules,
    entry_rules: EntryRules,
    expiration: date,
    strike: float,
    premium: float,
    delta: float | None,
    evaluated_at: str,
    spy_return_pct: float | None,
    regime: str | None,
) -> dict[str, Any]:
    pos_id = f"paper:{entry_rules.chain_symbol}:{expiration.isoformat()}:{int(strike)}"
    return {
        "position_id": pos_id,
        "lane": "A",
        "chain_symbol": entry_rules.chain_symbol,
        "option_type": "call",
        "strike": strike,
        "expiration_date": expiration.isoformat(),
        "quantity": entry_rules.quantity,
        "average_price": round(premium, 4),
        "mark_price": round(premium, 4),
        "delta_at_entry": delta,
        "entry_ts": evaluated_at,
        "dte": compute_dte(expiration),
        "status": "open",
        "paper_mode": "automated_log_only",
        "entry_reason": "bb_bounce_long_call",
        "logic_version": rules.logic_version,
        "regime_at_entry": regime,
        "prior_day_spy_return_pct": spy_return_pct,
        "quote_source": "SPY_chain_proxy",
    }


def stamp_quote_source(position: dict[str, Any], source: str) -> dict[str, Any]:
    position["quote_source"] = source
    return position


def append_entry_log(
    decision: EntryDecision,
    *,
    log_path: Path | None = None,
) -> None:
    path = log_path or DEFAULT_PAPER_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": decision.evaluated_at,
        "event": "paper_entry" if decision.entered else "paper_entry_skip",
        "logic_version": decision.logic_version,
        "entered": decision.entered,
        "skip_reason": decision.skip_reason,
        "regime": decision.regime,
        "prior_day_spy_return_pct": decision.prior_day_spy_return_pct,
        "ta_snapshot": decision.ta_snapshot,
        "bb_entry_ok": decision.bb_entry_ok,
        "position": decision.position,
        "errors": decision.errors,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def write_entry_brief(decision: EntryDecision, out_path: Path | None = None) -> Path:
    path = out_path or DEFAULT_OUT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(decision.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def entry_gates_ok(
    now: datetime,
    *,
    entry_rules: EntryRules,
    ta_rules: TaRules,
    ta: TaSignal,
    force: bool,
    intraday: bool,
) -> tuple[bool, str | None]:
    """Combine close window, RTH, and BB bounce gates per rules mode."""
    if not force and not in_rth(now) and not in_entry_window(now, entry_rules):
        return False, "outside RTH and close window"

    in_win = in_entry_window(now, entry_rules) or force
    mode = ta_rules.entry_mode

    if mode == "close_window_only":
        if not in_win:
            return False, "outside entry window 15:45–16:00 ET"
        return True, None

    if mode == "bb_bounce":
        if not ta.entry_ok:
            return False, f"no BB bounce: {ta.detail}"
        if not force and not in_rth(now):
            return False, "outside RTH"
        return True, None

    # close_window_and_bb
    if intraday and ta_rules.intraday_entry_enabled and ta.entry_ok and in_rth(now):
        return True, None
    if not in_win:
        return False, "outside entry window 15:45–16:00 ET"
    if not ta.entry_ok:
        return False, f"no BB bounce at close window: {ta.detail}"
    return True, None


def run_paper_entry(
    *,
    rules_path: Path | None = None,
    state_path: Path | None = None,
    now_et: datetime | None = None,
    force: bool = False,
    intraday: bool = False,
    publish_intel: bool = True,
    ta_signal: TaSignal | None = None,
) -> EntryDecision:
    lane_rules = LaneRules.from_yaml(rules_path or DEFAULT_RULES)
    entry_rules = EntryRules.from_yaml(rules_path or DEFAULT_RULES)
    ta_rules = TaRules.from_yaml(rules_path or DEFAULT_RULES)
    state = load_state(state_path or DEFAULT_STATE)
    now = now_et or datetime.now(ET)
    evaluated_at = datetime.now(timezone.utc).isoformat()

    if ta_signal is None:
        ta_signal = evaluate_ta_signals(ta_rules)

    regime, regime_ok = read_regime()
    decision = EntryDecision(
        entered=False,
        evaluated_at=evaluated_at,
        logic_version=lane_rules.logic_version,
        in_window=in_entry_window(now, entry_rules),
        regime=regime,
        regime_ok=regime_ok,
        prior_day_spy_return_pct=None,
        prior_day_ok=True,
        ta_snapshot=ta_signal.to_dict(),
        bb_entry_ok=ta_signal.entry_ok,
    )

    if not paper_entry_enabled():
        decision.skip_reason = "XSP_LANE_A_PAPER_ENTRY disabled"
        _finalize_entry(state, state_path, decision, publish_intel)
        return decision

    if not entry_rules.enabled:
        decision.skip_reason = "paper_entry.disabled in rules"
        _finalize_entry(state, state_path, decision, publish_intel)
        return decision

    gates_ok, gate_reason = entry_gates_ok(
        now,
        entry_rules=entry_rules,
        ta_rules=ta_rules,
        ta=ta_signal,
        force=force,
        intraday=intraday,
    )
    if not gates_ok:
        decision.skip_reason = gate_reason
        _finalize_entry(state, state_path, decision, publish_intel)
        return decision

    open_pos = open_paper_positions(state)
    if len(open_pos) >= entry_rules.max_open_positions:
        decision.skip_reason = f"max open paper positions ({entry_rules.max_open_positions})"
        _finalize_entry(state, state_path, decision, publish_intel)
        return decision

    if not force and already_entered_today(state, now.date()):
        decision.skip_reason = "already entered or attempted today"
        _finalize_entry(state, state_path, decision, publish_intel)
        return decision

    if lane_rules.regime_gate == "GREEN" and not regime_ok:
        decision.skip_reason = f"regime {regime} blocks new risk"
        _finalize_entry(state, state_path, decision, publish_intel)
        return decision

    _, _, spy_ret = fetch_spy_ohlcv()
    decision.prior_day_spy_return_pct = spy_ret
    if entry_rules.prior_day_spy_positive:
        decision.prior_day_ok = spy_ret is not None and spy_ret > 0
        if not decision.prior_day_ok:
            decision.skip_reason = "prior-day SPY not positive"
            _finalize_entry(state, state_path, decision, publish_intel)
            return decision

    spx = fetch_spx_proxy()
    if spx is None:
        decision.skip_reason = "SPX proxy unavailable"
        decision.errors.append("spx_proxy_failed")
        _finalize_entry(state, state_path, decision, publish_intel)
        return decision

    expiration = pick_expiration(lane_rules, today=now.date())
    if expiration is None:
        decision.skip_reason = "no eligible expiration in DTE window"
        _finalize_entry(state, state_path, decision, publish_intel)
        return decision

    strike = round_xsp_strike(spx)
    premium, delta = fetch_spy_call_quote(strike / 10.0, expiration)
    quote_source = "SPY_chain_proxy"
    if premium is None or premium <= 0:
        spy_px = spx / 10.0
        premium = estimate_fallback_premium(spy_px, compute_dte(expiration, today=now.date()))
        quote_source = "fallback_estimate_after_hours"
        decision.errors.append("quote_fallback_used")

    position = build_paper_position(
        rules=lane_rules,
        entry_rules=entry_rules,
        expiration=expiration,
        strike=strike,
        premium=premium,
        delta=delta,
        evaluated_at=evaluated_at,
        spy_return_pct=spy_ret,
        regime=regime,
    )
    stamp_quote_source(position, quote_source)
    position["entry_ta_detail"] = ta_signal.detail
    paper_positions = state.setdefault("paper_positions", {})
    paper_positions[position["position_id"]] = position

    decision.entered = True
    decision.position = position
    decision.skip_reason = None

    _finalize_entry(state, state_path, decision, publish_intel)
    return decision


def close_open_paper_positions(
    state: dict[str, Any],
    *,
    state_path: Path | None = None,
    reason: str = "manual",
    position_id: str | None = None,
    evaluated_at: str | None = None,
) -> list[dict[str, Any]]:
    """Close open paper positions (operator cleanup or simulated exit)."""
    ts = evaluated_at or datetime.now(timezone.utc).isoformat()
    paper = state.setdefault("paper_positions", {})
    if not isinstance(paper, dict):
        return []
    closed: list[dict[str, Any]] = []
    for pid, raw in list(paper.items()):
        if not isinstance(raw, dict) or raw.get("status", "open") != "open":
            continue
        if position_id and pid != position_id:
            continue
        avg = float(raw.get("average_price") or 0)
        mark = float(raw.get("mark_price") or avg)
        qty = float(raw.get("quantity") or 1)
        pnl_per_contract = (mark - avg) * 100.0 if avg > 0 else 0.0
        pnl_usd = pnl_per_contract * qty
        row = dict(raw)
        row["status"] = "closed"
        row["exit_ts"] = ts
        row["exit_reason"] = reason
        row["exit_pnl_usd"] = round(pnl_usd, 2)
        row["exit_pnl_per_contract"] = round(pnl_per_contract, 2)
        paper[pid] = row
        closed.append(row)
        events = list(state.get("paper_events") or [])
        events.append(
            {
                "evaluated_at": ts,
                "position_id": pid,
                "exit_reason": reason,
                "paper_pnl_usd": row["exit_pnl_usd"],
                "paper_pnl_per_contract": row["exit_pnl_per_contract"],
                "logic_version": raw.get("logic_version", "xsp_lane_a_v1"),
                "paper_mode": "operator_close",
                "entry_ts": raw.get("entry_ts"),
            }
        )
        state["paper_events"] = events[-500:]
    if closed:
        save_state(state_path or DEFAULT_STATE, state)
        path = DEFAULT_PAPER_LOG
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for row in closed:
                fh.write(
                    json.dumps(
                        {
                            "ts": ts,
                            "event": "paper_exit",
                            "position_id": row.get("position_id"),
                            "exit_reason": reason,
                            "paper_pnl_usd": row.get("exit_pnl_usd"),
                            "logic_version": row.get("logic_version"),
                        }
                    )
                    + "\n"
                )
    return closed


def _finalize_entry(
    state: dict[str, Any],
    state_path: Path | None,
    decision: EntryDecision,
    publish_intel: bool,
) -> None:
    log = list(state.get("entry_log") or [])
    log.append(
        {
            "evaluated_at": decision.evaluated_at,
            "entered": decision.entered,
            "skip_reason": decision.skip_reason,
            "position_id": (decision.position or {}).get("position_id"),
            "regime": decision.regime,
            "prior_day_spy_return_pct": decision.prior_day_spy_return_pct,
        }
    )
    state["entry_log"] = log[-200:]
    save_state(state_path or DEFAULT_STATE, state)
    append_entry_log(decision)
    write_entry_brief(decision)

    if publish_intel:
        try:
            from xsp_killer.intel import IntelPublisher

            IntelPublisher.publish(
                "intel:xsp_lane_a_entry",
                decision.to_dict(),
                source_system="xsp_lane_a_entry",
                confidence=1.0 if decision.entered else 0.5,
                ttl=86400,
            )
        except Exception as exc:
            decision.errors.append(f"intel publish failed: {exc}")
