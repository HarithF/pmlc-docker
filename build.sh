#!/bin/bash
# build.sh -- build the image (tag: mimir). mimir-frontend and benchmark are
# cloned from GitHub at build time; a push to either re-clones it.
#
#   ./build.sh [TAG]
#   FRONTEND_REF=my-branch BENCH_REF=my-branch ./build.sh     # other branches
#   FRONTEND_REPO=me/mimir-frontend ./build.sh                # or a fork
#
# JOBS (default: all cores), LINK_JOBS (default 2), MIMIR_BUILD_JOBS (default 8).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

TAG="${1:-mimir}"
args=()
for v in FRONTEND_REPO FRONTEND_REF BENCH_REPO BENCH_REF; do
  [[ -n "${!v:-}" ]] && args+=(--build-arg "$v=${!v}")
done

docker build \
  --build-arg JOBS="${JOBS:-}" \
  --build-arg LINK_JOBS="${LINK_JOBS:-2}" \
  --build-arg MIMIR_BUILD_JOBS="${MIMIR_BUILD_JOBS:-8}" \
  "${args[@]}" \
  -t "$TAG" .
echo "==> image ready: $TAG"
