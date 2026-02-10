# -*- coding: utf-8 -*-
"""
Pocket-R Tamagotchi Test (v5)
- Uses Waveshare ST7789 (240x240) demo driver (ST7789.py + config.py)
- Joystick changes rooms
- KEY1/KEY2/KEY3 do Feed / Play / Clean
- Joystick center:
    * short press -> random message
    * HOLD 10 seconds -> show shutdown instructions, turn off backlight, power off Linux
"""
import os
import time
import random
import subprocess
from dataclasses import dataclass
from typing import Dict, Optional

from PIL import Image, ImageDraw, ImageFont

import ST7789


# --------- Settings you might tweak ---------
ROTATE_DEG = 270          # 0 / 90 / 180 / 270. Demo 'main.py' used 270.
ACTIVE_HIGH = False       # If True: pressed reads 1. If False: pressed reads 0 (typical pull-up).
FPS = 15                  # Lower = less CPU.
BACKLIGHT = 60            # 0-100
SHUTDOWN_HOLD_SECONDS = 10.0
CLICK_MAX_SECONDS = 0.7   # PRESS shorter than this is treated as a click/message
# -------------------------------------------


ROOMS = ["GAME", "BED", "LIVING", "BATH"]
ROOM_BG = {
    "GAME": (18, 18, 32),
    "BED": (20, 16, 24),
    "LIVING": (16, 24, 18),
    "BATH": (20, 24, 28),
}


def clamp(v, lo=0, hi=100):
    return lo if v < lo else hi if v > hi else v


def load_font(size: int):
    # Try common system fonts; fall back to default.
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def pressed(raw: int) -> bool:
    # Buttons are usually wired as pull-up: released=1, pressed=0
    return (raw != 0) if ACTIVE_HIGH else (raw == 0)


def rotate_if_needed(img: Image.Image) -> Image.Image:
    if ROTATE_DEG in (90, 180, 270):
        return img.rotate(ROTATE_DEG, expand=False)
    return img


@dataclass
class Pet:
    hunger: float = 75.0     # 0..100
    happy: float = 70.0
    hygiene: float = 65.0
    energy: float = 80.0

    mood: str = "OK"         # OK / SAD / HAPPY
    last_action: str = "..."
    last_action_until: float = 0.0

    def tick(self, dt: float):
        # natural decay over time
        self.hunger = clamp(self.hunger - 2.2 * dt)
        self.hygiene = clamp(self.hygiene - 1.2 * dt)
        self.energy = clamp(self.energy - 1.6 * dt)

        # happiness depends on others
        stress = (100 - self.hunger) * 0.25 + (100 - self.hygiene) * 0.25 + (100 - self.energy) * 0.25
        self.happy = clamp(self.happy - 0.4 * dt - 0.01 * stress * dt)

        # mood
        if self.hunger < 20 or self.energy < 20 or self.hygiene < 20:
            self.mood = "SAD"
        elif self.happy > 75 and self.hunger > 40 and self.energy > 40:
            self.mood = "HAPPY"
        else:
            self.mood = "OK"

    def action(self, kind: str):
        now = time.time()
        if kind == "FEED":
            self.hunger = clamp(self.hunger + 28)
            self.happy = clamp(self.happy + 6)
            self.hygiene = clamp(self.hygiene - 4)
            self.last_action = "Nom nom!"
        elif kind == "PLAY":
            self.happy = clamp(self.happy + 18)
            self.energy = clamp(self.energy - 12)
            self.hunger = clamp(self.hunger - 6)
            self.last_action = "Yay!"
        elif kind == "CLEAN":
            self.hygiene = clamp(self.hygiene + 30)
            self.happy = clamp(self.happy + 4)
            self.last_action = "Fresh!"
        else:
            self.last_action = kind
        self.last_action_until = now + 1.3


class InputEdge:
    """
    Tracks pressed state for each input and returns edge events:
      - "UP" / "DOWN" / ... when the input is pressed (down-edge)
      - "UP_UP" / "PRESS_UP" / ... when the input is released (up-edge)
    """
    def __init__(self, disp):
        self.disp = disp
        self.state: Dict[str, bool] = {}

        self.map = {
            "UP": disp.GPIO_KEY_UP_PIN,
            "DOWN": disp.GPIO_KEY_DOWN_PIN,
            "LEFT": disp.GPIO_KEY_LEFT_PIN,
            "RIGHT": disp.GPIO_KEY_RIGHT_PIN,
            "PRESS": disp.GPIO_KEY_PRESS_PIN,
            "K1": disp.GPIO_KEY1_PIN,
            "K2": disp.GPIO_KEY2_PIN,
            "K3": disp.GPIO_KEY3_PIN,
        }

    def is_down(self, name: str) -> bool:
        return bool(self.state.get(name, False))

    def update(self) -> Dict[str, bool]:
        events: Dict[str, bool] = {}
        for name, pin in self.map.items():
            raw = self.disp.digital_read(pin)
            p = pressed(raw)
            prev = self.state.get(name, False)
            self.state[name] = p

            if (not prev) and p:
                events[name] = True              # pressed
            elif prev and (not p):
                events[f"{name}_UP"] = True      # released
        return events


