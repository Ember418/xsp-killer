#!/usr/bin/env bash
# K158 Phase-0 adoption — SOFR front-end operator steals (log-only; extends K155).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_JSON="$ROOT/briefs/k158-xsp-ops-phase0-adopt-latest.json"
cd "$ROOT"

TEST_STATUS="FAIL"
VERDICT="PARTIAL"

echo "== K158 Phase-0: pytest macro weather operator notes (K155 + K158) =="
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
    "brief": "xsp-2026-07-11_k158-sofr-front-end-operator-steals",
    "extends": "xsp-2026-07-10_k155-operator-steals",
    "phase": "P0",
    "verdict": "$VERDICT",
    "test_status": "$TEST_STATUS",
    "tests": ["tests/test_k155_macro_weather_notes.py"],
    "files": [
        "briefs/xsp-2026-07-11_k158-sofr-front-end-operator-steals.md",
        "config/k155_operator_notes.yaml",
        "xsp_killer/macro_weather_notes.py",
        "tests/test_k155_macro_weather_notes.py",
        "scripts/adopt_k158_xsp_ops_phase0.sh",
    ],
    "steals": [
        "xsp-2026-07-11_capital-flows-sofr-front-end-operator-steal",
    ],
    "k158_fields": [
        "sofr_front_end",
        "fomc_jul29",
        "cpi_skew",
        "japan_yen",
        "cme_ssf.tickers",
    ],
    "gate_impact": "LOG_ONLY_NO_REGIME_GATE_CHANGE",
}
Path("$OUT_JSON").write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
print("Wrote", "$OUT_JSON")
PY

echo "K158 Phase-0 complete ($VERDICT)."
