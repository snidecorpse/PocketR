#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
echo "[setup] App dir: $APP_DIR"

install_unit() {
  local src_in="$1"
  local dst="/etc/systemd/system/$2"
  local tmp="/tmp/$2.$$"
  sed "s|@@APP_DIR@@|$APP_DIR|g" "$src_in" > "$tmp"
  sudo cp "$tmp" "$dst"
  sudo chmod 0644 "$dst"
}

echo "[setup] Installing pocketr-splash.service"
install_unit "$APP_DIR/deploy/pocketr-splash.service.in" "pocketr-splash.service"

echo "[setup] Installing pocketr.service"
install_unit "$APP_DIR/deploy/pocketr.service.in" "pocketr.service"

sudo systemctl daemon-reload
sudo systemctl enable pocketr-splash.service
sudo systemctl enable pocketr.service

# Start splash immediately; then start game (game will stop splash)
sudo systemctl restart pocketr-splash.service || true
sudo systemctl restart pocketr.service || true

echo
echo "✅ Installed/updated services."
echo "Check:"
echo "  systemctl status pocketr-splash.service --no-pager"
echo "  systemctl status pocketr.service --no-pager"
echo "Logs:"
echo "  journalctl -u pocketr.service -b --no-pager | tail -n 200"
