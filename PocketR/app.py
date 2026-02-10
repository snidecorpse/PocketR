# -*- coding: utf-8 -*-
"""
Pocket-R Tamagotchi Test (v3-ish, simple)
- Uses Waveshare ST7789 (240x240) demo driver (ST7789.py + config.py)
- Joystick changes rooms
- KEY1/KEY2/KEY3 do Feed / Play / Clean
"""
import time
import random
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

import ST7789


# --------- Settings you might tweak ---------
ROTATE_DEG = 270          # 0 / 90 / 180 / 270. Demo 'main.py' used 270.
ACTIVE_HIGH = False       # If True: pressed reads 1. If False: pressed reads 0 (typical pull-up).
FPS = 15                  # Lower = less CPU.
BACKLIGHT = 60            # 0-100
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
    # Try a common system font; fall back to default.
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

    def update(self) -> Dict[str, bool]:
        events = {}
        for name, pin in self.map.items():
            raw = self.disp.digital_read(pin)
            p = pressed(raw)
            prev = self.state.get(name, False)
            self.state[name] = p
            if (not prev) and p:
                events[name] = True
        return events


def draw_bar(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, val: float, label: str, font):
    # outline
    draw.rounded_rectangle((x, y, x + w, y + h), radius=3, outline=(220, 220, 220), width=1)
    # fill
    fill_w = int((w - 2) * (val / 100.0))
    draw.rounded_rectangle((x + 1, y + 1, x + 1 + fill_w, y + h - 1), radius=2, fill=(255, 255, 255))
    draw.text((x, y - 10), f"{label}", font=font, fill=(255, 255, 255))


def make_pet_sprite(frame: int, mood: str) -> Image.Image:
    # 16x16 pixel sprite, resized with NEAREST later
    im = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    body = (255, 220, 200, 255)
    if mood == "SAD":
        body = (210, 210, 210, 255)
    elif mood == "HAPPY":
        body = (220, 255, 220, 255)

    # body blob
    d.rounded_rectangle((3, 4, 12, 13), radius=4, fill=body, outline=(0, 0, 0, 255), width=1)

    # eyes
    d.point((6, 7), fill=(0, 0, 0, 255))
    d.point((9, 7), fill=(0, 0, 0, 255))

    # mouth
    if mood == "SAD":
        d.line((6, 10, 9, 10), fill=(0, 0, 0, 255), width=1)
        d.point((5, 11), fill=(0, 0, 0, 255))
        d.point((10, 11), fill=(0, 0, 0, 255))
    elif mood == "HAPPY":
        d.arc((5, 9, 10, 13), start=200, end=340, fill=(0, 0, 0, 255), width=1)
    else:
        d.line((7, 10, 8, 10), fill=(0, 0, 0, 255), width=1)

    # legs (two-frame walk)
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
        # Zzz
        draw.text((x, y), "Zz", fill=c)
    elif room == "BATH":
        # droplet
        draw.ellipse((x, y, x+10, y+10), outline=c, width=2)
        draw.polygon([(x+5, y-3), (x+9, y+4), (x+1, y+4)], outline=c, fill=None)
    elif room == "LIVING":
        # heart
        draw.polygon([(x+5, y+10), (x, y+5), (x+2, y), (x+5, y+3), (x+8, y), (x+10, y+5)], outline=c, fill=None)
    elif room == "GAME":
        # controller-ish
        draw.rounded_rectangle((x, y+3, x+12, y+10), radius=3, outline=c, width=2)
        draw.line((x+3, y+6, x+5, y+6), fill=c, width=2)
        draw.line((x+4, y+5, x+4, y+7), fill=c, width=2)
        draw.point((x+9, y+6), fill=c)


def rotate_if_needed(img: Image.Image) -> Image.Image:
    if ROTATE_DEG in (90, 180, 270):
        return img.rotate(ROTATE_DEG, expand=False)
    return img


