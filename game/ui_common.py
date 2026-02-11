from __future__ import annotations

import math
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
