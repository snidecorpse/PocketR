from __future__ import annotations

import glob
import os
import time
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw

from ..ui_common import app_background, overlay_panel


GALLERY_DIR = "blank_gallery"
GALLERY_EXTS = ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp")
GALLERY_SCAN_SECONDS = 1.0


def _gallery_prefs(ctx) -> Dict:
    prefs = ctx.user.get("_prefs", {}) if isinstance(ctx.user.get("_prefs"), dict) else {}
    return {
        "mode": "GRID" if str(prefs.get("gallery_mode", "SLIDE")).upper() == "GRID" else "SLIDE",
        "auto_scroll": bool(prefs.get("gallery_auto_scroll", True)),
        "auto_seconds": float(prefs.get("gallery_auto_seconds", 3.2) or 3.2),
        "swipe_seconds": float(prefs.get("gallery_swipe_seconds", 0.22) or 0.22),
        "show_filename": bool(prefs.get("gallery_show_filename", True)),
    }


def _gallery_paths(ctx) -> List[str]:
    now = time.time()
    cache = ctx.user.get("_blank_paths_cache", None)
    if isinstance(cache, dict):
        age = now - float(cache.get("t", 0.0))
        paths = cache.get("paths", [])
        if age < GALLERY_SCAN_SECONDS and isinstance(paths, list):
            return paths

    roots: List[str] = [ctx.asset(GALLERY_DIR)]
    if hasattr(ctx, "data_path"):
        roots.append(ctx.data_path("gallery"))
    else:
        base = str(getattr(ctx, "base_dir", ".") or ".")
        roots.append(os.path.join(base, ".pocketr", "gallery"))

    found: List[str] = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for ext in GALLERY_EXTS:
            found.extend(glob.glob(os.path.join(root, ext)))

    uniq = sorted({os.path.abspath(p) for p in found})
    out = [p for p in uniq if os.path.isfile(p)]
    ctx.user["_blank_paths_cache"] = {"t": now, "paths": out}
    return out


def _resample():
    if hasattr(Image, "Resampling"):
        return Image.Resampling.LANCZOS
    return Image.LANCZOS


def _fit_image(src: Image.Image, max_size: Tuple[int, int]) -> Image.Image:
    out = src.copy()
    out.thumbnail(max_size, _resample())
    return out


def _load_cards(ctx, w: int, h: int, tag: str) -> List[Image.Image]:
    paths = _gallery_paths(ctx)
    key_parts: List[str] = []
    for p in paths:
        try:
            key_parts.append(f"{p}:{int(os.path.getmtime(p))}")
        except Exception:
            key_parts.append(f"{p}:0")
    key = f"{tag}|{w}x{h}|" + "|".join(key_parts)

    cache_map = ctx.user.get("_blank_cards_cache", None)
    if not isinstance(cache_map, dict):
        cache_map = {}
    if key in cache_map and isinstance(cache_map.get(key), list):
        return cache_map[key]

    cards: List[Image.Image] = []
    for p in paths:
        card = Image.new("RGB", (w, h), (10, 8, 10))
        d = ImageDraw.Draw(card)

        try:
            src = Image.open(p).convert("RGB")
            fit = _fit_image(src, (max(8, w - 12), max(8, h - 24)))
            x = (w - fit.width) // 2
            y = max(4, (h - fit.height) // 2 - 4)
            card.paste(fit, (x, y))
        except Exception:
            d.text((8, 8), "Image load failed", font=ctx.font_s, fill=(255, 120, 120))

        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=7, outline=(255, 218, 208), width=2)
        d.rounded_rectangle([2, 2, w - 3, h - 3], radius=6, outline=(92, 66, 62), width=1)
        cards.append(card)

    cache_map[key] = cards
    # keep cache bounded
    if len(cache_map) > 10:
        cache_map = {key: cards}
    ctx.user["_blank_cards_cache"] = cache_map
    return cards


