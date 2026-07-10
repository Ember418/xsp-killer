#!/usr/bin/env bash
# K157 Phase-0 adoption — Muse Spark orchestration spike (log-only, NO-GO default).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_JSON="$ROOT/briefs/k157-ops-phase0-adopt-latest.json"
cd "$ROOT"

TEST_STATUS="FAIL"
VERDICT="PARTIAL"

echo "== K157 Phase-0: pytest Muse Spark orchestration spike =="
if python3 -m pytest "$ROOT/tests/test_k157_muse_spark_spike.py" -q --tb=short; then
  TEST_STATUS="PASS"
  VERDICT="SHIPPED"
fi

python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path

payload = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "brief": "xsp-2026-07-10_k157-muse-spark-orchestration-eval",
    "phase": "P0",
    "verdict": "$VERDICT",
    "test_status": "$TEST_STATUS",
    "tests": ["tests/test_k157_muse_spark_spike.py"],
    "files": [
        "briefs/xsp-2026-07-10_k157-muse-spark-orchestration-eval.md",
        "config/k157_muse_spark_spike.yaml",
        "xsp_killer/muse_spark_spike.py",
        "xsp_killer/macro_weather_notes.py",
        "tests/test_k157_muse_spark_spike.py",
        "scripts/adopt_k157_phase0.sh",
    ],
    "env_opt_in": "XSP_K157_MUSE_SPARK",
    "default_verdict": "NO_GO",
    "gate_impact": "LOG_ONLY_NO_REGIME_GATE_CHANGE",
}
Path("$OUT_JSON").write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
print("Wrote", "$OUT_JSON")
PY

echo "K157 Phase-0 complete ($VERDICT)."
