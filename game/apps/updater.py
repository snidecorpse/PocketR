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
META_REL_PATH = "update/last_update.json"
REPO_SCAN_SECONDS = 1.5

SOURCE_AUTO = "AUTO"
SOURCE_PRESET = "PRESET"

STAGE_CONFIRM = "CONFIRM"
STAGE_REVIEW = "REVIEW_METHOD"
STAGE_RUNNING = "RUNNING"
STAGE_DONE = "DONE"
STAGE_ERROR = "ERROR"

METHOD_KEYSEQ = "KEYSEQ_PULL"
METHOD_SCRIPT = "SCRIPT_FALLBACK"

UPDATER_PRESETS = [
    "/root/PocketR",
    "/root/pocketr",
    "/home/pi/PocketR",
    "/home/pi/pocketr",
]


def _run(cmd: List[str], timeout: float = 1.0) -> str:
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


def _git_root(path: str) -> str:
    if not path:
        return ""
    out = _run(["git", "-C", path, "rev-parse", "--show-toplevel"], timeout=1.0)
    p = (out or "").strip()
    return p if p and os.path.isdir(p) else ""


def _git_branch(path: str) -> str:
    return _run(["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"], timeout=1.0) or "unknown"


def _git_sha(path: str) -> str:
    return _run(["git", "-C", path, "rev-parse", "--short", "HEAD"], timeout=1.0) or ""


