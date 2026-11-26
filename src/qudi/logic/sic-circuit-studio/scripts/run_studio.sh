#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${SIC_STUDIO_PORT:-8765}"
cd "$ROOT"
python3 server.py --port "$PORT" &
SERVER_PID=$!
cleanup(){ kill "$SERVER_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if python3 - "$PORT" <<'PY' 2>/dev/null
import sys, urllib.request
urllib.request.urlopen('http://127.0.0.1:'+sys.argv[1]+'/api/health',timeout=.3)
PY
  then break; fi
  sleep .2
done
URL="http://127.0.0.1:${PORT}/"
if command -v powershell.exe >/dev/null 2>&1; then
  powershell.exe -NoProfile -Command "Start-Process '$URL'" >/dev/null 2>&1 || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" >/dev/null 2>&1 || true
fi
printf 'SiC Circuit Studio: %s\nPress Ctrl+C to stop.\n' "$URL"
wait "$SERVER_PID"
