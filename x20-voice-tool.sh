#!/usr/bin/env bash

is_sourced() {
  if [ -n "${ZSH_VERSION:-}" ]; then
    case ${ZSH_EVAL_CONTEXT:-} in
      *:file:* | *:file) return 0 ;;
    esac
  fi
  if [ -n "${BASH_VERSION:-}" ]; then
    [ "${BASH_SOURCE[0]:-}" != "${0:-}" ] && return 0
  fi
  return 1
}

if is_sourced; then
  echo "[ERROR] Do not source this script (do not use: . ./x20-voice-tool.sh)." >&2
  echo "Run it directly instead:" >&2
  echo "  ./x20-voice-tool.sh" >&2
  return 1 2>/dev/null || exit 1
fi

if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_PY="$ROOT_DIR/scripts/voice_tool_cli.py"
MENU_TUI_PY="$ROOT_DIR/scripts/voice_tool_app.py"
TERMINAL_RESTORE_PY="$ROOT_DIR/scripts/terminal_restore.py"

mkdir -p "$ROOT_DIR/config" "$ROOT_DIR/workspace" "$ROOT_DIR/output"

fail() { printf "[ERROR] %s\n" "$*" >&2; }

have() { command -v "$1" >/dev/null 2>&1; }

CLI_MODE=0
JSON_FLAG=()
NO_PAUSE=0

restore_terminal() {
  if [ "${CLI_MODE:-0}" -eq 1 ] || [ ! -t 1 ]; then
    return 0
  fi
  if [ -f "$TERMINAL_RESTORE_PY" ]; then
    python3 "$TERMINAL_RESTORE_PY" >/dev/null 2>&1 || true
  fi
  tput cnorm 2>/dev/null || true
  stty sane 2>/dev/null || true
}

pause_if_interactive() {
  local code="${1:-0}"
  if [ "${NO_PAUSE:-0}" -eq 1 ] || [ "$code" -eq 0 ] || [ "${CLI_MODE:-0}" -eq 1 ]; then
    return "$code"
  fi
  if [ -t 0 ] && [ -t 1 ]; then
    printf "\n[ERROR] Exited with code %s. Your shell is still active.\n" "$code" >&2
    printf "Press Enter to return to the shell..."
    IFS= read -r _ || true
    printf "\n"
  fi
  return "$code"
}

finish_tui() {
  local code="${1:-0}"
  restore_terminal
  pause_if_interactive "$code" || true
  exit "$code"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --cli)
      CLI_MODE=1
      shift
      ;;
    --json)
      JSON_FLAG=(--json)
      CLI_MODE=1
      shift
      ;;
    --no-pause)
      NO_PAUSE=1
      shift
      ;;
    -h|--help|help)
      python3 "$CLI_PY" --help
      exit 0
      ;;
    *)
      break
      ;;
  esac
done

if [ "${X20_VOICE_CLI:-}" = "1" ]; then
  CLI_MODE=1
fi

run_cli() {
  python3 "$CLI_PY" "${JSON_FLAG[@]}" "$@"
}

require_python() {
  if have python3; then
    return 0
  fi
  fail "python3 is required."
  return 1
}

run_tui() {
  require_python || return 1
  # Trap only affects this script process, not when sourced (sourcing is blocked above).
  trap 'restore_terminal' EXIT INT TERM HUP
  python3 "$MENU_TUI_PY"
  local code=$?
  restore_terminal
  trap - EXIT INT TERM HUP
  return "$code"
}

main_menu() {
  require_python || return 1
  if [ "$CLI_MODE" -eq 1 ]; then
    run_cli readiness
    return $?
  fi

  if ! python3 - <<'PY' >/dev/null 2>&1
import textual
PY
  then
    fail "Textual is not installed."
    printf "Install with: ./x20-voice-tool.sh --cli deps\n" >&2
    printf "Or use CLI mode: ./x20-voice-tool.sh --cli --help\n" >&2
    return 1
  fi

  run_tui
}

dispatch_cli() {
  case "$1" in
    deps) shift; run_cli deps "$@" ;;
    readiness|ready) shift; run_cli readiness "$@" ;;
    configure) shift; run_cli configure "$@" ;;
    devices) shift; run_cli devices "$@" ;;
    download) shift; run_cli download "$@" ;;
    languages) shift; run_cli languages "$@" ;;
    status) shift; run_cli status "$@" ;;
    build) shift; run_cli build "$@" ;;
    install) shift; run_cli install "$@" ;;
    official) shift; run_cli official "$@" ;;
    studio) shift; run_cli studio "$@" ;;
    pack) shift; run_cli pack "$@" ;;
    robot) shift; run_cli robot "$@" ;;
    virusscan) shift; run_cli virusscan "$@" ;;
    run) shift; run_cli run "$@" ;;
    menu) main_menu ;;
    *)
      fail "Unknown command: $1"
      printf "Run: ./x20-voice-tool.sh --help\n" >&2
      return 1
      ;;
  esac
}

if [ $# -eq 0 ]; then
  main_menu
  finish_tui $?
fi

if [ "$1" = "menu" ]; then
  shift
  main_menu
  finish_tui $?
fi

CLI_MODE=1
dispatch_cli "$@"
exit $?
