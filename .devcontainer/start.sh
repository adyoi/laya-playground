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
  kill -TERM -"$(cat server.pid)" 2>/dev/null || kill "$(cat server.pid)" 2>/dev/null || true
  rm -f server.pid
  sleep 2
fi

ROOT="$PWD"
RUN="setsid"
command -v setsid >/dev/null 2>&1 || RUN=""

nohup $RUN bash -c '
  cd "'"$ROOT"'"
  APP="app.py"
  BIND="--host 0.0.0.0"
  P="--port 8000"
  DEV="--device cpu"
  child=""
  stop() {
    [ -n "$child" ] && kill "$child" 2>/dev/null
    exit 0
  }
  trap stop TERM INT
  while true; do
    .venv/bin/python "$APP" "$BIND" "$P" "$DEV" >> server.log 2>&1 &
    child=$!
    wait "$child"
    echo "--- server keluar, restart dalam 5 detik ---" >> server.log
    sleep 5
  done
' >> supervisor.log 2>&1 &

echo $! > server.pid
sleep 3

if ! kill -0 "$(cat server.pid)" 2>/dev/null; then
  echo "supervisor langsung mati, lihat supervisor.log" >&2
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
