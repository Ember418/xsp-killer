#!/usr/bin/env bash
# Standalone VPS health/soak report for xsp-killer.
set -uo pipefail

XSP_KILLER_DIR="/opt/xsp-killer"
PYTHON_BIN="/usr/bin/python3"

cd "${XSP_KILLER_DIR}"
export PYTHONPATH="${XSP_KILLER_DIR}"

quick=0
strict=0
for arg in "$@"; do
  case "$arg" in
    --quick) quick=1 ;;
    --strict) strict=1 ;;
    *)
      echo "Unknown arg: ${arg}" >&2
      echo "Usage: $0 [--quick] [--strict]" >&2
      exit 2
      ;;
  esac
done

mkdir -p "${XSP_KILLER_DIR}/logs"
timestamp_utc="$(date -u +%Y%m%dT%H%M%SZ)"
report_path="${XSP_KILLER_DIR}/logs/health_soak_${timestamp_utc}.md"

timer_tmp="$(mktemp)"
scoreboard_payload_tmp="$(mktemp)"
scoreboard_meta_tmp="$(mktemp)"
scoreboard_log_tmp="$(mktemp)"
pytest_tmp="$(mktemp)"
paper_brief_path="${XSP_KILLER_DIR}/briefs/xsp-lane-a-paper-pnl-latest.json"
telemetry_brief_path="${XSP_KILLER_DIR}/briefs/xsp-lane-a-entry-telemetry-latest.json"

cleanup() {
  rm -f \
    "${timer_tmp}" \
    "${scoreboard_payload_tmp}" \
    "${scoreboard_meta_tmp}" \
    "${scoreboard_log_tmp}" \
    "${pytest_tmp}"
}
trap cleanup EXIT

systemctl list-timers --all --no-pager --plain > "${timer_tmp}" 2>&1 || true

scoreboard_status=0
"${PYTHON_BIN}" - "${scoreboard_payload_tmp}" "${scoreboard_meta_tmp}" "${paper_brief_path}" "${telemetry_brief_path}" <<'PY' > "${scoreboard_log_tmp}" 2>&1 || scoreboard_status=$?
import json
import sys
from pathlib import Path

from xsp_killer.health_soak import scoreboard_report_metrics
from xsp_killer.lane_a_variants import build_scoreboard


def _read_json(path: Path):
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    return json.loads(raw)


out = build_scoreboard()
payload = json.loads(out.read_text(encoding="utf-8"))
summary = scoreboard_report_metrics(
    payload,
    paper_brief=_read_json(Path(sys.argv[3])),
    telemetry_brief=_read_json(Path(sys.argv[4])),
)

Path(sys.argv[1]).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
Path(sys.argv[2]).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(out)
PY

pytest_status=0
if [ "${quick}" -eq 1 ]; then
  printf 'skipped (--quick)\n' > "${pytest_tmp}"
else
  "${PYTHON_BIN}" -m pytest -q > "${pytest_tmp}" 2>&1 || pytest_status=$?
fi

report_status=0
"${PYTHON_BIN}" - \
  "${report_path}" \
  "${timer_tmp}" \
  "${scoreboard_payload_tmp}" \
  "${scoreboard_meta_tmp}" \
  "${scoreboard_log_tmp}" \
  "${scoreboard_status}" \
  "${pytest_tmp}" \
  "${pytest_status}" \
  "${quick}" \
  "${strict}" <<'PY' || report_status=$?
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

report_path = Path(sys.argv[1])
timer_output = Path(sys.argv[2]).read_text(encoding="utf-8")
scoreboard_payload_path = Path(sys.argv[3])
scoreboard_meta_path = Path(sys.argv[4])
scoreboard_log_path = Path(sys.argv[5])
scoreboard_status = int(sys.argv[6])
pytest_output = Path(sys.argv[7]).read_text(encoding="utf-8")
pytest_status = int(sys.argv[8])
quick = bool(int(sys.argv[9]))
strict = bool(int(sys.argv[10]))


def _read_json(path: Path):
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    return json.loads(raw)


def _excerpt(text: str, *, max_lines: int = 40) -> str:
    lines = text.strip().splitlines()
    if not lines:
        return "(no output)"
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(["..."] + lines[-max_lines:])


payload = _read_json(scoreboard_payload_path) if scoreboard_status == 0 else None
summary = _read_json(scoreboard_meta_path) if scoreboard_status == 0 else None
strict_anomalies = []
if isinstance(summary, dict):
    strict_anomalies.extend(summary.get("strict_anomalies") or [])
if scoreboard_status != 0:
    strict_anomalies.append("scoreboard_build_failed")
if not quick and pytest_status != 0:
    strict_anomalies.append("pytest_failed")

units = [
    "xsp-killer-lane-a-entry.timer",
    "xsp-killer-lane-a-monitor.timer",
    "xsp-killer-lane-a-intraday.timer",
    "xsp-killer-lane-b-monitor.timer",
]
timer_lines = timer_output.splitlines()
timer_status = {}
for unit in units:
    match = next((line.strip() for line in timer_lines if unit in line), None)
    timer_status[unit] = match or "not listed"

