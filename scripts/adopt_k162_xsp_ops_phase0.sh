#!/usr/bin/env bash
# K162 Phase-0 adoption — Macro Charts sentiment capitulation (log-only).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_JSON="$ROOT/briefs/k162-xsp-ops-phase0-adopt-latest.json"
cd "$ROOT"

TEST_STATUS="FAIL"
VERDICT="PARTIAL"

echo "== K162 Phase-0: pytest macro weather operator notes (K155 + K158 + K161/K162) =="
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
    "brief": "xsp-2026-07-13_k162-macro-charts-sentiment-capitulation-steal",
    "extends": "xsp-2026-07-10_k155-operator-steals",
    "pairs_with": "xsp-2026-07-13_k161-cev-resistance-support-aspiration-steal",
    "phase": "P0",
    "verdict": "$VERDICT",
    "test_status": "$TEST_STATUS",
    "tests": ["tests/test_k155_macro_weather_notes.py"],
    "files": [
        "briefs/xsp-2026-07-13_k162-macro-charts-sentiment-capitulation-steal.md",
        "config/k155_operator_notes.yaml",
        "xsp_killer/macro_weather_notes.py",
        "tests/test_k155_macro_weather_notes.py",
        "scripts/adopt_k162_xsp_ops_phase0.sh",
    ],
    "steals": [
        "xsp-2026-07-13_k162-macro-charts-sentiment-capitulation-steal",
    ],
    "k162_fields": [
        "sentiment_capitulation.crowded_semis_risk",
        "sentiment_capitulation.sox_relative_weakness",
        "sentiment_capitulation.gold_models_turning_up",
        "sentiment_capitulation.yen_hedge_narrative_only",
        "sentiment_capitulation.no_chase_spmo_semis_into_lane_a_overnight",
    ],
    "gate_impact": "LOG_ONLY_NO_REGIME_GATE_CHANGE",
}
Path("$OUT_JSON").write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
print("Wrote", "$OUT_JSON")
PY

echo "K162 Phase-0 complete ($VERDICT)."
