#!/usr/bin/env bash
set -euo pipefail

echo "=== Pocket-R kiosk boot tune ==="
echo "This will disable a few non-essential services (for a single-purpose device)."
echo

apply_disable() {
  local unit="$1"
  if systemctl list-unit-files | awk '{print $1}' | grep -qx "$unit"; then
    echo "-> disable --now $unit"
    sudo systemctl disable --now "$unit" || true
  else
    echo "-> (skip) $unit not installed"
  fi
}

apply_mask() {
  local unit="$1"
  echo "-> mask $unit"
  sudo systemctl mask "$unit" || true
}

echo "[1/5] Show current boot stats"
systemd-analyze time || true
echo
systemd-analyze blame | head -n 25 || true
echo

echo "[2/5] Safe wins for Pocket-R"
# ModemManager: only needed for cellular modems / 4G hats etc.
apply_disable ModemManager.service

# Avahi: only needed for .local mDNS discovery
apply_disable avahi-daemon.service
apply_disable avahi-daemon.socket

echo
echo "[3/5] Small wins (kernel debug/tracing mounts)"
# Only needed for kernel debugging / tracing tools.
apply_mask sys-kernel-debug.mount
apply_mask sys-kernel-tracing.mount

# mqueue (POSIX message queues) is rarely needed for simple kiosk apps.
apply_mask dev-mqueue.mount

echo
echo "[4/5] OPTIONAL toggles (uncomment if you want them)"
cat <<'OPT'

If you want to also disable these, edit this script and uncomment:

# Swap on SD card (optional; risk: OOM -> app crash)
# sudo dphys-swapfile swapoff
# sudo dphys-swapfile uninstall
# sudo systemctl disable --now dphys-swapfile.service

# Time sync (optional; risk: wrong timestamps until network/RTC)
# sudo systemctl disable --now systemd-timesyncd.service

# Keyboard setup (optional; only if you truly never plug a keyboard)
# sudo systemctl disable --now keyboard-setup.service

# Fake hwclock (optional; only if you have an RTC, or you don't care about time)
# sudo systemctl disable --now fake-hwclock.service

# e2scrub (optional; saves ~2s; reduces periodic filesystem scrub)
# sudo systemctl disable --now e2scrub_reap.service
# sudo systemctl disable --now e2scrub_all.timer

OPT

echo
echo "[5/5] Done. Reboot to measure:"
echo "  sudo reboot"
echo
echo "After reboot, re-check:"
echo "  systemd-analyze time"
echo "  systemd-analyze blame | head -n 25"
