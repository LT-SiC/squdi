#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/sic-studio" <<EOF
#!/usr/bin/env bash
exec bash "$ROOT/scripts/run_studio.sh" "\$@"
EOF
cat > "$HOME/.local/bin/sic-studio-update" <<EOF
#!/usr/bin/env bash
cd "$ROOT"
exec python3 "$ROOT/scripts/apply_update.py" "\$@"
EOF
chmod +x "$HOME/.local/bin/sic-studio" "$HOME/.local/bin/sic-studio-update" "$ROOT/scripts/run_studio.sh"
echo "Installed: $HOME/.local/bin/sic-studio"
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
 echo 'Add ~/.local/bin to PATH, for example: echo '\''export PATH="$HOME/.local/bin:$PATH"'\'' >> ~/.bashrc && source ~/.bashrc'
fi
