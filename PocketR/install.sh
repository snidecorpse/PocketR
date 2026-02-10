#!/usr/bin/env bash
set -e

echo "[1/3] Updating apt..."
sudo apt update

echo "[2/3] Installing apt deps..."
# Matches Waveshare wiki guidance
sudo apt install -y python3-pip python3-pil python3-numpy

echo "[3/3] Installing/Updating spidev..."
sudo pip3 install --upgrade spidev

echo "Done."
echo "If button inputs don't respond, ensure pull-ups are enabled:"
echo "  sudo nano /boot/config.txt"
echo "Add (or keep) this line and reboot:"
echo "  gpio=6,19,5,26,13,21,20,16=pu"
