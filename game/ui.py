# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageOps


def fit_image(path: str, size: Tuple[int, int]) -> Image.Image:
    """
    Loads an image from disk and fits/crops it to the LCD size.
    """
    img = Image.open(path).convert("RGB")
    return ImageOps.fit(img, size, method=Image.Resampling.LANCZOS)


def draw_progress_bar(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, p: float):
    p = max(0.0, min(1.0, float(p)))
    draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, outline=(140, 140, 150), width=2)
    fill_w = int((w - 4) * p)
    if fill_w > 0:
        draw.rounded_rectangle([x + 2, y + 2, x + 2 + fill_w, y + h - 2], radius=(h - 4) // 2, fill=(220, 220, 230))


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int):
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


def center_text(draw: ImageDraw.ImageDraw, xy: Tuple[int, int], text: str, font, fill):
    x, y = xy
    tw = draw.textlength(text, font=font)
    th = font.size if hasattr(font, "size") else 14
    draw.text((x - tw / 2, y - th / 2), text, font=font, fill=fill)
