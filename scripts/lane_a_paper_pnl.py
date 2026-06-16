#!/usr/bin/env python3
"""Roll up XSP Lane A hypothetical paper PnL from monitor JSONL + state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from xsp_killer.lane_a_monitor import (  # noqa: E402
    DEFAULT_PAPER_BRIEF,
    DEFAULT_PAPER_LOG,
    DEFAULT_STATE,
    load_state,
    write_paper_pnl_brief,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="XSP Lane A paper PnL rollup")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--log", type=Path, default=DEFAULT_PAPER_LOG)
    parser.add_argument("--out", type=Path, default=DEFAULT_PAPER_BRIEF)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    state = load_state(args.state)
    latest_mtm = None
    latest_ts = None
    if args.log.is_file():
        for line in args.log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            latest_mtm = row.get("paper_mtm_usd")
            latest_ts = row.get("ts")

    class _R:
        evaluated_at = latest_ts
        logic_version = "xsp_lane_a_v1"
        paper_mtm_usd = latest_mtm

    out = write_paper_pnl_brief(state, report=_R(), out_path=args.out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"lane_a paper | open_mtm ${payload.get('open_positions_mtm_usd')} "
            f"| hypo_exits {payload.get('hypothetical_exits_n')} "
            f"| hypo_pnl ${payload.get('hypothetical_realized_pnl_usd')} "
            f"| out {out}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
