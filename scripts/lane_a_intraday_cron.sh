#!/usr/bin/env bash
# Lane A intraday scan (every 15m RTH):
#  1) base intraday BB-bounce cycle (paper log only)
#  2) dip-swing variants: intraday dip-bounce entries + hold/TP exit checks
#     (only intraday-enabled variants run here; close-window variants are
#      handled by the 15:45 entry cron and the morning monitor cron).
set -uo pipefail
XSP_KILLER_DIR="/opt/xsp-killer"
cd "${XSP_KILLER_DIR}"
export PYTHONPATH="${XSP_KILLER_DIR}"

/usr/bin/python3 "${XSP_KILLER_DIR}/scripts/lane_a_intraday.py" "$@" || true
/usr/bin/python3 "${XSP_KILLER_DIR}/scripts/lane_a_variants.py" entry --intraday || true
/usr/bin/python3 "${XSP_KILLER_DIR}/scripts/lane_a_variants.py" monitor --intraday || true
