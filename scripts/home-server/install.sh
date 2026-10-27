#!/usr/bin/env bash
# Installs the Lenovo home-server helpers for the current user. Safe to re-run; it
# overwrites the installed copies with the ones in this folder.
set -euo pipefail

src=$(cd "$(dirname "$0")" && pwd)
dest="$HOME/.local/share/home-server"
shared="$HOME/.claude-shared"

mkdir -p "$dest" "$HOME/.local/bin" "$HOME/.config/systemd/user" "$shared"
install -m 755 "$src/agent-service.sh" "$src/worktree-setup.sh" "$dest/"
install -m 644 "$src/shell.sh" "$dest/"
install -m 755 "$src/home-agents" "$HOME/.local/bin/home-agents"
install -m 644 "$src/home-agent@.service" "$HOME/.config/systemd/user/"

line='[ -f ~/.local/share/home-server/shell.sh ] && . ~/.local/share/home-server/shell.sh'
grep -qxF "$line" "$HOME/.bashrc" || echo "$line" >> "$HOME/.bashrc"

# One CLAUDE.md and settings.json for both accounts. Credentials stay per account.
cp "$src/machine-CLAUDE.md" "$shared/CLAUDE.md"
[ -e "$shared/settings.json" ] || echo '{}' > "$shared/settings.json"
for acct in claude-a claude-b; do
  dir="$HOME/.$acct"
  mkdir -p "$dir"
  for f in CLAUDE.md settings.json; do
    if [ -e "$dir/$f" ] && [ ! -L "$dir/$f" ]; then
      mv "$dir/$f" "$dir/$f.before-home-server"
      echo "kept the old $dir/$f as $f.before-home-server"
    fi
    ln -sfn "$shared/$f" "$dir/$f"
  done
done

systemctl --user daemon-reload
echo "Installed. Open a new terminal for claude-a / claude-b; enable services with: home-agents enable"
