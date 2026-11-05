#!/usr/bin/env bash
# Makes a fresh worktree runnable: links the gitignored env files and corpus data from
# the main checkout, then installs web and API dependencies.
# Usage: run from anywhere inside the worktree. --datapipeline also builds that venv.
set -euo pipefail

wt=$(git rev-parse --show-toplevel)
main=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
if [ "$wt" = "$main" ]; then
  echo "This is the main checkout; run it inside a worktree." >&2; exit 1
fi

link() {  # link <path relative to the repo root>
  if [ -e "$main/$1" ] && [ ! -e "$wt/$1" ]; then
    mkdir -p "$(dirname "$wt/$1")"
    ln -s "$main/$1" "$wt/$1"
    echo "linked $1"
  fi
}
for f in apps/web/.env.local services/api/.env datapipeline/.env \
         datapipeline/sources datapipeline/releases/snapshots datapipeline/cache.db; do
  link "$f"
done

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

(cd "$wt/apps/web" && npm ci --no-audit --no-fund)
(cd "$wt/services/api" && python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]")
if [ "${1:-}" = "--datapipeline" ]; then
  (cd "$wt/datapipeline" && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt)
fi
echo "worktree ready: $wt"
