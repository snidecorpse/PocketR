from __future__ import annotations

import os
import re
import subprocess
import time
from typing import Dict, Optional

from PIL import Image, ImageDraw


def _run(cmd, timeout: float = 0.6) -> str:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, text=True)
        return (p.stdout or "").strip()
    except Exception:
        return ""


def _uptime_str() -> str:
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            secs = float(f.read().split()[0])
        m = int(secs // 60)
        h = m // 60
        m = m % 60
        return f"{h}h {m}m"
    except Exception:
        return "?"


def _ip_for(iface: str) -> str:
    out = _run(["ip", "-4", "addr", "show", iface], timeout=0.6)
    m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out)
    return m.group(1) if m else "-"


def _ssid() -> str:
    # works on many Pi setups; fallback is blank
    s = _run(["iwgetid", "-r"], timeout=0.6)
    return s if s else "-"


def _git_short(ctx) -> str:
    base = getattr(ctx, "base_dir", "")
    if not base:
        return "-"
    out = _run(["git", "-C", base, "rev-parse", "--short", "HEAD"], timeout=0.8)
    return out if out else "-"


def _disk_root() -> str:
    out = _run(["df", "-h", "/"], timeout=0.8)
    lines = out.splitlines()
    if len(lines) < 2:
        return "-"
    parts = lines[1].split()
    # Filesystem Size Used Avail Use% Mounted
    if len(parts) >= 5:
        return f"{parts[2]}/{parts[1]} ({parts[4]})"
    return "-"


def update(ctx, dt: float, ev: Dict[str, bool]) -> bool:
    # K2 = back
    if "K2" in ev:
        return True

    # K1 = refresh (optional)
    if "K1" in ev:
        ctx.user.pop("_settings_cache", None)

    return False


def render(ctx) -> Image.Image:
    w, h = int(ctx.disp.width), int(ctx.disp.height)
    img = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(img)

    # Cache expensive lookups a bit
    cache = ctx.user.get("_settings_cache")
    now = time.time()
    if not cache or (now - float(cache.get("t", 0))) > 2.5:
        cache = {
            "t": now,
            "ssid": _ssid(),
            "ip_wlan0": _ip_for("wlan0"),
            "ip_eth0": _ip_for("eth0"),
            "uptime": _uptime_str(),
            "disk": _disk_root(),
            "git": _git_short(ctx),
        }
        ctx.user["_settings_cache"] = cache

    d.text((12, 12), "Settings / Debug", font=ctx.font_l, fill=(255, 255, 255))

    y = 52
    lines = [
        f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Uptime: {cache['uptime']}",
        f"Wi-Fi: {cache['ssid']}",
        f"IP wlan0: {cache['ip_wlan0']}",
        f"IP eth0: {cache['ip_eth0']}",
        f"Disk: {cache['disk']}",
        f"Git: {cache['git']}",
    ]

    for line in lines:
        d.text((12, y), line, font=ctx.font_m, fill=(220, 220, 220))
        y += 20

    d.text((12, h - 22), "K1: refresh   K2: back", font=ctx.font_s, fill=(160, 160, 160))
    return img
