"""Lane A variant soak — parallel paper instances with different entry/exit params."""

from __future__ import annotations

import fcntl
import json
import shutil
import logging
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from xsp_killer.lane_a_entry import run_paper_entry, summarize_entry_telemetry_from_logs
from xsp_killer.lane_a_monitor import (
    DEFAULT_RULES,
    load_state,
    run_monitor,
    save_state,
)

logger = logging.getLogger("xsp_killer.lane_a_variants")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VARIANTS_CONFIG = ROOT / "config" / "lane_a_variants.yaml"
DEFAULT_VARIANTS_STATE = ROOT / "briefs" / "xsp-lane-a-variants-state.json"
DEFAULT_SCOREBOARD = ROOT / "briefs" / "xsp-lane-a-variants-scoreboard.json"

# Side-by-side regime-gate experiment axis (baseline GREEN vs YELLOW bounce brackets).
REGIME_GATE_COMPARISON_IDS = (
    "v2_baseline_prod",
    "v2_yellow_mid_bounce",
    "v2_yellow_top_quartile_bounce",
)

PROMOTION_SESSIONS_GATE = 20


@dataclass
class VariantSpec:
    variant_id: str
    description: str
    active: bool
    overrides: dict[str, Any]

    @property
    def logic_version(self) -> str:
        logging_cfg = self.overrides.get("logging") or {}
        return str(logging_cfg.get("logic_version") or f"xsp_lane_a_{self.variant_id}")


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, val in patch.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def load_base_rules() -> dict[str, Any]:
    return yaml.safe_load(DEFAULT_RULES.read_text(encoding="utf-8")) or {}


def load_variant_specs(path: Path | None = None) -> list[VariantSpec]:
    cfg_path = path or DEFAULT_VARIANTS_CONFIG
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    specs: list[VariantSpec] = []
    for variant_id, raw in (data.get("variants") or {}).items():
        if not isinstance(raw, dict):
            continue
        specs.append(
            VariantSpec(
                variant_id=str(variant_id),
                description=str(raw.get("description") or ""),
                active=bool(raw.get("active", True)),
                overrides=dict(raw.get("overrides") or {}),
            )
        )
    return specs


def merged_rules_path(spec: VariantSpec, *, tmp_dir: Path | None = None) -> Path:
    merged = _deep_merge(load_base_rules(), spec.overrides)
    out_dir = tmp_dir or (ROOT / "briefs" / "variant_rules_cache")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{spec.variant_id}.yaml"
    out_path.write_text(yaml.safe_dump(merged, sort_keys=False), encoding="utf-8")
    return out_path


