#!/usr/bin/env bash
# XSP Lane A intraday — BB/VWAP scan every 15m during RTH (paper log only).
set -euo pipefail
XSP_KILLER_DIR="/opt/xsp-killer"
cd "${XSP_KILLER_DIR}"
export PYTHONPATH="${XSP_KILLER_DIR}"
exec /usr/bin/python3 "${CEMINI_DIR}/scripts/xsp_lane_a_intraday.py" "$@"
