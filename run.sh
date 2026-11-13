#!/bin/bash
# run.sh -- start the container "mimir-run".
#
#   ./run.sh                    interactive shell
#   ./run.sh ./run.sh build     run a command in ~/benchmark and exit
#
# Resume it with: docker start -ai mimir-run
set -euo pipefail

TAG="${TAG:-mimir}"
if [[ $# -eq 0 ]]; then
  exec docker run -it --name mimir-run "$TAG"
fi
exec docker run -it --name mimir-run "$TAG" "$@"
