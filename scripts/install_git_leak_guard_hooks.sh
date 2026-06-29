#!/usr/bin/env bash
# Install git leak-guard hooks for xsp-killer (public GitHub + prod .env on same host).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK_SRC="$ROOT/scripts/git-hooks"
HOOK_DST="$ROOT/.git/hooks"

install_git_leak_guard_hooks() {
  local root="${1:-$ROOT}"
  local src="$root/scripts/git-hooks"
  local dst="$root/.git/hooks"

  if [[ ! -d "$root/.git" ]]; then
    echo "FAIL: $root is not a git repository" >&2
    return 1
  fi

  for name in pre-commit post-commit; do
    local script="$src/${name}.sh"
    if [[ ! -f "$script" ]]; then
      echo "FAIL: missing canonical hook script $script" >&2
      return 1
    fi
    chmod +x "$script"
    ln -sf "$script" "$dst/$name"
    chmod +x "$dst/$name"
  done

  echo "OK: leak-guard hooks installed -> $dst/{pre-commit,post-commit}"
}

run_hook_verification_tests() {
  local test_root="${1:-/tmp/xsp-killer-hook-test}"
  local pre_commit="$ROOT/scripts/git-hooks/pre-commit.sh"
  _ip() { local -a o=("$@"); printf '%d.%d.%d.%d' "${o[@]}"; }

  rm -rf "$test_root"
  mkdir -p "$test_root"
  git -C "$test_root" init -q
  git -C "$test_root" config user.email "xsp-hook-test@local"
  git -C "$test_root" config user.name "XSP Hook Test"
  ln -sf "$pre_commit" "$test_root/.git/hooks/pre-commit"
  chmod +x "$test_root/.git/hooks/pre-commit" "$pre_commit"

  local result_a result_b result_c result_d

  fake_sk="sk-$(printf 'a%.0s' {1..25})"
  echo "OPENAI_KEY=${fake_sk}" > "$test_root/secret.txt"
  git -C "$test_root" add secret.txt
  if git -C "$test_root" commit -m "test A secret" >/dev/null 2>&1; then
    result_a=FAIL
  else
    result_a=PASS
  fi
  git -C "$test_root" rm --cached -f secret.txt 2>/dev/null || true
  rm -f "$test_root/secret.txt"

  test_ip="$(_ip 5 161 53 103)"
  echo "server host ${test_ip}" > "$test_root/infra.txt"
  git -C "$test_root" add infra.txt
  if git -C "$test_root" commit -m "test B ip" >/dev/null 2>&1; then
    result_b=FAIL
  else
    result_b=PASS
  fi
  git -C "$test_root" rm --cached -f infra.txt 2>/dev/null || true
  rm -f "$test_root/infra.txt"

  fake_or="sk-or-v1-$(printf 'b%.0s' {1..20})"
  or_key="OPENROUTER_API_KEY"
  echo "${or_key}=${fake_or}" > "$test_root/env.txt"
  git -C "$test_root" add env.txt
  if git -C "$test_root" commit -m "test C openrouter" >/dev/null 2>&1; then
    result_c=FAIL
  else
    result_c=PASS
  fi
  git -C "$test_root" rm --cached -f env.txt 2>/dev/null || true
  rm -f "$test_root/env.txt"

  echo 'routine brief update with no secrets' > "$test_root/clean.txt"
  git -C "$test_root" add clean.txt
  if git -C "$test_root" commit -m "test D clean" >/dev/null 2>&1; then
    result_d=PASS
  else
    result_d=FAIL
  fi

  echo "Hook verification ($test_root):"
  echo "  Test A (sk- key blocked):           $result_a"
  echo "  Test B (Hetzner IP blocked):        $result_b"
  echo "  Test C (OPENROUTER_API_KEY blocked): $result_c"
  echo "  Test D (clean commit allowed):       $result_d"

  if [[ "$result_a" != PASS || "$result_b" != PASS || "$result_c" != PASS || "$result_d" != PASS ]]; then
    return 1
  fi
}

RUN_TESTS=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --verify-hooks) RUN_TESTS=true; shift ;;
    -h|--help)
      echo "Usage: $0 [--verify-hooks]"
      echo "  Installs leak-guard git hooks under $HOOK_DST (symlinked from $HOOK_SRC)."
      exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

echo "== xsp-killer: install git leak-guard hooks =="
install_git_leak_guard_hooks "$ROOT"

if [[ "$RUN_TESTS" == "true" ]]; then
  echo "== xsp-killer: hook verification tests =="
  run_hook_verification_tests /tmp/xsp-killer-hook-test
fi

echo "xsp-killer leak-guard hooks installed."
