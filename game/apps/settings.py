from __future__ import annotations

import os
import subprocess
import time
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw

from ..persistence import ensure_data_dir, read_json, write_json_atomic
from ..ui_common import (
    app_background,
    clamp,
    overlay_panel,
    wrap_text,
)


PREFS_REL_PATH = "settings.json"

BRIGHTNESS_STEP = 5
FPS_MIN, FPS_MAX = 5, 30

GALLERY_AUTO_MIN, GALLERY_AUTO_MAX = 1.0, 12.0
GALLERY_SWIPE_MIN, GALLERY_SWIPE_MAX = 0.08, 1.20

ITEM_H = 34
ITEM_GAP = 6

MODE_LIST = "LIST"
MODE_HELP = "HELP"
MODE_GALLERY = "GALLERY"
MODE_DEBUG = "DEBUG"
MODE_SHUTDOWN = "SHUTDOWN"


def _run(cmd: List[str], timeout: float = 0.8) -> str:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, text=True)
        return (p.stdout or "").strip()
    except Exception:
        return ""


def _prefs_path(ctx) -> str:
    ensure_data_dir(ctx)
    if hasattr(ctx, "data_path"):
        return ctx.data_path(PREFS_REL_PATH)
    return os.path.join(getattr(ctx, "base_dir", "."), PREFS_REL_PATH)


def _defaults(ctx) -> Dict:
    return {
        "brightness": 60,
        "target_fps": 15,
        "show_fps": False,
        "gallery_mode": "SLIDE",
        "gallery_auto_scroll": True,
        "gallery_auto_seconds": 3.2,
        "gallery_swipe_seconds": 0.22,
        "gallery_show_filename": True,
    }


def _is_git_repo(path: str) -> bool:
    if not path:
        return False
    out = _run(["git", "-C", path, "rev-parse", "--is-inside-work-tree"], timeout=0.7)
    return out.strip() == "true"


def _git_root(path: str) -> str:
    if not path:
        return ""
    out = _run(["git", "-C", path, "rev-parse", "--show-toplevel"], timeout=0.8)
    p = (out or "").strip()
    return p if p and os.path.isdir(p) else ""


def _coerce_mode(v) -> str:
    s = str(v or "SLIDE").strip().upper()
    return "GRID" if s == "GRID" else "SLIDE"


def _ensure_prefs(ctx) -> Dict:
    if isinstance(ctx.user.get("_prefs"), dict):
        prefs = ctx.user["_prefs"]
    else:
        prefs = _defaults(ctx)
        disk = read_json(ctx, PREFS_REL_PATH, {})
        if isinstance(disk, dict):
            prefs.update({k: disk.get(k, v) for k, v in prefs.items()})

    # Main settings
    try:
        prefs["brightness"] = int(clamp(float(prefs.get("brightness", 60)), 0, 100))
    except Exception:
        prefs["brightness"] = 60

    try:
        prefs["target_fps"] = int(clamp(float(prefs.get("target_fps", 15)), FPS_MIN, FPS_MAX))
    except Exception:
        prefs["target_fps"] = 15

    prefs["show_fps"] = bool(prefs.get("show_fps", False))

    # Gallery settings
    prefs["gallery_mode"] = _coerce_mode(prefs.get("gallery_mode", "SLIDE"))
    prefs["gallery_auto_scroll"] = bool(prefs.get("gallery_auto_scroll", True))

    try:
        v = float(prefs.get("gallery_auto_seconds", 3.2))
        prefs["gallery_auto_seconds"] = round(clamp(v, GALLERY_AUTO_MIN, GALLERY_AUTO_MAX), 1)
    except Exception:
        prefs["gallery_auto_seconds"] = 3.2

    try:
        v = float(prefs.get("gallery_swipe_seconds", 0.22))
        prefs["gallery_swipe_seconds"] = round(clamp(v, GALLERY_SWIPE_MIN, GALLERY_SWIPE_MAX), 2)
    except Exception:
        prefs["gallery_swipe_seconds"] = 0.22

    prefs["gallery_show_filename"] = bool(prefs.get("gallery_show_filename", True))

    ctx.user["_prefs"] = prefs
    return prefs


def _save_prefs(ctx) -> None:
    try:
        write_json_atomic(ctx, PREFS_REL_PATH, _ensure_prefs(ctx))
    except Exception:
        pass


def _step(v: float, delta: float, lo: float, hi: float, digits: int) -> float:
    return round(clamp(v + delta, lo, hi), digits)


