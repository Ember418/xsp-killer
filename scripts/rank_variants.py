#!/usr/bin/env python3
"""Rank Lane A shadow variants by realized paper P&L.

Reads the per-variant monitor logs (``logs/xsp_lane_a_variant_*.jsonl``),
reconstructs each closed trade from the first exit alert emitted for a
position, and prints a ranking by total realized P&L.

P&L in the logs is premium-scaled (SPY chain mid -> XSP notional via
``premium_scale``); the ``~1ct`` columns divide by that scale to approximate a
single real XSP contract.

Usage:
    python3 scripts/rank_variants.py [--scale 10] [--min-trades N] [--active-only]

With ``--active-only``, only variants marked ``active: true`` in
``config/lane_a_variants.yaml`` are ranked (pruned / inactive ids are skipped
even if their monitor logs still exist).
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LOG_GLOB = str(ROOT / "logs" / "xsp_lane_a_variant_*.jsonl")
VARIANTS_CONFIG = ROOT / "config" / "lane_a_variants.yaml"


def load_active_variant_ids(path: Path | None = None) -> set[str]:
    """Return variant ids with ``active: true`` in lane_a_variants.yaml."""
    cfg_path = path or VARIANTS_CONFIG
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    active: set[str] = set()
    for variant_id, raw in (data.get("variants") or {}).items():
        if isinstance(raw, dict) and bool(raw.get("active", True)):
            active.add(str(variant_id))
    return active


def analyze(path: str) -> dict:
    recs = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    entries = sum(1 for r in recs if r.get("event") == "paper_entry")
    first_exit: dict[str, tuple[str, float]] = {}
    for r in recs:
        if r.get("event") != "monitor_eval":
            continue
        for a in r.get("alerts", []):
            pid = a.get("position_id")
            reason = a.get("exit_reason")
            pnl = a.get("pnl_usd")
            if pid and reason and pnl is not None and pid not in first_exit:
                first_exit[pid] = (reason, float(pnl))
    closed = list(first_exit.values())
    n = len(closed)
    total = sum(p for _, p in closed)
    wins = sum(1 for _, p in closed if p > 0)
    reasons = collections.Counter(reason for reason, _ in closed)
    return {
        "entries": entries,
        "closed": n,
        "wins": wins,
        "total": total,
        "reasons": dict(reasons),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=10.0, help="premium_scale")
    ap.add_argument("--min-trades", type=int, default=0)
    ap.add_argument(
        "--active-only",
        action="store_true",
        help="only rank variants with active: true in config/lane_a_variants.yaml",
    )
    args = ap.parse_args()

    active_ids: set[str] | None = None
    if args.active_only:
        active_ids = load_active_variant_ids()

    rows = []
    for f in sorted(glob.glob(LOG_GLOB)):
        name = Path(f).stem.replace("xsp_lane_a_variant_", "")
        if active_ids is not None and name not in active_ids:
            continue
        rows.append((name, analyze(f)))
    rows.sort(key=lambda kv: -kv[1]["total"])

    hdr = (
        f"{'variant':<28}{'ent':>4}{'cls':>4}{'win%':>6}"
        f"{'pnl(scaled)':>13}{'~1ct':>9}{'~1ct/trade':>12}  reasons"
    )
    print(hdr)
    print("-" * len(hdr))
    for name, a in rows:
        n = a["closed"]
        if n < args.min_trades:
            continue
        wr = (a["wins"] / n * 100) if n else 0.0
        per = a["total"] / args.scale
        avg1 = (per / n) if n else 0.0
        print(
            f"{name:<28}{a['entries']:>4}{n:>4}{wr:>5.0f}%"
            f"{a['total']:>13,.0f}{per:>9,.0f}{avg1:>12,.1f}  {a['reasons']}"
        )


if __name__ == "__main__":
    main()
