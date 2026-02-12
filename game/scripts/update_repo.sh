#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${1:-${POCKETR_REPO:-}}"
if [[ -z "$REPO_DIR" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  for CAND in "/root/PocketR" "/root/pocketr" "$(cd "$SCRIPT_DIR/../.." && pwd)"; do
    if [[ -d "$CAND" ]]; then
      REPO_DIR="$CAND"
      break
    fi
  done
fi

if [[ -z "$REPO_DIR" ]]; then
  echo "ERROR: missing repo_dir and no default repo found" >&2
  exit 2
fi

# Normalize path if possible
if REPO_DIR_REAL=$(cd "$REPO_DIR" 2>/dev/null && pwd); then
  REPO_DIR="$REPO_DIR_REAL"
fi

# If it's not a git repo, walk up a few levels (helps if you pass a subfolder)
CUR="$REPO_DIR"
for _ in 1 2 3 4 5 6; do
  if git -C "$CUR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    REPO_DIR="$CUR"
    break
  fi
  PARENT="$(dirname "$CUR")"
  if [[ "$PARENT" == "$CUR" ]]; then
    break
  fi
  CUR="$PARENT"
done

if ! git -C "$REPO_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: $REPO_DIR is not a git repo" >&2
  echo "Hint: install Pocket-R by cloning the repo, not by copying a zip." >&2
  exit 3
fi

# If running under sudo/root on a recent git, you may need safe.directory
git config --global --add safe.directory "$REPO_DIR" >/dev/null 2>&1 || true

echo "[Pocket-R] repo: $REPO_DIR"
BRANCH="$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
PRE_SHA="$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || true)"
echo "POCKETR_META_BRANCH=${BRANCH:-unknown}"
echo "POCKETR_META_PRE_SHA=${PRE_SHA:-unknown}"

echo "[Pocket-R] git pull..."
git -C "$REPO_DIR" pull --rebase --autostash

POST_SHA="$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || true)"
echo "POCKETR_META_POST_SHA=${POST_SHA:-unknown}"
echo "[Pocket-R] update ok"
sync
