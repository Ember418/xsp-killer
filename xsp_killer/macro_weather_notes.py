"""K155 macro weather operator notes — log-only Lane A monitor enrichment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_K155_NOTES = ROOT / "config" / "k155_operator_notes.yaml"

USDJPY_ZONE = (162.25, 162.50)


def load_k155_notes(path: Path | None = None) -> dict[str, Any]:
    """Load K155 operator notes from YAML config."""
    p = path or DEFAULT_K155_NOTES
    if not p.is_file():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    block = data.get("k155")
    return dict(block) if isinstance(block, dict) else {}


def build_macro_weather_extras(
    *,
    usdjpy: float | None,
    sofr_curve_note: str | None,
    event_cluster: str | None,
) -> dict[str, Any]:
    """Build log-only macro weather extras for monitor JSON."""
    lo, hi = USDJPY_ZONE
    in_zone = usdjpy is not None and lo <= usdjpy <= hi
    return {
        "usdjpy": usdjpy,
        "usdjpy_zone_lo": lo,
        "usdjpy_zone_hi": hi,
        "usdjpy_in_zone": in_zone,
        "sofr_curve_note": sofr_curve_note,
        "event_cluster": event_cluster,
    }


def conviction_journal_fields(
    *,
    evidence_count: int,
    cross_asset_confirms: int,
    pro_con_balanced: bool,
) -> dict[str, Any]:
    """Trade journal conviction fields; block size-up on balanced pro/con alone."""
    conviction_sufficient = evidence_count >= 2 and cross_asset_confirms >= 1
    block_size_up = pro_con_balanced and not conviction_sufficient
    return {
        "evidence_count": evidence_count,
        "cross_asset_confirms": cross_asset_confirms,
        "pro_con_balanced": pro_con_balanced,
        "conviction_sufficient": conviction_sufficient,
        "block_size_up": block_size_up,
    }


def build_monitor_macro_weather_extras(
    notes: dict[str, Any] | None = None,
    *,
    usdjpy: float | None = None,
) -> dict[str, Any] | None:
    """Merge K155 YAML notes with runtime extras for monitor attachment."""
    k155 = notes if notes is not None else load_k155_notes()
    if not k155:
        return None

    sofr = k155.get("sofr_curve")
    sofr_note = sofr.get("note") if isinstance(sofr, dict) else None
    extras = build_macro_weather_extras(
        usdjpy=usdjpy,
        sofr_curve_note=sofr_note,
        event_cluster=str(k155.get("event_cluster") or ""),
    )
    extras["k155_version"] = k155.get("version")
    for key in (
        "events",
        "cme_ssf",
        "fundsmith_sentiment",
        "sox_kospi_watch",
        "usdjpy_zone",
        "macro_weather_snapshot",
        "conviction_journal",
        "vol_edge",
    ):
        if key in k155:
            extras[key] = k155[key]
    if isinstance(sofr, dict):
        extras["sofr_curve"] = sofr
    return extras


def maybe_enrich_with_muse_spark(prompt: str) -> dict[str, Any] | None:
    """Optional log-only Muse Spark enrichment when K157 spike is enabled."""
    from xsp_killer.muse_spark_spike import muse_spark_enabled, run_macro_research_enrichment

    if not muse_spark_enabled():
        return None
    return run_macro_research_enrichment(prompt)