def draw_bar(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, val: float, label: str, font):
    draw.rounded_rectangle((x, y, x + w, y + h), radius=3, outline=(220, 220, 220), width=1)
    fill_w = int((w - 2) * (val / 100.0))
    draw.rounded_rectangle((x + 1, y + 1, x + 1 + fill_w, y + h - 1), radius=2, fill=(255, 255, 255))
    draw.text((x, y - 10), f"{label}", font=font, fill=(255, 255, 255))


def make_pet_sprite(frame: int, mood: str) -> Image.Image:
    im = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    body = (255, 220, 200, 255)
    if mood == "SAD":
        body = (210, 210, 210, 255)
    elif mood == "HAPPY":
        body = (220, 255, 220, 255)

    d.rounded_rectangle((3, 4, 12, 13), radius=4, fill=body, outline=(0, 0, 0, 255), width=1)
    d.point((6, 7), fill=(0, 0, 0, 255))
    d.point((9, 7), fill=(0, 0, 0, 255))

    if mood == "SAD":
        d.line((6, 10, 9, 10), fill=(0, 0, 0, 255), width=1)
        d.point((5, 11), fill=(0, 0, 0, 255))
        d.point((10, 11), fill=(0, 0, 0, 255))
    elif mood == "HAPPY":
        d.arc((5, 9, 10, 13), start=200, end=340, fill=(0, 0, 0, 255), width=1)
    else:
        d.line((7, 10, 8, 10), fill=(0, 0, 0, 255), width=1)

    if frame % 2 == 0:
        d.rectangle((5, 13, 6, 14), fill=(0, 0, 0, 255))
        d.rectangle((9, 13, 10, 14), fill=(0, 0, 0, 255))
    else:
        d.rectangle((6, 13, 7, 14), fill=(0, 0, 0, 255))
        d.rectangle((8, 13, 9, 14), fill=(0, 0, 0, 255))

    return im


