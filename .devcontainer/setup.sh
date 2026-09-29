#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -r requirements.txt -r requirements-test.txt

nohup .venv/bin/python app.py --host 0.0.0.0 --port 8000 --device cpu \
  > server.log 2>&1 &
echo $! > server.pid
echo "server pid $(cat server.pid)"

for _ in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "health ok di http://127.0.0.1:8000"
    break
  fi
  sleep 2
done

nohup bash -c 'curl -sf -X POST http://127.0.0.1:8000/predict \
  -H "Content-Type: application/json" \
  -d "{\"preset\":\"triage\",\"state\":\"Saya mau refund pesanan saya\"}" \
  > warmup.json 2>&1' >/dev/null 2>&1 &
echo "warmup jalan di background, unduh checkpoint di ./warmup.json"
