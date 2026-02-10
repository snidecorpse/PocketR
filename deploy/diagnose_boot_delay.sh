#!/usr/bin/env bash
set -euo pipefail

echo "=== Pocket-R boot delay quick diagnosis ==="
echo
echo "1) Overall boot time:"
systemd-analyze time || true
echo
echo "2) Top 30 slow units:"
systemd-analyze blame | head -n 30 || true
echo
echo "3) Critical chain for local-fs.target (if you see ~1m30, often a missing fstab device):"
systemd-analyze critical-chain local-fs.target || true
echo
echo "4) Mount units taking long (if any):"
systemd-analyze blame | grep -E '\.mount' | head -n 50 || true
echo
echo "5) Any failed units:"
systemctl --failed || true
echo
echo "Done."
