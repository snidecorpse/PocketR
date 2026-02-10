# Pocket-R v7 Boot Splash Fast Pack

This pack fixes a common ~90s delay where Pocket-R waits on `local-fs.target`.
If your system is waiting for a missing drive listed in `/etc/fstab`, `local-fs.target`
can be delayed ~1m30, and Pocket-R won't start until after that.

These updated service templates remove `After=local-fs.target` so the splash/game can
start immediately (as soon as SPI is available), even if some mount is timing out.

## Install
Copy `deploy/` into your Pocket-R folder (same folder as app.py), overwriting existing deploy files:
```bash
cp -r deploy ~/pocketr_tamagotchi_test/deploy
cd ~/pocketr_tamagotchi_test
chmod +x deploy/*.sh
./deploy/setup_autoboot.sh
sudo reboot
```

## Diagnose a 90s delay
```bash
chmod +x deploy/diagnose_boot_delay.sh
./deploy/diagnose_boot_delay.sh
```

If you see a `.mount` unit or local-fs critical chain taking ~1m30, check `/etc/fstab`
for missing devices (USB drive, SSD, etc.) and add `nofail` and a shorter timeout.
