#!/usr/bin/env bash
# K161 Phase-0 adoption — CEV aspiration operator notes (log-only; no solver).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_JSON="$ROOT/briefs/k161-xsp-ops-phase0-adopt-latest.json"
cd "$ROOT"

TEST_STATUS="FAIL"
VERDICT="PARTIAL"

echo "== K161 Phase-0: pytest macro weather operator notes (K155 + K158 + K161/K162) =="
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
    "brief": "xsp-2026-07-13_k161-cev-resistance-support-aspiration-steal",
    "extends": "xsp-2026-07-10_k155-operator-steals",
    "phase": "P0",
    "verdict": "$VERDICT",
    "test_status": "$TEST_STATUS",
    "tests": ["tests/test_k155_macro_weather_notes.py"],
    "files": [
        "briefs/xsp-2026-07-13_k161-cev-resistance-support-aspiration-steal.md",
        "config/k155_operator_notes.yaml",
        "xsp_killer/macro_weather_notes.py",
        "tests/test_k155_macro_weather_notes.py",
        "scripts/adopt_k161_xsp_ops_phase0.sh",
    ],
    "steals": [
        "xsp-2026-07-13_k161-cev-resistance-support-aspiration-steal",
    ],
    "k161_fields": [
        "cev_aspiration.regime_tag_required",
        "cev_aspiration.band_thinking_on_positive_drift",
        "cev_aspiration.elasticity_widen_bands_when_vol_sensitive",
        "cev_aspiration.no_integral_solver",
    ],
    "gate_impact": "LOG_ONLY_NO_REGIME_GATE_CHANGE",
    "solver_impact": "NO_INTEGRAL_SOLVER",
}
Path("$OUT_JSON").write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
print("Wrote", "$OUT_JSON")
PY

echo "K161 Phase-0 complete ($VERDICT)."
