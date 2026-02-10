#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "[setup] App dir: $APP_DIR"
echo "[setup] Installing systemd service: pocketr.service"

TMP_SERVICE="/tmp/pocketr.service.$$"
sed "s|@@APP_DIR@@|$APP_DIR|g" "$APP_DIR/deploy/pocketr.service.in" > "$TMP_SERVICE"

sudo cp "$TMP_SERVICE" /etc/systemd/system/pocketr.service
sudo chmod 0644 /etc/systemd/system/pocketr.service

sudo systemctl daemon-reload
sudo systemctl enable pocketr.service
sudo systemctl restart pocketr.service

echo
echo "✅ Auto-boot enabled."
echo "Useful commands:"
echo "  systemctl status pocketr.service --no-pager"
echo "  journalctl -u pocketr.service -n 200 --no-pager"
