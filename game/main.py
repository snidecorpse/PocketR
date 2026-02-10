from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional, Set

from PIL import Image, ImageDraw


W, H = 240, 240


# ----- OS States -----
MODE_INTRO = "intro"
MODE_HOME = "home"
MODE_APP = "app"


@dataclass
class OSAssets:
    intro: Image.Image
    icons: Dict[int, Image.Image]


def _load_or_blank(path, size=(W, H), color=(0, 0, 0)):
    try:
        img = Image.open(path).convert("RGBA")
        if img.size != size:
            img = img.resize(size)
        return img
    except Exception:
        return Image.new("RGBA", size, color)


def init(ctx):
    """Runs once at boot."""
    ctx.user.setdefault("mode", MODE_INTRO)
    ctx.user.setdefault("selected", 0)
    ctx.user.setdefault("opened_app", 0)
    ctx.user["intro_start"] = time.time()

    # Load assets once
    intro_path = ctx.asset("ui", "intro.png")
    intro = _load_or_blank(intro_path, (W, H), (0, 0, 0))

    icons = {}
    for i in range(4):
        icons[i] = _load_or_blank(ctx.asset("ui", f"icon_{i+1}.png"), (96, 96), (20, 20, 20))

    ctx.user["_assets"] = OSAssets(intro=intro, icons=icons)


def update(ctx, dt: float, ev: Set[str]):
    mode = ctx.user.get("mode", MODE_INTRO)

    if mode == MODE_INTRO:
        # Auto-advance after ~2 seconds, or on any input
        if (time.time() - ctx.user.get("intro_start", time.time())) > 2.0:
            ctx.user["mode"] = MODE_HOME
        elif len(ev) > 0:
            ctx.user["mode"] = MODE_HOME
        return

    if mode == MODE_HOME:
        sel = int(ctx.user.get("selected", 0))
        row, col = divmod(sel, 2)

        if "UP" in ev:
            row = (row - 1) % 2
        if "DOWN" in ev:
            row = (row + 1) % 2
        if "LEFT" in ev:
            col = (col - 1) % 2
        if "RIGHT" in ev:
            col = (col + 1) % 2

        ctx.user["selected"] = row * 2 + col

        if "PRESS" in ev:
            ctx.user["opened_app"] = int(ctx.user["selected"])
            ctx.user["mode"] = MODE_APP
        return

    if mode == MODE_APP:
        # K1 is a simple "back" for now (you can repurpose later)
        if "K1" in ev or "PRESS_UP" in ev:
            ctx.user["mode"] = MODE_HOME
        return


def _draw_shutdown_overlay(img: Image.Image, ctx):
    if not ctx.user.get("shutdown_holding", False):
        return img

    held = float(ctx.user.get("shutdown_hold_seconds", 0.0))
    target = float(ctx.user.get("shutdown_hold_target", 3.0))
    p = 0.0 if target <= 0 else max(0.0, min(1.0, held / target))

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 160))
    d = ImageDraw.Draw(overlay)

    # Progress bar
    bar_w = 180
    bar_h = 14
    x0 = (W - bar_w) // 2
    y0 = 130
    d.rectangle([x0, y0, x0 + bar_w, y0 + bar_h], outline=(255, 255, 255, 255), width=2)
    d.rectangle([x0 + 2, y0 + 2, x0 + 2 + int((bar_w - 4) * p), y0 + bar_h - 2], fill=(255, 255, 255, 255))

    d.text((40, 100), "Hold K3 to shutdown", fill=(255, 255, 255, 255), font=ctx.font_m)
    d.text((88, 154), f"{int(p*100)}%", fill=(255, 255, 255, 255), font=ctx.font_m)

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def render(ctx) -> Image.Image:
    assets: Optional[OSAssets] = ctx.user.get("_assets")
    mode = ctx.user.get("mode", MODE_INTRO)

    # Base canvas
    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))

    if assets is None:
        # Defensive fallback
        d = ImageDraw.Draw(img)
        d.text((10, 10), "Loading...", fill=(255, 255, 255, 255), font=ctx.font_m)
        return img.convert("RGB")

    if mode == MODE_INTRO:
        img.paste(assets.intro, (0, 0), assets.intro)
        # Optional: subtle hint
        d = ImageDraw.Draw(img)
        d.text((70, 210), "Pocket-R", fill=(255, 255, 255, 200), font=ctx.font_m)
        out = img.convert("RGB")
        return _draw_shutdown_overlay(out, ctx)

    if mode == MODE_HOME:
        d = ImageDraw.Draw(img)

        # 2x2 icon grid
        pad = 12
        cell = (W - pad * 3) // 2  # two cells + 3 paddings

        sel = int(ctx.user.get("selected", 0))

        for i in range(4):
            r, c = divmod(i, 2)
            x = pad + c * (cell + pad)
            y = pad + r * (cell + pad)

            # Cell background
            d.rectangle([x, y, x + cell, y + cell], outline=(70, 70, 70, 255), width=2)

            # Icon centered
            icon = assets.icons.get(i)
            if icon is not None:
                ix = x + (cell - icon.width) // 2
                iy = y + (cell - icon.height) // 2
                img.paste(icon, (ix, iy), icon)

            # Selection border
            if i == sel:
                d.rectangle([x - 2, y - 2, x + cell + 2, y + cell + 2], outline=(255, 255, 255, 255), width=3)

        # Footer hint
        d.rectangle([0, H - 26, W, H], fill=(0, 0, 0, 200))
        d.text((8, H - 22), "D-pad: move  PRESS: open  (Hold K3: off)", fill=(255, 255, 255, 255), font=ctx.font_s)

        out = img.convert("RGB")
        return _draw_shutdown_overlay(out, ctx)

    if mode == MODE_APP:
        d = ImageDraw.Draw(img)
        idx = int(ctx.user.get("opened_app", 0))
        d.text((12, 12), f"App {idx+1}", fill=(255, 255, 255, 255), font=ctx.font_l)
        d.text((12, 54), "Placeholder screen", fill=(200, 200, 200, 255), font=ctx.font_m)
        d.text((12, 80), "Press K1 to go back", fill=(200, 200, 200, 255), font=ctx.font_m)

        # Big placeholder box
        d.rectangle([20, 110, W - 20, H - 40], outline=(120, 120, 120, 255), width=2)
        d.text((44, 160), "(Coming soon)", fill=(180, 180, 180, 255), font=ctx.font_m)

        out = img.convert("RGB")
        return _draw_shutdown_overlay(out, ctx)

    # Unknown mode
    d = ImageDraw.Draw(img)
    d.text((10, 10), "Unknown mode", fill=(255, 0, 0, 255), font=ctx.font_m)
    out = img.convert("RGB")
    return _draw_shutdown_overlay(out, ctx)
