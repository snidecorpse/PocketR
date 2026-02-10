# Pocket-R Autoboot Fix (v2)

Use this if Pocket-R runs manually (`python3 app.py`) but does NOT auto-start after reboot.

## What this fixes
Runs `pocketr.service` as user **pi** instead of root, so it uses the same Python environment that worked for manual runs.

## Install
From your Pocket-R folder (where app.py lives):

```bash
unzip pocketr_deploy_fix_v2.zip
cp -r pocketr_deploy_fix_v2/deploy ./deploy
chmod +x deploy/*.sh
./deploy/setup_autoboot.sh
sudo reboot
```

## Debug
```bash
./deploy/debug_autoboot.sh
```
