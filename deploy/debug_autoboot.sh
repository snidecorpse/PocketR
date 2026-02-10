#!/usr/bin/env bash
set -euo pipefail
echo "=== pocketr.service enabled? ==="
sudo systemctl is-enabled pocketr.service || true
echo
echo "=== pocketr.service status ==="
sudo systemctl status pocketr.service -l --no-pager || true
echo
echo "=== pocketr.service logs (this boot) ==="
sudo journalctl -u pocketr.service -b -n 200 --no-pager || true
