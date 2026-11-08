#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -x .venv/bin/uvicorn ]]; then
  echo 'Create .venv and install requirements.txt first. See README.md.' >&2
  exit 1
fi
if [[ $# -gt 0 ]]; then
  case "$1" in
    start|stop|status) exec .venv/bin/python scripts/dev_server.py "$1" ;;
    *) echo 'Usage: ./run.sh [start|stop|status]' >&2; exit 1 ;;
  esac
fi
if [[ -f .env ]]; then
  exec .venv/bin/uvicorn backend.main:app --env-file .env --host 127.0.0.1 --port 8000
fi
exec .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
