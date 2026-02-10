from __future__ import annotations

import importlib
import json
import os
import time
from dataclasses import dataclass
from typing import Dict

from PIL import Image, ImageDraw

from .ui_common import (
    breathe,
    ease_in_out,
    fade_from_black,
    load_image_or_blank,
    overlay_hold_progress,
)


# --- OS modes ---
MODE_INTRO = "INTRO"
MODE_HOME = "HOME"
MODE_APP = "APP"

# --- Tunables ---
PREFS_FILE = "pocketr_settings.json"  # stored beside app.py (ctx.base_dir)

INTRO_SECONDS = 7.5        # splash length (skippable by any input)
INTRO_FADE_SECONDS = 1.8   # fade-in duration
TRANSITION_SECONDS = 0.75  # crossfade between screens

K3_SHUTDOWN_HOLD = 3.0     # seconds to hold K3 to power off


@dataclass
class Assets:
    intro: Image.Image
    icons: Dict[int, Image.Image]


# Menu mapping (0..3 matches the 2x2 grid)
MENU_MODULES = {
    0: "game.apps.pet_game",   # Menu 1
    1: "game.apps.blank",      # Menu 2
    2: "game.apps.settings",   # Menu 3
    3: "game.apps.updater",    # Menu 4
}


def _size(ctx):
    return int(ctx.disp.width), int(ctx.disp.height)


