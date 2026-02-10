from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Dict, List

from PIL import Image, ImageDraw

from ..ui_common import (
    breathe,
    dots,
    draw_bottom_hint,
    draw_progress_bar,
    draw_top_bar,
    fit_ellipsis,
    wrap_hard,
)


LOG_PATH = "/tmp/pocketr_update.log"
PREFS_FILE = "pocketr_settings.json"


def _prefs_path(ctx) -> str:
    base = getattr(ctx, "base_dir", ".")
    return os.path.join(base, PREFS_FILE)


def _read_prefs(ctx) -> Dict:
    try:
        with open(_prefs_path(ctx), "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        return {}


def _repo_path(ctx) -> str:
    prefs = _read_prefs(ctx)
    rp = str(prefs.get("repo_path", "") or "")
    return rp if rp else getattr(ctx, "base_dir", "")


def _run(cmd: List[str], timeout: float = 0.9) -> str:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, text=True)
        return (p.stdout or "").strip()
    except Exception:
        return ""


def _is_git_repo(path: str) -> bool:
    if not path:
        return False
    out = _run(["git", "-C", path, "rev-parse", "--is-inside-work-tree"], timeout=0.8)
    return out.strip() == "true"


def _resolve_git_root(path: str, max_child_depth: int = 3) -> str:
    if not path:
        return ""

    if _is_git_repo(path):
        return path

    # parents
    cur = os.path.abspath(path)
    for _ in range(6):
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        if _is_git_repo(parent):
            return parent
        cur = parent

    # children (bounded)
    root = os.path.abspath(path)
    if not os.path.isdir(root):
        return ""

    root_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, _filenames in os.walk(root):
        depth = dirpath.rstrip(os.sep).count(os.sep) - root_depth
        if depth > max_child_depth:
            dirnames[:] = []
            continue
        if ".git" in dirnames:
            return dirpath
        for bad in (".venv", "venv", "__pycache__", "node_modules"):
            if bad in dirnames:
                dirnames.remove(bad)

    return ""


def _tail(path: str, n: int = 10) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        return lines[-n:]
    except Exception:
        return []


def _reboot():
    # No return (system should reboot)
    for cmd in (
        ["/usr/bin/sudo", "/usr/bin/systemctl", "reboot"],
        ["/usr/bin/systemctl", "reboot"],
        ["/sbin/reboot"],
        ["reboot"],
    ):
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
    st.setdefault("repo", "")
    ctx.user["_updater"] = st
    return st


def init(ctx):
    # reset state each time we enter updater (feels safer)
    ctx.user["_updater"] = {"stage": "CONFIRM", "msg": "", "reboot_at": 0.0, "repo": ""}


def update(ctx, dt: float, ev: Dict[str, bool]) -> bool:
    """Return True to go back to the OS home."""
    st = _state(ctx)
    stage = st.get("stage", "CONFIRM")

    confirm = ("K1" in ev) or ("PRESS" in ev)

    # Back gesture on most screens
    if stage in ("CONFIRM", "ERROR") and "K2" in ev:
        return True

    if stage == "CONFIRM":
        repo = _repo_path(ctx)
        st["repo"] = repo
        st["repo_resolved"] = _resolve_git_root(repo)

        if confirm:
            resolved = str(st.get("repo_resolved") or "")
            if not resolved:
                st["stage"] = "ERROR"
                st["msg"] = (
                    f"Could not find a git repo under:\n{repo}\n\n"
                    "Fix: Settings → Repo Path (or Auto-find Repo)\n"
                    "Tip: clone Pocket-R with git so Update can pull."
                )
                return False

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
                    ["bash", script_path, resolved],
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
            st["reboot_at"] = time.time() + 2.0
        else:
            st["stage"] = "ERROR"
            st["msg"] = f"Update failed (code {rc})."
        return False

    if stage == "DONE":
        if time.time() >= float(st.get("reboot_at", 0.0)):
            _reboot()
        return False

    if stage == "ERROR":
        if confirm:
            st["stage"] = "CONFIRM"
            st["msg"] = ""
        return False

    st["stage"] = "CONFIRM"
    return False


