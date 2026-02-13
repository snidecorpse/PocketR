from __future__ import annotations

import json
import math
import os
import random
import re
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from ..persistence import ensure_data_dir, read_json, write_json_atomic
from ..ui_common import clamp, overlay_panel, wrap_text


ROOM_HUB = "HUB"
ROOM_BED = "BEDROOM"
ROOM_LIVING = "LIVING"
ROOM_ARCADE = "ARCADE"
ROOM_BATH = "BATHROOM"

MODE_ONBOARD_1 = "ONBOARD_1"
MODE_ONBOARD_2 = "ONBOARD_2"
MODE_PLAY = "PLAY"
PLAY_WORLD = "PLAY_WORLD"
PLAY_PANEL = "PLAY_PANEL"
PLAY_MINIGAME = "PLAY_MINIGAME"
BRICK_MAX_LEVELS = 5

STATE_REL_PATH = "pet/state.json"
DIALOGUE_REL_PATH = "pet/dialogue.json"

ONBOARD_WELCOME = "intro_welcome.png"
ONBOARD_CONTROLS = "intro_controls.png"

AGE_ACCEL = 60.0  # 1 real minute = 1 pet hour
K2_EXIT_HOLD_SECONDS = 1.6
K2_EXIT_SHOW_DELAY = 0.35
B3_SHORT_MAX_SECONDS = 0.85
PERSIST_SECONDS = 4.0

PLAY_RECT_LEFT = 6
PLAY_RECT_TOP = 74
PLAY_RECT_RIGHT_PAD = 7
PLAY_RECT_BOTTOM_PAD = 7
PLAY_BOUNDS_TOP_PAD = 50
PLAY_BOUNDS_BOTTOM_PAD = 2
IDLE_SIT_SECONDS = 7.0
ACTION_POSE_SECONDS = 6.0
BLOCK_FLASH_SECONDS = 0.16
DECAY_TUNE_MULT = 1.25
SNACK_COOLDOWN_SECONDS = 45.0
ROOM_SWITCH_INSET_X = 6.0

DIALOGUE_CPS_DEFAULT = 31.0
DIALOGUE_LINE_HOLD_SECONDS = 0.75
SPRITE_SCALE_MIN = 0.85
SPRITE_SCALE_MAX = 1.20
SPRITE_SCALE_DEFAULT = 1.00
SPRITE_SCALE_FROM_MEDIUM = 1.10
UNIFORM_BODY_HEIGHT = 92
SPRITE_CANVAS_W = 112
SPRITE_CANVAS_H = 112
SPRITE_CENTER_ANCHOR_ANIMS = {"sleeping_anim"}
BRICK_LEVEL_SPEED_FACTORS = [1.00, 1.12, 1.24, 1.36, 1.50]
ARCADE_GAMES = ("Brick Breaker", "Memory Match", "Runner Dash", "Micro Snake", "Heart Catch", "Reflex Tap")
SNACK_OPTIONS = ("Light Snack", "Balanced Meal", "Sweet Treat")
GALLERY_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
ANIM_FPS = {
    "walk": 5.8,
    "idle_happy": 4.9,
    "idle_sad": 4.7,
    "idle_sit": 4.2,
    "talking": 5.7,
    "shower": 5.0,
    "sleeping": 4.0,
    "changing": 4.9,
    "gaming": 5.1,
    "hugcuddle": 4.8,
}


ROOMS: Dict[str, Dict] = {
    ROOM_HUB: {
        "name": "Main Hall",
        "slug": "hub",
        "neighbors": {"LEFT": ROOM_ARCADE, "RIGHT": ROOM_BED, "UP": ROOM_BATH, "DOWN": ROOM_LIVING},
        "actions": ["Check In", "Stretch", "Take Picture", "Save & Quit"],
        "color": (42, 24, 20),
    },
    ROOM_BED: {
        "name": "Bedroom",
        "slug": "bedroom",
        "neighbors": {"LEFT": ROOM_HUB},
        "actions": ["Cuddle", "Give Hug", "Sleep"],
        "color": (54, 24, 40),
    },
    ROOM_LIVING: {
        "name": "Living Room",
        "slug": "living",
        "neighbors": {"UP": ROOM_HUB},
        "actions": ["Watch TV", "Lounge", "Eat Snack", "Talk", "Open Gallery"],
        "color": (24, 36, 44),
    },
    ROOM_ARCADE: {
        "name": "Arcade",
        "slug": "arcade",
        "neighbors": {"RIGHT": ROOM_HUB},
        "actions": list(ARCADE_GAMES),
        "color": (26, 24, 50),
    },
    ROOM_BATH: {
        "name": "Bathroom",
        "slug": "bathroom",
        "neighbors": {"DOWN": ROOM_HUB},
        "actions": ["Use Toilet", "Shower", "Night Routine", "Change Clothes"],
        "color": (18, 42, 46),
    },
}


STAT_COLORS: Dict[str, Tuple[int, int, int]] = {
    "health": (255, 116, 116),
    "hunger": (255, 192, 102),
    "energy": (148, 208, 255),
    "hygiene": (170, 240, 200),
    "social": (255, 164, 230),
    "fun": (186, 170, 255),
    "bladder": (214, 194, 136),
    "mood": (255, 230, 136),
}


SPRITE_FILES = {
    "idle": "idle.png",
    "walk1": "walk1.png",
    "walk2": "walk2.png",
    "sleep": "sleep.png",
    "shower": "shower.png",
    "toilet": "toilet.png",
}


@dataclass
class PetState:
    mode: str = MODE_ONBOARD_1
    seen_tutorial: bool = False

    room: str = ROOM_HUB
    x: float = 120.0
    y: float = 164.0

    health: float = 96.0
    hunger: float = 82.0
    energy: float = 86.0
    hygiene: float = 78.0
    social: float = 72.0
    fun: float = 72.0
    bladder: float = 68.0
    mood: float = 84.0

    alive: bool = True
    death_reason: str = ""
    age_seconds: float = 0.0

    panel_open: bool = False
    panel_kind: str = "ACTIONS"
    panel_sel: int = 0
    talk_index: int = 0
    play_submode: str = PLAY_WORLD
    minigame_name: str = ""
    minigame_state: Dict = field(default_factory=dict)

    msg: str = ""
    msg_until: float = 0.0
    dialogue_active: bool = False
    dialogue_queue: List[Dict[str, str]] = field(default_factory=list)
    dialogue_line_idx: int = 0
    dialogue_char_idx: int = 0
    dialogue_cps: float = DIALOGUE_CPS_DEFAULT
    dialogue_line_hold_until: float = 0.0
    dialogue_started_at: float = 0.0

    walk_phase: float = 0.0
    pose: str = "idle"
    pose_until: float = 0.0
    blur_until: float = 0.0

    last_tick: float = 0.0
    last_persist: float = 0.0

    k2_hold_t0: float = 0.0
    k2_long_triggered: bool = False

    k3_hold_t0: float = 0.0
    k3_long_triggered: bool = False
    hugs_given: int = 0
    cuddles_shared: int = 0
    talk_sessions: int = 0
    arcade_sessions: int = 0
    snacks_given: int = 0
    snack_cooldown_until: float = 0.0
    arcade_best: Dict[str, float] = field(default_factory=dict)
    facing: int = 1
    last_move_at: float = 0.0
    sad_idle_t0: float = 0.0
    edge_flash_until: float = 0.0
    edge_flash_side: str = "NONE"


def _state_fields() -> set:
    return set(PetState.__dataclass_fields__.keys())


def _st_from_dict(data: Dict) -> PetState:
    if not isinstance(data, dict):
        return PetState()
    fields = _state_fields()
    cleaned = {k: data[k] for k in fields if k in data}
    try:
        return PetState(**cleaned)
    except Exception:
        return PetState()


def _to_dict(st: PetState) -> Dict:
    return {k: getattr(st, k) for k in _state_fields()}


def _asset_path(ctx, name: str) -> str:
    return ctx.asset("pet_game", name)


def _play_rect(size: Tuple[int, int]) -> Tuple[int, int, int, int]:
    w, h = int(size[0]), int(size[1])
    x0 = PLAY_RECT_LEFT
    y0 = PLAY_RECT_TOP
    x1 = max(x0 + 20, w - PLAY_RECT_RIGHT_PAD)
    y1 = max(y0 + 20, h - PLAY_RECT_BOTTOM_PAD)
    return (x0, y0, x1, y1)