def _layout(w: int, h: int):
    """Square-screen 2x2 layout. No bars on HOME."""
    pad = max(12, w // 20)
    cell = (w - pad * 3) // 2
    icon = max(24, cell - 6)
    grid_h = pad * 3 + cell * 2
    top = max(0, (h - grid_h) // 2)
    return pad, cell, icon, top


def _prefs_path(ctx) -> str:
    return os.path.join(getattr(ctx, "base_dir", "."), PREFS_FILE)


def _get_prefs(ctx) -> Dict:
    """Read prefs with lightweight mtime caching (used for FPS overlay, updater, etc)."""
    path = _prefs_path(ctx)
    try:
        st = os.stat(path)
        mtime = float(st.st_mtime)
    except Exception:
        mtime = -1.0

    cache = ctx.user.get("_prefs_cache", None)
    if isinstance(cache, dict) and cache.get("mtime") == mtime:
        return cache.get("prefs", {}) or {}

    prefs = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            prefs = json.load(f) or {}
        if not isinstance(prefs, dict):
            prefs = {}
    except Exception:
        prefs = {}

    ctx.user["_prefs_cache"] = {"mtime": mtime, "prefs": prefs}
    return prefs


def _load_assets(ctx):
    w, h = _size(ctx)
    key = f"{w}x{h}"
    if ctx.user.get("_assets_key") == key:
        return

    intro = load_image_or_blank(ctx.asset("ui", "intro.png"), (w, h), (0, 0, 0))

    pad, _cell, icon_sz, _top = _layout(w, h)
    icons: Dict[int, Image.Image] = {}
    for i in range(4):
        p = ctx.asset("ui", f"icon_{i+1}.png")
        icons[i] = load_image_or_blank(p, (icon_sz, icon_sz), (20, 20, 20))

    ctx.user["_assets"] = Assets(intro=intro, icons=icons)
    ctx.user["_assets_key"] = key


def init(ctx):
    _load_assets(ctx)

    ctx.user.setdefault("os_mode", MODE_INTRO)
    ctx.user.setdefault("os_selected", 0)
    ctx.user.setdefault("os_active_app", None)

    ctx.user["_intro_t0"] = time.time()
    ctx.user["_k3_hold_t0"] = None
    ctx.user["_k3_held"] = 0.0

    # Used for screen crossfades
    ctx.user["_transition"] = None
    ctx.user["_last_frame"] = None


def _start_transition(ctx):
    """Capture the last rendered frame for crossfading into the next mode."""
    last = ctx.user.get("_last_frame")
    if last is None:
        return
    ctx.user["_transition"] = {
        "t0": time.time(),
        "dur": float(TRANSITION_SECONDS),
        "from": last.convert("RGB"),
    }


def _switch_mode(ctx, new_mode: str, new_app: int | None = None):
    _start_transition(ctx)
    ctx.user["os_mode"] = new_mode
    ctx.user["os_active_app"] = new_app


def _update_k3_hold(ctx, now: float, ev: Dict[str, bool]):
    if "K3" in ev:
        ctx.user["_k3_hold_t0"] = now
    if "K3_UP" in ev:
        ctx.user["_k3_hold_t0"] = None
        ctx.user["_k3_held"] = 0.0

    t0 = ctx.user.get("_k3_hold_t0")
    if t0 is not None and ctx.inputs.is_down("K3"):
        held = now - float(t0)
        ctx.user["_k3_held"] = held
        if held >= K3_SHUTDOWN_HOLD:
            ctx.request_poweroff()
    else:
        ctx.user["_k3_held"] = 0.0


def _get_app_module(idx: int):
    mod_name = MENU_MODULES.get(idx)
    return importlib.import_module(mod_name) if mod_name else None


def update(ctx, dt: float, ev: Dict[str, bool]):
    _load_assets(ctx)
    now = time.time()

    # global K3 hold-to-shutdown
    _update_k3_hold(ctx, now, ev)

    mode = ctx.user.get("os_mode", MODE_INTRO)

    # INTRO
    if mode == MODE_INTRO:
        if (now - float(ctx.user.get("_intro_t0", now))) >= INTRO_SECONDS:
            _switch_mode(ctx, MODE_HOME, None)
            return
        # any input skips intro
        if ev:
            _switch_mode(ctx, MODE_HOME, None)
        return

    # HOME
    if mode == MODE_HOME:
        sel = int(ctx.user.get("os_selected", 0))
        r, c = divmod(sel, 2)

        if "UP" in ev:
            r = (r - 1) % 2
        if "DOWN" in ev:
            r = (r + 1) % 2
        if "LEFT" in ev:
            c = (c - 1) % 2
        if "RIGHT" in ev:
            c = (c + 1) % 2

        ctx.user["os_selected"] = r * 2 + c

        # K1 OR joystick PRESS = confirm/open
        if "K1" in ev or "PRESS" in ev:
            idx = int(ctx.user["os_selected"])
            _switch_mode(ctx, MODE_APP, idx)
            mod = _get_app_module(idx)
            if mod is not None and hasattr(mod, "init"):
                try:
                    mod.init(ctx)
                except Exception:
                    pass
        return

    # APP
    if mode == MODE_APP:
        idx = ctx.user.get("os_active_app")
        if idx is None:
            _switch_mode(ctx, MODE_HOME, None)
            return

        idx = int(idx)
        mod = _get_app_module(idx)
        if mod is None:
            _switch_mode(ctx, MODE_HOME, None)
            return

        # convention: app.update() returns True to go back
        if hasattr(mod, "update"):
            try:
                wants_back = bool(mod.update(ctx, dt, ev))
            except Exception:
                wants_back = True
            if wants_back:
                _switch_mode(ctx, MODE_HOME, None)
        else:
            if "K2" in ev:
                _switch_mode(ctx, MODE_HOME, None)
        return


def _overlay_fps(img: Image.Image, ctx) -> Image.Image:
    prefs = _get_prefs(ctx)
    if not bool(prefs.get("show_fps", False)):
        return img

    fps = float(ctx.user.get("_fps_smooth", 0.0) or 0.0)
    txt = f"{fps:.0f}fps"
    out = img.convert("RGB")
    d = ImageDraw.Draw(out)
    tw = int(d.textlength(txt, font=ctx.font_s))
    d.rectangle([out.width - tw - 10, 2, out.width - 2, 18], fill=(0, 0, 0))
    d.text((out.width - tw - 6, 4), txt, font=ctx.font_s, fill=(200, 200, 200))
    return out


def _render_intro(ctx, assets: Assets) -> Image.Image:
    w, h = _size(ctx)
    t = time.time() - float(ctx.user.get("_intro_t0", time.time()))

    fade = ease_in_out(min(1.0, t / max(0.001, INTRO_FADE_SECONDS)))
    img = fade_from_black(assets.intro, fade).convert("RGB")

    # subtle animated 3-dot loader (no "Starting" text)
    d = ImageDraw.Draw(img)
    y = h - 20
    cx = w // 2
    spacing = 12
    phase = int((t * 2.2) % 4)  # 0..3
    for i in range(3):
        x = cx + (i - 1) * spacing
        on = i < phase
        r = 3 + int(2 * breathe(t + i * 0.18, 1.4))
        col = (230, 230, 230) if on else (90, 90, 95)
        d.ellipse([x - r, y - r, x + r, y + r], fill=col)

    return img


def _render_home(ctx, assets: Assets) -> Image.Image:
    w, h = _size(ctx)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)

    pad, cell, icon_sz, top = _layout(w, h)
    sel = int(ctx.user.get("os_selected", 0))

    for i in range(4):
        r, c = divmod(i, 2)
        x = pad + c * (cell + pad)
        y = top + pad + r * (cell + pad)

        d.rectangle([x, y, x + cell, y + cell], outline=(70, 70, 70, 255), width=2)

        icon = assets.icons.get(i)
        if icon is not None:
            ix = x + (cell - icon_sz) // 2
            iy = y + (cell - icon_sz) // 2
            img.paste(icon, (ix, iy), icon)

        if i == sel:
            d.rectangle([x - 2, y - 2, x + cell + 2, y + cell + 2], outline=(255, 255, 255, 255), width=3)

    return img.convert("RGB")


def _render_app(ctx) -> Image.Image:
    w, h = _size(ctx)
    idx = ctx.user.get("os_active_app")
    if idx is None:
        return Image.new("RGB", (w, h), (0, 0, 0))

    idx = int(idx)
    mod = _get_app_module(idx)
    if mod is None or not hasattr(mod, "render"):
        img = Image.new("RGB", (w, h), (0, 0, 0))
        d = ImageDraw.Draw(img)
        d.text((12, 12), "App missing", font=ctx.font_l, fill=(255, 80, 80))
        d.text((12, 48), "K2 to go back", font=ctx.font_m, fill=(220, 220, 220))
        return img

    try:
        return mod.render(ctx)
    except Exception:
        img = Image.new("RGB", (w, h), (0, 0, 0))
        d = ImageDraw.Draw(img)
        d.text((12, 12), "App crashed", font=ctx.font_l, fill=(255, 80, 80))
        d.text((12, 48), "K2 to go back", font=ctx.font_m, fill=(220, 220, 220))
        return img


def render(ctx) -> Image.Image:
    _load_assets(ctx)
    assets: Assets = ctx.user.get("_assets")

    mode = ctx.user.get("os_mode", MODE_INTRO)

    if mode == MODE_INTRO:
        img = _render_intro(ctx, assets)
    elif mode == MODE_HOME:
        img = _render_home(ctx, assets)
    elif mode == MODE_APP:
        img = _render_app(ctx)
    else:
        w, h = _size(ctx)
        img = Image.new("RGB", (w, h), (0, 0, 0))

    # Overlay hold-to-shutdown progress (K3)
    held = float(ctx.user.get("_k3_held", 0.0) or 0.0)
    if held > 0:
        img = overlay_hold_progress(img, "Hold K3 to shutdown", held, K3_SHUTDOWN_HOLD, ctx.font_s)

    # Optional FPS overlay
    img = _overlay_fps(img, ctx)

    # Crossfade transition if active
    tr = ctx.user.get("_transition")
    if isinstance(tr, dict) and tr.get("from") is not None:
        t0 = float(tr.get("t0", 0.0))
        dur = max(0.001, float(tr.get("dur", TRANSITION_SECONDS)))
        p = (time.time() - t0) / dur
        if p >= 1.0:
            ctx.user["_transition"] = None
        else:
            a = ease_in_out(p)
            try:
                img = Image.blend(tr["from"].convert("RGB"), img.convert("RGB"), a)
            except Exception:
                pass

    ctx.user["_last_frame"] = img
    return img