def _safe_directory(path: str) -> None:
    try:
        subprocess.run(
            ["git", "config", "--global", "--add", "safe.directory", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1.2,
        )
    except Exception:
        pass


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


def _unique_paths(paths: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in paths:
        p = os.path.abspath(os.path.expanduser(str(raw or "").strip()))
        if not p:
            continue
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def _repo_candidates(ctx) -> List[str]:
    base = str(getattr(ctx, "base_dir", "") or "")
    game_dir = str(getattr(ctx, "game_dir", "") or "")
    cwd = os.getcwd()
    raw: List[str] = [
        os.environ.get("POCKETR_REPO", ""),
        base,
        os.path.dirname(game_dir) if game_dir else "",
        cwd,
        "/opt/pocketr",
    ] + UPDATER_PRESETS

    out: List[str] = []
    for p in _unique_paths(raw):
        out.append(p)
        out.append(os.path.join(p, "PocketR"))
    return _unique_paths(out)


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


def _updater_source_prefs(ctx) -> Tuple[str, str]:
    prefs = ctx.user.get("_prefs", {})
    if not isinstance(prefs, dict):
        prefs = read_json(ctx, "settings.json", {})
        if not isinstance(prefs, dict):
            prefs = {}

    mode = str(prefs.get("updater_source_mode", SOURCE_AUTO) or SOURCE_AUTO).strip().upper()
    if mode != SOURCE_PRESET:
        mode = SOURCE_AUTO
    value = str(prefs.get("updater_source_value", UPDATER_PRESETS[0]) or UPDATER_PRESETS[0]).strip()
    return mode, value


def _build_candidate_chain(ctx) -> List[str]:
    mode, value = _updater_source_prefs(ctx)
    _repo, checked = _discover_repo_cached(ctx)
    checked_paths = _unique_paths([p for p in checked if os.path.isdir(p)])
    auto = _unique_paths(checked_paths + _repo_candidates(ctx))

    if mode == SOURCE_PRESET:
        return _unique_paths([value] + UPDATER_PRESETS + auto)
    return _unique_paths(auto + UPDATER_PRESETS)


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
        "selected_mode": SOURCE_AUTO,
        "selected_value": "",
        "attempted_paths": [],
        "attempts": [],
        "method_used": "",
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


def _state(ctx) -> Dict:
    st = ctx.user.get("_updater", None)
    if not isinstance(st, dict):
        st = {}
    st.setdefault("stage", STAGE_CONFIRM)
    st.setdefault("msg", "")
    st.setdefault("reboot_at", 0.0)
    st.setdefault("last", _load_last_update(ctx))
    st.setdefault("selected_mode", SOURCE_AUTO)
    st.setdefault("selected_value", "")
    st.setdefault("candidates", [])
    st.setdefault("attempt_idx", 0)
    st.setdefault("attempt_method", METHOD_KEYSEQ)
    st.setdefault("attempts", [])
    st.setdefault("current_repo", "")
    st.setdefault("current_branch", "")
    st.setdefault("current_pre_sha", "")
    st.setdefault("method_used", "")
    ctx.user["_updater"] = st
    return st


def init(ctx):
    last = _load_last_update(ctx)
    if str(last.get("status", "never") or "never") == "never":
        _save_last_update(ctx, last)
    ctx.user["_updater"] = {
        "stage": STAGE_CONFIRM,
        "msg": "",
        "reboot_at": 0.0,
        "last": last,
        "selected_mode": SOURCE_AUTO,
        "selected_value": "",
        "candidates": [],
        "attempt_idx": 0,
        "attempt_method": METHOD_KEYSEQ,
        "attempts": [],
        "current_repo": "",
        "current_branch": "",
        "current_pre_sha": "",
        "method_used": "",
    }
    ctx.user["_updater_repo_cache"] = {"t": 0.0, "repo": "", "checked": []}


def _record_attempt(st: Dict, repo: str, method: str, status: str, rc: int, branch: str, pre_sha: str, post_sha: str) -> None:
    st["attempts"].append(
        {
            "repo_path": repo,
            "method": method,
            "status": status,
            "return_code": rc,
            "branch": branch,
            "pre_sha": pre_sha,
            "post_sha": post_sha,
            "at": _now_iso(),
        }
    )


def _persist_running(ctx, st: Dict) -> None:
    _save_last_update(
        ctx,
        {
            "last_run": _now_iso(),
            "repo_path": str(st.get("current_repo", "") or ""),
            "status": "running",
            "return_code": None,
            "message": "update in progress",
            "selected_mode": st.get("selected_mode", SOURCE_AUTO),
            "selected_value": st.get("selected_value", ""),
            "attempted_paths": [a.get("repo_path", "") for a in st.get("attempts", [])],
            "attempts": st.get("attempts", []),
            "method_used": st.get("attempt_method", ""),
        },
    )


def _launch_attempt(ctx, st: Dict) -> bool:
    candidates = st.get("candidates", [])
    if not isinstance(candidates, list):
        candidates = []

    while int(st.get("attempt_idx", 0)) < len(candidates):
        idx = int(st.get("attempt_idx", 0))
        method = str(st.get("attempt_method", METHOD_KEYSEQ) or METHOD_KEYSEQ)
        repo = str(candidates[idx] or "")

        if method == METHOD_SCRIPT:
            if not os.path.isdir(repo) or not _is_git_repo(repo):
                discovered, _checked = _discover_repo_cached(ctx)
                if discovered and _is_git_repo(discovered):
                    repo = discovered
                else:
                    _record_attempt(st, repo, method, "failed", 2, "", "", "")
                    st["attempt_method"] = METHOD_KEYSEQ
                    st["attempt_idx"] = idx + 1
                    continue
            st["current_branch"] = _git_branch(repo)
            st["current_pre_sha"] = _git_sha(repo)
            _safe_directory(repo)
        else:
            info_repo = repo if _is_git_repo(repo) else ""
            if not info_repo:
                discovered, _checked = _discover_repo_cached(ctx)
                if discovered and _is_git_repo(discovered):
                    info_repo = discovered
            st["current_branch"] = _git_branch(info_repo) if info_repo else ""
            st["current_pre_sha"] = _git_sha(info_repo) if info_repo else ""
            if info_repo:
                _safe_directory(info_repo)

        st["current_repo"] = repo

        try:
            try:
                with open(LOG_PATH, "w", encoding="utf-8"):
                    pass
            except Exception:
                pass
            log_f = open(LOG_PATH, "a", encoding="utf-8")
            env = os.environ.copy()
            env["POCKETR_REPO"] = repo

            if method == METHOD_KEYSEQ:
                repo_safe = str(repo).replace('"', '\\"')
                repo_name = os.path.basename(repo_safe.rstrip("/")) or "PocketR"
                cmd = (
                    'cd ~ && '
                    '(cd PocketR || cd pocketr || cd "{name}" || cd "{path}") && '
                    "git pull"
                ).format(name=repo_name, path=repo_safe)
                proc = subprocess.Popen(
                    ["bash", "-lc", cmd],
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    env=env,
                )
            else:
                script_path = os.path.join(ctx.game_dir, "scripts", "update_repo.sh")
                proc = subprocess.Popen(
                    ["bash", script_path, repo],
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    env=env,
                )

            ctx.user["_updater_proc"] = proc
            ctx.user["_updater_logf"] = log_f
            st["msg"] = f"Updating with {method.lower().replace('_', ' ')}..."
            _persist_running(ctx, st)
            return True
        except Exception as e:
            _record_attempt(st, repo, method, "failed", 3, st.get("current_branch", ""), st.get("current_pre_sha", ""), "")
            st["msg"] = f"Start failed: {e}"
            if method == METHOD_KEYSEQ:
                st["attempt_method"] = METHOD_SCRIPT
            else:
                st["attempt_method"] = METHOD_KEYSEQ
                st["attempt_idx"] = idx + 1
            continue

    return False


def _persist_result(ctx, st: Dict, status: str, rc: int, msg: str, method_used: str = "") -> Dict:
    mode = st.get("selected_mode", SOURCE_AUTO)
    value = st.get("selected_value", "")
    attempts = st.get("attempts", [])
    if not isinstance(attempts, list):
        attempts = []
    attempted_paths = [str(a.get("repo_path", "") or "") for a in attempts]

    branch = ""
    pre_sha = ""
    post_sha = ""
    for a in reversed(attempts):
        if a.get("status") == "ok":
            branch = str(a.get("branch", "") or "")
            pre_sha = str(a.get("pre_sha", "") or "")
            post_sha = str(a.get("post_sha", "") or "")
            break

    if method_used == METHOD_SCRIPT:
        markers = _parse_markers(LOG_PATH)
        branch = markers.get("POCKETR_META_BRANCH", branch)
        pre_sha = markers.get("POCKETR_META_PRE_SHA", pre_sha)
        post_sha = markers.get("POCKETR_META_POST_SHA", post_sha)

    last_repo = str(st.get("current_repo", "") or "")
    payload = {
        "last_run": _now_iso(),
        "repo_path": last_repo,
        "status": status,
        "return_code": rc,
        "message": msg,
        "branch": branch,
        "pre_sha": pre_sha,
        "post_sha": post_sha,
        "selected_mode": mode,
        "selected_value": value,
        "attempted_paths": attempted_paths,
        "attempts": attempts,
        "method_used": method_used,
    }
    _save_last_update(ctx, payload)
    return payload


def _close_proc_log(ctx) -> None:
    try:
        log_f = ctx.user.pop("_updater_logf", None)
        if log_f:
            log_f.close()
    except Exception:
        pass


def update(ctx, dt: float, ev: Dict[str, bool]) -> bool:
    st = _state(ctx)
    stage = str(st.get("stage", STAGE_CONFIRM))
    confirm = ("K1" in ev) or ("PRESS" in ev)

    if stage in (STAGE_CONFIRM, STAGE_ERROR) and "K2" in ev:
        return True

    if stage == STAGE_CONFIRM:
        mode, value = _updater_source_prefs(ctx)
        st["selected_mode"] = mode
        st["selected_value"] = value
        st["candidates"] = _build_candidate_chain(ctx)
        if confirm:
            st["stage"] = STAGE_REVIEW
        return False

    if stage == STAGE_REVIEW:
        if "K2" in ev:
            st["stage"] = STAGE_CONFIRM
            return False
        if confirm:
            st["attempt_idx"] = 0
            st["attempt_method"] = METHOD_KEYSEQ
            st["attempts"] = []
            st["current_repo"] = ""
            st["current_branch"] = ""
            st["current_pre_sha"] = ""
            if _launch_attempt(ctx, st):
                st["stage"] = STAGE_RUNNING
            else:
                st["stage"] = STAGE_ERROR
                st["msg"] = "No valid git source found in candidate list."
                st["last"] = _persist_result(ctx, st, "failed", 2, st["msg"], "")
        return False

    if stage == STAGE_RUNNING:
        proc = ctx.user.get("_updater_proc", None)
        if proc is None:
            st["stage"] = STAGE_ERROR
            st["msg"] = "Update process missing."
            st["last"] = _persist_result(ctx, st, "failed", 3, st["msg"], "")
            return False

        rc = proc.poll()
        if rc is None:
            return False

        _close_proc_log(ctx)
        ctx.user.pop("_updater_proc", None)

        repo = str(st.get("current_repo", "") or "")
        method = str(st.get("attempt_method", METHOD_KEYSEQ) or METHOD_KEYSEQ)
        branch = str(st.get("current_branch", "") or "")
        pre_sha = str(st.get("current_pre_sha", "") or "")
        post_sha = _git_sha(repo) if repo else ""

        if rc == 0:
            _record_attempt(st, repo, method, "ok", 0, branch, pre_sha, post_sha)
            st["method_used"] = method
            st["stage"] = STAGE_DONE
            st["msg"] = "Update complete. Rebooting..."
            st["reboot_at"] = time.time() + 2.0
            st["last"] = _persist_result(ctx, st, "ok", 0, "update complete", method)
            return False

        _record_attempt(st, repo, method, "failed", int(rc), branch, pre_sha, post_sha)
        idx = int(st.get("attempt_idx", 0))
        if method == METHOD_KEYSEQ:
            st["attempt_method"] = METHOD_SCRIPT
        else:
            st["attempt_method"] = METHOD_KEYSEQ
            st["attempt_idx"] = idx + 1

        if _launch_attempt(ctx, st):
            return False

        st["stage"] = STAGE_ERROR
        st["msg"] = "All update sources failed."
        st["last"] = _persist_result(ctx, st, "failed", int(rc), st["msg"], "")
        return False

    if stage == STAGE_DONE:
        if time.time() >= float(st.get("reboot_at", 0.0)):
            _reboot()
        return False

    if stage == STAGE_ERROR:
        if confirm:
            st["stage"] = STAGE_CONFIRM
            st["msg"] = ""
            st["last"] = _load_last_update(ctx)
            ctx.user["_updater_repo_cache"] = {"t": 0.0, "repo": "", "checked": []}
        return False

    st["stage"] = STAGE_CONFIRM
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
    stage = str(st.get("stage", STAGE_CONFIRM))
    last = st.get("last", _load_last_update(ctx))
    candidates = st.get("candidates", [])
    if not isinstance(candidates, list):
        candidates = []

    img = app_background(ctx, dim_alpha=112)
    if stage in (STAGE_CONFIRM, STAGE_ERROR):
        right = "B2 Back"
    elif stage == STAGE_REVIEW:
        right = "B2 Cancel"
    elif stage == STAGE_RUNNING:
        right = "Updating"
    else:
        right = "Rebooting"
    img, panel = _draw_header(ctx, img, "Update", right)

    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = panel
    tx = x0 + 12
    ty = y0 + 12
    tw = (x1 - x0) - 24

    if stage == STAGE_CONFIRM:
        ty = _draw_wrapped_lines(
            d,
            "This will pull latest PocketR code and reboot when complete.",
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
        ty += 5
        _draw_wrapped_lines(d, "B1/PRESS: review method\nB2: cancel", tx, ty, tw, ctx.font_s, (240, 220, 210), line_h=15)
        foot = _fmt_last_update(last)
        d.text((tx, y1 - 18), foot, font=ctx.font_s, fill=(214, 194, 186))
        return img

    if stage == STAGE_REVIEW:
        mode = str(st.get("selected_mode", SOURCE_AUTO) or SOURCE_AUTO)
        source_line = f"Source mode: {mode}"
        ty = _draw_wrapped_lines(d, source_line, tx, ty, tw, ctx.font_s, (240, 220, 210), line_h=15)
        ty = _draw_wrapped_lines(
            d,
            "Method 1: terminal sequence (cd ~, cd PocketR, git pull)\nMethod 2: update_repo.sh fallback",
            tx,
            ty + 2,
            tw,
            ctx.font_s,
            (240, 220, 210),
            line_h=15,
        )
        ty += 3
        _draw_wrapped_lines(d, "Candidate order:", tx, ty, tw, ctx.font_s, (236, 216, 208), line_h=15)
        y = ty + 14
        for p in candidates[:4]:
            line = f"- {p}"
            for wline in wrap_text(d, line, ctx.font_s, max_width=tw):
                if y > y1 - 30:
                    break
                d.text((tx, y), wline, font=ctx.font_s, fill=(222, 204, 196))
                y += 14
            if y > y1 - 30:
                break
        d.text((tx, y1 - 18), "B1/PRESS: start  B2: back", font=ctx.font_s, fill=(214, 194, 186))
        return img

    if stage == STAGE_RUNNING:
        method = str(st.get("attempt_method", METHOD_KEYSEQ)).replace("_", " ").lower()
        repo = str(st.get("current_repo", "") or "")
        title = f"{method}: {os.path.basename(repo) or repo}"
        ty = _draw_wrapped_lines(d, title + dots(time.time()), tx, ty, tw, ctx.font_m, (242, 232, 226), line_h=18)

        frac = 0.15 + 0.70 * breathe(time.time(), 1.6)
        draw_progress_bar(d, tx, ty + 4, tw, 12, frac)

        y = ty + 24
        for raw in _tail(LOG_PATH, n=10):
            for line in wrap_text(d, raw, ctx.font_s, max_width=tw):
                if y > y1 - 18:
                    break
                d.text((tx, y), line, font=ctx.font_s, fill=(225, 205, 196))
                y += 15
            if y > y1 - 18:
                break
        return img

    if stage == STAGE_DONE:
        ty = _draw_wrapped_lines(d, st.get("msg", "Rebooting..."), tx, ty, tw, ctx.font_m, (242, 232, 226), line_h=18)
        ty += 6
        _draw_wrapped_lines(
            d,
            "If reboot does not start, use hardware power switch.",
            tx,
            ty,
            tw,
            ctx.font_s,
            (225, 205, 196),
            line_h=16,
        )
        draw_progress_bar(d, tx, y1 - 22, tw, 10, 1.0)
        return img

    if stage == STAGE_ERROR:
        d.text((tx, ty), "Update error", font=ctx.font_m, fill=(255, 120, 120))
        ty += 20
        ty = _draw_wrapped_lines(d, st.get("msg", "Unknown update error"), tx, ty, tw, ctx.font_s, (240, 220, 210), line_h=16)
        y = ty + 6
        for raw in _tail(LOG_PATH, n=6):
            for line in wrap_text(d, raw, ctx.font_s, max_width=tw):
                if y > y1 - 20:
                    break
                d.text((tx, y), line, font=ctx.font_s, fill=(225, 205, 196))
                y += 15
            if y > y1 - 20:
                break
        d.text((tx, y1 - 18), "B1 retry  B2 back", font=ctx.font_s, fill=(214, 194, 186))
        return img

    return img
