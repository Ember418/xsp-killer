#!/usr/bin/env bash
# XSP Lane A paper entry — 15:45 / 15:50 / 15:55 ET (log only, no RH orders).
set -euo pipefail
XSP_KILLER_DIR="/opt/xsp-killer"
cd "${XSP_KILLER_DIR}"
export PYTHONPATH="${XSP_KILLER_DIR}"
exec /usr/bin/python3 "${CEMINI_DIR}/scripts/xsp_lane_a_entry.py" "$@"
