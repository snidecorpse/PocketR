#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
echo "[kiosk] Installing Pocket-R autoboot service for: $APP_DIR"

# Stop/disable any existing service cleanly
sudo systemctl stop pocketr.service 2>/dev/null || true
sudo systemctl disable pocketr.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/pocketr.service

# Install fresh service
TMP="/tmp/pocketr.service.$$"
sed "s|@@APP_DIR@@|$APP_DIR|g" "$APP_DIR/deploy/pocketr.service.in" > "$TMP"
sudo cp "$TMP" /etc/systemd/system/pocketr.service
sudo chmod 0644 /etc/systemd/system/pocketr.service

sudo systemctl daemon-reload
sudo systemctl enable pocketr.service
sudo systemctl reset-failed pocketr.service 2>/dev/null || true
sudo systemctl start pocketr.service

echo
echo "✅ Installed. Check:"
echo "  sudo systemctl status pocketr.service -l --no-pager"
echo "  sudo journalctl -u pocketr.service -b -n 200 --no-pager"
