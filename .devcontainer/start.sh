#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

PY=.venv/bin/python
if [ ! -x "$PY" ]; then
  echo "venv belum ada, jalankan: bash .devcontainer/setup.sh" >&2
  exit 1
fi

if curl -sf -m 5 http://127.0.0.1:8000/health >/dev/null 2>&1; then
  echo "server sudah hidup, tidak ada yang dilakukan"
  exit 0
fi

if [ -f server.pid ]; then
  kill "$(cat server.pid)" 2>/dev/null || true
  rm -f server.pid
fi
pkill -f "app[.]py --host 0.0.0.0" 2>/dev/null || true
sleep 1

nohup bash -c '
  cd "'"$PWD"'"
  trap "kill 0" TERM INT
  while true; do
    .venv/bin/python app.py --host 0.0.0.0 --port 8000 --device cpu >> server.log 2>&1
    echo "--- server keluar, restart dalam 5 detik ---" >> server.log
    sleep 5
  done
' >> supervisor.log 2>&1 &

echo $! > server.pid
sleep 2

if ! kill -0 "$(cat server.pid)" 2>/dev/null; then
  echo "supervisor langsung mati, lihat supervisor.log dan server.log" >&2
  exit 1
fi

echo "supervisor pid $(cat server.pid)"

for _ in $(seq 1 90); do
  if curl -sf -m 5 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "health ok di http://127.0.0.1:8000"
    exit 0
  fi
  sleep 2
done

echo "server tidak merespons dalam 180 detik, lihat supervisor.log" >&2
exit 1
