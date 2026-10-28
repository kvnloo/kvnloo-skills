#!/usr/bin/env bash
# install-guard.sh: put the phone install/IME/settings guard next to each Python's stdlib as a
# sitecustomize hook, so that RAW uiautomator2 / adbutils scripts written by any agent are blocked
# from installs, uninstalls, IME changes, clipboard use and settings writes too.
#
# THIS SCRIPT CHANGES NOTHING UNLESS YOU PASS --apply. Plain `install-guard.sh` prints the plan.
#
# What it installs, per Python stdlib directory:
#   _phone_guard.py   a copy of phone/guard.py (stdlib only)
#   sitecustomize.py  scripts/sitecustomize_phone_guard.py (chains to any other sitecustomize)
# Interpreter start only registers an import hook. The patch is applied the moment a script imports
# adbutils or uiautomator2. Python processes that never import them are unaffected.
#
# BLAST RADIUS (read before applying): every Python process on this host that imports adbutils or
# uiautomator2 loses install/uninstall/IME/settings/clipboard on phones, including legitimate tools
# such as app test harnesses that install APKs. List such scripts in /etc/phone-guard.allow (one
# absolute script path per line, root-owned); they are then exempt. `python -c` and `python -m` are
# never exempt. The phone package's own guard (import phone) has no exemption at all.
#
# Usage:
#   install-guard.sh [--status] [--apply] [--uninstall] [--verify] [--sudo] [--force]
#                    [--python PATH]... [--target-dir DIR]...
#     --status       show the state of every target and exit
#     --apply        write the files (with --uninstall: remove them)
#     --uninstall    plan or perform removal; restores a backed-up foreign sitecustomize
#     --verify       after acting, run each target interpreter's guard self-test
#     --sudo         use sudo for targets the current user cannot write (for example /usr/lib)
#     --force        replace a foreign sitecustomize.py (kept as sitecustomize.py.phoneguard-orig)
#     --python PATH  also target the stdlib directory of this interpreter
#     --target-dir   target exactly these directories instead of discovering (used by tests)
#
# Auto-discovered targets: uv-managed Pythons (`uv python dir`), /usr/lib/python3.*,
# /usr/local/lib/python3.*.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_GUARD="$here/phone/guard.py"
SRC_SITE="$here/scripts/sitecustomize_phone_guard.py"
MARK="# phone-guard-sitecustomize"

APPLY=0; UNINSTALL=0; VERIFY=0; USE_SUDO=0; FORCE=0; STATUS_ONLY=0
declare -a TARGETS=() EXTRA_PY=() EXPLICIT=()

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --verify) VERIFY=1 ;;
    --sudo) USE_SUDO=1 ;;
    --force) FORCE=1 ;;
    --status) STATUS_ONLY=1 ;;
    --python) shift; EXTRA_PY+=("${1:?--python needs a path}") ;;
    --target-dir) shift; EXPLICIT+=("${1:?--target-dir needs a directory}") ;;
    -h|--help) awk 'NR>1 && /^#/{sub(/^# ?/,""); print; next} NR>1{exit}' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

[ -f "$SRC_GUARD" ] && [ -f "$SRC_SITE" ] || { echo "missing source files under $here" >&2; exit 1; }

add_target() {
  local d real
  d="$1"
  [ -f "$d/os.py" ] || return 0
  real="$(readlink -f "$d")"
  for t in "${TARGETS[@]:-}"; do [ "$t" = "$real" ] && return 0; done
  TARGETS+=("$real")
}

