#!/usr/bin/env python3
"""XSP Lane A intraday TA scan — BB bounce entry / upper BB exit (paper log only)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

from xsp_killer.lane_a_intraday import (  # noqa: E402
    DEFAULT_INTRADAY_OUT,
    DEFAULT_RULES,
    DEFAULT_STATE,
    ET,
    run_intraday_cycle,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("xsp_killer.lane_a_intraday")


def main() -> int:
    parser = argparse.ArgumentParser(description="XSP Lane A intraday BB/VWAP cycle")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--out", type=Path, default=DEFAULT_INTRADAY_OUT)
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--at-et", help="Override ET time (ISO or HH:MM)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    now_et = None
    if args.at_et:
        raw = args.at_et.strip()
        if "T" in raw or ("-" in raw and len(raw) > 8):
            now_et = datetime.fromisoformat(raw)
            if now_et.tzinfo is None:
                now_et = now_et.replace(tzinfo=ET)
        else:
            h, m = raw.split(":")
            today = datetime.now(ET).date()
            now_et = datetime.combine(
                today, datetime.strptime(raw, "%H:%M").time(), tzinfo=ET
            )

    report = run_intraday_cycle(
        rules_path=args.rules,
        state_path=args.state,
        now_et=now_et,
        publish_intel=not args.no_publish,
    )

    logger.info(
        "intraday rth=%s open=%d ta=%s entry=%s exits=%d reason=%s",
        report.in_rth,
        report.open_positions_n,
        report.ta_signal,
        report.entry_entered,
        report.exit_alerts_n,
        report.skip_reason,
    )

    if args.out != DEFAULT_INTRADAY_OUT:
        args.out.write_text(
            json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8"
        )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
