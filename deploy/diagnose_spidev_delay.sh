#!/usr/bin/env bash
set -euo pipefail

echo "=== SPI (/dev/spidev0.0) boot delay diagnosis ==="
echo

echo "1) Does the device exist right now?"
ls -l /dev/spidev* 2>/dev/null || echo "No /dev/spidev* nodes right now."

echo
echo "2) systemd device unit status (if any):"
systemctl status dev-spidev0.0.device --no-pager 2>/dev/null || echo "No dev-spidev0.0.device unit active (normal if node not present)."

echo
echo "3) config.txt SPI lines:"
if [[ -f /boot/firmware/config.txt ]]; then
  echo "Found /boot/firmware/config.txt (Bookworm+)."
  grep -nE "^(dtparam=spi=on|dtoverlay=spi|dtparam=spi)" /boot/firmware/config.txt || true
elif [[ -f /boot/config.txt ]]; then
  echo "Found /boot/config.txt."
  grep -nE "^(dtparam=spi=on|dtoverlay=spi|dtparam=spi)" /boot/config.txt || true
else
  echo "No /boot/firmware/config.txt or /boot/config.txt found."
fi

echo
echo "4) Modules loaded:"
lsmod | grep -E "spi|spidev" || echo "No spi/spidev modules loaded (at least by name)."

echo
echo "5) dmesg SPI lines (last 80 matches):"
dmesg | grep -i spi | tail -n 80 || true

echo
echo "6) Boot messages around spidev wait (this boot):"
journalctl -b -o short-monotonic | grep -E "spidev0\.0|dev-spidev0\.0\.device" | tail -n 200 || true

echo
echo "Done."