def _move_to(ctx, new_idx: int, direction: int, now: float, count: int) -> None:
    if count <= 0:
        return
    cur = int(ctx.user.get("_blank_idx", 0)) % count
    nxt = new_idx % count
    if nxt == cur:
        return
    ctx.user["_blank_prev_idx"] = cur
    ctx.user["_blank_idx"] = nxt
    ctx.user["_blank_anim_t0"] = now
    ctx.user["_blank_anim_dir"] = 1 if direction >= 0 else -1
    ctx.user["_blank_last_auto"] = now


def _grid_dims(content_w: int, content_h: int) -> Tuple[int, int]:
    cols = 3 if content_w >= 180 else 2
    rows = 2
    return cols, rows


def init(ctx):
    now = time.time()
    ctx.user["_blank_idx"] = int(ctx.user.get("_blank_idx", 0))
    ctx.user["_blank_prev_idx"] = None
    ctx.user["_blank_anim_t0"] = 0.0
    ctx.user["_blank_anim_dir"] = 1
    ctx.user["_blank_last_auto"] = now
    ctx.user["_blank_paths_cache"] = {"t": 0.0, "paths": []}
    ctx.user.setdefault("_blank_focus", False)


def update(ctx, dt: float, ev: Dict[str, bool]) -> bool:
    prefs = _gallery_prefs(ctx)
    mode = prefs["mode"]

    if "K2" in ev:
        if mode == "GRID" and bool(ctx.user.get("_blank_focus", False)):
            ctx.user["_blank_focus"] = False
            return False
        return True

    now = time.time()
    paths = _gallery_paths(ctx)
    count = len(paths)
    if count <= 0:
        return False

    idx = int(ctx.user.get("_blank_idx", 0)) % count
    ctx.user["_blank_idx"] = idx

    auto_enabled = bool(prefs["auto_scroll"])
    auto_seconds = max(0.8, float(prefs["auto_seconds"]))

    if mode == "SLIDE":
        ctx.user["_blank_focus"] = False

        if "LEFT" in ev:
            _move_to(ctx, idx - 1, -1, now, count)
        elif "RIGHT" in ev or "K1" in ev or "PRESS" in ev:
            _move_to(ctx, idx + 1, 1, now, count)
        elif auto_enabled and count > 1:
            last_auto = float(ctx.user.get("_blank_last_auto", now))
            if now - last_auto >= auto_seconds:
                _move_to(ctx, idx + 1, 1, now, count)

        return False

    # GRID mode
    focus = bool(ctx.user.get("_blank_focus", False))

    if focus:
        if "LEFT" in ev:
            _move_to(ctx, idx - 1, -1, now, count)
        elif "RIGHT" in ev:
            _move_to(ctx, idx + 1, 1, now, count)
        elif "UP" in ev:
            _move_to(ctx, idx - 3, -1, now, count)
        elif "DOWN" in ev:
            _move_to(ctx, idx + 3, 1, now, count)
        elif "K1" in ev or "PRESS" in ev:
            ctx.user["_blank_focus"] = False

        if auto_enabled and count > 1 and not ev:
            last_auto = float(ctx.user.get("_blank_last_auto", now))
            if now - last_auto >= auto_seconds:
                _move_to(ctx, idx + 1, 1, now, count)

        return False

    # Grid browse
    if "LEFT" in ev:
        _move_to(ctx, idx - 1, -1, now, count)
    elif "RIGHT" in ev:
        _move_to(ctx, idx + 1, 1, now, count)
    elif "UP" in ev:
        _move_to(ctx, idx - 3, -1, now, count)
    elif "DOWN" in ev:
        _move_to(ctx, idx + 3, 1, now, count)
    elif "K1" in ev or "PRESS" in ev:
        ctx.user["_blank_focus"] = True

    return False


