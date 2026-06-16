#!/usr/bin/env bash
set -euo pipefail
XSP_KILLER_DIR="/opt/xsp-killer"
cd "${XSP_KILLER_DIR}"
export PYTHONPATH="${XSP_KILLER_DIR}"
exec /usr/bin/python3 "${XSP_KILLER_DIR}/scripts/lane_a_monitor.py" "$@"
