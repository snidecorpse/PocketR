from __future__ import annotations

import json
import os
from typing import Any


DEFAULT_DATA_DIR = "/root/.pocketr"


def _safe_mkdir(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception:
        return False


def ensure_data_dir(ctx) -> str:
    data_dir = str(getattr(ctx, "data_dir", "") or "").strip()
    if not data_dir:
        base_dir = str(getattr(ctx, "base_dir", ".") or ".")
        env = str(os.environ.get("POCKETR_DATA_DIR", "") or "").strip()
        data_dir = os.path.abspath(os.path.expanduser(env)) if env else DEFAULT_DATA_DIR

        if not _safe_mkdir(data_dir):
            fallback = os.path.join(base_dir, ".pocketr")
            _safe_mkdir(fallback)
            data_dir = fallback

        try:
            setattr(ctx, "data_dir", data_dir)
        except Exception:
            pass

    _safe_mkdir(data_dir)
    return data_dir


def _abs_path(ctx, rel_path: str) -> str:
    rel = str(rel_path or "").strip().lstrip("/")
    if hasattr(ctx, "data_path"):
        return ctx.data_path(rel)
    return os.path.join(ensure_data_dir(ctx), rel)


def read_json(ctx, rel_path: str, default: Any):
    path = _abs_path(ctx, rel_path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception:
        return default


def write_json_atomic(ctx, rel_path: str, data: Any) -> str:
    path = _abs_path(ctx, rel_path)
    parent = os.path.dirname(path)
    if parent:
        _safe_mkdir(parent)

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)
    return path