def _draw_header(ctx, img: Image.Image, mode_label: str, right: str) -> Tuple[Image.Image, Tuple[int, int, int, int]]:
    w, h = img.size
    img = overlay_panel(
        img,
        (8, 8, w - 9, 42),
        radius=10,
        fill=(6, 6, 10, 176),
        outline=(255, 220, 210, 120),
        width=2,
    )
    d = ImageDraw.Draw(img)
    d.text((16, 15), "Gallery", font=ctx.font_m, fill=(255, 248, 244))

    chip = str(mode_label or "").strip()
    if chip:
        ctw = int(d.textlength(chip, font=ctx.font_s))
        cx = (w - ctw) // 2
        d.text((cx + 1, 15), chip, font=ctx.font_s, fill=(8, 6, 8, 180))
        d.text((cx, 14), chip, font=ctx.font_s, fill=(235, 220, 214))

    tw = int(d.textlength(right, font=ctx.font_s))
    d.text((w - 14 - tw, 16), right, font=ctx.font_s, fill=(220, 210, 205))

    content_rect = (8, 50, w - 9, h - 9)
    img = overlay_panel(
        img,
        content_rect,
        radius=12,
        fill=(6, 6, 10, 158),
        outline=(255, 220, 210, 90),
        width=2,
    )
    return img, content_rect


def _render_empty(ctx, img: Image.Image, rect: Tuple[int, int, int, int]) -> Image.Image:
    d = ImageDraw.Draw(img)
    x0, y0, x1, _y1 = rect
    d.text((x0 + 12, y0 + 16), "No gallery images found.", font=ctx.font_m, fill=(240, 230, 226))
    d.text((x0 + 12, y0 + 40), "Add .png/.jpg files in:", font=ctx.font_s, fill=(215, 190, 182))
    d.text((x0 + 12, y0 + 56), "game/assets/blank_gallery/", font=ctx.font_s, fill=(215, 190, 182))
    d.text((x0 + 12, y0 + 78), "B2 Back", font=ctx.font_s, fill=(215, 190, 182))
    return img


