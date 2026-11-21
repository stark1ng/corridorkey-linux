#!/bin/bash
# CorridorKey 2.0 Linux: демон + окно приложения
cd "$(dirname "$0")"
mkdir -p logs

if ! curl -sf http://127.0.0.1:8129/health >/dev/null 2>&1; then
  .venv/bin/python daemon.py >> logs/daemon.log 2>&1 &
  echo $! > logs/daemon.pid
  for _ in $(seq 1 40); do
    curl -sf http://127.0.0.1:8129/health >/dev/null 2>&1 && break
    sleep 0.25
  done
fi

exec .venv/bin/python app.py "$@"
