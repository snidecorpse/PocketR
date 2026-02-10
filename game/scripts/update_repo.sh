#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${1:-}"
if [[ -z "$BASE_DIR" ]]; then
  echo "ERROR: missing repo base_dir argument" >&2
  exit 2
fi

cd "$BASE_DIR"

# Make sure we are in a git repo
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: $BASE_DIR is not a git repo" >&2
  exit 3
fi

echo "[Pocket-R] git pull..."
# --autostash helps if you have local edits
if git pull --rebase --autostash; then
  echo "[Pocket-R] update ok"
else
  echo "[Pocket-R] git pull failed" >&2
  exit 4
fi

sync
