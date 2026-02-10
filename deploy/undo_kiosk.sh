#!/usr/bin/env bash
set -euo pipefail

echo "=== Pocket-R kiosk boot tune rollback ==="
echo

reenable() {
  local unit="$1"
  if systemctl list-unit-files | awk '{print $1}' | grep -qx "$unit"; then
    echo "-> enable --now $unit"
    sudo systemctl unmask "$unit" 2>/dev/null || true
    sudo systemctl enable --now "$unit" || true
  else
    echo "-> (skip) $unit not installed"
  fi
}

unmask_only() {
  local unit="$1"
  echo "-> unmask $unit"
  sudo systemctl unmask "$unit" || true
}

# Restore services
reenable ModemManager.service
reenable avahi-daemon.service
reenable avahi-daemon.socket

# Restore mounts
unmask_only sys-kernel-debug.mount
unmask_only sys-kernel-tracing.mount
unmask_only dev-mqueue.mount

cat <<'OPT'

Optional: if you disabled these manually, re-enable them yourself:

- dphys-swapfile.service
- systemd-timesyncd.service
- keyboard-setup.service
- fake-hwclock.service
- e2scrub_reap.service / e2scrub_all.timer

OPT

echo
echo "Rollback applied. Reboot recommended:"
echo "  sudo reboot"
