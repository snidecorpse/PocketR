#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "[setup] App dir: $APP_DIR"
echo "[setup] Installing systemd service: pocketr.service"

TMP_SERVICE="/tmp/pocketr.service.$$"
sed "s|@@APP_DIR@@|$APP_DIR|g" "$APP_DIR/deploy/pocketr.service.in" > "$TMP_SERVICE"

sudo cp "$TMP_SERVICE" /etc/systemd/system/pocketr.service
sudo chmod 0644 /etc/systemd/system/pocketr.service

echo "[setup] Installing shutdown backlight hook: pocketr-poweroff-backlight.service"

TMP_POWEROFF="/tmp/pocketr-poweroff-backlight.service.$$"
sed "s|@@APP_DIR@@|$APP_DIR|g" "$APP_DIR/deploy/pocketr-poweroff-backlight.service.in" > "$TMP_POWEROFF"

sudo cp "$TMP_POWEROFF" /etc/systemd/system/pocketr-poweroff-backlight.service
sudo chmod 0644 /etc/systemd/system/pocketr-poweroff-backlight.service
sudo systemctl enable pocketr-poweroff-backlight.service

sudo systemctl daemon-reload
sudo systemctl enable pocketr.service
sudo systemctl restart pocketr.service

echo
echo "✅ Auto-boot enabled."
echo "Useful commands:"
echo "  systemctl status pocketr.service --no-pager"
echo "  journalctl -u pocketr.service -n 200 --no-pager"
