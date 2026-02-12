#!/usr/bin/env python3
"""Pocket-R Desktop Runner

Runs the SAME ./game/main.py loop on a laptop (no ST7789 / no GPIO).

Controls (keyboard):
  D-pad: Arrow keys (or WASD)
  PRESS: Enter or Space
  K1 (Confirm): 1
  K2 (Back):    2
  K3 (Hold):    3   (hold ~3s triggers "shutdown" -> exits runner)

Dev helpers:
  R  = hot reload game modules
  ESC/Q = quit

Usage:
  python3 desktop_run.py
  python3 desktop_run.py --scale 3 --fps 30

Notes:
- This runner expects to live next to your project's app.py and game/ folder.
- It does NOT call systemctl poweroff; "shutdown" just exits the runner.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from PIL import Image, ImageDraw, ImageFont


def load_font(size: int):
    # Prefer a common system font; fallback to PIL default.
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


class DesktopDisp:
    def __init__(self, width: int = 240, height: int = 240):
        self.width = int(width)
        self.height = int(height)
        self._last: Optional[Image.Image] = None
        self._brightness = 100

    def ShowImage(self, img: Image.Image):
        self._last = img.copy()

    def bl_DutyCycle(self, duty: int):
        # Not really used on desktop; kept for compatibility.
        self._brightness = max(0, min(100, int(duty)))


class DesktopInputs:
    """Edge + held-state inputs driven by pygame keyboard events."""

    def __init__(self):
        self.state: Dict[str, bool] = {}

    def is_down(self, name: str) -> bool:
        return bool(self.state.get(name, False))

    def apply_key(self, name: str, is_down: bool, events: Dict[str, bool]):
        prev = bool(self.state.get(name, False))
        self.state[name] = bool(is_down)
        if (not prev) and is_down:
            events[name] = True
        elif prev and (not is_down):
            events[f"{name}_UP"] = True


@dataclass
class Ctx:
    disp: Any
    inputs: Any
    font_s: Any
    font_m: Any
    font_l: Any
    base_dir: str
    game_dir: str
    data_dir: str
    user: Dict[str, Any] = field(default_factory=dict)

    def asset(self, *parts: str) -> str:
        return os.path.join(self.game_dir, "assets", *parts)

    def data_path(self, *parts: str) -> str:
        return os.path.join(self.data_dir, *parts)

    def show(self, img: Image.Image):
        self.disp.ShowImage(img)

    def request_poweroff(self):
        # On desktop, poweroff just exits.
        raise SystemExit(0)


def reload_game_modules():
    """Reload all loaded modules under the 'game' package."""
    mods = [m for name, m in list(sys.modules.items()) if name == "game" or name.startswith("game.")]
    # Reload deeper modules first.
    mods_sorted = sorted(mods, key=lambda m: getattr(m, "__name__", ""), reverse=True)
    for m in mods_sorted:
        try:
            importlib.reload(m)
        except Exception:
            pass


def pil_to_surface(pg, img: Image.Image):
    # Ensure RGB
    if img.mode != "RGB":
        img = img.convert("RGB")
    data = img.tobytes()
    return pg.image.fromstring(data, img.size, "RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--w", type=int, default=240)
    ap.add_argument("--h", type=int, default=240)
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    # Lazy import pygame so your pip error is clearer.
    import pygame as pg

    pg.init()
    w, h = int(args.w), int(args.h)
    scale = max(1, int(args.scale))
    win = pg.display.set_mode((w * scale, h * scale))
    pg.display.set_caption("Pocket-R Desktop")
    clock = pg.time.Clock()

    base_dir = os.path.abspath(os.path.dirname(__file__))
    game_dir = os.path.join(base_dir, "game")
    if not os.path.isdir(game_dir):
        print("ERROR: couldn't find ./game next to desktop_run.py")
        print(f"Looked for: {game_dir}")
        return 2

    disp = DesktopDisp(w, h)
    inputs = DesktopInputs()
    data_dir = os.path.join(base_dir, ".pocketr")
    os.makedirs(data_dir, exist_ok=True)

    ctx = Ctx(
        disp=disp,
        inputs=inputs,
        font_s=load_font(14),
        font_m=load_font(18),
        font_l=load_font(24),
        base_dir=base_dir,
        game_dir=game_dir,
        data_dir=data_dir,
    )

    # Import game
    sys.path.insert(0, base_dir)
    game_main = importlib.import_module("game.main")
    if hasattr(game_main, "init"):
        game_main.init(ctx)

    # Key mapping
    KEYMAP = {
        pg.K_UP: "UP",
        pg.K_DOWN: "DOWN",
        pg.K_LEFT: "LEFT",
        pg.K_RIGHT: "RIGHT",
        pg.K_w: "UP",
        pg.K_s: "DOWN",
        pg.K_a: "LEFT",
        pg.K_d: "RIGHT",
        pg.K_RETURN: "PRESS",
        pg.K_SPACE: "PRESS",
        pg.K_1: "K1",
        pg.K_2: "K2",
        pg.K_3: "K3",
    }

    last = time.time()
    while True:
        now = time.time()
        dt = max(0.0001, now - last)
        last = now

        ev: Dict[str, bool] = {}

        for e in pg.event.get():
            if e.type == pg.QUIT:
                return 0
            if e.type in (pg.KEYDOWN, pg.KEYUP):
                key = e.key
                if key in (pg.K_ESCAPE, pg.K_q) and e.type == pg.KEYDOWN:
                    return 0
                if key == pg.K_r and e.type == pg.KEYDOWN:
                    # Hot reload all game modules
                    try:
                        reload_game_modules()
                        game_main = importlib.import_module("game.main")
                        ctx.user.clear()
                        if hasattr(game_main, "init"):
                            game_main.init(ctx)
                    except Exception as ex:
                        print("Reload failed:", ex)
                    continue

                name = KEYMAP.get(key)
                if name:
                    inputs.apply_key(name, e.type == pg.KEYDOWN, ev)

        # Update + render
        try:
            if hasattr(game_main, "update"):
                game_main.update(ctx, dt, ev)
            img = game_main.render(ctx)
        except SystemExit:
            return 0
        except Exception as ex:
            # Show exception on screen instead of crashing.
            img = Image.new("RGB", (w, h), (0, 0, 0))
            d = ImageDraw.Draw(img)
            d.text((8, 8), "CRASH", font=ctx.font_l, fill=(255, 80, 80))
            msg = str(ex)
            d.text((8, 46), msg[:200], font=ctx.font_s, fill=(220, 220, 220))

        # Present
        surf = pil_to_surface(pg, img)
        if scale != 1:
            surf = pg.transform.scale(surf, (w * scale, h * scale))
        win.blit(surf, (0, 0))
        pg.display.flip()

        clock.tick(int(args.fps))


if __name__ == "__main__":
    raise SystemExit(main())
