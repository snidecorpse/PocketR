from __future__ import annotations

from typing import Tuple

from PIL import Image, ImageDraw


def load_image_or_blank(path: str, size: Tuple[int, int], color=(0, 0, 0)) -> Image.Image:
    """Load an image, convert to RGBA, and resize. Fallback to a solid-color image."""
    try:
        img = Image.open(path).convert("RGBA")
        if img.size != size:
            img = img.resize(size)
        return img
    except Exception:
        return Image.new("RGBA", size, color)


def draw_center_text(img: Image.Image, text: str, font, fill=(255, 255, 255)) -> None:
    d = ImageDraw.Draw(img)
    w, h = img.size
    tw = int(d.textlength(text, font=font))
    th = font.size if hasattr(font, "size") else 16
    d.text(((w - tw) // 2, (h - th) // 2), text, font=font, fill=fill)


def overlay_hold_progress(img: Image.Image, title: str, held: float, target: float, font) -> Image.Image:
    """Draw a simple progress overlay at the bottom."""
    if target <= 0 or held <= 0:
        return img

    w, h = img.size
    p = max(0.0, min(1.0, held / target))

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
    d.rectangle([bar_x0 + 2, bar_y0 + 2, bar_x0 + 2 + int((bar_w - 4) * p), bar_y0 + bar_h - 2], fill=(255, 255, 255, 230))

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