def _play_bounds(size: Tuple[int, int]) -> Tuple[float, float]:
    _x0, y0, _x1, y1 = _play_rect(size)
    top_bound = float(y0 + PLAY_BOUNDS_TOP_PAD)
    bottom_bound = float(y1 - PLAY_BOUNDS_BOTTOM_PAD)
    if bottom_bound <= top_bound:
        mid = float((y0 + y1) // 2)
        return (mid, mid)
    return (top_bound, bottom_bound)


def _data_dialogue_path(ctx) -> str:
    if hasattr(ctx, "data_path"):
        return ctx.data_path(DIALOGUE_REL_PATH)
    base = str(getattr(ctx, "base_dir", ".") or ".")
    return os.path.join(base, ".pocketr", DIALOGUE_REL_PATH)


def _persist_state(ctx, st: PetState, force: bool = False) -> None:
    now = time.time()
    if (not force) and (now - float(st.last_persist) < PERSIST_SECONDS):
        return
    st.last_persist = now
    try:
        write_json_atomic(ctx, STATE_REL_PATH, _to_dict(st))
    except Exception:
        pass


def _pet_defaults() -> Dict:
    return {
        "sim_speed": 1.0,
        "sprite_global_scale": SPRITE_SCALE_DEFAULT,
        "sprite_size_preset": "small",
        "difficulty_profile": "normal",
        "decay_hunger_mult": 1.0,
        "decay_energy_mult": 1.0,
        "decay_hygiene_mult": 1.0,
        "decay_social_mult": 1.0,
        "decay_fun_mult": 1.0,
        "decay_bladder_mult": 1.0,
        "hp_loss_mult": 1.0,
        "hp_regen_mult": 1.0,
        "brick_speed_mult": 1.0,
        "memory_reveal_seconds": 1.1,
        "runner_speed_mult": 1.0,
        "show_tutorial_next_open": False,
    }


def _pet_cfg(ctx) -> Dict:
    prefs = ctx.user.get("_prefs", {}) if isinstance(ctx.user.get("_prefs"), dict) else {}
    pg = prefs.get("pet_game", {}) if isinstance(prefs.get("pet_game"), dict) else {}
    cfg = _pet_defaults()
    for k in cfg:
        if k in pg:
            cfg[k] = pg[k]

    try:
        cfg["sim_speed"] = float(clamp(float(cfg.get("sim_speed", 1.0)), 0.5, 2.0))
    except Exception:
        cfg["sim_speed"] = 1.0

    preset = str(cfg.get("sprite_size_preset", "small") or "small").strip().lower()
    if preset not in ("small", "medium"):
        preset = "small"
    cfg["sprite_size_preset"] = preset
    if "sprite_global_scale" in pg:
        raw_scale = pg.get("sprite_global_scale", SPRITE_SCALE_DEFAULT)
    else:
        raw_scale = SPRITE_SCALE_FROM_MEDIUM if preset == "medium" else SPRITE_SCALE_DEFAULT
    try:
        cfg["sprite_global_scale"] = float(clamp(float(raw_scale), SPRITE_SCALE_MIN, SPRITE_SCALE_MAX))
    except Exception:
        cfg["sprite_global_scale"] = SPRITE_SCALE_DEFAULT

    prof = str(cfg.get("difficulty_profile", "normal") or "normal").strip().lower()
    if prof not in ("easy", "normal", "hard", "custom"):
        prof = "normal"
    cfg["difficulty_profile"] = prof

    for k in (
        "decay_hunger_mult",
        "decay_energy_mult",
        "decay_hygiene_mult",
        "decay_social_mult",
        "decay_fun_mult",
        "decay_bladder_mult",
        "hp_loss_mult",
        "hp_regen_mult",
        "brick_speed_mult",
        "runner_speed_mult",
    ):
        try:
            cfg[k] = float(clamp(float(cfg.get(k, 1.0)), 0.5, 2.0))
        except Exception:
            cfg[k] = 1.0

    try:
        cfg["memory_reveal_seconds"] = float(clamp(float(cfg.get("memory_reveal_seconds", 1.1)), 0.3, 3.0))
    except Exception:
        cfg["memory_reveal_seconds"] = 1.1

    cfg["show_tutorial_next_open"] = bool(cfg.get("show_tutorial_next_open", False))
    return cfg


def _consume_tutorial_flag(ctx) -> bool:
    prefs = ctx.user.get("_prefs", {})
    if not isinstance(prefs, dict):
        return False
    pg = prefs.get("pet_game", {})
    if not isinstance(pg, dict):
        return False
    if not bool(pg.get("show_tutorial_next_open", False)):
        return False

    pg["show_tutorial_next_open"] = False
    prefs["pet_game"] = pg
    ctx.user["_prefs"] = prefs
    try:
        write_json_atomic(ctx, "settings.json", prefs)
    except Exception:
        pass
    return True


def _overlay_font(ctx):
    return getattr(ctx, "font_s", None)


def _meta_font(ctx):
    return getattr(ctx, "font_s", None)


def init(ctx):
    ensure_data_dir(ctx)
    now = time.time()
    cfg = _pet_cfg(ctx)

    raw = read_json(ctx, STATE_REL_PATH, {})
    st = _st_from_dict(raw)

    # First time only intro. After first completion, open straight into gameplay.
    force_tutorial = _consume_tutorial_flag(ctx) or bool(cfg.get("show_tutorial_next_open", False))
    st.mode = MODE_ONBOARD_1 if (force_tutorial or not st.seen_tutorial) else MODE_PLAY
    st.panel_open = False
    st.panel_kind = "ACTIONS"
    st.panel_sel = 0
    st.play_submode = PLAY_WORLD
    st.minigame_name = ""
    st.minigame_state = {}
    st.msg = ""
    st.msg_until = 0.0
    st.dialogue_active = False
    st.dialogue_queue = []
    st.dialogue_line_idx = 0
    st.dialogue_char_idx = 0
    st.dialogue_cps = DIALOGUE_CPS_DEFAULT
    st.dialogue_line_hold_until = 0.0
    st.dialogue_started_at = 0.0

    st.k2_hold_t0 = 0.0
    st.k2_long_triggered = False
    st.k3_hold_t0 = 0.0
    st.k3_long_triggered = False

    st.last_tick = now
    if st.last_move_at <= 0.0:
        st.last_move_at = now
    st.sad_idle_t0 = 0.0

    w, h = int(ctx.disp.width), int(ctx.disp.height)
    x0, _y0, x1, _y1 = _play_rect((w, h))
    top_bound, bottom_bound = _play_bounds((w, h))
    st.x = float(clamp(st.x, float(x0 + 8), float(x1 - 8)))
    st.y = float(clamp(st.y, top_bound, bottom_bound))

    ctx.user["pet_game_v3"] = _to_dict(st)


def _st(ctx) -> PetState:
    raw = ctx.user.get("pet_game_v3", {})
    st = _st_from_dict(raw)
    if st.last_tick <= 0.0:
        st.last_tick = time.time()
    return st


def _save(ctx, st: PetState, force_persist: bool = False) -> None:
    ctx.user["pet_game_v3"] = _to_dict(st)
    _persist_state(ctx, st, force=force_persist)


def _placeholder_sprite(size, label: str) -> Image.Image:
    if isinstance(size, tuple):
        sw = max(8, int(size[0]))
        sh = max(8, int(size[1]))
    else:
        sw = max(8, int(size))
        sh = sw

    img = Image.new("RGBA", (sw, sh), (16, 14, 20, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([1, 1, sw - 2, sh - 2], radius=max(5, min(sw, sh) // 8), fill=(56, 38, 42, 255), outline=(255, 215, 205, 210), width=2)
    head_w = max(10, sw // 2)
    head_h = max(10, sh // 3)
    hx0 = (sw - head_w) // 2
    hy0 = max(6, sh // 7)
    d.ellipse([hx0, hy0, hx0 + head_w, hy0 + head_h], fill=(255, 210, 175, 255), outline=(36, 18, 10, 220), width=2)
    d.text((6, max(0, sh - 14)), label.upper(), fill=(255, 244, 240, 230))
    return img


def _sprite_resample():
    if hasattr(Image, "Resampling"):
        return Image.Resampling.NEAREST
    return Image.NEAREST


def _sprite_global_scale(ctx) -> float:
    cfg = _pet_cfg(ctx)
    try:
        return float(clamp(float(cfg.get("sprite_global_scale", SPRITE_SCALE_DEFAULT)), SPRITE_SCALE_MIN, SPRITE_SCALE_MAX))
    except Exception:
        return SPRITE_SCALE_DEFAULT


def _sprite_canvas() -> Tuple[int, int]:
    return (SPRITE_CANVAS_W, SPRITE_CANVAS_H)


def _canonical_bounds(frames: List[Image.Image]) -> Optional[Tuple[int, int, int, int]]:
    min_l = 10**9
    min_t = 10**9
    max_r = -1
    max_b = -1

    found = False
    for fr in frames:
        if not isinstance(fr, Image.Image):
            continue
        bb = fr.getbbox()
        if not bb:
            continue
        found = True
        min_l = min(min_l, int(bb[0]))
        min_t = min(min_t, int(bb[1]))
        max_r = max(max_r, int(bb[2]))
        max_b = max(max_b, int(bb[3]))

    if not found or max_r <= min_l or max_b <= min_t:
        return None
    return (min_l, min_t, max_r, max_b)


def _bounds_size(bounds: Optional[Tuple[int, int, int, int]]) -> Tuple[int, int]:
    if not bounds:
        return (0, 0)
    return (max(0, int(bounds[2]) - int(bounds[0])), max(0, int(bounds[3]) - int(bounds[1])))


def _shared_sprite_scale(raw_sets: Dict[str, List[Image.Image]], global_scale: float) -> float:
    ref_order = [
        "idle_happy_anim",
        "walking",
        "idle_sad_anim",
        "talking_anim",
        "changing_anim",
        "shower_anim",
        "gaming_anim",
        "hugcuddle_anim",
    ]

    ref_h = 0
    for key in ref_order:
        bounds = _canonical_bounds(raw_sets.get(key, []))
        _w, h = _bounds_size(bounds)
        if h > 0:
            ref_h = h
            break
    if ref_h <= 0:
        ref_h = UNIFORM_BODY_HEIGHT

    max_w = 0
    max_h = 0
    for frames in raw_sets.values():
        w, h = _bounds_size(_canonical_bounds(frames))
        max_w = max(max_w, w)
        max_h = max(max_h, h)

    base_scale = float(UNIFORM_BODY_HEIGHT) / float(max(1, ref_h))
    requested = base_scale * float(global_scale)
    fit_scale = requested
    if max_w > 0 and max_h > 0:
        fit_scale = min(
            float(SPRITE_CANVAS_W - 2) / float(max_w),
            float(SPRITE_CANVAS_H - 2) / float(max_h),
        )
    return max(0.01, min(requested, fit_scale))


def _normalize_anim_frames(
    frames: List[Image.Image],
    shared_scale: float,
    center_anchor: bool = False,
) -> List[Image.Image]:
    if not frames:
        return []

    canvas_w, canvas_h = _sprite_canvas()
    bounds = _canonical_bounds(frames)
    if not bounds:
        return [Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0)) for _ in frames]

    min_l, min_t, max_r, max_b = bounds
    canon_w, canon_h = _bounds_size(bounds)
    nw = max(1, int(round(float(canon_w) * float(shared_scale))))
    nh = max(1, int(round(float(canon_h) * float(shared_scale))))

    out: List[Image.Image] = []
    for fr in frames:
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        if not isinstance(fr, Image.Image):
            out.append(canvas)
            continue

        crop = fr.crop((min_l, min_t, max_r, max_b))
        resized = crop.resize((nw, nh), _sprite_resample())
        px = (canvas_w - nw) // 2
        py = (canvas_h - nh) // 2 if center_anchor else (canvas_h - nh)
        canvas.paste(resized, (px, py), resized)
        out.append(canvas)
    return out


def _anim_frame_paths(ctx, subdir: str) -> List[str]:
    root = ctx.asset("pet_game", "Sprites", subdir)
    paths: List[str] = []
    if os.path.isdir(root):
        for name in sorted(os.listdir(root)):
            low = name.lower()
            if not low.endswith(".png"):
                continue
            if not low.startswith("frame_"):
                continue
            paths.append(os.path.join(root, name))
    return paths


def _first_anim_paths(ctx, names: List[str]) -> Tuple[str, List[str]]:
    for name in names:
        paths = _anim_frame_paths(ctx, name)
        if paths:
            return name, paths
    return "", []


def _load_anim_frames(paths: List[str]) -> List[Image.Image]:
    frames: List[Image.Image] = []
    for p in paths:
        try:
            fr = Image.open(p).convert("RGBA")
            frames.append(fr)
        except Exception:
            pass
    return frames


def _mirror_frames(frames: List[Image.Image]) -> List[Image.Image]:
    out: List[Image.Image] = []
    for fr in frames:
        if isinstance(fr, Image.Image):
            out.append(ImageOps.mirror(fr))
    return out


def _set_anim_pair(sprites: Dict[str, object], key: str, frames: List[Image.Image]) -> None:
    cleaned = [fr for fr in frames if isinstance(fr, Image.Image)]
    sprites[key] = cleaned
    sprites[f"{key}_r"] = cleaned
    sprites[f"{key}_l"] = _mirror_frames(cleaned)


def _load_sprites(ctx) -> Dict[str, object]:
    global_scale = _sprite_global_scale(ctx)
    mtags: List[str] = []
    for k, fname in SPRITE_FILES.items():
        p = _asset_path(ctx, fname)
        try:
            mtags.append(f"{k}:{int(os.path.getmtime(p))}")
        except Exception:
            mtags.append(f"{k}:0")

    anim_sources = {
        "walking": ["Walking"],
        "shower_anim": ["Shower"],
        "gaming_anim": ["Gaming"],
        "idle_happy_anim": ["IdleHappy"],
        "idle_sad_anim": ["IdleSad"],
        "idle_sit_anim": ["IdleSitting", "IdleSit", "Sitting"],
        "talking_anim": ["Talking"],
        "changing_anim": ["Changing"],
        "sleeping_anim": ["Sleeping"],
        "hugcuddle_anim": ["HugCuddle"],
    }

    anim_paths: Dict[str, List[str]] = {}
    for tag, names in anim_sources.items():
        subdir, paths = _first_anim_paths(ctx, names)
        anim_paths[tag] = paths
        if subdir:
            root = ctx.asset("pet_game", "Sprites", subdir)
            try:
                mtags.append(f"{subdir}:{int(os.path.getmtime(root))}")
            except Exception:
                mtags.append(f"{subdir}:0")
        for p in paths:
            try:
                mtags.append(f"{tag}:{int(os.path.getmtime(p))}:{os.path.basename(p)}")
            except Exception:
                mtags.append(f"{tag}:0:{os.path.basename(p)}")

    key = f"slot-v3:{global_scale:.2f}|" + "|".join(mtags)
    cache = ctx.user.get("_pet_sprite_cache", None)
    if isinstance(cache, dict) and cache.get("key") == key and isinstance(cache.get("data"), dict):
        return cache["data"]

    raw_sets: Dict[str, List[Image.Image]] = {}
    for tag in anim_sources:
        raw_sets[tag] = _load_anim_frames(anim_paths.get(tag, []))

    raw_idle: Optional[Image.Image] = None
    raw_walk1: Optional[Image.Image] = None
    raw_walk2: Optional[Image.Image] = None
    for key_name, attr in (("idle", "raw_idle"), ("walk1", "raw_walk1"), ("walk2", "raw_walk2")):
        p = _asset_path(ctx, SPRITE_FILES[key_name])
        try:
            img = Image.open(p).convert("RGBA")
            if attr == "raw_idle":
                raw_idle = img
            elif attr == "raw_walk1":
                raw_walk1 = img
            else:
                raw_walk2 = img
        except Exception:
            pass

    if not raw_sets.get("idle_happy_anim") and isinstance(raw_idle, Image.Image):
        raw_sets["idle_happy_anim"] = [raw_idle]
    if not raw_sets.get("walking"):
        walk_seed: List[Image.Image] = []
        if isinstance(raw_walk1, Image.Image):
            walk_seed.append(raw_walk1)
        if isinstance(raw_walk2, Image.Image):
            walk_seed.append(raw_walk2)
        if walk_seed:
            raw_sets["walking"] = walk_seed

    shared_scale = _shared_sprite_scale(raw_sets, global_scale)
    fallback_center = "sleeping_anim" in SPRITE_CENTER_ANCHOR_ANIMS

    def _single_from_path(name: str, center_anchor: bool = False) -> Image.Image:
        p = _asset_path(ctx, name)
        try:
            src = Image.open(p).convert("RGBA")
            norm = _normalize_anim_frames([src], shared_scale, center_anchor=center_anchor)
            if norm:
                return norm[0]
        except Exception:
            pass
        return _placeholder_sprite(_sprite_canvas(), name.split(".")[0])

    sprites: Dict[str, object] = {}
    sprites["idle"] = _single_from_path("idle.png")
    sprites["walk1"] = _single_from_path("walk1.png")
    sprites["walk2"] = _single_from_path("walk2.png")
    sprites["sleep"] = _single_from_path("sleep.png", center_anchor=fallback_center)
    sprites["shower"] = _single_from_path("shower.png")
    sprites["toilet"] = _single_from_path("toilet.png")

    walk_anim_r = _normalize_anim_frames(
        raw_sets.get("walking", []),
        shared_scale,
    )
    shower_anim = _normalize_anim_frames(
        raw_sets.get("shower_anim", []),
        shared_scale,
    )
    gaming_anim = _normalize_anim_frames(
        raw_sets.get("gaming_anim", []),
        shared_scale,
    )
    idle_happy_anim = _normalize_anim_frames(
        raw_sets.get("idle_happy_anim", []),
        shared_scale,
    )
    idle_sad_anim = _normalize_anim_frames(
        raw_sets.get("idle_sad_anim", []),
        shared_scale,
    )
    idle_sit_anim = _normalize_anim_frames(
        raw_sets.get("idle_sit_anim", []),
        shared_scale,
    )
    talking_anim = _normalize_anim_frames(
        raw_sets.get("talking_anim", []),
        shared_scale,
    )
    changing_anim = _normalize_anim_frames(
        raw_sets.get("changing_anim", []),
        shared_scale,
    )
    sleeping_anim = _normalize_anim_frames(
        raw_sets.get("sleeping_anim", []),
        shared_scale,
        center_anchor=True,
    )
    hugcuddle_anim = _normalize_anim_frames(
        raw_sets.get("hugcuddle_anim", []),
        shared_scale,
    )

    if walk_anim_r:
        sprites["walk_anim_r"] = walk_anim_r
        sprites["walk_anim_l"] = [ImageOps.mirror(fr) for fr in walk_anim_r]
    else:
        fallback_w1 = sprites.get("walk1")
        fallback_w2 = sprites.get("walk2")
        frames: List[Image.Image] = []
        if isinstance(fallback_w1, Image.Image):
            frames.append(fallback_w1)
        if isinstance(fallback_w2, Image.Image):
            frames.append(fallback_w2)
        if not frames and isinstance(sprites.get("idle"), Image.Image):
            frames = [sprites["idle"]]
        sprites["walk_anim_r"] = frames
        sprites["walk_anim_l"] = [ImageOps.mirror(fr) for fr in frames] if frames else []

    fallback_idle = sprites.get("idle")
    fallback_idle_frames = [fallback_idle] if isinstance(fallback_idle, Image.Image) else []
    fallback_sleep = sprites.get("sleep")
    fallback_sleep_frames = [fallback_sleep] if isinstance(fallback_sleep, Image.Image) else fallback_idle_frames
    fallback_sh = sprites.get("shower")
    fallback_sh_frames = [fallback_sh] if isinstance(fallback_sh, Image.Image) else fallback_idle_frames

    _set_anim_pair(sprites, "shower_anim", shower_anim if shower_anim else fallback_sh_frames)
    _set_anim_pair(sprites, "gaming_anim", gaming_anim if gaming_anim else fallback_idle_frames)
    _set_anim_pair(sprites, "idle_happy_anim", idle_happy_anim if idle_happy_anim else fallback_idle_frames)
    _set_anim_pair(sprites, "idle_sad_anim", idle_sad_anim if idle_sad_anim else fallback_idle_frames)
    _set_anim_pair(sprites, "idle_sit_anim", idle_sit_anim if idle_sit_anim else list(sprites.get("idle_happy_anim", [])))
    _set_anim_pair(sprites, "talking_anim", talking_anim if talking_anim else list(sprites.get("idle_happy_anim", [])))
    _set_anim_pair(sprites, "changing_anim", changing_anim if changing_anim else list(sprites.get("idle_happy_anim", [])))
    _set_anim_pair(sprites, "sleeping_anim", sleeping_anim if sleeping_anim else fallback_sleep_frames)
    _set_anim_pair(sprites, "hugcuddle_anim", hugcuddle_anim if hugcuddle_anim else list(sprites.get("talking_anim", [])))

    ctx.user["_pet_sprite_cache"] = {"key": key, "data": sprites}
    return sprites


def _dialogue_data(ctx) -> Dict[str, List[Dict]]:
    data_path = _data_dialogue_path(ctx)
    fallback_path = _asset_path(ctx, "dialogue.json")

    try:
        data_mtime = int(os.path.getmtime(data_path))
    except Exception:
        data_mtime = -1

    try:
        fallback_mtime = int(os.path.getmtime(fallback_path))
    except Exception:
        fallback_mtime = -1

    key = f"{data_path}:{data_mtime}|{fallback_path}:{fallback_mtime}"
    cache = ctx.user.get("_pet_dialogue_cache", {})
    if isinstance(cache, dict) and cache.get("key") == key and isinstance(cache.get("data"), dict):
        return cache["data"]

    data: Dict[str, List[Dict]] = {}
    source = data_path if os.path.isfile(data_path) else fallback_path

    try:
        with open(source, "r", encoding="utf-8") as f:
            raw_text = f.read()
        try:
            raw = json.loads(raw_text)
        except Exception:
            # Be tolerant of trailing commas in editable dialogue JSON.
            relaxed = re.sub(r",(\s*[}\]])", r"\1", raw_text)
            raw = json.loads(relaxed)
        if isinstance(raw, dict):
            for k, v in raw.items():
                if not isinstance(v, list):
                    continue
                cleaned: List[Dict] = []
                for item in v:
                    if isinstance(item, dict):
                        cleaned.append(item)
                if cleaned:
                    data[str(k)] = cleaned
    except Exception:
        data = {}

    if not data:
        data = {
            "greeting": [{"player": "Hey love, I missed you.", "pet": "I missed you too, come here.", "social": 4, "fun": 2}],
            "feelings": [{"player": "How are you feeling?", "pet": "Better when we talk like this.", "social": 3, "fun": 1}],
            "reassurance": [{"player": "I am proud of you.", "pet": "That means a lot to me.", "social": 4, "fun": 1}],
        }

    ctx.user["_pet_dialogue_cache"] = {"key": key, "data": data}
    return data


def _set_pose(st: PetState, pose: str, seconds: float, now: float) -> None:
    st.pose = pose
    st.pose_until = now + max(0.0, float(seconds))


def _make_message(st: PetState, text: str, now: float, seconds: float = 2.4) -> None:
    st.msg = str(text)
    st.msg_until = now + max(0.8, float(seconds))


def _dialogue_line_text(entry: Dict[str, str]) -> str:
    speaker = str(entry.get("speaker", "") or "").strip()
    text = str(entry.get("text", "") or "").strip()
    if speaker and text:
        return f"{speaker}: {text}"
    if text:
        return text
    return speaker


def _clear_dialogue(st: PetState) -> None:
    st.dialogue_active = False
    st.dialogue_queue = []
    st.dialogue_line_idx = 0
    st.dialogue_char_idx = 0
    st.dialogue_line_hold_until = 0.0
    st.dialogue_started_at = 0.0


def _estimate_dialogue_seconds(lines: List[Dict[str, str]], cps: float, hold_seconds: float) -> float:
    total = 0.0
    c = max(8.0, float(cps))
    hold = max(0.05, float(hold_seconds))
    for ln in lines:
        total += (len(_dialogue_line_text(ln)) / c) + hold + 0.05
    return max(0.9, total)


def _queue_scene_lines(
    st: PetState,
    lines: List[Dict[str, str]],
    now: float,
    cps: float = DIALOGUE_CPS_DEFAULT,
    hold_seconds: float = DIALOGUE_LINE_HOLD_SECONDS,
    pose: str = "",
    min_pose_seconds: float = 0.0,
) -> None:
    cleaned: List[Dict[str, str]] = []
    for ln in lines:
        if not isinstance(ln, dict):
            continue
        speaker = str(ln.get("speaker", "") or "").strip()
        text = str(ln.get("text", "") or "").strip()
        if not text and not speaker:
            continue
        cleaned.append({"speaker": speaker, "text": text})

    if not cleaned:
        _clear_dialogue(st)
        return

    base_hold = max(0.05, float(hold_seconds))
    estimated = _estimate_dialogue_seconds(cleaned, float(cps), base_hold)
    target_total = estimated
    if pose:
        target_total = max(estimated, float(min_pose_seconds))
    if target_total > estimated and cleaned:
        base_hold += (target_total - estimated) / float(len(cleaned))

    for ln in cleaned:
        ln["hold"] = float(base_hold)

    st.dialogue_active = True
    st.dialogue_queue = cleaned
    st.dialogue_line_idx = 0
    st.dialogue_char_idx = 0
    st.dialogue_cps = max(8.0, float(cps))
    st.dialogue_line_hold_until = 0.0
    st.dialogue_started_at = now
    st.msg = ""
    st.msg_until = 0.0

    if pose:
        _set_pose(st, pose, target_total, now)


def _queue_scene_text(
    st: PetState,
    text: str,
    now: float,
    speaker: str = "",
    cps: float = DIALOGUE_CPS_DEFAULT,
    hold_seconds: float = DIALOGUE_LINE_HOLD_SECONDS,
    pose: str = "",
    min_pose_seconds: float = 0.0,
) -> None:
    _queue_scene_lines(
        st,
        [{"speaker": speaker, "text": str(text)}],
        now=now,
        cps=cps,
        hold_seconds=hold_seconds,
        pose=pose,
        min_pose_seconds=min_pose_seconds,
    )


def _advance_dialogue_line(st: PetState, now: float) -> None:
    st.dialogue_line_idx += 1
    if st.dialogue_line_idx >= len(st.dialogue_queue):
        _clear_dialogue(st)
        return
    st.dialogue_char_idx = 0
    st.dialogue_line_hold_until = 0.0
    st.dialogue_started_at = now


def _update_dialogue_playback(st: PetState, dt: float, now: float, ev: Dict[str, bool]) -> bool:
    if not st.dialogue_active:
        return False
    if st.dialogue_line_idx < 0 or st.dialogue_line_idx >= len(st.dialogue_queue):
        _clear_dialogue(st)
        return False

    line = _dialogue_line_text(st.dialogue_queue[st.dialogue_line_idx])
    line_len = len(line)
    if line_len <= 0:
        _advance_dialogue_line(st, now)
        return False

    confirm = ("K1" in ev) or ("PRESS" in ev)
    if confirm:
        if st.dialogue_char_idx < line_len:
            st.dialogue_char_idx = line_len
            st.dialogue_line_hold_until = max(float(st.dialogue_line_hold_until), now + 0.05)
        else:
            _advance_dialogue_line(st, now)
        return True

    if st.dialogue_char_idx < line_len:
        elapsed = max(0.0, now - float(st.dialogue_started_at))
        chars = int(elapsed * max(8.0, float(st.dialogue_cps)))
        st.dialogue_char_idx = max(st.dialogue_char_idx, min(line_len, chars))

    hold_for_line = DIALOGUE_LINE_HOLD_SECONDS
    try:
        hold_for_line = float(st.dialogue_queue[st.dialogue_line_idx].get("hold", DIALOGUE_LINE_HOLD_SECONDS))
    except Exception:
        hold_for_line = DIALOGUE_LINE_HOLD_SECONDS
    hold_for_line = max(0.05, hold_for_line)

    if st.dialogue_char_idx >= line_len:
        if st.dialogue_line_hold_until <= 0.0:
            st.dialogue_line_hold_until = now + hold_for_line
        if now >= float(st.dialogue_line_hold_until):
            _advance_dialogue_line(st, now)

    return False


def _enter_room(st: PetState, room: str, side: str, w: int, h: int, now: float) -> None:
    st.room = room
    x0, _y0, x1, _y1 = _play_rect((w, h))
    top_bound, bottom_bound = _play_bounds((w, h))

    if side == "LEFT":
        st.x = float(x1 - 8)
    elif side == "RIGHT":
        st.x = float(x0 + 8)
    elif side == "UP":
        st.y = float(bottom_bound - 2)
    elif side == "DOWN":
        st.y = float(top_bound + 2)

    _make_message(st, f"You and him moved into {ROOMS.get(room, {}).get('name', room)}.", now, seconds=1.2)


def _trigger_edge_flash(st: PetState, side: str, now: float) -> None:
    st.edge_flash_side = str(side).upper()
    st.edge_flash_until = now + BLOCK_FLASH_SECONDS


def _apply_movement(ctx, st: PetState, dt: float, now: float) -> bool:
    if dt <= 0.0:
        return False

    if now < float(st.pose_until):
        return False

    mx = (1 if ctx.inputs.is_down("RIGHT") else 0) - (1 if ctx.inputs.is_down("LEFT") else 0)
    my = (1 if ctx.inputs.is_down("DOWN") else 0) - (1 if ctx.inputs.is_down("UP") else 0)

    if mx == 0 and my == 0:
        return False

    if mx < 0:
        st.facing = -1
    elif mx > 0:
        st.facing = 1

    mlen = math.sqrt(float(mx * mx + my * my))
    if mlen > 0:
        mx = float(mx) / mlen
        my = float(my) / mlen

    speed = 84.0
    st.x += mx * speed * dt
    st.y += my * speed * dt
    st.walk_phase += dt * 8.0

    w, h = int(ctx.disp.width), int(ctx.disp.height)
    x0, _y0, x1, _y1 = _play_rect((w, h))
    top_bound, bottom_bound = _play_bounds((w, h))
    edge = 10.0

    room_info = ROOMS.get(st.room, ROOMS[ROOM_HUB])
    neigh = room_info.get("neighbors", {})

    # Horizontal room switches use the same visible clamp boundary as rendering,
    # so left/right transitions happen at the edge instead of after an extra hold.
    sprites = _load_sprites(ctx)
    probe_sprite = _sprite_for_state(st, sprites, moving=True, now=now)
    half_w = float(_sprite_visible_width(probe_sprite)) * 0.5
    left_vis = float(x0 + 2) + half_w
    right_vis = float(x1 - 1) - half_w

    if mx < 0 and st.x < (left_vis - ROOM_SWITCH_INSET_X):
        nxt = neigh.get("LEFT")
        if nxt:
            _enter_room(st, str(nxt), "LEFT", w, h, now)
            return True
        st.x = left_vis
        _trigger_edge_flash(st, "LEFT", now)
    elif mx > 0 and st.x > (right_vis + ROOM_SWITCH_INSET_X):
        nxt = neigh.get("RIGHT")
        if nxt:
            _enter_room(st, str(nxt), "RIGHT", w, h, now)
            return True
        st.x = right_vis
        _trigger_edge_flash(st, "RIGHT", now)

    if st.y < (top_bound - edge):
        nxt = neigh.get("UP")
        if nxt:
            _enter_room(st, str(nxt), "UP", w, h, now)
        else:
            st.y = top_bound + 2
            _trigger_edge_flash(st, "UP", now)
    elif st.y > (bottom_bound + edge):
        nxt = neigh.get("DOWN")
        if nxt:
            _enter_room(st, str(nxt), "DOWN", w, h, now)
        else:
            st.y = bottom_bound - 2
            _trigger_edge_flash(st, "DOWN", now)

    return True


def _base_drain_per_hour(cfg: Dict) -> Dict[str, float]:
    profile = str(cfg.get("difficulty_profile", "normal"))
    profile_decay = 1.0
    if profile == "easy":
        profile_decay = 0.85
    elif profile == "hard":
        profile_decay = 1.20

    return {
        "hunger": 5.0 * DECAY_TUNE_MULT,
        "energy": 4.2 * DECAY_TUNE_MULT,
        "hygiene": 2.4 * DECAY_TUNE_MULT,
        "social": 2.0 * DECAY_TUNE_MULT,
        "fun": 2.2 * DECAY_TUNE_MULT,
        "bladder": 4.6 * DECAY_TUNE_MULT,
        "profile_decay": profile_decay,
    }


def _activity_load(st: PetState, moving: bool) -> float:
    load = 1.0
    if moving:
        load += 0.55
    if st.room == ROOM_ARCADE:
        load += 0.35
    if st.play_submode == PLAY_MINIGAME:
        load += 0.65
    if st.pose in ("talk", "hugcuddle", "shower", "changing"):
        load += 0.12
    return max(1.0, load)


def _apply_decay(st: PetState, dt: float, moving: bool, now: float, cfg: Dict) -> None:
    if not st.alive:
        return
    if dt <= 0.0:
        return

    st.age_seconds += dt * AGE_ACCEL

    profile = str(cfg.get("difficulty_profile", "normal") or "normal")
    drains = _base_drain_per_hour(cfg)
    profile_decay = float(drains.get("profile_decay", 1.0))
    activity_load = _activity_load(st, moving)
    load_delta = max(0.0, activity_load - 1.0)

    hunger_scale = profile_decay * float(cfg.get("decay_hunger_mult", 1.0)) * (1.0 + (0.62 * load_delta))
    energy_scale = profile_decay * float(cfg.get("decay_energy_mult", 1.0)) * (1.0 + (0.95 * load_delta))
    hygiene_scale = profile_decay * float(cfg.get("decay_hygiene_mult", 1.0)) * (1.0 + (0.40 * load_delta))
    social_scale = profile_decay * float(cfg.get("decay_social_mult", 1.0)) * (1.0 + (0.10 * load_delta))
    fun_scale = profile_decay * float(cfg.get("decay_fun_mult", 1.0)) * (1.0 + (0.18 * load_delta))
    bladder_scale = profile_decay * float(cfg.get("decay_bladder_mult", 1.0)) * (1.0 + (0.74 * load_delta))

    hunger_drop = (drains["hunger"] * hunger_scale) * (dt / 3600.0)
    energy_drop = (drains["energy"] * energy_scale) * (dt / 3600.0)
    hygiene_drop = (drains["hygiene"] * hygiene_scale) * (dt / 3600.0)
    social_drop = (drains["social"] * social_scale) * (dt / 3600.0)
    fun_drop = (drains["fun"] * fun_scale) * (dt / 3600.0)
    bladder_drop = (drains["bladder"] * bladder_scale) * (dt / 3600.0)

    sleeping = st.pose == "sleep" and now < st.pose_until
    if sleeping:
        energy_drop -= 7.5 * (dt / 3600.0)
        bladder_drop += 1.1 * (dt / 3600.0)
        hunger_drop += 0.8 * (dt / 3600.0)

    st.hunger = clamp(st.hunger - hunger_drop, 0.0, 100.0)
    st.energy = clamp(st.energy - energy_drop, 0.0, 100.0)
    st.hygiene = clamp(st.hygiene - hygiene_drop, 0.0, 100.0)
    st.social = clamp(st.social - social_drop, 0.0, 100.0)
    st.fun = clamp(st.fun - fun_drop, 0.0, 100.0)
    st.bladder = clamp(st.bladder - bladder_drop, 0.0, 100.0)

    def _def(v: float, thresh: float) -> float:
        if v >= thresh:
            return 0.0
        return clamp((thresh - v) / max(1e-6, thresh), 0.0, 1.0)

    stress = 0.0
    stress += 0.26 * _def(st.hunger, 30.0)
    stress += 0.24 * _def(st.energy, 28.0)
    stress += 0.18 * _def(st.hygiene, 26.0)
    stress += 0.22 * _def(st.bladder, 24.0)
    stress += 0.05 * _def(st.social, 22.0)
    stress += 0.05 * _def(st.fun, 22.0)
    stress += 0.08 * _def(st.energy, 36.0) * clamp(load_delta, 0.0, 2.0)

    critical_count = sum(1 for v in [st.hunger, st.energy, st.hygiene, st.bladder] if v < 15.0)

    hp_loss_hour = 0.0
    if stress > 0.15:
        hp_loss_hour += (stress - 0.15) * 5.6
    if critical_count >= 2:
        hp_loss_hour += (critical_count - 1) * 2.8
    if critical_count >= 3:
        hp_loss_hour += 2.2
    if critical_count >= 4:
        hp_loss_hour += 1.2
    if load_delta > 0.0 and st.energy < 35.0:
        hp_loss_hour += (clamp(load_delta, 0.0, 1.8) * _def(st.energy, 35.0) * 1.8)

    hp_regen_hour = 0.0
    core_min = min(st.hunger, st.energy, st.hygiene, st.bladder)
    if core_min > 62.0 and st.mood > 65.0:
        hp_regen_hour = 0.75
    elif core_min > 48.0 and st.mood > 52.0:
        hp_regen_hour = 0.22

    profile_loss = 1.0
    profile_regen = 1.0
    if profile == "easy":
        profile_loss = 0.75
        profile_regen = 1.15
    elif profile == "hard":
        profile_loss = 1.25
        profile_regen = 0.90

    hp_loss_hour *= profile_loss * float(cfg.get("hp_loss_mult", 1.0))
    hp_regen_hour *= profile_regen * float(cfg.get("hp_regen_mult", 1.0))
    st.health = clamp(st.health + ((hp_regen_hour - hp_loss_hour) * (dt / 3600.0)), 0.0, 100.0)

    mood_target = (
        (st.health * 0.28)
        + (st.fun * 0.20)
        + (st.social * 0.17)
        + (st.energy * 0.12)
        + (st.hunger * 0.09)
        + (st.hygiene * 0.07)
        + (st.bladder * 0.07)
    )
    lerp = clamp(dt * 2.0, 0.0, 1.0)
    st.mood = clamp(st.mood + ((mood_target - st.mood) * lerp), 0.0, 100.0)

    if st.health <= 0.0:
        st.alive = False
        st.panel_open = False
        st.pose = "idle"
        lowest = {
            "hunger": st.hunger,
            "energy": st.energy,
            "hygiene": st.hygiene,
            "social": st.social,
            "fun": st.fun,
            "bladder": st.bladder,
        }
        reason = min(lowest, key=lowest.get)
        st.death_reason = reason
        _make_message(st, f"He faded away from low {reason}. Press B1 to restart.", now, 8.0)


def _boost(st: PetState, **kwargs: float) -> None:
    for k, delta in kwargs.items():
        if not hasattr(st, k):
            continue
        cur = float(getattr(st, k))
        setattr(st, k, float(clamp(cur + float(delta), 0.0, 100.0)))


def _run_action(st: PetState, action: str, now: float) -> str:
    if action == "Check In":
        _boost(st, social=3, mood=2, fun=1)
        return "You checked in on him. He smiles right away."

    if action == "Stretch":
        _boost(st, energy=2, mood=1, fun=1)
        return "You and him did a tiny stretch break."

    if action == "Cuddle":
        _boost(st, social=8, mood=6, energy=-2, fun=3)
        st.cuddles_shared = int(st.cuddles_shared) + 1
        _set_pose(st, "hugcuddle", ACTION_POSE_SECONDS, now)
        return "Cuddle time. He feels safe and warm with you."

    if action == "Give Hug":
        _boost(st, social=7, mood=5, fun=2, energy=-1)
        st.hugs_given = int(st.hugs_given) + 1
        _set_pose(st, "hugcuddle", ACTION_POSE_SECONDS, now)
        return "Big hug delivered. He looks extra happy."

    if action == "Sleep":
        _boost(st, energy=14, mood=4, hunger=-3, bladder=-5)
        _set_pose(st, "sleep", ACTION_POSE_SECONDS, now)
        return "Nap time. He is recovering energy."

    if action == "Watch TV":
        _boost(st, fun=7, social=1, energy=-2, hunger=-1)
        return "Cozy TV time together."

    if action == "Lounge":
        _boost(st, energy=6, mood=3, fun=2, bladder=-2)
        return "Lounge time. Calm, close, comfy."

    if action == "Eat Snack":
        return "Choose a snack option."

    if action in ARCADE_GAMES:
        return "Arcade game starting."

    if action == "Use Toilet":
        _boost(st, bladder=38, hygiene=-3, mood=1)
        st.blur_until = now + 2.0
        _set_pose(st, "toilet", 2.0, now)
        return "Woah look away. Privacy moment."

    if action == "Shower":
        _boost(st, hygiene=34, mood=5, energy=-3)
        _set_pose(st, "shower", ACTION_POSE_SECONDS, now)
        return "Shower done. He feels fresh and clean."

    if action == "Night Routine":
        _boost(st, hygiene=18, energy=11, mood=7, social=2, bladder=-6, hunger=-3)
        _set_pose(st, "changing", ACTION_POSE_SECONDS, now)
        return "Night routine complete. Cozy mode unlocked."

    if action == "Change Clothes":
        _boost(st, mood=5, hygiene=2, social=1)
        _set_pose(st, "changing", ACTION_POSE_SECONDS, now)
        return "Outfit change done. He looks so good."

    return "He waits for your next move."


def _run_snack_action(st: PetState, snack: str, now: float) -> str:
    st.snacks_given = int(st.snacks_given) + 1
    st.snack_cooldown_until = now + SNACK_COOLDOWN_SECONDS

    if snack == "Light Snack":
        _boost(st, hunger=8, mood=1, bladder=-1)
        return "Light snack shared. He feels a little better."
    if snack == "Balanced Meal":
        _boost(st, hunger=16, energy=3, mood=2, bladder=-3)
        return "Balanced meal done. He looks recharged."
    _boost(st, hunger=6, fun=7, mood=5, energy=-2, hygiene=-2)
    return "Sweet treat time. He is happy and extra playful."


def _panel_items(st: PetState, dialogue: Dict[str, List[Dict]]) -> List[str]:
    if st.panel_kind == "TALK":
        cats = list(dialogue.keys())
        return cats or ["greeting"]
    if st.panel_kind == "SNACK":
        return list(SNACK_OPTIONS)

    room_info = ROOMS.get(st.room, ROOMS[ROOM_HUB])
    actions = room_info.get("actions", [])
    if isinstance(actions, list):
        return [str(a) for a in actions]
    return []


def _talk_once(st: PetState, dialogue: Dict[str, List[Dict]], category: str, now: float) -> Tuple[str, str]:
    entries = dialogue.get(category, [])
    if not entries:
        _boost(st, social=2, mood=1)
        st.talk_sessions = int(st.talk_sessions) + 1
        return ("Hey love.", "I missed you.")

    idx = st.talk_index % len(entries)
    st.talk_index += 1
    line = entries[idx]

    user_line = str(line.get("player", "Hi"))
    pet_line = str(line.get("pet", "Hey"))
    social_gain = float(line.get("social", 3))
    fun_gain = float(line.get("fun", 2))

    _boost(st, social=social_gain, fun=fun_gain, mood=2)
    st.talk_sessions = int(st.talk_sessions) + 1
    return (user_line, pet_line)


def _handle_short_long(st: PetState, now: float, ev: Dict[str, bool], inputs, key: str, hold_attr: str, long_attr: str, long_seconds: float) -> str:
    key_up = f"{key}_UP"

    if key in ev:
        setattr(st, hold_attr, now)
        setattr(st, long_attr, False)

    t0 = float(getattr(st, hold_attr, 0.0) or 0.0)
    long_triggered = bool(getattr(st, long_attr, False))
    if t0 > 0.0 and inputs.is_down(key) and (not long_triggered):
        if (now - t0) >= long_seconds:
            setattr(st, long_attr, True)
            return "LONG"

    if key_up in ev:
        t0 = float(getattr(st, hold_attr, 0.0) or 0.0)
        was_tracking = (t0 > 0.0) or bool(getattr(st, long_attr, False))
        if not was_tracking:
            setattr(st, hold_attr, 0.0)
            setattr(st, long_attr, False)
            return "NONE"
        was_long = bool(getattr(st, long_attr, False)) or (t0 > 0.0 and (now - t0) >= long_seconds)
        setattr(st, hold_attr, 0.0)
        setattr(st, long_attr, False)
        return "LONG" if was_long else "SHORT"

    return "NONE"


def _quick_support(st: PetState, now: float, dialogue: Optional[Dict[str, List[Dict]]] = None) -> None:
    pairs: List[Tuple[str, str]] = []
    if isinstance(dialogue, dict):
        for cat in ("reassurance", "flirty", "greeting", "feelings"):
            for item in dialogue.get(cat, []):
                if isinstance(item, dict):
                    player_line = str(item.get("player", "")).strip()
                    pet_line = str(item.get("pet", "")).strip()
                    if player_line and pet_line:
                        pairs.append((player_line, pet_line))
    if not pairs:
        pairs = [
            ("Hey you, I wanted to check on you.", "I feel better already, thank you."),
            ("You doing okay right now?", "Much better now that we are talking."),
            ("I am here with you.", "I needed that. I missed you."),
            ("Quick little check-in.", "Big comfort for me, thank you."),
        ]
    _boost(st, mood=1.5, social=1.0)
    player_line, pet_line = random.choice(pairs)
    _queue_scene_lines(
        st,
        [{"speaker": "You", "text": player_line}, {"speaker": "Him", "text": pet_line}],
        now=now,
        pose="talk",
        min_pose_seconds=ACTION_POSE_SECONDS,
    )


def _quick_care(st: PetState, now: float) -> None:
    if st.hunger < 50:
        _boost(st, hunger=4, mood=1)
        _queue_scene_text(st, "You brought him a quick snack. He needed that.", now=now)
        return
    if st.energy < 50:
        _boost(st, energy=4, mood=1)
        _queue_scene_text(st, "You told him to rest a little.", now=now)
        return
    if st.hygiene < 45:
        _boost(st, hygiene=5, mood=1)
        _queue_scene_text(st, "Quick tidy-up done. He feels better.", now=now)
        return
    if st.social < 45 or st.fun < 45:
        _boost(st, social=3, fun=3, mood=1)
        _queue_scene_text(st, "A quick little date break helped him.", now=now)
        return

    _boost(st, mood=2, health=0.3)
    _queue_scene_text(st, "Quick care and affection delivered.", now=now)


def _capture_gallery_dir(ctx) -> str:
    if hasattr(ctx, "data_path"):
        root = ctx.data_path("gallery")
    else:
        root = os.path.join(ensure_data_dir(ctx), "gallery")
    try:
        os.makedirs(root, exist_ok=True)
    except Exception:
        pass
    return root


def _gallery_image_paths(ctx) -> List[str]:
    roots: List[str] = [ctx.asset("blank_gallery")]
    if hasattr(ctx, "data_path"):
        roots.append(ctx.data_path("gallery"))
    else:
        base = str(getattr(ctx, "base_dir", ".") or ".")
        roots.append(os.path.join(base, ".pocketr", "gallery"))

    found: List[str] = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            for name in os.listdir(root):
                p = os.path.join(root, name)
                if not os.path.isfile(p):
                    continue
                ext = os.path.splitext(name)[1].lower()
                if ext in GALLERY_IMAGE_EXTS:
                    found.append(os.path.abspath(p))
        except Exception:
            continue

    return sorted(set(found))


def _sprite_draw_pos(st: PetState, sprite: Image.Image) -> Tuple[int, int]:
    px = int(st.x - (sprite.width // 2))
    if st.pose == "sleep":
        py = int(st.y - (sprite.height // 2))
    else:
        py = int(st.y - sprite.height)
    return px, py


def _sprite_visible_width(sprite: Image.Image) -> int:
    if not isinstance(sprite, Image.Image):
        return 1
    bb = sprite.getbbox()
    if not bb:
        return max(1, int(sprite.width))
    return max(1, int(bb[2]) - int(bb[0]))


def _clamp_sprite_x_for_frame(
    ctx,
    x: float,
    sprite: Image.Image,
    left_inset: float = 0.0,
    right_inset: float = 0.0,
) -> float:
    sw = _sprite_visible_width(sprite)
    x0, _y0, x1, _y1 = _play_rect((int(ctx.disp.width), int(ctx.disp.height)))
    left = float(x0 + 2 + (sw * 0.5) - max(0.0, float(left_inset)))
    right = float(x1 - 1 - (sw * 0.5) + max(0.0, float(right_inset)))
    if right < left:
        mid = float((x0 + x1) / 2.0)
        left = mid
        right = mid
    return float(clamp(float(x), left, right))


def _paste_sprite_clipped(
    img: Image.Image,
    sprite: Image.Image,
    px: int,
    py: int,
    clip_rect: Tuple[int, int, int, int],
) -> None:
    cx0, cy0, cx1, cy1 = [int(v) for v in clip_rect]
    ix0 = max(px, cx0)
    iy0 = max(py, cy0)
    ix1 = min(px + sprite.width, cx1)
    iy1 = min(py + sprite.height, cy1)
    if ix1 <= ix0 or iy1 <= iy0:
        return

    sx0 = ix0 - px
    sy0 = iy0 - py
    sx1 = sx0 + (ix1 - ix0)
    sy1 = sy0 + (iy1 - iy0)
    part = sprite.crop((sx0, sy0, sx1, sy1))
    img.paste(part, (ix0, iy0), part)


def _capture_pet_photo(ctx, st: PetState, now: float) -> str:
    try:
        w, h = int(ctx.disp.width), int(ctx.disp.height)
        img = _load_layered_room(ctx, st.room, (w, h)).convert("RGB")
        sprites = _load_sprites(ctx)
        sprite = _sprite_for_state(st, sprites, moving=False, now=now)
        draw_x = _clamp_sprite_x_for_frame(ctx, st.x, sprite)
        px = int(draw_x - (sprite.width // 2))
        py = int(st.y - (sprite.height // 2)) if st.pose == "sleep" else int(st.y - sprite.height)
        x0, y0, x1, y1 = _play_rect((w, h))
        _paste_sprite_clipped(img, sprite, px, py, (x0 + 2, y0 + 2, x1 - 1, y1 - 1))
        fg = _load_room_foreground(ctx, st.room, (w, h))
        if isinstance(fg, Image.Image):
            img_rgba = Image.alpha_composite(img.convert("RGBA"), fg)
            img = img_rgba.convert("RGB")

        d = ImageDraw.Draw(img)
        stamp = time.strftime("%Y-%m-%d %H:%M")
        tw = int(d.textlength(stamp, font=ctx.font_s))
        d.text((w - tw - 5, h - 12), stamp, font=ctx.font_s, fill=(240, 228, 222))

        out_dir = _capture_gallery_dir(ctx)
        name = f"pet_{int(now)}.png"
        path = os.path.join(out_dir, name)
        img.save(path, "PNG")
        ctx.user["_blank_paths_cache"] = {"t": 0.0, "paths": []}
        ctx.user["_blank_cards_cache"] = {}
        return name
    except Exception:
        return ""


def _brick_layout(w: int, level: int) -> List[Dict]:
    cols = 6
    lvl = max(1, min(BRICK_MAX_LEVELS, int(level)))
    if lvl <= 1:
        rows = 1
    elif lvl <= 3:
        rows = 2
    else:
        rows = 3
    gap_x = 4
    gap_y = 3
    bw = max(16, (w - 28 - ((cols - 1) * gap_x)) // cols)
    bh = 10
    start_x = 14
    start_y = 30
    bricks: List[Dict] = []

    for r in range(rows):
        x = start_x
        for c in range(cols):
            hp = 1
            if r == 0 and lvl >= 3:
                hp = 2
            elif lvl >= 5 and r == 1 and (c % 2 == 0):
                hp = 2
            bricks.append({
                "x": x,
                "y": start_y + (r * (bh + gap_y)),
                "w": bw,
                "h": bh,
                "alive": True,
                "hp": hp,
            })
            x += bw + gap_x
    return bricks


def _brick_reset_ball(mg: Dict, w: int, h: int, level: int) -> None:
    base_speed = float(mg.get("base_speed", 88.0))
    idx = max(1, min(int(level), len(BRICK_LEVEL_SPEED_FACTORS))) - 1
    speed = base_speed * float(BRICK_LEVEL_SPEED_FACTORS[idx])
    x_dir = -1.0 if random.random() < 0.5 else 1.0
    mg["paddle_x"] = float(w // 2)
    mg["ball_x"] = float(w // 2)
    mg["ball_y"] = float(h - 34)
    mg["ball_vx"] = speed * 0.88 * x_dir
    mg["ball_vy"] = -speed


def _spawn_snake_food(grid_w: int, grid_h: int, snake: List[List[int]]) -> List[int]:
    occupied = {(int(p[0]), int(p[1])) for p in snake if isinstance(p, list) and len(p) >= 2}
    candidates: List[Tuple[int, int]] = []
    for y in range(grid_h):
        for x in range(grid_w):
            if (x, y) not in occupied:
                candidates.append((x, y))
    if not candidates:
        return [max(0, grid_w // 2), max(0, grid_h // 2)]
    fx, fy = random.choice(candidates)
    return [int(fx), int(fy)]


def _start_minigame(ctx, st: PetState, name: str, cfg: Dict, now: float) -> None:
    w, h = int(ctx.disp.width), int(ctx.disp.height)
    _clear_dialogue(st)
    st.play_submode = PLAY_MINIGAME
    st.minigame_name = str(name)
    st.panel_open = False
    st.panel_kind = "ACTIONS"
    st.panel_sel = 0

    if name == "Brick Breaker":
        speed = 88.0 * float(cfg.get("brick_speed_mult", 1.0))
        st.minigame_state = {
            "base_speed": speed,
            "level": 1,
            "max_levels": BRICK_MAX_LEVELS,
            "bricks": _brick_layout(w, 1),
            "score": 0.0,
            "elapsed": 0.0,
            "level_up_until": 0.0,
        }
        _brick_reset_ball(st.minigame_state, w, h, 1)
    elif name == "Memory Match":
        media = _gallery_image_paths(ctx)
        random.shuffle(media)
        keys = media[:3]
        while len(keys) < 3:
            keys.append(f"fallback:{len(keys)}")
        cards = [0, 1, 2, 0, 1, 2]
        random.shuffle(cards)
        st.minigame_state = {
            "cards": cards,
            "card_keys": keys,
            "matched": [False] * 6,
            "revealed": [],
            "cursor": 0,
            "pending_until": 0.0,
            "moves": 0,
            "elapsed": 0.0,
        }
    elif name == "Runner Dash":
        st.minigame_state = {
            "player_y": float(h - 26),
            "vy": 0.0,
            "on_ground": True,
            "obstacles": [],
            "spawn_in": 0.9,
            "elapsed": 0.0,
            "score": 0.0,
        }
    elif name == "Micro Snake":
        snake = [[7, 7], [6, 7], [5, 7]]
        st.minigame_state = {
            "grid_w": 14,
            "grid_h": 14,
            "snake": snake,
            "dir": [1, 0],
            "next_dir": [1, 0],
            "food": _spawn_snake_food(14, 14, snake),
            "tick": 0.0,
            "step_sec": 0.12,
            "score": 0.0,
            "elapsed": 0.0,
        }
    elif name == "Heart Catch":
        st.minigame_state = {
            "basket_x": float(w // 2),
            "items": [],
            "spawn_in": 0.55,
            "elapsed": 0.0,
            "score": 0.0,
            "lives": 3,
        }
    else:  # Reflex Tap
        zone_w = 26
        zone_min = 20
        zone_max = max(zone_min, w - zone_w - 20)
        st.minigame_state = {
            "elapsed": 0.0,
            "score": 0.0,
            "round": 1,
            "max_rounds": 10,
            "marker_x": 22.0,
            "marker_vx": 122.0,
            "zone_x": float(random.randint(zone_min, zone_max)),
            "zone_w": zone_w,
            "result": "",
            "result_until": 0.0,
            "streak": 0,
        }
    st.arcade_sessions = int(st.arcade_sessions) + 1
    st.msg = ""
    st.msg_until = 0.0


def _finish_minigame(st: PetState, name: str, win: bool, score: float, now: float) -> None:
    if not isinstance(st.arcade_best, dict):
        st.arcade_best = {}
    prev_best = float(st.arcade_best.get(str(name), 0.0))
    if float(score) > prev_best:
        st.arcade_best[str(name)] = float(score)

    # Reward loop: mood/fun-centric, minor fatigue/hunger cost.
    if win:
        _boost(st, fun=8.0, mood=6.0, energy=-2.5, hunger=-1.8, bladder=-1.2)
        _queue_scene_text(st, f"{name} win. He had so much fun.", now=now)
    else:
        _boost(st, fun=3.0, mood=1.5, energy=-2.0, hunger=-1.2, bladder=-0.8)
        _queue_scene_text(st, f"{name}: {int(score)} points for him.", now=now)
    st.play_submode = PLAY_WORLD
    st.minigame_name = ""
    st.minigame_state = {}


def _update_brick_breaker(ctx, st: PetState, dt: float, ev: Dict[str, bool], cfg: Dict, now: float) -> Tuple[bool, bool, float]:
    w, h = int(ctx.disp.width), int(ctx.disp.height)
    mg = st.minigame_state
    if not isinstance(mg, dict):
        return True, False, 0.0

    paddle_w = 42
    paddle_h = 5
    paddle_y = h - 14
    paddle_speed = 120.0
    if ctx.inputs.is_down("LEFT"):
        mg["paddle_x"] = float(mg.get("paddle_x", w / 2)) - (paddle_speed * dt)
    if ctx.inputs.is_down("RIGHT"):
        mg["paddle_x"] = float(mg.get("paddle_x", w / 2)) + (paddle_speed * dt)
    mg["paddle_x"] = float(clamp(float(mg.get("paddle_x", w / 2)), 10 + paddle_w / 2, w - 10 - paddle_w / 2))

    mg["ball_x"] = float(mg.get("ball_x", w / 2)) + (float(mg.get("ball_vx", 80.0)) * dt)
    mg["ball_y"] = float(mg.get("ball_y", h / 2)) + (float(mg.get("ball_vy", -80.0)) * dt)
    mg["elapsed"] = float(mg.get("elapsed", 0.0)) + dt
    mg["score"] = float(mg.get("score", 0.0)) + (dt * 5.0)

    bx = float(mg.get("ball_x", w / 2))
    by = float(mg.get("ball_y", h / 2))
    bvx = float(mg.get("ball_vx", 80.0))
    bvy = float(mg.get("ball_vy", -80.0))

    if bx < 10:
        bx = 10
        bvx = abs(bvx)
    elif bx > w - 10:
        bx = w - 10
        bvx = -abs(bvx)
    if by < 20:
        by = 20
        bvy = abs(bvy)

    px0 = float(mg.get("paddle_x", w / 2)) - (paddle_w / 2)
    px1 = px0 + paddle_w
    if (paddle_y - 4) <= by <= (paddle_y + paddle_h) and px0 <= bx <= px1 and bvy > 0:
        bvy = -abs(bvy)
        offs = (bx - (px0 + paddle_w / 2)) / max(1.0, paddle_w / 2)
        bvx += offs * 38.0

    bricks = mg.get("bricks", [])
    for b in bricks:
        if not b.get("alive", False):
            continue
        bx0 = float(b.get("x", 0))
        by0 = float(b.get("y", 0))
        bw = float(b.get("w", 20))
        bh = float(b.get("h", 10))
        if (bx0 - 3) <= bx <= (bx0 + bw + 3) and (by0 - 3) <= by <= (by0 + bh + 3):
            hp = int(b.get("hp", 1))
            if hp > 1:
                b["hp"] = hp - 1
                mg["score"] = float(mg.get("score", 0.0)) + 4.0
            else:
                b["alive"] = False
                mg["score"] = float(mg.get("score", 0.0)) + 10.0
            bvy = -bvy
            break

    mg["ball_x"] = bx
    mg["ball_y"] = by
    mg["ball_vx"] = bvx
    mg["ball_vy"] = bvy

    alive_count = sum(1 for b in bricks if bool(b.get("alive", False)))
    if alive_count <= 0:
        level = int(mg.get("level", 1))
        max_levels = int(mg.get("max_levels", BRICK_MAX_LEVELS))
        if level < max_levels:
            level += 1
            mg["level"] = level
            mg["bricks"] = _brick_layout(w, level)
            mg["level_up_until"] = now + 0.8
            mg["score"] = float(mg.get("score", 0.0)) + (16.0 * level)
            _brick_reset_ball(mg, w, h, level)
            return False, False, float(mg.get("score", 0.0))
        return True, True, float(mg.get("score", 0.0))
    if by > (h - 3):
        return True, False, float(mg.get("score", 0.0))
    return False, False, float(mg.get("score", 0.0))


def _update_memory_match(st: PetState, dt: float, ev: Dict[str, bool], cfg: Dict, now: float) -> Tuple[bool, bool, float]:
    mg = st.minigame_state
    if not isinstance(mg, dict):
        return True, False, 0.0
    mg["elapsed"] = float(mg.get("elapsed", 0.0)) + dt

    cards = list(mg.get("cards", []))
    if len(cards) != 6:
        return True, False, 0.0
    matched = list(mg.get("matched", [False] * 6))
    revealed = list(mg.get("revealed", []))
    cursor = int(mg.get("cursor", 0))
    pending_until = float(mg.get("pending_until", 0.0))

    if pending_until > 0.0 and now >= pending_until:
        revealed = []
        pending_until = 0.0

    if pending_until <= 0.0:
        c = cursor
        if "LEFT" in ev:
            c = c - 1 if (c % 3) > 0 else c + 2
        if "RIGHT" in ev:
            c = c + 1 if (c % 3) < 2 else c - 2
        if "UP" in ev:
            c = (c - 3) % 6
        if "DOWN" in ev:
            c = (c + 3) % 6
        cursor = c

        if ("K1" in ev) or ("PRESS" in ev):
            if (not matched[cursor]) and (cursor not in revealed):
                revealed.append(cursor)
                if len(revealed) == 2:
                    mg["moves"] = int(mg.get("moves", 0)) + 1
                    a, b = revealed[0], revealed[1]
                    if cards[a] == cards[b]:
                        matched[a] = True
                        matched[b] = True
                        revealed = []
                    else:
                        pending_until = now + float(cfg.get("memory_reveal_seconds", 1.1))

    mg["cursor"] = cursor
    mg["revealed"] = revealed
    mg["matched"] = matched
    mg["pending_until"] = pending_until

    if all(bool(x) for x in matched):
        moves = int(mg.get("moves", 0))
        score = max(5, 30 - (moves * 2))
        return True, True, float(score)
    return False, False, float(max(0, 20 - int(mg.get("moves", 0))))


def _update_runner_dash(ctx, st: PetState, dt: float, ev: Dict[str, bool], cfg: Dict) -> Tuple[bool, bool, float]:
    w, h = int(ctx.disp.width), int(ctx.disp.height)
    mg = st.minigame_state
    if not isinstance(mg, dict):
        return True, False, 0.0

    ground_y = h - 26
    player_x = 34
    player_w = 12
    player_h = 16
    grav = 330.0
    jump_v = -145.0

    if (("K1" in ev) or ("PRESS" in ev)) and bool(mg.get("on_ground", True)):
        mg["vy"] = jump_v
        mg["on_ground"] = False

    vy = float(mg.get("vy", 0.0)) + (grav * dt)
    py = float(mg.get("player_y", ground_y)) + (vy * dt)
    if py >= ground_y:
        py = float(ground_y)
        vy = 0.0
        mg["on_ground"] = True

    elapsed = float(mg.get("elapsed", 0.0)) + dt
    speed = (86.0 + min(42.0, elapsed * 3.4)) * float(cfg.get("runner_speed_mult", 1.0))
    obs = list(mg.get("obstacles", []))
    for o in obs:
        o["x"] = float(o.get("x", w)) - (speed * dt)
    obs = [o for o in obs if float(o.get("x", -20.0)) > -24.0]

    spawn_in = float(mg.get("spawn_in", 0.8)) - dt
    if spawn_in <= 0.0:
        oh = random.randint(10, 22)
        ow = random.randint(10, 18)
        obs.append({"x": float(w + 10), "w": float(ow), "h": float(oh)})
        spawn_in = random.uniform(0.85, 1.45)

    player_top = py - player_h
    collided = False
    for o in obs:
        ox = float(o.get("x", w))
        ow = float(o.get("w", 12))
        oh = float(o.get("h", 14))
        otop = ground_y - oh
        if (player_x < ox + ow) and (player_x + player_w > ox) and (player_top < ground_y) and ((py) > otop):
            collided = True
            break

    score = float(mg.get("score", 0.0)) + (dt * (8.0 + (speed * 0.03)))
    mg["player_y"] = py
    mg["vy"] = vy
    mg["obstacles"] = obs
    mg["spawn_in"] = spawn_in
    mg["elapsed"] = elapsed
    mg["score"] = score

    if collided:
        return True, False, score
    if elapsed >= 20.0:
        return True, True, score
    return False, False, score


def _update_micro_snake(st: PetState, dt: float, ev: Dict[str, bool]) -> Tuple[bool, bool, float]:
    mg = st.minigame_state
    if not isinstance(mg, dict):
        return True, False, 0.0

    grid_w = max(8, int(mg.get("grid_w", 14)))
    grid_h = max(8, int(mg.get("grid_h", 14)))
    snake = [[int(p[0]), int(p[1])] for p in list(mg.get("snake", [])) if isinstance(p, list) and len(p) >= 2]
    if not snake:
        snake = [[grid_w // 2, grid_h // 2]]

    cur_dir = list(mg.get("dir", [1, 0]))
    if len(cur_dir) < 2:
        cur_dir = [1, 0]
    next_dir = list(mg.get("next_dir", cur_dir))
    if len(next_dir) < 2:
        next_dir = list(cur_dir)

    candidate = None
    if "LEFT" in ev:
        candidate = [-1, 0]
    elif "RIGHT" in ev:
        candidate = [1, 0]
    elif "UP" in ev:
        candidate = [0, -1]
    elif "DOWN" in ev:
        candidate = [0, 1]
    if candidate and (candidate[0] != -int(cur_dir[0]) or candidate[1] != -int(cur_dir[1])):
        next_dir = candidate

    tick = float(mg.get("tick", 0.0)) + dt
    elapsed = float(mg.get("elapsed", 0.0)) + dt
    score = float(mg.get("score", 0.0))
    step_sec = max(0.06, float(mg.get("step_sec", 0.12)))
    food = list(mg.get("food", [grid_w // 2, grid_h // 2]))
    if len(food) < 2:
        food = [grid_w // 2, grid_h // 2]

    while tick >= step_sec:
        tick -= step_sec
        cur_dir = list(next_dir)
        head_x = int(snake[0][0]) + int(cur_dir[0])
        head_y = int(snake[0][1]) + int(cur_dir[1])
        if head_x < 0 or head_x >= grid_w or head_y < 0 or head_y >= grid_h:
            mg["elapsed"] = elapsed
            mg["score"] = score
            return True, False, score
        if any((head_x == int(p[0]) and head_y == int(p[1])) for p in snake):
            mg["elapsed"] = elapsed
            mg["score"] = score
            return True, False, score

        snake.insert(0, [head_x, head_y])
        if head_x == int(food[0]) and head_y == int(food[1]):
            score += 1.0
            if score >= 25.0:
                mg["snake"] = snake
                mg["dir"] = cur_dir
                mg["next_dir"] = next_dir
                mg["tick"] = tick
                mg["elapsed"] = elapsed
                mg["score"] = score
                return True, True, score
            food = _spawn_snake_food(grid_w, grid_h, snake)
        else:
            snake.pop()

    mg["snake"] = snake
    mg["dir"] = cur_dir
    mg["next_dir"] = next_dir
    mg["tick"] = tick
    mg["food"] = food
    mg["elapsed"] = elapsed
    mg["score"] = score
    return False, False, score


def _update_heart_catch(ctx, st: PetState, dt: float, ev: Dict[str, bool]) -> Tuple[bool, bool, float]:
    w, h = int(ctx.disp.width), int(ctx.disp.height)
    mg = st.minigame_state
    if not isinstance(mg, dict):
        return True, False, 0.0

    basket_w = 28
    basket_h = 6
    basket_y = h - 24
    basket_speed = 140.0
    basket_x = float(mg.get("basket_x", w / 2))
    if ctx.inputs.is_down("LEFT"):
        basket_x -= basket_speed * dt
    if ctx.inputs.is_down("RIGHT"):
        basket_x += basket_speed * dt
    basket_x = float(clamp(basket_x, 12 + basket_w / 2.0, w - 12 - basket_w / 2.0))

    items = list(mg.get("items", []))
    spawn_in = float(mg.get("spawn_in", 0.55)) - dt
    if spawn_in <= 0.0:
        kind = "bomb" if random.random() < 0.26 else "heart"
        items.append(
            {
                "x": float(random.randint(12, max(12, w - 12))),
                "y": 20.0,
                "vy": float(random.uniform(54.0, 94.0)),
                "kind": kind,
            }
        )
        spawn_in = random.uniform(0.35, 0.9)

    score = float(mg.get("score", 0.0))
    lives = int(mg.get("lives", 3))
    remain: List[Dict] = []
    bx0 = basket_x - (basket_w / 2.0)
    bx1 = basket_x + (basket_w / 2.0)
    by0 = float(basket_y)
    by1 = float(basket_y + basket_h)

    for item in items:
        x = float(item.get("x", 0.0))
        y = float(item.get("y", 0.0)) + (float(item.get("vy", 68.0)) * dt)
        kind = str(item.get("kind", "heart"))
        caught = (bx0 <= x <= bx1) and (by0 <= y <= by1 + 2.0)
        if caught:
            if kind == "heart":
                score += 1.5
            else:
                lives -= 1
            continue
        if y > float(h + 8):
            continue
        item["y"] = y
        remain.append(item)

    elapsed = float(mg.get("elapsed", 0.0)) + dt
    mg["basket_x"] = basket_x
    mg["items"] = remain
    mg["spawn_in"] = spawn_in
    mg["score"] = score
    mg["elapsed"] = elapsed
    mg["lives"] = lives

    if lives <= 0:
        return True, False, score
    if elapsed >= 35.0:
        return True, True, score
    return False, False, score


def _update_reflex_tap(ctx, st: PetState, dt: float, ev: Dict[str, bool], now: float) -> Tuple[bool, bool, float]:
    w = int(ctx.disp.width)
    mg = st.minigame_state
    if not isinstance(mg, dict):
        return True, False, 0.0

    lane_l = 18.0
    lane_r = float(max(26, w - 18))
    marker_x = float(mg.get("marker_x", lane_l))
    marker_vx = float(mg.get("marker_vx", 120.0))
    marker_x += marker_vx * dt
    if marker_x <= lane_l:
        marker_x = lane_l
        marker_vx = abs(marker_vx)
    elif marker_x >= lane_r:
        marker_x = lane_r
        marker_vx = -abs(marker_vx)

    zone_w = max(14.0, float(mg.get("zone_w", 26)))
    zone_x = float(mg.get("zone_x", 80.0))
    zone_x = float(clamp(zone_x, lane_l, lane_r - zone_w))
    round_idx = int(mg.get("round", 1))
    max_rounds = int(mg.get("max_rounds", 10))
    score = float(mg.get("score", 0.0))
    streak = int(mg.get("streak", 0))
    result_until = float(mg.get("result_until", 0.0))
    result = str(mg.get("result", ""))

    if (("K1" in ev) or ("PRESS" in ev)) and now >= result_until and round_idx <= max_rounds:
        marker_c = marker_x
        zone_c = zone_x + (zone_w / 2.0)
        dist = abs(marker_c - zone_c)
        half = max(1.0, zone_w / 2.0)
        if dist <= half:
            accuracy = 1.0 - (dist / half)
            points = int(20 + (accuracy * 80.0) + (streak * 5))
            streak += 1
            result = f"Hit +{points}"
        else:
            points = max(0, int(10 - ((dist - half) * 0.7)))
            streak = 0
            result = f"Miss +{points}"
        score += float(points)
        round_idx += 1
        result_until = now + 0.30

        if round_idx <= max_rounds:
            min_zone = int(lane_l)
            max_zone = int(max(min_zone, lane_r - zone_w))
            zone_x = float(random.randint(min_zone, max_zone))

    elapsed = float(mg.get("elapsed", 0.0)) + dt
    mg["marker_x"] = marker_x
    mg["marker_vx"] = marker_vx
    mg["zone_x"] = zone_x
    mg["round"] = round_idx
    mg["score"] = score
    mg["streak"] = streak
    mg["result"] = result
    mg["result_until"] = result_until
    mg["elapsed"] = elapsed

    if round_idx > max_rounds:
        return True, bool(score >= 450.0), score
    return False, False, score


def _update_minigame(ctx, st: PetState, dt: float, ev: Dict[str, bool], cfg: Dict, now: float) -> bool:
    if st.play_submode != PLAY_MINIGAME:
        return False
    name = str(st.minigame_name or "")
    if not name:
        st.play_submode = PLAY_WORLD
        st.minigame_state = {}
        return False

    if "K2" in ev:
        _finish_minigame(st, name, False, float(st.minigame_state.get("score", 0.0)) if isinstance(st.minigame_state, dict) else 0.0, now)
        return True

    if name == "Brick Breaker":
        done, win, score = _update_brick_breaker(ctx, st, dt, ev, cfg, now)
    elif name == "Memory Match":
        done, win, score = _update_memory_match(st, dt, ev, cfg, now)
    elif name == "Runner Dash":
        done, win, score = _update_runner_dash(ctx, st, dt, ev, cfg)
    elif name == "Micro Snake":
        done, win, score = _update_micro_snake(st, dt, ev)
    elif name == "Heart Catch":
        done, win, score = _update_heart_catch(ctx, st, dt, ev)
    else:
        done, win, score = _update_reflex_tap(ctx, st, dt, ev, now)

    if done:
        _finish_minigame(st, name, win, score, now)
        return True
    return True


def update(ctx, dt: float, ev: Dict[str, bool]) -> bool:
    st = _st(ctx)
    now = time.time()
    cfg = _pet_cfg(ctx)

    # Strict frame-based progression while app is active only.
    sim_dt = max(0.0, min(float(dt), 0.25)) * float(cfg.get("sim_speed", 1.0))
    st.last_tick = now

    if st.msg and now >= float(st.msg_until):
        st.msg = ""

    if now >= float(st.pose_until):
        st.pose = "idle"

    k2_evt = _handle_short_long(st, now, ev, ctx.inputs, "K2", "k2_hold_t0", "k2_long_triggered", K2_EXIT_HOLD_SECONDS)
    b3_evt = _handle_short_long(st, now, ev, ctx.inputs, "K3", "k3_hold_t0", "k3_long_triggered", B3_SHORT_MAX_SECONDS)

    if k2_evt == "LONG":
        _clear_dialogue(st)
        st.panel_open = False
        st.panel_kind = "ACTIONS"
        st.panel_sel = 0
        st.play_submode = PLAY_WORLD
        st.minigame_name = ""
        st.minigame_state = {}
        _save(ctx, st, force_persist=True)
        return True

    intro_confirm = ("K1" in ev) or ("PRESS" in ev)

    if st.mode == MODE_ONBOARD_1:
        if intro_confirm:
            st.mode = MODE_ONBOARD_2
        elif k2_evt == "SHORT":
            _save(ctx, st, force_persist=True)
            return True
        _save(ctx, st)
        return False

    if st.mode == MODE_ONBOARD_2:
        if intro_confirm:
            st.mode = MODE_PLAY
            st.seen_tutorial = True
            st.last_tick = now
            st.play_submode = PLAY_WORLD
            _queue_scene_text(st, "Welcome to Pocket-R pet life.", now=now, speaker="Him")
            _save(ctx, st, force_persist=True)
            return False
        elif k2_evt == "SHORT":
            _save(ctx, st, force_persist=True)
            return True
        _save(ctx, st)
        return False

    # MODE_PLAY
    if st.play_submode == PLAY_MINIGAME:
        _update_minigame(ctx, st, sim_dt, ev, cfg, now)
        _apply_decay(st, sim_dt * 1.20, moving=True, now=now, cfg=cfg)
        _save(ctx, st)
        return False

    dialogue = _dialogue_data(ctx)
    if st.dialogue_active and st.panel_open:
        st.panel_open = False
        st.panel_kind = "ACTIONS"
        st.panel_sel = 0
        st.play_submode = PLAY_WORLD

    dialogue_confirm_consumed = _update_dialogue_playback(st, sim_dt, now, ev)

    if k2_evt == "SHORT" and not st.dialogue_active:
        if st.panel_open:
            st.panel_open = False
            st.panel_kind = "ACTIONS"
            st.panel_sel = 0
            st.play_submode = PLAY_WORLD
        else:
            _quick_support(st, now, dialogue)

    # B3 short quick care action (global hold-B3 shutdown still handled by launcher).
    if b3_evt == "SHORT" and st.alive and (not st.dialogue_active):
        _quick_care(st, now)

    opened_panel_now = False
    # B1 and joystick PRESS both open the actions panel.
    if (not dialogue_confirm_consumed) and (not st.dialogue_active) and (("PRESS" in ev) or ("K1" in ev)) and st.alive and (not st.panel_open) and st.play_submode == PLAY_WORLD:
        st.panel_open = True
        st.panel_kind = "ACTIONS"
        st.panel_sel = 0
        st.play_submode = PLAY_PANEL
        opened_panel_now = True

    if not st.alive:
        if (("K1" in ev) or ("PRESS" in ev)) and (not st.dialogue_active):
            keep_age = st.age_seconds
            st = PetState(mode=MODE_PLAY, seen_tutorial=True, age_seconds=keep_age, last_tick=now)
            st.play_submode = PLAY_WORLD
            _queue_scene_text(st, "He is back. Take good care of him.", now=now)
            _save(ctx, st, force_persist=True)
            return False
        _save(ctx, st)
        return False

    moving = False
    if (not st.dialogue_active) and (not st.panel_open) and st.play_submode == PLAY_WORLD:
        moving = _apply_movement(ctx, st, sim_dt, now)
    if moving:
        st.last_move_at = now
    elif st.last_move_at <= 0.0:
        st.last_move_at = now

    _apply_decay(st, sim_dt, moving=moving, now=now, cfg=cfg)

    if st.panel_open and (not st.dialogue_active):
        items = _panel_items(st, dialogue)
        if items:
            st.panel_sel = int(clamp(float(st.panel_sel), 0.0, float(len(items) - 1)))

        if "UP" in ev and items:
            st.panel_sel = (st.panel_sel - 1) % len(items)
        if "DOWN" in ev and items:
            st.panel_sel = (st.panel_sel + 1) % len(items)

        # B1 confirm only.
        if ("K1" in ev) and items and (not opened_panel_now):
            chosen = items[st.panel_sel]

            if st.panel_kind == "ACTIONS" and chosen == "Talk":
                st.panel_kind = "TALK"
                st.panel_sel = 0
            elif st.panel_kind == "ACTIONS" and chosen == "Eat Snack":
                if now < float(st.snack_cooldown_until):
                    remain = int(max(1.0, float(st.snack_cooldown_until) - now))
                    _queue_scene_text(st, f"Snack cooldown: {remain}s", now=now)
                    st.panel_open = False
                    st.panel_kind = "ACTIONS"
                    st.panel_sel = 0
                    st.play_submode = PLAY_WORLD
                else:
                    st.panel_kind = "SNACK"
                    st.panel_sel = 0
            elif st.panel_kind == "ACTIONS" and chosen == "Save & Quit":
                st.panel_open = False
                st.panel_kind = "ACTIONS"
                st.panel_sel = 0
                st.play_submode = PLAY_WORLD
                _save(ctx, st, force_persist=True)
                return True
            elif st.panel_kind == "ACTIONS" and chosen == "Open Gallery":
                st.panel_open = False
                st.panel_kind = "ACTIONS"
                st.panel_sel = 0
                st.play_submode = PLAY_WORLD
                _queue_scene_text(st, "Opening Gallery...", now=now)
                ctx.user["_app_switch_to"] = 1
                _save(ctx, st, force_persist=True)
                return False
            elif st.panel_kind == "ACTIONS" and chosen == "Take Picture":
                snap = _capture_pet_photo(ctx, st, now)
                if snap:
                    _queue_scene_text(st, f"Saved photo: {snap}", now=now)
                else:
                    _queue_scene_text(st, "Photo capture failed.", now=now)
                st.panel_open = False
                st.panel_kind = "ACTIONS"
                st.panel_sel = 0
                st.play_submode = PLAY_WORLD
            elif st.panel_kind == "ACTIONS" and chosen in ARCADE_GAMES:
                _start_minigame(ctx, st, chosen, cfg, now)
            elif st.panel_kind == "SNACK":
                msg = _run_snack_action(st, chosen, now)
                hold = max(DIALOGUE_LINE_HOLD_SECONDS, max(0.0, float(st.pose_until) - now))
                _queue_scene_text(st, msg, now=now, hold_seconds=hold)
                st.panel_open = False
                st.panel_kind = "ACTIONS"
                st.panel_sel = 0
                st.play_submode = PLAY_WORLD
            elif st.panel_kind == "TALK":
                you_line, him_line = _talk_once(st, dialogue, chosen, now)
                _queue_scene_lines(
                    st,
                    [
                        {"speaker": "You", "text": you_line},
                        {"speaker": "Him", "text": him_line},
                    ],
                    now=now,
                    cps=DIALOGUE_CPS_DEFAULT,
                    hold_seconds=DIALOGUE_LINE_HOLD_SECONDS,
                    pose="talk",
                    min_pose_seconds=ACTION_POSE_SECONDS,
                )
                st.panel_open = False
                st.panel_kind = "ACTIONS"
                st.panel_sel = 0
                st.play_submode = PLAY_WORLD
            else:
                msg = _run_action(st, chosen, now)
                hold = max(DIALOGUE_LINE_HOLD_SECONDS, max(0.0, float(st.pose_until) - now))
                _queue_scene_text(st, msg, now=now, hold_seconds=hold)
                st.panel_open = False
                st.panel_kind = "ACTIONS"
                st.panel_sel = 0
                st.play_submode = PLAY_WORLD

    _save(ctx, st)
    return False


def _room_base_fallback(size: Tuple[int, int], room: str) -> Image.Image:
    w, h = size
    base = Image.new("RGBA", (w, h), (12, 10, 10, 255))
    d = ImageDraw.Draw(base)

    room_info = ROOMS.get(room, ROOMS[ROOM_HUB])
    r, g, b = room_info.get("color", (32, 24, 24))

    for y in range(h):
        t = y / float(max(1, h - 1))
        rr = int(10 + (r * (0.45 + 0.55 * (1.0 - t))))
        gg = int(6 + (g * (0.42 + 0.58 * (1.0 - t))))
        bb = int(8 + (b * (0.40 + 0.60 * (1.0 - t))))
        d.line([0, y, w, y], fill=(rr, gg, bb, 255), width=1)

    return base


def _load_layered_room(ctx, room: str, size: Tuple[int, int]) -> Image.Image:
    w, h = size
    room_info = ROOMS.get(room, ROOMS[ROOM_HUB])
    slug = str(room_info.get("slug", "hub"))

    base_path = ctx.asset("pet_game", "rooms", slug, "base.png")
    if not os.path.isfile(base_path):
        alt_path = ctx.asset("pet_game", "rooms", slug, "Base.png")
        if os.path.isfile(alt_path):
            base_path = alt_path

    try:
        base_mtime = int(os.path.getmtime(base_path))
    except Exception:
        base_mtime = 0

    key = f"{room}:base-only:{w}x{h}:{base_path}:{base_mtime}"
    cache = ctx.user.get("_pet_room_cache", {})
    if isinstance(cache, dict) and cache.get("key") == key and isinstance(cache.get("img"), Image.Image):
        return cache["img"].copy()

    if os.path.isfile(base_path):
        try:
            base = Image.open(base_path).convert("RGBA")
            if base.size != (w, h):
                base = base.resize((w, h))
        except Exception:
            base = _room_base_fallback((w, h), room)
    else:
        base = _room_base_fallback((w, h), room)

    out = base.copy().convert("RGBA")
    ctx.user["_pet_room_cache"] = {"key": key, "img": out.copy()}
    return out.convert("RGB")


def _room_foreground_fallback(size: Tuple[int, int]) -> Image.Image:
    w, h = size
    x0, y0, x1, y1 = _play_rect((w, h))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer, "RGBA")

    # Foreground wall lip so sprite appears to pass behind room border.
    d.rounded_rectangle([x0, y0, x1, y1], radius=7, outline=(255, 226, 216, 238), width=3)
    return layer


def _load_room_foreground(ctx, room: str, size: Tuple[int, int]) -> Image.Image:
    w, h = size
    room_info = ROOMS.get(room, ROOMS[ROOM_HUB])
    slug = str(room_info.get("slug", "hub"))
    fg_path = ctx.asset("pet_game", "rooms", slug, "fg.png")

    try:
        fg_mtime = int(os.path.getmtime(fg_path))
    except Exception:
        fg_mtime = 0

    key = f"{room}:fg:{w}x{h}:{fg_mtime}"
    cache = ctx.user.get("_pet_room_fg_cache", {})
    if isinstance(cache, dict) and cache.get("key") == key and isinstance(cache.get("img"), Image.Image):
        return cache["img"].copy()

    if os.path.isfile(fg_path):
        try:
            fg = Image.open(fg_path).convert("RGBA")
            if fg.size != (w, h):
                fg = fg.resize((w, h))
        except Exception:
            fg = _room_foreground_fallback((w, h))
    else:
        fg = _room_foreground_fallback((w, h))

    ctx.user["_pet_room_fg_cache"] = {"key": key, "img": fg.copy()}
    return fg


def _load_intro_slide(ctx, filename: str, fallback_title: str, size: Tuple[int, int]) -> Image.Image:
    path = _asset_path(ctx, filename)
    if os.path.isfile(path):
        try:
            img = Image.open(path).convert("RGB")
            if img.size != size:
                img = img.resize(size)
            return img
        except Exception:
            pass

    w, h = size
    img = Image.new("RGB", size, (14, 10, 12))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / float(max(1, h - 1))
        r = int(24 + (80 * (1.0 - t)))
        g = int(10 + (22 * (1.0 - t)))
        b = int(14 + (28 * (1.0 - t)))
        d.line([0, y, w, y], fill=(r, g, b), width=1)

    d.rounded_rectangle([12, 12, w - 13, h - 13], radius=8, outline=(255, 228, 214), width=2)
    d.text((20, 24), fallback_title, fill=(255, 246, 238), font=ctx.font_l)
    d.text((20, 70), f"[{filename} placeholder]", fill=(226, 210, 204), font=ctx.font_s)
    d.text((20, h - 26), "B1/PRESS next  B2 exit", fill=(226, 210, 204), font=ctx.font_s)
    return img


def _draw_stat_bar(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, label: str, value: float, color: Tuple[int, int, int], font) -> None:
    frac = clamp(float(value) / 100.0, 0.0, 1.0)
    d.rounded_rectangle([x, y, x + w, y + h], radius=4, fill=(18, 14, 16, 220), outline=(255, 220, 210, 90), width=1)
    fill_w = int((w - 2) * frac)
    if fill_w > 0:
        d.rounded_rectangle([x + 1, y + 1, x + 1 + fill_w, y + h - 1], radius=3, fill=(color[0], color[1], color[2], 220))
    d.text((x + 3, y + 1), label, font=font, fill=(20, 14, 12))


def _draw_stats(ctx, img: Image.Image, st: PetState) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    w, _h = img.size

    margin = 7
    gap = 4
    cols = 4
    bar_w = (w - (margin * 2) - (gap * (cols - 1))) // cols
    bar_h = 13

    row1 = [
        ("HP", st.health, "health"),
        ("HNG", st.hunger, "hunger"),
        ("ENG", st.energy, "energy"),
        ("HYG", st.hygiene, "hygiene"),
    ]
    row2 = [
        ("SOC", st.social, "social"),
        ("FUN", st.fun, "fun"),
        ("BLD", st.bladder, "bladder"),
        ("MOOD", st.mood, "mood"),
    ]

    for i, (label, value, key) in enumerate(row1):
        x = margin + i * (bar_w + gap)
        _draw_stat_bar(d, x, 6, bar_w, bar_h, label, value, STAT_COLORS[key], ctx.font_s)

    for i, (label, value, key) in enumerate(row2):
        x = margin + i * (bar_w + gap)
        _draw_stat_bar(d, x, 23, bar_w, bar_h, label, value, STAT_COLORS[key], ctx.font_s)


def _format_age(age_seconds: float) -> str:
    age = max(0, int(age_seconds))
    if age < 3600:
        m = age // 60
        s = age % 60
        return f"{m}m {s}s"
    if age < 86400:
        h = age // 3600
        m = (age % 3600) // 60
        return f"{h}h {m}m"
    if age < 30 * 86400:
        d = age // 86400
        h = (age % 86400) // 3600
        return f"{d}d {h}h"
    mo = age // (30 * 86400)
    d = (age % (30 * 86400)) // 86400
    return f"{mo}mo {d}d"


def _mood_word(st: PetState) -> str:
    if st.hygiene < 24:
        return "Dirty"
    if st.energy < 24:
        return "Tired"
    if st.social < 30 or st.fun < 30:
        return "Misses You"
    if st.mood >= 72:
        return "Happy"
    if st.mood >= 44:
        return "Okay"
    return "Sad"


def _short_room(room: str) -> str:
    mapping = {
        ROOM_HUB: "Hall",
        ROOM_BED: "Bed",
        ROOM_LIVING: "Liv",
        ROOM_BATH: "Bath",
        ROOM_ARCADE: "Arc",
    }
    return mapping.get(str(room), str(room).title())


def _draw_room_minimap(d: ImageDraw.ImageDraw, x: int, y: int, st: PetState) -> None:
    node = 4
    gap = 4

    def _p(gx: int, gy: int) -> Tuple[int, int]:
        return (x + gx * (node + gap), y + gy * (node + gap))

    grid = {
        ROOM_BATH: (1, 0),
        ROOM_ARCADE: (0, 1),
        ROOM_HUB: (1, 1),
        ROOM_BED: (2, 1),
        ROOM_LIVING: (1, 2),
    }

    links = [
        (ROOM_HUB, ROOM_BATH),
        (ROOM_HUB, ROOM_ARCADE),
        (ROOM_HUB, ROOM_BED),
        (ROOM_HUB, ROOM_LIVING),
    ]
    for a, b in links:
        ax, ay = _p(*grid[a])
        bx, by = _p(*grid[b])
        d.line(
            [
                ax + node // 2,
                ay + node // 2,
                bx + node // 2,
                by + node // 2,
            ],
            fill=(228, 206, 198, 160),
            width=1,
        )

    for room, (gx, gy) in grid.items():
        nx, ny = _p(gx, gy)
        active = (room == st.room)
        fill = (255, 236, 224, 240) if active else (84, 68, 74, 220)
        out = (255, 220, 210, 220) if active else (200, 176, 168, 160)
        d.rounded_rectangle([nx, ny, nx + node, ny + node], radius=1, fill=fill, outline=out, width=1)


def _draw_vertical_edge_text(
    img: Image.Image,
    text: str,
    left: bool,
    y: int,
    font,
    fill: Tuple[int, int, int, int],
    x_left: int,
    x_right: int,
) -> None:
    if not text:
        return
    tmp = Image.new("RGBA", (100, 14), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    td.text((0, 0), text, font=font, fill=fill)
    bb = tmp.getbbox()
    if not bb:
        return
    core = tmp.crop(bb)
    rot = core.rotate(90 if left else 270, expand=True)
    x = x_left if left else max(x_left, x_right - rot.width)
    img.paste(rot, (x, y), rot)


def _draw_edge_room_hints(ctx, img: Image.Image, st: PetState) -> None:
    if st.panel_open:
        return

    room_info = ROOMS.get(st.room, ROOMS[ROOM_HUB])
    neigh = room_info.get("neighbors", {})
    d = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    sf = ctx.font_s
    play_l, play_top, play_r, play_bot = _play_rect((w, h))

    up = neigh.get("UP")
    if up:
        top = "^ " + _short_room(str(up))
        tw = int(d.textlength(top, font=sf))
        up_y = max(42, play_top - 12)
        d.text(((w - tw) // 2, up_y), top, font=sf, fill=(238, 220, 214, 186))

    down = neigh.get("DOWN")
    if down:
        bottom = "v " + _short_room(str(down))
        tw = int(d.textlength(bottom, font=sf))
        d.text(((w - tw) // 2, play_bot - 11), bottom, font=sf, fill=(238, 220, 214, 176))

    side_y = max(play_top + 18, ((play_top + play_bot) // 2) - 14)

    left = neigh.get("LEFT")
    if left:
        _draw_vertical_edge_text(
            img,
            _short_room(str(left)),
            left=True,
            y=side_y,
            font=sf,
            fill=(238, 220, 214, 164),
            x_left=play_l + 2,
            x_right=play_r - 2,
        )

    right = neigh.get("RIGHT")
    if right:
        _draw_vertical_edge_text(
            img,
            _short_room(str(right)),
            left=False,
            y=side_y,
            font=sf,
            fill=(238, 220, 214, 164),
            x_left=play_l + 2,
            x_right=play_r - 2,
        )


def _draw_blocked_edge_flash(img: Image.Image, st: PetState, now: float) -> None:
    until = float(st.edge_flash_until or 0.0)
    if now >= until:
        st.edge_flash_side = "NONE"
        return

    remain = max(0.0, until - now)
    frac = clamp(remain / BLOCK_FLASH_SECONDS, 0.0, 1.0)
    alpha = int(220 * frac)
    if alpha <= 0:
        return

    x0, y0, x1, y1 = _play_rect(img.size)
    side = str(st.edge_flash_side or "NONE").upper()
    d = ImageDraw.Draw(img, "RGBA")
    color = (255, 82, 82, alpha)
    glow = (255, 82, 82, int(alpha * 0.45))

    if side == "LEFT":
        d.rectangle([x0 - 1, y0 + 2, x0 + 3, y1 - 2], fill=glow)
        d.line([x0 + 1, y0 + 2, x0 + 1, y1 - 2], fill=color, width=2)
    elif side == "RIGHT":
        d.rectangle([x1 - 3, y0 + 2, x1 + 1, y1 - 2], fill=glow)
        d.line([x1 - 1, y0 + 2, x1 - 1, y1 - 2], fill=color, width=2)
    elif side == "UP":
        d.rectangle([x0 + 2, y0 - 1, x1 - 2, y0 + 3], fill=glow)
        d.line([x0 + 2, y0 + 1, x1 - 2, y0 + 1], fill=color, width=2)
    elif side == "DOWN":
        d.rectangle([x0 + 2, y1 - 3, x1 - 2, y1 + 1], fill=glow)
        d.line([x0 + 2, y1 - 1, x1 - 2, y1 - 1], fill=color, width=2)


def _add_months(dt: datetime, months: int) -> datetime:
    total = (dt.year * 12) + (dt.month - 1) + int(months)
    y = total // 12
    m = (total % 12) + 1
    day = min(dt.day, 28)
    return dt.replace(year=y, month=m, day=day)


def _together_start(now_dt: datetime) -> datetime:
    start = datetime(now_dt.year, 11, 2, 0, 0, 0)
    if now_dt < start:
        start = datetime(now_dt.year - 1, 11, 2, 0, 0, 0)
    return start


def _format_together_elapsed(now_dt: datetime) -> str:
    start = _together_start(now_dt)
    years = 0
    while _add_months(start, (years + 1) * 12) <= now_dt:
        years += 1
    anchor = _add_months(start, years * 12)
    months = 0
    while _add_months(anchor, 1) <= now_dt:
        months += 1
        anchor = _add_months(anchor, 1)

    rem = now_dt - anchor
    days = int(rem.days)
    hours = int(rem.seconds // 3600)
    mins = int((rem.seconds % 3600) // 60)
    return f"{years}Y {months}M {days}D {hours:02d}H {mins:02d}M"


def _birthday_countdown(now_dt: datetime, month: int, day: int) -> str:
    target = datetime(now_dt.year, month, day, 0, 0, 0)
    if target <= now_dt:
        target = datetime(now_dt.year + 1, month, day, 0, 0, 0)
    delta = target - now_dt
    d = int(delta.days)
    h = int(delta.seconds // 3600)
    return f"{d}D {h:02d}H"


def _draw_hub_couple_stats(ctx, img: Image.Image, st: PetState, now: float) -> None:
    if st.room != ROOM_HUB or st.panel_open:
        return
    d = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    play_l, _play_t, play_r, play_b = _play_rect((w, h))

    now_dt = datetime.fromtimestamp(now)
    together = _format_together_elapsed(now_dt)
    rahil_bday = _birthday_countdown(now_dt, 3, 1)
    dianna_bday = _birthday_countdown(now_dt, 7, 31)
    hugs = int(st.hugs_given)
    cuddles = int(st.cuddles_shared)
    chats = int(st.talk_sessions)
    dates = int(st.arcade_sessions)

    lines = [
        f"T {together} | R {rahil_bday} | D {dianna_bday}",
        f"H{hugs} C{cuddles} T{chats} A{dates}",
    ]
    max_w = max(10, (play_r - play_l) - 8)

    def _fit(line: str) -> str:
        txt = str(line)
        while txt and d.textlength(txt, font=ctx.font_s) > max_w:
            txt = txt[:-1]
        return txt

    y = play_b - 22
    for line in lines:
        line = _fit(line)
        d.text((play_l + 1, y), line, font=ctx.font_s, fill=(8, 6, 8, 85))
        d.text((play_l, y), line, font=ctx.font_s, fill=(244, 232, 226, 108))
        y += 10


def _draw_top_info(ctx, img: Image.Image, st: PetState) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    w, _h = img.size
    mf = _meta_font(ctx)
    _draw_room_minimap(d, 10, 40, st)

    room_name = str(ROOMS.get(st.room, ROOMS[ROOM_HUB]).get("name", st.room))
    room_x = 35
    info_y = 44
    age_text = _format_age(st.age_seconds)
    age_tw = int(d.textlength(age_text, font=mf))
    age_x = w - 10 - age_tw
    max_room_w = max(20, age_x - room_x - 8)
    while room_name and d.textlength(room_name, font=mf) > max_room_w:
        room_name = room_name[:-1]
    if not room_name:
        room_name = str(st.room)
    d.text((room_x, info_y), room_name, font=mf, fill=(245, 234, 228, 228))

    d.text((age_x, info_y), age_text, font=mf, fill=(232, 210, 202, 224))

    # Mood word intentionally removed from top line to keep header uncluttered.


def _sprite_for_state(st: PetState, sprites: Dict[str, object], moving: bool, now: float) -> Image.Image:
    idle = sprites.get("idle")
    if not isinstance(idle, Image.Image):
        idle = _placeholder_sprite(46, "idle")

    def _pick(frames_obj, idx: int) -> Optional[Image.Image]:
        if not isinstance(frames_obj, list) or not frames_obj:
            return None
        frame = frames_obj[idx % len(frames_obj)]
        return frame if isinstance(frame, Image.Image) else None

    def _pick_dir(base: str, idx: int) -> Optional[Image.Image]:
        side = "l" if int(st.facing) < 0 else "r"
        fr = _pick(sprites.get(f"{base}_{side}"), idx)
        if fr is not None:
            return fr
        return _pick(sprites.get(base), idx)

    if moving:
        st.sad_idle_t0 = 0.0
        key = "walk_anim_l" if int(st.facing) < 0 else "walk_anim_r"
        idx = int(st.walk_phase * (float(ANIM_FPS.get("walk", 5.8)) / 8.0))
        fr = _pick(sprites.get(key), idx)
        if fr is not None:
            return fr
        w1 = sprites.get("walk1")
        w2 = sprites.get("walk2")
        if int(st.walk_phase) % 2 == 0 and isinstance(w1, Image.Image):
            return w1
        if isinstance(w2, Image.Image):
            return w2
        return idle

    pose_deadline = now < float(st.pose_until)
    if st.pose == "sleep" and now < st.pose_until:
        fr = _pick_dir("sleeping_anim", int(now * float(ANIM_FPS.get("sleeping", 4.0))))
        if fr is not None:
            return fr
        sleep = sprites.get("sleep")
        return sleep if isinstance(sleep, Image.Image) else idle

    if st.pose == "shower" and now < st.pose_until:
        fr = _pick_dir("shower_anim", int(now * float(ANIM_FPS.get("shower", 5.0))))
        if fr is not None:
            return fr
        sh = sprites.get("shower")
        return sh if isinstance(sh, Image.Image) else idle

    if st.pose == "changing" and now < st.pose_until:
        fr = _pick_dir("changing_anim", int(now * float(ANIM_FPS.get("changing", 4.9))))
        if fr is not None:
            return fr
        return idle

    if st.pose == "hugcuddle" and pose_deadline:
        fr = _pick_dir("hugcuddle_anim", int(now * float(ANIM_FPS.get("hugcuddle", 4.8))))
        if fr is not None:
            return fr
        return _pick_dir("talking_anim", int(now * float(ANIM_FPS.get("talking", 5.7)))) or idle

    if st.pose == "talk" and now < st.pose_until:
        fr = _pick_dir("talking_anim", int(now * float(ANIM_FPS.get("talking", 5.7))))
        if fr is not None:
            return fr
        return idle

    if st.pose == "toilet" and now < st.pose_until:
        tl = sprites.get("toilet")
        if isinstance(tl, Image.Image):
            if int(st.facing) < 0:
                return ImageOps.mirror(tl)
            return tl
        return idle

    idle_for = 0.0
    if st.last_move_at > 0.0:
        idle_for = max(0.0, now - float(st.last_move_at))

    low_stats = (
        st.health < 55.0
        or st.mood < 55.0
        or st.hunger < 45.0
        or st.energy < 45.0
        or st.hygiene < 45.0
        or st.social < 40.0
        or st.fun < 40.0
        or st.bladder < 45.0
    )

    if st.room == ROOM_ARCADE:
        fr = _pick_dir("gaming_anim", int(now * float(ANIM_FPS.get("gaming", 5.1))))
        if fr is not None:
            return fr

    if low_stats:
        sad_key = "idle_sad_anim_l" if int(st.facing) < 0 else "idle_sad_anim_r"
        sad_frames = sprites.get(sad_key)
        if not isinstance(sad_frames, list):
            sad_frames = sprites.get("idle_sad_anim")
        if isinstance(sad_frames, list) and sad_frames:
            if st.sad_idle_t0 <= 0.0:
                st.sad_idle_t0 = now
            elapsed = max(0.0, now - float(st.sad_idle_t0))
            fps = float(ANIM_FPS.get("idle_sad", 4.7))
            n = len(sad_frames)
            intro_seconds = float(n) / fps
            if n <= 5:
                idx = int(elapsed * fps) % n
            elif elapsed < intro_seconds:
                idx = min(n - 1, int(elapsed * fps))
            else:
                loop_span = max(1, n - 5)
                idx = 5 + (int((elapsed - intro_seconds) * fps) % loop_span)
            fr = _pick(sad_frames, idx)
            if fr is not None:
                return fr
    else:
        st.sad_idle_t0 = 0.0

    if idle_for >= IDLE_SIT_SECONDS:
        fr = _pick_dir("idle_sit_anim", int(now * float(ANIM_FPS.get("idle_sit", 4.2))))
        if fr is not None:
            return fr

    fr = _pick_dir("idle_happy_anim", int(now * float(ANIM_FPS.get("idle_happy", 4.9))))
    if fr is not None:
        return fr

    if low_stats:
        fr = _pick_dir("idle_sad_anim", int(now * float(ANIM_FPS.get("idle_sad", 4.7))))
        if fr is not None:
            return fr

    if int(st.facing) < 0:
        return ImageOps.mirror(idle)
    return idle


def _draw_action_panel(ctx, img: Image.Image, st: PetState, dialogue: Dict[str, List[Dict]]) -> Image.Image:
    w, h = img.size
    play_l, play_t, play_r, play_b = _play_rect((w, h))
    panel_h = 84
    panel_y0 = max(play_t + 20, play_b - panel_h)
    rect = (play_l + 2, panel_y0, play_r - 2, play_b - 2)
    img = overlay_panel(img, rect, radius=6, fill=(8, 6, 10, 168), outline=(255, 220, 210, 105), width=1)
    d = ImageDraw.Draw(img)
    of = _overlay_font(ctx)

    x0, y0, x1, _y1 = rect
    if st.panel_kind == "TALK":
        title = "Talk"
    elif st.panel_kind == "SNACK":
        title = "Snack"
    else:
        title = "Actions"
    d.text((x0 + 10, y0 + 6), title, font=of, fill=(252, 240, 234))

    items = _panel_items(st, dialogue)
    if not items:
        d.text((x0 + 10, y0 + 28), "No options", font=of, fill=(240, 210, 198))
        return img

    vis = 3
    sel = int(clamp(float(st.panel_sel), 0.0, float(len(items) - 1)))
    start = max(0, min(sel - 1, max(0, len(items) - vis)))
    y = y0 + 30

    for idx in range(start, min(len(items), start + vis)):
        item = items[idx]
        selected = idx == sel
        if selected:
            d.rounded_rectangle([x0 + 8, y - 2, x1 - 8, y + 16], radius=4, fill=(245, 232, 225))
            fg = (24, 14, 12)
        else:
            fg = (236, 222, 215)

        name = str(item).replace("_", " ").title() if st.panel_kind == "TALK" else str(item)
        d.text((x0 + 12, y), name, font=of, fill=fg)
        y += 18

    hint = "B1 confirm"
    tw = int(d.textlength(hint, font=of))
    d.text((x1 - 10 - tw, y0 + 6), hint, font=of, fill=(225, 205, 197))
    return img


def _draw_top_center_text(ctx, img: Image.Image, text: str) -> None:
    if not text:
        return

    d = ImageDraw.Draw(img)
    of = _overlay_font(ctx)
    w, _h = img.size
    lines = wrap_text(d, text, of, max_width=w - 24)[:2]
    y = 62

    for line in lines:
        tw = int(d.textlength(line, font=of))
        x = (w - tw) // 2
        d.text((x + 1, y + 1), line, font=of, fill=(10, 8, 8, 220))
        d.text((x, y), line, font=of, fill=(248, 238, 232, 235))
        y += 15


def _draw_k2_exit_overlay(ctx, img: Image.Image, st: PetState, now: float) -> Image.Image:
    t0 = float(st.k2_hold_t0 or 0.0)
    if t0 <= 0.0 or (not ctx.inputs.is_down("K2")):
        return img

    held = max(0.0, now - t0)
    if held < K2_EXIT_SHOW_DELAY:
        return img

    denom = max(0.001, K2_EXIT_HOLD_SECONDS - K2_EXIT_SHOW_DELAY)
    p = clamp((held - K2_EXIT_SHOW_DELAY) / denom, 0.0, 1.0)

    w, h = img.size
    rect = (18, h - 52, w - 19, h - 16)
    img = overlay_panel(img, rect, radius=6, fill=(10, 8, 12, 176), outline=(255, 220, 210, 120), width=1)
    d = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = rect

    label = "Hold B2 to Exit Game"
    tw = int(d.textlength(label, font=ctx.font_s))
    d.text((x0 + ((x1 - x0 - tw) // 2), y0 + 6), label, font=ctx.font_s, fill=(245, 232, 226))

    bar_x0 = x0 + 10
    bar_x1 = x1 - 10
    bar_y0 = y0 + 22
    bar_y1 = y0 + 30
    d.rounded_rectangle([bar_x0, bar_y0, bar_x1, bar_y1], radius=3, fill=(30, 24, 26, 210), outline=(255, 220, 210, 90), width=1)
    fill_w = int((bar_x1 - bar_x0 - 2) * p)
    if fill_w > 0:
        d.rounded_rectangle([bar_x0 + 1, bar_y0 + 1, bar_x0 + 1 + fill_w, bar_y1 - 1], radius=2, fill=(255, 176, 160, 230))

    hint = "Release to cancel"
    hw = int(d.textlength(hint, font=ctx.font_s))
    d.text((x0 + ((x1 - x0 - hw) // 2), y0 + 33), hint, font=ctx.font_s, fill=(220, 205, 198))
    return img


def _dialogue_scene_text(st: PetState) -> str:
    if not st.dialogue_active:
        return ""
    if st.dialogue_line_idx < 0 or st.dialogue_line_idx >= len(st.dialogue_queue):
        return ""
    line = _dialogue_line_text(st.dialogue_queue[st.dialogue_line_idx])
    if not line:
        return ""
    chars = int(clamp(float(st.dialogue_char_idx), 0.0, float(len(line))))
    out = line[:chars]
    if chars < len(line):
        out += "▌"
    return out


def _memory_thumb(ctx, key: str, size: Tuple[int, int]) -> Image.Image:
    tw = max(8, int(size[0]))
    th = max(8, int(size[1]))
    k = str(key or "")
    if not k or k.startswith("fallback:"):
        img = Image.new("RGB", (tw, th), (58, 46, 44))
        d = ImageDraw.Draw(img)
        label = "?"
        lw = int(d.textlength(label, font=ctx.font_m))
        d.text(((tw - lw) // 2, max(0, (th // 2) - 8)), label, font=ctx.font_m, fill=(246, 230, 224))
        return img

    try:
        mtime = int(os.path.getmtime(k))
    except Exception:
        mtime = 0
    cache_key = f"{k}:{mtime}:{tw}x{th}"
    cache = ctx.user.get("_pet_memory_thumb_cache", {})
    if isinstance(cache, dict):
        hit = cache.get(cache_key)
        if isinstance(hit, Image.Image):
            return hit.copy()
    else:
        cache = {}

    out = Image.new("RGB", (tw, th), (18, 14, 16))
    try:
        src = Image.open(k).convert("RGB")
        resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
        src.thumbnail((tw, th), resample)
        x = (tw - src.width) // 2
        y = (th - src.height) // 2
        out.paste(src, (x, y))
    except Exception:
        d = ImageDraw.Draw(out)
        d.text((4, 4), "Load", font=ctx.font_s, fill=(255, 182, 176))

    cache[cache_key] = out.copy()
    if len(cache) > 80:
        cache = {cache_key: out.copy()}
    ctx.user["_pet_memory_thumb_cache"] = cache
    return out


def _draw_minigame_overlay(ctx, img: Image.Image, st: PetState) -> Image.Image:
    name = str(st.minigame_name or "")
    if not name:
        return img

    now = time.time()
    w, h = img.size
    rect = (2, 2, w - 3, h - 3)
    img = overlay_panel(img, rect, radius=6, fill=(0, 0, 0, 255), outline=(255, 220, 210, 95), width=1)
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = rect
    d.text((x0 + 8, y0 + 4), name, font=ctx.font_s, fill=(250, 238, 232))
    d.text((x1 - 8 - int(d.textlength("B2 exit", font=ctx.font_s)), y0 + 4), "B2 exit", font=ctx.font_s, fill=(222, 208, 200))

    mg = st.minigame_state if isinstance(st.minigame_state, dict) else {}
    cx0, cy0 = x0 + 4, y0 + 16
    cx1, cy1 = x1 - 4, y1 - 6

    if name == "Brick Breaker":
        for b in list(mg.get("bricks", [])):
            if not b.get("alive", False):
                continue
            bx0 = int(b.get("x", 0))
            by0 = int(b.get("y", 0))
            bw = int(b.get("w", 18))
            bh = int(b.get("h", 10))
            hp = int(b.get("hp", 1))
            fill = (255, 176, 120) if hp <= 1 else (255, 132, 102)
            d.rounded_rectangle([bx0, by0, bx0 + bw, by0 + bh], radius=2, fill=fill, outline=(255, 234, 214), width=1)

        paddle_x = int(mg.get("paddle_x", w // 2))
        paddle_y = h - 14
        d.rounded_rectangle([paddle_x - 21, paddle_y, paddle_x + 21, paddle_y + 6], radius=2, fill=(238, 226, 220))
        ball_x = int(mg.get("ball_x", w // 2))
        ball_y = int(mg.get("ball_y", h // 2))
        d.ellipse([ball_x - 3, ball_y - 3, ball_x + 3, ball_y + 3], fill=(255, 240, 232))
        score = int(mg.get("score", 0))
        d.text((cx0, cy1 - 12), f"Score {score}", font=ctx.font_s, fill=(238, 228, 220))
        level = int(mg.get("level", 1))
        max_levels = int(mg.get("max_levels", BRICK_MAX_LEVELS))
        lvl = f"L{level}/{max_levels}"
        d.text((cx1 - int(d.textlength(lvl, font=ctx.font_s)), cy1 - 12), lvl, font=ctx.font_s, fill=(238, 228, 220))
        if now < float(mg.get("level_up_until", 0.0)):
            up = "LEVEL UP"
            uw = int(d.textlength(up, font=ctx.font_m))
            d.text(((w - uw) // 2, y0 + 16), up, font=ctx.font_m, fill=(255, 232, 200))

    elif name == "Memory Match":
        cards = list(mg.get("cards", []))
        card_keys = list(mg.get("card_keys", []))
        matched = list(mg.get("matched", [False] * 6))
        revealed = set(mg.get("revealed", []))
        cursor = int(mg.get("cursor", 0))
        cols, rows = 3, 2
        gw = cx1 - cx0
        gh = cy1 - cy0
        cw = max(20, (gw - 10) // cols)
        ch = max(20, (gh - 8) // rows)
        for i in range(min(6, len(cards))):
            r, c = divmod(i, cols)
            bx = cx0 + c * (cw + 3)
            by = cy0 + r * (ch + 4)
            is_open = bool(matched[i]) or (i in revealed)
            fill = (238, 228, 220) if is_open else (42, 36, 44)
            fg = (18, 12, 10) if is_open else (236, 220, 212)
            out = (255, 220, 210) if i == cursor else (150, 128, 120)
            d.rounded_rectangle([bx, by, bx + cw, by + ch], radius=4, fill=fill, outline=out, width=2 if i == cursor else 1)
            if is_open:
                key_idx = int(cards[i]) if i < len(cards) else -1
                key = card_keys[key_idx] if 0 <= key_idx < len(card_keys) else f"fallback:{key_idx}"
                thumb = _memory_thumb(ctx, str(key), (max(8, cw - 4), max(8, ch - 4)))
                img.paste(thumb, (bx + 2, by + 2))
            else:
                label = "?"
                lw = int(d.textlength(label, font=ctx.font_m))
                d.text((bx + (cw - lw) // 2, by + (ch // 2) - 8), label, font=ctx.font_m, fill=fg)
        d.text((cx0, cy1 - 12), f"Moves {int(mg.get('moves', 0))}", font=ctx.font_s, fill=(238, 228, 220))

    elif name == "Runner Dash":
        ground = h - 26
        d.line([cx0, ground, cx1, ground], fill=(236, 224, 216), width=2)
        player_y = int(mg.get("player_y", ground))
        d.rounded_rectangle([34, player_y - 16, 46, player_y], radius=2, fill=(255, 214, 184), outline=(255, 242, 234), width=1)
        for o in list(mg.get("obstacles", [])):
            ox = int(o.get("x", w))
            ow = int(o.get("w", 12))
            oh = int(o.get("h", 14))
            d.rounded_rectangle([ox, ground - oh, ox + ow, ground], radius=2, fill=(232, 120, 120), outline=(255, 220, 220), width=1)
        score = int(mg.get("score", 0))
        d.text((cx0, cy1 - 12), f"Score {score}", font=ctx.font_s, fill=(238, 228, 220))

    elif name == "Micro Snake":
        grid_w = max(8, int(mg.get("grid_w", 14)))
        grid_h = max(8, int(mg.get("grid_h", 14)))
        area_w = max(20, cx1 - cx0)
        area_h = max(20, cy1 - cy0 - 12)
        cell = max(6, min(area_w // grid_w, area_h // grid_h))
        gw = cell * grid_w
        gh = cell * grid_h
        sx = cx0 + (area_w - gw) // 2
        sy = cy0 + max(0, (area_h - gh) // 2)
        d.rectangle([sx - 1, sy - 1, sx + gw + 1, sy + gh + 1], outline=(255, 220, 210, 120), width=1)
        snake = [[int(p[0]), int(p[1])] for p in list(mg.get("snake", [])) if isinstance(p, list) and len(p) >= 2]
        for idx, seg in enumerate(snake):
            fx = sx + (seg[0] * cell)
            fy = sy + (seg[1] * cell)
            fill = (255, 214, 150) if idx == 0 else (238, 190, 120)
            d.rectangle([fx + 1, fy + 1, fx + cell - 2, fy + cell - 2], fill=fill)
        food = list(mg.get("food", [0, 0]))
        if len(food) >= 2:
            fx = sx + (int(food[0]) * cell)
            fy = sy + (int(food[1]) * cell)
            d.ellipse([fx + 1, fy + 1, fx + cell - 2, fy + cell - 2], fill=(255, 120, 120))
        score = int(mg.get("score", 0))
        d.text((cx0, cy1 - 12), f"Food {score}/25", font=ctx.font_s, fill=(238, 228, 220))
    elif name == "Heart Catch":
        basket_x = int(mg.get("basket_x", w // 2))
        basket_y = h - 24
        d.rounded_rectangle([basket_x - 14, basket_y, basket_x + 14, basket_y + 6], radius=2, fill=(255, 226, 196))
        for item in list(mg.get("items", [])):
            ix = int(item.get("x", 0))
            iy = int(item.get("y", 0))
            kind = str(item.get("kind", "heart"))
            if kind == "bomb":
                d.ellipse([ix - 4, iy - 4, ix + 4, iy + 4], fill=(148, 148, 148), outline=(220, 220, 220))
            else:
                d.polygon(
                    [
                        (ix, iy + 4),
                        (ix - 4, iy - 1),
                        (ix - 2, iy - 4),
                        (ix, iy - 2),
                        (ix + 2, iy - 4),
                        (ix + 4, iy - 1),
                    ],
                    fill=(255, 120, 140),
                )
        lives = int(mg.get("lives", 3))
        score = int(mg.get("score", 0))
        d.text((cx0, cy1 - 12), f"Score {score}", font=ctx.font_s, fill=(238, 228, 220))
        lives_txt = f"Lives {lives}"
        d.text((cx1 - int(d.textlength(lives_txt, font=ctx.font_s)), cy1 - 12), lives_txt, font=ctx.font_s, fill=(238, 228, 220))
    else:  # Reflex Tap
        lane_y = (cy0 + cy1) // 2
        lane_l = 18
        lane_r = w - 18
        d.line([lane_l, lane_y, lane_r, lane_y], fill=(236, 224, 216), width=2)
        zone_x = int(mg.get("zone_x", 80))
        zone_w = int(mg.get("zone_w", 26))
        d.rectangle([zone_x, lane_y - 7, zone_x + zone_w, lane_y + 7], outline=(120, 220, 160), width=2)
        marker_x = int(mg.get("marker_x", lane_l))
        d.line([marker_x, lane_y - 10, marker_x, lane_y + 10], fill=(255, 212, 148), width=2)
        score = int(mg.get("score", 0))
        round_idx = int(mg.get("round", 1))
        max_rounds = int(mg.get("max_rounds", 10))
        d.text((cx0, cy1 - 12), f"Score {score}", font=ctx.font_s, fill=(238, 228, 220))
        rr = f"R{min(round_idx, max_rounds)}/{max_rounds}"
        d.text((cx1 - int(d.textlength(rr, font=ctx.font_s)), cy1 - 12), rr, font=ctx.font_s, fill=(238, 228, 220))
        result = str(mg.get("result", ""))
        if result and now < float(mg.get("result_until", 0.0)):
            rw = int(d.textlength(result, font=ctx.font_s))
            d.text(((w - rw) // 2, lane_y + 14), result, font=ctx.font_s, fill=(255, 236, 214))

    return img


def _draw_game_over(ctx, st: PetState, size: Tuple[int, int]) -> Image.Image:
    w, h = int(size[0]), int(size[1])
    img = Image.new("RGB", (w, h), (36, 0, 0))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / float(max(1, h - 1))
        r = int(86 + (64 * t))
        g = int(4 + (8 * t))
        b = int(4 + (8 * t))
        d.line([0, y, w, y], fill=(r, g, b), width=1)

    d.rounded_rectangle([10, 22, w - 11, h - 24], radius=8, fill=(16, 0, 0), outline=(255, 180, 180), width=2)

    title = "GAME OVER"
    msg = "You did not take care of him."
    hint = "B1 / PRESS to restart"
    reason = ""
    if st.death_reason:
        reason = f"Cause: low {str(st.death_reason)}"

    tw = int(d.textlength(title, font=ctx.font_l))
    d.text(((w - tw) // 2, 38), title, font=ctx.font_l, fill=(255, 232, 232))

    mw = int(d.textlength(msg, font=ctx.font_s))
    d.text(((w - mw) // 2, 76), msg, font=ctx.font_s, fill=(255, 214, 214))

    if reason:
        rw = int(d.textlength(reason, font=ctx.font_s))
        d.text(((w - rw) // 2, 96), reason, font=ctx.font_s, fill=(245, 190, 190))

    hw = int(d.textlength(hint, font=ctx.font_s))
    d.text(((w - hw) // 2, h - 48), hint, font=ctx.font_s, fill=(255, 236, 236))
    return img


def render(ctx) -> Image.Image:
    st = _st(ctx)
    w, h = int(ctx.disp.width), int(ctx.disp.height)
    now = time.time()

    if st.mode == MODE_ONBOARD_1:
        img = _load_intro_slide(ctx, ONBOARD_WELCOME, "Welcome to Pocket R", (w, h))
        d = ImageDraw.Draw(img)
        hint = "B1/PRESS next   B2 exit"
        tw = int(d.textlength(hint, font=ctx.font_s))
        d.text((w - tw - 10, h - 18), hint, font=ctx.font_s, fill=(245, 232, 226))
        return img

    if st.mode == MODE_ONBOARD_2:
        img = _load_intro_slide(ctx, ONBOARD_CONTROLS, "Controls", (w, h))
        d = ImageDraw.Draw(img)
        hint = "B1/PRESS start   B2 exit"
        tw = int(d.textlength(hint, font=ctx.font_s))
        d.text((w - tw - 10, h - 18), hint, font=ctx.font_s, fill=(245, 232, 226))
        return img

    if st.play_submode == PLAY_MINIGAME:
        img = Image.new("RGB", (w, h), (0, 0, 0))
        img = _draw_minigame_overlay(ctx, img, st)
        return img

    if not st.alive:
        return _draw_game_over(ctx, st, (w, h))

    img = _load_layered_room(ctx, st.room, (w, h)).convert("RGB")
    _draw_stats(ctx, img, st)
    _draw_top_info(ctx, img, st)

    sprites = _load_sprites(ctx)

    moving = False
    if st.alive and not st.panel_open and now >= st.pose_until:
        moving = (
            ctx.inputs.is_down("LEFT")
            or ctx.inputs.is_down("RIGHT")
            or ctx.inputs.is_down("UP")
            or ctx.inputs.is_down("DOWN")
        )

    sprite = _sprite_for_state(st, sprites, moving=moving, now=now)
    if not st.alive:
        sprite = sprite.convert("RGBA")
        tint = Image.new("RGBA", sprite.size, (40, 40, 40, 170))
        sprite = Image.alpha_composite(sprite, tint)

    room_info = ROOMS.get(st.room, ROOMS[ROOM_HUB])
    neigh = room_info.get("neighbors", {})
    left_inset = 0.0
    right_inset = 0.0
    if moving and bool(neigh.get("LEFT")) and ctx.inputs.is_down("LEFT"):
        left_inset = ROOM_SWITCH_INSET_X
    if moving and bool(neigh.get("RIGHT")) and ctx.inputs.is_down("RIGHT"):
        right_inset = ROOM_SWITCH_INSET_X

    draw_x = _clamp_sprite_x_for_frame(ctx, st.x, sprite, left_inset=left_inset, right_inset=right_inset)
    px = int(draw_x - (sprite.width // 2))
    py = int(st.y - (sprite.height // 2)) if st.pose == "sleep" else int(st.y - sprite.height)
    x0, y0, x1, y1 = _play_rect((w, h))
    _paste_sprite_clipped(img, sprite, px, py, (x0 + 2, y0 + 2, x1 - 1, y1 - 1))

    fg = _load_room_foreground(ctx, st.room, (w, h))
    if isinstance(fg, Image.Image):
        img_rgba = Image.alpha_composite(img.convert("RGBA"), fg)
        img = img_rgba.convert("RGB")

    _draw_blocked_edge_flash(img, st, now)

    if st.pose == "toilet" and now < st.blur_until:
        img = img.filter(ImageFilter.GaussianBlur(2.2))
        d = ImageDraw.Draw(img)
        text = "Woah look away"
        tw = int(d.textlength(text, font=ctx.font_l))
        d.text(((w - tw) // 2, (h // 2) - 10), text, font=ctx.font_l, fill=(255, 245, 238))

    if st.dialogue_active:
        _draw_top_center_text(ctx, img, _dialogue_scene_text(st))
    elif st.msg:
        _draw_top_center_text(ctx, img, st.msg)

    if st.panel_open and (not st.dialogue_active):
        img = _draw_action_panel(ctx, img, st, _dialogue_data(ctx))

    img = _draw_k2_exit_overlay(ctx, img, st, now)
    return img
