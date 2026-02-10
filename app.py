# -*- coding: utf-8 -*-
"""
Pocket-R Launcher (stable entrypoint for systemd)

Goal:
- Keep THIS file stable so your systemd autoboot never breaks.
- Put your real game in ./game/ (python files + assets).
- On the Pi: `git pull` + `sudo systemctl restart pocketr.service` to test.

Game contract (recommended):
- game/main.py exports:
    init(ctx)            # optional
    update(ctx, dt, ev)  # optional
    render(ctx) -> PIL.Image.Image  # REQUIRED for engine-driven mode

Engine features kept here:
- Hardware init (ST7789)
- Input edge events (joystick + K1/K2/K3)
- Global hold-to-shutdown (K3 hold -> systemctl poweroff)
- Frame pacing (FPS can be overridden by pocketr_settings.json)

If your game instead exports run(ctx) (custom loop), we'll call that, but then YOU must
implement hold-to-shutdown in your own loop using ctx.request_poweroff().
"""
import json
import os
import time
import subprocess
import traceback
import importlib
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, Tuple

from PIL import Image, ImageDraw, ImageFont

import ST7789

# --------- Hardware / UX defaults ---------
ROTATE_DEG = 270          # 0 / 90 / 180 / 270
ACTIVE_HIGH = False       # Typical pull-up buttons: pressed=0

FPS_DEFAULT = 15          # will be overridden by pocketr_settings.json if present
BACKLIGHT_DEFAULT = 60    # will be overridden by pocketr_settings.json if present

SHUTDOWN_HOLD_SECONDS = 3.0     # hold K3 to shut down
PREFS_FILE = "pocketr_settings.json"  # written by game/apps/settings.py
# -----------------------------------------


def clamp(v, lo=0, hi=100):
    return lo if v < lo else hi if v > hi else v


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


def pressed(raw: int) -> bool:
    return (raw != 0) if ACTIVE_HIGH else (raw == 0)


def rotate_if_needed(img: Image.Image) -> Image.Image:
    if ROTATE_DEG in (90, 180, 270):
        return img.rotate(ROTATE_DEG, expand=False)
    return img


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
    """Real Linux shutdown. A separate systemd shutdown hook can turn BL off at the end."""
    show_shutdown_screen(disp, font_title, font_body)

    try:
        os.sync()
    except Exception:
        pass

    try:
        subprocess.Popen(["/usr/bin/systemctl", "poweroff"])
    except Exception:
        subprocess.Popen(["/sbin/shutdown", "-h", "now"])

    while True:
        time.sleep(1)


class InputEdge:
    """Edge events for joystick/buttons using Waveshare pin constants on disp."""
    def __init__(self, disp):
        self.disp = disp
        self.state: Dict[str, bool] = {}
        self.map = {
            "UP": disp.GPIO_KEY_UP_PIN,
            "DOWN": disp.GPIO_KEY_DOWN_PIN,
            "LEFT": disp.GPIO_KEY_LEFT_PIN,
            "RIGHT": disp.GPIO_KEY_RIGHT_PIN,
            "PRESS": disp.GPIO_KEY_PRESS_PIN,  # joystick center
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
                events[name] = True
            elif prev and (not p):
                events[f"{name}_UP"] = True
        return events


@dataclass
class Ctx:
    disp: Any
    inputs: InputEdge
    font_s: Any
    font_m: Any
    font_l: Any
    base_dir: str
    game_dir: str
    user: Dict[str, Any] = field(default_factory=dict)

    # expose helpers to game
    def asset(self, *parts: str) -> str:
        """Absolute path to a file in ./game/assets/"""
        return os.path.join(self.game_dir, "assets", *parts)

    def show(self, img: Image.Image):
        """Show an image on the LCD with the configured rotation."""
        self.disp.ShowImage(rotate_if_needed(img))

    def request_poweroff(self):
        """Game can call this if it runs its own loop."""
        request_poweroff(self.disp, self.font_l, self.font_m)


def show_error_screen(disp, title: str, body: str, font_title, font_body):
    img = Image.new("RGB", (disp.width, disp.height), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), title, font=font_title, fill=(255, 80, 80))
    lines = wrap_text(draw, body, font_body, max_width=disp.width - 20)
    y = 45
    for line in lines[:10]:
        draw.text((10, y), line, font=font_body, fill=(255, 255, 255))
        y += 16
    disp.ShowImage(rotate_if_needed(img))


def _prefs_path(base_dir: str) -> str:
    return os.path.join(base_dir, PREFS_FILE)


