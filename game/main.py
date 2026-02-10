# -*- coding: utf-8 -*-
"""
Pocket-R "Main OS" (game layer)

Features implemented here (inside /game):
- Intro splash (game/assets/ui/intro.png) -> auto-advance or PRESS to skip
- Home screen with 4 icons (2x2), D-pad navigation, PRESS to open
- Global K3 hold-to-shutdown (calls ctx.request_poweroff())

Why shutdown here?
Your launcher (app.py) currently triggers shutdown on PRESS hold, but you said you
only copy the /game folder. This file adds K3 shutdown in the game layer.

NOTE:
- If you want to DISABLE the PRESS-hold shutdown entirely, you must change app.py
  (engine-level). See notes in the README section at bottom of this file.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageOps

from .ui import fit_image, draw_progress_bar, center_text, wrap_text


# ---- Tuning knobs ----
INTRO_SECONDS = 1.6          # auto-advance after this time (PRESS skips instantly)
K3_SHUTDOWN_HOLD = 3.0       # seconds to hold K3 before shutdown
GRID_PAD = 10                # padding around icons
GAP = 10                     # gap between icons
TOPBAR_H = 34
# ----------------------


@dataclass
class HomeState:
    selected: int = 0         # 0..3
    page: int = 0             # reserved for future "pages" with K1/K2 (stub)
    opened_app: Optional[int] = None  # 0..3 when inside app, None when on home


def _size(ctx) -> Tuple[int, int]:
    return (int(ctx.disp.width), int(ctx.disp.height))


def _load_assets(ctx):
    # cache images in ctx.user to avoid reloading each frame
    if "_assets_loaded" in ctx.user:
        return

    w, h = _size(ctx)

    intro_path = ctx.asset("ui", "intro.png")
    try:
        ctx.user["_intro_img"] = fit_image(intro_path, (w, h))
    except Exception:
        # fallback: blank screen
        ctx.user["_intro_img"] = Image.new("RGB", (w, h), (0, 0, 0))

    icons = []
    for i in range(4):
        p = ctx.asset("ui", f"icon_{i}.png")
        try:
            icons.append(fit_image(p, (120, 120)))
        except Exception:
            icons.append(Image.new("RGB", (120, 120), (30, 30, 35)))

    ctx.user["_icons"] = icons
    ctx.user["_assets_loaded"] = True


def init(ctx):
    _load_assets(ctx)
    ctx.user["_boot_t0"] = time.time()
    ctx.user["screen"] = "INTRO"  # INTRO -> HOME -> APP
    ctx.user["home"] = HomeState().__dict__

    # K3 hold tracking
    ctx.user["_k3_hold_t0"] = None
    ctx.user["_k3_held_secs"] = 0.0


def _home_state(ctx) -> HomeState:
    d = ctx.user.get("home", {})
    return HomeState(**d)


def _set_home_state(ctx, hs: HomeState):
    ctx.user["home"] = hs.__dict__


def _update_k3_shutdown(ctx, now: float, ev: Dict[str, bool]):
    """
    Hold K3 for K3_SHUTDOWN_HOLD seconds to shutdown.
    Works in all screens.
    """
    if "K3" in ev:
        ctx.user["_k3_hold_t0"] = now

    if "K3_UP" in ev:
        ctx.user["_k3_hold_t0"] = None
        ctx.user["_k3_held_secs"] = 0.0

    t0 = ctx.user.get("_k3_hold_t0", None)

    if t0 is not None and ctx.inputs.is_down("K3"):
        held = now - t0
        ctx.user["_k3_held_secs"] = held
        if held >= K3_SHUTDOWN_HOLD:
            # Call into launcher helper (does safe system poweroff screen + systemctl)
            ctx.request_poweroff()
    else:
        ctx.user["_k3_held_secs"] = 0.0


def update(ctx, dt: float, ev: Dict[str, bool]):
    _load_assets(ctx)
    now = time.time()

    # global K3 hold-to-shutdown
    _update_k3_shutdown(ctx, now, ev)

    screen = ctx.user.get("screen", "INTRO")

    # 1) Intro screen
    if screen == "INTRO":
        # PRESS skips
        if "PRESS" in ev:
            ctx.user["screen"] = "HOME"
            return

        # auto-advance
        if now - float(ctx.user.get("_boot_t0", now)) >= INTRO_SECONDS:
            ctx.user["screen"] = "HOME"
        return

    # 2) Home screen + apps
    hs = _home_state(ctx)

    if hs.opened_app is None:
        # Home navigation
        r, c = divmod(hs.selected, 2)

        if "UP" in ev and r > 0:
            r -= 1
        if "DOWN" in ev and r < 1:
            r += 1
        if "LEFT" in ev and c > 0:
            c -= 1
        if "RIGHT" in ev and c < 1:
            c += 1

        hs.selected = r * 2 + c

        if "PRESS" in ev:
            hs.opened_app = hs.selected

        # Reserved: page toggles (safe stubs)
        if "K1" in ev:
            hs.page = (hs.page - 1) % 3
        if "K2" in ev:
            hs.page = (hs.page + 1) % 3

        _set_home_state(ctx, hs)
        return

    else:
        # In an "app"
        if "K1" in ev or "K2" in ev:
            hs.opened_app = None
            _set_home_state(ctx, hs)
            return


def _render_topbar(ctx, draw: ImageDraw.ImageDraw, title: str):
    w, h = _size(ctx)
    draw.rectangle([0, 0, w, TOPBAR_H], fill=(18, 18, 22))
    draw.line([0, TOPBAR_H, w, TOPBAR_H], fill=(50, 50, 60), width=1)
    draw.text((10, 8), title, font=ctx.font_m, fill=(240, 240, 245))


def _render_k3_overlay(ctx, img: Image.Image):
    held = float(ctx.user.get("_k3_held_secs", 0.0))
    if held <= 0.0:
        return

    w, h = img.size
    draw = ImageDraw.Draw(img)

    # translucent-ish overlay (simulate by dark rect)
    box_h = 62
    y0 = h - box_h - 10
    draw.rounded_rectangle([10, y0, w - 10, y0 + box_h], radius=14, fill=(10, 10, 12), outline=(60, 60, 70), width=2)
    draw.text((22, y0 + 10), "Hold K3 to shut down", font=ctx.font_s, fill=(230, 230, 235))

    p = min(1.0, held / K3_SHUTDOWN_HOLD)
    draw_progress_bar(draw, 22, y0 + 30, w - 44, 20, p)


def render(ctx) -> Image.Image:
    _load_assets(ctx)
    w, h = _size(ctx)

    screen = ctx.user.get("screen", "INTRO")

    if screen == "INTRO":
        img = ctx.user.get("_intro_img").copy()
        # small hint
        draw = ImageDraw.Draw(img)
        draw.text((10, h - 22), "PRESS to skip", font=ctx.font_s, fill=(220, 220, 230))
        _render_k3_overlay(ctx, img)
        return img

    # HOME / APP
    img = Image.new("RGB", (w, h), (12, 12, 15))
    draw = ImageDraw.Draw(img)

    hs = _home_state(ctx)
    icons = ctx.user.get("_icons", [])

    if hs.opened_app is None:
        _render_topbar(ctx, draw, f"Home  •  Page {hs.page + 1}")

        # 2x2 grid layout
        # Available square region below topbar
        y_top = TOPBAR_H + GRID_PAD
        avail_h = h - y_top - GRID_PAD
        avail_w = w - 2 * GRID_PAD

        cell_w = (avail_w - GAP) // 2
        cell_h = (avail_h - GAP) // 2
        icon_size = min(cell_w, cell_h)

        for i in range(4):
            r, c = divmod(i, 2)
            x0 = GRID_PAD + c * (cell_w + GAP) + (cell_w - icon_size) // 2
            y0 = y_top + r * (cell_h + GAP) + (cell_h - icon_size) // 2

            # draw icon bg
            draw.rounded_rectangle([x0, y0, x0 + icon_size, y0 + icon_size], radius=18, fill=(22, 22, 28))

            # paste icon image
            if i < len(icons):
                icon = icons[i].resize((icon_size, icon_size))
                img.paste(icon, (x0, y0))

            # selection highlight
            if i == hs.selected:
                draw.rounded_rectangle([x0 - 3, y0 - 3, x0 + icon_size + 3, y0 + icon_size + 3],
                                      radius=20, outline=(240, 240, 245), width=3)

        # footer hints
        draw.text((10, h - 22), "D-pad: move   PRESS: open   K3: hold power", font=ctx.font_s, fill=(170, 170, 180))
        _render_k3_overlay(ctx, img)
        return img

    # App screen
    app_i = int(hs.opened_app)
    _render_topbar(ctx, draw, f"App {app_i + 1}")

    msg = "Placeholder screen.\nK1 or K2 to go back."
    lines = msg.splitlines()
    y = TOPBAR_H + 30
    for line in lines:
        draw.text((18, y), line, font=ctx.font_m, fill=(235, 235, 240))
        y += 24

    # show which icon was launched
    draw.rounded_rectangle([18, y + 10, w - 18, y + 106], radius=18, outline=(70, 70, 80), width=2)
    draw.text((28, y + 22), "You can map these to:", font=ctx.font_s, fill=(180, 180, 190))
    items = ["Messages", "Stats / Care", "Mini-games", "Settings"]
    yy = y + 44
    for t in items:
        draw.text((28, yy), f"• {t}", font=ctx.font_s, fill=(210, 210, 220))
        yy += 18

    _render_k3_overlay(ctx, img)
    return img


# --------------------------
# ENGINE NOTE (IMPORTANT)
# --------------------------
# Your launcher currently shuts down on PRESS hold (center joystick) at the engine level.
# That logic lives in app.py:
#   SHUTDOWN_HOLD_SECONDS = 10.0
#   and it watches "PRESS" in run_engine(...)
#
# If you want ONLY K3 to shutdown (and NOT PRESS), you must change app.py:
#   - Replace "PRESS" references in the global hold-to-shutdown section with "K3"
#   - Or disable it completely and rely on this game-layer K3 hold instead.
#
# You said you only copy /game, so we implemented K3 hold here, but PRESS-hold will still exist
# until app.py is updated.
