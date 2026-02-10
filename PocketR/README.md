# Pocket‑R Tamagotchi Test (Pi + Waveshare 1.3" LCD HAT)

This is a **simple “v3-ish” tamagotchi test** that runs on the **Waveshare 1.3inch LCD HAT (ST7789, 240×240)** using the same style of demo driver you already ran (`ST7789.py` + `config.py`).

## Controls

- **Joystick**:
  - **Up** → GAME
  - **Down** → LIVING
  - **Left** → BED
  - **Right** → BATH
  - **Press** → shows a random message bubble
- **Buttons**:
  - **KEY1** → FEED
  - **KEY2** → PLAY
  - **KEY3** → CLEAN

## What you’ll see
- Top HUD with 4 stats (HUN/HAP/HYG/ENE)
- A tiny pixel pet that “walks”
- Room changes + an action/message bubble

---

## 0) One-time setup (SPI + deps)

### Enable SPI
```bash
sudo raspi-config
# Interfacing Options -> SPI -> Yes
sudo reboot
```

### Install dependencies
From inside this project folder:
```bash
chmod +x install.sh run.sh
./install.sh
```

> Waveshare also recommends enabling GPIO pull-ups for the buttons. If your inputs act weird, add this to `/boot/config.txt` and reboot:
>
> `gpio=6,19,5,26,13,21,20,16=pu`

(Those BCM pins match the Waveshare button/joystick pin map.)  

---

## 1) Run it
```bash
./run.sh
```

If the image is sideways, open `app.py` and change:
- `ROTATE_DEG = 270` → try `0`, `90`, `180`, or `270`

If buttons feel inverted, toggle:
- `ACTIVE_HIGH = False` → `True`

---

## 2) How to download this zip on the Pi (once you host it)

Example (replace URL with wherever you host the zip):
```bash
wget -O pocketr.zip "https://your-hosting-site/pocketr_tamagotchi_test.zip"
unzip pocketr.zip
cd pocketr_tamagotchi_test
chmod +x install.sh run.sh
./install.sh
./run.sh
```

Good free hosting options:
- GitHub repo + “Releases” (direct zip download link)
- Google Drive (make file public) / Dropbox shared link (direct download)
- Any simple web server

---

## Files
- `app.py` — the tamagotchi test
- `ST7789.py` + `config.py` — LCD + input driver (Waveshare-style)
- `install.sh` — installs deps
- `run.sh` — runs with sudo
