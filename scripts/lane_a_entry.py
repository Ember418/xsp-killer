#!/usr/bin/env python3
"""XSP Lane A paper entry CLI — 15:45–16:00 ET window, log only (no RH orders)."""

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

from xsp_killer.lane_a_entry import (  # noqa: E402
    DEFAULT_OUT,
    DEFAULT_RULES,
    DEFAULT_STATE,
    ET,
    close_open_paper_positions,
    load_state,
    run_paper_entry,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("xsp_killer.lane_a_entry")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="XSP Lane A paper entry (15:45–16:00 ET)"
    )
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--force", action="store_true", help="Bypass window/time gates (tests)"
    )
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--at-et", help="Override ET time (ISO or HH:MM)")
    parser.add_argument(
        "--close-paper",
        nargs="?",
        const="__all__",
        metavar="POSITION_ID",
        help="Close open paper position(s); omit ID to close all",
    )
    args = parser.parse_args()

    if args.close_paper:
        state = load_state(args.state)
        pid = None if args.close_paper == "__all__" else args.close_paper
        closed = close_open_paper_positions(
            state,
            state_path=args.state,
            reason="operator_test_cleanup",
            position_id=pid,
        )
        logger.info("closed %d paper position(s)", len(closed))
        for row in closed:
            logger.info(
                "closed %s pnl=%s",
                row.get("position_id"),
                row.get("exit_pnl_usd"),
            )
        return 0

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

    decision = run_paper_entry(
        rules_path=args.rules,
        state_path=args.state,
        now_et=now_et,
        force=args.force,
        publish_intel=not args.no_publish,
    )

    logger.info(
        "lane_a_entry entered=%s regime=%s prior_spy=%s reason=%s",
        decision.entered,
        decision.regime,
        decision.prior_day_spy_return_pct,
        decision.skip_reason,
    )
    if decision.position:
        logger.info(
            "paper position %s strike=%s exp=%s premium=%s",
            decision.position.get("position_id"),
            decision.position.get("strike"),
            decision.position.get("expiration_date"),
            decision.position.get("average_price"),
        )
    if args.out != DEFAULT_OUT:
        args.out.write_text(
            json.dumps(decision.to_dict(), indent=2) + "\n", encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
