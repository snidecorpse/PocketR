#!/usr/bin/env bash
set -euo pipefail

echo "[uninstall] Stopping/disabling pocketr.service"
sudo systemctl stop pocketr.service || true
sudo systemctl disable pocketr.service || true
sudo rm -f /etc/systemd/system/pocketr.service

echo "[uninstall] Removing USB update hook (if installed)"
sudo systemctl stop pocketr-usb-update.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/pocketr-usb-update.service
sudo rm -f /etc/udev/rules.d/99-pocketr-usb.rules

sudo systemctl daemon-reload
sudo udevadm control --reload-rules || true

echo "✅ Removed."
