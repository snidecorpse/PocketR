#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-}"
if [[ -z "$APP_DIR" || ! -d "$APP_DIR" ]]; then
  echo "Usage: usb_update.sh /absolute/path/to/app"
  exit 2
fi

LABEL="POCKETR"
DEV="$(/sbin/blkid -L "$LABEL" 2>/dev/null || true)"
if [[ -z "$DEV" ]]; then
  echo "[usb-update] No device with label $LABEL found."
  exit 0
fi

MNT="/mnt/pocketr_usb"
mkdir -p "$MNT"

# Mount if not already mounted
if ! mountpoint -q "$MNT"; then
  echo "[usb-update] Mounting $DEV to $MNT..."
  # Try a generic mount; works for ext*, vfat, exfat (if exfat packages installed)
  mount "$DEV" "$MNT" || {
    echo "[usb-update] Mount failed. If this is exFAT, install support: sudo apt install -y exfatprogs"
    exit 1
  }
fi

cleanup() {
  if mountpoint -q "$MNT"; then
    umount "$MNT" || true
  fi
}
trap cleanup EXIT

echo "[usb-update] Looking for update payload on $MNT..."

# Accept any of these layouts on the USB drive:
# A) /pocketr_update.zip  (zip contains app.py, ST7789.py, etc OR a folder)
# B) /app.py directly at the root
# C) /pocketr_tamagotchi_test/app.py (folder drop)
SRC=""

if [[ -f "$MNT/pocketr_update.zip" ]]; then
  echo "[usb-update] Found pocketr_update.zip"
  TMP="/tmp/pocketr_update.$$"
  mkdir -p "$TMP"
  unzip -oq "$MNT/pocketr_update.zip" -d "$TMP"

  if [[ -f "$TMP/app.py" ]]; then
    SRC="$TMP"
  elif [[ -d "$TMP/pocketr_tamagotchi_test" && -f "$TMP/pocketr_tamagotchi_test/app.py" ]]; then
    SRC="$TMP/pocketr_tamagotchi_test"
  else
    # try first folder that contains app.py
    FOUND="$(find "$TMP" -maxdepth 3 -type f -name app.py -print -quit || true)"
    if [[ -n "$FOUND" ]]; then
      SRC="$(dirname "$FOUND")"
    fi
  fi
elif [[ -f "$MNT/app.py" ]]; then
  SRC="$MNT"
elif [[ -d "$MNT/pocketr_tamagotchi_test" && -f "$MNT/pocketr_tamagotchi_test/app.py" ]]; then
  SRC="$MNT/pocketr_tamagotchi_test"
fi

if [[ -z "$SRC" ]]; then
  echo "[usb-update] No update found. Put either:"
  echo "  - pocketr_update.zip at USB root, OR"
  echo "  - app.py at USB root, OR"
  echo "  - pocketr_tamagotchi_test/ folder at USB root."
  exit 0
fi

echo "[usb-update] Updating app from: $SRC"
echo "[usb-update] Target app dir: $APP_DIR"

# Use rsync if available; else fallback to cp
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete "$SRC/" "$APP_DIR/"
else
  echo "[usb-update] rsync not found; using cp (won't delete old files)."
  cp -a "$SRC/"* "$APP_DIR/"
fi

# Keep ownership friendly for pi user edits
chown -R pi:pi "$APP_DIR" 2>/dev/null || true

echo "[usb-update] Restarting pocketr.service..."
systemctl restart pocketr.service || true

echo "[usb-update] Done."