discover() {
  local uvdir d
  if [ "${#EXPLICIT[@]}" -gt 0 ]; then
    for d in "${EXPLICIT[@]}"; do mkdir -p "$d"; TARGETS+=("$(readlink -f "$d")"); done
    return
  fi
  if command -v uv >/dev/null 2>&1; then
    uvdir="$(uv python dir 2>/dev/null || true)"
  else
    uvdir="${XDG_DATA_HOME:-$HOME/.local/share}/uv/python"
  fi
  if [ -n "${uvdir:-}" ] && [ -d "$uvdir" ]; then
    for d in "$uvdir"/*/lib/python3.*; do [ -d "$d" ] && add_target "$d"; done
  fi
  for d in /usr/lib/python3.* /usr/local/lib/python3.*; do [ -d "$d" ] && add_target "$d"; done
  for py in "${EXTRA_PY[@]:-}"; do
    [ -n "$py" ] || continue
    d="$("$py" -c 'import sysconfig; print(sysconfig.get_paths()["stdlib"])')"
    add_target "$d"
  done
}

sha() { sha256sum "$1" | cut -d' ' -f1; }

state_of() {  # echo: absent | current | outdated | foreign
  local d="$1" site="$1/sitecustomize.py" g="$1/_phone_guard.py"
  if [ -f "$site" ] && ! head -1 "$site" | grep -qF "$MARK"; then echo foreign; return; fi
  if [ ! -f "$site" ] && [ ! -f "$g" ]; then echo absent; return; fi
  if [ -f "$site" ] && [ -f "$g" ] && [ "$(sha "$g")" = "$(sha "$SRC_GUARD")" ] \
     && [ "$(sha "$site")" = "$(sha "$SRC_SITE")" ]; then echo current; return; fi
  echo outdated
}

as_owner() {  # as_owner DIR cmd...: run directly when writable, with sudo when allowed
  local d="$1"; shift
  if [ -w "$d" ]; then "$@"
  elif [ "$USE_SUDO" = 1 ]; then sudo "$@"
  else echo "  needs --sudo (not writable): $d" >&2; return 77
  fi
}

python_for() {  # python_for STDLIB_DIR -> interpreter path, if it can be inferred
  local d="$1" v
  v="$(basename "$d")"
  case "$d" in
    */lib/python3.*) [ -x "$d/../../bin/$v" ] && { readlink -f "$d/../../bin/$v"; return; } ;;
  esac
  [ -x "/usr/bin/$v" ] && echo "/usr/bin/$v"
}

act() {
  local d="$1" st
  st="$(state_of "$d")"
  if [ "$UNINSTALL" = 1 ]; then
    case "$st" in
      absent) echo "  nothing to remove"; return 0 ;;
      foreign) echo "  foreign sitecustomize, not ours: leaving it"; return 0 ;;
    esac
    if [ "$APPLY" = 0 ]; then echo "  would remove _phone_guard.py and sitecustomize.py"; return 0; fi
    as_owner "$d" rm -f "$d/_phone_guard.py" "$d/sitecustomize.py" \
      "$d/__pycache__/_phone_guard."*.pyc "$d/__pycache__/sitecustomize."*.pyc || return 1
    if [ -f "$d/sitecustomize.py.phoneguard-orig" ]; then
      as_owner "$d" mv "$d/sitecustomize.py.phoneguard-orig" "$d/sitecustomize.py"
      echo "  removed; restored the original sitecustomize.py"
    else
      echo "  removed"
    fi
    return 0
  fi
  case "$st" in
    current) echo "  already current"; return 0 ;;
    foreign)
      if [ "$FORCE" = 0 ]; then
        echo "  SKIP: a different sitecustomize.py exists (use --force to keep it as .phoneguard-orig and chain to it)"
        return 0
      fi ;;
  esac
  if [ "$APPLY" = 0 ]; then
    echo "  would install _phone_guard.py and sitecustomize.py ($st)"; return 0
  fi
  if [ "$st" = foreign ]; then
    as_owner "$d" cp -n "$d/sitecustomize.py" "$d/sitecustomize.py.phoneguard-orig" || return 1
  fi
  as_owner "$d" install -m 0644 "$SRC_GUARD" "$d/_phone_guard.py" || return 1
  as_owner "$d" install -m 0644 "$SRC_SITE" "$d/sitecustomize.py" || return 1
  echo "  installed"
}

verify() {
  local d="$1" py
  py="$(python_for "$d" || true)"
  if [ -z "$py" ]; then echo "  verify: no interpreter found for $d"; return 0; fi
  if "$py" -c 'import sys; assert hasattr(sys, "_phone_guard_state")' 2>/dev/null \
     && "$py" -m _phone_guard selftest >/dev/null 2>&1; then
    echo "  verify: guard active and self-test passes"
  else
    echo "  verify: FAILED for $py (guard not active or self-test failed)"; return 1
  fi
}

discover
[ "${#TARGETS[@]}" -gt 0 ] || { echo "no Python stdlib directories found"; exit 0; }
[ "$APPLY" = 1 ] || echo "DRY RUN (nothing is written; pass --apply to act)"
rc=0
for d in "${TARGETS[@]}"; do
  echo "$d [$(state_of "$d")]"
  [ "$STATUS_ONLY" = 1 ] && continue
  act "$d" || rc=1
  if [ "$VERIFY" = 1 ] && [ "$APPLY" = 1 ] && [ "$UNINSTALL" = 0 ]; then verify "$d" || rc=1; fi
done
exit "$rc"
