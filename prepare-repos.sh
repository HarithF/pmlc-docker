#!/bin/bash
# prepare-repos.sh -- copy ../mimir-frontend and ../benchmark into the build
# context: sources and git metadata (bootstrap needs it), no build trees,
# venvs or outputs. Local uncommitted changes are included.
#
#   MIMIR_SRC=/path/to/mimir-frontend BENCH_SRC=/path/to/benchmark ./prepare-repos.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

MIMIR_SRC="${MIMIR_SRC:-../mimir-frontend}"
BENCH_SRC="${BENCH_SRC:-../benchmark}"

for src in "$MIMIR_SRC" "$BENCH_SRC"; do
  [[ -d "$src" ]] || { echo "error: source not found: $src (see MIMIR_SRC / BENCH_SRC)" >&2; exit 1; }
done

copy() {  # copy <src> <dst> <exclude>...
  local src="$1" dst="$2"; shift 2
  local args=(--archive --delete --exclude=__pycache__ --exclude='*.pyc' --exclude=.pytest_cache)
  for e in "$@"; do args+=("--exclude=$e"); done
  mkdir -p "$dst"
  rsync "${args[@]}" "$src"/ "$dst"/
}

echo "==> mimir-frontend <- $MIMIR_SRC"
copy "$MIMIR_SRC" mimir-frontend \
  /.venv /MimIR/build /mim_debug /.cache '*.egg-info'

echo "==> benchmark <- $BENCH_SRC"
copy "$BENCH_SRC" benchmark /work

echo
echo "==> build context ready:"
echo "    mimir-frontend/  $(du -sh mimir-frontend | cut -f1)"
echo "    benchmark/       $(du -sh benchmark | cut -f1)"
echo "Next: ./build.sh -n   (or docker build -t mimir .)"
