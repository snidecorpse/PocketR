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
sudo systemctl reset-failed pocketr.service || true
sudo systemctl restart pocketr.service

echo
echo "✅ Auto-boot enabled."
echo "Check:"
echo "  sudo systemctl status pocketr.service -l --no-pager"
echo "Logs:"
echo "  sudo journalctl -u pocketr.service -b -n 200 --no-pager"