def _load_prefs(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_runtime_settings(base_dir: str) -> Tuple[int, int]:
    """
    Returns (brightness, target_fps).
    Safe defaults when the prefs file doesn't exist.
    """
    prefs = _load_prefs(_prefs_path(base_dir))

    # brightness 0..100
    try:
        bl = int(clamp(float(prefs.get("brightness", BACKLIGHT_DEFAULT)), 0, 100))
    except Exception:
        bl = int(BACKLIGHT_DEFAULT)

    # target_fps 5..60 (engine uses 1/fps sleep)
    try:
        fps = int(clamp(float(prefs.get("target_fps", FPS_DEFAULT)), 5, 60))
    except Exception:
        fps = int(FPS_DEFAULT)

    return bl, fps


def run_engine(game_mod, ctx: Ctx):
    # optional init hook
    if hasattr(game_mod, "init"):
        game_mod.init(ctx)

    # K3 hold tracking (engine-level so it works even if the game crashes)
    k3_start: Optional[float] = None

    # Runtime settings hot-reload (file mtime)
    prefs_path = _prefs_path(ctx.base_dir)
    last_mtime: float = -1.0
    next_check: float = 0.0
    backlight = BACKLIGHT_DEFAULT
    fps_target = FPS_DEFAULT

    # apply initial persisted settings (if present)
    backlight, fps_target = _read_runtime_settings(ctx.base_dir)
    try:
        ctx.disp.bl_DutyCycle(int(backlight))
    except Exception:
        pass

    t_last = time.time()

    while True:
        now = time.time()
        dt = max(0.0, min(now - t_last, 0.2))
        t_last = now

        ev = ctx.inputs.update()

        # ---- engine-level hold-to-shutdown: K3 only ----
        if "K3" in ev:
            k3_start = now
        if "K3_UP" in ev:
            k3_start = None

        if k3_start is not None and ctx.inputs.is_down("K3"):
            held = now - k3_start
            if held >= SHUTDOWN_HOLD_SECONDS:
                ctx.request_poweroff()

            # optional: expose progress to the game if it wants it
            ctx.user["shutdown_holding"] = True
            ctx.user["shutdown_hold_seconds"] = held
            ctx.user["shutdown_hold_total"] = SHUTDOWN_HOLD_SECONDS
            ctx.user["shutdown_hold_key"] = "K3"
        else:
            ctx.user["shutdown_holding"] = False
            ctx.user["shutdown_hold_seconds"] = 0.0
            ctx.user["shutdown_hold_total"] = SHUTDOWN_HOLD_SECONDS
            ctx.user["shutdown_hold_key"] = "K3"

        # ---- hot reload persisted settings (brightness/fps) ----
        if now >= next_check:
            next_check = now + 0.5  # check twice per second
            try:
                mtime = os.path.getmtime(prefs_path)
            except Exception:
                mtime = -1.0

            if mtime != last_mtime:
                last_mtime = mtime
                bl, fps = _read_runtime_settings(ctx.base_dir)
                backlight = bl
                fps_target = fps
                try:
                    ctx.disp.bl_DutyCycle(int(backlight))
                except Exception:
                    pass

        if hasattr(game_mod, "update"):
            game_mod.update(ctx, dt, ev)

        if not hasattr(game_mod, "render"):
            raise RuntimeError("game/main.py must define render(ctx) -> PIL.Image")

        img = game_mod.render(ctx)
        if img is not None:
            ctx.show(img)

        # Frame pacing
        frame_time = time.time() - now
        time.sleep(max(0.0, (1.0 / max(1, int(fps_target))) - frame_time))


def main():
    # Absolute paths (never rely on cwd)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    game_dir = os.path.join(base_dir, "game")

    # Hardware init
    disp = ST7789.ST7789()
    disp.Init()
    disp.clear()

    # Apply persisted brightness immediately (if available)
    bl, _fps = _read_runtime_settings(base_dir)
    try:
        disp.bl_DutyCycle(int(bl))
    except Exception:
        disp.bl_DutyCycle(int(BACKLIGHT_DEFAULT))

    # Fonts + input
    font_s = load_font(12)
    font_m = load_font(16)
    font_l = load_font(22)
    inputs = InputEdge(disp)

    ctx = Ctx(
        disp=disp,
        inputs=inputs,
        font_s=font_s,
        font_m=font_m,
        font_l=font_l,
        base_dir=base_dir,
        game_dir=game_dir,
    )

    try:
        # Import the real game
        game_mod = importlib.import_module("game.main")

        # If game exports run(ctx), let it own the loop
        if hasattr(game_mod, "run") and not hasattr(game_mod, "render"):
            game_mod.run(ctx)
            return

        # Otherwise use the stable engine loop here
        run_engine(game_mod, ctx)

    except Exception as e:
        tb = traceback.format_exc()
        show_error_screen(disp, "GAME CRASH", str(e), font_l, font_s)
        # Also print to journalctl
        print(tb)
        time.sleep(5)
        raise
    finally:
        try:
            disp.clear()
            disp.module_exit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
