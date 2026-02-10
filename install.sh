#!/usr/bin/env bash
set -e

echo "[1/4] Updating apt..."
sudo apt update

echo "[2/4] Installing apt deps..."
# Display + math deps (matches Waveshare-style demos)
sudo apt install -y python3-pip python3-pil python3-numpy

echo "[3/4] Installing I2C deps for INA219..."
sudo apt install -y i2c-tools python3-smbus

echo "[4/4] Installing/Updating spidev..."
sudo pip3 install --upgrade spidev

echo "Done."
echo
echo "If button inputs don't respond, ensure pull-ups are enabled:"
echo "  sudo nano /boot/config.txt"
echo "Add (or keep) this line and reboot:"
echo "  gpio=6,19,5,26,13,21,20,16=pu"
echo
echo "INA219 battery notes:"
echo "  - Enable I2C: sudo raspi-config -> Interface Options -> I2C -> Enable -> reboot"
echo "  - Verify INA219 is visible: sudo i2cdetect -y 1  (look for 40)"
