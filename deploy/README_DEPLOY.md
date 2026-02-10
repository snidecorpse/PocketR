# Pocket-R v8 Deploy Patch (removes 90s /dev/spidev0.0 wait)

If you saw:
  "A start job is running for dev-spidev0.0.device (1min 30s / 1min 30s)"

That's systemd waiting ~90s for a device unit job. This patch removes explicit `Wants/After=dev-spidev0.0.device`
and uses a short (5s) poll for `/dev/spidev0.0` instead.

## Install
```bash
unzip pocketr_v8_deploy_no_90s_spidev_wait.zip
cp -r pocketr_v8_deploy_no_90s_spidev_wait/deploy ~/pocketr_tamagotchi_test/deploy

cd ~/pocketr_tamagotchi_test
chmod +x deploy/*.sh
./deploy/setup_autoboot.sh
sudo reboot
```

## Diagnose
```bash
./deploy/diagnose_spidev_delay.sh
```

If `/dev/spidev0.0` never appears, ensure SPI is enabled in config.txt (Bookworm uses /boot/firmware/config.txt).
