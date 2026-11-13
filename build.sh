#!/bin/bash
# build.sh -- prepare the build context and build the image.
#
#   ./build.sh [TAG]      # prepare-repos + docker build (tag: mimir)
#   ./build.sh -n [TAG]   # reuse the existing context
#
# JOBS (default: all cores), LINK_JOBS (default 2), MIMIR_BUILD_JOBS (default 8).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

TAG="mimir"
SKIP_PREPARE=0
if [[ "${1:-}" == "-n" ]]; then
  SKIP_PREPARE=1
  shift
fi
[[ -n "${1:-}" ]] && TAG="$1"

[[ "$SKIP_PREPARE" == 0 ]] && ./prepare-repos.sh

docker build \
  --build-arg JOBS="${JOBS:-}" \
  --build-arg LINK_JOBS="${LINK_JOBS:-2}" \
  --build-arg MIMIR_BUILD_JOBS="${MIMIR_BUILD_JOBS:-8}" \
  -t "$TAG" .
echo "==> image ready: $TAG"