def room_icon(draw: ImageDraw.ImageDraw, room: str, x: int, y: int):
    c = (255, 255, 255)
    if room == "BED":
        draw.text((x, y), "Zz", fill=c)
    elif room == "BATH":
        draw.ellipse((x, y, x + 10, y + 10), outline=c, width=2)
        draw.polygon([(x + 5, y - 3), (x + 9, y + 4), (x + 1, y + 4)], outline=c, fill=None)
    elif room == "LIVING":
        draw.polygon([(x + 5, y + 10), (x, y + 5), (x + 2, y), (x + 5, y + 3), (x + 8, y), (x + 10, y + 5)],
                     outline=c, fill=None)
    elif room == "GAME":
        draw.rounded_rectangle((x, y + 3, x + 12, y + 10), radius=3, outline=c, width=2)
        draw.line((x + 3, y + 6, x + 5, y + 6), fill=c, width=2)
        draw.line((x + 4, y + 5, x + 4, y + 7), fill=c, width=2)
        draw.point((x + 9, y + 6), fill=c)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int):
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def show_shutdown_screen(disp, font_title, font_body):
    img = Image.new("RGB", (disp.width, disp.height), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.text((12, 12), "Shutting down...", font=font_title, fill=(255, 255, 255))

    msg = "Flick OFF the right switch when the screen backlight turns off."
    lines = wrap_text(draw, msg, font_body, max_width=disp.width - 24)

    y = 60
    for line in lines:
        draw.text((12, y), line, font=font_body, fill=(255, 255, 255))
        y += 18

    draw.text((12, disp.height - 26), "Safe to power on again anytime.", font=font_body, fill=(200, 200, 200))

    disp.ShowImage(rotate_if_needed(img))


def request_poweroff(disp, font_title, font_body):
    """
    Start a real Linux shutdown, but keep the backlight ON so the user keeps seeing
    the shutdown instructions. A separate systemd shutdown hook will turn the
    backlight OFF at the *end* of shutdown to signal it is safe to flip the power switch.
    """
    show_shutdown_screen(disp, font_title, font_body)

    # Flush writes
    try:
        os.sync()
    except Exception:
        pass

    # Initiate shutdown (pocketr.service runs as root, so no password)
    try:
        subprocess.Popen(["/usr/bin/systemctl", "poweroff"])
    except Exception:
        subprocess.Popen(["/sbin/shutdown", "-h", "now"])

    # Keep the screen up until systemd stops us
    while True:
        time.sleep(1)


def main():
    disp = ST7789.ST7789()
    disp.Init()
    disp.clear()
    disp.bl_DutyCycle(BACKLIGHT)

    inputs = InputEdge(disp)
    pet = Pet()
    room = "LIVING"

    # Fonts
    font_s = load_font(12)
    font_m = load_font(16)
    font_l = load_font(22)

    msgs = [
        "hi :)",
        "miss u",
        "hydrated?",
        "u got this!",
        "tiny W today",
        "take a breath",
    ]

    press_start: Optional[float] = None

    try:
        t_last = time.time()
        frame = 0

        while True:
            now = time.time()
            dt = max(0.0, min(now - t_last, 0.2))
            t_last = now

            pet.tick(dt)

            ev = inputs.update()

            # Rooms on d-pad press
            if "UP" in ev:
                room = "GAME"
            elif "DOWN" in ev:
                room = "LIVING"
            elif "LEFT" in ev:
                room = "BED"
            elif "RIGHT" in ev:
                room = "BATH"

            # Joystick center: click vs hold
            if "PRESS" in ev:
                press_start = now

            if "PRESS_UP" in ev:
                if press_start is not None:
                    held = now - press_start
                    if held <= CLICK_MAX_SECONDS:
                        pet.action(random.choice(msgs))
                press_start = None

            held_seconds = 0.0
            holding = False
            if press_start is not None and inputs.is_down("PRESS"):
                holding = True
                held_seconds = now - press_start
                if held_seconds >= SHUTDOWN_HOLD_SECONDS:
                    request_poweroff(disp, font_l, font_m)

            # Actions
            if "K1" in ev:
                pet.action("FEED")
            if "K2" in ev:
                pet.action("PLAY")
            if "K3" in ev:
                pet.action("CLEAN")

            # --- draw frame ---
            img = Image.new("RGB", (disp.width, disp.height), ROOM_BG[room])
            draw = ImageDraw.Draw(img)

            # top HUD
            draw.rectangle((0, 0, disp.width, 46), fill=(0, 0, 0))
            draw.text((8, 6), f"ROOM: {room}", font=font_m, fill=(255, 255, 255))
            room_icon(draw, room, 190, 6)

            draw_bar(draw, 8, 30, 52, 10, pet.hunger, "HUN", font=font_s)
            draw_bar(draw, 66, 30, 52, 10, pet.happy, "HAP", font=font_s)
            draw_bar(draw, 124, 30, 52, 10, pet.hygiene, "HYG", font=font_s)
            draw_bar(draw, 182, 30, 52, 10, pet.energy, "ENE", font=font_s)

            # pet sprite
            frame = (frame + 1) % 1000000
            sprite = make_pet_sprite(frame // 6, pet.mood).resize((72, 72), Image.NEAREST)

            pos = {
                "LIVING": (84, 98),
                "BED": (40, 120),
                "BATH": (140, 120),
                "GAME": (84, 120),
            }[room]
            img.paste(sprite, pos, sprite)

            # hint line
            hint = {
                "LIVING": "PRESS: message   (hold 10s = off)",
                "BED": "rest vibes",
                "BATH": "stay clean",
                "GAME": "play time",
            }[room]
            draw.text((8, 56), hint, font=font_s, fill=(255, 255, 255))

            # action bubble
            if now < pet.last_action_until:
                bubble_w, bubble_h = 150, 30
                bx = (disp.width - bubble_w) // 2
                by = 70
                draw.rounded_rectangle((bx, by, bx + bubble_w, by + bubble_h), radius=10,
                                       fill=(0, 0, 0), outline=(255, 255, 255), width=2)
                draw.text((bx + 10, by + 7), pet.last_action, font=font_m, fill=(255, 255, 255))

            # HOLD overlay
            if holding:
                remain = max(0.0, SHUTDOWN_HOLD_SECONDS - held_seconds)
                msg = f"HOLDING... OFF IN {remain:0.0f}"
                w = int(draw.textlength(msg, font=font_m)) + 20
                h = 34
                x = (disp.width - w) // 2
                y = disp.height - 70
                draw.rounded_rectangle((x, y, x + w, y + h), radius=10, fill=(0, 0, 0),
                                       outline=(255, 255, 255), width=2)
                draw.text((x + 10, y + 8), msg, font=font_m, fill=(255, 255, 255))

            # bottom legend
            draw.rectangle((0, disp.height - 26, disp.width, disp.height), fill=(0, 0, 0))
            draw.text((8, disp.height - 20), "K1 FEED   K2 PLAY   K3 CLEAN", font=font_s, fill=(255, 255, 255))

            disp.ShowImage(rotate_if_needed(img))

            # pace
            frame_time = time.time() - now
            time.sleep(max(0.0, (1.0 / FPS) - frame_time))

    except KeyboardInterrupt:
        pass
    except Exception as e:
        try:
            img = Image.new("RGB", (disp.width, disp.height), (0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), "CRASH", font=font_l, fill=(255, 0, 0))
            draw.text((10, 40), str(e)[:200], font=font_s, fill=(255, 255, 255))
            disp.ShowImage(rotate_if_needed(img))
            time.sleep(3)
        except Exception:
            pass
        raise
    finally:
        try:
            disp.clear()
            disp.module_exit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
