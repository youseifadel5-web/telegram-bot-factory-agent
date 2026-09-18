#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
PID_FILE="$ROOT/data/bot.pid"
mkdir -p "$ROOT/data" "$ROOT/logs"

is_ours() {
  local pid="$1"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  local cmd
  cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  [[ "$cmd" == *"$ROOT"*"boot.py"* || "$cmd" == *"$ROOT"*"main.py"* ]]
}

stop_old_bot() {
  local old_pid=""
  if [[ -f "$PID_FILE" ]]; then
    old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if is_ours "$old_pid"; then
      echo "Stopping previous bot process: $old_pid"
      kill -TERM "$old_pid" 2>/dev/null || true
      for _ in {1..10}; do
        is_ours "$old_pid" || break
        sleep 1
      done
      if is_ours "$old_pid"; then
        kill -KILL "$old_pid" 2>/dev/null || true
      fi
    fi
    rm -f "$PID_FILE"
  fi

  # Remove only processes whose command line points into this checkout.
  # Never use a broad pkill such as `pkill ffmpeg` on shared hosts.
  while read -r pid; do
    [[ -n "$pid" ]] || continue
    [[ "$pid" == "$$" ]] && continue
    kill -TERM "$pid" 2>/dev/null || true
  done < <(pgrep -f "$ROOT/(boot|main)\.py" || true)

  while read -r pid; do
    [[ -n "$pid" ]] || continue
    [[ "$pid" == "$$" ]] && continue
    kill -TERM "$pid" 2>/dev/null || true
  done < <(pgrep -f "$ROOT/bin/ffmpeg" || true)
}

stop_old_bot
printf '%s\n' "$$" > "$PID_FILE"

cleanup() {
  rm -f "$PID_FILE"
}
child_pid=""
stop_child() {
  if [[ -n "$child_pid" ]] && kill -0 "$child_pid" 2>/dev/null; then
    kill -TERM "$child_pid" 2>/dev/null || true
    wait "$child_pid" 2>/dev/null || true
  fi
  exit 143
}
trap stop_child INT TERM
trap cleanup EXIT

python3 boot.py &
child_pid="$!"
wait "$child_pid"
