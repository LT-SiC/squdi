#!/usr/bin/env bash
# Start the LOCAL-ONLY Studio server detached from the invoking WSL terminal.
# Does not register scheduled tasks or install an antivirus exception.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${HOME}/.local/state/sic-studio"
mkdir -p "$LOG_DIR"
health() { python3 - <<'PYHEALTH' >/dev/null 2>&1
import json, urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=1) as r:
        data=json.load(r)
    if data.get('ok') is True: raise SystemExit(0)
except Exception: pass
raise SystemExit(1)
PYHEALTH
}
if health; then
  # Do not silently reuse an outdated Studio server still listening on the port.
  remote_version="$(python3 - <<'PYVERSION'
import json, urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=2) as r:
        print(json.load(r).get('version','unknown'))
except Exception: print('unknown')
PYVERSION
)"
  local_version="$(cat "$ROOT/VERSION")"
  if [[ "$remote_version" != "$local_version" ]]; then
    printf 'Port 8765 is already serving Studio v%s (project is v%s). Stop the older server first.\n' "$remote_version" "$local_version" >&2
    exit 1
  fi
  printf 'Studio server already available (v%s).\n' "$local_version"
  exit 0
fi
cd "$ROOT"
nohup python3 server.py >>"$LOG_DIR/server.log" 2>&1 </dev/null &
for i in 1 2 3 4 5 6 7 8 9 10; do
  if health; then printf 'Studio server ready: http://127.0.0.1:8765\n'; exit 0; fi
  sleep .25
done
printf 'Studio did not start; see %s\n' "$LOG_DIR/server.log" >&2
exit 1
