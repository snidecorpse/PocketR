from __future__ import annotations

import importlib
import time
from dataclasses import dataclass
from typing import Dict, Optional

from PIL import Image, ImageDraw

from .ui_common import load_image_or_blank, overlay_hold_progress


# --- OS modes ---
MODE_INTRO = "INTRO"
MODE_HOME = "HOME"
MODE_APP = "APP"

# --- Tunables ---
INTRO_SECONDS = 3.5      # longer splash per your request
K3_SHUTDOWN_HOLD = 3.0   # seconds to hold K3 to power off


@dataclass
class Assets:
    intro: Image.Image
    icons: Dict[int, Image.Image]


# Menu mapping (0..3 matches the 2x2 grid)
MENU_MODULES = {
    0: "game.apps.pet_game",
    1: "game.apps.blank",
    2: "game.apps.settings",
    3: "game.apps.updater",
}


def _size(ctx):
    return int(ctx.disp.width), int(ctx.disp.height)


def _layout(w: int, h: int):
    """Match the earlier panel sizing (no top/bottom bars)."""
    pad = max(12, w // 20)
    cell = (w - pad * 3) // 2
    icon = max(24, cell - 6)  # previous version was 96 inside a 102 cell
    # If not perfectly square, center vertically
    grid_h = pad * 3 + cell * 2
    top = max(0, (h - grid_h) // 2)
    return pad, cell, icon, top


def _load_assets(ctx):
    # Cache assets once per boot (and per display size)
    w, h = _size(ctx)
    key = f"{w}x{h}"
    if ctx.user.get("_assets_key") == key:
        return

    intro = load_image_or_blank(ctx.asset("ui", "intro.png"), (w, h), (0, 0, 0))

    pad, cell, icon_sz, _top = _layout(w, h)

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

    # K3 hold tracking
    ctx.user["_k3_hold_t0"] = None
    ctx.user["_k3_held"] = 0.0


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
    if not mod_name:
        return None
    return importlib.import_module(mod_name)


def _ensure_app_inited(ctx, idx: int):
    init_key = f"_app_inited_{idx}"
    if ctx.user.get(init_key):
        return
    mod = _get_app_module(idx)
    if mod and hasattr(mod, "init"):
        try:
            mod.init(ctx)
        except Exception:
            # app init failures should not crash the whole OS
            pass
    ctx.user[init_key] = True


def update(ctx, dt: float, ev: Dict[str, bool]):
    _load_assets(ctx)
    now = time.time()

    # global K3 hold-to-shutdown
    _update_k3_hold(ctx, now, ev)

    mode = ctx.user.get("os_mode", MODE_INTRO)

    # INTRO
    if mode == MODE_INTRO:
        if (now - float(ctx.user.get("_intro_t0", now))) >= INTRO_SECONDS:
            ctx.user["os_mode"] = MODE_HOME
            return
        # any input skips intro (K1/K2/dpad/press)
        if ev:
            ctx.user["os_mode"] = MODE_HOME
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

        # K1 = confirm/open (PER YOUR REQUEST)
        if "K1" in ev:
            idx = int(ctx.user["os_selected"])
            ctx.user["os_active_app"] = idx
            ctx.user["os_mode"] = MODE_APP
            _ensure_app_inited(ctx, idx)
        return

    # APP
    if mode == MODE_APP:
        idx = ctx.user.get("os_active_app")
        if idx is None:
            ctx.user["os_mode"] = MODE_HOME
            return

        idx = int(idx)
        mod = _get_app_module(idx)
        if mod is None:
            ctx.user["os_mode"] = MODE_HOME
            ctx.user["os_active_app"] = None
            return

        # Let the app decide back behavior; convention: update() returns True to go back
        if hasattr(mod, "update"):
            try:
                wants_back = bool(mod.update(ctx, dt, ev))
            except Exception:
                wants_back = True
            if wants_back:
                ctx.user["os_mode"] = MODE_HOME
                ctx.user["os_active_app"] = None
        else:
            # no update() => allow K2 to back
            if "K2" in ev:
                ctx.user["os_mode"] = MODE_HOME
                ctx.user["os_active_app"] = None
        return


def render(ctx) -> Image.Image:
    _load_assets(ctx)
    assets: Assets = ctx.user.get("_assets")
    w, h = _size(ctx)

    mode = ctx.user.get("os_mode", MODE_INTRO)

    # INTRO
    if mode == MODE_INTRO:
        img = assets.intro.copy().convert("RGB")
        held = float(ctx.user.get("_k3_held", 0.0))
        if held > 0:
            img = overlay_hold_progress(img, "Hold K3 to shutdown", held, K3_SHUTDOWN_HOLD, ctx.font_s)
        return img

    # HOME
    if mode == MODE_HOME:
        img = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        d = ImageDraw.Draw(img)

        pad, cell, icon_sz, top = _layout(w, h)
        sel = int(ctx.user.get("os_selected", 0))

        for i in range(4):
            r, c = divmod(i, 2)
            x = pad + c * (cell + pad)
            y = top + pad + r * (cell + pad)

            # panel
            d.rectangle([x, y, x + cell, y + cell], outline=(70, 70, 70, 255), width=2)

            # icon (centered)
            icon = assets.icons.get(i)
            if icon is not None:
                ix = x + (cell - icon_sz) // 2
                iy = y + (cell - icon_sz) // 2
                img.paste(icon, (ix, iy), icon)

            if i == sel:
                d.rectangle([x - 2, y - 2, x + cell + 2, y + cell + 2], outline=(255, 255, 255, 255), width=3)

        out = img.convert("RGB")
        held = float(ctx.user.get("_k3_held", 0.0))
        if held > 0:
            out = overlay_hold_progress(out, "Hold K3 to shutdown", held, K3_SHUTDOWN_HOLD, ctx.font_s)
        return out

    # APP
    if mode == MODE_APP:
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
            img = mod.render(ctx)
        except Exception:
            img = Image.new("RGB", (w, h), (0, 0, 0))
            d = ImageDraw.Draw(img)
            d.text((12, 12), "App crashed", font=ctx.font_l, fill=(255, 80, 80))
            d.text((12, 48), "K2 to go back", font=ctx.font_m, fill=(220, 220, 220))

        held = float(ctx.user.get("_k3_held", 0.0))
        if held > 0:
            img = overlay_hold_progress(img, "Hold K3 to shutdown", held, K3_SHUTDOWN_HOLD, ctx.font_s)
        return img

    # fallback
    return Image.new("RGB", (w, h), (0, 0, 0))
