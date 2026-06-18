#!/usr/bin/env bash
set -euo pipefail
XSP_KILLER_DIR="/opt/xsp-killer"
cd "${XSP_KILLER_DIR}"
export PYTHONPATH="${XSP_KILLER_DIR}"
/usr/bin/python3 "${XSP_KILLER_DIR}/scripts/lane_a_entry.py" "$@"
/usr/bin/python3 "${XSP_KILLER_DIR}/scripts/lane_a_variants.py" entry || true
