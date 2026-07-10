#!/usr/bin/env bash
# K155 Phase-0 adoption — macro weather operator steals (log-only).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_JSON="$ROOT/briefs/k155-ops-phase0-adopt-latest.json"
cd "$ROOT"

TEST_STATUS="FAIL"
VERDICT="PARTIAL"

echo "== K155 Phase-0: pytest macro weather operator notes =="
if python3 -m pytest "$ROOT/tests/test_k155_macro_weather_notes.py" -q --tb=short; then
  TEST_STATUS="PASS"
  VERDICT="SHIPPED"
fi

python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path

payload = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "brief": "xsp-2026-07-10_k155-operator-steals",
    "split_briefs": [
        "2026-07-10_xsp-sofr-conviction-pre-lane-a-checklist",
        "2026-07-10_xsp-macro-weather-usdjpy-cpi-operator",
    ],
    "phase": "P0",
    "verdict": "$VERDICT",
    "test_status": "$TEST_STATUS",
    "tests": ["tests/test_k155_macro_weather_notes.py"],
    "files": [
        "briefs/xsp-2026-07-10_k155-operator-steals.md",
        "config/k155_operator_notes.yaml",
        "xsp_killer/macro_weather_notes.py",
        "tests/test_k155_macro_weather_notes.py",
        "scripts/adopt_k155_ops_phase0.sh",
    ],
    "steals": [
        "xsp-2026-07-10_capital-flows-sofr-conviction-framework-steal",
        "xsp-2026-07-10_macro-charts-jpy-gold-cpi-steal",
        "2026-07-10_xsp-sofr-conviction-pre-lane-a-checklist",
        "2026-07-10_xsp-macro-weather-usdjpy-cpi-operator",
    ],
    "gate_impact": "LOG_ONLY_NO_REGIME_GATE_CHANGE",
}
Path("$OUT_JSON").write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
print("Wrote", "$OUT_JSON")
PY

echo "K155 Phase-0 complete ($VERDICT)."
