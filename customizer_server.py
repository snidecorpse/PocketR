#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import mimetypes
import os
import re
import shutil
import tempfile
import threading
import zipfile
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote_plus, urlparse

from PIL import Image


ROOM_SLUGS = ["hub", "bedroom", "living", "bathroom", "arcade"]
ANIM_GROUPS = [
    "Walking",
    "IdleHappy",
    "IdleSad",
    "Talking",
    "HugCuddle",
    "Sleeping",
    "Shower",
    "Changing",
    "Gaming",
]
SINGLE_SPRITE_FILES = ["idle.png", "walk1.png", "walk2.png", "sleep.png", "shower.png", "toilet.png"]

BACKGROUND_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
SPRITE_EXTS = {".png"}

ROOM_SIZE = (240, 240)
MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _write_json_atomic(path: Path, payload: Any, *, sort_keys: bool = False) -> None:
    _ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=True, sort_keys=sort_keys)
    os.replace(tmp, path)


def _safe_unlink(path: Path) -> None:
    try:
        if path.is_file() or path.is_symlink():
            path.unlink()
    except Exception:
        pass


def _safe_rmtree(path: Path) -> None:
    try:
        if path.exists():
            shutil.rmtree(path)
    except Exception:
        pass


def _copytree_if_exists(src: Path, dst: Path) -> None:
    if not src.is_dir():
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _clean_file_name(name: str) -> str:
    base = os.path.basename(str(name or "").strip())
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    return safe or "upload"


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    s = str(value or "").strip().lower()
    return s in {"1", "true", "yes", "on"}


def _merge_unique(items: List[str], value: str) -> List[str]:
    out = [x for x in items if x != value]
    out.append(value)
    return out


def _remove_item(items: List[str], value: str) -> List[str]:
    return [x for x in items if x != value]


def _mtime_or_zero(path: Path) -> int:
    try:
        return int(path.stat().st_mtime)
    except Exception:
        return 0


def _resample_lanczos():
    if hasattr(Image, "Resampling"):
        return Image.Resampling.LANCZOS
    return Image.LANCZOS


@dataclass
class UploadedFile:
    field: str
    filename: str
    content_type: str
    data: bytes


