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
- Global hold-to-shutdown (hold K3 -> poweroff)
- Frame pacing (target FPS from Settings)
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from PIL import Image, ImageDraw, ImageFont

import ST7789


# --------- Hardware / UX settings ---------
ROTATE_DEG = 270          # 0 / 90 / 180 / 270
ACTIVE_HIGH = False       # Typical pull-up buttons: pressed=0
FPS = 15                  # Default target FPS (can be changed in Settings)
BACKLIGHT = 60            # Default backlight 0-100 (can be changed in Settings)
SHUTDOWN_HOLD_SECONDS = 3.0
SHUTDOWN_OVERLAY_DELAY = 0.45

DEFAULT_DATA_DIR = "/root/.pocketr"
LEGACY_SETTINGS_FILE = "pocketr_settings.json"
SETTINGS_REL_PATH = "settings.json"
SETTINGS_POLL_SECONDS = 0.5
# -----------------------------------------


def clamp(v, lo=0, hi=100):
    return lo if v < lo else hi if v > hi else v


def _safe_mkdir(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception:
        return False


def _resolve_data_dir(base_dir: str) -> str:
    env = str(os.environ.get("POCKETR_DATA_DIR", "") or "").strip()
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return DEFAULT_DATA_DIR


def _legacy_settings_path(base_dir: str) -> str:
    return os.path.join(base_dir, LEGACY_SETTINGS_FILE)


def _settings_path(ctx: "Ctx") -> str:
    if hasattr(ctx, "data_path"):
        return ctx.data_path(SETTINGS_REL_PATH)
    return _legacy_settings_path(ctx.base_dir)


def _load_settings(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _apply_settings(ctx: "Ctx", settings: Dict[str, Any]) -> None:
    try:
        b = int(clamp(float(settings.get("brightness", BACKLIGHT)), 0, 100))
    except Exception:
        b = BACKLIGHT

    try:
        tfps = int(clamp(float(settings.get("target_fps", FPS)), 5, 60))
    except Exception:
        tfps = FPS

    ctx.user["brightness"] = b
    ctx.user["target_fps"] = tfps

    try:
        ctx.disp.bl_DutyCycle(int(b))
    except Exception:
        pass


def _maybe_reload_settings(ctx: "Ctx", now: float) -> None:
    st = ctx.user.get("_settings_state")
    if not isinstance(st, dict):
        st = {"last": 0.0, "mtime": -1.0}
        ctx.user["_settings_state"] = st

    if (now - float(st.get("last", 0.0))) < SETTINGS_POLL_SECONDS:
        return
    st["last"] = now

    path = _settings_path(ctx)
    try:
        mtime = float(os.path.getmtime(path))
    except Exception:
        mtime = -1.0

    if mtime == float(st.get("mtime", -2.0)):
        return
    st["mtime"] = mtime

    data = _load_settings(path) if mtime > 0 else {}
    ctx.user["_prefs"] = data
    _apply_settings(ctx, data)


def _migrate_legacy_settings(base_dir: str, data_dir: str) -> None:
    legacy = _legacy_settings_path(base_dir)
    target = os.path.join(data_dir, SETTINGS_REL_PATH)

    if not os.path.isfile(legacy):
        return
    if os.path.isfile(target):
        return

    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(legacy, target)
    except Exception:
        pass


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
    data_dir: str
    user: Dict[str, Any] = field(default_factory=dict)

    def asset(self, *parts: str) -> str:
        """Absolute path to a file in ./game/assets/."""
        return os.path.join(self.game_dir, "assets", *parts)

    def data_path(self, *parts: str) -> str:
        """Absolute path to a file in persistent data directory."""
        return os.path.join(self.data_dir, *parts)

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


def run_engine(game_mod, ctx: Ctx):
    if hasattr(game_mod, "init"):
        game_mod.init(ctx)

    k3_start: Optional[float] = None
    t_last = time.time()

    while True:
        now = time.time()
        dt = max(0.0, min(now - t_last, 0.2))
        t_last = now

        ev = ctx.inputs.update()

        # live settings (fps + backlight)
        _maybe_reload_settings(ctx, now)

        # global hold-to-shutdown (K3)
        if "K3" in ev:
            k3_start = now
        if "K3_UP" in ev:
            k3_start = None

        if k3_start is not None and ctx.inputs.is_down("K3"):
            held = now - k3_start
            if held >= SHUTDOWN_HOLD_SECONDS:
                ctx.request_poweroff()

            ctx.user["shutdown_holding"] = held >= SHUTDOWN_OVERLAY_DELAY
            ctx.user["shutdown_hold_seconds"] = held
        else:
            ctx.user["shutdown_holding"] = False
            ctx.user["shutdown_hold_seconds"] = 0.0

        if dt > 0.0001:
            inst = 1.0 / dt
            prev = float(ctx.user.get("_fps_smooth", inst) or inst)
            ctx.user["_fps_smooth"] = prev * 0.90 + inst * 0.10

        if hasattr(game_mod, "update"):
            game_mod.update(ctx, dt, ev)

        if not hasattr(game_mod, "render"):
            raise RuntimeError("game/main.py must define render(ctx) -> PIL.Image")

        img = game_mod.render(ctx)
        if img is not None:
            prefs = ctx.user.get("_prefs", {})
            if isinstance(prefs, dict) and prefs.get("show_fps", False):
                try:
                    d = ImageDraw.Draw(img)
                    fps_live = float(ctx.user.get("_fps_smooth", 0.0) or 0.0)
                    label = f"{fps_live:.1f} fps"
                    tw = int(d.textlength(label, font=ctx.font_s))
                    d.text((max(2, img.width - 2 - tw), 2), label, font=ctx.font_s, fill=(255, 255, 255))
                except Exception:
                    pass
            ctx.show(img)

        target_fps = float(ctx.user.get("target_fps", FPS) or FPS)
        target_fps = max(5.0, min(60.0, target_fps))
        frame_time = time.time() - now
        time.sleep(max(0.0, (1.0 / target_fps) - frame_time))


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    game_dir = os.path.join(base_dir, "game")

    data_dir = _resolve_data_dir(base_dir)
    if not _safe_mkdir(data_dir):
        fallback = os.path.join(base_dir, ".pocketr")
        _safe_mkdir(fallback)
        data_dir = fallback

    _migrate_legacy_settings(base_dir, data_dir)

    disp = ST7789.ST7789()
    disp.Init()
    disp.clear()
    disp.bl_DutyCycle(BACKLIGHT)

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
        data_dir=data_dir,
    )

    _maybe_reload_settings(ctx, time.time())

    try:
        game_mod = importlib.import_module("game.main")

        if hasattr(game_mod, "run") and not hasattr(game_mod, "render"):
            game_mod.run(ctx)
            return

        run_engine(game_mod, ctx)

    except Exception as e:
        tb = traceback.format_exc()
        show_error_screen(disp, "GAME CRASH", str(e), font_l, font_s)
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