def _ensure_visible(sel: int, scroll: int, total: int, visible: int) -> int:
    if sel < scroll:
        scroll = sel
    elif sel >= scroll + visible:
        scroll = sel - visible + 1
    return max(0, min(scroll, max(0, total - visible)))


def init(ctx):
    prefs = _ensure_prefs(ctx)

    try:
        ctx.disp.bl_DutyCycle(int(prefs.get("brightness", 60)))
    except Exception:
        pass

    ctx.user.setdefault("_settings_mode", MODE_LIST)
    ctx.user.setdefault("_settings_sel", 0)
    ctx.user.setdefault("_settings_scroll", 0)

    ctx.user.setdefault("_settings_gallery_sel", 0)
    ctx.user.setdefault("_settings_gallery_scroll", 0)

    ctx.user.setdefault("_help_scroll", 0)
    ctx.user.setdefault("_debug_scroll", 0)
    ctx.user.setdefault("_debug_cache", {"t": 0.0, "lines": []})


def _help_lines() -> List[str]:
    return [
        "PocketR Controls",
        "D-Pad: navigate items and values.",
        "PRESS or B1: select/confirm action.",
        "B2: back to previous screen.",
        "Hold B3 for 3 seconds anywhere to shut down safely.",
        "",
        "Apps",
        "Pet Game: room-based pet interactions (WIP gameplay).",
        "Gallery: browse images in Slide or Grid mode.",
        "Settings: display and gallery behavior.",
        "Update: pulls latest git changes then reboots Linux.",
        "",
        "Update Notes",
        "Updater auto-targets /root/PocketR on Pi.",
        "If pull fails, check network, git remote, and branch state.",
    ]


