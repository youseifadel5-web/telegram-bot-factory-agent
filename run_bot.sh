#!/usr/bin/env bash
set -euo pipefail
export PYTHONUNBUFFERED=1
MODE="${PLATFORM_MODE:-legacy}"
case "$MODE" in
  legacy)
    exec python legacy_launcher.py
    ;;
  advanced|unified)
    exec python main.py
    ;;
  *)
    echo "PLATFORM_MODE must be legacy or advanced; got: $MODE" >&2
    exit 2
    ;;
esac
