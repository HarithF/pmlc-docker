#!/bin/bash
# import.sh -- load an image written by save.sh (tag: mimir) back into docker.
#
#   ./import.sh [FILE]          default: mimir.tar.gz next to this script
set -euo pipefail

FILE="${1:-$(dirname "${BASH_SOURCE[0]}")/mimir.tar.gz}"
[[ -f "$FILE" ]] || { echo "import.sh: $FILE not found" >&2; exit 1; }

# docker load reads gzip-compressed archives directly.
docker load -i "$FILE"
