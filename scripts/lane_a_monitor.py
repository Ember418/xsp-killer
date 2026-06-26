#!/usr/bin/env python3
"""XSP Lane A Phase 0 monitor CLI — alerts only, no auto-close."""

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

from xsp_killer.lane_a_monitor import (  # noqa: E402
    DEFAULT_OUT,
    DEFAULT_RULES,
    DEFAULT_STATE,
    ET,
    run_monitor,
    write_report,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("xsp_killer.lane_a_monitor")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="XSP Lane A overnight swing monitor (Phase 0)"
    )
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--fixture",
        type=Path,
        help="JSON file with RH-like open option positions (skips live RH poll)",
    )
    parser.add_argument(
        "--no-publish", action="store_true", help="Skip intel:xsp_lane_a_alert publish"
    )
    parser.add_argument(
        "--at-et",
        help="Override evaluation time (ISO or HH:MM) for replay/tests",
    )
    args = parser.parse_args()

    positions_override = None
    if args.fixture:
        positions_override = json.loads(args.fixture.read_text(encoding="utf-8"))

    now_et = None
    if args.at_et:
        raw = args.at_et.strip()
        if "T" in raw or "-" in raw and len(raw) > 8:
            now_et = datetime.fromisoformat(raw)
            if now_et.tzinfo is None:
                now_et = now_et.replace(tzinfo=ET)
        else:
            h, m = raw.split(":")
            today = datetime.now(ET).date()
            now_et = datetime.combine(
                today, datetime.strptime(raw, "%H:%M").time(), tzinfo=ET
            )

    report = run_monitor(
        rules_path=args.rules,
        state_path=args.state,
        positions_override=positions_override,
        now_et=now_et,
        publish_intel=not args.no_publish,
    )
    out = write_report(report, args.out)

    logger.info(
        "lane_a phase=%s positions=%d alerts=%d rh=%s regime=%s paper_mtm=%s out=%s",
        report.phase,
        len(report.positions),
        len(report.alerts),
        report.rh_connected,
        report.regime,
        report.paper_mtm_usd,
        out,
    )
    if report.errors:
        for err in report.errors:
            logger.warning("error: %s", err)
    if report.alerts:
        for alert in report.alerts:
            logger.warning(
                "ALERT %s: %s", alert.get("exit_reason"), alert.get("message")
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
