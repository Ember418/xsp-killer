#!/usr/bin/env bash
# Leak-guard — append one-line audit entry after each commit.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG="$ROOT/logs/git-hook-audit.log"
mkdir -p "$(dirname "$LOG")"

SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

echo "$TS $SHA $BRANCH" >> "$LOG"
