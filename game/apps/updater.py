from __future__ import annotations

import os
import subprocess
import time
from typing import Dict, List

from PIL import Image, ImageDraw


LOG_PATH = "/tmp/pocketr_update.log"


def _tail(path: str, n: int = 8) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        return lines[-n:]
    except Exception:
        return []


def _reboot():
    # No return (system should reboot)
    for cmd in (["/usr/bin/systemctl", "reboot"], ["/sbin/reboot"], ["reboot"]):
        try:
            subprocess.Popen(cmd)
            return
        except Exception:
            pass


def _state(ctx) -> Dict:
    st = ctx.user.get("_updater", None)
    if not isinstance(st, dict):
        st = {}
    st.setdefault("stage", "CONFIRM")  # CONFIRM / RUNNING / DONE / ERROR
    st.setdefault("msg", "")
    st.setdefault("reboot_at", 0.0)
    ctx.user["_updater"] = st
    return st


def update(ctx, dt: float, ev: Dict[str, bool]) -> bool:
    """Return True to go back to the OS home."""
    st = _state(ctx)
    stage = st.get("stage", "CONFIRM")

    # Cancel / back gesture on confirm + error screens
    if stage in ("CONFIRM", "ERROR") and "K2" in ev:
        return True

    # Confirm screen
    if stage == "CONFIRM":
        if "K1" in ev:
            # Start update subprocess
            try:
                # reset log
                try:
                    with open(LOG_PATH, "w", encoding="utf-8"):
                        pass
                except Exception:
                    pass

                script_path = os.path.join(ctx.game_dir, "scripts", "update_repo.sh")
                log_f = open(LOG_PATH, "a", encoding="utf-8")
                proc = subprocess.Popen(
                    ["bash", script_path, ctx.base_dir],
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                )
                ctx.user["_updater_proc"] = proc
                ctx.user["_updater_logf"] = log_f

                st["stage"] = "RUNNING"
                st["msg"] = "Updating from git..."
            except Exception as e:
                st["stage"] = "ERROR"
                st["msg"] = f"Failed to start update: {e}"
        return False

    # Running screen
    if stage == "RUNNING":
        proc = ctx.user.get("_updater_proc", None)
        if proc is None:
            st["stage"] = "ERROR"
            st["msg"] = "Update process missing"
            return False

        rc = proc.poll()
        if rc is None:
            return False

        # Close log file handle
        try:
            log_f = ctx.user.pop("_updater_logf", None)
            if log_f:
                log_f.close()
        except Exception:
            pass

        if rc == 0:
            st["stage"] = "DONE"
            st["msg"] = "Update complete. Rebooting..."
            st["reboot_at"] = time.time() + 1.0
        else:
            st["stage"] = "ERROR"
            st["msg"] = f"Update failed (code {rc})."
        return False

    # Done -> reboot
    if stage == "DONE":
        if time.time() >= float(st.get("reboot_at", 0.0)):
            _reboot()
        return False

    # Error screen
    if stage == "ERROR":
        if "K1" in ev:
            # retry
            st["stage"] = "CONFIRM"
            st["msg"] = ""
        return False

    # fallback
    st["stage"] = "CONFIRM"
    return False


def render(ctx) -> Image.Image:
    w, h = int(ctx.disp.width), int(ctx.disp.height)
    img = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(img)

    st = _state(ctx)
    stage = st.get("stage", "CONFIRM")

    d.text((12, 12), "Update", font=ctx.font_l, fill=(255, 255, 255))

    if stage == "CONFIRM":
        lines = [
            "This will:",
            "  1) git pull the repo", 
            "  2) reboot Pocket-R", 
            "",
            "K1: confirm", 
            "K2: cancel", 
        ]
        y = 52
        for line in lines:
            d.text((12, y), line, font=ctx.font_m, fill=(220, 220, 220))
            y += 20
        return img

    if stage == "RUNNING":
        d.text((12, 52), st.get("msg", "Updating..."), font=ctx.font_m, fill=(220, 220, 220))
        y = 82
        for line in _tail(LOG_PATH, n=8):
            d.text((12, y), line[:40], font=ctx.font_s, fill=(180, 180, 180))
            y += 16
        d.text((12, h - 22), "Updating... (do not power off)", font=ctx.font_s, fill=(160, 160, 160))
        return img

    if stage == "DONE":
        d.text((12, 52), st.get("msg", "Rebooting..."), font=ctx.font_m, fill=(255, 255, 255))
        d.text((12, 78), "If it doesn't restart,", font=ctx.font_m, fill=(200, 200, 200))
        d.text((12, 98), "flip the power switch.", font=ctx.font_m, fill=(200, 200, 200))
        return img

    if stage == "ERROR":
        d.text((12, 52), "Update error", font=ctx.font_m, fill=(255, 80, 80))
        d.text((12, 76), st.get("msg", ""), font=ctx.font_s, fill=(220, 220, 220))
        y = 112
        for line in _tail(LOG_PATH, n=6):
            d.text((12, y), line[:40], font=ctx.font_s, fill=(180, 180, 180))
            y += 16
        d.text((12, h - 22), "K1: retry   K2: back", font=ctx.font_s, fill=(160, 160, 160))
        return img

    return img
