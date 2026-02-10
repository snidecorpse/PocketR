#!/usr/bin/env bash
set -euo pipefail
echo "=== pocketr.service enabled? ==="
systemctl is-enabled pocketr.service || true
echo
echo "=== pocketr.service status ==="
systemctl status pocketr.service --no-pager || true
echo
echo "=== pocketr.service logs (this boot) ==="
journalctl -u pocketr.service -b -n 200 --no-pager || true
