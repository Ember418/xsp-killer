#!/usr/bin/env python3
"""Backfill shadow exit bracket logs for closed paper positions (post-reset soak)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from xsp_killer.exit_shadow import append_shadow_exit_log, build_shadow_exit_record  # noqa: E402
from xsp_killer.lane_a_monitor import (  # noqa: E402
    DEFAULT_RULES,
    DEFAULT_STATE,
    ExitAlert,
    LaneRules,
    compute_dte,
    evaluate_exit_alerts,
    parse_expiration,
)
from xsp_killer.lane_a_variants import DEFAULT_VARIANTS_STATE, load_variant_specs, merged_rules_path  # noqa: E402

ET = ZoneInfo("America/New_York")
DEFAULT_LOG = ROOT / "logs" / "xsp_lane_a_shadow_exits.jsonl"
DEFAULT_OUT = ROOT / "briefs" / "2026-06-23_xsp-lane-a-shadow-exits-session1-backfill.json"


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return ts if ts.tzinfo else ts.replace(tzinfo=ET)
    except (ValueError, TypeError):
        return None


def _lane_position(raw: dict) -> tuple[object, LaneRules]:
    from xsp_killer.lane_a_monitor import LaneAPosition, _attach_economics_pnl

    exp = parse_expiration(str(raw.get("expiration_date") or ""))
    if exp is None:
        raise ValueError(f"bad expiration on {raw.get('position_id')}")
    entry_mid_raw = raw.get("entry_mid_premium")
    avg = float(raw.get("average_price") or 0)
    entry_mid = float(entry_mid_raw) if entry_mid_raw is not None else avg
    mark_raw = raw.get("mark_price")
    mark = float(mark_raw) if mark_raw is not None else None
    pos = LaneAPosition(
        position_id=str(raw.get("position_id") or ""),
        chain_symbol=str(raw.get("chain_symbol") or "XSP"),
        option_type=str(raw.get("option_type") or "call"),
        strike=float(raw.get("strike") or 0),
        expiration_date=exp,
        quantity=float(raw.get("quantity") or 1),
        average_price=avg,
        mark_price=mark,
        dte=int(raw.get("dte") or compute_dte(exp)),
        lane=str(raw.get("lane") or "A"),
        entry_ts=raw.get("entry_ts"),
        delta_at_entry=raw.get("delta_at_entry"),
        entry_mid_premium=entry_mid,
        mark_quote_stale=bool(raw.get("mark_quote_stale")),
    )
    rules_path = DEFAULT_RULES
    variant_id = raw.get("variant_id")
    if variant_id:
        spec = next((s for s in load_variant_specs() if s.variant_id == variant_id), None)
        if spec is not None:
            rules_path = merged_rules_path(spec)
    rules = LaneRules.from_yaml(rules_path)
    _attach_economics_pnl(pos, rules_path=rules_path)
    return pos, rules


def _iter_closed_positions(
    *,
    variants_state_path: Path,
    baseline_state_path: Path,
    since: str | None,
) -> list[dict]:
    rows: list[dict] = []
    vs = json.loads(variants_state_path.read_text(encoding="utf-8"))
    reset_at = since or vs.get("soak_reset_at")
    for _vid, slice_state in (vs.get("variants") or {}).items():
        if not isinstance(slice_state, dict):
            continue
        for raw in (slice_state.get("paper_positions") or {}).values():
            if not isinstance(raw, dict) or raw.get("status") != "closed":
                continue
            exit_ts = raw.get("exit_ts")
            if reset_at and exit_ts and str(exit_ts) < str(reset_at):
                continue
            rows.append(raw)
    if baseline_state_path.is_file():
        baseline = json.loads(baseline_state_path.read_text(encoding="utf-8"))
        for raw in (baseline.get("paper_positions") or {}).values():
            if not isinstance(raw, dict) or raw.get("status") != "closed":
                continue
            exit_ts = raw.get("exit_ts")
            if reset_at and exit_ts and str(exit_ts) < str(reset_at):
                continue
            raw = dict(raw)
            raw.setdefault("variant_id", None)
            rows.append(raw)
    return rows


def backfill(
    *,
    variants_state_path: Path,
    baseline_state_path: Path,
    log_path: Path,
    out_path: Path,
    since: str | None,
    dry_run: bool,
) -> dict:
    from xsp_killer.lane_a_ta import TaRules

    closed = _iter_closed_positions(
        variants_state_path=variants_state_path,
        baseline_state_path=baseline_state_path,
        since=since,
    )
    state: dict = {"paper_shadow_events": []}
    records: list[dict] = []
    ta_rules = TaRules.from_yaml(DEFAULT_RULES)
    suppress_dte = ta_rules.suppress_morning_cut_dte_gte

    for raw in closed:
        pos, rules = _lane_position(raw)
        exit_ts = _parse_ts(raw.get("exit_ts")) or datetime.now(ET)
        now_et = exit_ts.astimezone(ET)
        alert = ExitAlert(
            position_id=pos.position_id,
            exit_reason=str(raw.get("exit_reason") or "manual"),
            message=f"backfill {raw.get('exit_reason')}",
            pnl_usd=raw.get("exit_pnl_usd"),
            pnl_per_contract=raw.get("exit_pnl_per_contract"),
        )
        rec = build_shadow_exit_record(
            pos,
            rules,
            now_et=now_et,
            ta_signal=None,
            suppress_morning_cut_dte=suppress_dte,
            actual_alert=alert,
            evaluated_at=raw.get("exit_ts") or now_et.isoformat(),
            evaluate_fn=evaluate_exit_alerts,
        )
        payload = rec.to_dict()
        payload["backfill"] = True
        payload["session_note"] = "post-reset session 1 (2026-06-23 morning cut)"
        records.append(payload)
        if not dry_run:
            append_shadow_exit_log(rec, state=state, log_path=log_path)

    summary = {
        "backfilled_at": datetime.now().astimezone().isoformat(),
        "positions_n": len(records),
        "log_path": str(log_path),
        "records": records,
    }
    if not dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description="Backfill shadow exit bracket logs")
    p.add_argument("--variants-state", type=Path, default=DEFAULT_VARIANTS_STATE)
    p.add_argument("--baseline-state", type=Path, default=DEFAULT_STATE)
    p.add_argument("--log", type=Path, default=DEFAULT_LOG)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--since", help="Only exits after this ISO timestamp (default: soak_reset_at)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    summary = backfill(
        variants_state_path=args.variants_state,
        baseline_state_path=args.baseline_state,
        log_path=args.log,
        out_path=args.out,
        since=args.since,
        dry_run=args.dry_run,
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "records"}, indent=2))
    print(f"records: {summary['positions_n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
