#!/usr/bin/env bash
# XSP Lane A Phase 0 — morning exit monitor (alerts only).
# Schedule: 09:35 / 09:45 / 10:00 / 10:30 America/New_York (systemd timer).
set -euo pipefail
XSP_KILLER_DIR="/opt/xsp-killer"
cd "${XSP_KILLER_DIR}"
export PYTHONPATH="${XSP_KILLER_DIR}"
# Loads RH creds from .env via python dotenv in monitor path / EnvironmentFile on systemd.
exec /usr/bin/python3 "${CEMINI_DIR}/scripts/xsp_lane_a_monitor.py" "$@"
