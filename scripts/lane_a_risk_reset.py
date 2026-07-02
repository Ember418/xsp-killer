#!/usr/bin/env python3
"""Set the Lane A paper-risk streak reset marker."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

from xsp_killer.lane_a_monitor import DEFAULT_STATE, load_state, save_state  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("xsp_killer.lane_a_risk_reset")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set Lane A consecutive-loss streak reset marker"
    )
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument(
        "--at",
        help="UTC timestamp override in ISO format (default: now)",
    )
    args = parser.parse_args()

    reset_at = args.at or datetime.now(timezone.utc).isoformat()
    state = load_state(args.state)
    state["risk_streak_reset_at"] = reset_at
    save_state(args.state, state)
    logger.info("set risk_streak_reset_at=%s in %s", reset_at, args.state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