def main():
    disp = ST7789.ST7789()
    disp.Init()
    disp.clear()
    disp.bl_DutyCycle(BACKLIGHT)

    inputs = InputEdge(disp)
    pet = Pet()
    room_i = 2  # start in LIVING
    room = ROOMS[room_i]

    # rendering assets
    font_s = load_font(12)
    font_m = load_font(16)
    font_l = load_font(22)

    # animation
    frame = 0
    t_last = time.time()
    t_accum = 0.0

    # message pool
    msgs = [
        "hi :)",
        "miss u",
        "hydrated?",
        "u got this!",
        "tiny W today",
        "take a breath",
    ]

    try:
        while True:
            now = time.time()
            dt = now - t_last
            t_last = now
            dt = max(0.0, min(dt, 0.2))

            # sim tick
            pet.tick(dt)

            # inputs (edge events)
            ev = inputs.update()
            if "UP" in ev:
                room = "GAME"
            elif "DOWN" in ev:
                room = "LIVING"
            elif "LEFT" in ev:
                room = "BED"
            elif "RIGHT" in ev:
                room = "BATH"
            elif "PRESS" in ev:
                # quick random message
                pet.action(random.choice(msgs))

            if "K1" in ev:
                pet.action("FEED")
            if "K2" in ev:
                pet.action("PLAY")
            if "K3" in ev:
                pet.action("CLEAN")

            # draw frame
            img = Image.new("RGB", (disp.width, disp.height), ROOM_BG[room])
            draw = ImageDraw.Draw(img)

            # top HUD
            draw.rectangle((0, 0, disp.width, 46), fill=(0, 0, 0))
            draw.text((8, 6), f"ROOM: {room}", font=font_m, fill=(255, 255, 255))
            room_icon(draw, room, 190, 6)

            draw_bar(draw, 8, 30, 52, 10, pet.hunger, "HUN", font_s)
            draw_bar(draw, 66, 30, 52, 10, pet.happy, "HAP", font_s)
            draw_bar(draw, 124, 30, 52, 10, pet.hygiene, "HYG", font_s)
            draw_bar(draw, 182, 30, 52, 10, pet.energy, "ENE", font_s)

            # pet sprite
            frame = (frame + 1) % 1000000
            sprite = make_pet_sprite(frame // 6, pet.mood).resize((72, 72), Image.NEAREST)

            # place pet in slightly different spot depending room
            pos = {
                "LIVING": (84, 98),
                "BED": (40, 120),
                "BATH": (140, 120),
                "GAME": (84, 120),
            }[room]

            img.paste(sprite, pos, sprite)

            # room label / hint
            hint = {
                "LIVING": "PRESS: message",
                "BED": "rest vibes",
                "BATH": "stay clean",
                "GAME": "play time",
            }[room]
            draw.text((8, 56), hint, font=font_s, fill=(255, 255, 255))

            # action bubble
            if now < pet.last_action_until:
                bubble_w = 150
                bubble_h = 30
                bx = (disp.width - bubble_w) // 2
                by = 70
                draw.rounded_rectangle((bx, by, bx + bubble_w, by + bubble_h), radius=10, fill=(0, 0, 0), outline=(255, 255, 255), width=2)
                draw.text((bx + 10, by + 7), pet.last_action, font=font_m, fill=(255, 255, 255))

            # bottom legend
            draw.rectangle((0, disp.height - 26, disp.width, disp.height), fill=(0, 0, 0))
            draw.text((8, disp.height - 20), "K1 FEED   K2 PLAY   K3 CLEAN", font=font_s, fill=(255, 255, 255))

            # push to LCD (rotation)
            disp.ShowImage(rotate_if_needed(img))

            # pace
            time.sleep(max(0.0, (1.0 / FPS) - (time.time() - now)))

    except KeyboardInterrupt:
        pass
    except Exception as e:
        # show error on display for quick debugging
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