def load_variants_state(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_VARIANTS_STATE
    if not p.is_file():
        return {"variants": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"variants": {}}


def variant_state_slice(root: dict[str, Any], variant_id: str) -> dict[str, Any]:
    variants = root.setdefault("variants", {})
    if variant_id not in variants or not isinstance(variants[variant_id], dict):
        variants[variant_id] = {
            "paper_positions": {},
            "entry_log": [],
            "paper_events": [],
            "positions": {},
        }
    return variants[variant_id]


def _variants_state_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+", encoding="utf-8")
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    return fh


def save_variant_state_slice(
    root: dict[str, Any],
    variant_id: str,
    slice_state: dict[str, Any],
    *,
    path: Path | None = None,
) -> None:
    root.setdefault("variants", {})[variant_id] = slice_state
    p = path or DEFAULT_VARIANTS_STATE
    lock = _variants_state_lock(p)
    try:
        p.write_text(json.dumps(root, indent=2) + "\n", encoding="utf-8")
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


def run_variant_entry(
    spec: VariantSpec,
    *,
    root_state: dict[str, Any] | None = None,
    state_path: Path | None = None,
    now_et: datetime | None = None,
    force: bool = False,
) -> Any:
    root = root_state if root_state is not None else load_variants_state(state_path)
    slice_state = variant_state_slice(root, spec.variant_id)
    rules_path = merged_rules_path(spec)
    log_path = ROOT / "logs" / f"xsp_lane_a_variant_{spec.variant_id}.jsonl"
    tmp_state = ROOT / "briefs" / f".variant-{spec.variant_id}-state.json"
    save_state(tmp_state, slice_state)

    decision = run_paper_entry(
        rules_path=rules_path,
        state_path=tmp_state,
        log_path=log_path,
        now_et=now_et,
        force=force,
        publish_intel=False,
        brief_path=False,
    )
    updated = load_state(tmp_state)
    if decision.entered and decision.position:
        pos = dict(decision.position)
        pos["variant_id"] = spec.variant_id
        updated.setdefault("paper_positions", {})[pos["position_id"]] = pos
    save_variant_state_slice(root, spec.variant_id, updated, path=state_path)
    try:
        tmp_state.unlink(missing_ok=True)
    except OSError:
        pass
    return decision


def run_variant_monitor(
    spec: VariantSpec,
    *,
    root_state: dict[str, Any] | None = None,
    state_path: Path | None = None,
    now_et: datetime | None = None,
) -> Any:
    root = root_state if root_state is not None else load_variants_state(state_path)
    slice_state = variant_state_slice(root, spec.variant_id)
    rules_path = merged_rules_path(spec)
    tmp_state = ROOT / "briefs" / f".variant-{spec.variant_id}-state.json"
    save_state(tmp_state, slice_state)
    log_path = ROOT / "logs" / f"xsp_lane_a_variant_{spec.variant_id}.jsonl"

    report = run_monitor(
        rules_path=rules_path,
        state_path=tmp_state,
        now_et=now_et,
        publish_intel=False,
        log_path=log_path,
        write_paper_brief=False,
    )
    updated = load_state(tmp_state)
    save_variant_state_slice(root, spec.variant_id, updated, path=state_path)
    try:
        tmp_state.unlink(missing_ok=True)
    except OSError:
        pass
    return report


def _prune_variant_rules_cache(active_ids: set[str]) -> None:
    cache_dir = ROOT / "briefs" / "variant_rules_cache"
    if not cache_dir.is_dir():
        return
    for fp in cache_dir.glob("*.yaml"):
        if fp.stem not in active_ids:
            try:
                fp.unlink(missing_ok=True)
            except OSError:
                pass


def run_all_variant_entries(
    *,
    config_path: Path | None = None,
    state_path: Path | None = None,
    now_et: datetime | None = None,
    exclude: set[str] | None = None,
    force: bool = False,
) -> list[tuple[VariantSpec, Any]]:
    from xsp_killer.chain_cache import clear_chain_cache

    specs = load_variant_specs(config_path)
    _prune_variant_rules_cache({s.variant_id for s in specs if s.active})
    clear_chain_cache()
    root = load_variants_state(state_path)
    results: list[tuple[VariantSpec, Any]] = []
    for spec in specs:
        if not spec.active:
            continue
        if exclude and spec.variant_id in exclude:
            continue
        try:
            decision = run_variant_entry(
                spec,
                root_state=root,
                state_path=state_path,
                now_et=now_et,
                force=force,
            )
            results.append((spec, decision))
            logger.info(
                "variant_entry %s entered=%s reason=%s",
                spec.variant_id,
                decision.entered,
                decision.skip_reason,
            )
        except Exception as exc:
            logger.exception("variant_entry %s failed: %s", spec.variant_id, exc)
    return results


def run_all_variant_monitors(
    *,
    config_path: Path | None = None,
    state_path: Path | None = None,
    now_et: datetime | None = None,
    exclude: set[str] | None = None,
) -> list[tuple[VariantSpec, Any]]:
    from xsp_killer.chain_cache import clear_chain_cache

    clear_chain_cache()
    root = load_variants_state(state_path)
    results: list[tuple[VariantSpec, Any]] = []
    for spec in load_variant_specs(config_path):
        if not spec.active:
            continue
        if exclude and spec.variant_id in exclude:
            continue
        try:
            report = run_variant_monitor(
                spec, root_state=root, state_path=state_path, now_et=now_et
            )
            results.append((spec, report))
            logger.info(
                "variant_monitor %s positions=%d alerts=%d",
                spec.variant_id,
                len(report.positions),
                len(report.alerts),
            )
        except Exception as exc:
            logger.exception("variant_monitor %s failed: %s", spec.variant_id, exc)
    return results


def _soak_reset_at(root: dict[str, Any]) -> str | None:
    raw = root.get("soak_reset_at")
    return str(raw) if raw else None


def _events_in_soak_epoch(
    state: dict[str, Any], soak_reset_at: str | None
) -> list[dict[str, Any]]:
    events = [e for e in (state.get("paper_events") or []) if isinstance(e, dict)]
    if not soak_reset_at:
        return events
    return [e for e in events if str(e.get("evaluated_at") or "") >= soak_reset_at]


def _entry_logs_in_soak_epoch(
    state: dict[str, Any], soak_reset_at: str | None
) -> list[dict[str, Any]]:
    logs = [e for e in (state.get("entry_log") or []) if isinstance(e, dict)]
    if not soak_reset_at:
        return logs
    return [e for e in logs if str(e.get("evaluated_at") or "") >= soak_reset_at]


def _parse_timestamp(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _last_exit_with_contract_meta(
    state: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if not events:
        return None
    last_exit = dict(events[-1])
    paper_positions = state.get("paper_positions") or {}
    position = (
        paper_positions.get(last_exit.get("position_id"))
        if isinstance(paper_positions, dict)
        else None
    )
    if not isinstance(position, dict):
        position = {}

    dte_actual = last_exit.get("dte_actual", position.get("dte_actual"))
    if dte_actual is not None:
        last_exit["dte_actual"] = dte_actual

    expiration = (
        last_exit.get("expiration")
        or last_exit.get("expiration_date")
        or position.get("expiration")
        or position.get("expiration_date")
    )
    if expiration is not None:
        last_exit["expiration"] = expiration

    return last_exit


def reset_soak(
    *,
    commit: str | None = None,
    reason: str = "post-patch scoreboard epoch",
    state_path: Path | None = None,
    baseline_state_path: Path | None = None,
    scoreboard_path: Path | None = None,
    archive_dir: Path | None = None,
    clear_baseline_events: bool = True,
) -> dict[str, Any]:
    """Archive pre-reset soak data and start a fresh scoreboard epoch."""
    reset_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    sp = state_path or DEFAULT_VARIANTS_STATE
    bp = baseline_state_path or (ROOT / "briefs" / "xsp-lane-a-state.json")
    sb = scoreboard_path or DEFAULT_SCOREBOARD
    ad = archive_dir or (ROOT / "briefs" / "archive")
    ad.mkdir(parents=True, exist_ok=True)
    stamp = reset_at.replace(":", "").replace("-", "")[:15]

    archived: list[str] = []
    for src in (sp, sb, bp):
        if src.is_file():
            dest = ad / f"{src.stem}-pre-reset-{stamp}{src.suffix}"
            shutil.copy2(src, dest)
            archived.append(str(dest))

    root = load_variants_state(sp)
    for slice_state in (root.get("variants") or {}).values():
        if isinstance(slice_state, dict):
            slice_state["paper_events"] = []
            slice_state["entry_log"] = []

    root["soak_reset_at"] = reset_at
    if commit:
        root["soak_reset_commit"] = commit
    root["soak_reset_reason"] = reason
    root["soak_reset_archives"] = archived

    lock = _variants_state_lock(sp)
    try:
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(root, indent=2) + "\n", encoding="utf-8")
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()

    if clear_baseline_events and bp.is_file():
        try:
            baseline = json.loads(bp.read_text(encoding="utf-8"))
            baseline["paper_events"] = []
            baseline["soak_reset_at"] = reset_at
            if commit:
                baseline["soak_reset_commit"] = commit
            from xsp_killer.lane_a_entry import _sync_entry_telemetry

            _sync_entry_telemetry(baseline)
            bp.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("baseline soak reset failed: %s", exc)

    out = build_scoreboard(state_path=sp, baseline_state_path=bp, out_path=sb)
    meta = {
        "soak_reset_at": reset_at,
        "soak_reset_commit": commit,
        "soak_reset_reason": reason,
        "archived": archived,
        "scoreboard": str(out),
    }
    logger.info("variant soak reset: %s", meta)
    return meta


def clear_pnl_epoch(
    *,
    commit: str | None = None,
    reason: str = "unreliable PnL cleared — per-variant epoch restart",
    state_path: Path | None = None,
    baseline_state_path: Path | None = None,
    scoreboard_path: Path | None = None,
    archive_dir: Path | None = None,
) -> dict[str, Any]:
    """Clear paper_events only; keep entry history. Restart per-variant PnL tracking."""
    epoch_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    sp = state_path or DEFAULT_VARIANTS_STATE
    bp = baseline_state_path or (ROOT / "briefs" / "xsp-lane-a-state.json")
    sb = scoreboard_path or DEFAULT_SCOREBOARD
    ad = archive_dir or (ROOT / "briefs" / "archive")
    ad.mkdir(parents=True, exist_ok=True)
    stamp = epoch_at.replace(":", "").replace("-", "")[:15]

    archived: list[str] = []
    for src in (sp, sb, bp):
        if src.is_file():
            dest = ad / f"{src.stem}-pre-pnl-clear-{stamp}{src.suffix}"
            shutil.copy2(src, dest)
            archived.append(str(dest))

    root = load_variants_state(sp)
    for slice_state in (root.get("variants") or {}).values():
        if isinstance(slice_state, dict):
            slice_state["paper_events"] = []

    root["soak_reset_at"] = epoch_at
    root["pnl_epoch_at"] = epoch_at
    if commit:
        root["pnl_epoch_commit"] = commit
    root["pnl_clear_reason"] = reason
    root["pnl_clear_archives"] = archived

    lock = _variants_state_lock(sp)
    try:
        sp.write_text(json.dumps(root, indent=2) + "\n", encoding="utf-8")
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()

    if bp.is_file():
        try:
            baseline = json.loads(bp.read_text(encoding="utf-8"))
            baseline["paper_events"] = []
            baseline["soak_reset_at"] = epoch_at
            baseline["pnl_epoch_at"] = epoch_at
            if commit:
                baseline["pnl_epoch_commit"] = commit
            from xsp_killer.lane_a_entry import _sync_entry_telemetry, _write_entry_telemetry_brief

            _sync_entry_telemetry(baseline)
            bp.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
            _write_entry_telemetry_brief(baseline)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("baseline pnl clear failed: %s", exc)

    out = build_scoreboard(state_path=sp, baseline_state_path=bp, out_path=sb)
    return {
        "pnl_epoch_at": epoch_at,
        "pnl_epoch_commit": commit,
        "pnl_clear_reason": reason,
        "archived": archived,
        "scoreboard": str(out),
    }


def _variant_track_meta(
    variant_id: str,
    spec: VariantSpec | None,
) -> dict[str, Any]:
    """Regime-gate metadata for scoreboard rows and cross-variant comparison."""
    if spec is not None:
        entry = spec.overrides.get("entry") or {}
        logic_version = spec.logic_version
    elif variant_id == "v2_baseline_prod":
        base = load_base_rules()
        entry = base.get("entry") or {}
        logic_version = str((base.get("logging") or {}).get("logic_version") or "")
    else:
        entry = {}
        logic_version = None

    regime_gate = str(entry.get("regime_gate") or "GREEN")
    yellow_frac_min = entry.get("regime_yellow_frac_min")

    meta: dict[str, Any] = {
        "logic_version": logic_version,
        "regime_gate": regime_gate,
        "regime_yellow_frac_min": yellow_frac_min,
    }
    if regime_gate == "GREEN_OR_YELLOW_BOUNCE":
        meta["track_family"] = "yellow_bounce_frac_axis"
    elif regime_gate == "GREEN" and variant_id == "v2_baseline_prod":
        meta["track_family"] = "baseline_green"
    return meta


def _entry_session_stats(entry_logs: list[dict[str, Any]]) -> dict[str, int]:
    entered_sessions = sum(1 for row in entry_logs if row.get("entered"))
    regime_gate_skips = sum(
        1
        for row in entry_logs
        if str(row.get("skip_reason") or "").startswith("regime ")
    )
    bounce_signal_sessions = sum(1 for row in entry_logs if row.get("bb_entry_ok"))
    bounce_blocked_by_regime = sum(
        1
        for row in entry_logs
        if row.get("bb_entry_ok")
        and not row.get("entered")
        and str(row.get("skip_reason") or "").startswith("regime ")
    )
    return {
        "entered_sessions": entered_sessions,
        "regime_gate_skip_sessions": regime_gate_skips,
        "bb_bounce_signal_sessions": bounce_signal_sessions,
        "bb_bounce_blocked_by_regime_sessions": bounce_blocked_by_regime,
    }


def _vol_shadow_from_log_row(row: dict[str, Any]) -> dict[str, Any] | None:
    raw = row.get("vol_shadow")
    if isinstance(raw, dict):
        return raw
    if row.get("spy_rv_annualized") is not None or row.get("vol_shadow_would_block") is not None:
        return {
            "spy_rv_annualized": row.get("spy_rv_annualized"),
            "shadow_would_block": row.get("vol_shadow_would_block"),
            "reason": row.get("vol_shadow_reason"),
        }
    return None


def _vol_shadow_session_stats(entry_logs: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate shadow vol gate observations from epoch entry_log rows."""
    would_block_sessions = 0
    rvs: list[float] = []
    latest: dict[str, Any] | None = None
    for row in entry_logs:
        vs = _vol_shadow_from_log_row(row)
        if vs is None:
            continue
        latest = vs
        if vs.get("shadow_would_block"):
            would_block_sessions += 1
        rv = vs.get("spy_rv_annualized")
        if rv is not None:
            try:
                rvs.append(float(rv))
            except (TypeError, ValueError):
                pass
    return {
        "vol_shadow_would_block_sessions": would_block_sessions,
        "vol_shadow_latest_spy_rv": (latest or {}).get("spy_rv_annualized"),
        "vol_shadow_latest_would_block": (latest or {}).get("shadow_would_block"),
        "vol_shadow_avg_spy_rv": round(sum(rvs) / len(rvs), 4) if rvs else None,
    }


def _build_regime_gate_comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {row["variant_id"]: row for row in rows}
    comparison_rows: list[dict[str, Any]] = []
    for variant_id in REGIME_GATE_COMPARISON_IDS:
        row = by_id.get(variant_id)
        if row is None:
            continue
        comparison_rows.append(
            {
                "variant_id": variant_id,
                "description": row.get("description"),
                "logic_version": row.get("logic_version"),
                "regime_gate": row.get("regime_gate"),
                "regime_yellow_frac_min": row.get("regime_yellow_frac_min"),
                "track_family": row.get("track_family"),
                "sessions_evaluated": row.get("sessions_evaluated"),
                "entered_sessions": row.get("entered_sessions"),
                "trades_closed": row.get("trades_closed"),
                "realized_pnl_usd": row.get("realized_pnl_usd"),
                "avg_pnl_per_trade_usd": row.get("avg_pnl_per_trade_usd"),
                "bb_bounce_signal_sessions": row.get("bb_bounce_signal_sessions"),
                "bb_bounce_blocked_by_regime_sessions": row.get(
                    "bb_bounce_blocked_by_regime_sessions"
                ),
                "vol_shadow_would_block_sessions": row.get(
                    "vol_shadow_would_block_sessions"
                ),
                "vol_shadow_latest_spy_rv": row.get("vol_shadow_latest_spy_rv"),
                "vol_shadow_latest_would_block": row.get(
                    "vol_shadow_latest_would_block"
                ),
                "vol_shadow_avg_spy_rv": row.get("vol_shadow_avg_spy_rv"),
                "vs_baseline_avg_per_trade_usd": row.get(
                    "vs_baseline_avg_per_trade_usd"
                ),
            }
        )
    return {
        "description": (
            "Side-by-side GREEN baseline vs YELLOW bounce brackets (frac≥0.50 vs "
            "frac≥0.75). Independent shadow books — compare avg_pnl_per_trade_usd "
            "and how often each gate would have entered."
        ),
        "track_family": "yellow_bounce_frac_axis",
        "baseline_variant_id": "v2_baseline_prod",
        "variants": comparison_rows,
    }


def _promotion_meta(sessions_evaluated: int, trades_closed: int) -> dict[str, Any]:
    remaining = max(0, PROMOTION_SESSIONS_GATE - sessions_evaluated)
    if sessions_evaluated < PROMOTION_SESSIONS_GATE:
        status = "collecting"
    elif trades_closed == 0:
        status = "sessions_met_no_trades"
    else:
        status = "eligible_review"
    return {
        "promotion_sessions_gate": PROMOTION_SESSIONS_GATE,
        "sessions_to_promotion_gate": remaining,
        "promotion_status": status,
        "promotion_ready": status == "eligible_review",
    }


def _build_promotion_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [
        r["variant_id"]
        for r in rows
        if r.get("promotion_ready") and r.get("variant_id") != "v2_baseline_prod"
    ]
    collecting = sum(
        1 for r in rows if r.get("promotion_status") == "collecting"
    )
    return {
        "sessions_gate": PROMOTION_SESSIONS_GATE,
        "variants_collecting": collecting,
        "variants_eligible_review": eligible,
        "baseline_promotion_ready": bool(
            next(
                (r for r in rows if r.get("variant_id") == "v2_baseline_prod"),
                {},
            ).get("promotion_ready")
        ),
    }


def build_scoreboard(
    *,
    config_path: Path | None = None,
    state_path: Path | None = None,
    baseline_state_path: Path | None = None,
    out_path: Path | None = None,
) -> Path:
    """Aggregate realized paper PnL per variant for comparison."""
    specs = {s.variant_id: s for s in load_variant_specs(config_path)}
    root = load_variants_state(state_path)
    rows: list[dict[str, Any]] = []
    latest_entry_eval: datetime | None = None

    soak_reset_at = _soak_reset_at(root)

    def _summarize(
        variant_id: str,
        state: dict[str, Any],
        description: str,
        spec: VariantSpec | None = None,
    ) -> None:
        events = _events_in_soak_epoch(state, soak_reset_at)
        entry_logs = _entry_logs_in_soak_epoch(state, soak_reset_at)
        open_pos = [
            p
            for p in (state.get("paper_positions") or {}).values()
            if isinstance(p, dict) and p.get("status", "open") == "open"
        ]
        nonlocal latest_entry_eval
        for row in entry_logs:
            evaluated_at = _parse_timestamp(row.get("evaluated_at"))
            if evaluated_at is None:
                continue
            if latest_entry_eval is None or evaluated_at > latest_entry_eval:
                latest_entry_eval = evaluated_at
        realized = round(sum(float(e.get("paper_pnl_usd") or 0) for e in events), 2)
        wins = sum(1 for e in events if float(e.get("paper_pnl_usd") or 0) > 0)
        losses = sum(1 for e in events if float(e.get("paper_pnl_usd") or 0) < 0)
        trades = len(events)
        sessions_evaluated = len(entry_logs)
        win_rate = round(wins / trades * 100.0, 1) if trades else None
        avg_pnl = round(realized / trades, 2) if trades else None
        row: dict[str, Any] = {
            "variant_id": variant_id,
            "description": description,
            "trades_closed": trades,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": win_rate,
            "realized_pnl_usd": realized,
            "avg_pnl_per_trade_usd": avg_pnl,
            "sessions_evaluated": sessions_evaluated,
            "sessions_to_gate": max(0, 20 - sessions_evaluated),
            "open_positions": len(open_pos),
            "last_exit": _last_exit_with_contract_meta(state, events),
        }
        row.update(_variant_track_meta(variant_id, spec))
        row.update(_entry_session_stats(entry_logs))
        row.update(_vol_shadow_session_stats(entry_logs))
        row.update(_promotion_meta(sessions_evaluated, trades))
        tel = summarize_entry_telemetry_from_logs(entry_logs)
        if tel.get("sessions_evaluated", 0) > 0:
            row["entry_telemetry"] = {
                "skip_reason_counts": tel.get("skip_reason_counts") or {},
                "regime_counts": tel.get("regime_counts") or {},
                "entered_sessions": tel.get("entered_sessions", 0),
            }
        rows.append(row)

    # Shadow variants
    state_variants = root.get("variants") or {}
    active_specs = [spec for spec in specs.values() if spec.active]
    variant_ids = list(
        dict.fromkeys(
            [spec.variant_id for spec in active_specs] + list(state_variants.keys())
        )
    )
    for variant_id in variant_ids:
        spec = specs.get(variant_id)
        if spec is not None and not spec.active:
            continue
        raw_slice_state = state_variants.get(variant_id)
        slice_state = raw_slice_state if isinstance(raw_slice_state, dict) else {}
        desc = spec.description if spec else ""
        _summarize(variant_id, slice_state, desc, spec=spec)

    # Production baseline from main state
    baseline_path = baseline_state_path or (ROOT / "briefs" / "xsp-lane-a-state.json")
    if baseline_path.is_file():
        try:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            _summarize(
                "v2_baseline_prod",
                baseline,
                "Production lane_a_rules.yaml (systemd cron)",
                spec=None,
            )
        except (json.JSONDecodeError, OSError):
            pass

    baseline_row = next(
        (r for r in rows if r["variant_id"] == "v2_baseline_prod"), None
    )
    shadow_rows = [r for r in rows if r["variant_id"] != "v2_baseline_prod"]
    baseline_avg = (baseline_row or {}).get("avg_pnl_per_trade_usd")
    for row in shadow_rows:
        avg = row.get("avg_pnl_per_trade_usd")
        if baseline_avg is not None and avg is not None:
            row["vs_baseline_avg_per_trade_usd"] = round(avg - baseline_avg, 2)
        else:
            row["vs_baseline_avg_per_trade_usd"] = None

    shadow_rows.sort(
        key=lambda r: (
            r.get("avg_pnl_per_trade_usd") is not None,
            r.get("avg_pnl_per_trade_usd") or -1e18,
        ),
        reverse=True,
    )
    ordered = shadow_rows + ([baseline_row] if baseline_row else [])
    updated_at_dt = datetime.now(timezone.utc)
    updated_at = updated_at_dt.isoformat()
    last_entry_eval_at = latest_entry_eval.isoformat() if latest_entry_eval else None
    stale = latest_entry_eval is None or (
        updated_at_dt - latest_entry_eval
    ) > timedelta(hours=36)
    payload = {
        "updated_at": updated_at,
        "soak_reset_at": soak_reset_at,
        "pnl_epoch_at": root.get("pnl_epoch_at") or soak_reset_at,
        "soak_reset_commit": root.get("soak_reset_commit"),
        "pnl_epoch_commit": root.get("pnl_epoch_commit"),
        "last_entry_eval_at": last_entry_eval_at,
        "stale": stale,
        "comparison_guidance": (
            "Rank shadow variants by avg_pnl_per_trade_usd vs v2_baseline_prod. "
            "Do NOT sum PnL across variants — configs are independent experiments."
        ),
        "ranked_by": "avg_pnl_per_trade_usd",
        "baseline_prod": baseline_row,
        "shadow_variants": shadow_rows,
        "variants": ordered,
        "regime_gate_comparison": _build_regime_gate_comparison(rows),
        "promotion_summary": _build_promotion_summary(rows),
        "note": (
            "Per-variant comparison only. Need ≥20 post-epoch sessions per variant before promotion."
        ),
    }
    out = out_path or DEFAULT_SCOREBOARD
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out
