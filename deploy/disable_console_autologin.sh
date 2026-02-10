#!/usr/bin/env bash
set -euo pipefail

echo "[autologin] Disabling console autologin on tty1"
sudo rm -f /etc/systemd/system/getty@tty1.service.d/autologin.conf
sudo rmdir --ignore-fail-on-non-empty /etc/systemd/system/getty@tty1.service.d 2>/dev/null || true

sudo systemctl daemon-reload
sudo systemctl restart getty@tty1.service

echo "✅ Console autologin disabled."
