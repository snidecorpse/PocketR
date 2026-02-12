from __future__ import annotations

import importlib
import time
from dataclasses import dataclass
from typing import Dict, Optional

from PIL import Image, ImageChops, ImageDraw

from .ui_common import (
    app_background,
    breathe,
    dots,
    ease_in_out,
    fade_from_black,
    load_image_or_blank,
    overlay_hold_progress,
)


# --- OS modes ---
MODE_INTRO = "INTRO"
MODE_INTRO_OUT = "INTRO_OUT"
MODE_HOME = "HOME"
MODE_APP = "APP"

# --- Tunables ---
INTRO_SECONDS = 8.0          # longer splash
INTRO_FADE_IN_SECONDS = 1.2  # fade-in duration
INTRO_FADE_OUT_SECONDS = 1.6 # transition to HOME
HOME_FADE_IN_SECONDS = 1.0   # transition from black into HOME
K3_SHUTDOWN_HOLD = 3.0    # seconds to hold K3 to power off
K3_OVERLAY_SHOW_DELAY = 0.45


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
    """Square-screen 2x2 layout. No bars on HOME."""
    pad = max(12, w // 20)
    cell = (w - pad * 3) // 2
    icon = max(24, cell - 6)
    grid_h = pad * 3 + cell * 2
    top = max(0, (h - grid_h) // 2)
    return pad, cell, icon, top


def _load_assets(ctx):
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
    ctx.user["_intro_out_t0"] = None
    ctx.user["_home_t0"] = None

    # K3 hold tracking
    ctx.user["_k3_hold_t0"] = None
    ctx.user["_k3_held"] = 0.0

    # FPS smoothing (for optional overlay in apps)
    ctx.user.setdefault("_fps_smooth", 0.0)


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


def _square_point(x0: int, y0: int, x1: int, y1: int, dist: float):
    """Point along a rectangle perimeter, clockwise from top-left."""
    top = max(1.0, float(x1 - x0))
    side = max(1.0, float(y1 - y0))
    perim = 2.0 * (top + side)
    d = dist % perim

    if d < top:
        return (x0 + d, y0)
    d -= top
    if d < side:
        return (x1, y0 + d)
    d -= side
    if d < top:
        return (x1 - d, y1)
    d -= top
    return (x0, y1 - d)


def _draw_square_intro_ring(base: Image.Image, t: float, pad: int) -> Image.Image:
    w, h = base.size
    x0, y0 = pad, pad
    x1, y1 = w - pad - 1, h - pad - 1

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    pulse = breathe(t, 1.25)

    # Thicker outward pulsing glow near screen edges.
    for i, grow in enumerate((8, 5, 3, 1, 0)):
        alpha = int((30 + 75 * pulse) * (1.0 - (i * 0.16)))
        width = max(1, 5 - i)
        d.rounded_rectangle(
            [x0 - grow, y0 - grow, x1 + grow, y1 + grow],
            radius=max(10, 24 + grow),
            outline=(255, 235, 215, max(18, alpha)),
            width=width,
        )

    top = max(1.0, float(x1 - x0))
    side = max(1.0, float(y1 - y0))
    perim = 2.0 * (top + side)

    head = (t * 260.0) % perim
    trail = perim * 0.40

    outer_w = max(10, w // 18)
    inner_w = max(5, outer_w - 5)
    steps = 120

    for i in range(steps):
        f0 = i / float(steps)
        f1 = (i + 1) / float(steps)

        p0 = _square_point(x0, y0, x1, y1, head - (trail * f0))
        p1 = _square_point(x0, y0, x1, y1, head - (trail * f1))
        strength = 1.0 - f0

        a_outer = int((50 + 80 * pulse) * strength)
        a_inner = int((95 + 125 * pulse) * strength)

        d.line([p0, p1], fill=(255, 210, 170, max(6, a_outer)), width=outer_w)
        d.line([p0, p1], fill=(255, 245, 230, max(8, a_inner)), width=inner_w)

    return Image.alpha_composite(base, overlay)


def _draw_pulse_ring(
    img: Image.Image,
    rect: tuple[int, int, int, int],
    radius: int,
    thickness: int,
    color: tuple[int, int, int],
    alpha: int,
) -> Image.Image:
    """Draw a contiguous rounded-rect ring (no segmented outline artifacts)."""
    x0, y0, x1, y1 = rect
    if x1 <= x0 or y1 <= y0:
        return img

    a = max(0, min(255, int(alpha)))
    if a <= 0:
        return img

    r = max(0, int(radius))
    t = max(1, int(thickness))
    outer_mask = Image.new("L", img.size, 0)
    d_outer = ImageDraw.Draw(outer_mask)
    d_outer.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=255)

    inner_mask = Image.new("L", img.size, 0)
    ix0 = x0 + t
    iy0 = y0 + t
    ix1 = x1 - t
    iy1 = y1 - t
    if ix1 > ix0 and iy1 > iy0:
        d_inner = ImageDraw.Draw(inner_mask)
        d_inner.rounded_rectangle([ix0, iy0, ix1, iy1], radius=max(0, r - t), fill=255)

    ring_mask = ImageChops.subtract(outer_mask, inner_mask)
    ring_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ring_layer.paste((color[0], color[1], color[2], a), (0, 0, img.size[0], img.size[1]), ring_mask)
    return Image.alpha_composite(img, ring_layer)



def update(ctx, dt: float, ev: Dict[str, bool]):
    _load_assets(ctx)
    now = time.time()

    # FPS smoothing (used by Settings UI if enabled)
    if dt > 0:
        inst = 1.0 / dt
        prev = float(ctx.user.get("_fps_smooth", 0.0))
        ctx.user["_fps_smooth"] = (prev * 0.90) + (inst * 0.10) if prev > 0 else inst

    # global K3 hold-to-shutdown
    _update_k3_hold(ctx, now, ev)

    mode = ctx.user.get("os_mode", MODE_INTRO)

    # INTRO
    if mode == MODE_INTRO:
        t = now - float(ctx.user.get("_intro_t0", now))
        # Start a smoother transition either after timeout or when user interacts
        if t >= INTRO_SECONDS or (ev and t >= 0.6):
            ctx.user["os_mode"] = MODE_INTRO_OUT
            ctx.user["_intro_out_t0"] = now
        return

    # INTRO -> HOME transition
    if mode == MODE_INTRO_OUT:
        t = now - float(ctx.user.get("_intro_out_t0", now))
        if t >= INTRO_FADE_OUT_SECONDS:
            ctx.user["os_mode"] = MODE_HOME
            ctx.user["_home_t0"] = now
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
            ctx.user["os_active_app"] = idx
            ctx.user["os_mode"] = MODE_APP
            # init app on every entry (idempotent)
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
            ctx.user["os_mode"] = MODE_HOME
            return

        idx = int(idx)
        mod = _get_app_module(idx)
        if mod is None:
            ctx.user["os_mode"] = MODE_HOME
            ctx.user["os_active_app"] = None
            return

        if hasattr(mod, "update"):
            try:
                wants_back = bool(mod.update(ctx, dt, ev))
            except Exception:
                wants_back = True
            if wants_back:
                ctx.user["os_mode"] = MODE_HOME
                ctx.user["os_active_app"] = None
                ctx.user.pop("_app_switch_to", None)
                return

            # Optional app-to-app switch contract:
            # app sets ctx.user["_app_switch_to"] to a menu index.
            sw = ctx.user.pop("_app_switch_to", None)
            if sw is not None:
                try:
                    sw_idx = int(sw)
                except Exception:
                    sw_idx = -1
                if sw_idx in MENU_MODULES:
                    ctx.user["os_active_app"] = sw_idx
                    ctx.user["os_mode"] = MODE_APP
                    sw_mod = _get_app_module(sw_idx)
                    if sw_mod is not None and hasattr(sw_mod, "init"):
                        try:
                            sw_mod.init(ctx)
                        except Exception:
                            pass
                else:
                    ctx.user["os_mode"] = MODE_HOME
                    ctx.user["os_active_app"] = None
        else:
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
    if mode in (MODE_INTRO, MODE_INTRO_OUT):
        now = time.time()
        t = now - float(ctx.user.get("_intro_t0", now))

        # Fade-in
        fade_in = ease_in_out(min(1.0, t / max(0.001, INTRO_FADE_IN_SECONDS)))
        base = fade_from_black(assets.intro, fade_in).convert("RGBA")

        # Loading ring: square perimeter glow sweep
        pad = max(3, w // 70)
        base = _draw_square_intro_ring(base, t, pad)

        # Fade-out to HOME
        if mode == MODE_INTRO_OUT:
            out_t0 = float(ctx.user.get("_intro_out_t0", now))
            p = ease_in_out(min(1.0, (now - out_t0) / max(0.001, INTRO_FADE_OUT_SECONDS)))
            black = Image.new("RGBA", (w, h), (0, 0, 0, 255))
            base = Image.blend(base, black, p)

        img = base.convert("RGB")

        held = float(ctx.user.get("_k3_held", 0.0))
        if held >= K3_OVERLAY_SHOW_DELAY:
            img = overlay_hold_progress(img, "Hold B3 to shutdown", held, K3_SHUTDOWN_HOLD, ctx.font_s)
        return img

    # HOME
    if mode == MODE_HOME:
        img = app_background(ctx, dim_alpha=116).convert("RGBA")
        d = ImageDraw.Draw(img)

        pad, cell, icon_sz, top = _layout(w, h)
        sel = int(ctx.user.get("os_selected", 0))
        now = time.time()
        sel_rect = None

        for i in range(4):
            r, c = divmod(i, 2)
            x = pad + c * (cell + pad)
            y = top + pad + r * (cell + pad)

            d.rounded_rectangle(
                [x, y, x + cell, y + cell],
                radius=max(6, cell // 14),
                fill=(10, 10, 14, 138),
                outline=(245, 220, 210, 70),
                width=2,
            )

            icon = assets.icons.get(i)
            if icon is not None:
                ix = x + (cell - icon_sz) // 2
                iy = y + (cell - icon_sz) // 2
                img.paste(icon, (ix, iy), icon)

            if i == sel:
                sel_rect = (x, y, x + cell, y + cell)

        # Draw selection pulse last so other tile draws never clip/flicker its edges.
        if sel_rect is not None:
            x0, y0, x1, y1 = sel_rect
            pulse = breathe(now, 4.8)
            rad = max(8, cell // 12)
            alpha = int(90 + 140 * pulse)
            img = _draw_pulse_ring(
                img,
                (x0 - 4, y0 - 4, x1 + 4, y1 + 4),
                radius=rad + 1,
                thickness=3,
                color=(255, 244, 236),
                alpha=alpha,
            )

        out = img.convert("RGB")

        # Fade in after splash transition
        home_t0 = ctx.user.get("_home_t0")
        if home_t0 is not None:
            p = (time.time() - float(home_t0)) / max(0.001, HOME_FADE_IN_SECONDS)
            if p < 1.0:
                p = ease_in_out(p)
                black = Image.new("RGB", (w, h), (0, 0, 0))
                out = Image.blend(black, out, p)
            else:
                ctx.user["_home_t0"] = None
        held = float(ctx.user.get("_k3_held", 0.0))
        if held >= K3_OVERLAY_SHOW_DELAY:
            out = overlay_hold_progress(out, "Hold B3 to shutdown", held, K3_SHUTDOWN_HOLD, ctx.font_s)
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
            d.text((12, 48), "B2 to go back", font=ctx.font_m, fill=(220, 220, 220))
            return img

        try:
            img = mod.render(ctx)
        except Exception:
            img = Image.new("RGB", (w, h), (0, 0, 0))
            d = ImageDraw.Draw(img)
            d.text((12, 12), "App crashed", font=ctx.font_l, fill=(255, 80, 80))
            d.text((12, 48), "B2 to go back", font=ctx.font_m, fill=(220, 220, 220))

        held = float(ctx.user.get("_k3_held", 0.0))
        if held >= K3_OVERLAY_SHOW_DELAY:
            img = overlay_hold_progress(img, "Hold B3 to shutdown", held, K3_SHUTDOWN_HOLD, ctx.font_s)
        return img

    return Image.new("RGB", (w, h), (0, 0, 0))
