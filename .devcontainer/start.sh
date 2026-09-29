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
  pid="$(cat server.pid)"
  kill -TERM -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  rm -f server.pid
  sleep 2
fi

RUN=""
command -v setsid >/dev/null 2>&1 && RUN="setsid"

nohup $RUN bash .devcontainer/supervise.sh >> supervisor.log 2>&1 &
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
