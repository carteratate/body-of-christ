#!/usr/bin/env bash
# Which CI jobs a pull request needs, from the paths it changes (one per line on stdin).
# Prints `web=`, `tests=` and `image=` (each true or false) for $GITHUB_OUTPUT.
#
#   web    the web job: apps/web/, plus the two files outside it that web tests read
#          (src/lib/collection-scopes.test.ts reads datapipeline/registry/works.json;
#          src/lib/collections.test.ts reads services/api/app/rag/constants.py)
#   tests  the api and datapipeline jobs: anything that is not documentation
#   image  the api-image job, which builds services/api/Dockerfile: services/api/
#
# Documentation is docs/ and any *.md, except docs/adr/, which datapipeline tests read
# (tests/test_papal_held.py checks ADR 0001's table). The workflow file counts for both.
# When a test starts reading a file outside these rules, add it here.
#
#   git diff --name-only HEAD^1 HEAD | scripts/ci_changes.sh
set -euo pipefail

web=false
tests=false
image=false
while IFS= read -r path; do
  [ -z "$path" ] && continue
  case "$path" in
    apps/web/*|datapipeline/registry/works.json|services/api/app/rag/constants.py|.github/*|scripts/ci_changes.sh)
      web=true ;;
  esac
  case "$path" in
    docs/adr/*) tests=true ;;
    docs/*|*.md) ;;
    *) tests=true ;;
  esac
  case "$path" in
    services/api/*|.github/*|scripts/ci_changes.sh) image=true ;;
  esac
done
echo "web=$web"
echo "tests=$tests"
echo "image=$image"
