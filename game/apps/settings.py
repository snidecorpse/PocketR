from __future__ import annotations

import json
import os
import re
import subprocess
import time
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw

from ..ui_common import (
    clamp,
    draw_bottom_hint,
    draw_list_item,
    draw_progress_bar,
    draw_top_bar,
    wrap_text,
)


PREFS_FILE = "pocketr_settings.json"  # stored beside app.py (ctx.base_dir)

# Value ranges
BRIGHTNESS_STEP = 5
FPS_MIN, FPS_MAX = 5, 30

# UI sizing (fits 240x240 and smaller, with scroll)
ITEM_H = 36
ITEM_GAP = 6
BOTTOM_BAR_H = 24


def _run(cmd: List[str], timeout: float = 0.8) -> str:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, text=True)
        return (p.stdout or "").strip()
    except Exception:
        return ""


def _read_json(path: str) -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _write_json(path: str, data: Dict) -> None:
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        pass


def _prefs_path(ctx) -> str:
    return os.path.join(getattr(ctx, "base_dir", "."), PREFS_FILE)


def _default_repo_candidates(ctx) -> List[str]:
    base = getattr(ctx, "base_dir", "")
    home = os.path.expanduser("~")

    # common places
    candidates = [
        base,
        os.path.join(home, "PocketR"),
        os.path.join(home, "pocketr"),
        os.path.join(home, "Pocket-R"),
        os.path.join(home, "PocketR"),
        "/opt/pocketr",
        "/home/pi/pocketr",
        "/home/pizero/pocketr",
        "/home/pizero/PocketR",
        "/home/pizero2/PocketR",
    ]

    # Also try a few common names under /home/* (lightweight glob)
    try:
        import glob

        for pat in ("/home/*/PocketR", "/home/*/Pocket-R", "/home/*/pocketr", "/home/*/PocketR"):
            for p in glob.glob(pat):
                candidates.append(p)
    except Exception:
        pass

    # de-dupe while preserving order
    out: List[str] = []
    for p in candidates:
        if p and p not in out:
            out.append(p)

    # keep only existing dirs (but always include base)
    exist = []
    for p in out:
        if p == base or os.path.isdir(p):
            exist.append(p)
    return exist


def _is_git_repo(path: str) -> bool:
    if not path:
        return False
    out = _run(["git", "-C", path, "rev-parse", "--is-inside-work-tree"], timeout=0.7)
    return out.strip() == "true"


def _git_root(path: str) -> str:
    """Return git top-level for a path, or empty string."""
    if not path:
        return ""
    out = _run(["git", "-C", path, "rev-parse", "--show-toplevel"], timeout=0.8)
    p = (out or "").strip()
    return p if p and os.path.isdir(p) else ""


def _short_path(p: str, max_len: int = 22) -> str:
    if not p:
        return "-"
    if len(p) <= max_len:
        return p
    return "…" + p[-(max_len - 1):]


def _ensure_prefs(ctx) -> Dict:
    if isinstance(ctx.user.get("_prefs"), dict):
        return ctx.user["_prefs"]

    prefs = {
        "brightness": 60,
        "target_fps": 15,
        "show_fps": False,
        "repo_path": getattr(ctx, "base_dir", ""),
    }

    # load persisted
    path = _prefs_path(ctx)
    disk = _read_json(path)
    if isinstance(disk, dict):
        prefs.update({k: disk.get(k, v) for k, v in prefs.items()})

    # coerce
    try:
        prefs["brightness"] = int(clamp(float(prefs.get("brightness", 60)), 0, 100))
    except Exception:
        prefs["brightness"] = 60

    try:
        prefs["target_fps"] = int(clamp(float(prefs.get("target_fps", 15)), FPS_MIN, FPS_MAX))
    except Exception:
        prefs["target_fps"] = 15

    prefs["show_fps"] = bool(prefs.get("show_fps", False))

    rp = str(prefs.get("repo_path", "") or "")
    # If possible, normalize to the git repo root (fixes wrong paths / CWD confusion)
    root = _git_root(rp) or _git_root(getattr(ctx, "base_dir", ""))
    prefs["repo_path"] = root if root else rp

    ctx.user["_prefs"] = prefs
    return prefs


def _save_prefs(ctx) -> None:
    prefs = _ensure_prefs(ctx)
    _write_json(_prefs_path(ctx), prefs)


def init(ctx):
    prefs = _ensure_prefs(ctx)

    # Apply brightness immediately
    try:
        ctx.disp.bl_DutyCycle(int(prefs.get("brightness", 60)))
    except Exception:
        pass

    ctx.user.setdefault("_settings_mode", "LIST")
    ctx.user.setdefault("_settings_sel", 0)
    ctx.user.setdefault("_settings_scroll", 0)
    ctx.user.setdefault("_debug_scroll", 0)
    ctx.user.setdefault("_debug_cache", {"t": 0.0, "lines": []})


