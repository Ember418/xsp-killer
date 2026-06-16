#!/usr/bin/env python3
"""XSP Lane B LEAPS hedge monitor CLI — Phase 0 alerts only."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

from xsp_killer.lane_b_monitor import (  # noqa: E402
    DEFAULT_OUT,
    DEFAULT_RULES,
    DEFAULT_STATE,
    run_monitor,
    write_report,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("xsp_killer.lane_b_monitor")


def main() -> int:
    parser = argparse.ArgumentParser(description="XSP Lane B LEAPS hedge monitor (Phase 0)")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--fixture", type=Path, help="RH-like positions JSON")
    parser.add_argument("--no-publish", action="store_true")
    args = parser.parse_args()

    positions_override = None
    if args.fixture:
        positions_override = json.loads(args.fixture.read_text(encoding="utf-8"))

    report = run_monitor(
        rules_path=args.rules,
        state_path=args.state,
        positions_override=positions_override,
        publish_intel=not args.no_publish,
    )
    out = write_report(report, args.out)
    logger.info(
        "lane_b calls=%d puts=%d alerts=%d mtm=%s out=%s",
        len(report.calls),
        len(report.hedge_puts),
        len(report.alerts),
        report.portfolio_mtm_usd,
        out,
    )
    for alert in report.alerts:
        logger.warning("ALERT %s: %s", alert.get("alert_code"), alert.get("message"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
