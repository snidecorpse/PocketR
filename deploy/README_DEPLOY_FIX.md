# Pocket-R Autoboot Fix (v3)

Use this if autoboot FAILED with an ExecStartPre check like `/dev/spidev0,0` (comma) or said it couldn't find `/dev/spidev0.0`.

## What this fixes
- Uses a robust SPI pre-check: `ls /dev/spidev*` (works whether the device is `/dev/spidev0.0` or `/dev/spidev0.1`)
- Debug script uses sudo so logs show up
- Resets failed state automatically

## Install
From your Pocket-R folder (where app.py lives):
```bash
unzip pocketr_deploy_fix_v3.zip
cp -r pocketr_deploy_fix_v3/deploy ./deploy
chmod +x deploy/*.sh
./deploy/setup_autoboot.sh
sudo reboot
```

## Debug
```bash
./deploy/debug_autoboot.sh
```
