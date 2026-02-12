from __future__ import annotations

import math
import os
from typing import List, Tuple

from PIL import Image, ImageDraw


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def load_image_or_blank(path: str, size: Tuple[int, int], color=(0, 0, 0)) -> Image.Image:
    """Load an image, convert to RGBA, and resize. Fallback to a solid-color image."""
    try:
        img = Image.open(path).convert("RGBA")
        if img.size != size:
            img = img.resize(size)
        return img
    except Exception:
        return Image.new("RGBA", size, color)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> List[str]:
    """Simple word-wrap for a single paragraph."""
    words = text.split()
    lines: List[str] = []
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


def draw_center_text(img: Image.Image, text: str, font, fill=(255, 255, 255)) -> None:
    d = ImageDraw.Draw(img)
    w, h = img.size
    tw = int(d.textlength(text, font=font))
    th = getattr(font, "size", 16)
    d.text(((w - tw) // 2, (h - th) // 2), text, font=font, fill=fill)


def ease_in_out(t: float) -> float:
    """Smoothstep-ish easing for t in [0,1]."""
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def fade_from_black(img: Image.Image, amount: float) -> Image.Image:
    """amount=0 -> black, amount=1 -> original."""
    amount = clamp(amount, 0.0, 1.0)
    base = img.convert("RGBA")
    black = Image.new("RGBA", base.size, (0, 0, 0, 255))
    return Image.blend(black, base, amount)


def overlay_hold_progress(img: Image.Image, title: str, held: float, target: float, font) -> Image.Image:
    """Draw a simple progress overlay at the bottom."""
    if target <= 0 or held <= 0:
        return img

    w, h = img.size
    p = clamp(held / target, 0.0, 1.0)

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    box_h = 54
    x0, y0 = 10, h - box_h - 10
    x1, y1 = w - 10, h - 10

    d.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=(0, 0, 0, 160), outline=(255, 255, 255, 180), width=2)
    d.text((x0 + 12, y0 + 8), title, font=font, fill=(255, 255, 255, 230))

    bar_x0 = x0 + 12
    bar_y0 = y0 + 28
    bar_w = (x1 - x0) - 24
    bar_h = 12

    d.rectangle([bar_x0, bar_y0, bar_x0 + bar_w, bar_y0 + bar_h], outline=(255, 255, 255, 200), width=2)
    d.rectangle(
        [bar_x0 + 2, bar_y0 + 2, bar_x0 + 2 + int((bar_w - 4) * p), bar_y0 + bar_h - 2],
        fill=(255, 255, 255, 230),
    )

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def draw_top_bar(img: Image.Image, title: str, font, right_text: str | None = None) -> int:
    """Draw a top bar and return the y-offset where content should start."""
    w, h = img.size
    bar_h = 34 if h >= 200 else 28

    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, bar_h], fill=(16, 16, 18))
    d.line([0, bar_h, w, bar_h], fill=(60, 60, 68), width=1)

    d.text((10, 7), title, font=font, fill=(255, 255, 255))

    if right_text:
        tw = int(d.textlength(right_text, font=font))
        d.text((w - 10 - tw, 7), right_text, font=font, fill=(200, 200, 200))

    return bar_h + 8


def draw_bottom_hint(img: Image.Image, text: str, font) -> None:
    w, h = img.size
    bar_h = 24
    d = ImageDraw.Draw(img)
    d.rectangle([0, h - bar_h, w, h], fill=(10, 10, 12))
    d.line([0, h - bar_h, w, h - bar_h], fill=(50, 50, 58), width=1)
    d.text((10, h - bar_h + 5), text, font=font, fill=(160, 160, 160))


def draw_progress_bar(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, frac: float) -> None:
    frac = clamp(frac, 0.0, 1.0)
    d.rounded_rectangle([x, y, x + w, y + h], radius=8, outline=(210, 210, 210), width=2)
    inner = max(0, int((w - 4) * frac))
    if inner > 0:
        d.rounded_rectangle([x + 2, y + 2, x + 2 + inner, y + h - 2], radius=6, fill=(230, 230, 230))


def draw_list_item(
    d: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    left: str,
    right: str,
    font,
    selected: bool,
) -> None:
    if selected:
        d.rounded_rectangle([x, y, x + w, y + h], radius=14, fill=(235, 235, 235))
        fg = (0, 0, 0)
        sub = (40, 40, 40)
    else:
        d.rounded_rectangle([x, y, x + w, y + h], radius=14, outline=(70, 70, 80), width=2)
        fg = (235, 235, 235)
        sub = (180, 180, 180)

    d.text((x + 12, y + 8), left, font=font, fill=fg)

    tw = int(d.textlength(right, font=font))
    d.text((x + w - 12 - tw, y + 8), right, font=font, fill=sub)


def dots(t: float, speed: float = 1.4) -> str:
    n = int((t * speed) % 4)
    return "." * n


def ping_pong(t: float, period: float) -> float:
    if period <= 0:
        return 0.0
    x = (t / period) % 2.0
    return 2.0 - x if x > 1.0 else x


def breathe(t: float, period: float = 2.0) -> float:
    """0..1..0 smoothly."""
    return 0.5 - 0.5 * math.cos(2.0 * math.pi * ((t / period) % 1.0))