def _build_debug_lines(ctx, prefs: Dict) -> List[str]:
    repo = str(prefs.get("repo_path", "") or getattr(ctx, "base_dir", ""))

    ssid = _run(["iwgetid", "-r"], timeout=0.7) or "-"
    ip_wlan = _run(["bash", "-lc", "ip -4 addr show wlan0 | sed -n 's/.*inet \\([0-9.]*\\).*/\\1/p' | head -n1"], timeout=0.8) or "-"
    ip_eth = _run(["bash", "-lc", "ip -4 addr show eth0 | sed -n 's/.*inet \\([0-9.]*\\).*/\\1/p' | head -n1"], timeout=0.8) or "-"

    # uptime
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

    # disk
    disk = "-"
    df = _run(["df", "-h", "/"], timeout=0.9)
    lines = df.splitlines()
    if len(lines) >= 2:
        parts = lines[1].split()
        if len(parts) >= 5:
            disk = f"{parts[2]}/{parts[1]} ({parts[4]})"

    # temp (works on many Pi installs)
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
        "- If Update fails, set Repo Path to your git clone.",
        "- You can install from a git clone (recommended).",
    ]


def _list_items(ctx, prefs: Dict) -> List[Tuple[str, str]]:
    repo = _short_path(str(prefs.get("repo_path", "") or "-"), 24)
    return [
        ("Brightness", f"{int(prefs.get('brightness', 60))}%"),
        ("Target FPS", str(int(prefs.get("target_fps", 15)))),
        ("Show FPS", "ON" if prefs.get("show_fps", False) else "OFF"),
        ("Repo Path", repo),
        ("Debug", ">"),
    ]


