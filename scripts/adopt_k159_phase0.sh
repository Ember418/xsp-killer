#!/usr/bin/env bash
# K159 Phase-0 adoption — Fable Advisor orchestration spike (log-only, NO-GO default).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_JSON="$ROOT/briefs/k159-ops-phase0-adopt-latest.json"
cd "$ROOT"

TEST_STATUS="FAIL"
VERDICT="PARTIAL"

echo "== K159 Phase-0: pytest Fable Advisor orchestration spike =="
if python3 -m pytest "$ROOT/tests/test_k159_fable_advisor_spike.py" -q --tb=short; then
  TEST_STATUS="PASS"
  VERDICT="SHIPPED"
fi

python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path

payload = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "brief": "xsp-2026-07-11_k159-fable-advisor-orchestration-steal",
    "phase": "P0",
    "verdict": "$VERDICT",
    "test_status": "$TEST_STATUS",
    "tests": ["tests/test_k159_fable_advisor_spike.py"],
    "files": [
        "briefs/xsp-2026-07-11_k159-fable-advisor-orchestration-steal.md",
        "config/k159_fable_advisor_spike.yaml",
        "xsp_killer/fable_advisor_spike.py",
        "xsp_killer/macro_weather_notes.py",
        "tests/test_k159_fable_advisor_spike.py",
        "scripts/adopt_k159_phase0.sh",
    ],
    "env_opt_in": "XSP_K159_FABLE_ADVISOR",
    "grok_lane_env": "XSP_K159_GROK_LANE",
    "default_verdict": "NO_GO",
    "gate_impact": "LOG_ONLY_NO_REGIME_GATE_CHANGE",
}
Path("$OUT_JSON").write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
print("Wrote", "$OUT_JSON")
PY

echo "K159 Phase-0 complete ($VERDICT)."
