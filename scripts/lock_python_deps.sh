#!/usr/bin/env bash
# Regenerates or checks the Python lock files.
#
# Inputs (edit these):  services/api/pyproject.toml, datapipeline/requirements.txt
# Outputs (generated):  services/api/requirements.lock      production image (Dockerfile)
#                       services/api/requirements-dev.lock  CI and local tests (adds [dev])
#                       datapipeline/requirements.lock      CI and local venvs
#
# The locks are universal (Linux, macOS, Python 3.11 and up) and carry hashes, so
# `pip install --require-hashes -r <lock>` installs exactly what CI tested. uv keeps
# every existing pin when it recompiles, so rerunning after an input edit changes only
# what the edit needs. To move pins forward on purpose, pass --upgrade (all) or
# --upgrade-package NAME.
#
#   scripts/lock_python_deps.sh [api|datapipeline|all] [--upgrade | --upgrade-package NAME]
#   scripts/lock_python_deps.sh --check [api|datapipeline|all]   # CI: fail if a lock is stale
#
# Needs uv (`pip install uv`).
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
check=false
if [ "${1:-}" = "--check" ]; then check=true; shift; fi
target="${1:-all}"
[ $# -gt 0 ] && shift
extra=("$@")

compile() {  # <dir> <input> <output> [uv args...]
  local dir="$1" input="$2" output="$3"; shift 3
  (cd "$root/$dir" && uv pip compile "$input" --universal --python-version 3.11 \
    --generate-hashes --quiet -o "$output" "$@" "${extra[@]}")
}

files=()
case "$target" in
  api|all)
    compile services/api pyproject.toml requirements.lock
    compile services/api pyproject.toml requirements-dev.lock --extra dev -c requirements.lock
    files+=(services/api/requirements.lock services/api/requirements-dev.lock) ;;&
  datapipeline|all)
    compile datapipeline requirements.txt requirements.lock
    files+=(datapipeline/requirements.lock) ;;
  api) ;;
  *) echo "unknown target: $target (api, datapipeline or all)" >&2; exit 2 ;;
esac

if $check && ! git -C "$root" diff --quiet -- "${files[@]}"; then
  git -C "$root" --no-pager diff --stat -- "${files[@]}"
  echo "A lock file is out of date with its input. Run scripts/lock_python_deps.sh" \
       "$target and commit the result." >&2
  exit 1
fi
