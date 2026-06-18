#!/usr/bin/env python3
"""Run Lane A variant soak — parallel shadow entries/monitors + scoreboard."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from xsp_killer.lane_a_variants import (  # noqa: E402
    build_scoreboard,
    run_all_variant_entries,
    run_all_variant_monitors,
)

ET = ZoneInfo("America/New_York")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("xsp_killer.lane_a_variants_cli")


def _parse_at_et(raw: str | None) -> datetime | None:
    if not raw:
        return None
    s = raw.strip()
    if "T" in s or (len(s) > 8 and "-" in s):
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=ET)
    h, m = s.split(":")
    today = datetime.now(ET).date()
    return datetime.combine(today, datetime.strptime(s, "%H:%M").time(), tzinfo=ET)


def main() -> int:
    parser = argparse.ArgumentParser(description="XSP Lane A variant soak runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_entry = sub.add_parser("entry", help="Run close-window entry for all active variants")
    p_entry.add_argument("--at-et", help="Override evaluation time (HH:MM or ISO)")
    p_entry.add_argument("--force", action="store_true")

    p_mon = sub.add_parser("monitor", help="Run morning monitor for all active variants")
    p_mon.add_argument("--at-et", help="Override evaluation time (HH:MM or ISO)")

    sub.add_parser("scoreboard", help="Rebuild variant comparison scoreboard")

    args = parser.parse_args()
    now_et = _parse_at_et(getattr(args, "at_et", None))

    if args.cmd == "entry":
        results = run_all_variant_entries(now_et=now_et, force=bool(args.force))
        for spec, decision in results:
            print(
                f"{spec.variant_id}: entered={decision.entered} "
                f"reason={decision.skip_reason or 'ok'}"
            )
        build_scoreboard()
        return 0

    if args.cmd == "monitor":
        results = run_all_variant_monitors(now_et=now_et)
        for spec, report in results:
            print(
                f"{spec.variant_id}: positions={len(report.positions)} "
                f"alerts={len(report.alerts)} mtm={report.paper_mtm_usd}"
            )
        build_scoreboard()
        return 0

    if args.cmd == "scoreboard":
        out = build_scoreboard()
        payload = json.loads(out.read_text(encoding="utf-8"))
        print(json.dumps(payload, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