def _build_debug_lines(ctx, prefs: Dict) -> List[str]:
    base = str(getattr(ctx, "base_dir", "") or "")
    repo = _git_root(base) or base

    ssid = _run(["iwgetid", "-r"], timeout=0.7) or "-"
    ip_wlan = _run(["bash", "-lc", "ip -4 addr show wlan0 | sed -n 's/.*inet \\([0-9.]*\\).*/\\1/p' | head -n1"], timeout=0.8) or "-"
    ip_eth = _run(["bash", "-lc", "ip -4 addr show eth0 | sed -n 's/.*inet \\([0-9.]*\\).*/\\1/p' | head -n1"], timeout=0.8) or "-"

    uptime = "-"
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            secs = float(f.read().split()[0])
        m = int(secs // 60)
        h = m // 60
        m = m % 60
        uptime = f"{h}h {m}m"
    except Exception:
        pass

    git_short = _run(["git", "-C", repo, "rev-parse", "--short", "HEAD"], timeout=0.9) if _is_git_repo(repo) else "(not a git repo)"

    disk = "-"
    df = _run(["df", "-h", "/"], timeout=0.9)
    rows = df.splitlines()
    if len(rows) >= 2:
        parts = rows[1].split()
        if len(parts) >= 5:
            disk = f"{parts[2]}/{parts[1]} ({parts[4]})"

    temp = _run(["bash", "-lc", "vcgencmd measure_temp 2>/dev/null | sed 's/[^0-9.]*//g'"], timeout=0.8)
    temp = (temp + "C") if temp else "-"

    fps_live = float(ctx.user.get("_fps_smooth", 0.0) or 0.0)

    return [
        f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Uptime: {uptime}",
        f"Wi-Fi SSID: {ssid}",
        f"IP wlan0: {ip_wlan}",
        f"IP eth0: {ip_eth}",
        f"Disk: {disk}",
        f"CPU temp: {temp}",
        f"Brightness: {prefs.get('brightness', 60)}%",
        f"FPS (live): {fps_live:.1f}",
        f"Target FPS: {prefs.get('target_fps', 15)}",
        f"Repo: {repo}",
        f"Git: {git_short}",
        "",
        "Tips:",
        "- Updater auto-detects your PocketR git repo.",
        "- Default target is /root/PocketR on Pi.",
    ]


def _list_items(prefs: Dict) -> List[Tuple[str, str]]:
    return [
        ("Controls & Help", ">"),
        ("Gallery Settings", ">"),
        ("Brightness", f"{int(prefs.get('brightness', 60))}%"),
        ("Target FPS", str(int(prefs.get("target_fps", 15)))),
        ("Show FPS", "ON" if prefs.get("show_fps", False) else "OFF"),
        ("Debug", ">"),
        ("Shutdown", ">"),
    ]


def _gallery_items(prefs: Dict) -> List[Tuple[str, str]]:
    return [
        ("Mode", str(prefs.get("gallery_mode", "SLIDE"))),
        ("Auto Scroll", "ON" if prefs.get("gallery_auto_scroll", True) else "OFF"),
        ("Auto Delay", f"{float(prefs.get('gallery_auto_seconds', 3.2)):.1f}s"),
        ("Swipe Time", f"{float(prefs.get('gallery_swipe_seconds', 0.22)):.2f}s"),
        ("Show Filename", "ON" if prefs.get("gallery_show_filename", True) else "OFF"),
    ]


def update(ctx, dt: float, ev: Dict[str, bool]) -> bool:
    prefs = _ensure_prefs(ctx)
    mode = str(ctx.user.get("_settings_mode", MODE_LIST))
    confirm = ("K1" in ev) or ("PRESS" in ev)

    if "K2" in ev:
        if mode == MODE_LIST:
            _save_prefs(ctx)
            return True
        ctx.user["_settings_mode"] = MODE_LIST
        return False

    if mode == MODE_HELP:
        s = int(ctx.user.get("_help_scroll", 0))
        if "UP" in ev:
            s -= 1
        if "DOWN" in ev:
            s += 1
        if "LEFT" in ev:
            s -= 4
        if "RIGHT" in ev:
            s += 4
        ctx.user["_help_scroll"] = max(0, s)
        return False

    if mode == MODE_DEBUG:
        if "UP" in ev:
            ctx.user["_debug_scroll"] = max(0, int(ctx.user.get("_debug_scroll", 0)) - 1)
        if "DOWN" in ev:
            ctx.user["_debug_scroll"] = int(ctx.user.get("_debug_scroll", 0)) + 1
        if "LEFT" in ev:
            ctx.user["_debug_scroll"] = max(0, int(ctx.user.get("_debug_scroll", 0)) - 4)
        if "RIGHT" in ev:
            ctx.user["_debug_scroll"] = int(ctx.user.get("_debug_scroll", 0)) + 4
        if confirm:
            ctx.user["_debug_cache"] = {"t": 0.0, "lines": []}
        return False

    if mode == MODE_SHUTDOWN:
        if confirm:
            ctx.request_poweroff()
        return False

    if mode == MODE_GALLERY:
        items = _gallery_items(prefs)
        sel = int(ctx.user.get("_settings_gallery_sel", 0))
        sel = max(0, min(sel, len(items) - 1))

        if "UP" in ev:
            sel = (sel - 1) % len(items)
        if "DOWN" in ev:
            sel = (sel + 1) % len(items)

        if sel == 0 and ("LEFT" in ev or "RIGHT" in ev or confirm):
            cur = _coerce_mode(prefs.get("gallery_mode", "SLIDE"))
            prefs["gallery_mode"] = "GRID" if cur == "SLIDE" else "SLIDE"

        elif sel == 1 and ("LEFT" in ev or "RIGHT" in ev or confirm):
            prefs["gallery_auto_scroll"] = not bool(prefs.get("gallery_auto_scroll", True))

        elif sel == 2:
            v = float(prefs.get("gallery_auto_seconds", 3.2))
            if "LEFT" in ev:
                prefs["gallery_auto_seconds"] = _step(v, -0.2, GALLERY_AUTO_MIN, GALLERY_AUTO_MAX, 1)
            if "RIGHT" in ev:
                prefs["gallery_auto_seconds"] = _step(v, 0.2, GALLERY_AUTO_MIN, GALLERY_AUTO_MAX, 1)

        elif sel == 3:
            v = float(prefs.get("gallery_swipe_seconds", 0.22))
            if "LEFT" in ev:
                prefs["gallery_swipe_seconds"] = _step(v, -0.02, GALLERY_SWIPE_MIN, GALLERY_SWIPE_MAX, 2)
            if "RIGHT" in ev:
                prefs["gallery_swipe_seconds"] = _step(v, 0.02, GALLERY_SWIPE_MIN, GALLERY_SWIPE_MAX, 2)

        elif sel == 4 and ("LEFT" in ev or "RIGHT" in ev or confirm):
            prefs["gallery_show_filename"] = not bool(prefs.get("gallery_show_filename", True))

        ctx.user["_settings_gallery_sel"] = sel

        h = int(getattr(ctx.disp, "height", 240))
        content_h = max(1, h - 66)
        visible = max(1, int(content_h // max(1, ITEM_H + ITEM_GAP)))
        scroll = int(ctx.user.get("_settings_gallery_scroll", 0))
        ctx.user["_settings_gallery_scroll"] = _ensure_visible(sel, scroll, len(items), visible)

        if ev:
            _save_prefs(ctx)
        return False

    # LIST mode
    items = _list_items(prefs)
    sel = int(ctx.user.get("_settings_sel", 0))
    sel = max(0, min(sel, len(items) - 1))

    if "UP" in ev:
        sel = (sel - 1) % len(items)
    if "DOWN" in ev:
        sel = (sel + 1) % len(items)

    if sel == 0 and confirm:
        ctx.user["_settings_mode"] = MODE_HELP

    elif sel == 1 and confirm:
        ctx.user["_settings_mode"] = MODE_GALLERY

    elif sel == 2:  # brightness
        if "LEFT" in ev:
            prefs["brightness"] = int(clamp(int(prefs.get("brightness", 60)) - BRIGHTNESS_STEP, 0, 100))
        if "RIGHT" in ev:
            prefs["brightness"] = int(clamp(int(prefs.get("brightness", 60)) + BRIGHTNESS_STEP, 0, 100))
        try:
            ctx.disp.bl_DutyCycle(int(prefs.get("brightness", 60)))
        except Exception:
            pass

    elif sel == 3:  # target fps
        if "LEFT" in ev:
            prefs["target_fps"] = int(clamp(int(prefs.get("target_fps", 15)) - 1, FPS_MIN, FPS_MAX))
        if "RIGHT" in ev:
            prefs["target_fps"] = int(clamp(int(prefs.get("target_fps", 15)) + 1, FPS_MIN, FPS_MAX))

    elif sel == 4 and confirm:  # show fps
        prefs["show_fps"] = not bool(prefs.get("show_fps", False))

    elif sel == 5 and confirm:
        ctx.user["_settings_mode"] = MODE_DEBUG
        ctx.user["_debug_scroll"] = 0
        ctx.user["_debug_cache"] = {"t": 0.0, "lines": []}

    elif sel == 6 and confirm:
        ctx.user["_settings_mode"] = MODE_SHUTDOWN

    ctx.user["_settings_sel"] = sel

    h = int(getattr(ctx.disp, "height", 240))
    content_h = max(1, h - 66)
    visible = max(1, int(content_h // max(1, ITEM_H + ITEM_GAP)))
    scroll = int(ctx.user.get("_settings_scroll", 0))
    ctx.user["_settings_scroll"] = _ensure_visible(sel, scroll, len(items), visible)

    if ev:
        _save_prefs(ctx)

    return False


def _draw_header(ctx, img: Image.Image, title: str, right: str = "") -> Tuple[Image.Image, int]:
    w, _h = img.size
    img = overlay_panel(
        img,
        (8, 8, w - 9, 42),
        radius=13,
        fill=(6, 6, 10, 170),
        outline=(255, 220, 210, 120),
        width=2,
    )
    d = ImageDraw.Draw(img)
    d.text((16, 15), title, font=ctx.font_m, fill=(255, 248, 244))
    if right:
        tw = int(d.textlength(right, font=ctx.font_s))
        d.text((w - 16 - tw, 18), right, font=ctx.font_s, fill=(220, 210, 205))
    return img, 52


def _draw_list_panel(ctx, img: Image.Image, y0: int) -> Tuple[Image.Image, Tuple[int, int, int, int]]:
    w, h = img.size
    rect = (8, y0, w - 9, h - 9)
    img = overlay_panel(
        img,
        rect,
        radius=16,
        fill=(6, 6, 10, 145),
        outline=(255, 220, 210, 90),
        width=2,
    )
    return img, rect


def _draw_menu_items(
    ctx,
    img: Image.Image,
    rect: Tuple[int, int, int, int],
    items: List[Tuple[str, str]],
    sel: int,
    scroll_key: str,
    mini_bars: Dict[int, float] | None = None,
) -> Image.Image:
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = rect

    content_x = x0 + 8
    content_y = y0 + 8
    content_w = (x1 - x0) - 16
    content_h = (y1 - y0) - 16

    slot = ITEM_H + ITEM_GAP
    visible = max(1, int(content_h // max(1, slot)))
    scroll = int(ctx.user.get(scroll_key, 0))
    scroll = max(0, min(scroll, max(0, len(items) - visible)))
    ctx.user[scroll_key] = scroll

    y = content_y
    for i in range(scroll, min(len(items), scroll + visible)):
        left, right = items[i]
        is_sel = i == sel

        if is_sel:
            d.rounded_rectangle([content_x, y, content_x + content_w, y + ITEM_H], radius=12, fill=(245, 232, 225))
            fg = (20, 12, 10)
            sub = (70, 42, 36)
            bar_bg = (195, 178, 170)
            bar_fg = (40, 20, 16)
        else:
            d.rounded_rectangle([content_x, y, content_x + content_w, y + ITEM_H], radius=12, fill=(15, 10, 12), outline=(255, 200, 190), width=1)
            fg = (244, 232, 226)
            sub = (220, 180, 170)
            bar_bg = (78, 54, 50)
            bar_fg = (240, 222, 214)

        label_x = content_x + 10
        label_y = y + 6
        d.text((label_x, label_y), left, font=ctx.font_m, fill=fg)
        tw = int(d.textlength(right, font=ctx.font_m))
        right_x = content_x + content_w - 10 - tw
        d.text((right_x, label_y), right, font=ctx.font_m, fill=sub)

        if mini_bars and i in mini_bars:
            frac = clamp(float(mini_bars.get(i, 0.0)), 0.0, 1.0)
            bar_x0 = label_x
            bar_x1 = right_x - 8
            if bar_x1 - bar_x0 >= 20:
                bar_y0 = y + ITEM_H - 10
                bar_y1 = bar_y0 + 4
                d.rounded_rectangle([bar_x0, bar_y0, bar_x1, bar_y1], radius=3, fill=bar_bg)
                fill_w = int((bar_x1 - bar_x0 - 2) * frac)
                if fill_w > 0:
                    d.rounded_rectangle([bar_x0 + 1, bar_y0 + 1, bar_x0 + 1 + fill_w, bar_y1 - 1], radius=2, fill=bar_fg)
        y += slot

    return img


def _render_help(ctx, prefs: Dict) -> Image.Image:
    img = app_background(ctx, dim_alpha=112)
    img, y0 = _draw_header(ctx, img, "Controls & Help", "B2 Back")
    img, rect = _draw_list_panel(ctx, img, y0)

    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = rect
    tx = x0 + 12
    ty = y0 + 12
    tw = (x1 - x0) - 24
    th = (y1 - y0) - 24

    wrapped: List[str] = []
    for line in _help_lines():
        if not line:
            wrapped.append("")
        else:
            wrapped.extend(wrap_text(d, line, ctx.font_s, max_width=tw))

    line_h = 15
    max_lines = max(1, int(th // line_h))
    scroll = max(0, int(ctx.user.get("_help_scroll", 0)))
    scroll = min(scroll, max(0, len(wrapped) - max_lines))
    ctx.user["_help_scroll"] = scroll

    y = ty
    for line in wrapped[scroll : scroll + max_lines]:
        d.text((tx, y), line, font=ctx.font_s, fill=(236, 228, 222))
        y += line_h

    pos = f"{scroll + 1}/{max(1, len(wrapped) - max_lines + 1)}"
    p_tw = int(d.textlength(pos, font=ctx.font_s))
    d.text((x1 - 10 - p_tw, y0 + 3), pos, font=ctx.font_s, fill=(210, 190, 182))
    return img


def _render_debug(ctx, prefs: Dict) -> Image.Image:
    img = app_background(ctx, dim_alpha=112)
    img, y0 = _draw_header(ctx, img, "Debug", "B2 Back")
    img, rect = _draw_list_panel(ctx, img, y0)

    cache = ctx.user.get("_debug_cache", {"t": 0.0, "lines": []})
    now = time.time()
    if (not cache.get("lines")) or (now - float(cache.get("t", 0.0)) > 3.0):
        cache = {"t": now, "lines": _build_debug_lines(ctx, prefs)}
        ctx.user["_debug_cache"] = cache

    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = rect
    tx = x0 + 12
    ty = y0 + 12
    tw = (x1 - x0) - 24
    th = (y1 - y0) - 24

    wrapped: List[str] = []
    for line in list(cache.get("lines", [])):
        if not line:
            wrapped.append("")
        else:
            wrapped.extend(wrap_text(d, line, ctx.font_s, max_width=tw))

    line_h = 15
    max_lines = max(1, int(th // line_h))
    scroll = max(0, int(ctx.user.get("_debug_scroll", 0)))
    scroll = min(scroll, max(0, len(wrapped) - max_lines))
    ctx.user["_debug_scroll"] = scroll

    y = ty
    for line in wrapped[scroll : scroll + max_lines]:
        d.text((tx, y), line, font=ctx.font_s, fill=(232, 225, 220))
        y += line_h

    pos = f"{scroll + 1}/{max(1, len(wrapped) - max_lines + 1)}"
    p_tw = int(d.textlength(pos, font=ctx.font_s))
    d.text((x1 - 10 - p_tw, y0 + 3), pos, font=ctx.font_s, fill=(210, 190, 182))
    d.text((x0 + 12, y0 + 3), "B1 refresh", font=ctx.font_s, fill=(210, 190, 182))
    return img


def _render_gallery_settings(ctx, prefs: Dict) -> Image.Image:
    items = _gallery_items(prefs)
    sel = int(ctx.user.get("_settings_gallery_sel", 0))

    img = app_background(ctx, dim_alpha=112)
    img, y0 = _draw_header(ctx, img, "Gallery Settings", "B2 Back")
    img, rect = _draw_list_panel(ctx, img, y0)
    auto_frac = (float(prefs.get("gallery_auto_seconds", 3.2)) - GALLERY_AUTO_MIN) / float(GALLERY_AUTO_MAX - GALLERY_AUTO_MIN)
    swipe_frac = (float(prefs.get("gallery_swipe_seconds", 0.22)) - GALLERY_SWIPE_MIN) / float(GALLERY_SWIPE_MAX - GALLERY_SWIPE_MIN)
    mini_bars = {
        2: auto_frac,
        3: swipe_frac,
    }
    img = _draw_menu_items(ctx, img, rect, items, sel, "_settings_gallery_scroll", mini_bars=mini_bars)
    return img


def _render_list(ctx, prefs: Dict) -> Image.Image:
    items = _list_items(prefs)
    sel = int(ctx.user.get("_settings_sel", 0))

    img = app_background(ctx, dim_alpha=112)
    fps_live = float(ctx.user.get("_fps_smooth", 0.0) or 0.0)
    right = f"{fps_live:.1f}fps" if prefs.get("show_fps", False) else "B2 Exit"
    img, y0 = _draw_header(ctx, img, "Settings", right)
    img, rect = _draw_list_panel(ctx, img, y0)
    bright_frac = float(prefs.get("brightness", 60)) / 100.0
    fps_frac = (float(prefs.get("target_fps", 15)) - FPS_MIN) / float(FPS_MAX - FPS_MIN)
    mini_bars = {
        2: bright_frac,
        3: fps_frac,
    }
    img = _draw_menu_items(ctx, img, rect, items, sel, "_settings_scroll", mini_bars=mini_bars)
    return img


def _render_shutdown(ctx, prefs: Dict) -> Image.Image:
    img = app_background(ctx, dim_alpha=122)
    img, y0 = _draw_header(ctx, img, "Shutdown", "B2 Cancel")
    img, rect = _draw_list_panel(ctx, img, y0)

    d = ImageDraw.Draw(img)
    x0, y0, x1, _y1 = rect
    tx = x0 + 14
    tw = (x1 - x0) - 28
    y = y0 + 16

    for line in wrap_text(d, "Are you sure you want to shut down Pocket-R now?", ctx.font_m, max_width=tw):
        d.text((tx, y), line, font=ctx.font_m, fill=(244, 232, 226))
        y += 18

    y += 8
    d.text((tx, y), "B1/PRESS: Confirm shutdown", font=ctx.font_s, fill=(230, 205, 196))
    y += 16
    d.text((tx, y), "B2: Return to settings", font=ctx.font_s, fill=(230, 205, 196))
    return img


def render(ctx) -> Image.Image:
    prefs = _ensure_prefs(ctx)
    mode = str(ctx.user.get("_settings_mode", MODE_LIST))

    if mode == MODE_HELP:
        return _render_help(ctx, prefs)

    if mode == MODE_GALLERY:
        return _render_gallery_settings(ctx, prefs)

    if mode == MODE_DEBUG:
        return _render_debug(ctx, prefs)

    if mode == MODE_SHUTDOWN:
        return _render_shutdown(ctx, prefs)

    return _render_list(ctx, prefs)
