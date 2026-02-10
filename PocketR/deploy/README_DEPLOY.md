# Pocket-R Auto-boot + USB Update Pack

Drop this `deploy/` folder into your Pocket-R project (same folder as `app.py`), then run the setup scripts.

## 1) Auto-start on boot (no keyboard needed)
```bash
chmod +x deploy/*.sh
./deploy/setup_autoboot.sh
```

Reboot to test:
```bash
sudo reboot
```

## 2) Optional: USB "update pack" (plug in a labeled drive to update + restart)
```bash
./deploy/setup_usb_update.sh
```

### USB contents accepted
Put **one** of these on a USB drive (filesystem label **POCKETR**):

A) `pocketr_update.zip` at USB root  
B) `app.py` (and other files) at USB root  
C) `pocketr_tamagotchi_test/` folder at USB root

When you plug it in, it copies into your app folder and restarts `pocketr.service`.

### Label the USB drive "POCKETR"
- FAT/ext filesystems: label it in whatever tool you use, or from Linux with `e2label` / `fatlabel`.
- exFAT: install support if needed: `sudo apt install -y exfatprogs`

## 3) Optional: console autologin (removes login prompt)
```bash
./deploy/enable_console_autologin.sh
# or specify another user:
./deploy/enable_console_autologin.sh pi
```

Undo:
```bash
./deploy/disable_console_autologin.sh
```

## Uninstall
```bash
./deploy/uninstall_autoboot.sh
```