def _render_slide(ctx, img: Image.Image, rect: Tuple[int, int, int, int], cards: List[Image.Image], show_filename: bool, swipe_seconds: float) -> Image.Image:
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = rect
    content_x = x0 + 8
    content_y = y0 + 8
    content_w = (x1 - x0) - 16
    content_h = (y1 - y0) - 16

    count = len(cards)
    idx = int(ctx.user.get("_blank_idx", 0)) % count
    prev_idx = ctx.user.get("_blank_prev_idx")
    anim_t0 = float(ctx.user.get("_blank_anim_t0", 0.0))
    anim_dir = int(ctx.user.get("_blank_anim_dir", 1))

    p = 1.0
    if prev_idx is not None:
        p = min(1.0, max(0.0, (time.time() - anim_t0) / max(0.001, swipe_seconds)))

    d.rounded_rectangle([content_x - 2, content_y - 2, content_x + content_w + 1, content_y + content_h + 1], radius=7, outline=(255, 220, 210), width=1)
    cur = cards[idx]
    if prev_idx is not None and 0 <= int(prev_idx) < count and p < 1.0:
        prev = cards[int(prev_idx)]
        dx = content_w
        if anim_dir >= 0:
            prev_x = content_x - int(dx * p)
            cur_x = content_x + int(dx * (1.0 - p))
        else:
            prev_x = content_x + int(dx * p)
            cur_x = content_x - int(dx * (1.0 - p))
        img.paste(prev, (prev_x, content_y))
        img.paste(cur, (cur_x, content_y))
    else:
        img.paste(cur, (content_x, content_y))
        ctx.user["_blank_prev_idx"] = None

    page = f"{idx + 1}/{count}"
    tw = int(d.textlength(page, font=ctx.font_s))
    px = x1 - 10 - tw
    d.text((px + 1, y0 + 7), page, font=ctx.font_s, fill=(8, 6, 8, 170))
    d.text((px, y0 + 6), page, font=ctx.font_s, fill=(228, 214, 208))

    if show_filename:
        name = os.path.basename(_gallery_paths(ctx)[idx])
        ntw = int(d.textlength(name, font=ctx.font_s))
        bx = content_x + max(0, (content_w - ntw) // 2)
        by = y1 - 24
        d.text((bx + 1, by + 1), name, font=ctx.font_s, fill=(8, 6, 8, 170))
        d.text((bx, by), name, font=ctx.font_s, fill=(235, 225, 220))

    return img


def _render_grid(ctx, img: Image.Image, rect: Tuple[int, int, int, int], thumbs: List[Image.Image]) -> Image.Image:
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = rect
    content_x = x0 + 8
    content_y = y0 + 8
    content_w = (x1 - x0) - 16
    content_h = (y1 - y0) - 16

    cols, rows = _grid_dims(content_w, content_h)
    gap = 6
    cell_w = max(20, (content_w - ((cols - 1) * gap)) // cols)
    cell_h = max(20, (content_h - ((rows - 1) * gap)) // rows)

    count = len(thumbs)
    idx = int(ctx.user.get("_blank_idx", 0)) % count

    page_size = cols * rows
    page = idx // page_size
    page_start = page * page_size
    pages = (count + page_size - 1) // page_size

    for slot in range(page_size):
        item_idx = page_start + slot
        col = slot % cols
        row = slot // cols

        x = content_x + col * (cell_w + gap)
        y = content_y + row * (cell_h + gap)

        if item_idx >= count:
            d.rounded_rectangle([x, y, x + cell_w, y + cell_h], radius=6, fill=(20, 12, 12), outline=(120, 90, 86), width=1)
            continue

        d.rounded_rectangle([x, y, x + cell_w, y + cell_h], radius=6, fill=(12, 8, 10), outline=(92, 70, 68), width=1)
        thumb = thumbs[item_idx]
        tx = x + max(0, (cell_w - thumb.width) // 2)
        ty = y + max(0, (cell_h - thumb.height) // 2)
        img.paste(thumb, (tx, ty))

        if item_idx == idx:
            d.rounded_rectangle([x - 2, y - 2, x + cell_w + 2, y + cell_h + 2], radius=7, outline=(255, 238, 228), width=2)
        else:
            d.rounded_rectangle([x, y, x + cell_w, y + cell_h], radius=6, outline=(210, 170, 160), width=1)

    label = f"Page {page + 1}/{max(1, pages)}"
    tw = int(d.textlength(label, font=ctx.font_s))
    d.text((x1 - 12 - tw, y0 + 6), label, font=ctx.font_s, fill=(220, 200, 192))
    return img


def render(ctx) -> Image.Image:
    prefs = _gallery_prefs(ctx)
    mode = prefs["mode"]
    focus = bool(ctx.user.get("_blank_focus", False))

    w, h = int(ctx.disp.width), int(ctx.disp.height)
    base = app_background(ctx, dim_alpha=112)

    mode_label = "Slide" if mode == "SLIDE" else ("Grid Focus" if focus else "Grid")
    right = "B2 Grid" if (mode == "GRID" and focus) else "B2 Back"
    base, rect = _draw_header(ctx, base, mode_label, right)

    x0, y0, x1, y1 = rect
    content_w = (x1 - x0) - 16
    content_h = (y1 - y0) - 16

    paths = _gallery_paths(ctx)
    if not paths:
        return _render_empty(ctx, base, rect)

    idx = int(ctx.user.get("_blank_idx", 0)) % len(paths)
    ctx.user["_blank_idx"] = idx

    # Grid mode has a browse grid and a focus view; slide mode always uses focus-like renderer.
    if mode == "GRID" and not focus:
        thumbs = _load_cards(ctx, max(30, (content_w // 3) - 6), max(30, (content_h // 2) - 6), "grid")
        return _render_grid(ctx, base, rect, thumbs)

    cards = _load_cards(ctx, content_w, content_h, "slide")
    swipe_seconds = max(0.05, float(prefs["swipe_seconds"]))
    return _render_slide(ctx, base, rect, cards, bool(prefs["show_filename"]), swipe_seconds)
