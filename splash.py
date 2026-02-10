# -*- coding: utf-8 -*-
"""Pocket-R Boot Splash (v6)

- Shows a "Booting Pocket-R..." screen on the Waveshare ST7789 LCD while Linux finishes booting.
- This does NOT show the kernel console; it is a Python-rendered splash started by systemd.
- pocketr.service stops this splash right before launching app.py.
"""

import time
import signal

from PIL import Image, ImageDraw, ImageFont
import ST7789

ROTATE_DEG = 270
BACKLIGHT = 60
FPS = 8

_running = True


def _handle_sigterm(signum, frame):
    global _running
    _running = False


signal.signal(signal.SIGTERM, _handle_sigterm)
signal.signal(signal.SIGINT, _handle_sigterm)


def rotate_if_needed(img: Image.Image) -> Image.Image:
    if ROTATE_DEG in (90, 180, 270):
        return img.rotate(ROTATE_DEG, expand=False)
    return img


def load_font(size: int):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def uptime_seconds() -> int:
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            return int(float(f.read().split()[0]))
    except Exception:
        return 0


def main():
    disp = ST7789.ST7789()
    try:
        disp.Init()
        disp.clear()
        disp.bl_DutyCycle(BACKLIGHT)

        font_title = load_font(26)
        font_body = load_font(16)
        font_small = load_font(12)

        spinner = ["|", "/", "-", "\\"]

        i = 0
        while _running:
            img = Image.new("RGB", (disp.width, disp.height), (0, 0, 0))
            d = ImageDraw.Draw(img)

            d.text((14, 18), "POCKET-R", font=font_title, fill=(255, 255, 255))
            sp = spinner[i % len(spinner)]
            d.text((16, 64), f"Booting... {sp}", font=font_body, fill=(220, 220, 220))

            up = uptime_seconds()
            d.text((16, 92), f"Up: {up}s", font=font_small, fill=(150, 150, 150))

            d.text((16, disp.height - 44), "Please wait", font=font_body, fill=(220, 220, 220))
            d.text((16, disp.height - 22), "Launching game soon", font=font_small, fill=(150, 150, 150))

            disp.ShowImage(rotate_if_needed(img))
            i += 1
            time.sleep(1.0 / FPS)

    finally:
        try:
            disp.clear()
            disp.module_exit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
