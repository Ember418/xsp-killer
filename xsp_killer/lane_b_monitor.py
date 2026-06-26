"""XSP Lane B LEAPS + hedge put monitor — Phase 0 alerts only (K116).

Shares RH poll helpers with Lane A. Inventory + hedge-gap alerts; no auto-orders.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from xsp_killer.lane_a_monitor import (
    compute_dte,
    fetch_robinhood_option_positions,
    is_lane_a_contract,
    load_state,
    parse_expiration,
    read_regime,
    rh_poll_enabled,
    save_state,
)

logger = logging.getLogger("xsp_killer.xsp_lane_b")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = ROOT / "config" / "lane_b_rules.yaml"
DEFAULT_STATE = ROOT / "config" / "lane_b_state.json"
DEFAULT_OUT = ROOT / "briefs" / "xsp-lane-b-monitor-latest.json"
DEFAULT_PAPER_LOG = ROOT / "logs" / "xsp_lane_b_paper.jsonl"
DEFAULT_SCORECARD = ROOT / "briefs/lane-b-scorecard-latest.json"


@dataclass
class LaneBRules:
    lane: str
    dte_min: int
    chain_symbols: tuple[str, ...]
    call_delta_above: float
    portfolio_drawdown_pct: float
    hedge_dte_below: int
    max_lane_b_notional_pct: float
    logic_version: str
    regime_gate_new_lots: str = "GREEN"

    @classmethod
    def from_yaml(cls, path: Path) -> LaneBRules:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        calls = data.get("calls") or {}
        hedge = data.get("hedge_puts") or {}
        triggers = hedge.get("roll_alert_triggers") or {}
        risk = data.get("risk") or {}
        scorecard = data.get("scorecard") or {}
        return cls(
            lane=str(data.get("lane", "B")),
            dte_min=int(calls.get("dte_min", 180)),
            chain_symbols=tuple(
                str(x).upper() for x in data.get("chain_symbols") or ["SPX", "XSP"]
            ),
            call_delta_above=float(triggers.get("call_delta_above", 0.65)),
            portfolio_drawdown_pct=float(triggers.get("portfolio_drawdown_pct", 8)),
            hedge_dte_below=int(triggers.get("hedge_dte_below", 45)),
            max_lane_b_notional_pct=float(risk.get("max_lane_b_notional_pct", 50)),
            logic_version=str(scorecard.get("logic_version", "xsp_lane_b_v1")),
            regime_gate_new_lots=str(calls.get("regime_gate_new_lots", "GREEN")),
        )


@dataclass
class LaneBPosition:
    position_id: str
    leg_type: str
    chain_symbol: str
    option_type: str
    strike: float
    expiration_date: date
    quantity: float
    average_price: float
    mark_price: float | None
    dte: int
    lane: str = "B"
    delta: float | None = None
    hedge_pair_id: str | None = None
    linked_call_id: str | None = None
    notional_usd: float | None = None
    pnl_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["expiration_date"] = self.expiration_date.isoformat()
        return d


@dataclass
class LaneBAlert:
    alert_code: str
    message: str
    position_id: str | None = None
    hedge_pair_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LaneBReport:
    evaluated_at: str
    phase: int
    logic_version: str
    regime: str | None
    calls: list[dict[str, Any]] = field(default_factory=list)
    hedge_puts: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    rh_connected: bool = False
    rh_poll_skipped: bool = False
    portfolio_mtm_usd: float = 0.0
    portfolio_notional_usd: float = 0.0
    drawdown_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _lane_a_rules_stub(rules: LaneBRules):
    class _Stub:
        chain_symbols = rules.chain_symbols
        exclude_expiry_month = ("01",)
        dte_min = 14
        dte_max = 60

    return _Stub()


def _position_id(raw: dict[str, Any], chain: str, exp: date) -> str:
    return str(
        raw.get("id")
        or raw.get("option_id")
        or raw.get("url")
        or f"{chain}:{exp}:{raw.get('strike_price')}"
    )


def _notional_and_pnl(
    qty: float, avg: float, mark: float | None
) -> tuple[float | None, float | None]:
    if mark is None:
        return None, None
    return mark * qty * 100.0, (mark - avg) * qty * 100.0


def classify_lane_b_call(
    raw: dict[str, Any], rules: LaneBRules
) -> LaneBPosition | None:
    chain = str(raw.get("chain_symbol") or raw.get("symbol") or "").upper()
    opt_type = str(raw.get("type") or raw.get("option_type") or "").lower()
    exp = parse_expiration(
        str(raw.get("expiration_date") or raw.get("expiration") or "")
    )
    if exp is None or chain not in rules.chain_symbols or opt_type != "call":
        return None
    if is_lane_a_contract(
        chain_symbol=chain,
        option_type=opt_type,
        expiration=exp,
        rules=_lane_a_rules_stub(rules),
    ):
        return None
    if compute_dte(exp) <= rules.dte_min:
        return None
    qty = float(raw.get("quantity") or raw.get("qty") or 0)
    if qty <= 0:
        return None
    avg = float(raw.get("average_price") or raw.get("avg_price") or 0)
    mark_raw = raw.get("mark_price") or raw.get("mark")
    mark = float(mark_raw) if mark_raw is not None else None
    delta_raw = raw.get("delta")
    if delta_raw is None and isinstance(raw.get("greeks"), dict):
        delta_raw = raw["greeks"].get("delta")
    delta = float(delta_raw) if delta_raw is not None else None
    notional, pnl = _notional_and_pnl(qty, avg, mark)
    return LaneBPosition(
        position_id=_position_id(raw, chain, exp),
        leg_type="call",
        chain_symbol=chain,
        option_type=opt_type,
        strike=float(raw.get("strike_price") or raw.get("strike") or 0),
        expiration_date=exp,
        quantity=qty,
        average_price=avg,
        mark_price=mark,
        dte=compute_dte(exp),
        delta=delta,
        notional_usd=notional,
        pnl_usd=pnl,
    )


def classify_hedge_put(raw: dict[str, Any], rules: LaneBRules) -> LaneBPosition | None:
    chain = str(raw.get("chain_symbol") or raw.get("symbol") or "").upper()
    opt_type = str(raw.get("type") or raw.get("option_type") or "").lower()
    exp = parse_expiration(
        str(raw.get("expiration_date") or raw.get("expiration") or "")
    )
    if exp is None or chain not in rules.chain_symbols or opt_type != "put":
        return None
    qty = float(raw.get("quantity") or raw.get("qty") or 0)
    if qty <= 0:
        return None
    avg = float(raw.get("average_price") or raw.get("avg_price") or 0)
    mark_raw = raw.get("mark_price") or raw.get("mark")
    mark = float(mark_raw) if mark_raw is not None else None
    notional, pnl = _notional_and_pnl(qty, avg, mark)
    return LaneBPosition(
        position_id=_position_id(raw, chain, exp),
        leg_type="hedge_put",
        chain_symbol=chain,
        option_type=opt_type,
        strike=float(raw.get("strike_price") or raw.get("strike") or 0),
        expiration_date=exp,
        quantity=qty,
        average_price=avg,
        mark_price=mark,
        dte=compute_dte(exp),
        notional_usd=notional,
        pnl_usd=pnl,
    )


def merge_state_metadata(positions: list[LaneBPosition], state: dict[str, Any]) -> None:
    pos_tags = state.get("positions") or {}
    links = state.get("hedge_links") or {}
    for pos in positions:
        tag = pos_tags.get(pos.position_id) or {}
        if tag.get("lane"):
            pos.lane = str(tag["lane"])
        if tag.get("hedge_pair_id"):
            pos.hedge_pair_id = str(tag["hedge_pair_id"])
        if tag.get("delta_at_entry") is not None:
            pos.delta = float(tag["delta_at_entry"])
        if tag.get("linked_call_id"):
            pos.linked_call_id = str(tag["linked_call_id"])
        if pos.leg_type == "call" and pos.position_id in links:
            link = links[pos.position_id] or {}
            pos.hedge_pair_id = pos.hedge_pair_id or link.get("hedge_pair_id")
        if pos.leg_type == "hedge_put":
            for call_id, link in links.items():
                if pos.position_id in (link.get("put_position_ids") or []):
                    pos.hedge_pair_id = link.get("hedge_pair_id")
                    pos.linked_call_id = call_id
                    break


def evaluate_lane_b_alerts(
    calls: list[LaneBPosition],
    puts: list[LaneBPosition],
    rules: LaneBRules,
    state: dict[str, Any],
    *,
    regime: str | None,
    drawdown_pct: float | None,
    portfolio_notional_usd: float,
) -> list[LaneBAlert]:
    alerts: list[LaneBAlert] = []
    links = state.get("hedge_links") or {}
    puts_by_pair: dict[str, list[LaneBPosition]] = {}
    for p in puts:
        if p.hedge_pair_id:
            puts_by_pair.setdefault(p.hedge_pair_id, []).append(p)

    for call in calls:
        pair_id = call.hedge_pair_id or (links.get(call.position_id) or {}).get(
            "hedge_pair_id"
        )
        if call.lane == "B" and not pair_id:
            alerts.append(
                LaneBAlert(
                    alert_code="B_HEDGE_MISSING",
                    message=f"Lane B call {call.position_id} has no linked protective put",
                    position_id=call.position_id,
                )
            )
        elif pair_id:
            linked_puts = puts_by_pair.get(pair_id, [])
            if call.lane == "B" and not linked_puts:
                alerts.append(
                    LaneBAlert(
                        alert_code="B_HEDGE_MISSING",
                        message=f"Lane B call {call.position_id} has no linked protective put",
                        position_id=call.position_id,
                        hedge_pair_id=pair_id,
                    )
                )
            for hp in linked_puts:
                if hp.dte < rules.hedge_dte_below:
                    alerts.append(
                        LaneBAlert(
                            alert_code="B_HEDGE_DTE_LOW",
                            message=f"Hedge put DTE {hp.dte} < {rules.hedge_dte_below}",
                            position_id=hp.position_id,
                            hedge_pair_id=pair_id,
                        )
                    )
        delta = call.delta
        if delta is not None and delta > rules.call_delta_above:
            alerts.append(
                LaneBAlert(
                    alert_code="B_CALL_DELTA_HIGH",
                    message=f"Call delta {delta:.2f} > {rules.call_delta_above}",
                    position_id=call.position_id,
                    hedge_pair_id=pair_id,
                )
            )

    if drawdown_pct is not None and drawdown_pct >= rules.portfolio_drawdown_pct:
        alerts.append(
            LaneBAlert(
                alert_code="B_DRAWDOWN",
                message=f"Lane B drawdown {drawdown_pct:.1f}% off peak",
            )
        )
    if regime and regime.upper() == "YELLOW" and (calls or puts):
        alerts.append(
            LaneBAlert(
                alert_code="B_REGIME_YELLOW",
                message="Regime YELLOW with open Lane B — review hedges",
            )
        )
    acct_eq = state.get("account_equity_usd")
    if acct_eq and float(acct_eq) > 0 and portfolio_notional_usd > 0:
        pct = 100.0 * portfolio_notional_usd / float(acct_eq)
        if pct > rules.max_lane_b_notional_pct:
            alerts.append(
                LaneBAlert(
                    alert_code="B_SLEEVE_OVER",
                    message=f"Lane B notional {pct:.1f}% > cap {rules.max_lane_b_notional_pct}%",
                )
            )
    return alerts


def delta_adjusted_return(
    pnl_usd: float, delta_at_entry: float, exposure_days: float
) -> float | None:
    denom = delta_at_entry * exposure_days
    return None if denom <= 0 else pnl_usd / denom


def build_scorecard(state: dict[str, Any], logic_version: str) -> dict[str, Any]:
    closed = list(state.get("closed_trades") or [])
    rows = []
    for t in closed:
        pnl = float(t.get("pnl_usd") or 0)
        delta = float(t.get("delta_at_entry") or 0)
        days = float(t.get("exposure_days") or 1)
        rows.append(
            {**t, "delta_adjusted_return": delta_adjusted_return(pnl, delta, days)}
        )
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "logic_version": logic_version,
        "metric": "delta_adjusted_return",
        "closed_trades_n": len(rows),
        "trades": rows,
    }


def run_monitor(
    *,
    rules_path: Path | None = None,
    state_path: Path | None = None,
    positions_override: list[dict[str, Any]] | None = None,
    publish_intel: bool = True,
) -> LaneBReport:
    rules = LaneBRules.from_yaml(rules_path or DEFAULT_RULES)
    state = load_state(state_path or DEFAULT_STATE)
    regime, _ = read_regime()
    report = LaneBReport(
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        phase=0,
        logic_version=rules.logic_version,
        regime=regime,
    )

    if positions_override is not None:
        raw_positions = positions_override
        report.rh_connected = True
    elif not rh_poll_enabled():
        raw_positions = []
        report.rh_poll_skipped = True
    else:
        raw_positions, err = fetch_robinhood_option_positions()
        if err:
            report.errors.append(err)
        else:
            report.rh_connected = True

    calls: list[LaneBPosition] = []
    puts: list[LaneBPosition] = []
    for raw in raw_positions:
        c = classify_lane_b_call(raw, rules)
        if c:
            calls.append(c)
        p = classify_hedge_put(raw, rules)
        if p:
            puts.append(p)
    merge_state_metadata(calls + puts, state)
    report.calls = [c.to_dict() for c in calls]
    report.hedge_puts = [p.to_dict() for p in puts]

    portfolio_mtm = sum((x.pnl_usd or 0) for x in calls + puts)
    portfolio_notional = sum((x.notional_usd or 0) for x in calls + puts)
    report.portfolio_mtm_usd = round(portfolio_mtm, 2)
    report.portfolio_notional_usd = round(portfolio_notional, 2)

    peak = state.get("mtm_peak_usd")
    if peak is None or portfolio_mtm > float(peak):
        state["mtm_peak_usd"] = portfolio_mtm
        peak = portfolio_mtm
    drawdown_pct = None
    if peak and float(peak) > 0 and portfolio_mtm < float(peak):
        drawdown_pct = 100.0 * (float(peak) - portfolio_mtm) / float(peak)
    report.drawdown_pct = drawdown_pct

    report.alerts = [
        a.to_dict()
        for a in evaluate_lane_b_alerts(
            calls,
            puts,
            rules,
            state,
            regime=regime,
            drawdown_pct=drawdown_pct,
            portfolio_notional_usd=portfolio_notional,
        )
    ]

    if publish_intel and report.alerts:
        try:
            from xsp_killer.intel import IntelPublisher

            IntelPublisher.publish(
                "intel:xsp_lane_b_alert",
                {
                    "evaluated_at": report.evaluated_at,
                    "alerts": report.alerts,
                    "calls_n": len(calls),
                    "puts_n": len(puts),
                    "logic_version": rules.logic_version,
                },
                source_system="xsp_lane_b_monitor",
                confidence=1.0,
                ttl=86400,
            )
        except Exception as exc:
            report.errors.append(f"intel publish failed: {exc}")

    tags = state.setdefault("positions", {})
    for pos in calls + puts:
        prev = tags.get(pos.position_id) or {}
        tags[pos.position_id] = {
            **prev,
            "lane": pos.lane,
            "leg_type": pos.leg_type,
            "last_seen": report.evaluated_at,
            "dte": pos.dte,
            "hedge_pair_id": pos.hedge_pair_id,
        }

    append_paper_log(report)
    save_state(state_path or DEFAULT_STATE, state)
    write_scorecard(state, rules.logic_version)
    return report


def append_paper_log(report: LaneBReport, log_path: Path | None = None) -> None:
    path = log_path or DEFAULT_PAPER_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": report.evaluated_at,
                    "event": "lane_b_monitor",
                    "logic_version": report.logic_version,
                    "calls_n": len(report.calls),
                    "puts_n": len(report.hedge_puts),
                    "portfolio_mtm_usd": report.portfolio_mtm_usd,
                    "alerts_n": len(report.alerts),
                    "alerts": report.alerts,
                }
            )
            + "\n"
        )


def write_scorecard(
    state: dict[str, Any], logic_version: str, out_path: Path | None = None
) -> Path:
    path = out_path or DEFAULT_SCORECARD
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_scorecard(state, logic_version), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def write_report(report: LaneBReport, out_path: Path | None = None) -> Path:
    path = out_path or DEFAULT_OUT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path
