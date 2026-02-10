#!/usr/bin/env bash
set -euo pipefail

echo "=== Where is app.py? ==="
pwd
ls -l ./app.py 2>/dev/null || true
echo

echo "=== SPI nodes right now ==="
ls -l /dev/spidev* 2>/dev/null || echo "(none found)"
echo

echo "=== pocketr.service (installed) ==="
sudo systemctl cat pocketr.service || true
echo

echo "=== pocketr.service status ==="
sudo systemctl status pocketr.service -l --no-pager || true
echo

echo "=== pocketr logs (this boot) ==="
sudo journalctl -u pocketr.service -b -n 200 --no-pager || true
