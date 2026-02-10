#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${1:-}"
if [[ -z "$REPO_DIR" ]]; then
  echo "ERROR: missing repo_dir argument" >&2
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
  # Try to find a git repo inside the given directory (bounded depth)
  if [[ -d "$REPO_DIR" ]]; then
    FOUND_GIT="$(find "$REPO_DIR" -maxdepth 3 -type d -name .git -print -quit 2>/dev/null || true)"
    if [[ -n "$FOUND_GIT" ]]; then
      REPO_DIR="$(dirname "$FOUND_GIT")"
    fi
  fi
fi

if ! git -C "$REPO_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: $REPO_DIR is not a git repo" >&2
  echo "Hint: install Pocket-R by cloning the repo, not by copying a zip." >&2
  exit 3
fi

TARGET_USER=""
if id -u pizero >/dev/null 2>&1; then
  TARGET_USER="pizero"
elif id -u pi >/dev/null 2>&1; then
  TARGET_USER="pi"
fi

run_git() {
  if [[ "$(id -u)" == "0" && -n "$TARGET_USER" ]]; then
    # runuser is preferred (no sudo password). fall back to sudo if available.
    if command -v runuser >/dev/null 2>&1; then
      runuser -u "$TARGET_USER" -- git "$@"
    else
      sudo -u "$TARGET_USER" git "$@"
    fi
  else
    git "$@"
  fi
}

# If running as root, recent git may need safe.directory
run_git config --global --add safe.directory "$REPO_DIR" >/dev/null 2>&1 || true

echo "[Pocket-R] repo: $REPO_DIR"
echo "[Pocket-R] git pull..."
run_git -C "$REPO_DIR" pull --rebase --autostash

echo "[Pocket-R] update ok"
sync
