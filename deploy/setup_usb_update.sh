#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "[setup] App dir: $APP_DIR"
echo "[setup] Installing USB update hook (label POCKETR)..."

# deps
sudo apt update
sudo apt install -y rsync unzip util-linux

# systemd service
TMP_SERVICE="/tmp/pocketr-usb-update.service.$$"
sed "s|@@APP_DIR@@|$APP_DIR|g" "$APP_DIR/deploy/pocketr-usb-update.service.in" > "$TMP_SERVICE"

sudo cp "$TMP_SERVICE" /etc/systemd/system/pocketr-usb-update.service
sudo chmod 0644 /etc/systemd/system/pocketr-usb-update.service

# udev rule
sudo cp "$APP_DIR/deploy/99-pocketr-usb.rules" /etc/udev/rules.d/99-pocketr-usb.rules
sudo chmod 0644 /etc/udev/rules.d/99-pocketr-usb.rules

# script
sudo chmod +x "$APP_DIR/deploy/usb_update.sh"

sudo systemctl daemon-reload
sudo udevadm control --reload-rules
sudo udevadm trigger

echo
echo "✅ USB update enabled."
echo "How to use:"
echo "  1) Label your USB drive filesystem as POCKETR"
echo "  2) Put either pocketr_update.zip OR your app files on it"
echo "  3) Plug it in -> Pocket-R auto-updates + restarts"
