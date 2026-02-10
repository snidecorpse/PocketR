from __future__ import annotations

from typing import Dict

from PIL import Image, ImageDraw


def init(ctx):
    # no state needed
    pass


def update(ctx, dt: float, ev: Dict[str, bool]) -> bool:
    # K2 = back
    return "K2" in ev


def render(ctx) -> Image.Image:
    w, h = int(ctx.disp.width), int(ctx.disp.height)
    img = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((12, 12), "Empty", font=ctx.font_l, fill=(255, 255, 255))
    d.text((12, 48), "(Reserved for later)", font=ctx.font_m, fill=(200, 200, 200))
    d.text((12, h - 22), "K2: back", font=ctx.font_s, fill=(160, 160, 160))
    return img
