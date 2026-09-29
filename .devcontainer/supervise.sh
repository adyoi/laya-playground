#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

child=""
fails=0

stop() {
  if [ -n "$child" ]; then
    kill "$child" 2>/dev/null
  fi
  exit 0
}
trap stop TERM INT

while true; do
  .venv/bin/python app.py --host 0.0.0.0 --port 8000 --device cpu >> server.log 2>&1 &
  child=$!
  wait "$child"
  code=$?
  child=""

  if [ "$code" -eq 0 ]; then
    fails=0
    echo "--- server keluar bersih, restart dalam 5 detik ---" >> server.log
  else
    fails=$((fails + 1))
    echo "--- server keluar kode $code (percobaan gagal $fails/5) ---" >> server.log
    if [ "$fails" -ge 5 ]; then
      echo "--- 5 kali gagal berturut-turut, supervisor berhenti ---" >> server.log
      echo "--- cek supervisor.log dan server.log ---" >> server.log
      exit 1
    fi
  fi

  sleep 5
done
