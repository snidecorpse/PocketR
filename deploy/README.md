# Pocket-R Boot Tune Tools (safe-ish kiosk trimming)

These scripts help you disable services that are commonly unnecessary for a single-purpose Pocket-R device.
They are written to be conservative: **they do NOT disable critical storage checks**, and optional sections are clearly marked.

## 0) Before you change anything (recommended)
Run:
```bash
systemd-analyze time
systemd-analyze blame | head -n 30
systemd-analyze critical-chain
systemd-analyze critical-chain pocketr.service
```

## 1) Apply kiosk tune
```bash
chmod +x tune_kiosk.sh undo_kiosk.sh
./tune_kiosk.sh
sudo reboot
```

## 2) Undo (rollback)
```bash
./undo_kiosk.sh
sudo reboot
```

## Notes
- If you still want to `git pull` over Wi‑Fi, keep NetworkManager enabled.
- Disabling swap is optional; do it only if you're comfortable with the risk of OOM (crashes) under memory pressure.
- Disabling timesync means system time may be wrong until the network sets it (or an RTC is installed).
