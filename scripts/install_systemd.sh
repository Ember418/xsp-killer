#!/usr/bin/env bash
# Install XSP Killer systemd units to /etc/systemd/system/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="/etc/systemd/system"

for unit in "$ROOT/deploy/systemd/"*.service "$ROOT/deploy/systemd/"*.timer; do
  [ -f "$unit" ] || continue
  name="$(basename "$unit")"
  sed "s|/opt/xsp-killer|${ROOT}|g" "$unit" > "/tmp/${name}"
  sudo cp "/tmp/${name}" "${DEST}/${name}"
  echo "installed ${name}"
done

sudo systemctl daemon-reload
echo "Run: sudo systemctl enable --now xsp-killer-lane-a-intraday.timer"
