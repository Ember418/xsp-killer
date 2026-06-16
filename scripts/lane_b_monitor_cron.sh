#!/usr/bin/env bash
# XSP Lane B — daily LEAPS inventory + hedge-gap monitor (08:00 ET).
set -euo pipefail
XSP_KILLER_DIR="/opt/xsp-killer"
cd "${XSP_KILLER_DIR}"
export PYTHONPATH="${XSP_KILLER_DIR}"
exec /usr/bin/python3 "${CEMINI_DIR}/scripts/xsp_lane_b_monitor.py" "$@"
