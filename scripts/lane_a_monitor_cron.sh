#!/usr/bin/env bash
# Lane A morning monitor + variant soak + scoreboard.
set -uo pipefail
XSP_KILLER_DIR="/opt/xsp-killer"
cd "${XSP_KILLER_DIR}"
export PYTHONPATH="${XSP_KILLER_DIR}"

/usr/bin/python3 "${XSP_KILLER_DIR}/scripts/lane_a_monitor.py" "$@" || true
/usr/bin/python3 "${XSP_KILLER_DIR}/scripts/lane_a_variants.py" monitor || true
/usr/bin/python3 "${XSP_KILLER_DIR}/scripts/lane_a_variants.py" scoreboard || true