class ApiError(Exception):
    def __init__(self, message: str, *, status: int = 400, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status = int(status)
        self.details = details or {}


@dataclass
class ParsedBody:
    fields: Dict[str, str]
    files: Dict[str, List[UploadedFile]]
    json_data: Optional[Any]


def _parse_multipart(content_type: str, body: bytes) -> ParsedBody:
    m = re.search(r"boundary=(?P<q>\"?)(?P<b>[^\";]+)(?P=q)", content_type)
    if not m:
        raise ApiError("Missing multipart boundary.", status=400)
    boundary = m.group("b").encode("utf-8", errors="ignore")
    marker = b"--" + boundary

    fields: Dict[str, str] = {}
    files: Dict[str, List[UploadedFile]] = {}

    parts = body.split(marker)
    for part in parts:
        if not part:
            continue
        if part in (b"--", b"--\r\n", b"\r\n"):
            continue

        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        if part.endswith(b"--"):
            part = part[:-2]

        header_blob, sep, data = part.partition(b"\r\n\r\n")
        if not sep:
            continue

        headers: Dict[str, str] = {}
        for raw_line in header_blob.split(b"\r\n"):
            line = raw_line.decode("latin-1", errors="ignore")
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()

        disp = headers.get("content-disposition", "")
        if not disp:
            continue

        params: Dict[str, str] = {}
        for token in disp.split(";")[1:]:
            token = token.strip()
            if "=" not in token:
                continue
            k, v = token.split("=", 1)
            k = k.strip().lower()
            v = v.strip().strip('"')
            params[k] = unquote_plus(v)

        field_name = params.get("name", "")
        if not field_name:
            continue

        file_name = params.get("filename", "")
        if file_name:
            item = UploadedFile(
                field=field_name,
                filename=file_name,
                content_type=headers.get("content-type", "application/octet-stream"),
                data=data,
            )
            files.setdefault(field_name, []).append(item)
        else:
            fields[field_name] = data.decode("utf-8", errors="replace")

    return ParsedBody(fields=fields, files=files, json_data=None)


def _parse_body(headers: Dict[str, str], body: bytes) -> ParsedBody:
    content_type = str(headers.get("content-type", "") or "").lower()
    if content_type.startswith("application/json"):
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as exc:
            raise ApiError(f"Invalid JSON body: {exc}", status=400)
        return ParsedBody(fields={}, files={}, json_data=payload)

    if content_type.startswith("application/x-www-form-urlencoded"):
        parsed = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
        fields = {k: (v[-1] if v else "") for k, v in parsed.items()}
        return ParsedBody(fields=fields, files={}, json_data=None)

    if content_type.startswith("multipart/form-data"):
        return _parse_multipart(content_type, body)

    return ParsedBody(fields={}, files={}, json_data=None)


class CustomizerState:
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.web_root = self.project_root / "customizer_web"
        self.asset_root = self.project_root / "game" / "assets" / "pet_game"

        self.data_root = self.project_root / ".pocketr"
        self.customizer_root = self.data_root / "customizer"
        self.draft_root = self.customizer_root / "draft"
        self.snapshots_root = self.customizer_root / "snapshots"
        self.last_apply_path = self.customizer_root / "last_apply.json"

        self.applied_overrides_root = self.data_root / "pet" / "overrides" / "pet_game"
        self.applied_dialogue_path = self.data_root / "pet" / "dialogue.json"

        self._lock = threading.RLock()
        self._ensure_layout()

    def _ensure_layout(self) -> None:
        _ensure_dir(self.web_root)
        _ensure_dir(self.asset_root)
        _ensure_dir(self.draft_root)
        _ensure_dir(self.snapshots_root)
        _ensure_dir(self.applied_overrides_root)
        _ensure_dir(self.applied_dialogue_path.parent)
        manifest = self._load_manifest()
        self._save_manifest(manifest)

    def _default_manifest(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "backgrounds": {},
            "backgrounds_clear": [],
            "sprites_anim": {},
            "sprites_anim_clear": [],
            "sprites_single": {},
            "sprites_single_clear": [],
            "dialogue": None,
            "dialogue_clear": False,
            "updated_at": _now_iso(),
        }

    @property
    def _manifest_path(self) -> Path:
        return self.draft_root / "manifest.json"

    def _normalize_manifest(self, raw: Any) -> Dict[str, Any]:
        base = self._default_manifest()
        if not isinstance(raw, dict):
            return base

        for key in ("backgrounds", "sprites_anim", "sprites_single"):
            val = raw.get(key)
            base[key] = val if isinstance(val, dict) else {}

        for key in ("backgrounds_clear", "sprites_anim_clear", "sprites_single_clear"):
            val = raw.get(key)
            if isinstance(val, list):
                base[key] = [str(x) for x in val]

        dlg = raw.get("dialogue")
        if isinstance(dlg, dict):
            base["dialogue"] = dlg
        base["dialogue_clear"] = bool(raw.get("dialogue_clear", False))
        base["updated_at"] = str(raw.get("updated_at", _now_iso()))
        return base

    def _load_manifest(self) -> Dict[str, Any]:
        raw = _read_json(self._manifest_path, self._default_manifest())
        return self._normalize_manifest(raw)

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        manifest = self._normalize_manifest(manifest)
        manifest["updated_at"] = _now_iso()
        _write_json_atomic(self._manifest_path, manifest, sort_keys=False)

    def _draft_abs(self, rel: str) -> Path:
        rel_path = Path(rel)
        return (self.draft_root / rel_path).resolve()

    def _assert_within_draft(self, path: Path) -> None:
        root = self.draft_root.resolve()
        if root not in path.parents and path != root:
            raise ApiError("Draft path traversal blocked.", status=400)

    def _write_draft_file(self, rel: str, data: bytes) -> Path:
        path = self._draft_abs(rel)
        self._assert_within_draft(path)
        _ensure_dir(path.parent)
        with path.open("wb") as fh:
            fh.write(data)
        return path

    def _remove_draft_path(self, rel: str) -> None:
        path = self._draft_abs(rel)
        self._assert_within_draft(path)
        if path.is_dir():
            _safe_rmtree(path)
        else:
            _safe_unlink(path)

    def _fallback_room_path(self, room: str) -> Optional[Path]:
        p1 = self.asset_root / "rooms" / room / "base.png"
        p2 = self.asset_root / "rooms" / room / "Base.png"
        if p1.is_file():
            return p1
        if p2.is_file():
            return p2
        return None

    def _applied_room_path(self, room: str) -> Optional[Path]:
        p1 = self.applied_overrides_root / "rooms" / room / "base.png"
        p2 = self.applied_overrides_root / "rooms" / room / "Base.png"
        if p1.is_file():
            return p1
        if p2.is_file():
            return p2
        return None

    def _fallback_anim_paths(self, group: str) -> List[Path]:
        root = self.asset_root / "Sprites" / group
        if not root.is_dir():
            return []
        out: List[Path] = []
        for name in sorted(os.listdir(root)):
            low = name.lower()
            if low.endswith(".png") and low.startswith("frame_"):
                out.append(root / name)
        return out

    def _applied_anim_paths(self, group: str) -> List[Path]:
        root = self.applied_overrides_root / "Sprites" / group
        if not root.is_dir():
            return []
        out: List[Path] = []
        for name in sorted(os.listdir(root)):
            low = name.lower()
            if low.endswith(".png") and low.startswith("frame_"):
                out.append(root / name)
        return out

    def _fallback_single_path(self, name: str) -> Optional[Path]:
        p = self.asset_root / name
        return p if p.is_file() else None

    def _applied_single_path(self, name: str) -> Optional[Path]:
        p = self.applied_overrides_root / name
        return p if p.is_file() else None

    def _draft_has_changes(self, manifest: Dict[str, Any]) -> bool:
        return bool(
            manifest.get("backgrounds")
            or manifest.get("backgrounds_clear")
            or manifest.get("sprites_anim")
            or manifest.get("sprites_anim_clear")
            or manifest.get("sprites_single")
            or manifest.get("sprites_single_clear")
            or manifest.get("dialogue")
            or manifest.get("dialogue_clear")
        )

    def _resolve_background(self, room: str, manifest: Dict[str, Any], source: str) -> Tuple[Optional[Path], str]:
        room = str(room)
        if room not in ROOM_SLUGS:
            return None, "invalid"

        if source == "draft":
            entry = manifest.get("backgrounds", {}).get(room)
            if isinstance(entry, dict):
                rel = str(entry.get("file", ""))
                p = self._draft_abs(rel)
                if p.is_file():
                    return p, "draft"
            return None, "draft"

        if source == "applied":
            p = self._applied_room_path(room)
            return (p, "applied") if p else (None, "applied")

        if source == "asset":
            p = self._fallback_room_path(room)
            return (p, "asset") if p else (None, "asset")

        cleared = room in manifest.get("backgrounds_clear", [])
        if not cleared:
            draft_p, _ = self._resolve_background(room, manifest, "draft")
            if draft_p:
                return draft_p, "draft"
            applied_p, _ = self._resolve_background(room, manifest, "applied")
            if applied_p:
                return applied_p, "applied"
        fallback_p, _ = self._resolve_background(room, manifest, "asset")
        return (fallback_p, "asset") if fallback_p else (None, "missing")

    def _resolve_anim(self, group: str, manifest: Dict[str, Any], source: str) -> Tuple[List[Path], str]:
        group = str(group)
        if group not in ANIM_GROUPS:
            return [], "invalid"

        if source == "draft":
            entry = manifest.get("sprites_anim", {}).get(group)
            files: List[Path] = []
            if isinstance(entry, dict):
                for rel in entry.get("files", []):
                    p = self._draft_abs(str(rel))
                    if p.is_file():
                        files.append(p)
            return files, "draft"

        if source == "applied":
            return self._applied_anim_paths(group), "applied"

        if source == "asset":
            return self._fallback_anim_paths(group), "asset"

        cleared = group in manifest.get("sprites_anim_clear", [])
        if not cleared:
            draft_files, _ = self._resolve_anim(group, manifest, "draft")
            if draft_files:
                return draft_files, "draft"
            applied_files, _ = self._resolve_anim(group, manifest, "applied")
            if applied_files:
                return applied_files, "applied"
        fallback_files, _ = self._resolve_anim(group, manifest, "asset")
        return (fallback_files, "asset") if fallback_files else ([], "missing")

    def _resolve_single(self, name: str, manifest: Dict[str, Any], source: str) -> Tuple[Optional[Path], str]:
        name = str(name)
        if name not in SINGLE_SPRITE_FILES:
            return None, "invalid"

        if source == "draft":
            entry = manifest.get("sprites_single", {}).get(name)
            if isinstance(entry, dict):
                rel = str(entry.get("file", ""))
                p = self._draft_abs(rel)
                if p.is_file():
                    return p, "draft"
            return None, "draft"

        if source == "applied":
            p = self._applied_single_path(name)
            return (p, "applied") if p else (None, "applied")

        if source == "asset":
            p = self._fallback_single_path(name)
            return (p, "asset") if p else (None, "asset")

        cleared = name in manifest.get("sprites_single_clear", [])
        if not cleared:
            draft_p, _ = self._resolve_single(name, manifest, "draft")
            if draft_p:
                return draft_p, "draft"
            applied_p, _ = self._resolve_single(name, manifest, "applied")
            if applied_p:
                return applied_p, "applied"
        fallback_p, _ = self._resolve_single(name, manifest, "asset")
        return (fallback_p, "asset") if fallback_p else (None, "missing")

    def _dialogue_source(self, manifest: Dict[str, Any]) -> Tuple[Optional[Path], str]:
        if bool(manifest.get("dialogue_clear")):
            fallback = self.asset_root / "dialogue.json"
            return (fallback if fallback.is_file() else None, "asset")

        dlg = manifest.get("dialogue")
        if isinstance(dlg, dict):
            rel = str(dlg.get("file", ""))
            p = self._draft_abs(rel)
            if p.is_file():
                return p, "draft"

        if self.applied_dialogue_path.is_file():
            return self.applied_dialogue_path, "applied"

        fallback = self.asset_root / "dialogue.json"
        return (fallback if fallback.is_file() else None, "asset")

    def _load_dialogue_payload(self, path: Optional[Path]) -> Dict[str, List[Dict[str, Any]]]:
        if not path:
            return {}
        try:
            raw_text = path.read_text(encoding="utf-8")
        except Exception:
            return {}

        try:
            raw = json.loads(raw_text)
        except Exception:
            # Match pet_game.py tolerance for trailing commas in editable dialogue files.
            relaxed = re.sub(r",(\s*[}\]])", r"\1", raw_text)
            try:
                raw = json.loads(relaxed)
            except Exception:
                raw = {}

        if not isinstance(raw, dict):
            return {}

        cleaned: Dict[str, List[Dict[str, Any]]] = {}
        for cat, rows in raw.items():
            key = str(cat)
            if not isinstance(rows, list):
                continue
            out_rows: List[Dict[str, Any]] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                player = str(row.get("player", "")).strip()
                pet = str(row.get("pet", "")).strip()
                if not player and not pet:
                    continue
                out_item: Dict[str, Any] = {"player": player, "pet": pet}
                if "social" in row:
                    try:
                        out_item["social"] = float(row["social"])
                    except Exception:
                        pass
                if "fun" in row:
                    try:
                        out_item["fun"] = float(row["fun"])
                    except Exception:
                        pass
                out_rows.append(out_item)
            cleaned[key] = out_rows
        return cleaned

    def _normalize_dialogue_input(self, payload: Any) -> Dict[str, List[Dict[str, Any]]]:
        if not isinstance(payload, dict):
            raise ApiError("Dialogue payload must be a JSON object.", status=400)

        out: Dict[str, List[Dict[str, Any]]] = {}
        for raw_cat, raw_rows in payload.items():
            cat = str(raw_cat or "").strip()
            if not cat:
                raise ApiError("Dialogue category names cannot be empty.", status=400)
            if not isinstance(raw_rows, list):
                raise ApiError(f"Dialogue category '{cat}' must be a list.", status=400)

            rows: List[Dict[str, Any]] = []
            for idx, raw_row in enumerate(raw_rows):
                if not isinstance(raw_row, dict):
                    raise ApiError(f"Dialogue '{cat}' row {idx + 1} must be an object.", status=400)

                player = str(raw_row.get("player", "")).strip()
                pet = str(raw_row.get("pet", "")).strip()
                if not player:
                    raise ApiError(f"Dialogue '{cat}' row {idx + 1} is missing player text.", status=400)
                if not pet:
                    raise ApiError(f"Dialogue '{cat}' row {idx + 1} is missing pet text.", status=400)

                row: Dict[str, Any] = {"player": player, "pet": pet}

                if "social" in raw_row and str(raw_row.get("social", "")).strip() != "":
                    try:
                        row["social"] = round(float(raw_row["social"]), 2)
                    except Exception:
                        raise ApiError(f"Dialogue '{cat}' row {idx + 1} has invalid social value.", status=400)
                if "fun" in raw_row and str(raw_row.get("fun", "")).strip() != "":
                    try:
                        row["fun"] = round(float(raw_row["fun"]), 2)
                    except Exception:
                        raise ApiError(f"Dialogue '{cat}' row {idx + 1} has invalid fun value.", status=400)

                rows.append(row)

            out[cat] = rows

        return out

    def _draft_summary(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "has_changes": self._draft_has_changes(manifest),
            "backgrounds": {
                "staged": sorted(list(manifest.get("backgrounds", {}).keys())),
                "clear": sorted(list(manifest.get("backgrounds_clear", []))),
            },
            "sprites_anim": {
                "staged": sorted(list(manifest.get("sprites_anim", {}).keys())),
                "clear": sorted(list(manifest.get("sprites_anim_clear", []))),
            },
            "sprites_single": {
                "staged": sorted(list(manifest.get("sprites_single", {}).keys())),
                "clear": sorted(list(manifest.get("sprites_single_clear", []))),
            },
            "dialogue": {
                "staged": bool(manifest.get("dialogue")),
                "clear": bool(manifest.get("dialogue_clear")),
            },
        }

    def meta_payload(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "meta": {
                "rooms": ROOM_SLUGS,
                "anim_groups": ANIM_GROUPS,
                "single_sprites": SINGLE_SPRITE_FILES,
                "background_exts": sorted(BACKGROUND_EXTS),
                "sprite_exts": sorted(SPRITE_EXTS),
                "room_size": {"width": ROOM_SIZE[0], "height": ROOM_SIZE[1]},
                "max_upload_bytes": MAX_UPLOAD_BYTES,
            },
        }

    def current_payload(self) -> Dict[str, Any]:
        with self._lock:
            manifest = self._load_manifest()
            dialogue_path, dialogue_source = self._dialogue_source(manifest)
            dialogue_data = self._load_dialogue_payload(dialogue_path)
            dialogue_template = self._load_dialogue_payload(self.asset_root / "dialogue.json")

            backgrounds = []
            for room in ROOM_SLUGS:
                path, source = self._resolve_background(room, manifest, "effective")
                backgrounds.append(
                    {
                        "room": room,
                        "source": source,
                        "exists": bool(path and path.is_file()),
                        "mtime": _mtime_or_zero(path) if path else 0,
                        "file_name": path.name if path else "",
                    }
                )

            anim_groups = []
            for group in ANIM_GROUPS:
                files, source = self._resolve_anim(group, manifest, "effective")
                anim_groups.append(
                    {
                        "group": group,
                        "source": source,
                        "count": len(files),
                        "mtime": max((_mtime_or_zero(p) for p in files), default=0),
                        "file_names": [p.name for p in files],
                    }
                )

            singles = []
            for name in SINGLE_SPRITE_FILES:
                path, source = self._resolve_single(name, manifest, "effective")
                singles.append(
                    {
                        "name": name,
                        "source": source,
                        "exists": bool(path and path.is_file()),
                        "mtime": _mtime_or_zero(path) if path else 0,
                        "file_name": path.name if path else "",
                    }
                )

            return {
                "ok": True,
                "draft": self._draft_summary(manifest),
                "effective": {
                    "backgrounds": backgrounds,
                    "anim_groups": anim_groups,
                    "single_sprites": singles,
                    "dialogue_source": dialogue_source,
                },
                "dialogue": {
                    "source": dialogue_source,
                    "data": dialogue_data,
                    "template": dialogue_template,
                },
                "last_apply": _read_json(self.last_apply_path, {}),
            }

    def list_snapshots(self) -> Dict[str, Any]:
        with self._lock:
            items: List[Dict[str, Any]] = []
            if self.snapshots_root.is_dir():
                for name in sorted(os.listdir(self.snapshots_root), reverse=True):
                    d = self.snapshots_root / name
                    if not d.is_dir():
                        continue
                    meta = _read_json(d / "manifest.json", {})
                    if not isinstance(meta, dict):
                        meta = {}
                    items.append(
                        {
                            "id": name,
                            "created_at": str(meta.get("created_at", "")),
                            "action": str(meta.get("action", "")),
                            "has_overrides": bool(meta.get("has_overrides", False)),
                            "has_dialogue": bool(meta.get("has_dialogue", False)),
                        }
                    )
            return {"ok": True, "snapshots": items}

    def stage_background(self, fields: Dict[str, str], files: Dict[str, List[UploadedFile]]) -> Dict[str, Any]:
        room = str(fields.get("room", "")).strip()
        if room not in ROOM_SLUGS:
            raise ApiError("Invalid room slug.", status=400)

        clear = _parse_bool(fields.get("clear"))
        with self._lock:
            manifest = self._load_manifest()

            if clear:
                entry = manifest.get("backgrounds", {}).pop(room, None)
                if isinstance(entry, dict):
                    rel = str(entry.get("file", ""))
                    if rel:
                        self._remove_draft_path(rel)
                manifest["backgrounds_clear"] = _merge_unique(list(manifest.get("backgrounds_clear", [])), room)
                self._save_manifest(manifest)
                return {"ok": True, "message": f"Background for '{room}' marked for removal."}

            upload = (files.get("file") or [])
            if not upload:
                raise ApiError("Background upload is missing file field.", status=400)
            item = upload[0]
            if len(item.data) == 0:
                raise ApiError("Uploaded background file is empty.", status=400)
            if len(item.data) > MAX_UPLOAD_BYTES:
                raise ApiError("Background file exceeds max upload size.", status=413)

            ext = Path(item.filename).suffix.lower()
            if ext not in BACKGROUND_EXTS:
                raise ApiError("Background must be .png, .jpg, .jpeg, or .webp.", status=400)

            try:
                with Image.open(io.BytesIO(item.data)) as img:
                    img.verify()
            except Exception:
                raise ApiError("Uploaded background is not a valid image.", status=400)

            target_rel = f"backgrounds/{room}/source{ext}"
            self._remove_draft_path(f"backgrounds/{room}")
            self._write_draft_file(target_rel, item.data)

            manifest.setdefault("backgrounds", {})[room] = {
                "file": target_rel,
                "name": _clean_file_name(item.filename),
            }
            manifest["backgrounds_clear"] = _remove_item(list(manifest.get("backgrounds_clear", [])), room)
            self._save_manifest(manifest)
            return {"ok": True, "message": f"Staged background for '{room}'."}

    def stage_sprite(self, fields: Dict[str, str], files: Dict[str, List[UploadedFile]]) -> Dict[str, Any]:
        mode = str(fields.get("mode", "")).strip().lower()
        clear = _parse_bool(fields.get("clear"))

        with self._lock:
            manifest = self._load_manifest()

            if mode == "anim":
                group = str(fields.get("group", "")).strip()
                if group not in ANIM_GROUPS:
                    raise ApiError("Invalid animation group.", status=400)

                if clear:
                    entry = manifest.get("sprites_anim", {}).pop(group, None)
                    if isinstance(entry, dict):
                        for rel in entry.get("files", []):
                            self._remove_draft_path(str(rel))
                        self._remove_draft_path(f"sprites/anim/{group}")
                    manifest["sprites_anim_clear"] = _merge_unique(list(manifest.get("sprites_anim_clear", [])), group)
                    self._save_manifest(manifest)
                    return {"ok": True, "message": f"Animation group '{group}' marked for removal."}

                upload_items = []
                upload_items.extend(files.get("files", []))
                upload_items.extend(files.get("file", []))
                if not upload_items:
                    raise ApiError("Missing sprite frame uploads.", status=400)

                clean_items: List[Tuple[str, bytes]] = []
                for idx, item in enumerate(upload_items):
                    if len(item.data) == 0:
                        continue
                    if len(item.data) > MAX_UPLOAD_BYTES:
                        raise ApiError("One of the sprite frames exceeds max upload size.", status=413)
                    ext = Path(item.filename).suffix.lower()
                    if ext not in SPRITE_EXTS:
                        raise ApiError("Sprite frames must be .png.", status=400)
                    fname = _clean_file_name(item.filename)
                    if not fname.lower().endswith(".png"):
                        fname = f"frame_{idx:03d}.png"
                    clean_items.append((fname, item.data))

                if not clean_items:
                    raise ApiError("No usable sprite frames were uploaded.", status=400)

                # Validate all images first.
                for fname, blob in clean_items:
                    try:
                        with Image.open(io.BytesIO(blob)) as img:
                            img.verify()
                    except Exception:
                        raise ApiError(f"Sprite frame '{fname}' is not a valid PNG image.", status=400)

                target_dir_rel = f"sprites/anim/{group}"
                self._remove_draft_path(target_dir_rel)
                rel_files: List[str] = []
                seen: set[str] = set()
                for idx, (fname, blob) in enumerate(clean_items):
                    candidate = fname
                    if candidate in seen:
                        candidate = f"frame_{idx:03d}.png"
                    seen.add(candidate)
                    rel = f"{target_dir_rel}/{candidate}"
                    self._write_draft_file(rel, blob)
                    rel_files.append(rel)

                manifest.setdefault("sprites_anim", {})[group] = {"files": rel_files}
                manifest["sprites_anim_clear"] = _remove_item(list(manifest.get("sprites_anim_clear", [])), group)
                self._save_manifest(manifest)
                return {"ok": True, "message": f"Staged {len(rel_files)} frame(s) for '{group}'."}

            if mode == "single":
                name = str(fields.get("name", "")).strip()
                if name not in SINGLE_SPRITE_FILES:
                    raise ApiError("Invalid single sprite target.", status=400)

                if clear:
                    entry = manifest.get("sprites_single", {}).pop(name, None)
                    if isinstance(entry, dict):
                        rel = str(entry.get("file", ""))
                        if rel:
                            self._remove_draft_path(rel)
                    manifest["sprites_single_clear"] = _merge_unique(list(manifest.get("sprites_single_clear", [])), name)
                    self._save_manifest(manifest)
                    return {"ok": True, "message": f"Sprite '{name}' marked for removal."}

                upload = (files.get("file") or [])
                if not upload:
                    raise ApiError("Missing single sprite upload file.", status=400)
                item = upload[0]
                if len(item.data) == 0:
                    raise ApiError("Uploaded sprite file is empty.", status=400)
                if len(item.data) > MAX_UPLOAD_BYTES:
                    raise ApiError("Single sprite file exceeds max upload size.", status=413)

                ext = Path(item.filename).suffix.lower()
                if ext not in SPRITE_EXTS:
                    raise ApiError("Single sprite must be .png.", status=400)

                try:
                    with Image.open(io.BytesIO(item.data)) as img:
                        img.verify()
                except Exception:
                    raise ApiError("Single sprite upload is not a valid PNG image.", status=400)

                rel = f"sprites/single/{name}"
                self._remove_draft_path(rel)
                self._write_draft_file(rel, item.data)
                manifest.setdefault("sprites_single", {})[name] = {"file": rel}
                manifest["sprites_single_clear"] = _remove_item(list(manifest.get("sprites_single_clear", [])), name)
                self._save_manifest(manifest)
                return {"ok": True, "message": f"Staged sprite '{name}'."}

            raise ApiError("Sprite mode must be 'anim' or 'single'.", status=400)

    def stage_dialogue(self, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ApiError("Dialogue endpoint requires JSON payload.", status=400)

        clear = _parse_bool(payload.get("clear"))
        with self._lock:
            manifest = self._load_manifest()
            if clear:
                dlg_entry = manifest.get("dialogue")
                if isinstance(dlg_entry, dict):
                    rel = str(dlg_entry.get("file", ""))
                    if rel:
                        self._remove_draft_path(rel)
                manifest["dialogue"] = None
                manifest["dialogue_clear"] = True
                self._save_manifest(manifest)
                return {"ok": True, "message": "Dialogue marked for removal (fallback to asset dialogue)."}

            src = payload.get("dialogue") if "dialogue" in payload else payload
            normalized = self._normalize_dialogue_input(src)

            rel = "dialogue/dialogue.json"
            abs_path = self._draft_abs(rel)
            self._assert_within_draft(abs_path)
            _write_json_atomic(abs_path, normalized, sort_keys=False)

            manifest["dialogue"] = {"file": rel}
            manifest["dialogue_clear"] = False
            self._save_manifest(manifest)
            return {"ok": True, "message": f"Staged dialogue with {len(normalized)} categorie(s)."}

    def discard_draft(self) -> Dict[str, Any]:
        with self._lock:
            self._clear_draft_workspace()
            return {"ok": True, "message": "Draft workspace cleared."}

    def _clear_draft_workspace(self) -> None:
        _safe_rmtree(self.draft_root)
        _ensure_dir(self.draft_root)
        self._save_manifest(self._default_manifest())

    def validate_draft(self) -> Dict[str, Any]:
        with self._lock:
            manifest = self._load_manifest()
            errors: List[str] = []
            warnings: List[str] = []

            for room, entry in manifest.get("backgrounds", {}).items():
                if room not in ROOM_SLUGS:
                    errors.append(f"Unknown room in draft backgrounds: {room}")
                    continue
                if not isinstance(entry, dict):
                    errors.append(f"Background entry for {room} is malformed.")
                    continue
                rel = str(entry.get("file", ""))
                p = self._draft_abs(rel)
                if not p.is_file():
                    errors.append(f"Background file missing for {room}.")
                    continue
                ext = p.suffix.lower()
                if ext not in BACKGROUND_EXTS:
                    errors.append(f"Background file for {room} has unsupported extension: {ext}")
                else:
                    try:
                        with Image.open(p) as img:
                            img.verify()
                    except Exception:
                        errors.append(f"Background file for {room} is not a valid image.")

            for group, entry in manifest.get("sprites_anim", {}).items():
                if group not in ANIM_GROUPS:
                    errors.append(f"Unknown animation group in draft: {group}")
                    continue
                if not isinstance(entry, dict):
                    errors.append(f"Animation entry for {group} is malformed.")
                    continue
                rels = entry.get("files", [])
                if not isinstance(rels, list) or not rels:
                    errors.append(f"Animation group {group} has no files.")
                    continue
                for rel in rels:
                    p = self._draft_abs(str(rel))
                    if not p.is_file():
                        errors.append(f"Missing animation frame in {group}: {rel}")
                        continue
                    if p.suffix.lower() not in SPRITE_EXTS:
                        errors.append(f"Animation frame has non-png extension in {group}: {p.name}")
                        continue
                    try:
                        with Image.open(p) as img:
                            img.verify()
                    except Exception:
                        errors.append(f"Invalid PNG animation frame in {group}: {p.name}")

            for name, entry in manifest.get("sprites_single", {}).items():
                if name not in SINGLE_SPRITE_FILES:
                    errors.append(f"Unknown single sprite draft target: {name}")
                    continue
                if not isinstance(entry, dict):
                    errors.append(f"Single sprite entry for {name} is malformed.")
                    continue
                rel = str(entry.get("file", ""))
                p = self._draft_abs(rel)
                if not p.is_file():
                    errors.append(f"Single sprite file missing for {name}.")
                    continue
                if p.suffix.lower() not in SPRITE_EXTS:
                    errors.append(f"Single sprite for {name} must be png.")
                    continue
                try:
                    with Image.open(p) as img:
                        img.verify()
                except Exception:
                    errors.append(f"Single sprite for {name} is not valid PNG.")

            if manifest.get("dialogue"):
                dlg_entry = manifest.get("dialogue")
                if not isinstance(dlg_entry, dict):
                    errors.append("Draft dialogue entry is malformed.")
                else:
                    rel = str(dlg_entry.get("file", ""))
                    p = self._draft_abs(rel)
                    if not p.is_file():
                        errors.append("Draft dialogue file is missing.")
                    else:
                        raw = _read_json(p, None)
                        try:
                            self._normalize_dialogue_input(raw)
                        except ApiError as exc:
                            errors.append(str(exc))

            has_changes = self._draft_has_changes(manifest)
            if not has_changes:
                warnings.append("No staged changes to validate.")

            return {
                "ok": True,
                "valid": len(errors) == 0,
                "has_changes": has_changes,
                "errors": errors,
                "warnings": warnings,
                "draft": self._draft_summary(manifest),
            }

    def _create_snapshot(self, action: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        snap_dir = self.snapshots_root / stamp
        _ensure_dir(snap_dir)

        had_overrides = self.applied_overrides_root.is_dir() and any(self.applied_overrides_root.rglob("*"))
        had_dialogue = self.applied_dialogue_path.is_file()

        if had_overrides:
            _copytree_if_exists(self.applied_overrides_root, snap_dir / "overrides" / "pet_game")

        if had_dialogue:
            _ensure_dir((snap_dir / "dialogue.json").parent)
            shutil.copy2(self.applied_dialogue_path, snap_dir / "dialogue.json")

        snap_manifest = {
            "id": stamp,
            "created_at": _now_iso(),
            "action": action,
            "has_overrides": had_overrides,
            "has_dialogue": had_dialogue,
        }
        _write_json_atomic(snap_dir / "manifest.json", snap_manifest, sort_keys=False)
        return stamp

    def apply_draft(self) -> Dict[str, Any]:
        with self._lock:
            check = self.validate_draft()
            if not check.get("valid", False):
                raise ApiError("Draft validation failed.", status=400, details={"errors": check.get("errors", [])})
            if not check.get("has_changes", False):
                raise ApiError("No staged changes to apply.", status=400)

            manifest = self._load_manifest()
            pre_snapshot_id = self._create_snapshot("pre_apply")

            applied_counts = {
                "backgrounds_written": 0,
                "backgrounds_removed": 0,
                "anim_written": 0,
                "anim_removed": 0,
                "single_written": 0,
                "single_removed": 0,
                "dialogue_written": 0,
                "dialogue_removed": 0,
            }

            # Background clears.
            for room in manifest.get("backgrounds_clear", []):
                p1 = self.applied_overrides_root / "rooms" / room / "base.png"
                p2 = self.applied_overrides_root / "rooms" / room / "Base.png"
                _safe_unlink(p1)
                _safe_unlink(p2)
                try:
                    p1.parent.rmdir()
                except Exception:
                    pass
                applied_counts["backgrounds_removed"] += 1

            # Background writes.
            for room, entry in manifest.get("backgrounds", {}).items():
                rel = str(entry.get("file", ""))
                src = self._draft_abs(rel)
                if not src.is_file():
                    raise ApiError(f"Missing staged background for room '{room}'.", status=400)

                dst_dir = self.applied_overrides_root / "rooms" / room
                _ensure_dir(dst_dir)
                dst = dst_dir / "base.png"

                with Image.open(src) as img:
                    out = img.convert("RGB")
                    if out.size != ROOM_SIZE:
                        out = out.resize(ROOM_SIZE, _resample_lanczos())
                    tmp = dst.with_suffix(".png.tmp")
                    out.save(tmp, format="PNG")
                os.replace(tmp, dst)
                applied_counts["backgrounds_written"] += 1

            # Animation clears.
            for group in manifest.get("sprites_anim_clear", []):
                group_dir = self.applied_overrides_root / "Sprites" / group
                _safe_rmtree(group_dir)
                applied_counts["anim_removed"] += 1

            # Animation writes.
            for group, entry in manifest.get("sprites_anim", {}).items():
                rels = [str(x) for x in entry.get("files", [])]
                src_files = [self._draft_abs(rel) for rel in rels if self._draft_abs(rel).is_file()]
                if not src_files:
                    raise ApiError(f"No staged sprite files found for group '{group}'.", status=400)

                sprites_parent = self.applied_overrides_root / "Sprites"
                _ensure_dir(sprites_parent)
                temp_dir = Path(tempfile.mkdtemp(prefix=f".__tmp_{group}_", dir=str(sprites_parent)))

                try:
                    for idx, src in enumerate(sorted(src_files)):
                        with Image.open(src) as img:
                            out = img.convert("RGBA")
                            out_name = f"frame_{idx:03d}.png"
                            out.save(temp_dir / out_name, format="PNG")

                    dst_dir = self.applied_overrides_root / "Sprites" / group
                    _safe_rmtree(dst_dir)
                    os.replace(temp_dir, dst_dir)
                except Exception:
                    _safe_rmtree(temp_dir)
                    raise

                applied_counts["anim_written"] += 1

            # Single sprite clears.
            for name in manifest.get("sprites_single_clear", []):
                _safe_unlink(self.applied_overrides_root / name)
                applied_counts["single_removed"] += 1

            # Single sprite writes.
            for name, entry in manifest.get("sprites_single", {}).items():
                rel = str(entry.get("file", ""))
                src = self._draft_abs(rel)
                if not src.is_file():
                    raise ApiError(f"Missing staged single sprite '{name}'.", status=400)

                dst = self.applied_overrides_root / name
                _ensure_dir(dst.parent)
                with Image.open(src) as img:
                    out = img.convert("RGBA")
                    tmp = dst.with_suffix(".png.tmp")
                    out.save(tmp, format="PNG")
                os.replace(tmp, dst)
                applied_counts["single_written"] += 1

            # Dialogue clear/write.
            if bool(manifest.get("dialogue_clear")):
                _safe_unlink(self.applied_dialogue_path)
                applied_counts["dialogue_removed"] += 1
            elif manifest.get("dialogue"):
                dlg_entry = manifest.get("dialogue")
                rel = str(dlg_entry.get("file", ""))
                src = self._draft_abs(rel)
                if not src.is_file():
                    raise ApiError("Missing staged dialogue file.", status=400)
                data = _read_json(src, {})
                normalized = self._normalize_dialogue_input(data)
                _write_json_atomic(self.applied_dialogue_path, normalized, sort_keys=False)
                applied_counts["dialogue_written"] += 1

            apply_meta = {
                "action": "apply",
                "applied_at": _now_iso(),
                "snapshot_id": "",
                "pre_snapshot_id": pre_snapshot_id,
                "counts": applied_counts,
            }
            post_snapshot_id = self._create_snapshot("applied_state")
            apply_meta["snapshot_id"] = post_snapshot_id
            _write_json_atomic(self.last_apply_path, apply_meta, sort_keys=False)

            self._clear_draft_workspace()
            return {
                "ok": True,
                "message": "Draft applied successfully.",
                "snapshot_id": post_snapshot_id,
                "pre_snapshot_id": pre_snapshot_id,
                "counts": applied_counts,
            }

    def restore_snapshot(self, snapshot_id: str) -> Dict[str, Any]:
        sid = str(snapshot_id or "").strip()
        if not sid:
            raise ApiError("Missing snapshot_id.", status=400)

        with self._lock:
            src_dir = self.snapshots_root / sid
            if not src_dir.is_dir():
                raise ApiError("Snapshot not found.", status=404)

            self._create_snapshot("pre_restore")

            snap_overrides = src_dir / "overrides" / "pet_game"
            _safe_rmtree(self.applied_overrides_root)
            _ensure_dir(self.applied_overrides_root)
            if snap_overrides.is_dir():
                _safe_rmtree(self.applied_overrides_root)
                shutil.copytree(snap_overrides, self.applied_overrides_root)

            snap_dialogue = src_dir / "dialogue.json"
            if snap_dialogue.is_file():
                _ensure_dir(self.applied_dialogue_path.parent)
                shutil.copy2(snap_dialogue, self.applied_dialogue_path)
            else:
                _safe_unlink(self.applied_dialogue_path)

            restore_meta = {
                "action": "restore",
                "restored_at": _now_iso(),
                "snapshot_id": sid,
            }
            _write_json_atomic(self.last_apply_path, restore_meta, sort_keys=False)

            self._clear_draft_workspace()
            return {
                "ok": True,
                "message": f"Restored snapshot '{sid}'.",
                "snapshot_id": sid,
            }

    def snapshot_zip_payload(self, snapshot_id: str) -> Tuple[str, bytes]:
        sid = str(snapshot_id or "").strip()
        if not sid:
            raise ApiError("Missing snapshot_id.", status=400)

        with self._lock:
            src_dir = self.snapshots_root / sid
            if not src_dir.is_dir():
                raise ApiError("Snapshot not found.", status=404)

            arc_root = Path(".pocketr")
            data = io.BytesIO()
            with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                snap_overrides = src_dir / "overrides" / "pet_game"
                if snap_overrides.is_dir():
                    for p in sorted(snap_overrides.rglob("*")):
                        if not p.is_file():
                            continue
                        rel = p.relative_to(snap_overrides)
                        arcname = (arc_root / "pet" / "overrides" / "pet_game" / rel).as_posix()
                        zf.write(p, arcname=arcname)

                snap_dialogue = src_dir / "dialogue.json"
                if snap_dialogue.is_file():
                    zf.write(snap_dialogue, arcname=(arc_root / "pet" / "dialogue.json").as_posix())

                install_txt = (
                    "PocketR Snapshot Install\n\n"
                    "1. Copy this zip to the Pi.\n"
                    "2. From your PocketR repo root on Pi, unzip with:\n"
                    "   unzip pocketr_snapshot_*.zip -d .\n"
                    "3. Restart PocketR app/service.\n\n"
                    "This archive only contains user overrides under .pocketr/.\n"
                )
                zf.writestr("INSTALL_ON_PI.txt", install_txt)

            return f"pocketr_snapshot_{sid}.zip", data.getvalue()

    def preview_asset(self, query: Dict[str, List[str]]) -> Tuple[str, bytes]:
        kind = str((query.get("kind") or [""])[0]).strip().lower()
        source = str((query.get("source") or ["effective"])[0]).strip().lower()
        if source not in {"effective", "draft", "applied", "asset"}:
            raise ApiError("Invalid source selector.", status=400)

        with self._lock:
            manifest = self._load_manifest()

            if kind == "room":
                room = str((query.get("room") or [""])[0]).strip()
                path, _src = self._resolve_background(room, manifest, source)
                if not path or (not path.is_file()):
                    raise ApiError("Requested room preview asset not found.", status=404)
                mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                return mime, path.read_bytes()

            if kind == "sprite_anim":
                group = str((query.get("group") or [""])[0]).strip()
                files, _src = self._resolve_anim(group, manifest, source)
                if not files:
                    raise ApiError("Requested sprite animation preview not found.", status=404)
                raw_index = str((query.get("frame") or ["0"])[0]).strip()
                try:
                    idx = int(raw_index)
                except Exception:
                    idx = 0
                idx = max(0, min(idx, len(files) - 1))
                p = files[idx]
                return "image/png", p.read_bytes()

            if kind == "sprite_single":
                name = str((query.get("name") or [""])[0]).strip()
                path, _src = self._resolve_single(name, manifest, source)
                if not path or (not path.is_file()):
                    raise ApiError("Requested single sprite preview not found.", status=404)
                return "image/png", path.read_bytes()

        raise ApiError("Invalid preview kind.", status=400)


def make_handler(state: CustomizerState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PocketRCustomizer/1.0"

        def log_message(self, fmt: str, *args) -> None:
            # Keep concise logs.
            print(f"[{self.log_date_time_string()}] {self.client_address[0]} {fmt % args}")

        def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self) -> bytes:
            try:
                length = int(self.headers.get("content-length", "0"))
            except Exception:
                length = 0
            if length <= 0:
                return b""
            return self.rfile.read(length)

        def _serve_static(self, req_path: str) -> None:
            rel = req_path.lstrip("/")
            if not rel:
                rel = "index.html"
            full = (state.web_root / rel).resolve()
            web_root = state.web_root.resolve()
            if web_root not in full.parents and full != web_root:
                self._send_json(404, {"ok": False, "error": "Not found."})
                return
            if full.is_dir():
                full = full / "index.html"
            if not full.is_file():
                self._send_json(404, {"ok": False, "error": "Not found."})
                return
            ctype = mimetypes.guess_type(full.name)[0] or "application/octet-stream"
            self._send_bytes(200, full.read_bytes(), ctype)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query, keep_blank_values=True)

            try:
                if path == "/api/meta":
                    self._send_json(200, state.meta_payload())
                    return
                if path == "/api/current":
                    self._send_json(200, state.current_payload())
                    return
                if path == "/api/snapshots":
                    self._send_json(200, state.list_snapshots())
                    return
                if path == "/api/snapshot_download":
                    sid = str((query.get("snapshot_id") or [""])[0]).strip()
                    filename, payload = state.snapshot_zip_payload(sid)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/zip")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                if path == "/api/preview_asset":
                    ctype, blob = state.preview_asset(query)
                    self._send_bytes(200, blob, ctype)
                    return

                self._serve_static(path)
            except ApiError as exc:
                payload = {"ok": False, "error": str(exc)}
                if exc.details:
                    payload["details"] = exc.details
                self._send_json(exc.status, payload)
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": f"Server error: {exc}"})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            body = self._read_body()
            try:
                parsed_body = _parse_body({k.lower(): v for k, v in self.headers.items()}, body)

                if path == "/api/draft/background":
                    result = state.stage_background(parsed_body.fields, parsed_body.files)
                    self._send_json(200, result)
                    return

                if path == "/api/draft/sprite":
                    result = state.stage_sprite(parsed_body.fields, parsed_body.files)
                    self._send_json(200, result)
                    return

                if path == "/api/draft/dialogue":
                    payload = parsed_body.json_data
                    if payload is None:
                        raise ApiError("Dialogue endpoint requires JSON payload.", status=400)
                    result = state.stage_dialogue(payload)
                    self._send_json(200, result)
                    return

                if path == "/api/draft/discard":
                    result = state.discard_draft()
                    self._send_json(200, result)
                    return

                if path == "/api/validate":
                    self._send_json(200, state.validate_draft())
                    return

                if path == "/api/apply":
                    self._send_json(200, state.apply_draft())
                    return

                if path == "/api/restore":
                    payload = parsed_body.json_data
                    if not isinstance(payload, dict):
                        raise ApiError("Restore endpoint requires JSON payload.", status=400)
                    sid = str(payload.get("snapshot_id", "")).strip()
                    self._send_json(200, state.restore_snapshot(sid))
                    return

                self._send_json(404, {"ok": False, "error": "Unknown API route."})
            except ApiError as exc:
                payload = {"ok": False, "error": str(exc)}
                if exc.details:
                    payload["details"] = exc.details
                self._send_json(exc.status, payload)
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": f"Server error: {exc}"})

    return Handler


def create_server(state: CustomizerState, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, int(port)), make_handler(state))


def main() -> int:
    parser = argparse.ArgumentParser(description="PocketR Customizer Web Server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    parser.add_argument(
        "--project-root",
        default=str(Path(__file__).resolve().parent),
        help="Project root path (default: script directory)",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    state = CustomizerState(project_root)
    server = create_server(state, host=args.host, port=args.port)

    print(f"PocketR customizer running on http://{args.host}:{args.port}")
    print(f"Project root: {project_root}")
    print(f"Data root: {state.data_root}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
