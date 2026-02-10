# Pocket‑R Tamagotchi Test (v4) — Auto‑boot + Safe Shutdown

Runs on the **Waveshare 1.3inch LCD HAT (ST7789, 240×240)** using the demo-style driver (`ST7789.py` + `config.py`).

## What’s new in v4
- **Auto‑boot** support (systemd service) so it starts on power‑on with **no keyboard**
- **Safe shutdown**: **hold joystick center for 10 seconds**
  - Shows an on‑screen message
  - Turns **backlight off**
  - Powers off Linux cleanly

## Controls
- **Joystick**:
  - **Up** → GAME
  - **Down** → LIVING
  - **Left** → BED
  - **Right** → BATH
  - **Center short‑press** → random “message bubble”
  - **Center HOLD 10s** → shutdown
- **Buttons**:
  - **KEY1** → FEED
  - **KEY2** → PLAY
  - **KEY3** → CLEAN

---

## Install & Run (manual)
```bash
chmod +x install.sh run.sh
./install.sh
./run.sh
```

## Enable auto‑boot (recommended for handheld)
```bash
chmod +x deploy/*.sh
./deploy/setup_autoboot.sh
sudo reboot
```

After reboot: the game starts automatically.

### Disable auto‑boot (undo)
```bash
sudo systemctl disable --now pocketr.service
```
Or fully remove:
```bash
./deploy/uninstall_autoboot.sh
```

---

## Safe shutdown (end‑user flow)
1) **Hold joystick center for 10 seconds**  
2) Screen shows shutdown instructions  
3) When the **backlight turns off**, flick **OFF** your power switch  
4) To turn back on, flick **ON** — it will boot and auto‑start

---

## Notes
- Auto‑boot works without logging in. Your Linux password still exists (good for maintenance), but you don’t need it for normal use.
- If SPI isn’t enabled, enable it once with:
  ```bash
  sudo raspi-config
  # Interfacing Options -> SPI -> Yes
  sudo reboot
  ```
