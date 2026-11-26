#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ "${1:-}" == "--delete" ]]; then
  find "$ROOT" -type f -name '*:Zone.Identifier' -print -delete
else
  echo "Preview only. Add --delete to remove:" 
  find "$ROOT" -type f -name '*:Zone.Identifier' -print
fi
