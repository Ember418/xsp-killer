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

from xsp_killer.paper_economics import SPY_TO_XSP_PREMIUM_SCALE
from xsp_killer.spy_quote import (
    fetch_spy_call_quote_legacy as fetch_spy_call_quote,
    fetch_spy_call_quote as fetch_spy_call_mark,
    xsp_strike_to_spy_chain_strike,
)
from xsp_killer.conductor_shadow import shadow_review_entry
from xsp_killer.risk_gates import entry_allowed_by_risk
from xsp_killer.lane_a_monitor import (
    DEFAULT_PAPER_LOG,
    DEFAULT_RULES,
    DEFAULT_STATE,
    LaneRules,
    compute_dte,
    is_lane_a_contract,
    load_state,
    read_regime_detail,
    regime_gate_allows,
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
    strike_max_steps_from_atm: int = 1
    dte_pick: str = "min"
    dte_target: int | None = None
    strike_pick: str = "cheapest_near_atm"

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
            prior_day_spy_positive=bool(entry.get("prior_day_spy_positive", False)),
            max_open_positions=int(paper.get("max_open_positions", 1)),
            quantity=float(paper.get("quantity", 1)),
            enabled=bool(paper.get("enabled", True)),
            chain_symbol=str(data.get("instrument", "XSP")).upper(),
            strike_max_steps_from_atm=int(entry.get("strike_max_steps_from_atm", 1)),
            dte_pick=str(entry.get("dte_pick", "min")).strip().lower(),
            dte_target=int(entry["dte_target"])
            if entry.get("dte_target") is not None
            else None,
            strike_pick=str(entry.get("strike_pick", "cheapest_near_atm"))
            .strip()
            .lower(),
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
    regime_frac: float | None = None
    regime_gate: str | None = None
    prior_day_spy_session: str | None = None
    skip_reason: str | None = None
    position: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    ta_snapshot: dict[str, Any] | None = None
    bb_entry_ok: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def paper_entry_enabled() -> bool:
    return os.getenv("XSP_LANE_A_PAPER_ENTRY", "true").strip().lower() in (
        "1",
        "true",
        "yes",
    )


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
    """True only after a successful entry today (not failed attempts)."""
    day = today.isoformat()
    for pos in (state.get("paper_positions") or {}).values():
        if not isinstance(pos, dict):
            continue
        if str(pos.get("entry_ts") or "")[:10] == day:
            return True
    for evt in state.get("entry_log") or []:
        if not isinstance(evt, dict):
            continue
        if (
            evt.get("entered")
            and evt.get("position_id")
            and str(evt.get("evaluated_at", ""))[:10] == day
        ):
            return True
    return False


def fetch_spy_ohlcv() -> tuple[float | None, float | None, float | None, str | None]:
    """Return (prior_close, prior_open, prior_close_to_close_return_pct, session_date)."""
    try:
        import yfinance as yf

        hist = yf.Ticker("SPY").history(period="5d", interval="1d", timeout=10)
        if hist is None or len(hist) < 2:
            return None, None, None, None
        prev = hist.iloc[-2]
        o = float(prev["Open"])
        c = float(prev["Close"])
        ret: float | None = None
        if len(hist) >= 3:
            prev_prev_close = float(hist.iloc[-3]["Close"])
            if prev_prev_close:
                ret = (c - prev_prev_close) / prev_prev_close * 100.0
        elif o:
            ret = (c - o) / o * 100.0
        try:
            session_date = (
                prev.name.date() if hasattr(prev.name, "date") else str(prev.name)[:10]
            )
        except Exception:
            session_date = "unknown"
        logger.debug(
            "prior_day_spy session=%s close=%.4f open=%.4f return_cc=%s",
            session_date,
            c,
            o,
            f"{ret:.4f}" if ret is not None else "n/a",
        )
        return c, o, ret, str(session_date)
    except Exception as exc:
        logger.warning("SPY OHLCV fetch failed: %s", exc)
        return None, None, None, None


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


def pick_expiration(
    rules: LaneRules,
    *,
    today: date,
    dte_pick: str = "min",
    dte_target: int | None = None,
) -> date | None:
    try:
        from xsp_killer.chain_cache import get_spy_expirations

        expirations = get_spy_expirations()
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
    mode = (dte_pick or "min").lower()
    if mode == "max":
        return candidates[-1][1]
    if mode == "target" and dte_target is not None:
        return min(candidates, key=lambda x: abs(x[0] - dte_target))[1]
    return candidates[0][1]


def round_xsp_strike(spx_level: float) -> float:
    step = 5.0
    return round(spx_level / step) * step


def pick_cheapest_atm_strike(
    spx_level: float,
    expiration: date,
    *,
    max_steps_from_atm: int = 1,
) -> tuple[float, float | None, float | None]:
    """Cheapest near-ATM XSP strike (mentor: closest to money, lowest premium)."""
    atm = round_xsp_strike(spx_level)
    step = 5.0
    candidates = [
        atm + i * step for i in range(-max_steps_from_atm, max_steps_from_atm + 1)
    ]
    best_strike = atm
    best_premium: float | None = None
    best_delta: float | None = None
    best_dist = float("inf")
    for xsp_strike in candidates:
        prem, delta = fetch_spy_call_quote(xsp_strike / 10.0, expiration)
        if prem is None or prem <= 0:
            continue
        dist = abs(xsp_strike - spx_level)
        xsp_prem = prem * SPY_TO_XSP_PREMIUM_SCALE
        if dist < best_dist or (
            dist == best_dist and (best_premium is None or xsp_prem < best_premium)
        ):
            best_strike = xsp_strike
            best_premium = xsp_prem
            best_delta = delta
            best_dist = dist
    if best_premium is None:
        return atm, None, None
    return best_strike, best_premium, best_delta


def pick_strike(
    spx_level: float,
    expiration: date,
    *,
    strike_pick: str = "cheapest_near_atm",
    max_steps_from_atm: int = 1,
) -> tuple[float, float | None, float | None]:
    """Select strike by mode: cheapest_near_atm | atm_only | otm_one."""
    mode = (strike_pick or "cheapest_near_atm").lower()
    atm = round_xsp_strike(spx_level)
    if mode == "atm_only":
        prem, delta = fetch_spy_call_quote(atm / 10.0, expiration)
        if prem is None or prem <= 0:
            return atm, None, None
        return atm, prem * SPY_TO_XSP_PREMIUM_SCALE, delta
    if mode == "otm_one":
        otm = atm + 5.0
        prem, delta = fetch_spy_call_quote(otm / 10.0, expiration)
        if prem is None or prem <= 0:
            return otm, None, None
        return otm, prem * SPY_TO_XSP_PREMIUM_SCALE, delta
    return pick_cheapest_atm_strike(
        spx_level, expiration, max_steps_from_atm=max_steps_from_atm
    )


def estimate_fallback_premium(
    spy_price: float,
    dte: int,
    *,
    xsp_strike: float | None = None,
    spx_level: float | None = None,
    scale_to_xsp: bool = True,
) -> float:
    """Strike-aware paper premium when live quote unavailable (XSP notional by default)."""
    base = max(0.35, spy_price * 0.012)
    scale = max(0.6, min(1.4, (dte / 30.0) ** 0.5))
    prem = base * scale
    if xsp_strike is not None and spx_level is not None and spx_level > 0:
        otm_steps = max(0.0, (xsp_strike - spx_level) / 5.0)
        prem *= max(0.55, 1.0 - 0.08 * otm_steps)
    if scale_to_xsp:
        prem *= SPY_TO_XSP_PREMIUM_SCALE
    return round(prem, 4)


def build_paper_position(
    *,
    rules: LaneRules,
    entry_rules: EntryRules,
    expiration: date,
    strike: float,
    premium: float,
    entry_mid_premium: float,
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
        "mark_price": round(entry_mid_premium, 4),
        "entry_mid_premium": round(entry_mid_premium, 4),
        "delta_at_entry": delta,
        "entry_ts": evaluated_at,
        "dte": compute_dte(expiration),
        "dte_actual": compute_dte(expiration),
        "status": "open",
        "paper_mode": "automated_log_only",
        "entry_reason": "bb_bounce_long_call",
        "logic_version": rules.logic_version,
        "regime_at_entry": regime,
        "prior_day_spy_return_pct": spy_return_pct,
        "quote_source": "SPY_chain_proxy",
    }


def stamp_quote_source(
    position: dict[str, Any],
    source: str,
    *,
    spy_row_strike: float | None = None,
) -> dict[str, Any]:
    position["quote_source"] = source
    if spy_row_strike is not None:
        position["spy_row_strike"] = spy_row_strike
    return position


def append_entry_log(
    decision: EntryDecision,
    *,
    log_path: Path | None = None,
    brief_path: Path | None = None,
) -> None:
    path = log_path if log_path is not None else DEFAULT_PAPER_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": decision.evaluated_at,
        "event": "paper_entry" if decision.entered else "paper_entry_skip",
        "logic_version": decision.logic_version,
        "entered": decision.entered,
        "skip_reason": decision.skip_reason,
        "regime": decision.regime,
        "regime_frac": decision.regime_frac,
        "regime_gate": decision.regime_gate,
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
    log_path: Path | None = None,
    now_et: datetime | None = None,
    force: bool = False,
    intraday: bool = False,
    publish_intel: bool = True,
    ta_signal: TaSignal | None = None,
    brief_path: Path | None = None,
) -> EntryDecision:
    lane_rules = LaneRules.from_yaml(rules_path or DEFAULT_RULES)
    entry_rules = EntryRules.from_yaml(rules_path or DEFAULT_RULES)
    ta_rules = TaRules.from_yaml(rules_path or DEFAULT_RULES)
    state = load_state(state_path or DEFAULT_STATE)
    now = now_et or datetime.now(ET)
    evaluated_at = datetime.now(timezone.utc).isoformat()

    if ta_signal is None:
        ta_signal = evaluate_ta_signals(ta_rules, now_et=now)

    regime, regime_ok, yellow_frac, _ = read_regime_detail()
    decision = EntryDecision(
        entered=False,
        evaluated_at=evaluated_at,
        logic_version=lane_rules.logic_version,
        in_window=in_entry_window(now, entry_rules),
        regime=regime,
        regime_ok=regime_ok,
        regime_frac=yellow_frac,
        regime_gate=lane_rules.regime_gate,
        prior_day_spy_return_pct=None,
        prior_day_ok=True,
        prior_day_spy_session=None,
        ta_snapshot=ta_signal.to_dict(),
        bb_entry_ok=ta_signal.entry_ok,
    )

    if not paper_entry_enabled():
        decision.skip_reason = "XSP_LANE_A_PAPER_ENTRY disabled"
        _finalize_entry(
            state,
            state_path,
            decision,
            publish_intel,
            log_path=log_path,
            brief_path=brief_path,
        )
        return decision

    if not entry_rules.enabled:
        decision.skip_reason = "paper_entry.disabled in rules"
        _finalize_entry(
            state,
            state_path,
            decision,
            publish_intel,
            log_path=log_path,
            brief_path=brief_path,
        )
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
        _finalize_entry(
            state,
            state_path,
            decision,
            publish_intel,
            log_path=log_path,
            brief_path=brief_path,
        )
        return decision

    open_pos = open_paper_positions(state)
    if len(open_pos) >= entry_rules.max_open_positions:
        decision.skip_reason = (
            f"max open paper positions ({entry_rules.max_open_positions})"
        )
        _finalize_entry(
            state,
            state_path,
            decision,
            publish_intel,
            log_path=log_path,
            brief_path=brief_path,
        )
        return decision

    if not force and already_entered_today(state, now.date()):
        decision.skip_reason = "already entered or attempted today"
        _finalize_entry(
            state,
            state_path,
            decision,
            publish_intel,
            log_path=log_path,
            brief_path=brief_path,
        )
        return decision

    regime_gate_ok, regime_gate_reason = regime_gate_allows(
        regime_gate=lane_rules.regime_gate,
        regime=regime,
        regime_ok=regime_ok,
        yellow_frac=yellow_frac,
        ta_entry_ok=ta_signal.entry_ok,
        yellow_frac_min=lane_rules.regime_yellow_frac_min,
    )
    if not regime_gate_ok:
        decision.skip_reason = regime_gate_reason
        _finalize_entry(
            state,
            state_path,
            decision,
            publish_intel,
            log_path=log_path,
            brief_path=brief_path,
        )
        return decision

    _, _, spy_ret, spy_session = fetch_spy_ohlcv()
    decision.prior_day_spy_return_pct = spy_ret
    decision.prior_day_spy_session = spy_session
    if entry_rules.prior_day_spy_positive:
        decision.prior_day_ok = spy_ret is not None and spy_ret > 0
        if not decision.prior_day_ok:
            decision.skip_reason = "prior-day SPY not positive"
            _finalize_entry(
                state,
                state_path,
                decision,
                publish_intel,
                log_path=log_path,
                brief_path=brief_path,
            )
            return decision

    ok_risk, risk_reason = entry_allowed_by_risk(state)
    if not ok_risk:
        decision.skip_reason = risk_reason
        _finalize_entry(
            state,
            state_path,
            decision,
            publish_intel,
            log_path=log_path,
            brief_path=brief_path,
        )
        return decision

    spx = fetch_spx_proxy()
    if spx is None:
        decision.skip_reason = "SPX proxy unavailable"
        decision.errors.append("spx_proxy_failed")
        _finalize_entry(
            state,
            state_path,
            decision,
            publish_intel,
            log_path=log_path,
            brief_path=brief_path,
        )
        return decision

    expiration = pick_expiration(
        lane_rules,
        today=now.date(),
        dte_pick=entry_rules.dte_pick,
        dte_target=entry_rules.dte_target,
    )
    if expiration is None:
        decision.skip_reason = "no eligible expiration in DTE window"
        _finalize_entry(
            state,
            state_path,
            decision,
            publish_intel,
            log_path=log_path,
            brief_path=brief_path,
        )
        return decision

    strike, premium, delta = pick_strike(
        spx,
        expiration,
        strike_pick=entry_rules.strike_pick,
        max_steps_from_atm=entry_rules.strike_max_steps_from_atm,
    )
    quote_source = f"SPY_chain_proxy_{entry_rules.strike_pick}"
    from xsp_killer.paper_economics import PaperEconomics, entry_fill_premium

    econ = PaperEconomics.from_yaml(rules_path or DEFAULT_RULES)
    if premium is None or premium <= 0:
        spy_px = spx / 10.0
        dte_actual = compute_dte(expiration, today=now.date())
        entry_mid = estimate_fallback_premium(
            spy_px,
            dte_actual,
            xsp_strike=strike,
            spx_level=spx,
        )
        quote_source = "fallback_estimate_strike_aware"
        decision.errors.append("quote_fallback_used")
    else:
        entry_mid = premium
    fill_premium = entry_fill_premium(entry_mid, econ)

    position = build_paper_position(
        rules=lane_rules,
        entry_rules=entry_rules,
        expiration=expiration,
        strike=strike,
        premium=fill_premium,
        entry_mid_premium=entry_mid,
        delta=delta,
        evaluated_at=evaluated_at,
        spy_return_pct=spy_ret,
        regime=regime,
    )
    spy_row = None
    try:
        q = fetch_spy_call_mark(xsp_strike_to_spy_chain_strike(strike), expiration)
        spy_row = q.spy_row_strike
    except Exception:
        spy_row = None
    stamp_quote_source(position, quote_source, spy_row_strike=spy_row)
    position["dte_actual"] = compute_dte(expiration, today=now.date())
    position["dte_pick"] = entry_rules.dte_pick
    position["dte_target"] = entry_rules.dte_target
    position["entry_ta_detail"] = ta_signal.detail
    paper_positions = state.setdefault("paper_positions", {})
    paper_positions[position["position_id"]] = position

    ok_shadow, shadow_reason = shadow_review_entry(
        regime=regime,
        prior_day_spy_return_pct=spy_ret,
        ta_detail=ta_signal.detail,
        position=position,
    )
    if not ok_shadow:
        paper_positions.pop(position["position_id"], None)
        decision.skip_reason = shadow_reason
        _finalize_entry(
            state,
            state_path,
            decision,
            publish_intel,
            log_path=log_path,
            brief_path=brief_path,
        )
        return decision

    decision.entered = True
    decision.position = position
    decision.skip_reason = None

    _finalize_entry(
        state,
        state_path,
        decision,
        publish_intel,
        log_path=log_path,
        brief_path=brief_path,
    )
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
    log_path: Path | None = None,
    brief_path: Path | None = None,
) -> None:
    log = list(state.get("entry_log") or [])
    log.append(
        {
            "evaluated_at": decision.evaluated_at,
            "entered": decision.entered,
            "skip_reason": decision.skip_reason,
            "position_id": (decision.position or {}).get("position_id"),
            "regime": decision.regime,
            "regime_frac": decision.regime_frac,
            "regime_gate": decision.regime_gate,
            "bb_entry_ok": decision.bb_entry_ok,
            "prior_day_spy_return_pct": decision.prior_day_spy_return_pct,
            "prior_day_spy_session": decision.prior_day_spy_session,
        }
    )
    state["entry_log"] = log[-200:]
    save_state(state_path or DEFAULT_STATE, state)
    append_entry_log(decision, log_path=log_path)
    if brief_path is not False:
        write_entry_brief(decision, out_path=brief_path)

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
