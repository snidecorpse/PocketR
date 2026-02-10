# Pocket-R Clean Kiosk Autoboot (v1)

This pack fixes common Raspberry Pi boot timing issues where `/dev/spidev*` appears late, causing systemd services to fail on boot even though the app runs manually.

## Install (from your PocketR folder where app.py lives)
```bash
unzip pocketr_deploy_clean_kiosk_v1.zip
cp -r pocketr_deploy_clean_kiosk_v1/deploy ./deploy
chmod +x deploy/*.sh
./deploy/install_kiosk.sh
sudo reboot
```

## Debug
```bash
cd ~/PocketR
./deploy/debug_kiosk.sh
```

## Uninstall
```bash
./deploy/uninstall_kiosk.sh
```