def _resample():
    if hasattr(Image, "Resampling"):
        return Image.Resampling.LANCZOS
    return Image.LANCZOS


def _draw_star(d: ImageDraw.ImageDraw, x: int, y: int, size: int, color=(255, 220, 180), alpha: int = 255) -> None:
    c = (color[0], color[1], color[2], alpha)
    s = max(1, int(size))
    d.line([x - s, y, x + s, y], fill=c, width=1)
    d.line([x, y - s, x, y + s], fill=c, width=1)
    if s >= 2:
        d.line([x - (s - 1), y - (s - 1), x + (s - 1), y + (s - 1)], fill=(255, 190, 140, max(40, alpha - 90)), width=1)
        d.line([x + (s - 1), y - (s - 1), x - (s - 1), y + (s - 1)], fill=(255, 190, 140, max(40, alpha - 90)), width=1)


def generate_red_background(size: Tuple[int, int]) -> Image.Image:
    """Fallback red sparkle background if app_bg.png is not present."""
    w, h = size
    img = Image.new("RGBA", (w, h), (8, 0, 0, 255))
    d = ImageDraw.Draw(img)

    # Radial red core
    cx = w * 0.5
    cy = h * 0.52
    max_r = int(max(w, h) * 0.65)
    for i in range(max_r, 0, -1):
        t = i / float(max(1, max_r))
        alpha = int(70 * (1.0 - t))
        red = int(120 + 110 * (1.0 - t))
        d.ellipse([cx - i, cy - i, cx + i, cy + i], fill=(red, 0, 0, alpha))

    # Twinkling square frame near the edges
    margin = max(10, min(w, h) // 14)
    x0, y0 = margin, margin
    x1, y1 = w - margin - 1, h - margin - 1
    d.rounded_rectangle([x0, y0, x1, y1], radius=max(12, margin // 2), outline=(255, 170, 150, 65), width=2)

    perim = 2 * ((x1 - x0) + (y1 - y0))
    n = max(100, perim // 6)
    for i in range(n):
        t = i / float(max(1, n))
        p = t * perim
        seg = (x1 - x0)
        if p < seg:
            x, y = int(x0 + p), y0
        elif p < seg + (y1 - y0):
            x, y = x1, int(y0 + (p - seg))
        elif p < (2 * seg) + (y1 - y0):
            x, y = int(x1 - (p - (seg + (y1 - y0)))), y1
        else:
            x, y = x0, int(y1 - (p - ((2 * seg) + (y1 - y0))))
        bright = 90 + int(120 * (0.5 + 0.5 * math.sin(i * 1.7)))
        _draw_star(d, x, y, 1 if (i % 3) else 3, alpha=min(255, bright))

    # Fine texture
    for y in range(0, h, 2):
        alpha = 10 + ((y * 13) % 22)
        d.line([0, y, w, y], fill=(255, 30, 30, alpha), width=1)

    return img


def app_background(ctx, dim_alpha: int = 92) -> Image.Image:
    """
    Shared background for non-pet apps.
    Uses game/assets/ui/app_bg.png when available, otherwise procedural fallback.
    """
    w, h = int(ctx.disp.width), int(ctx.disp.height)
    bg_path = ctx.asset("ui", "app_bg.png")
    try:
        mtime = int(os.path.getmtime(bg_path))
    except Exception:
        mtime = -1
    key = f"{w}x{h}:{mtime}"

    if ctx.user.get("_app_bg_key") != key:
        if os.path.isfile(bg_path):
            try:
                base = Image.open(bg_path).convert("RGBA")
                if base.size != (w, h):
                    base = base.resize((w, h), _resample())
            except Exception:
                base = generate_red_background((w, h))
        else:
            base = generate_red_background((w, h))
        ctx.user["_app_bg_base"] = base
        ctx.user["_app_bg_key"] = key

    base = ctx.user.get("_app_bg_base")
    if not isinstance(base, Image.Image):
        base = generate_red_background((w, h))

    out = base.copy().convert("RGBA")
    if dim_alpha > 0:
        a = int(clamp(float(dim_alpha), 0.0, 255.0))
        out = Image.alpha_composite(out, Image.new("RGBA", (w, h), (0, 0, 0, a)))
    return out.convert("RGB")


def overlay_panel(
    img: Image.Image,
    rect: Tuple[int, int, int, int],
    radius: int = 14,
    fill=(6, 6, 10, 156),
    outline=(255, 255, 255, 90),
    width: int = 2,
) -> Image.Image:
    """Alpha-composited rounded panel drawn over an image."""
    base = img.convert("RGBA")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(list(rect), radius=radius, fill=fill, outline=outline, width=width)
    return Image.alpha_composite(base, layer).convert("RGB")


def draw_wrapped_block(
    d: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    max_width: int,
    font,
    fill=(220, 220, 220),
    line_h: int = 16,
) -> int:
    """Draw wrapped multi-line text and return the next y."""
    for para in (text or "").splitlines():
        if not para.strip():
            y += max(4, line_h // 2)
            continue
        lines = wrap_text(d, para, font, max_width=max_width) or [""]
        for line in lines:
            d.text((x, y), line, font=font, fill=fill)
            y += line_h
    return y
