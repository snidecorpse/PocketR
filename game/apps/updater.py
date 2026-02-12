from __future__ import annotations

import os
import subprocess
import time
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw

from ..persistence import ensure_data_dir, read_json, write_json_atomic
from ..ui_common import (
    app_background,
    breathe,
    dots,
    draw_progress_bar,
    overlay_panel,
    wrap_text,
)


LOG_PATH = "/tmp/pocketr_update.log"
REPO_SCAN_SECONDS = 1.5
META_REL_PATH = "update/last_update.json"


def _run(cmd: List[str], timeout: float = 1.0) -> str:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, text=True)
        return (p.stdout or "").strip()
    except Exception:
        return ""


def _git_root(path: str) -> str:
    if not path:
        return ""
    out = _run(["git", "-C", path, "rev-parse", "--show-toplevel"], timeout=1.0)
    p = (out or "").strip()
    return p if p and os.path.isdir(p) else ""


def _is_git_repo(path: str) -> bool:
    if not path:
        return False
    out = _run(["git", "-C", path, "rev-parse", "--is-inside-work-tree"], timeout=0.8)
    return out.strip() == "true"


def _tail(path: str, n: int = 10) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        return lines[-n:]
    except Exception:
        return []


def _read_all_lines(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except Exception:
        return []


def _reboot():
    try:
        os.sync()
    except Exception:
        pass

    for cmd in (
        ["/usr/bin/systemctl", "reboot"],
        ["/usr/bin/sudo", "/usr/bin/systemctl", "reboot"],
        ["/sbin/reboot"],
        ["reboot"],
    ):
        try:
            subprocess.Popen(cmd)
            return
        except Exception:
            pass


def _repo_candidates(ctx) -> List[str]:
    base = str(getattr(ctx, "base_dir", "") or "")
    game_dir = str(getattr(ctx, "game_dir", "") or "")
    cwd = os.getcwd()

    raw: List[str] = [
        os.environ.get("POCKETR_REPO", ""),
        "/root/PocketR",
        "/root/pocketr",
        base,
        os.path.dirname(game_dir) if game_dir else "",
        cwd,
        "/home/pi/PocketR",
        "/home/pi/pocketr",
        "/home/pizero/PocketR",
        "/home/pizero/pocketr",
        "/home/pizero2/PocketR",
        "/opt/pocketr",
    ]

    out: List[str] = []
    seen = set()

    for p in raw:
        if not p:
            continue
        p = os.path.abspath(os.path.expanduser(p))
        if p not in seen:
            seen.add(p)
            out.append(p)

        child = os.path.join(p, "PocketR")
        if child not in seen:
            seen.add(child)
            out.append(child)

    return out


def _discover_repo(ctx) -> Tuple[str, List[str]]:
    checked: List[str] = []

    for cand in _repo_candidates(ctx):
        if cand not in checked:
            checked.append(cand)

        if not os.path.isdir(cand):
            continue

        root = _git_root(cand)
        if root and _is_git_repo(root):
            return root, checked

        if _is_git_repo(cand):
            return cand, checked

    return "", checked


def _discover_repo_cached(ctx) -> Tuple[str, List[str]]:
    now = time.time()
    cache = ctx.user.get("_updater_repo_cache", None)
    if isinstance(cache, dict):
        age = now - float(cache.get("t", 0.0))
        repo = str(cache.get("repo", "") or "")
        checked = cache.get("checked", [])
        if age < REPO_SCAN_SECONDS and isinstance(checked, list):
            return repo, checked

    repo, checked = _discover_repo(ctx)
    ctx.user["_updater_repo_cache"] = {"t": now, "repo": repo, "checked": checked}
    return repo, checked


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _last_update_default() -> Dict:
    return {
        "last_run": "",
        "repo_path": "",
        "status": "never",
        "return_code": None,
        "message": "",
        "branch": "",
        "pre_sha": "",
        "post_sha": "",
    }


def _load_last_update(ctx) -> Dict:
    ensure_data_dir(ctx)
    data = read_json(ctx, META_REL_PATH, _last_update_default())
    if not isinstance(data, dict):
        return _last_update_default()
    out = _last_update_default()
    out.update(data)
    return out


def _save_last_update(ctx, data: Dict) -> None:
    payload = _last_update_default()
    payload.update(data or {})
    try:
        write_json_atomic(ctx, META_REL_PATH, payload)
    except Exception:
        pass


def _parse_markers(path: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw in _read_all_lines(path):
        line = str(raw).strip()
        if not line.startswith("POCKETR_META_"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _state(ctx) -> Dict:
    st = ctx.user.get("_updater", None)
    if not isinstance(st, dict):
        st = {}
    st.setdefault("stage", "CONFIRM")  # CONFIRM / RUNNING / DONE / ERROR
    st.setdefault("msg", "")
    st.setdefault("reboot_at", 0.0)
    st.setdefault("repo", "")
    st.setdefault("checked", [])
    st.setdefault("last", _load_last_update(ctx))
    ctx.user["_updater"] = st
    return st


def init(ctx):
    last = _load_last_update(ctx)
    if str(last.get("status", "never") or "never") == "never":
        _save_last_update(ctx, last)
    ctx.user["_updater"] = {
        "stage": "CONFIRM",
        "msg": "",
        "reboot_at": 0.0,
        "repo": "",
        "checked": [],
        "last": last,
    }
    ctx.user["_updater_repo_cache"] = {"t": 0.0, "repo": "", "checked": []}


def _record_update_result(ctx, repo_root: str, status: str, rc, msg: str) -> Dict:
    meta = _load_last_update(ctx)
    markers = _parse_markers(LOG_PATH)

    meta["last_run"] = _now_iso()
    meta["repo_path"] = repo_root
    meta["status"] = status
    meta["return_code"] = rc
    meta["message"] = msg
    meta["branch"] = markers.get("POCKETR_META_BRANCH", meta.get("branch", ""))
    meta["pre_sha"] = markers.get("POCKETR_META_PRE_SHA", meta.get("pre_sha", ""))
    meta["post_sha"] = markers.get("POCKETR_META_POST_SHA", meta.get("post_sha", ""))

    _save_last_update(ctx, meta)
    return meta


def update(ctx, dt: float, ev: Dict[str, bool]) -> bool:
    st = _state(ctx)
    stage = st.get("stage", "CONFIRM")
    confirm = ("K1" in ev) or ("PRESS" in ev)

    if stage in ("CONFIRM", "ERROR") and "K2" in ev:
        return True

    if stage == "CONFIRM":
        repo_root, checked = _discover_repo_cached(ctx)
        st["repo"] = repo_root
        st["checked"] = checked[-8:]

        if confirm:
            if not repo_root or not _is_git_repo(repo_root):
                st["stage"] = "ERROR"
                st["msg"] = (
                    "Update source not found."
                    "\nMake sure PocketR is installed as a git clone."
                    "\nIf needed, reinstall from GitHub."
                )
                return False

            try:
                try:
                    with open(LOG_PATH, "w", encoding="utf-8"):
                        pass
                except Exception:
                    pass

                script_path = os.path.join(ctx.game_dir, "scripts", "update_repo.sh")
                log_f = open(LOG_PATH, "a", encoding="utf-8")
                env = os.environ.copy()
                env["POCKETR_REPO"] = repo_root

                proc = subprocess.Popen(
                    ["bash", script_path, repo_root],
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    env=env,
                )
                ctx.user["_updater_proc"] = proc
                ctx.user["_updater_logf"] = log_f

                # Store running state to survive restarts with last known context.
                running = {
                    "last_run": _now_iso(),
                    "repo_path": repo_root,
                    "status": "running",
                    "return_code": None,
                    "message": "update in progress",
                }
                _save_last_update(ctx, running)
                st["last"] = _load_last_update(ctx)

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

        try:
            log_f = ctx.user.pop("_updater_logf", None)
            if log_f:
                log_f.close()
        except Exception:
            pass

        repo_root = str(st.get("repo", "") or "")

        if rc == 0:
            st["stage"] = "DONE"
            st["msg"] = "Update complete. Rebooting..."
            st["reboot_at"] = time.time() + 2.0
            st["last"] = _record_update_result(ctx, repo_root, "ok", 0, "update complete")
        else:
            st["stage"] = "ERROR"
            st["msg"] = f"Update failed (code {rc})."
            st["last"] = _record_update_result(ctx, repo_root, "failed", int(rc), st["msg"])
        return False

    if stage == "DONE":
        if time.time() >= float(st.get("reboot_at", 0.0)):
            _reboot()
        return False

    if stage == "ERROR":
        if confirm:
            st["stage"] = "CONFIRM"
            st["msg"] = ""
            st["last"] = _load_last_update(ctx)
            ctx.user["_updater_repo_cache"] = {"t": 0.0, "repo": "", "checked": []}
        return False

    st["stage"] = "CONFIRM"
    return False


def _draw_header(ctx, img: Image.Image, title: str, right: str) -> Tuple[Image.Image, Tuple[int, int, int, int]]:
    w, h = img.size
    img = overlay_panel(
        img,
        (8, 8, w - 9, 42),
        radius=10,
        fill=(6, 6, 10, 170),
        outline=(255, 220, 210, 120),
        width=2,
    )
    d = ImageDraw.Draw(img)
    d.text((16, 15), title, font=ctx.font_m, fill=(255, 248, 244))
    tw = int(d.textlength(right, font=ctx.font_s))
    d.text((w - 14 - tw, 18), right, font=ctx.font_s, fill=(220, 210, 205))

    panel = (8, 52, w - 9, h - 9)
    img = overlay_panel(
        img,
        panel,
        radius=8,
        fill=(6, 6, 10, 145),
        outline=(255, 220, 210, 90),
        width=2,
    )
    return img, panel


def _draw_wrapped_lines(d: ImageDraw.ImageDraw, text: str, x: int, y: int, max_width: int, font, fill, line_h: int = 16) -> int:
    for para in (text or "").splitlines():
        if not para.strip():
            y += max(4, line_h // 2)
            continue
        for line in wrap_text(d, para, font, max_width=max_width) or [""]:
            d.text((x, y), line, font=font, fill=fill)
            y += line_h
    return y


def _fmt_last_update(last: Dict) -> str:
    status = str(last.get("status", "never") or "never")
    if status == "never":
        return "No previous update"
    if status == "running":
        return "Last: running"
    if status == "ok":
        return "Last: success"
    return "Last: failed"


def render(ctx) -> Image.Image:
    st = _state(ctx)
    stage = st.get("stage", "CONFIRM")
    last = st.get("last", _load_last_update(ctx))

    img = app_background(ctx, dim_alpha=112)
    if stage in ("CONFIRM", "ERROR"):
        right = "B2 Back"
    elif stage == "RUNNING":
        right = "Updating"
    else:
        right = "Rebooting"
    img, panel = _draw_header(ctx, img, "Update", right)

    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = panel
    tx = x0 + 12
    ty = y0 + 12
    tw = (x1 - x0) - 24

    if stage == "CONFIRM":
        ty = _draw_wrapped_lines(
            d,
            "This will pull the latest PocketR code and reboot when complete.",
            tx,
            ty,
            tw,
            ctx.font_m,
            (242, 232, 226),
            line_h=17,
        )
        ty += 4
        ty = _draw_wrapped_lines(
            d,
            "Warning: do not power off during update.",
            tx,
            ty,
            tw,
            ctx.font_s,
            (240, 220, 210),
            line_h=15,
        )
        ty += 3

        _draw_wrapped_lines(
            d,
            "B1/PRESS: start update\nB2: cancel",
            tx,
            ty,
            tw,
            ctx.font_s,
            (240, 220, 210),
            line_h=15,
        )

        foot = _fmt_last_update(last)
        d.text((tx, y1 - 18), foot, font=ctx.font_s, fill=(214, 194, 186))
        return img

    if stage == "RUNNING":
        msg = st.get("msg", "Updating...") + dots(time.time())
        ty = _draw_wrapped_lines(d, msg, tx, ty, tw, ctx.font_m, (242, 232, 226), line_h=18)

        frac = 0.15 + 0.70 * breathe(time.time(), 1.6)
        draw_progress_bar(d, tx, ty + 4, tw, 12, frac)

        y = ty + 24
        for raw in _tail(LOG_PATH, n=12):
            for line in wrap_text(d, raw, ctx.font_s, max_width=tw):
                if y > y1 - 18:
                    break
                d.text((tx, y), line, font=ctx.font_s, fill=(225, 205, 196))
                y += 15
            if y > y1 - 18:
                break
        return img

    if stage == "DONE":
        ty = _draw_wrapped_lines(d, st.get("msg", "Rebooting..."), tx, ty, tw, ctx.font_m, (242, 232, 226), line_h=18)
        ty += 6
        _draw_wrapped_lines(
            d,
            "If reboot does not start, use the hardware power switch.",
            tx,
            ty,
            tw,
            ctx.font_s,
            (225, 205, 196),
            line_h=16,
        )
        draw_progress_bar(d, tx, y1 - 22, tw, 10, 1.0)
        return img

    if stage == "ERROR":
        d.text((tx, ty), "Update error", font=ctx.font_m, fill=(255, 120, 120))
        ty += 20
        ty = _draw_wrapped_lines(d, st.get("msg", "Unknown update error"), tx, ty, tw, ctx.font_s, (240, 220, 210), line_h=16)

        y = ty + 6
        for raw in _tail(LOG_PATH, n=8):
            for line in wrap_text(d, raw, ctx.font_s, max_width=tw):
                if y > y1 - 20:
                    break
                d.text((tx, y), line, font=ctx.font_s, fill=(225, 205, 196))
                y += 15
            if y > y1 - 20:
                break

        return img

    return img