md: list[str] = []
md.append("# XSP Killer Health Soak Check")
md.append("")
md.append(f"- Generated at (UTC): {datetime.now(timezone.utc).isoformat()}")
md.append(f"- Quick mode: {'yes' if quick else 'no'}")
md.append(f"- Strict mode: {'yes' if strict else 'no'}")
md.append("")
md.append("## Summary")
if isinstance(summary, dict):
    md.append(f"- Scoreboard stale: `{summary['stale']}`")
    md.append(
        "- Baseline sessions evaluated: "
        f"`{summary['baseline_sessions_evaluated']}`"
    )
    md.append(
        "- Regime-gate comparison variant count: "
        f"`{summary['regime_gate_comparison_variant_count']}`"
    )
    md.append(
        f"- Vol shadow latest SPY RV: `{summary.get('vol_shadow_latest_spy_rv')}`"
    )
    md.append(
        f"- Vol shadow avg SPY RV: `{summary.get('vol_shadow_avg_spy_rv')}`"
    )
    axis = summary.get("regime_axis_summary") or {}
    md.append(
        f"- Regime axis counter divergence: `{axis.get('has_counter_divergence')}`"
    )
    promo = summary.get("promotion_proximity") or {}
    md.append(
        f"- Baseline sessions to promotion gate: `{promo.get('baseline_sessions_to_gate')}`"
    )
    md.append(
        f"- Baseline entered sessions to gate: `{promo.get('baseline_entered_sessions_to_gate')}`"
    )
    md.append(f"- Baseline near gate (≤2 left): `{promo.get('baseline_near_gate')}`")
    md.append(
        f"- Baseline near entered gate (≤2 left): `{promo.get('baseline_near_entered_gate')}`"
    )
    if summary.get("brief_consistency_anomalies"):
        md.append(
            "- Brief consistency anomalies: "
            f"`{', '.join(summary['brief_consistency_anomalies'])}`"
        )
    if promo.get("variants_near_promotion_gate"):
        md.append(
            "- Variants near promotion gate: "
            f"`{', '.join(promo['variants_near_promotion_gate'])}`"
        )
else:
    md.append("- Scoreboard summary: `unavailable`")
md.append(
    f"- Pytest smoke: `{'skipped (--quick)' if quick else ('passed' if pytest_status == 0 else 'failed')}`"
)
md.append("")
md.append("## Strict Anomalies")
if strict_anomalies:
    for anomaly in strict_anomalies:
        md.append(f"- `{anomaly}`")
else:
    md.append("- None")
md.append("")
md.append("## Systemd Timers")
md.append("- Missing timers are reported but are non-fatal.")
for unit in units:
    md.append(f"- `{unit}`: `{timer_status[unit]}`")
md.append("")
md.append("## Scoreboard Details")
if isinstance(summary, dict):
    md.append(f"- Updated at: `{summary['updated_at']}`")
    md.append(f"- Soak reset at: `{summary['soak_reset_at']}`")
    md.append(f"- Last entry eval at: `{summary['last_entry_eval_at']}`")
    md.append(
        "- Baseline zero sessions after 5+ days: "
        f"`{summary['baseline_zero_sessions_after_grace']}`"
    )
    md.append(
        "- Baseline zero entries after 5+ days: "
        f"`{summary.get('baseline_zero_entries_after_grace')}`"
    )
    md.append(
        f"- Baseline entered sessions: `{summary.get('baseline_entered_sessions')}`"
    )
    axis = summary.get("regime_axis_summary") or {}
    variants = axis.get("variants") or []
    if variants:
        md.append("")
        md.append("### Regime axis counters (v4 brief — not PnL)")
        for row in variants:
            vid = row.get("variant_id")
            counters = row.get("counters") or {}
            md.append(f"- `{vid}`:")
            md.append(
                f"  sessions={counters.get('sessions_evaluated')} "
                f"entered={counters.get('entered_sessions')} "
                f"regime_skips={counters.get('regime_gate_skip_sessions')} "
                f"bb_bounce={counters.get('bb_bounce_signal_sessions')} "
                f"bb_blocked={counters.get('bb_bounce_blocked_by_regime_sessions')} "
                f"vol_shadow_blocks={counters.get('vol_shadow_would_block_sessions')}"
            )
            diff = row.get("diff_vs_baseline")
            if diff:
                md.append(f"  diff_vs_baseline: `{json.dumps(diff)}`")
if isinstance(payload, dict) and isinstance(payload.get("baseline_prod"), dict):
    md.append(
        "- Baseline variant id: "
        f"`{payload['baseline_prod'].get('variant_id')}`"
    )
if scoreboard_status != 0:
    md.append(f"- Scoreboard rebuild failed with exit code `{scoreboard_status}`")
md.append("")
md.append("## Pytest Smoke")
md.append("```text")
md.append(_excerpt(pytest_output))
md.append("```")
md.append("")
if scoreboard_status != 0:
    md.append("## Scoreboard Rebuild Output")
    md.append("```text")
    md.append(_excerpt(scoreboard_log_path.read_text(encoding="utf-8")))
    md.append("```")
    md.append("")
md.append("## Raw Timers")
md.append("```text")
md.append(_excerpt(timer_output, max_lines=80))
md.append("```")
md.append("")

report_path.write_text("\n".join(md), encoding="utf-8")
PY

if [ "${report_status}" -ne 0 ] || [ ! -f "${report_path}" ]; then
  echo "Failed to write report: ${report_path}" >&2
  exit 1
fi

strict_anomaly_count=0
if [ "${scoreboard_status}" -eq 0 ]; then
  strict_anomaly_count="$("${PYTHON_BIN}" - "${scoreboard_meta_tmp}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(len(payload.get("strict_anomalies") or []))
PY
)"
fi

echo "Wrote ${report_path}"

if [ "${strict}" -eq 1 ]; then
  if [ "${scoreboard_status}" -ne 0 ]; then
    exit 1
  fi
  if [ "${strict_anomaly_count}" -gt 0 ]; then
    exit 1
  fi
  if [ "${quick}" -ne 1 ] && [ "${pytest_status}" -ne 0 ]; then
    exit 1
  fi
fi

exit 0
