#!/bin/bash
# run.sh -- start the container "mimir-run".
#
#   ./run.sh                    interactive shell
#   ./run.sh ./run.sh build     run a command in ~/benchmark and exit
#
# GPUs are passed through (--gpus all; needs the NVIDIA Container Toolkit) when
# nvidia-smi finds one on the host; otherwise the container runs CPU-only.
# GPUS='"device=0"' picks some, GPUS= (empty) none, either way skipping the check.
#
# Resume it with: docker start -ai mimir-run
set -euo pipefail

TAG="${TAG:-mimir}"
if [[ -z "${GPUS+set}" ]]; then
  if command -v nvidia-smi >/dev/null && nvidia-smi -L >/dev/null 2>&1; then
    GPUS=all
  else
    echo "run.sh: warning: no NVIDIA GPU found (nvidia-smi); running CPU-only" >&2
    GPUS=
  fi
fi
gpus=()
[[ -n "$GPUS" ]] && gpus=(--gpus "$GPUS")
exec docker run -it --name mimir-run "${gpus[@]}" "$TAG" "$@"
