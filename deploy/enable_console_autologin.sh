#!/usr/bin/env bash
set -euo pipefail

USER_NAME="${1:-pi}"

echo "[autologin] Enabling console autologin on tty1 for user: $USER_NAME"
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d

sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf >/dev/null <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin ${USER_NAME} --noclear %I \$TERM
EOF

sudo systemctl daemon-reload
sudo systemctl restart getty@tty1.service

echo "✅ Console autologin enabled."
echo "To undo: run ./deploy/disable_console_autologin.sh"
