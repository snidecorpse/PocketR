#!/usr/bin/env bash
set -euo pipefail

echo "[kiosk] Uninstalling Pocket-R autoboot service"
sudo systemctl stop pocketr.service 2>/dev/null || true
sudo systemctl disable pocketr.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/pocketr.service
sudo systemctl daemon-reload
sudo systemctl reset-failed pocketr.service 2>/dev/null || true
echo "✅ Removed."