def update(ctx, dt: float, ev: Dict[str, bool]) -> bool:
    prefs = _ensure_prefs(ctx)

    mode = str(ctx.user.get("_settings_mode", "LIST"))

    # global back
    if "K2" in ev:
        if mode == "DEBUG":
            ctx.user["_settings_mode"] = "LIST"
            return False
        _save_prefs(ctx)
        return True

    confirm = ("K1" in ev) or ("PRESS" in ev)

    if mode == "DEBUG":
        # scroll debug page
        if "UP" in ev:
            ctx.user["_debug_scroll"] = max(0, int(ctx.user.get("_debug_scroll", 0)) - 1)
        if "DOWN" in ev:
            ctx.user["_debug_scroll"] = int(ctx.user.get("_debug_scroll", 0)) + 1
        if "LEFT" in ev:
            ctx.user["_debug_scroll"] = max(0, int(ctx.user.get("_debug_scroll", 0)) - 5)
        if "RIGHT" in ev:
            ctx.user["_debug_scroll"] = int(ctx.user.get("_debug_scroll", 0)) + 5

        if confirm:
            ctx.user["_debug_cache"] = {"t": 0.0, "lines": []}  # force refresh
        return False

    # LIST mode
    items = _list_items(ctx, prefs)
    sel = int(ctx.user.get("_settings_sel", 0))
    sel = max(0, min(sel, len(items) - 1))

    if "UP" in ev:
        sel = (sel - 1) % len(items)
    if "DOWN" in ev:
        sel = (sel + 1) % len(items)

    # adjust values
    if sel == 0:  # brightness
        if "LEFT" in ev:
            prefs["brightness"] = int(clamp(int(prefs.get("brightness", 60)) - BRIGHTNESS_STEP, 0, 100))
        if "RIGHT" in ev:
            prefs["brightness"] = int(clamp(int(prefs.get("brightness", 60)) + BRIGHTNESS_STEP, 0, 100))
        try:
            ctx.disp.bl_DutyCycle(int(prefs.get("brightness", 60)))
        except Exception:
            pass

    elif sel == 1:  # fps target
        if "LEFT" in ev:
            prefs["target_fps"] = int(clamp(int(prefs.get("target_fps", 15)) - 1, FPS_MIN, FPS_MAX))
        if "RIGHT" in ev:
            prefs["target_fps"] = int(clamp(int(prefs.get("target_fps", 15)) + 1, FPS_MIN, FPS_MAX))

    elif sel == 2:  # show fps
        if confirm:
            prefs["show_fps"] = not bool(prefs.get("show_fps", False))

    elif sel == 3:  # repo path
        candidates = _default_repo_candidates(ctx)
        cur = str(prefs.get("repo_path", "") or "")
        if cur not in candidates and cur:
            candidates.insert(0, cur)

        if candidates:
            i = candidates.index(cur) if cur in candidates else 0
            if "LEFT" in ev:
                i = (i - 1) % len(candidates)
                prefs["repo_path"] = candidates[i]
            if "RIGHT" in ev:
                i = (i + 1) % len(candidates)
                prefs["repo_path"] = candidates[i]
            if confirm and not prefs.get("repo_path"):
                prefs["repo_path"] = getattr(ctx, "base_dir", "")

    elif sel == 4:  # debug
        if confirm:
            ctx.user["_settings_mode"] = "DEBUG"
            ctx.user["_debug_scroll"] = 0
            ctx.user["_debug_cache"] = {"t": 0.0, "lines": []}

    ctx.user["_settings_sel"] = sel

    # keep selection visible (scroll window)
    w = int(getattr(ctx.disp, "width", 240))
    h = int(getattr(ctx.disp, "height", 240))
    # match draw_top_bar sizing: bar_h + 8
    top_bar_h = 34 if h >= 200 else 28
    y0 = top_bar_h + 8
    content_h = max(0, (h - BOTTOM_BAR_H) - y0)
    slot = ITEM_H + ITEM_GAP
    visible = max(1, int(content_h // max(1, slot)))
    scroll = int(ctx.user.get("_settings_scroll", 0))
    if sel < scroll:
        scroll = sel
    elif sel >= scroll + visible:
        scroll = sel - visible + 1
    scroll = max(0, min(scroll, max(0, len(items) - visible)))
    ctx.user["_settings_scroll"] = scroll

    # save occasionally
    if ev:
        _save_prefs(ctx)

    return False


def render(ctx) -> Image.Image:
    w, h = int(ctx.disp.width), int(ctx.disp.height)
    img = Image.new("RGB", (w, h), (0, 0, 0))

    prefs = _ensure_prefs(ctx)
    mode = str(ctx.user.get("_settings_mode", "LIST"))

    if mode == "DEBUG":
        y0 = draw_top_bar(img, "Debug", ctx.font_l)
        d = ImageDraw.Draw(img)

        cache = ctx.user.get("_debug_cache", {"t": 0.0, "lines": []})
        now = time.time()
        if (not cache.get("lines")) or (now - float(cache.get("t", 0.0)) > 3.0):
            cache = {"t": now, "lines": _build_debug_lines(ctx, prefs)}
            ctx.user["_debug_cache"] = cache

        lines: List[str] = list(cache.get("lines", []))

        # wrap long lines
        wrapped: List[str] = []
        for line in lines:
            if not line:
                wrapped.append("")
                continue
            wrapped.extend(wrap_text(d, line, ctx.font_s, max_width=w - 20))

        scroll = max(0, int(ctx.user.get("_debug_scroll", 0)))
        max_lines = max(0, int((h - y0 - 28) // 16))
        scroll = min(scroll, max(0, len(wrapped) - max_lines))
        ctx.user["_debug_scroll"] = scroll

        y = y0
        for line in wrapped[scroll : scroll + max_lines]:
            d.text((10, y), line, font=ctx.font_s, fill=(200, 200, 200))
            y += 16

        draw_bottom_hint(img, "UP/DOWN scroll · K1 refresh · K2 back", ctx.font_s)
        return img

    # LIST
    items = _list_items(ctx, prefs)
    sel = int(ctx.user.get("_settings_sel", 0))
    y0 = draw_top_bar(img, "Settings", ctx.font_l, right_text=f"{sel+1}/{len(items)}")
    d = ImageDraw.Draw(img)

    # list geometry + scrolling
    scroll = int(ctx.user.get("_settings_scroll", 0))
    x = 10
    w_item = w - 20
    slot = ITEM_H + ITEM_GAP
    content_h = max(0, (h - BOTTOM_BAR_H) - y0)
    visible = max(1, int(content_h // max(1, slot)))
    scroll = max(0, min(scroll, max(0, len(items) - visible)))
    ctx.user["_settings_scroll"] = scroll

    y = y0
    for row, i in enumerate(range(scroll, min(len(items), scroll + visible))):
        left, right = items[i]
        draw_list_item(d, x, y, w_item, ITEM_H, left, right, ctx.font_m, selected=(i == sel))

        # sliders for brightness + fps
        if i == 0:
            frac = float(prefs.get("brightness", 60)) / 100.0
            draw_progress_bar(d, x + 12, y + ITEM_H - 12, w_item - 24, 8, frac)
        if i == 1:
            frac = (float(prefs.get("target_fps", 15)) - FPS_MIN) / float(FPS_MAX - FPS_MIN)
            draw_progress_bar(d, x + 12, y + ITEM_H - 12, w_item - 24, 8, frac)

        y += slot

    # tiny status line
    fps_live = float(ctx.user.get("_fps_smooth", 0.0) or 0.0)
    status = f"FPS {fps_live:.1f}" if prefs.get("show_fps", False) else ""
    hint = "K1/PRESS select · LEFT/RIGHT adjust · K2 back"
    draw_bottom_hint(img, (hint + (" · " + status if status else "")), ctx.font_s)
    return img
