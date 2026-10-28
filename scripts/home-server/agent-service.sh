#!/usr/bin/env bash
# Runs one remote-control server and restarts it whenever it exits.
# Started inside its own tmux server by home-agent@<name>.service.
set -u
# systemd's user manager starts services with umask 0002 here, and Codex refuses a
# group-writable socket directory.
umask 022
name=${1:?usage: agent-service.sh claude-a|claude-b|codex}

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
export PATH="$HOME/.local/bin:$PATH"
# A key here would replace the subscription login.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN CLAUDE_CODE_OAUTH_TOKEN OPENAI_API_KEY

cd "$HOME/repos/body-of-christ" || exit 1

case "$name" in
  claude-a|claude-b)
    export CLAUDE_CONFIG_DIR="$HOME/.$name"
    cmd=(claude remote-control --spawn worktree) ;;
  codex)
    cmd=(codex remote-control --no-daemon) ;;
  *)
    echo "unknown service: $name" >&2; exit 2 ;;
esac

while true; do
  echo "$(date -Is) starting: ${cmd[*]}"
  "${cmd[@]}"
  rc=$?
  echo "$(date -Is) exited with status $rc; restarting in 15s"
  sleep 15
done
