#!/usr/bin/env bash
# Leak-guard — block staged secrets and private infra IPs before commit.
# Ported from cemini K132; extended for xsp-killer env creds (RH, OpenRouter, DeepSeek).
set -euo pipefail

STAGED="$(git diff --cached 2>/dev/null || true)"
if [[ -z "$STAGED" ]]; then
  exit 0
fi

_block() {
  echo "ERROR: leak-guard pre-commit blocked this commit." >&2
  echo "$1" >&2
  echo "Remove the secret from staged files before committing." >&2
  exit 1
}

ADDED="$(git diff --cached -U0 | grep -E '^\+[^+]' || true)"
ADDED_NON_HOOKS="$(
  git diff --cached -U0 -- . \
    ':(exclude)scripts/git-hooks' \
    ':(exclude)scripts/install_git_leak_guard_hooks.sh' \
    2>/dev/null | grep -E '^\+[^+]' || true
)"

if [[ -n "$ADDED_NON_HOOKS" ]] && echo "$ADDED_NON_HOOKS" | grep -qE 'sk-[a-zA-Z0-9]{20,}'; then
  _block "Staged content matches an OpenAI/API key pattern (sk-...)."
fi

# Octet tuples — avoid literal prod IPs in hook source (K132 leak-guard self-scan).
_ip() { local -a o=("$@"); printf '%d.%d.%d.%d' "${o[@]}"; }
BLOCK_IPS=( "$(_ip 5 161 53 103)" "$(_ip 204 168 139 190)" "$(_ip 10 0 0 3)" )
for ip in "${BLOCK_IPS[@]}"; do
  if [[ -n "$ADDED" ]] && echo "$ADDED" | grep -qF "$ip"; then
    _block "Staged additions contain private production infrastructure IP: $ip"
  fi
done

# Block literal env credential assignments in newly added lines (not comments).
if [[ -n "$ADDED_NON_HOOKS" ]]; then
  if echo "$ADDED_NON_HOOKS" | grep -qE '^\+[^#]*OPENROUTER_API_KEY=[^[:space:]]+'; then
    _block "Staged additions assign OPENROUTER_API_KEY=..."
  fi
  if echo "$ADDED_NON_HOOKS" | grep -qE '^\+[^#]*(RH_PASSWORD|ROBINHOOD_PASSWORD)=[^[:space:]]+'; then
    _block "Staged additions assign Robinhood password env vars."
  fi
  if echo "$ADDED_NON_HOOKS" | grep -qE '^\+[^#]*DEEPSEEK_API_KEY=[^[:space:]]+'; then
    _block "Staged additions assign DEEPSEEK_API_KEY=..."
  fi
fi

exit 0