def render(ctx) -> Image.Image:
    w, h = int(ctx.disp.width), int(ctx.disp.height)
    img = Image.new("RGB", (w, h), (0, 0, 0))

    st = _state(ctx)
    stage = st.get("stage", "CONFIRM")

    y0 = draw_top_bar(img, "Update", ctx.font_l)
    d = ImageDraw.Draw(img)

    repo = st.get("repo") or _repo_path(ctx)
    resolved = st.get("repo_resolved") or ""

    if stage == "CONFIRM":
        d.text((10, y0), "This will git pull and reboot.", font=ctx.font_m, fill=(220, 220, 220))

        # Fit repo line within the screen
        repo_line = f"Repo: {resolved or repo}"
        repo_line = fit_ellipsis(d, repo_line, ctx.font_s, w - 20)
        d.text((10, y0 + 22), repo_line, font=ctx.font_s, fill=(170, 170, 170))

        y = y0 + 54
        # little warning box
        d.rounded_rectangle([10, y, w - 10, y + 78], radius=16, outline=(70, 70, 80), width=2)
        d.text((22, y + 14), "Do not power off during update.", font=ctx.font_m, fill=(235, 235, 235))
        d.text((22, y + 40), "If update fails: Settings → Repo Path", font=ctx.font_s, fill=(180, 180, 180))

        draw_bottom_hint(img, "K1/PRESS confirm · K2 cancel", ctx.font_s)
        return img

    if stage == "RUNNING":
        d.text((10, y0), st.get("msg", "Updating...") + dots(time.time()), font=ctx.font_m, fill=(220, 220, 220))

        # progress bar (just a spinner-ish pulse)
        frac = 0.15 + 0.70 * breathe(time.time(), 1.6)
        draw_progress_bar(d, 10, y0 + 30, w - 20, 12, frac)

        y = y0 + 54
        max_lines = max(1, int((h - y - 24 - 6) // 16))
        shown = 0
        for raw in _tail(LOG_PATH, n=12):
            for line in wrap_hard(d, raw, ctx.font_s, w - 20):
                if shown >= max_lines:
                    break
                d.text((10, y), line, font=ctx.font_s, fill=(180, 180, 180))
                y += 16
                shown += 1
            if shown >= max_lines:
                break

        draw_bottom_hint(img, "Updating… please wait", ctx.font_s)
        return img

    if stage == "DONE":
        d.text((10, y0), st.get("msg", "Rebooting..."), font=ctx.font_m, fill=(235, 235, 235))
        d.text((10, y0 + 24), "If it doesn't restart, flip the power switch.", font=ctx.font_s, fill=(180, 180, 180))
        draw_progress_bar(d, 10, y0 + 54, w - 20, 12, 1.0)
        return img

    if stage == "ERROR":
        d.text((10, y0), "Update error", font=ctx.font_m, fill=(255, 90, 90))
        msg = st.get("msg", "")
        y = y0 + 22
        # Wrap error message to screen width
        for raw in msg.splitlines():
            for line in wrap_hard(d, raw, ctx.font_s, w - 20):
                d.text((10, y), line, font=ctx.font_s, fill=(220, 220, 220))
                y += 16
                if y >= h - 24 - 72:
                    break
            if y >= h - 24 - 72:
                break

        y += 6
        max_lines = max(1, int((h - y - 24 - 6) // 16))
        shown = 0
        for raw in _tail(LOG_PATH, n=12):
            for line in wrap_hard(d, raw, ctx.font_s, w - 20):
                if shown >= max_lines:
                    break
                d.text((10, y), line, font=ctx.font_s, fill=(170, 170, 170))
                y += 16
                shown += 1
            if shown >= max_lines:
                break

        draw_bottom_hint(img, "K1/PRESS retry · K2 back", ctx.font_s)
        return img

    return img
